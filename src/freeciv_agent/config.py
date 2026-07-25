"""Versioned FreeCiv capability configuration.

M7 conditions are data, not separate code forks.  This module validates the
condition matrix and exposes an immutable copy to runners and manifests.
"""

import copy
import os

import yaml

from .paths import repo_path


DEFAULT_CONFIG_PATH = repo_path("profile", "freeciv_agent.yaml")

CAPABILITIES = (
    "authoritative_state",
    "dependency_oracle",
    "scheduler",
    "uncertain_beliefs",
    "assumption_monitor",
    "constrained_llm",
)

CONDITION_ORDER = (
    "a_stock_llm",
    "b_state_oracle",
    "c_dependency_scheduler",
    "d_uncertain_monitor",
    "e_full_loop",
)

_DEPENDENCIES = {
    "dependency_oracle": ("authoritative_state",),
    "scheduler": ("authoritative_state", "dependency_oracle"),
    "uncertain_beliefs": ("authoritative_state", "dependency_oracle"),
    "assumption_monitor": ("uncertain_beliefs", "scheduler"),
    "constrained_llm": ("authoritative_state", "dependency_oracle", "scheduler"),
}


class FreecivConfigError(ValueError):
    """Configuration is missing, ambiguous, or violates a capability gate."""


def _read_yaml(path):
    try:
        with open(path, encoding="utf-8") as stream:
            value = yaml.safe_load(stream) or {}
    except OSError as exc:
        raise FreecivConfigError("cannot read FreeCiv agent config {}: {}".format(path, exc))
    if not isinstance(value, dict):
        raise FreecivConfigError("FreeCiv agent config root must be an object")
    return value


def validate_config(data):
    """Validate and return ``data``; raises :class:`FreecivConfigError`."""
    if data.get("schema_version") != "1.0":
        raise FreecivConfigError("schema_version must be '1.0'")
    conditions = data.get("conditions")
    if not isinstance(conditions, dict):
        raise FreecivConfigError("conditions must be an object")
    missing = [name for name in CONDITION_ORDER if name not in conditions]
    extra = sorted(set(conditions) - set(CONDITION_ORDER))
    if missing or extra:
        raise FreecivConfigError("condition set mismatch: missing={} extra={}".format(missing, extra))

    previous = set()
    for name in CONDITION_ORDER:
        row = conditions[name]
        if not isinstance(row, dict):
            raise FreecivConfigError("condition {} must be an object".format(name))
        if not isinstance(row.get("description"), str) or not row["description"].strip():
            raise FreecivConfigError("condition {} needs a description".format(name))
        caps = row.get("capabilities")
        if not isinstance(caps, dict):
            raise FreecivConfigError("condition {} capabilities must be an object".format(name))
        if set(caps) != set(CAPABILITIES):
            raise FreecivConfigError(
                "condition {} capability keys must be exactly {}".format(name, list(CAPABILITIES)))
        non_bool = sorted(key for key, value in caps.items() if not isinstance(value, bool))
        if non_bool:
            raise FreecivConfigError("condition {} non-boolean capabilities: {}".format(name, non_bool))
        enabled = {key for key, value in caps.items() if value}
        for capability in enabled:
            absent = [dep for dep in _DEPENDENCIES.get(capability, ()) if dep not in enabled]
            if absent:
                raise FreecivConfigError(
                    "condition {} enables {} without {}".format(name, capability, absent))
        if name != "a_stock_llm" and not previous.issubset(enabled):
            raise FreecivConfigError(
                "condition {} removes capabilities present in the previous condition: {}".format(
                    name, sorted(previous - enabled)))
        previous = enabled

    if any(conditions["a_stock_llm"]["capabilities"].values()):
        raise FreecivConfigError("a_stock_llm must not enable target-agent capabilities")
    if not all(conditions["e_full_loop"]["capabilities"].values()):
        raise FreecivConfigError("e_full_loop must enable every target-agent capability")

    defaults = data.get("defaults")
    if not isinstance(defaults, dict):
        raise FreecivConfigError("defaults must be an object")
    if defaults.get("condition") not in CONDITION_ORDER:
        raise FreecivConfigError("defaults.condition must name a known condition")
    if defaults.get("events_schema_version") != "1.0":
        raise FreecivConfigError("defaults.events_schema_version must be '1.0'")
    beliefs = data.get("beliefs")
    if not isinstance(beliefs, dict) or beliefs.get("schema_version") != "1.0":
        raise FreecivConfigError("beliefs.schema_version must be '1.0'")
    for key in (
            "actionable_threshold", "minimum_logged_confidence", "dampening_lambda",
            "observation_strength", "observation_confidence",
            "abduction_strength", "abduction_confidence",
            "induction_default_probability", "induction_decision_threshold",
            "conflict_min_confidence", "conflict_severity_threshold",
            "simulation_confidence_cap", "selection_unknown_discount"):
        value = beliefs.get(key)
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise FreecivConfigError("beliefs.{} must be in [0,1]".format(key))
    if (not isinstance(beliefs.get("induction_minimum_samples"), int)
            or beliefs["induction_minimum_samples"] < 1):
        raise FreecivConfigError("beliefs.induction_minimum_samples must be a positive integer")
    decay = beliefs.get("decay")
    if not isinstance(decay, dict) or "default" not in decay:
        raise FreecivConfigError("beliefs.decay.default is required")
    for predicate, schedule in decay.items():
        if (not isinstance(schedule, dict)
                or schedule.get("formula") != "linear-window"
                or not isinstance(schedule.get("window_turns"), int)
                or schedule["window_turns"] <= 0):
            raise FreecivConfigError("invalid decay schedule for {}".format(predicate))
    sweep = beliefs.get("sweep")
    if not isinstance(sweep, dict):
        raise FreecivConfigError("beliefs.sweep is required")
    for key in ("dampening_lambda", "actionable_threshold", "decay_window_multiplier"):
        if not isinstance(sweep.get(key), list) or not sweep[key]:
            raise FreecivConfigError("beliefs.sweep.{} must be nonempty".format(key))
    return data


def load_config(path=None):
    """Load, validate, and deep-copy the versioned configuration."""
    resolved = os.path.abspath(path or os.environ.get("FREECIV_AGENT_CONFIG", DEFAULT_CONFIG_PATH))
    return copy.deepcopy(validate_config(_read_yaml(resolved)))


def condition(condition_id, path=None):
    """Return one validated condition with its ID embedded."""
    data = load_config(path)
    if condition_id not in data["conditions"]:
        raise FreecivConfigError("unknown FreeCiv condition: {}".format(condition_id))
    value = copy.deepcopy(data["conditions"][condition_id])
    value["id"] = condition_id
    return value


def enabled(condition_id, capability, path=None):
    if capability not in CAPABILITIES:
        raise FreecivConfigError("unknown capability: {}".format(capability))
    return condition(condition_id, path)["capabilities"][capability]


def belief_config(path=None):
    """Return the complete declared confidence configuration."""
    return copy.deepcopy(load_config(path)["beliefs"])


def _selftest():
    data = load_config()
    assert list(data["conditions"]) == list(CONDITION_ORDER)
    assert not any(condition("a_stock_llm")["capabilities"].values())
    assert all(condition("e_full_loop")["capabilities"].values())


if __name__ == "__main__":
    _selftest()
    print("freeciv_agent.config: ok")
