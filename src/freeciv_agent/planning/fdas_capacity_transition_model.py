"""Deterministic shadow model for retained-capacity transition value."""

from dataclasses import dataclass
import hashlib
import math
import random

from ..events.schema import canonical_json_bytes, structural_hash
from .fdas_capacity_query_episode_dataset import (
    FdasRetainedCapacityQueryEpisodeRow,
)
from .fdas_capacity_transition_queries import (
    FdasRetainedCapacityTransitionQuery,
    RETAINED_CAPACITY_TRANSITION_FEATURE_SCHEMA,
)


RETAINED_CAPACITY_TRANSITION_MODEL_IDENTITY = (
    "fdas-retained-capacity-transition-model/1.0")
RETAINED_CAPACITY_TRANSITION_MODEL_ID = (
    "fdas-pr99-retained-capacity-transition-model-v1")
RETAINED_CAPACITY_PRODUCT_TARGET = "exact-product-effect"
RETAINED_CAPACITY_RELIEF_TARGET = "durable-goal-relief"
RETAINED_CAPACITY_TRANSITION_TARGETS = (
    RETAINED_CAPACITY_PRODUCT_TARGET, RETAINED_CAPACITY_RELIEF_TARGET)
RETAINED_CAPACITY_TRANSITION_MODEL_LEVELS = (
    "full-feature-signature",
    "category-lifecycle-product-phase-horizon",
    "category-lifecycle-product",
    "category-lifecycle",
)
RETAINED_CAPACITY_TRANSITION_MODEL_HIERARCHY = (
    (RETAINED_CAPACITY_TRANSITION_MODEL_LEVELS[0], (
        "action_category", "completion_horizon_band", "cross_city_deficit",
        "exact_queue_match", "lifecycle_state", "production_target",
        "source_city_disorder", "source_city_food_surplus_band",
        "source_city_own_unit_count_band",
        "source_city_shield_surplus_band", "source_city_size_band",
        "target_city_own_unit_count_band", "target_city_size_band",
        "turn_phase_band",
    )),
    (RETAINED_CAPACITY_TRANSITION_MODEL_LEVELS[1], (
        "action_category", "lifecycle_state", "production_target",
        "turn_phase_band", "completion_horizon_band",
    )),
    (RETAINED_CAPACITY_TRANSITION_MODEL_LEVELS[2], (
        "action_category", "lifecycle_state", "production_target",
    )),
    (RETAINED_CAPACITY_TRANSITION_MODEL_LEVELS[3], (
        "action_category", "lifecycle_state",
    )),
)
RETAINED_CAPACITY_TRANSITION_FEATURES = tuple(sorted(
    RETAINED_CAPACITY_TRANSITION_MODEL_HIERARCHY[0][1]))
RETAINED_CAPACITY_TRANSITION_MINIMUM_GAMES = 20
RETAINED_CAPACITY_TRANSITION_BOOTSTRAP_SAMPLES = 10000
RETAINED_CAPACITY_TRANSITION_BOOTSTRAP_SEED = 980301
RETAINED_CAPACITY_TRANSITION_MAXIMUM_INTERVAL_WIDTH = 0.40

PR98_COHORT_HASH = (
    "3c6203c6a7bd1512b026f0b66ae9dbfdae54c11d604d3343c06b4e4bfe1f5c8d")
PR98_DATASET_HASH = (
    "89eff1ca7b756bcbe47acf9a99e22b5a1f0f5da8fe34571457d78ace116c6eb1")
PR98_REPORT_SHA256 = (
    "be392866b5415a63667034c0c3f00711ea8384de0d8a37e7530ad48a7cf07e33")
PR98_SOURCE_COMMIT = "8370d5102df62a7815b687fa3264f4ab8025b331"

_STATUS_TARGETS = {
    "no-effect-observed": (0, 0),
    "effect-without-goal-relief": (1, 0),
    "goal-relief-observed": (1, 1),
}
_CENSORED_REASON = "right-censored-no-terminal-target"


def _text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


def _count(value, name, minimum=0):
    if (isinstance(value, bool) or not isinstance(value, int)
            or value < minimum):
        raise ValueError("{} is invalid".format(name))
    return value


def _probability(value, name):
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("{} must be a probability".format(name))
    return value


def _features(values):
    values = tuple(sorted((str(key), str(value)) for key, value in values))
    if (tuple(key for key, _value in values)
            != RETAINED_CAPACITY_TRANSITION_FEATURES
            or any(not value for _key, value in values)):
        raise ValueError("retained capacity model features differ")
    return values


def _target_value(status, target):
    values = _STATUS_TARGETS.get(status)
    if values is None or target not in RETAINED_CAPACITY_TRANSITION_TARGETS:
        raise ValueError("retained capacity model target differs")
    return values[RETAINED_CAPACITY_TRANSITION_TARGETS.index(target)]


def _bootstrap_interval(values):
    values = tuple(float(value) for value in values)
    if not values:
        raise ValueError("retained capacity bootstrap is empty")
    randomizer = random.Random(RETAINED_CAPACITY_TRANSITION_BOOTSTRAP_SEED)
    estimates = []
    count = len(values)
    for _sample in range(RETAINED_CAPACITY_TRANSITION_BOOTSTRAP_SAMPLES):
        estimates.append(sum(
            values[randomizer.randrange(count)] for _value in values
        ) / float(count))
    estimates.sort()
    return (
        sum(values) / float(count), estimates[250], estimates[9750])


@dataclass(frozen=True)
class FdasRetainedCapacityTransitionSourceGame:
    seed: int
    game_id: str
    parent_audit_hash: str
    source_commit: str
    query_rows: int
    terminal_rows: int
    censored_rows: int
    result_hash: str

    def __post_init__(self):
        _count(self.seed, "transition source seed", minimum=1)
        for value, name in (
                (self.game_id, "transition source game"),
                (self.parent_audit_hash, "transition parent audit hash"),
                (self.source_commit, "transition source commit")):
            _text(value, name)
        for value, name in (
                (self.query_rows, "transition source query rows"),
                (self.terminal_rows, "transition source terminal rows"),
                (self.censored_rows, "transition source censored rows")):
            _count(value, name)
        if (self.terminal_rows + self.censored_rows != self.query_rows
                or self.source_commit != PR98_SOURCE_COMMIT):
            raise ValueError("retained capacity source game partition differs")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("retained capacity source game hash differs")

    def _semantic(self):
        return {
            "censored_rows": self.censored_rows,
            "game_id": self.game_id,
            "parent_audit_hash": self.parent_audit_hash,
            "query_rows": self.query_rows,
            "seed": self.seed,
            "source_commit": self.source_commit,
            "terminal_rows": self.terminal_rows,
        }

    def to_dict(self):
        return {**self._semantic(), "result_hash": self.result_hash}

    @classmethod
    def build(cls, value):
        semantic = {
            "censored_rows": value["censored_rows"],
            "game_id": value["game_id"],
            "parent_audit_hash": value["parent_audit_hash"],
            "query_rows": value["query_rows"],
            "seed": value["seed"],
            "source_commit": value["source_commit"],
            "terminal_rows": value["terminal_rows"],
        }
        return cls(result_hash=structural_hash(semantic), **semantic)

    @classmethod
    def from_dict(cls, value):
        return cls(
            value["seed"], value["game_id"], value["parent_audit_hash"],
            value["source_commit"], value["query_rows"],
            value["terminal_rows"], value["censored_rows"],
            value["result_hash"])


@dataclass(frozen=True)
class FdasRetainedCapacityTransitionTrainingRow:
    seed: int
    game_id: str
    parent_audit_hash: str
    row_id: str
    query_id: str
    episode_id: str
    feature_signature: str
    features: tuple
    outcome_status: str
    exact_product_effect: int
    durable_goal_relief: int
    result_hash: str

    def __post_init__(self):
        _count(self.seed, "transition training seed", minimum=1)
        for value, name in (
                (self.game_id, "transition training game"),
                (self.parent_audit_hash, "transition training parent"),
                (self.row_id, "transition training row"),
                (self.query_id, "transition training query"),
                (self.episode_id, "transition training episode"),
                (self.feature_signature, "transition feature signature")):
            _text(value, name)
        object.__setattr__(self, "features", _features(self.features))
        expected = _STATUS_TARGETS.get(self.outcome_status)
        if (expected is None
                or (self.exact_product_effect, self.durable_goal_relief)
                != expected
                or self.durable_goal_relief > self.exact_product_effect):
            raise ValueError("retained capacity training target differs")
        if self.feature_signature != structural_hash({
                "feature_schema": RETAINED_CAPACITY_TRANSITION_FEATURE_SCHEMA,
                "features": dict(self.features),
        }):
            raise ValueError("retained capacity feature signature differs")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("retained capacity training row hash differs")

    def _semantic(self):
        return {
            "durable_goal_relief": self.durable_goal_relief,
            "episode_id": self.episode_id,
            "exact_product_effect": self.exact_product_effect,
            "feature_signature": self.feature_signature,
            "features": dict(self.features),
            "game_id": self.game_id,
            "outcome_status": self.outcome_status,
            "parent_audit_hash": self.parent_audit_hash,
            "query_id": self.query_id,
            "row_id": self.row_id,
            "seed": self.seed,
        }

    def to_dict(self):
        return {**self._semantic(), "result_hash": self.result_hash}

    @classmethod
    def build(cls, seed, game_id, parent_audit_hash, row):
        targets = _STATUS_TARGETS[row.outcome_status]
        semantic = {
            "durable_goal_relief": targets[1],
            "episode_id": row.episode.episode_id,
            "exact_product_effect": targets[0],
            "feature_signature": row.feature_signature,
            "features": dict(row.query.features),
            "game_id": game_id,
            "outcome_status": row.outcome_status,
            "parent_audit_hash": parent_audit_hash,
            "query_id": row.query.query_id,
            "row_id": row.row_id,
            "seed": seed,
        }
        return cls(
            seed, game_id, parent_audit_hash, row.row_id,
            row.query.query_id, row.episode.episode_id,
            row.feature_signature, tuple(row.query.features),
            row.outcome_status, targets[0], targets[1],
            structural_hash(semantic))

    @classmethod
    def from_dict(cls, value):
        return cls(
            value["seed"], value["game_id"], value["parent_audit_hash"],
            value["row_id"], value["query_id"], value["episode_id"],
            value["feature_signature"], tuple(value["features"].items()),
            value["outcome_status"], value["exact_product_effect"],
            value["durable_goal_relief"], value["result_hash"])


@dataclass(frozen=True)
class FdasRetainedCapacityTransitionExcludedRow:
    seed: int
    game_id: str
    parent_audit_hash: str
    row_id: str
    query_id: str
    exclusion_reason: str
    result_hash: str

    def __post_init__(self):
        _count(self.seed, "transition exclusion seed", minimum=1)
        for value, name in (
                (self.game_id, "transition exclusion game"),
                (self.parent_audit_hash, "transition exclusion parent"),
                (self.row_id, "transition exclusion row"),
                (self.query_id, "transition exclusion query")):
            _text(value, name)
        if self.exclusion_reason != _CENSORED_REASON:
            raise ValueError("retained capacity exclusion reason differs")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("retained capacity exclusion hash differs")

    def _semantic(self):
        return {
            "exclusion_reason": self.exclusion_reason,
            "game_id": self.game_id,
            "parent_audit_hash": self.parent_audit_hash,
            "query_id": self.query_id,
            "row_id": self.row_id,
            "seed": self.seed,
        }

    def to_dict(self):
        return {**self._semantic(), "result_hash": self.result_hash}

    @classmethod
    def build(cls, seed, game_id, parent_audit_hash, row):
        semantic = {
            "exclusion_reason": _CENSORED_REASON,
            "game_id": game_id,
            "parent_audit_hash": parent_audit_hash,
            "query_id": row.query.query_id,
            "row_id": row.row_id,
            "seed": seed,
        }
        return cls(result_hash=structural_hash(semantic), **semantic)

    @classmethod
    def from_dict(cls, value):
        return cls(
            value["seed"], value["game_id"], value["parent_audit_hash"],
            value["row_id"], value["query_id"],
            value["exclusion_reason"], value["result_hash"])


@dataclass(frozen=True)
class FdasRetainedCapacityTransitionGameOutcome:
    seed: int
    game_id: str
    row_ids: tuple
    outcome_mean: float
    result_hash: str

    def __post_init__(self):
        _count(self.seed, "transition bin seed", minimum=1)
        _text(self.game_id, "transition bin game")
        rows = tuple(sorted(str(value) for value in self.row_ids))
        if not rows or len(rows) != len(set(rows)) or any(not row for row in rows):
            raise ValueError("retained capacity bin rows differ")
        object.__setattr__(self, "row_ids", rows)
        object.__setattr__(
            self, "outcome_mean", _probability(
                self.outcome_mean, "transition game outcome"))
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("retained capacity game outcome hash differs")

    def _semantic(self):
        return {
            "game_id": self.game_id,
            "outcome_mean": self.outcome_mean,
            "row_ids": list(self.row_ids),
            "seed": self.seed,
        }

    def to_dict(self):
        return {**self._semantic(), "result_hash": self.result_hash}

    @classmethod
    def build(cls, seed, game_id, rows, target):
        row_ids = tuple(sorted(row.row_id for row in rows))
        outcome = sum(_target_value(row.outcome_status, target)
                      for row in rows) / float(len(rows))
        semantic = {
            "game_id": game_id,
            "outcome_mean": outcome,
            "row_ids": list(row_ids),
            "seed": seed,
        }
        return cls(seed, game_id, row_ids, outcome, structural_hash(semantic))

    @classmethod
    def from_dict(cls, value):
        return cls(
            value["seed"], value["game_id"], tuple(value["row_ids"]),
            value["outcome_mean"], value["result_hash"])


@dataclass(frozen=True)
class FdasRetainedCapacityTransitionModelBin:
    bin_id: str
    target: str
    level: str
    feature_values: tuple
    exact_feature_signature: object
    raw_rows: int
    independent_games: int
    game_outcomes: tuple
    sample_eligible: bool
    estimate: object
    interval_lower: object
    interval_upper: object
    numerically_usable: bool
    source_dataset_hash: str
    result_hash: str

    def __post_init__(self):
        _text(self.bin_id, "retained capacity model bin")
        if (self.target not in RETAINED_CAPACITY_TRANSITION_TARGETS
                or self.level not in RETAINED_CAPACITY_TRANSITION_MODEL_LEVELS):
            raise ValueError("retained capacity model bin scope differs")
        values = tuple((str(key), str(value))
                       for key, value in self.feature_values)
        expected_keys = dict(RETAINED_CAPACITY_TRANSITION_MODEL_HIERARCHY)[
            self.level]
        if (tuple(key for key, _value in values) != expected_keys
                or len(values) != len(set(key for key, _value in values))
                or any(not value for _key, value in values)):
            raise ValueError("retained capacity model bin features differ")
        object.__setattr__(self, "feature_values", values)
        expected_signature = (
            structural_hash({
                "feature_schema": RETAINED_CAPACITY_TRANSITION_FEATURE_SCHEMA,
                "features": dict(values),
            }) if self.level == "full-feature-signature" else None)
        if self.exact_feature_signature != expected_signature:
            raise ValueError("retained capacity exact signature differs")
        outcomes = tuple(sorted(
            self.game_outcomes, key=lambda value: (value.seed, value.game_id)))
        if (not outcomes or any(not isinstance(
                value, FdasRetainedCapacityTransitionGameOutcome)
                for value in outcomes)
                or len({(value.seed, value.game_id) for value in outcomes})
                != len(outcomes)):
            raise ValueError("retained capacity model game outcomes differ")
        object.__setattr__(self, "game_outcomes", outcomes)
        if (self.raw_rows != sum(len(value.row_ids) for value in outcomes)
                or self.independent_games != len(outcomes)):
            raise ValueError("retained capacity model bin counts differ")
        expected_eligible = (
            self.independent_games >= RETAINED_CAPACITY_TRANSITION_MINIMUM_GAMES)
        if self.sample_eligible is not expected_eligible:
            raise ValueError("retained capacity model eligibility differs")
        if expected_eligible:
            expected = _bootstrap_interval(tuple(
                value.outcome_mean for value in outcomes))
            actual = (self.estimate, self.interval_lower, self.interval_upper)
            if actual != expected:
                raise ValueError("retained capacity model interval differs")
            expected_usable = expected[2] - expected[1] <= (
                RETAINED_CAPACITY_TRANSITION_MAXIMUM_INTERVAL_WIDTH)
        else:
            if any(value is not None for value in (
                    self.estimate, self.interval_lower, self.interval_upper)):
                raise ValueError("ineligible retained capacity bin estimates")
            expected_usable = False
        if self.numerically_usable is not expected_usable:
            raise ValueError("retained capacity numerical gate differs")
        if self.source_dataset_hash != PR98_DATASET_HASH:
            raise ValueError("retained capacity bin source differs")
        if (self.result_hash != structural_hash(self._semantic())
                or self.bin_id != (
                    "retained-capacity-transition-bin-" +
                    self.result_hash[:24])):
            raise ValueError("retained capacity model bin hash differs")

    @property
    def interval_width(self):
        if self.interval_lower is None:
            return None
        return self.interval_upper - self.interval_lower

    def _semantic(self):
        return {
            "estimate": self.estimate,
            "exact_feature_signature": self.exact_feature_signature,
            "feature_values": dict(self.feature_values),
            "game_outcomes": [value.to_dict() for value in self.game_outcomes],
            "independent_games": self.independent_games,
            "interval_lower": self.interval_lower,
            "interval_upper": self.interval_upper,
            "level": self.level,
            "numerically_usable": self.numerically_usable,
            "raw_rows": self.raw_rows,
            "sample_eligible": self.sample_eligible,
            "source_dataset_hash": self.source_dataset_hash,
            "target": self.target,
        }

    def to_dict(self):
        return {
            **self._semantic(), "bin_id": self.bin_id,
            "interval_width": self.interval_width,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, value):
        keys = dict(RETAINED_CAPACITY_TRANSITION_MODEL_HIERARCHY)[
            value["level"]]
        instance = cls(
            value["bin_id"], value["target"], value["level"],
            tuple((key, value["feature_values"][key]) for key in keys),
            value.get("exact_feature_signature"), value["raw_rows"],
            value["independent_games"], tuple(
                FdasRetainedCapacityTransitionGameOutcome.from_dict(row)
                for row in value["game_outcomes"]),
            value["sample_eligible"], value.get("estimate"),
            value.get("interval_lower"), value.get("interval_upper"),
            value["numerically_usable"], value["source_dataset_hash"],
            value["result_hash"])
        if value.get("interval_width") != instance.interval_width:
            raise ValueError("retained capacity bin width projection differs")
        return instance


@dataclass(frozen=True)
class FdasRetainedCapacityTargetPrediction:
    target: str
    status: str
    reason: str
    bin_id: object
    estimate: object
    interval_lower: object
    interval_upper: object
    independent_games: int

    def __post_init__(self):
        if (self.target not in RETAINED_CAPACITY_TRANSITION_TARGETS
                or self.status not in ("estimated", "abstained")):
            raise ValueError("retained capacity target prediction differs")
        _text(self.reason, "retained capacity prediction reason")
        if self.status == "estimated":
            _text(self.bin_id, "retained capacity prediction bin")
            for name in ("estimate", "interval_lower", "interval_upper"):
                object.__setattr__(self, name, _probability(
                    getattr(self, name), "prediction " + name))
            _count(self.independent_games, "prediction games", minimum=1)
            if (self.interval_upper - self.interval_lower
                    > RETAINED_CAPACITY_TRANSITION_MAXIMUM_INTERVAL_WIDTH):
                raise ValueError("retained capacity prediction is too wide")
        elif (any(value is not None for value in (
                self.estimate, self.interval_lower, self.interval_upper))
                or self.independent_games != 0):
            raise ValueError("abstained retained capacity prediction leaks value")

    def to_dict(self):
        return {
            "bin_id": self.bin_id,
            "estimate": self.estimate,
            "independent_games": self.independent_games,
            "interval_lower": self.interval_lower,
            "interval_upper": self.interval_upper,
            "reason": self.reason,
            "status": self.status,
            "target": self.target,
        }

    @classmethod
    def from_dict(cls, value):
        return cls(
            value["target"], value["status"], value["reason"],
            value.get("bin_id"), value.get("estimate"),
            value.get("interval_lower"), value.get("interval_upper"),
            value["independent_games"])


@dataclass(frozen=True)
class FdasRetainedCapacityTransitionPrediction:
    query_id: str
    model_result_hash: str
    selected_level: object
    product_effect: FdasRetainedCapacityTargetPrediction
    goal_relief: FdasRetainedCapacityTargetPrediction
    result_hash: str

    def __post_init__(self):
        _text(self.query_id, "retained capacity prediction query")
        _text(self.model_result_hash, "retained capacity prediction model")
        if self.selected_level is not None and self.selected_level not in (
                RETAINED_CAPACITY_TRANSITION_MODEL_LEVELS):
            raise ValueError("retained capacity selected level differs")
        if (not isinstance(
                self.product_effect, FdasRetainedCapacityTargetPrediction)
                or not isinstance(
                    self.goal_relief, FdasRetainedCapacityTargetPrediction)
                or self.product_effect.target != RETAINED_CAPACITY_PRODUCT_TARGET
                or self.goal_relief.target != RETAINED_CAPACITY_RELIEF_TARGET):
            raise ValueError("retained capacity prediction targets differ")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("retained capacity prediction hash differs")

    def _semantic(self):
        return {
            "goal_relief": self.goal_relief.to_dict(),
            "model_result_hash": self.model_result_hash,
            "product_effect": self.product_effect.to_dict(),
            "query_id": self.query_id,
            "selected_level": self.selected_level,
        }

    def to_dict(self):
        return {
            **self._semantic(),
            "action_authority": False,
            "calibrated": False,
            "learning_write_through": False,
            "policy_authority": False,
            "readout_authority": False,
            "result_hash": self.result_hash,
            "truth_mutated": False,
        }

    @classmethod
    def from_dict(cls, value):
        if any(value.get(name) is not False for name in (
                "action_authority", "calibrated", "learning_write_through",
                "policy_authority", "readout_authority", "truth_mutated")):
            raise ValueError("retained capacity prediction grants authority")
        return cls(
            value["query_id"], value["model_result_hash"],
            value.get("selected_level"),
            FdasRetainedCapacityTargetPrediction.from_dict(
                value["product_effect"]),
            FdasRetainedCapacityTargetPrediction.from_dict(
                value["goal_relief"]), value["result_hash"])


def _bin_signature(level, features):
    keys = dict(RETAINED_CAPACITY_TRANSITION_MODEL_HIERARCHY)[level]
    return tuple((key, features[key]) for key in keys)


def _fit_bins(rows):
    bins = []
    for level, _keys in RETAINED_CAPACITY_TRANSITION_MODEL_HIERARCHY:
        groups = {}
        for row in rows:
            signature = _bin_signature(level, dict(row.features))
            groups.setdefault(signature, []).append(row)
        for signature, group in sorted(groups.items()):
            by_game = {}
            for row in group:
                by_game.setdefault((row.seed, row.game_id), []).append(row)
            for target in RETAINED_CAPACITY_TRANSITION_TARGETS:
                outcomes = tuple(
                    FdasRetainedCapacityTransitionGameOutcome.build(
                        seed, game_id, tuple(game_rows), target)
                    for (seed, game_id), game_rows in sorted(by_game.items()))
                eligible = len(outcomes) >= (
                    RETAINED_CAPACITY_TRANSITION_MINIMUM_GAMES)
                estimate, lower, upper = (
                    _bootstrap_interval(tuple(
                        value.outcome_mean for value in outcomes))
                    if eligible else (None, None, None))
                usable = bool(
                    eligible and upper - lower <=
                    RETAINED_CAPACITY_TRANSITION_MAXIMUM_INTERVAL_WIDTH)
                exact_signature = (
                    structural_hash({
                        "feature_schema": (
                            RETAINED_CAPACITY_TRANSITION_FEATURE_SCHEMA),
                        "features": dict(signature),
                    }) if level == "full-feature-signature" else None)
                semantic = {
                    "estimate": estimate,
                    "exact_feature_signature": exact_signature,
                    "feature_values": dict(signature),
                    "game_outcomes": [
                        value.to_dict() for value in outcomes],
                    "independent_games": len(outcomes),
                    "interval_lower": lower,
                    "interval_upper": upper,
                    "level": level,
                    "numerically_usable": usable,
                    "raw_rows": len(group),
                    "sample_eligible": eligible,
                    "source_dataset_hash": PR98_DATASET_HASH,
                    "target": target,
                }
                result_hash = structural_hash(semantic)
                bins.append(FdasRetainedCapacityTransitionModelBin(
                    "retained-capacity-transition-bin-" + result_hash[:24],
                    target, level, signature, exact_signature, len(group),
                    len(outcomes), outcomes, eligible, estimate, lower, upper,
                    usable, PR98_DATASET_HASH, result_hash))
    return tuple(sorted(bins, key=lambda value: (
        RETAINED_CAPACITY_TRANSITION_MODEL_LEVELS.index(value.level),
        value.feature_values,
        RETAINED_CAPACITY_TRANSITION_TARGETS.index(value.target))))


def _model_semantic(model_id, source_games, training_rows, excluded_rows, bins):
    return {
        "action_authority": False,
        "bins": [value.to_dict() for value in bins],
        "bootstrap": {
            "interval": "95%-order-statistics-250-9750",
            "samples": RETAINED_CAPACITY_TRANSITION_BOOTSTRAP_SAMPLES,
            "seed": RETAINED_CAPACITY_TRANSITION_BOOTSTRAP_SEED,
            "unit": "independent-game-mean",
        },
        "calibrated": False,
        "excluded_rows": [value.to_dict() for value in excluded_rows],
        "hierarchy": [
            {"feature_names": list(keys), "level": level}
            for level, keys in RETAINED_CAPACITY_TRANSITION_MODEL_HIERARCHY],
        "learning_write_through": False,
        "maximum_interval_width": (
            RETAINED_CAPACITY_TRANSITION_MAXIMUM_INTERVAL_WIDTH),
        "minimum_independent_games": (
            RETAINED_CAPACITY_TRANSITION_MINIMUM_GAMES),
        "model_id": model_id,
        "model_identity": RETAINED_CAPACITY_TRANSITION_MODEL_IDENTITY,
        "policy_authority": False,
        "readout_authority": False,
        "schema_version": 1,
        "source": {
            "cohort_structural_hash": PR98_COHORT_HASH,
            "dataset_hash": PR98_DATASET_HASH,
            "report_sha256": PR98_REPORT_SHA256,
            "source_commit": PR98_SOURCE_COMMIT,
        },
        "source_games": [value.to_dict() for value in source_games],
        "targets": {
            RETAINED_CAPACITY_PRODUCT_TARGET: {
                "effect-without-goal-relief": 1,
                "goal-relief-observed": 1,
                "no-effect-observed": 0,
            },
            RETAINED_CAPACITY_RELIEF_TARGET: {
                "effect-without-goal-relief": 0,
                "goal-relief-observed": 1,
                "no-effect-observed": 0,
            },
        },
        "training_rows": [value.to_dict() for value in training_rows],
        "truth_mutated": False,
    }


@dataclass(frozen=True)
class FdasRetainedCapacityTransitionModel:
    schema_version: int
    model_id: str
    source_games: tuple
    training_rows: tuple
    excluded_rows: tuple
    bins: tuple
    result_hash: str

    def __post_init__(self):
        if self.schema_version != 1 or self.model_id != (
                RETAINED_CAPACITY_TRANSITION_MODEL_ID):
            raise ValueError("retained capacity model identity differs")
        games = tuple(sorted(self.source_games, key=lambda value: value.seed))
        rows = tuple(sorted(self.training_rows, key=lambda value: (
            value.seed, value.row_id)))
        excluded = tuple(sorted(self.excluded_rows, key=lambda value: (
            value.seed, value.row_id)))
        bins = tuple(sorted(self.bins, key=lambda value: (
            RETAINED_CAPACITY_TRANSITION_MODEL_LEVELS.index(value.level),
            value.feature_values,
            RETAINED_CAPACITY_TRANSITION_TARGETS.index(value.target))))
        if (len(games) != 301
                or any(not isinstance(
                    value, FdasRetainedCapacityTransitionSourceGame)
                    for value in games)
                or len({value.seed for value in games}) != len(games)
                or len({value.game_id for value in games}) != len(games)):
            raise ValueError("retained capacity source game ledger differs")
        if (len(rows) != 162 or len(excluded) != 1
                or any(not isinstance(
                    value, FdasRetainedCapacityTransitionTrainingRow)
                    for value in rows)
                or any(not isinstance(
                    value, FdasRetainedCapacityTransitionExcludedRow)
                    for value in excluded)):
            raise ValueError("retained capacity model row ledger differs")
        all_row_ids = [value.row_id for value in rows + excluded]
        all_query_ids = [value.query_id for value in rows + excluded]
        if (len(set(all_row_ids)) != 163 or len(set(all_query_ids)) != 163):
            raise ValueError("retained capacity model rows overlap")
        game_keys = {(value.seed, value.game_id) for value in games}
        if any((value.seed, value.game_id) not in game_keys
               for value in rows + excluded):
            raise ValueError("retained capacity model row game differs")
        if (sum(value.query_rows for value in games) != 163
                or sum(value.terminal_rows for value in games) != 162
                or sum(value.censored_rows for value in games) != 1):
            raise ValueError("retained capacity source totals differ")
        expected_bins = _fit_bins(rows)
        if bins != expected_bins:
            raise ValueError("retained capacity fitted bins differ")
        object.__setattr__(self, "source_games", games)
        object.__setattr__(self, "training_rows", rows)
        object.__setattr__(self, "excluded_rows", excluded)
        object.__setattr__(self, "bins", bins)
        if self.result_hash != structural_hash(_model_semantic(
                self.model_id, games, rows, excluded, bins)):
            raise ValueError("retained capacity model hash differs")

    def to_dict(self):
        return {
            **_model_semantic(
                self.model_id, self.source_games, self.training_rows,
                self.excluded_rows, self.bins),
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, value):
        if any(value.get(name) is not False for name in (
                "action_authority", "calibrated", "learning_write_through",
                "policy_authority", "readout_authority", "truth_mutated")):
            raise ValueError("retained capacity model grants authority")
        expected_static = _model_semantic(
            RETAINED_CAPACITY_TRANSITION_MODEL_ID, (), (), (), ())
        for name in (
                "bootstrap", "hierarchy", "maximum_interval_width",
                "minimum_independent_games", "model_identity", "source",
                "targets"):
            if value.get(name) != expected_static[name]:
                raise ValueError("retained capacity model contract differs")
        return cls(
            value["schema_version"], value["model_id"], tuple(
                FdasRetainedCapacityTransitionSourceGame.from_dict(row)
                for row in value["source_games"]), tuple(
                FdasRetainedCapacityTransitionTrainingRow.from_dict(row)
                for row in value["training_rows"]), tuple(
                FdasRetainedCapacityTransitionExcludedRow.from_dict(row)
                for row in value["excluded_rows"]), tuple(
                FdasRetainedCapacityTransitionModelBin.from_dict(row)
                for row in value["bins"]), value["result_hash"])

    def _target_prediction(self, target, bin_value):
        if bin_value.numerically_usable:
            return FdasRetainedCapacityTargetPrediction(
                target, "estimated", "selected-level-estimate",
                bin_value.bin_id, bin_value.estimate,
                bin_value.interval_lower, bin_value.interval_upper,
                bin_value.independent_games)
        return FdasRetainedCapacityTargetPrediction(
            target, "abstained", "selected-level-interval-too-wide",
            bin_value.bin_id, None, None, None, 0)

    def predict(self, query):
        if not isinstance(query, FdasRetainedCapacityTransitionQuery):
            raise TypeError("retained capacity model requires typed query")
        features = dict(query.features)
        by_key = dict(((value.target, value.level, value.feature_values), value)
                      for value in self.bins)
        selected = None
        product = None
        relief = None
        for level, _keys in RETAINED_CAPACITY_TRANSITION_MODEL_HIERARCHY:
            signature = _bin_signature(level, features)
            product_bin = by_key.get((
                RETAINED_CAPACITY_PRODUCT_TARGET, level, signature))
            relief_bin = by_key.get((
                RETAINED_CAPACITY_RELIEF_TARGET, level, signature))
            if (product_bin is not None and relief_bin is not None
                    and product_bin.sample_eligible
                    and relief_bin.sample_eligible):
                selected = level
                product = self._target_prediction(
                    RETAINED_CAPACITY_PRODUCT_TARGET, product_bin)
                relief = self._target_prediction(
                    RETAINED_CAPACITY_RELIEF_TARGET, relief_bin)
                break
        if selected is None:
            product = FdasRetainedCapacityTargetPrediction(
                RETAINED_CAPACITY_PRODUCT_TARGET, "abstained",
                "insufficient-independent-game-support", None,
                None, None, None, 0)
            relief = FdasRetainedCapacityTargetPrediction(
                RETAINED_CAPACITY_RELIEF_TARGET, "abstained",
                "insufficient-independent-game-support", None,
                None, None, None, 0)
        semantic = {
            "goal_relief": relief.to_dict(),
            "model_result_hash": self.result_hash,
            "product_effect": product.to_dict(),
            "query_id": query.query_id,
            "selected_level": selected,
        }
        return FdasRetainedCapacityTransitionPrediction(
            query.query_id, self.result_hash, selected, product, relief,
            structural_hash(semantic))


def fit_retained_capacity_transition_model(report):
    """Fit the frozen PR99 model from the one accepted PR98 report."""
    if not isinstance(report, dict):
        raise TypeError("retained capacity model requires report mapping")
    report_sha = hashlib.sha256(
        canonical_json_bytes(report) + b"\n").hexdigest()
    dataset = report.get("dataset", {})
    if (report_sha != PR98_REPORT_SHA256
            or report.get("structural_hash") != PR98_COHORT_HASH
            or structural_hash(dict(
                (key, value) for key, value in report.items()
                if key != "structural_hash")) != PR98_COHORT_HASH
            or dataset.get("dataset_hash") != PR98_DATASET_HASH
            or structural_hash(dict(
                (key, value) for key, value in dataset.items()
                if key != "dataset_hash")) != PR98_DATASET_HASH
            or report.get("acceptance", {}).get("accepted") is not True
            or report.get("discovery_ready") is not True
            or report.get("adequacy", {}).get("decision") != (
                "eligible-for-preregistered-transition-model-fitting")
            or any(report.get(name) is not False for name in (
                "truth_mutated", "learning_authority",
                "policy_authority", "readout_authority"))):
        raise ValueError("retained capacity PR98 source differs")
    source_games = tuple(
        FdasRetainedCapacityTransitionSourceGame.build(value)
        for value in dataset["games"])
    games = dict((value.seed, value) for value in source_games)
    training = []
    excluded = []
    for value in dataset["rows"]:
        seed = value["seed"]
        source = games.get(seed)
        row = FdasRetainedCapacityQueryEpisodeRow.from_dict(value["row"])
        if (source is None or value["game_id"] != source.game_id
                or value["parent_audit_hash"] != source.parent_audit_hash
                or row.query.game_id != source.game_id):
            raise ValueError("retained capacity source row lineage differs")
        if row.observation_status == "terminal-observed":
            training.append(FdasRetainedCapacityTransitionTrainingRow.build(
                seed, source.game_id, source.parent_audit_hash, row))
        elif row.observation_status == "right-censored":
            excluded.append(FdasRetainedCapacityTransitionExcludedRow.build(
                seed, source.game_id, source.parent_audit_hash, row))
        else:
            raise ValueError("retained capacity observation partition differs")
    source_games = tuple(sorted(source_games, key=lambda value: value.seed))
    training = tuple(sorted(training, key=lambda value: (
        value.seed, value.row_id)))
    excluded = tuple(sorted(excluded, key=lambda value: (
        value.seed, value.row_id)))
    bins = _fit_bins(training)
    semantic = _model_semantic(
        RETAINED_CAPACITY_TRANSITION_MODEL_ID, source_games, training,
        excluded, bins)
    return FdasRetainedCapacityTransitionModel(
        1, RETAINED_CAPACITY_TRANSITION_MODEL_ID, source_games, training,
        excluded, bins, structural_hash(semantic))
