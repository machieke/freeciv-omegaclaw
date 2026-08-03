"""Decision-safe candidate union from calibrated selected-action estimates."""

from dataclasses import dataclass
import math

from ..events.schema import structural_hash
from ..pressure.induction import InductionFeatureQuery
from ..pressure.scheduler import OperationScore
from .fdas import ShadowOperationCandidate
from .fdas_candidate_calibration import FdasCandidateCalibrationModel
from .fdas_candidate_choices import (
    DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES,
)


CALIBRATED_CANDIDATE_UNION_IDENTITY = (
    "fdas-calibrated-candidate-union/1.0")


@dataclass(frozen=True)
class FdasCalibratedCandidateReadout:
    operation_id: str
    action_key: str
    operation_type: str
    baseline_rank: int
    baseline_priority: float
    prediction_status: str
    prediction_reason: str
    prediction_result_hash: str
    estimate: object
    interval_lower: object
    interval_upper: object
    effective_lineages: int
    eligible_for_calibrated_recall: bool
    eligibility_reason: str

    def __post_init__(self):
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.action_key, "action key"),
                (self.prediction_reason, "prediction reason"),
                (self.prediction_result_hash, "prediction hash"),
                (self.eligibility_reason, "eligibility reason")):
            if not isinstance(value, str) or not value:
                raise ValueError("candidate readout {} is required".format(
                    name))
        if self.operation_type not in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES:
            raise ValueError("candidate readout action stratum is invalid")
        if (isinstance(self.baseline_rank, bool)
                or not isinstance(self.baseline_rank, int)
                or self.baseline_rank < 1):
            raise ValueError("candidate readout baseline rank is invalid")
        priority = float(self.baseline_priority)
        if not math.isfinite(priority):
            raise ValueError("candidate readout priority is invalid")
        object.__setattr__(self, "baseline_priority", priority)
        if self.prediction_status not in ("estimated", "abstained"):
            raise ValueError("candidate readout prediction status is invalid")
        if self.prediction_status == "estimated":
            values = tuple(float(value) for value in (
                self.estimate, self.interval_lower, self.interval_upper))
            if (any(not math.isfinite(value) or not 0.0 <= value <= 1.0
                    for value in values)
                    or not values[1] <= values[0] <= values[2]
                    or isinstance(self.effective_lineages, bool)
                    or not isinstance(self.effective_lineages, int)
                    or self.effective_lineages < 1):
                raise ValueError("candidate readout estimate is invalid")
            object.__setattr__(self, "estimate", values[0])
            object.__setattr__(self, "interval_lower", values[1])
            object.__setattr__(self, "interval_upper", values[2])
        elif (any(value is not None for value in (
                self.estimate, self.interval_lower, self.interval_upper))
                or self.effective_lineages != 0
                or self.eligible_for_calibrated_recall):
            raise ValueError("abstained candidate readout carries recall")
        if not isinstance(self.eligible_for_calibrated_recall, bool):
            raise TypeError("candidate recall eligibility must be boolean")

    @property
    def interval_width(self):
        if self.estimate is None:
            return None
        return self.interval_upper - self.interval_lower

    def to_dict(self):
        return {
            "action_key": self.action_key,
            "baseline_priority": self.baseline_priority,
            "baseline_rank": self.baseline_rank,
            "effective_lineages": self.effective_lineages,
            "eligible_for_calibrated_recall": (
                self.eligible_for_calibrated_recall),
            "eligibility_reason": self.eligibility_reason,
            "estimate": self.estimate,
            "interval_lower": self.interval_lower,
            "interval_upper": self.interval_upper,
            "interval_width": self.interval_width,
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "prediction_reason": self.prediction_reason,
            "prediction_result_hash": self.prediction_result_hash,
            "prediction_status": self.prediction_status,
        }


@dataclass(frozen=True)
class FdasCalibratedCandidateMember:
    operation_id: str
    reasons: tuple

    def __post_init__(self):
        if not isinstance(self.operation_id, str) or not self.operation_id:
            raise ValueError("calibrated union member requires operation")
        reasons = tuple(sorted(str(value) for value in self.reasons))
        if (not reasons or any(not value for value in reasons)
                or len(reasons) != len(set(reasons))):
            raise ValueError("calibrated union reasons are invalid")
        object.__setattr__(self, "reasons", reasons)

    def to_dict(self):
        return {
            "operation_id": self.operation_id,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class FdasCalibratedCandidateUnion:
    snapshot_id: str
    revision_id: str
    model_result_hash: str
    baseline_selected_operation_id: str
    scalar_top_k: int
    calibrated_per_action: int
    maximum_interval_width: float
    members: tuple
    readouts: tuple
    calibrated_added_operation_ids: tuple
    abstained_operation_ids: tuple
    result_hash: str

    def __post_init__(self):
        for value, name in (
                (self.snapshot_id, "snapshot ID"),
                (self.revision_id, "revision ID"),
                (self.model_result_hash, "model hash"),
                (self.baseline_selected_operation_id, "baseline selection"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("calibrated union {} is required".format(
                    name))
        for value, name in (
                (self.scalar_top_k, "scalar top-k"),
                (self.calibrated_per_action, "calibrated per action")):
            if (isinstance(value, bool) or not isinstance(value, int)
                    or value < 1):
                raise ValueError("{} must be positive".format(name))
        width = float(self.maximum_interval_width)
        if not math.isfinite(width) or not 0.0 < width <= 1.0:
            raise ValueError("calibrated union interval width is invalid")
        object.__setattr__(self, "maximum_interval_width", width)
        if (not self.members
                or any(not isinstance(value, FdasCalibratedCandidateMember)
                       for value in self.members)):
            raise TypeError("calibrated union requires typed members")
        if (not self.readouts
                or any(not isinstance(value, FdasCalibratedCandidateReadout)
                       for value in self.readouts)):
            raise TypeError("calibrated union requires typed readouts")
        member_ids = tuple(value.operation_id for value in self.members)
        readout_ids = tuple(value.operation_id for value in self.readouts)
        if (len(member_ids) != len(set(member_ids))
                or len(readout_ids) != len(set(readout_ids))
                or set(member_ids) - set(readout_ids)
                or self.baseline_selected_operation_id not in member_ids):
            raise ValueError("calibrated union membership is inconsistent")
        additions = tuple(self.calibrated_added_operation_ids)
        abstained = tuple(self.abstained_operation_ids)
        if (len(additions) != len(set(additions))
                or set(additions) - set(member_ids)
                or len(abstained) != len(set(abstained))
                or set(abstained) - set(readout_ids)):
            raise ValueError("calibrated union diagnostics are inconsistent")
        semantic = self._semantic()
        if self.result_hash != structural_hash(semantic):
            raise ValueError("calibrated union result hash differs")

    @property
    def operation_ids(self):
        return tuple(value.operation_id for value in self.members)

    def _semantic(self):
        return {
            "abstained_operation_ids": list(self.abstained_operation_ids),
            "action_selection_changed": False,
            "baseline_selected_operation_id": (
                self.baseline_selected_operation_id),
            "calibrated_added_operation_ids": list(
                self.calibrated_added_operation_ids),
            "calibrated_per_action": self.calibrated_per_action,
            "capacity_solver_enabled": False,
            "flow_advection_enabled": False,
            "identity": CALIBRATED_CANDIDATE_UNION_IDENTITY,
            "maximum_interval_width": self.maximum_interval_width,
            "members": [value.to_dict() for value in self.members],
            "model_result_hash": self.model_result_hash,
            "policy_authority": False,
            "readout_authority": False,
            "readouts": [value.to_dict() for value in self.readouts],
            "revision_id": self.revision_id,
            "scalar_final_score_authority": True,
            "scalar_top_k": self.scalar_top_k,
            "snapshot_id": self.snapshot_id,
            "truth_mutated": False,
        }

    def to_dict(self):
        value = self._semantic()
        value["result_hash"] = self.result_hash
        return value


def build_calibrated_candidate_union(
        model, candidates, scores, feature_queries, snapshot_id, revision_id,
        scalar_top_k=3, calibrated_per_action=1,
        maximum_interval_width=0.55):
    """Enlarge scalar recall only; calibrated values never score or select."""
    if not isinstance(model, FdasCandidateCalibrationModel):
        raise TypeError("calibrated union requires typed model")
    for value, name in (
            (scalar_top_k, "scalar top-k"),
            (calibrated_per_action, "calibrated per action")):
        if (isinstance(value, bool) or not isinstance(value, int)
                or value < 1):
            raise ValueError("{} must be positive".format(name))
    if (isinstance(maximum_interval_width, bool)
            or not isinstance(maximum_interval_width, (int, float))
            or not math.isfinite(float(maximum_interval_width))
            or not 0.0 < float(maximum_interval_width) <= 1.0):
        raise ValueError("calibrated union interval width is invalid")
    candidates = tuple(candidates)
    scores = tuple(scores)
    if (not candidates or any(
            not isinstance(value, ShadowOperationCandidate)
            for value in candidates)):
        raise TypeError("calibrated union requires shadow candidates")
    if (not scores or any(not isinstance(value, OperationScore)
                          for value in scores)):
        raise TypeError("calibrated union requires operation scores")
    if not isinstance(feature_queries, dict):
        raise TypeError("calibrated union requires feature queries")
    score_by_id = dict((value.operation_id, value) for value in scores)
    candidate_by_id = dict(
        (value.operation.operation_id, value) for value in candidates)
    if (len(score_by_id) != len(scores)
            or len(candidate_by_id) != len(candidates)
            or set(candidate_by_id) != set(score_by_id)
            or set(candidate_by_id) != set(feature_queries)):
        raise ValueError("calibrated union inputs are incomplete or overlap")
    if any(not value.legal_bound for value in candidates):
        raise ValueError("calibrated union candidate is not legal-bound")
    ranked = tuple(sorted(
        (value for value in candidates
         if score_by_id[value.operation.operation_id].admissible),
        key=lambda value: (
            -score_by_id[value.operation.operation_id].priority,
            value.operation.operation_id)))
    if not ranked:
        raise ValueError("calibrated union has no admissible candidates")
    rank_by_id = dict(
        (value.operation.operation_id, index + 1)
        for index, value in enumerate(ranked))
    readouts = []
    for candidate in ranked:
        operation_id = candidate.operation.operation_id
        query = feature_queries[operation_id]
        if not isinstance(query, InductionFeatureQuery):
            raise TypeError("calibrated union query is not typed")
        operation_type = dict(query.context).get("operation_type")
        if operation_type != candidate.operation.operation_type:
            raise ValueError("calibrated union query action stratum differs")
        prediction = model.predict(query)
        width = (
            None if prediction.estimate is None else
            prediction.interval_upper - prediction.interval_lower)
        eligible = bool(
            prediction.status == "estimated"
            and width <= maximum_interval_width)
        eligibility_reason = (
            "supported-calibrated-transition"
            if eligible else prediction.reason
            if prediction.status == "abstained" else
            "prediction-interval-too-wide")
        readouts.append(FdasCalibratedCandidateReadout(
            operation_id, candidate.action_key, operation_type,
            rank_by_id[operation_id], score_by_id[operation_id].priority,
            prediction.status, prediction.reason,
            prediction.result_hash, prediction.estimate,
            prediction.interval_lower, prediction.interval_upper,
            prediction.effective_lineages, eligible, eligibility_reason))
    reasons = {}

    def protect(operation_id, reason):
        reasons.setdefault(operation_id, set()).add(reason)

    scalar_ids = tuple(value.operation.operation_id for value in ranked)
    for operation_id in scalar_ids[:scalar_top_k]:
        protect(operation_id, "scalar-top-k")
    protect(scalar_ids[0], "scalar-winner")
    for operation_type in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES:
        eligible = tuple(sorted(
            (value for value in readouts
             if value.operation_type == operation_type
             and value.eligible_for_calibrated_recall),
            key=lambda value: (
                -value.interval_lower, -value.estimate,
                value.baseline_rank, value.operation_id)))
        for value in eligible[:calibrated_per_action]:
            protect(value.operation_id, "calibrated-transition-recall")
    ordered = tuple(
        value for value in scalar_ids if value in reasons)
    scalar_protected = frozenset(scalar_ids[:scalar_top_k])
    additions = tuple(
        value for value in ordered
        if ("calibrated-transition-recall" in reasons[value]
            and value not in scalar_protected))
    members = tuple(FdasCalibratedCandidateMember(
        value, tuple(reasons[value])) for value in ordered)
    abstained = tuple(
        value.operation_id for value in readouts
        if value.prediction_status == "abstained")
    semantic = {
        "abstained_operation_ids": list(abstained),
        "action_selection_changed": False,
        "baseline_selected_operation_id": scalar_ids[0],
        "calibrated_added_operation_ids": list(additions),
        "calibrated_per_action": calibrated_per_action,
        "capacity_solver_enabled": False,
        "flow_advection_enabled": False,
        "identity": CALIBRATED_CANDIDATE_UNION_IDENTITY,
        "maximum_interval_width": float(maximum_interval_width),
        "members": [value.to_dict() for value in members],
        "model_result_hash": model.result_hash,
        "policy_authority": False,
        "readout_authority": False,
        "readouts": [value.to_dict() for value in readouts],
        "revision_id": str(revision_id),
        "scalar_final_score_authority": True,
        "scalar_top_k": scalar_top_k,
        "snapshot_id": str(snapshot_id),
        "truth_mutated": False,
    }
    return FdasCalibratedCandidateUnion(
        str(snapshot_id), str(revision_id), model.result_hash,
        scalar_ids[0], scalar_top_k, calibrated_per_action,
        float(maximum_interval_width), members, tuple(readouts), additions,
        abstained, structural_hash(semantic))
