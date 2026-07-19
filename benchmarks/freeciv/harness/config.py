"""Strict harness configuration and capability assertions."""

import copy
import hashlib
import math
import os
from statistics import NormalDist

import yaml

from freeciv_agent.config import CONDITION_ORDER, condition, belief_config
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.paths import repo_path

from .statistics import paired_win_design_power


DEFAULT_PATH = repo_path("profile", "freeciv_harness.yaml")


def _validate_impact_policy(impact, prefix="impact_policy"):
    if not isinstance(impact, dict):
        raise ValueError("{} configuration is required".format(prefix))
    for key, lower, upper in (
            ("max_actions_per_turn", 1, 32),
            ("expansion_city_target", 1, 20),
            ("settle_min_distance", 1, 12),
            ("horizon_turn", 1, 500),
            ("production_minimum_remaining_turns", 1, 100),
            ("expansion_minimum_remaining_turns", 1, 100),
            ("no_effect_retry_limit", 1, 8),
            ("max_no_effect_failovers_per_scope", 0, 8)):
        setting = impact.get(key)
        if isinstance(setting, bool) or not isinstance(setting, int) or not lower <= setting <= upper:
            raise ValueError("{}.{} must be in {}..{}".format(prefix, key, lower, upper))
    if not isinstance(impact.get("preserve_city_defenders"), bool):
        raise ValueError("{}.preserve_city_defenders must be boolean".format(prefix))
    if (impact["expansion_minimum_remaining_turns"]
            < impact["production_minimum_remaining_turns"]):
        raise ValueError(
            "{}.expansion_minimum_remaining_turns cannot be shorter than production"
            .format(prefix))


def _derive_seeds(spec, prefix):
    if not isinstance(spec, dict) or spec.get("algorithm") != "sha256-counter-v1":
        raise ValueError("{}.seed_derivation algorithm must be sha256-counter-v1".format(prefix))
    namespace = spec.get("namespace")
    count = spec.get("count")
    minimum = spec.get("minimum", 1)
    maximum = spec.get("maximum", 2147483647)
    if not isinstance(namespace, str) or not namespace.strip():
        raise ValueError("{}.seed_derivation namespace is required".format(prefix))
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("{}.seed_derivation count must be positive".format(prefix))
    if (isinstance(minimum, bool) or not isinstance(minimum, int)
            or isinstance(maximum, bool) or not isinstance(maximum, int)
            or minimum < 1 or maximum > 2147483647 or minimum > maximum):
        raise ValueError("{}.seed_derivation range is invalid".format(prefix))
    width = maximum - minimum + 1
    if count > width:
        raise ValueError("{}.seed_derivation range cannot contain count seeds".format(prefix))
    seeds = []
    seen = set()
    counter = 0
    while len(seeds) < count:
        material = "{}:{}".format(namespace, counter).encode("utf-8")
        candidate = minimum + int.from_bytes(
            hashlib.sha256(material).digest()[:8], "big") % width
        if candidate not in seen:
            seen.add(candidate)
            seeds.append(candidate)
        counter += 1
    return seeds


def _cohort_seeds(cohort, prefix):
    literal = cohort.get("seeds")
    derivation = cohort.get("seed_derivation")
    if (literal is None) == (derivation is None):
        raise ValueError("{} requires exactly one of seeds or seed_derivation".format(prefix))
    if derivation is not None:
        return _derive_seeds(derivation, prefix)
    if (not isinstance(literal, list) or not literal
            or any(isinstance(seed, bool) or not isinstance(seed, int) or seed < 1
                   for seed in literal)
            or len(literal) != len(set(literal))):
        raise ValueError("{}.seeds must be unique positive integers".format(prefix))
    return list(literal)


def _validate_paired_impact(value):
    paired = value.get("paired_impact")
    if paired is None:
        return
    if not isinstance(paired, dict) or paired.get("schema_version") != "1.0":
        raise ValueError("paired_impact schema_version must be 1.0")
    if paired.get("condition") != "e_full_loop":
        raise ValueError("paired_impact condition must be e_full_loop")
    if paired.get("experimental_unit") != "seed_pair":
        raise ValueError("paired_impact experimental_unit must be seed_pair")
    if paired.get("order") != "alternating_within_pair":
        raise ValueError("paired_impact order must be alternating_within_pair")
    if paired.get("primary_metric") != "score_turn_n":
        raise ValueError("paired_impact primary_metric must be score_turn_n")
    outcomes = paired.get("outcomes")
    if not isinstance(outcomes, dict):
        raise ValueError("paired_impact outcomes declaration is required")
    expected_outcomes = {
        "horizon_turn": value.get("turn_limit"),
        "score_metric": "score_turn_n",
        "score_margin_metric": "score_margin_turn_n",
        "opponent_score_metric": "opponent_score_turn_n",
        "win_metric": "score_lead_turn_n",
        "win_definition": "fixed_horizon_score_lead",
        "terminal_win_metric": None,
        "tie_handling": "non_win",
    }
    if outcomes != expected_outcomes:
        raise ValueError("paired_impact outcomes must explicitly declare fixed-horizon semantics")
    arms = paired.get("arms")
    if not isinstance(arms, dict) or set(arms) != {"baseline", "treatment"}:
        raise ValueError("paired_impact arms must be baseline and treatment")
    allowed = set(value["impact_policy"])
    merged = {}
    for arm in ("baseline", "treatment"):
        override = arms[arm]
        if not isinstance(override, dict) or not override or set(override) - allowed:
            raise ValueError("paired_impact.{} has invalid policy overrides".format(arm))
        merged[arm] = dict(value["impact_policy"], **override)
        _validate_impact_policy(merged[arm], "paired_impact.{}".format(arm))
    if merged["baseline"] == merged["treatment"]:
        raise ValueError("paired_impact arms must differ")
    power = paired.get("power")
    if not isinstance(power, dict):
        raise ValueError("paired_impact power declaration is required")
    for key in ("alpha", "target_power"):
        setting = power.get(key)
        if not isinstance(setting, (int, float)) or not 0 < setting < 1:
            raise ValueError("paired_impact.power.{} must be in (0,1)".format(key))
    if not math.isclose(
            float(value.get("statistics", {}).get("confidence", -1)),
            1.0 - float(power["alpha"]), rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(
            "paired_impact confidence interval must match its declared alpha")
    minimum_pairs = power.get("minimum_variance_pairs")
    bootstrap_samples = power.get("primary_bootstrap_samples")
    if (isinstance(minimum_pairs, bool) or not isinstance(minimum_pairs, int)
            or minimum_pairs < 30):
        raise ValueError("paired_impact power requires at least 30 variance-estimation pairs")
    if (isinstance(bootstrap_samples, bool) or not isinstance(bootstrap_samples, int)
            or bootstrap_samples < 10000):
        raise ValueError("paired_impact primary bootstrap requires at least 10000 samples")
    score_power = power.get("score")
    if not isinstance(score_power, dict):
        raise ValueError("paired_impact score power declaration is required")
    score_delta = score_power.get("minimum_detectable_delta")
    score_pairs = score_power.get("planned_pairs")
    maximum_sd = score_power.get("maximum_planning_sd")
    if not isinstance(score_delta, (int, float)) or score_delta <= 0:
        raise ValueError("paired_impact minimum detectable score delta must be positive")
    if (isinstance(score_pairs, bool) or not isinstance(score_pairs, int)
            or score_pairs < minimum_pairs):
        raise ValueError("paired_impact score planned_pairs is too small")
    if not isinstance(maximum_sd, (int, float)) or maximum_sd <= 0:
        raise ValueError("paired_impact maximum planning SD must be positive")
    normal = NormalDist()
    score_required = math.ceil((
        (normal.inv_cdf(1.0 - float(power["alpha"]) / 2.0)
         + normal.inv_cdf(float(power["target_power"])))
        * float(maximum_sd) / float(score_delta)) ** 2)
    if score_pairs < score_required:
        raise ValueError(
            "paired_impact score planned_pairs does not meet its declared power target")
    win_power = power.get("win")
    if not isinstance(win_power, dict):
        raise ValueError("paired_impact win power declaration is required")
    win_delta = win_power.get("minimum_detectable_delta")
    discordance = win_power.get("planned_discordance")
    win_pairs = win_power.get("planned_pairs")
    if not isinstance(win_delta, (int, float)) or not 0 < win_delta < 1:
        raise ValueError("paired_impact win minimum detectable delta must be in (0,1)")
    if (not isinstance(discordance, (int, float)) or not 0 < discordance <= 1
            or discordance < win_delta):
        raise ValueError("paired_impact planned discordance is invalid")
    if (isinstance(win_pairs, bool) or not isinstance(win_pairs, int)
            or win_pairs < minimum_pairs):
        raise ValueError("paired_impact win planned_pairs is too small")
    if not paired_win_design_power(
            win_pairs, win_delta, discordance, alpha=power["alpha"],
            target_power=power["target_power"])["target_met"]:
        raise ValueError(
            "paired_impact win planned_pairs does not meet its declared power target")

    claims = paired.get("claims")
    if not isinstance(claims, dict):
        raise ValueError("paired_impact claims declaration is required")
    if claims.get("multiplicity") != "hierarchical_score_then_win":
        raise ValueError("paired_impact claims must use hierarchical score-then-win testing")
    score_test = claims.get("score_test")
    if (not isinstance(score_test, dict)
            or set(score_test) != {"method", "alternative", "maximum_states"}
            or score_test.get("method") != "exact_paired_sign_flip"
            or score_test.get("alternative") != "two_sided"):
        raise ValueError(
            "paired_impact score claim requires a two-sided exact paired sign-flip test")
    maximum_states = score_test.get("maximum_states")
    if (isinstance(maximum_states, bool) or not isinstance(maximum_states, int)
            or maximum_states < 10000):
        raise ValueError(
            "paired_impact score randomization requires at least 10000 states")
    for key in ("score_superiority_margin", "win_superiority_margin"):
        setting = claims.get(key)
        if not isinstance(setting, (int, float)) or setting != 0:
            raise ValueError("paired_impact claims.{} must be zero".format(key))
    for key in ("meaningful_score_delta", "meaningful_win_rate_delta"):
        setting = claims.get(key)
        if not isinstance(setting, (int, float)) or setting <= 0:
            raise ValueError("paired_impact claims.{} must be positive".format(key))
    meaningful_score = float(claims["meaningful_score_delta"])
    if not meaningful_score.is_integer():
        raise ValueError(
            "paired_impact meaningful score delta must be an integer score margin")

    cohorts = paired.get("cohorts")
    if not isinstance(cohorts, dict) or not cohorts:
        raise ValueError("paired_impact cohorts declaration is required")
    default_cohort = paired.get("default_cohort")
    if default_cohort not in cohorts:
        raise ValueError("paired_impact default_cohort is unknown")
    allowed_endpoints = {outcomes["score_metric"], outcomes["win_metric"]}
    all_seeds = {}
    for name, cohort in sorted(cohorts.items()):
        prefix = "paired_impact.cohorts.{}".format(name)
        if not isinstance(cohort, dict):
            raise ValueError("{} must be an object".format(prefix))
        purpose = cohort.get("purpose")
        if purpose not in ("development", "pilot", "confirmatory"):
            raise ValueError("{}.purpose is invalid".format(prefix))
        for key in ("claim_eligible", "require_clean_source"):
            if not isinstance(cohort.get(key), bool):
                raise ValueError("{}.{} must be boolean".format(prefix, key))
        horizon_turn = cohort.get("horizon_turn", outcomes["horizon_turn"])
        if (isinstance(horizon_turn, bool) or not isinstance(horizon_turn, int)
                or not 1 <= horizon_turn <= 500):
            raise ValueError("{}.horizon_turn must be in 1..500".format(prefix))
        if purpose != "pilot" and horizon_turn != outcomes["horizon_turn"]:
            raise ValueError(
                "{}.horizon_turn may differ from the declared outcome only for pilots"
                .format(prefix))
        endpoints = cohort.get("endpoints")
        if (not isinstance(endpoints, list) or not endpoints
                or len(endpoints) != len(set(endpoints))
                or set(endpoints) - allowed_endpoints):
            raise ValueError("{}.endpoints are invalid".format(prefix))
        seeds = _cohort_seeds(cohort, prefix)
        cohort["seeds"] = seeds
        planned_pairs = cohort.get("planned_pairs")
        if planned_pairs != len(seeds):
            raise ValueError("{}.planned_pairs must equal its predeclared seed count".format(prefix))
        if purpose == "pilot" and len(seeds) < minimum_pairs:
            raise ValueError("{} requires at least {} pilot pairs".format(prefix, minimum_pairs))
        if purpose in ("pilot", "confirmatory") and not cohort["require_clean_source"]:
            raise ValueError("{} must require a clean source tree".format(prefix))
        if purpose == "confirmatory" and not cohort["claim_eligible"]:
            raise ValueError("{} must be claim eligible".format(prefix))
        if purpose != "confirmatory" and cohort["claim_eligible"]:
            raise ValueError("{} cannot be claim eligible".format(prefix))
        if outcomes["score_metric"] in endpoints and purpose == "confirmatory":
            if len(seeds) < score_pairs:
                raise ValueError("{} is underpowered for the declared score design".format(prefix))
        if outcomes["win_metric"] in endpoints and purpose == "confirmatory":
            if len(seeds) < win_pairs:
                raise ValueError("{} is underpowered for the declared win design".format(prefix))
        all_seeds[name] = set(seeds)
    names = sorted(all_seeds)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            overlap = sorted(all_seeds[left] & all_seeds[right])
            if overlap:
                raise ValueError("paired impact cohorts {} and {} overlap at {}".format(
                    left, right, overlap[:5]))


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
    model_config = value.get("model", {})
    readiness_timeout = model_config.get("readiness_timeout_seconds")
    if (not isinstance(readiness_timeout, (int, float))
            or isinstance(readiness_timeout, bool) or readiness_timeout <= 0):
        raise ValueError(
            "harness model.readiness_timeout_seconds must be positive")
    if (not isinstance(model_config.get("keep_alive"), str)
            or not model_config["keep_alive"].strip()):
        raise ValueError("harness model.keep_alive must be a non-empty string")
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
    _validate_impact_policy(value.get("impact_policy"))
    _validate_paired_impact(value)
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
