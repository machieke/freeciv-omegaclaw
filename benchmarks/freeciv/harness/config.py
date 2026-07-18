"""Strict harness configuration and capability assertions."""

import copy
import os

import yaml

from freeciv_agent.config import CONDITION_ORDER, condition, belief_config
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.paths import repo_path


DEFAULT_PATH = repo_path("profile", "freeciv_harness.yaml")


def load(path=None):
    with open(os.path.abspath(path or DEFAULT_PATH), encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if value.get("schema_version") != "1.0":
        raise ValueError("harness schema_version must be 1.0")
    if tuple(value.get("conditions", ())) != CONDITION_ORDER:
        raise ValueError("harness condition order must match capability matrix")
    seeds = value.get("seeds")
    if not isinstance(seeds, list) or len(seeds) < 30 or len(seeds) != len(set(seeds)):
        raise ValueError("harness needs at least 30 unique seeds")
    if value.get("induction", {}).get("games", 0) < 20:
        raise ValueError("induction track needs at least 20 games")
    if value.get("model", {}).get("name") != "qwen3-coder-next:latest":
        raise ValueError("harness model must match the configured evaluation model")
    if not isinstance(value.get("model", {}).get("think"), bool):
        raise ValueError("harness model.think must be an explicit boolean")
    rulebase = value.get("rulebase", {})
    if rulebase.get("compiler_version") != "freeciv-ruleset-compiler/1.0":
        raise ValueError("harness rulebase compiler version is not pinned")
    for key in ("source_sha256", "ir_sha256", "atomese_sha256"):
        digest = rulebase.get(key)
        if (not isinstance(digest, str) or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)):
            raise ValueError("harness rulebase.{} must be a SHA-256".format(key))
    calibration = value.get("calibration", {})
    if calibration.get("bucket_width") != 0.1:
        raise ValueError("calibration.bucket_width must be 0.1 for the v1 schema")
    if (not isinstance(calibration.get("minimum_bucket_samples"), int)
            or calibration["minimum_bucket_samples"] < 1):
        raise ValueError("calibration.minimum_bucket_samples must be positive")
    tolerance = calibration.get("tolerance")
    if not isinstance(tolerance, (int, float)) or not 0 <= tolerance <= 1:
        raise ValueError("calibration.tolerance must be in [0,1]")
    impact = value.get("impact_policy")
    if not isinstance(impact, dict):
        raise ValueError("impact_policy configuration is required")
    for key, lower, upper in (
            ("max_actions_per_turn", 1, 32),
            ("expansion_city_target", 1, 20),
            ("settle_min_distance", 1, 12),
            ("no_effect_retry_limit", 1, 8)):
        setting = impact.get(key)
        if isinstance(setting, bool) or not isinstance(setting, int) or not lower <= setting <= upper:
            raise ValueError("impact_policy.{} must be in {}..{}".format(key, lower, upper))
    if not isinstance(impact.get("preserve_city_defenders"), bool):
        raise ValueError("impact_policy.preserve_city_defenders must be boolean")
    value["beliefs"] = belief_config()
    value["capabilities"] = {
        name: condition(name)["capabilities"] for name in CONDITION_ORDER}
    value["configuration_hash"] = structural_hash(value)
    return copy.deepcopy(value)


class CapabilityContext(object):
    def __init__(self, condition_id, capabilities):
        self.condition_id = condition_id
        self.capabilities = dict(capabilities)
        self.accessed = set()

    def use(self, capability):
        if capability not in self.capabilities:
            raise PermissionError("unknown capability {}".format(capability))
        if not self.capabilities[capability]:
            raise PermissionError(
                "condition {} cannot import/use {}".format(self.condition_id, capability))
        self.accessed.add(capability)
        return True

    def audit(self):
        disallowed = sorted(name for name in self.accessed if not self.capabilities[name])
        if disallowed:
            raise PermissionError("disallowed capabilities accessed: {}".format(disallowed))
        return {"accessed": sorted(self.accessed), "condition": self.condition_id,
                "passed": True}
