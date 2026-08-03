"""Protect the scalar winner's exact decision target before calibrated recall."""

from dataclasses import dataclass

from ..events.schema import structural_hash
from ..pressure.scheduler import OperationScore
from .fdas import ShadowOperationCandidate


TARGET_SCOPED_CANDIDATE_FILTER_IDENTITY = (
    "fdas-target-scoped-candidate-filter/1.0")


@dataclass(frozen=True)
class FdasTargetScopedCandidateFilterReadout:
    operation_id: str
    action_key: str
    operation_type: str
    target_ref: str
    status: str
    scope_failures: tuple
    result_hash: str

    def __post_init__(self):
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.action_key, "action key"),
                (self.operation_type, "operation type"),
                (self.target_ref, "target reference"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("target scope {} is required".format(name))
        if self.status not in ("in-scope", "out-of-scope"):
            raise ValueError("target scope status is invalid")
        failures = tuple(sorted(set(str(value)
                                    for value in self.scope_failures)))
        if any(not value for value in failures):
            raise ValueError("target scope failures are invalid")
        if ((self.status == "in-scope") != (not failures)):
            raise ValueError("target scope status and failures differ")
        object.__setattr__(self, "scope_failures", failures)
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("target scope row hash differs")

    def _semantic(self):
        return {
            "action_key": self.action_key,
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "scope_failures": list(self.scope_failures),
            "status": self.status,
            "target_ref": self.target_ref,
        }

    def to_dict(self):
        return {**self._semantic(), "result_hash": self.result_hash}


@dataclass(frozen=True)
class FdasTargetScopedCandidateFilter:
    snapshot_id: str
    revision_id: str
    baseline_operation_id: str
    baseline_operation_type: str
    baseline_target_ref: str
    readouts: tuple
    in_scope_operation_ids: tuple
    out_of_scope_operation_ids: tuple
    result_hash: str

    def __post_init__(self):
        for value, name in (
                (self.snapshot_id, "snapshot ID"),
                (self.revision_id, "revision ID"),
                (self.baseline_operation_id, "baseline operation ID"),
                (self.baseline_operation_type, "baseline operation type"),
                (self.baseline_target_ref, "baseline target reference"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("target scope {} is required".format(name))
        readouts = tuple(self.readouts)
        if (not readouts or any(not isinstance(
                value, FdasTargetScopedCandidateFilterReadout)
                for value in readouts)):
            raise TypeError("target scope requires typed readouts")
        object.__setattr__(self, "readouts", readouts)
        operation_ids = tuple(value.operation_id for value in readouts)
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("target scope operation IDs overlap")
        in_scope = tuple(self.in_scope_operation_ids)
        out_scope = tuple(self.out_of_scope_operation_ids)
        if (in_scope != tuple(value.operation_id for value in readouts
                              if value.status == "in-scope")
                or out_scope != tuple(value.operation_id for value in readouts
                                      if value.status == "out-of-scope")
                or set(in_scope).intersection(out_scope)
                or set(in_scope).union(out_scope) != set(operation_ids)
                or self.baseline_operation_id not in in_scope):
            raise ValueError("target scope partitions differ")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("target scope result hash differs")

    def _semantic(self):
        return {
            "action_selection_changed": False,
            "baseline_operation_id": self.baseline_operation_id,
            "baseline_operation_type": self.baseline_operation_type,
            "baseline_target_ref": self.baseline_target_ref,
            "candidate_surface_preserved": True,
            "calibrated_union_input_filtered": True,
            "identity": TARGET_SCOPED_CANDIDATE_FILTER_IDENTITY,
            "in_scope_operation_ids": list(self.in_scope_operation_ids),
            "input_candidate_count": len(self.readouts),
            "out_of_scope_operation_ids": list(
                self.out_of_scope_operation_ids),
            "policy_authority": False,
            "readout_authority": False,
            "readouts": [value.to_dict() for value in self.readouts],
            "revision_id": self.revision_id,
            "snapshot_id": self.snapshot_id,
            "truth_mutated": False,
        }

    def to_dict(self):
        return {**self._semantic(), "result_hash": self.result_hash}


def build_target_scoped_candidate_filter(
        candidates, scores, snapshot_id, revision_id):
    """Retain only the global safe scalar winner's operation target scope."""
    candidates = tuple(candidates)
    scores = tuple(scores)
    if (not candidates or any(not isinstance(value, ShadowOperationCandidate)
                              for value in candidates)):
        raise TypeError("target scope requires shadow candidates")
    if (not scores or any(not isinstance(value, OperationScore)
                          for value in scores)):
        raise TypeError("target scope requires operation scores")
    candidate_by_id = {
        value.operation.operation_id: value for value in candidates}
    score_by_id = {value.operation_id: value for value in scores}
    if (len(candidate_by_id) != len(candidates)
            or len(score_by_id) != len(scores)
            or set(candidate_by_id) != set(score_by_id)):
        raise ValueError("target scope inputs are incomplete or overlap")
    ranked = tuple(sorted(
        (value for value in candidates
         if score_by_id[value.operation.operation_id].admissible),
        key=lambda value: (
            -score_by_id[value.operation.operation_id].priority,
            value.operation.operation_id)))
    if not ranked:
        raise ValueError("target scope has no admissible scalar baseline")
    baseline = ranked[0]
    baseline_type = baseline.operation.operation_type
    baseline_target = baseline.operation.target_ref
    readouts = []
    for candidate in candidates:
        failures = []
        if candidate.operation.operation_type != baseline_type:
            failures.append("operation-type-mismatch")
        if candidate.operation.target_ref != baseline_target:
            failures.append("target-ref-mismatch")
        semantic = {
            "action_key": candidate.action_key,
            "operation_id": candidate.operation.operation_id,
            "operation_type": candidate.operation.operation_type,
            "scope_failures": sorted(failures),
            "status": "in-scope" if not failures else "out-of-scope",
            "target_ref": candidate.operation.target_ref,
        }
        readouts.append(FdasTargetScopedCandidateFilterReadout(
            candidate.operation.operation_id, candidate.action_key,
            candidate.operation.operation_type, candidate.operation.target_ref,
            semantic["status"], tuple(semantic["scope_failures"]),
            structural_hash(semantic)))
    in_scope = tuple(value.operation_id for value in readouts
                     if value.status == "in-scope")
    out_scope = tuple(value.operation_id for value in readouts
                      if value.status == "out-of-scope")
    semantic = {
        "action_selection_changed": False,
        "baseline_operation_id": baseline.operation.operation_id,
        "baseline_operation_type": baseline_type,
        "baseline_target_ref": baseline_target,
        "candidate_surface_preserved": True,
        "calibrated_union_input_filtered": True,
        "identity": TARGET_SCOPED_CANDIDATE_FILTER_IDENTITY,
        "in_scope_operation_ids": list(in_scope),
        "input_candidate_count": len(readouts),
        "out_of_scope_operation_ids": list(out_scope),
        "policy_authority": False,
        "readout_authority": False,
        "readouts": [value.to_dict() for value in readouts],
        "revision_id": str(revision_id),
        "snapshot_id": str(snapshot_id),
        "truth_mutated": False,
    }
    return FdasTargetScopedCandidateFilter(
        str(snapshot_id), str(revision_id), baseline.operation.operation_id,
        baseline_type, baseline_target, tuple(readouts), in_scope, out_scope,
        structural_hash(semantic))
