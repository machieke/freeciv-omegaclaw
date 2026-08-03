"""Exact bounded-safety filter for protected candidate readout surfaces."""

from dataclasses import dataclass

from ..events.schema import structural_hash
from .fdas import ShadowOperationCandidate
from .fdas_authority import (
    validate_bounded_defense_fortification_candidate,
    validate_bounded_defense_reinforcement_candidate,
)


DECISION_SAFE_CANDIDATE_FILTER_IDENTITY = (
    "fdas-decision-safe-candidate-filter/1.0")


@dataclass(frozen=True)
class FdasDecisionSafeCandidateFilterReadout:
    operation_id: str
    action_key: str
    action_type: str
    blockers: tuple
    status: str
    reason: object
    source_atom_id: object
    result_hash: str

    def __post_init__(self):
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.action_key, "action key"),
                (self.action_type, "action type"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "candidate filter {} is required".format(name))
        if self.status not in ("eligible", "excluded"):
            raise ValueError("candidate filter status is invalid")
        blockers = tuple(sorted(set(str(value) for value in self.blockers)))
        if any(not value for value in blockers):
            raise ValueError("candidate filter blockers are invalid")
        object.__setattr__(self, "blockers", blockers)
        if self.status == "eligible":
            if (self.reason is not None
                    or not isinstance(self.source_atom_id, str)
                    or not self.source_atom_id):
                raise ValueError("eligible candidate filter row differs")
        elif (not isinstance(self.reason, str) or not self.reason
              or self.source_atom_id is not None):
            raise ValueError("excluded candidate filter row differs")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("candidate filter row hash differs")

    def _semantic(self):
        return {
            "action_key": self.action_key,
            "action_type": self.action_type,
            "blockers": list(self.blockers),
            "operation_id": self.operation_id,
            "reason": self.reason,
            "source_atom_id": self.source_atom_id,
            "status": self.status,
        }

    def to_dict(self):
        return {**self._semantic(), "result_hash": self.result_hash}


@dataclass(frozen=True)
class FdasDecisionSafeCandidateFilter:
    snapshot_id: str
    revision_id: str
    readouts: tuple
    eligible_operation_ids: tuple
    excluded_operation_ids: tuple
    result_hash: str

    def __post_init__(self):
        for value, name in (
                (self.snapshot_id, "snapshot ID"),
                (self.revision_id, "revision ID"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "candidate filter {} is required".format(name))
        readouts = tuple(self.readouts)
        if (not readouts
                or any(not isinstance(
                    value, FdasDecisionSafeCandidateFilterReadout)
                    for value in readouts)):
            raise TypeError("candidate filter requires typed readouts")
        object.__setattr__(self, "readouts", readouts)
        operation_ids = tuple(value.operation_id for value in readouts)
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("candidate filter operation IDs overlap")
        eligible = tuple(self.eligible_operation_ids)
        excluded = tuple(self.excluded_operation_ids)
        if (eligible != tuple(
                    value.operation_id for value in readouts
                    if value.status == "eligible")
                or excluded != tuple(
                    value.operation_id for value in readouts
                    if value.status == "excluded")
                or set(eligible).intersection(excluded)
                or set(eligible).union(excluded) != set(operation_ids)):
            raise ValueError("candidate filter partitions differ")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("candidate filter result hash differs")

    def _semantic(self):
        return {
            "action_selection_changed": False,
            "candidate_surface_preserved": True,
            "calibrated_union_input_filtered": True,
            "eligible_operation_ids": list(self.eligible_operation_ids),
            "excluded_operation_ids": list(self.excluded_operation_ids),
            "identity": DECISION_SAFE_CANDIDATE_FILTER_IDENTITY,
            "input_candidate_count": len(self.readouts),
            "policy_authority": False,
            "readout_authority": False,
            "readouts": [value.to_dict() for value in self.readouts],
            "revision_id": self.revision_id,
            "snapshot_id": self.snapshot_id,
            "truth_mutated": False,
        }

    def to_dict(self):
        return {**self._semantic(), "result_hash": self.result_hash}


def build_decision_safe_candidate_filter(
        candidates, snapshot, revision, goals):
    """Filter only the readout union; retain all observational candidates."""
    candidates = tuple(candidates)
    if (not candidates
            or any(not isinstance(value, ShadowOperationCandidate)
                   for value in candidates)):
        raise TypeError("candidate filter requires shadow candidates")
    operation_ids = tuple(
        value.operation.operation_id for value in candidates)
    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("candidate filter inputs overlap")
    readouts = []
    for candidate in candidates:
        action_type = candidate.action.get("action_type")
        blockers = tuple(sorted(set(str(value)
                                    for value in candidate.blockers)))
        if action_type == "unit_move":
            _route, source, reason = (
                validate_bounded_defense_reinforcement_candidate(
                    candidate, snapshot, revision, goals))
        elif action_type == "unit_fortify":
            _route, source, reason = (
                validate_bounded_defense_fortification_candidate(
                    candidate, snapshot, revision, goals))
        else:
            source = None
            reason = "outside-decision-safe-defense-action-domain"
        semantic = {
            "action_key": candidate.action_key,
            "action_type": str(action_type),
            "blockers": list(blockers),
            "operation_id": candidate.operation.operation_id,
            "reason": reason,
            "source_atom_id": (
                None if source is None else source.atom_id),
            "status": "eligible" if reason is None else "excluded",
        }
        readouts.append(FdasDecisionSafeCandidateFilterReadout(
            candidate.operation.operation_id,
            candidate.action_key,
            str(action_type),
            blockers,
            semantic["status"],
            reason,
            semantic["source_atom_id"],
            structural_hash(semantic)))
    eligible = tuple(
        value.operation_id for value in readouts
        if value.status == "eligible")
    excluded = tuple(
        value.operation_id for value in readouts
        if value.status == "excluded")
    semantic = {
        "action_selection_changed": False,
        "candidate_surface_preserved": True,
        "calibrated_union_input_filtered": True,
        "eligible_operation_ids": list(eligible),
        "excluded_operation_ids": list(excluded),
        "identity": DECISION_SAFE_CANDIDATE_FILTER_IDENTITY,
        "input_candidate_count": len(readouts),
        "policy_authority": False,
        "readout_authority": False,
        "readouts": [value.to_dict() for value in readouts],
        "revision_id": revision.revision_id,
        "snapshot_id": snapshot.snapshot_id,
        "truth_mutated": False,
    }
    return FdasDecisionSafeCandidateFilter(
        snapshot.snapshot_id, revision.revision_id, tuple(readouts),
        eligible, excluded, structural_hash(semantic))
