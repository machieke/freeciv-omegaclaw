"""Hierarchical, lineage-aware calibration for grounded move transitions."""

from dataclasses import dataclass
import math

from ..events.schema import structural_hash
from ..pressure.induction import InductionFeatureQuery
from .fdas_candidate_calibration import _wilson
from .fdas_candidate_choices import FdasCandidateChoiceCalibrationExport
from .fdas_candidate_transition_features import (
    CANDIDATE_TRANSITION_FEATURE_KEYS,
    CANDIDATE_TRANSITION_FEATURE_SCHEMA,
    CANDIDATE_TRANSITION_OPERATION_TYPE,
)
from .fdas_induction_labels import (
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
)


CANDIDATE_TRANSITION_CALIBRATION_SCHEMA_VERSION = 1
CANDIDATE_TRANSITION_CALIBRATION_IDENTITY = (
    "fdas-candidate-transition-calibration/1.0")
TRANSITION_FEATURE_PREFIX = "candidate-transition:"
LIFECYCLE_FEATURE_PREFIX = "context:turn_phase_band="

_FULL_KEYS = tuple(
    value for value in CANDIDATE_TRANSITION_FEATURE_KEYS
    if value != "transition_grounding_status")
_COMPACT_KEYS = (
    "actor_unit_type",
    "route_estimated_turns_band",
    "route_total_movement_cost_band",
    "source_city_relation",
    "source_other_own_units_band",
)
_ROUTE_KEYS = (
    "actor_unit_type",
    "route_estimated_turns_band",
    "source_city_relation",
)
_ETA_KEYS = ("route_estimated_turns_band",)

TRANSITION_CALIBRATION_LEVELS = (
    "action",
    "lifecycle",
    "eta",
    "eta-lifecycle",
    "route",
    "route-lifecycle",
    "compact",
    "compact-lifecycle",
    "full",
    "full-lifecycle",
)
TRANSITION_CALIBRATION_PREDICTION_ORDER = tuple(reversed(
    TRANSITION_CALIBRATION_LEVELS))
DEFAULT_TRANSITION_LEVEL_MINIMUM_LINEAGES = {
    "action": 12,
    "lifecycle": 10,
    "eta": 12,
    "eta-lifecycle": 10,
    "route": 10,
    "route-lifecycle": 8,
    "compact": 8,
    "compact-lifecycle": 6,
    "full": 6,
    "full-lifecycle": 5,
}
_PARENT_LEVEL = {
    "lifecycle": "action",
    "eta": "action",
    "eta-lifecycle": "lifecycle",
    "route": "eta",
    "route-lifecycle": "eta-lifecycle",
    "compact": "route",
    "compact-lifecycle": "route-lifecycle",
    "full": "compact",
    "full-lifecycle": "compact-lifecycle",
}


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("{} must be a positive integer".format(name))
    return value


def _probability(value, name):
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("{} must be a finite probability".format(name))
    return value


def _transition_values(query):
    values = {}
    for feature in query.features:
        if not feature.startswith(TRANSITION_FEATURE_PREFIX):
            continue
        row = feature[len(TRANSITION_FEATURE_PREFIX):].split("=", 1)
        if len(row) != 2 or not row[0] or not row[1] or row[0] in values:
            raise ValueError("transition calibration features are malformed")
        values[row[0]] = row[1]
    return values


def _lifecycle(query):
    values = tuple(
        value[len(LIFECYCLE_FEATURE_PREFIX):]
        for value in query.features
        if value.startswith(LIFECYCLE_FEATURE_PREFIX))
    if len(values) != 1 or not values[0]:
        raise ValueError("transition calibration requires exact lifecycle")
    return values[0]


def _query_scope(query):
    context = dict(query.context)
    return context.get("operation_type"), context.get("outcome_target")


def _feature_signature(level, values, lifecycle):
    if level not in TRANSITION_CALIBRATION_LEVELS:
        raise ValueError("transition calibration level is invalid")
    keys = (
        () if level in ("action", "lifecycle") else
        _ETA_KEYS if level.startswith("eta") else
        _ROUTE_KEYS if level.startswith("route") else
        _COMPACT_KEYS if level.startswith("compact") else _FULL_KEYS)
    signature = tuple("{}={}".format(key, values[key]) for key in keys)
    if level.endswith("lifecycle") or level == "lifecycle":
        signature += ("turn_phase_band={}".format(lifecycle),)
    return tuple(sorted(signature))


def _parent_signature(level, signature):
    if level == "action":
        return None
    values = dict(value.split("=", 1) for value in signature)
    lifecycle = values.get("turn_phase_band", "unknown")
    return _feature_signature(_PARENT_LEVEL[level], values, lifecycle)


def _canonical_minimums(values):
    values = dict(values)
    if set(values) != set(TRANSITION_CALIBRATION_LEVELS):
        raise ValueError("transition calibration minimums are incomplete")
    return tuple(sorted(
        (level, _positive_int(values[level], level + " minimum lineages"))
        for level in TRANSITION_CALIBRATION_LEVELS))


def _shrunk_interval(positive_mass, lineages, prior_estimate,
                     prior_strength):
    if prior_estimate is None:
        return _wilson(positive_mass, lineages)
    probability = (
        float(positive_mass) + float(prior_strength) * prior_estimate
    ) / (float(lineages) + float(prior_strength))
    return _wilson(probability * lineages, lineages)


@dataclass(frozen=True)
class FdasCandidateTransitionCalibrationBin:
    bin_id: str
    level: str
    feature_signature: tuple
    parent_bin_id: object
    raw_rows: int
    effective_lineages: int
    positive_mass: float
    prior_estimate: object
    prior_strength: float
    estimate: float
    interval_lower: float
    interval_upper: float
    lineage_ids: tuple
    result_hash: str

    def __post_init__(self):
        if not isinstance(self.bin_id, str) or not self.bin_id:
            raise ValueError("transition calibration bin ID is required")
        if self.level not in TRANSITION_CALIBRATION_LEVELS:
            raise ValueError("transition calibration bin level is invalid")
        signature = tuple(sorted(str(value)
                                 for value in self.feature_signature))
        if (len(signature) != len(set(signature))
                or any(not value or "=" not in value for value in signature)):
            raise ValueError("transition calibration signature is invalid")
        if (self.level == "action") != (not signature):
            raise ValueError("transition calibration action signature differs")
        object.__setattr__(self, "feature_signature", signature)
        if self.level == "action":
            if self.parent_bin_id is not None or self.prior_estimate is not None:
                raise ValueError("transition action bin cannot have a parent")
            if float(self.prior_strength) != 0.0:
                raise ValueError("transition action prior strength differs")
        else:
            if (not isinstance(self.parent_bin_id, str)
                    or not self.parent_bin_id):
                raise ValueError("transition child bin requires a parent")
            object.__setattr__(
                self, "prior_estimate",
                _probability(self.prior_estimate, "prior estimate"))
            if (not math.isfinite(float(self.prior_strength))
                    or float(self.prior_strength) <= 0.0):
                raise ValueError("transition child prior strength is invalid")
        object.__setattr__(self, "prior_strength", float(self.prior_strength))
        _positive_int(self.raw_rows, "transition calibration raw rows")
        _positive_int(
            self.effective_lineages,
            "transition calibration effective lineages")
        if self.effective_lineages > self.raw_rows:
            raise ValueError("transition calibration effective N differs")
        positive_mass = float(self.positive_mass)
        if (not math.isfinite(positive_mass)
                or not 0.0 <= positive_mass <= self.effective_lineages):
            raise ValueError("transition calibration positive mass is invalid")
        object.__setattr__(self, "positive_mass", positive_mass)
        for name in ("estimate", "interval_lower", "interval_upper"):
            object.__setattr__(
                self, name, _probability(getattr(self, name), name))
        if not self.interval_lower <= self.estimate <= self.interval_upper:
            raise ValueError("transition calibration interval differs")
        lineages = tuple(sorted(str(value) for value in self.lineage_ids))
        if (len(lineages) != self.effective_lineages
                or len(lineages) != len(set(lineages))
                or any(not value for value in lineages)):
            raise ValueError("transition calibration lineages are invalid")
        object.__setattr__(self, "lineage_ids", lineages)
        semantic = self._semantic()
        if (self.result_hash != structural_hash(semantic)
                or self.bin_id
                != "transition-calibration-bin-" + self.result_hash[:24]):
            raise ValueError("transition calibration bin hash differs")
        estimate, lower, upper = _shrunk_interval(
            self.positive_mass, self.effective_lineages,
            self.prior_estimate, self.prior_strength)
        if (self.estimate, self.interval_lower, self.interval_upper) != (
                estimate, lower, upper):
            raise ValueError("transition calibration bin estimate differs")

    def _semantic(self):
        return {
            "effective_lineages": self.effective_lineages,
            "feature_signature": list(self.feature_signature),
            "level": self.level,
            "lineage_ids": list(self.lineage_ids),
            "parent_bin_id": self.parent_bin_id,
            "positive_mass": self.positive_mass,
            "prior_estimate": self.prior_estimate,
            "prior_strength": self.prior_strength,
            "raw_rows": self.raw_rows,
        }

    @property
    def interval_width(self):
        return self.interval_upper - self.interval_lower

    def to_dict(self):
        return {
            **self._semantic(),
            "bin_id": self.bin_id,
            "estimate": self.estimate,
            "interval_lower": self.interval_lower,
            "interval_upper": self.interval_upper,
            "interval_width": self.interval_width,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, value):
        return cls(
            value["bin_id"], value["level"],
            tuple(value["feature_signature"]), value.get("parent_bin_id"),
            value["raw_rows"], value["effective_lineages"],
            value["positive_mass"], value.get("prior_estimate"),
            value["prior_strength"], value["estimate"],
            value["interval_lower"], value["interval_upper"],
            tuple(value["lineage_ids"]), value["result_hash"])


@dataclass(frozen=True)
class FdasCandidateTransitionCalibrationPrediction:
    query_id: str
    status: str
    reason: str
    operation_type: str
    lifecycle_state: str
    level: object
    feature_signature: tuple
    bin_id: object
    estimate: object
    interval_lower: object
    interval_upper: object
    raw_rows: int
    effective_lineages: int
    model_result_hash: str
    result_hash: str

    def __post_init__(self):
        if self.status not in ("estimated", "abstained"):
            raise ValueError("transition prediction status is invalid")
        for value, name in (
                (self.query_id, "query ID"), (self.reason, "reason"),
                (self.operation_type, "operation type"),
                (self.lifecycle_state, "lifecycle state"),
                (self.model_result_hash, "model hash"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("transition prediction {} is required".format(
                    name))
        signature = tuple(sorted(str(value)
                                 for value in self.feature_signature))
        object.__setattr__(self, "feature_signature", signature)
        if self.status == "estimated":
            if (self.level not in TRANSITION_CALIBRATION_LEVELS
                    or not isinstance(self.bin_id, str) or not self.bin_id):
                raise ValueError("estimated transition prediction lacks bin")
            for name in ("estimate", "interval_lower", "interval_upper"):
                object.__setattr__(
                    self, name, _probability(getattr(self, name), name))
            _positive_int(self.raw_rows, "transition prediction raw rows")
            _positive_int(
                self.effective_lineages,
                "transition prediction effective lineages")
        elif (self.level is not None or self.bin_id is not None
              or signature or any(value is not None for value in (
                  self.estimate, self.interval_lower, self.interval_upper))
              or self.raw_rows != 0 or self.effective_lineages != 0):
            raise ValueError("abstained transition prediction carries estimate")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("transition prediction hash differs")

    def _semantic(self):
        return {
            "bin_id": self.bin_id,
            "feature_signature": list(self.feature_signature),
            "level": self.level,
            "lifecycle_state": self.lifecycle_state,
            "model_result_hash": self.model_result_hash,
            "operation_type": self.operation_type,
            "query_id": self.query_id,
            "reason": self.reason,
            "status": self.status,
        }

    def to_dict(self):
        return {
            **self._semantic(),
            "effective_lineages": self.effective_lineages,
            "estimate": self.estimate,
            "interval_lower": self.interval_lower,
            "interval_upper": self.interval_upper,
            "policy_authority": False,
            "raw_rows": self.raw_rows,
            "readout_authority": False,
            "result_hash": self.result_hash,
            "truth_mutated": False,
        }


@dataclass(frozen=True)
class FdasCandidateTransitionCalibrationModel:
    schema_version: int
    model_id: str
    outcome_target: str
    minimum_level_lineages: tuple
    prior_strength: float
    source_export_hashes: tuple
    source_store_digests: tuple
    bins: tuple
    result_hash: str

    def __post_init__(self):
        if self.schema_version != (
                CANDIDATE_TRANSITION_CALIBRATION_SCHEMA_VERSION):
            raise ValueError("unsupported transition calibration schema")
        if not isinstance(self.model_id, str) or not self.model_id:
            raise ValueError("transition calibration model ID is required")
        if self.outcome_target != DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET:
            raise ValueError("transition calibration target differs")
        minimums = _canonical_minimums(dict(self.minimum_level_lineages))
        object.__setattr__(self, "minimum_level_lineages", minimums)
        if (not math.isfinite(float(self.prior_strength))
                or float(self.prior_strength) <= 0.0):
            raise ValueError("transition calibration prior is invalid")
        object.__setattr__(self, "prior_strength", float(self.prior_strength))
        for name in ("source_export_hashes", "source_store_digests"):
            values = tuple(sorted(str(value) for value in getattr(self, name)))
            if (not values or len(values) != len(set(values))
                    or any(not value for value in values)):
                raise ValueError("transition calibration sources overlap")
            object.__setattr__(self, name, values)
        bins = tuple(sorted(
            self.bins,
            key=lambda value: (
                TRANSITION_CALIBRATION_LEVELS.index(value.level),
                value.feature_signature)))
        if (not bins or any(
                not isinstance(value, FdasCandidateTransitionCalibrationBin)
                for value in bins)
                or len({value.bin_id for value in bins}) != len(bins)
                or len({(value.level, value.feature_signature)
                        for value in bins}) != len(bins)):
            raise ValueError("transition calibration bins are invalid")
        by_id = {value.bin_id: value for value in bins}
        for value in bins:
            if value.level == "action":
                continue
            parent = by_id.get(value.parent_bin_id)
            if (parent is None
                    or parent.level != _PARENT_LEVEL[value.level]
                    or parent.feature_signature
                    != _parent_signature(
                        value.level, value.feature_signature)
                    or parent.estimate != value.prior_estimate
                    or value.prior_strength != self.prior_strength):
                raise ValueError("transition calibration parent differs")
        object.__setattr__(self, "bins", bins)
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("transition calibration model hash differs")

    def _semantic(self):
        return {
            "bins": [value.to_dict() for value in self.bins],
            "model_id": self.model_id,
            "model_identity": CANDIDATE_TRANSITION_CALIBRATION_IDENTITY,
            "minimum_level_lineages": dict(self.minimum_level_lineages),
            "outcome_target": self.outcome_target,
            "policy_authority": False,
            "prior_strength": self.prior_strength,
            "readout_authority": False,
            "schema_version": self.schema_version,
            "source_export_hashes": list(self.source_export_hashes),
            "source_store_digests": list(self.source_store_digests),
            "truth_mutated": False,
        }

    def _prediction(self, query, status, reason, lifecycle,
                    bin_value=None):
        operation_type = _query_scope(query)[0] or "unknown"
        semantic = {
            "bin_id": None if bin_value is None else bin_value.bin_id,
            "feature_signature": (
                [] if bin_value is None
                else list(bin_value.feature_signature)),
            "level": None if bin_value is None else bin_value.level,
            "lifecycle_state": lifecycle,
            "model_result_hash": self.result_hash,
            "operation_type": operation_type,
            "query_id": query.query_id,
            "reason": reason,
            "status": status,
        }
        return FdasCandidateTransitionCalibrationPrediction(
            query.query_id, status, reason, operation_type, lifecycle,
            None if bin_value is None else bin_value.level,
            () if bin_value is None else bin_value.feature_signature,
            None if bin_value is None else bin_value.bin_id,
            None if bin_value is None else bin_value.estimate,
            None if bin_value is None else bin_value.interval_lower,
            None if bin_value is None else bin_value.interval_upper,
            0 if bin_value is None else bin_value.raw_rows,
            0 if bin_value is None else bin_value.effective_lineages,
            self.result_hash, structural_hash(semantic))

    def predict(self, query):
        if not isinstance(query, InductionFeatureQuery):
            raise TypeError("transition calibration requires feature query")
        operation_type, outcome_target = _query_scope(query)
        try:
            lifecycle = _lifecycle(query)
        except ValueError:
            lifecycle = "unknown"
        if (operation_type != CANDIDATE_TRANSITION_OPERATION_TYPE
                or outcome_target != self.outcome_target):
            return self._prediction(
                query, "abstained", "outside-transition-move-domain",
                lifecycle)
        context = dict(query.context)
        try:
            values = _transition_values(query)
        except ValueError:
            values = {}
        if (context.get("candidate_transition_feature_schema")
                != CANDIDATE_TRANSITION_FEATURE_SCHEMA
                or set(values) != set(CANDIDATE_TRANSITION_FEATURE_KEYS)
                or values.get("transition_grounding_status") != "complete"
                or lifecycle == "unknown"):
            return self._prediction(
                query, "abstained",
                "missing-or-incomplete-transition-grounding", lifecycle)
        minimums = dict(self.minimum_level_lineages)
        by_key = {
            (value.level, value.feature_signature): value
            for value in self.bins}
        for level in TRANSITION_CALIBRATION_PREDICTION_ORDER:
            signature = _feature_signature(level, values, lifecycle)
            bin_value = by_key.get((level, signature))
            if (bin_value is not None
                    and bin_value.effective_lineages >= minimums[level]):
                return self._prediction(
                    query, "estimated", level + "-estimate", lifecycle,
                    bin_value)
        return self._prediction(
            query, "abstained",
            "insufficient-independent-transition-lineage-support",
            lifecycle)

    def to_dict(self):
        return {**self._semantic(), "result_hash": self.result_hash}

    @classmethod
    def from_dict(cls, value):
        if any(value.get(name) is not False for name in (
                "policy_authority", "readout_authority", "truth_mutated")):
            raise ValueError("transition calibration artifact grants authority")
        return cls(
            value["schema_version"], value["model_id"],
            value["outcome_target"],
            tuple(sorted(value["minimum_level_lineages"].items())),
            value["prior_strength"], tuple(value["source_export_hashes"]),
            tuple(value["source_store_digests"]),
            tuple(FdasCandidateTransitionCalibrationBin.from_dict(row)
                  for row in value["bins"]), value["result_hash"])


def _lineage_rows(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["lineage_id"], []).append(row["outcome"])
    return {
        key: sum(values) / float(len(values))
        for key, values in grouped.items()}


def _build_bin(level, signature, rows, parent, prior_strength):
    outcomes = _lineage_rows(rows)
    positive_mass = sum(outcomes.values())
    estimate, lower, upper = _shrunk_interval(
        positive_mass, len(outcomes),
        None if parent is None else parent.estimate,
        0.0 if parent is None else prior_strength)
    semantic = {
        "effective_lineages": len(outcomes),
        "feature_signature": list(signature),
        "level": level,
        "lineage_ids": sorted(outcomes),
        "parent_bin_id": None if parent is None else parent.bin_id,
        "positive_mass": positive_mass,
        "prior_estimate": None if parent is None else parent.estimate,
        "prior_strength": 0.0 if parent is None else float(prior_strength),
        "raw_rows": len(rows),
    }
    result_hash = structural_hash(semantic)
    return FdasCandidateTransitionCalibrationBin(
        "transition-calibration-bin-" + result_hash[:24],
        level, signature, semantic["parent_bin_id"], len(rows),
        len(outcomes), positive_mass, semantic["prior_estimate"],
        semantic["prior_strength"], estimate, lower, upper,
        tuple(outcomes), result_hash)


def fit_candidate_transition_calibration(
        exports, model_id, minimum_level_lineages=None,
        prior_strength=4.0):
    """Fit selected-only grounded move outcomes with explicit backoff."""
    exports = tuple(exports)
    if (not exports or any(
            not isinstance(value, FdasCandidateChoiceCalibrationExport)
            for value in exports)):
        raise TypeError("transition calibration requires typed exports")
    if not isinstance(model_id, str) or not model_id:
        raise ValueError("transition calibration model identity is required")
    if (len({value.source_store_digest for value in exports}) != len(exports)
            or len({value.result_hash for value in exports}) != len(exports)):
        raise ValueError("transition calibration sources overlap")
    minimums = _canonical_minimums(
        DEFAULT_TRANSITION_LEVEL_MINIMUM_LINEAGES
        if minimum_level_lineages is None else minimum_level_lineages)
    if (not math.isfinite(float(prior_strength))
            or float(prior_strength) <= 0.0):
        raise ValueError("transition calibration prior is invalid")
    rows = []
    episode_ids = set()
    for export in exports:
        if export.outcome_target != DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET:
            raise ValueError("transition calibration export target differs")
        for episode in export.examples:
            if episode.episode_id in episode_ids:
                raise ValueError("transition calibration episodes overlap")
            episode_ids.add(episode.episode_id)
            query = InductionFeatureQuery(
                episode.episode_id, episode.context, episode.features,
                episode.provenance_ids)
            operation_type, outcome_target = _query_scope(query)
            if operation_type != CANDIDATE_TRANSITION_OPERATION_TYPE:
                continue
            if outcome_target != DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET:
                raise ValueError("transition calibration row target differs")
            context = dict(query.context)
            values = _transition_values(query)
            lifecycle = _lifecycle(query)
            if (context.get("candidate_transition_feature_schema")
                    != CANDIDATE_TRANSITION_FEATURE_SCHEMA
                    or set(values) != set(CANDIDATE_TRANSITION_FEATURE_KEYS)
                    or values["transition_grounding_status"] != "complete"):
                raise ValueError(
                    "transition calibration row grounding is incomplete")
            lineages = tuple(
                value[len("candidate-lineage:"):]
                for value in episode.provenance_ids
                if value.startswith("candidate-lineage:"))
            if len(lineages) != 1 or not lineages[0]:
                raise ValueError(
                    "transition calibration row requires exact lineage")
            rows.append({
                "lifecycle": lifecycle,
                "lineage_id": lineages[0],
                "outcome": 1.0 if episode.outcome else 0.0,
                "values": values,
            })
    if not rows:
        raise ValueError("transition calibration has no selected move outcomes")
    bins = []
    by_key = {}
    for level in TRANSITION_CALIBRATION_LEVELS:
        groups = {}
        for row in rows:
            signature = _feature_signature(
                level, row["values"], row["lifecycle"])
            groups.setdefault(signature, []).append(row)
        for signature, group in sorted(groups.items()):
            parent = None
            if level != "action":
                parent_level = _PARENT_LEVEL[level]
                parent_signature = _feature_signature(
                    parent_level, group[0]["values"], group[0]["lifecycle"])
                parent = by_key.get((parent_level, parent_signature))
                if parent is None:
                    raise RuntimeError("transition calibration parent is absent")
            bin_value = _build_bin(
                level, signature, tuple(group), parent,
                float(prior_strength))
            bins.append(bin_value)
            by_key[(level, signature)] = bin_value
    semantic = {
        "bins": [value.to_dict() for value in bins],
        "model_id": model_id,
        "model_identity": CANDIDATE_TRANSITION_CALIBRATION_IDENTITY,
        "minimum_level_lineages": dict(minimums),
        "outcome_target": DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
        "policy_authority": False,
        "prior_strength": float(prior_strength),
        "readout_authority": False,
        "schema_version": CANDIDATE_TRANSITION_CALIBRATION_SCHEMA_VERSION,
        "source_export_hashes": sorted(
            value.result_hash for value in exports),
        "source_store_digests": sorted(
            value.source_store_digest for value in exports),
        "truth_mutated": False,
    }
    return FdasCandidateTransitionCalibrationModel(
        CANDIDATE_TRANSITION_CALIBRATION_SCHEMA_VERSION, model_id,
        DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET, minimums,
        float(prior_strength), tuple(semantic["source_export_hashes"]),
        tuple(semantic["source_store_digests"]), tuple(bins),
        structural_hash(semantic))
