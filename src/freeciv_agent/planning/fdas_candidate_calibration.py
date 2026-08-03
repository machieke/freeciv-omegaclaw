"""Action-stratified, lineage-aware FDAS candidate calibration artifacts."""

from dataclasses import dataclass
import math

from ..events.schema import structural_hash
from ..pressure.induction import InductionFeatureQuery
from .fdas_candidate_choices import (
    DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES,
    FdasCandidateChoiceCalibrationExport,
)
from .fdas_induction_labels import (
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
)


CANDIDATE_CALIBRATION_SCHEMA_VERSION = 1
CALIBRATION_MODEL_IDENTITY = "fdas-candidate-calibration/1.0"
LIFECYCLE_FEATURE_PREFIX = "context:turn_phase_band="


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("{} must be a positive integer".format(name))
    return value


def _finite_probability(value, name):
    value = float(value)
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise ValueError("{} must be a finite probability".format(name))
    return value


def _single_prefixed(values, prefix, name):
    matches = tuple(
        value[len(prefix):] for value in values if value.startswith(prefix))
    if len(matches) != 1 or not matches[0]:
        raise ValueError("calibration row requires exact {}".format(name))
    return matches[0]


def _query_operation_type(query):
    context = dict(query.context)
    operation_type = context.get("operation_type")
    if operation_type not in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES:
        raise ValueError("calibration row operation stratum is unsupported")
    if context.get("outcome_target") != (
            DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET):
        raise ValueError("calibration row outcome target differs")
    return operation_type


def _query_lifecycle_state(query):
    return _single_prefixed(
        query.features, LIFECYCLE_FEATURE_PREFIX, "lifecycle state")


def _wilson(positive_mass, effective_lineages, z=1.959963984540054):
    n = float(effective_lineages)
    p = float(positive_mass) / n
    denominator = 1.0 + (z * z / n)
    center = (p + z * z / (2.0 * n)) / denominator
    radius = z * math.sqrt(
        (p * (1.0 - p) / n) + (z * z / (4.0 * n * n)))
    radius /= denominator
    return center, max(0.0, center - radius), min(1.0, center + radius)


@dataclass(frozen=True)
class FdasCandidateCalibrationBin:
    """One action or action/lifecycle estimate with cluster-effective N."""

    bin_id: str
    level: str
    operation_type: str
    lifecycle_state: object
    raw_rows: int
    effective_lineages: int
    positive_mass: float
    estimate: float
    interval_lower: float
    interval_upper: float
    lineage_ids: tuple
    result_hash: str

    def __post_init__(self):
        if not isinstance(self.bin_id, str) or not self.bin_id:
            raise ValueError("calibration bin ID is required")
        if self.level not in ("action", "lifecycle"):
            raise ValueError("calibration bin level is invalid")
        if self.operation_type not in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES:
            raise ValueError("calibration bin operation type is invalid")
        if self.level == "action" and self.lifecycle_state is not None:
            raise ValueError("action calibration bin cannot carry lifecycle")
        if self.level == "lifecycle" and (
                not isinstance(self.lifecycle_state, str)
                or not self.lifecycle_state):
            raise ValueError("lifecycle calibration bin requires state")
        _positive_int(self.raw_rows, "calibration raw rows")
        _positive_int(
            self.effective_lineages, "calibration effective lineages")
        if self.effective_lineages > self.raw_rows:
            raise ValueError("calibration effective N exceeds raw rows")
        positive_mass = float(self.positive_mass)
        if (not math.isfinite(positive_mass) or positive_mass < 0.0
                or positive_mass > self.effective_lineages):
            raise ValueError("calibration positive mass is invalid")
        object.__setattr__(self, "positive_mass", positive_mass)
        for name in ("estimate", "interval_lower", "interval_upper"):
            object.__setattr__(
                self, name, _finite_probability(getattr(self, name), name))
        if not self.interval_lower <= self.estimate <= self.interval_upper:
            raise ValueError("calibration estimate is outside interval")
        lineages = tuple(sorted(str(value) for value in self.lineage_ids))
        if (len(lineages) != self.effective_lineages
                or any(not value for value in lineages)
                or len(lineages) != len(set(lineages))):
            raise ValueError("calibration lineage identities are invalid")
        object.__setattr__(self, "lineage_ids", lineages)
        if not isinstance(self.result_hash, str) or not self.result_hash:
            raise ValueError("calibration bin result hash is required")
        semantic = {
            "effective_lineages": self.effective_lineages,
            "level": self.level,
            "lifecycle_state": self.lifecycle_state,
            "lineage_ids": list(self.lineage_ids),
            "operation_type": self.operation_type,
            "positive_mass": self.positive_mass,
            "raw_rows": self.raw_rows,
        }
        if self.result_hash != structural_hash(semantic):
            raise ValueError("calibration bin result hash differs")
        estimate, lower, upper = _wilson(
            self.positive_mass, self.effective_lineages)
        if (self.bin_id != "calibration-bin-" + self.result_hash[:28]
                or (self.estimate, self.interval_lower, self.interval_upper)
                != (estimate, lower, upper)):
            raise ValueError("calibration bin estimate differs")

    @property
    def interval_width(self):
        return self.interval_upper - self.interval_lower

    def to_dict(self):
        return {
            "bin_id": self.bin_id,
            "effective_lineages": self.effective_lineages,
            "estimate": self.estimate,
            "interval_lower": self.interval_lower,
            "interval_upper": self.interval_upper,
            "interval_width": self.interval_width,
            "level": self.level,
            "lifecycle_state": self.lifecycle_state,
            "lineage_ids": list(self.lineage_ids),
            "operation_type": self.operation_type,
            "positive_mass": self.positive_mass,
            "raw_rows": self.raw_rows,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, value):
        return cls(
            value["bin_id"], value["level"], value["operation_type"],
            value.get("lifecycle_state"), value["raw_rows"],
            value["effective_lineages"], value["positive_mass"],
            value["estimate"], value["interval_lower"],
            value["interval_upper"], tuple(value["lineage_ids"]),
            value["result_hash"])


@dataclass(frozen=True)
class FdasCandidateCalibrationPrediction:
    query_id: str
    status: str
    reason: str
    operation_type: str
    lifecycle_state: str
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
            raise ValueError("calibration prediction status is invalid")
        for value, name in (
                (self.query_id, "query ID"), (self.reason, "reason"),
                (self.operation_type, "operation type"),
                (self.lifecycle_state, "lifecycle state"),
                (self.model_result_hash, "model hash"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("calibration prediction {} is required".format(
                    name))
        if self.status == "estimated":
            if not isinstance(self.bin_id, str) or not self.bin_id:
                raise ValueError("estimated prediction requires bin")
            for name in ("estimate", "interval_lower", "interval_upper"):
                object.__setattr__(
                    self, name,
                    _finite_probability(getattr(self, name), name))
            _positive_int(self.raw_rows, "prediction raw rows")
            _positive_int(
                self.effective_lineages, "prediction effective lineages")
        elif any(value is not None for value in (
                self.bin_id, self.estimate, self.interval_lower,
                self.interval_upper)) or self.raw_rows != 0 or (
                    self.effective_lineages != 0):
            raise ValueError("abstained prediction carries an estimate")
        if self.operation_type not in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES:
            raise ValueError("calibration prediction operation is invalid")
        semantic = {
            "bin_id": self.bin_id,
            "lifecycle_state": self.lifecycle_state,
            "model_result_hash": self.model_result_hash,
            "operation_type": self.operation_type,
            "query_id": self.query_id,
            "reason": self.reason,
            "status": self.status,
        }
        if self.result_hash != structural_hash(semantic):
            raise ValueError("calibration prediction result hash differs")

    def to_dict(self):
        return {
            "bin_id": self.bin_id,
            "effective_lineages": self.effective_lineages,
            "estimate": self.estimate,
            "interval_lower": self.interval_lower,
            "interval_upper": self.interval_upper,
            "lifecycle_state": self.lifecycle_state,
            "model_result_hash": self.model_result_hash,
            "operation_type": self.operation_type,
            "policy_authority": False,
            "query_id": self.query_id,
            "raw_rows": self.raw_rows,
            "readout_authority": False,
            "reason": self.reason,
            "result_hash": self.result_hash,
            "status": self.status,
            "truth_mutated": False,
        }


@dataclass(frozen=True)
class FdasCandidateCalibrationModel:
    schema_version: int
    model_id: str
    outcome_target: str
    minimum_action_lineages: int
    minimum_lifecycle_lineages: int
    source_export_hashes: tuple
    source_store_digests: tuple
    bins: tuple
    result_hash: str

    def __post_init__(self):
        if self.schema_version != CANDIDATE_CALIBRATION_SCHEMA_VERSION:
            raise ValueError("unsupported candidate calibration schema")
        if not isinstance(self.model_id, str) or not self.model_id:
            raise ValueError("candidate calibration model ID is required")
        if self.outcome_target != DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET:
            raise ValueError("candidate calibration target is unsupported")
        _positive_int(
            self.minimum_action_lineages, "minimum action lineages")
        _positive_int(
            self.minimum_lifecycle_lineages, "minimum lifecycle lineages")
        for name in ("source_export_hashes", "source_store_digests"):
            values = tuple(sorted(str(value) for value in getattr(self, name)))
            if (not values or any(not value for value in values)
                    or len(values) != len(set(values))):
                raise ValueError("calibration sources must be independent")
            object.__setattr__(self, name, values)
        bins = tuple(sorted(
            self.bins,
            key=lambda value: (
                value.operation_type, value.level,
                value.lifecycle_state or "")))
        if (not bins or any(not isinstance(value, FdasCandidateCalibrationBin)
                            for value in bins)
                or len({value.bin_id for value in bins}) != len(bins)):
            raise ValueError("candidate calibration bins are invalid")
        object.__setattr__(self, "bins", bins)
        if not isinstance(self.result_hash, str) or not self.result_hash:
            raise ValueError("candidate calibration model hash is required")
        semantic = {
            "bins": [value.to_dict() for value in self.bins],
            "model_id": self.model_id,
            "minimum_action_lineages": self.minimum_action_lineages,
            "minimum_lifecycle_lineages": self.minimum_lifecycle_lineages,
            "model_identity": CALIBRATION_MODEL_IDENTITY,
            "outcome_target": self.outcome_target,
            "policy_authority": False,
            "readout_authority": False,
            "schema_version": self.schema_version,
            "source_export_hashes": list(self.source_export_hashes),
            "source_store_digests": list(self.source_store_digests),
            "truth_mutated": False,
        }
        if self.result_hash != structural_hash(semantic):
            raise ValueError("candidate calibration model hash differs")

    def _prediction(self, query, status, reason, bin_value=None):
        operation_type = _query_operation_type(query)
        lifecycle_state = _query_lifecycle_state(query)
        semantic = {
            "bin_id": None if bin_value is None else bin_value.bin_id,
            "lifecycle_state": lifecycle_state,
            "model_result_hash": self.result_hash,
            "operation_type": operation_type,
            "query_id": query.query_id,
            "reason": reason,
            "status": status,
        }
        return FdasCandidateCalibrationPrediction(
            query.query_id, status, reason, operation_type, lifecycle_state,
            None if bin_value is None else bin_value.bin_id,
            None if bin_value is None else bin_value.estimate,
            None if bin_value is None else bin_value.interval_lower,
            None if bin_value is None else bin_value.interval_upper,
            0 if bin_value is None else bin_value.raw_rows,
            0 if bin_value is None else bin_value.effective_lineages,
            self.result_hash, structural_hash(semantic))

    def predict(self, query):
        if not isinstance(query, InductionFeatureQuery):
            raise TypeError("candidate calibration requires feature query")
        operation_type = _query_operation_type(query)
        lifecycle_state = _query_lifecycle_state(query)
        lifecycle = next((
            value for value in self.bins
            if (value.level == "lifecycle"
                and value.operation_type == operation_type
                and value.lifecycle_state == lifecycle_state)), None)
        if (lifecycle is not None
                and lifecycle.effective_lineages
                >= self.minimum_lifecycle_lineages):
            return self._prediction(
                query, "estimated", "lifecycle-stratum-estimate", lifecycle)
        action = next((
            value for value in self.bins
            if (value.level == "action"
                and value.operation_type == operation_type)), None)
        if (action is not None
                and action.effective_lineages
                >= self.minimum_action_lineages):
            return self._prediction(
                query, "estimated", "action-stratum-backoff", action)
        return self._prediction(
            query, "abstained", "insufficient-independent-lineage-support")

    def to_dict(self):
        return {
            "bins": [value.to_dict() for value in self.bins],
            "model_id": self.model_id,
            "minimum_action_lineages": self.minimum_action_lineages,
            "minimum_lifecycle_lineages": self.minimum_lifecycle_lineages,
            "outcome_target": self.outcome_target,
            "policy_authority": False,
            "readout_authority": False,
            "result_hash": self.result_hash,
            "schema_version": self.schema_version,
            "source_export_hashes": list(self.source_export_hashes),
            "source_store_digests": list(self.source_store_digests),
            "truth_mutated": False,
        }

    @classmethod
    def from_dict(cls, value):
        if any(value.get(name) is not False for name in (
                "policy_authority", "readout_authority", "truth_mutated")):
            raise ValueError("candidate calibration artifact grants authority")
        return cls(
            value["schema_version"], value["model_id"],
            value["outcome_target"], value["minimum_action_lineages"],
            value["minimum_lifecycle_lineages"],
            tuple(value["source_export_hashes"]),
            tuple(value["source_store_digests"]),
            tuple(FdasCandidateCalibrationBin.from_dict(row)
                  for row in value["bins"]), value["result_hash"])


def _build_bin(level, operation_type, lifecycle_state, rows):
    lineage_outcomes = {}
    for row in rows:
        lineage_outcomes.setdefault(row["lineage_id"], []).append(
            1.0 if row["outcome"] else 0.0)
    lineage_means = dict(
        (key, sum(values) / float(len(values)))
        for key, values in lineage_outcomes.items())
    positive_mass = sum(lineage_means.values())
    estimate, lower, upper = _wilson(
        positive_mass, len(lineage_means))
    semantic = {
        "effective_lineages": len(lineage_means),
        "level": level,
        "lifecycle_state": lifecycle_state,
        "lineage_ids": sorted(lineage_means),
        "operation_type": operation_type,
        "positive_mass": positive_mass,
        "raw_rows": len(rows),
    }
    result_hash = structural_hash(semantic)
    return FdasCandidateCalibrationBin(
        "calibration-bin-" + result_hash[:28], level, operation_type,
        lifecycle_state, len(rows), len(lineage_means), positive_mass,
        estimate, lower, upper, tuple(lineage_means), result_hash)


def fit_candidate_calibration(
        exports, model_id, minimum_action_lineages=5,
        minimum_lifecycle_lineages=3):
    """Fit selected-only action/lifecycle estimates; never infer alternatives."""
    exports = tuple(exports)
    if (not exports or any(
            not isinstance(value, FdasCandidateChoiceCalibrationExport)
            for value in exports)):
        raise TypeError("candidate calibration requires typed exports")
    _positive_int(minimum_action_lineages, "minimum action lineages")
    _positive_int(minimum_lifecycle_lineages, "minimum lifecycle lineages")
    if not isinstance(model_id, str) or not model_id:
        raise ValueError("candidate calibration model identity is required")
    if len({value.source_store_digest for value in exports}) != len(exports):
        raise ValueError("candidate calibration source stores overlap")
    if len({value.result_hash for value in exports}) != len(exports):
        raise ValueError("candidate calibration exports overlap")
    if any(value.operation_type != "fdas-defense-choice-surface/1.0"
           or value.outcome_target
           != DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET
           for value in exports):
        raise ValueError("candidate calibration export scope differs")
    rows = []
    episode_ids = set()
    for export in exports:
        for episode in export.examples:
            if episode.episode_id in episode_ids:
                raise ValueError("candidate calibration episodes overlap")
            episode_ids.add(episode.episode_id)
            query = InductionFeatureQuery(
                episode.episode_id, episode.context, episode.features,
                episode.provenance_ids)
            rows.append({
                "lifecycle_state": _query_lifecycle_state(query),
                "lineage_id": _single_prefixed(
                    episode.provenance_ids, "candidate-lineage:",
                    "candidate lifecycle lineage"),
                "operation_type": _query_operation_type(query),
                "outcome": bool(episode.outcome),
            })
    if not rows:
        raise ValueError("candidate calibration has no selected outcomes")
    bins = []
    for operation_type in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES:
        action_rows = tuple(
            value for value in rows
            if value["operation_type"] == operation_type)
        if not action_rows:
            continue
        bins.append(_build_bin(
            "action", operation_type, None, action_rows))
        for lifecycle_state in sorted(set(
                value["lifecycle_state"] for value in action_rows)):
            bins.append(_build_bin(
                "lifecycle", operation_type, lifecycle_state,
                tuple(value for value in action_rows
                      if value["lifecycle_state"] == lifecycle_state)))
    semantic = {
        "bins": [value.to_dict() for value in bins],
        "model_id": model_id,
        "minimum_action_lineages": minimum_action_lineages,
        "minimum_lifecycle_lineages": minimum_lifecycle_lineages,
        "model_identity": CALIBRATION_MODEL_IDENTITY,
        "outcome_target": DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
        "policy_authority": False,
        "readout_authority": False,
        "schema_version": CANDIDATE_CALIBRATION_SCHEMA_VERSION,
        "source_export_hashes": sorted(
            value.result_hash for value in exports),
        "source_store_digests": sorted(
            value.source_store_digest for value in exports),
        "truth_mutated": False,
    }
    return FdasCandidateCalibrationModel(
        CANDIDATE_CALIBRATION_SCHEMA_VERSION, model_id,
        DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
        minimum_action_lineages, minimum_lifecycle_lineages,
        tuple(semantic["source_export_hashes"]),
        tuple(semantic["source_store_digests"]), tuple(bins),
        structural_hash(semantic))
