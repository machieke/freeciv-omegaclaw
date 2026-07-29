"""Exact current-state revalidation before Impact plan materialization."""

import math
from dataclasses import dataclass
from enum import Enum

from ..events.schema import canonical_json_bytes, structural_hash
from ..pressure.packets import PacketCost, PacketReservation
from .impact import ImpactCandidate
from .impact_flow_adapter import ControlQuery


class ValidationDisposition(str, Enum):
    COMMIT = "commit"
    REJECT = "reject"
    REGENERATE = "regenerate"


@dataclass(frozen=True)
class ValidationResult:
    disposition: ValidationDisposition
    reason: object
    current_snapshot_id: str
    current_legal_actions_digest: str
    released_packets: tuple
    refreshed_candidate_key: object
    checks: tuple = ()
    validator_identity: str = "impact-commit-validator/1.0"

    def __post_init__(self):
        if not isinstance(
                self.disposition, ValidationDisposition):
            object.__setattr__(
                self, "disposition",
                ValidationDisposition(self.disposition))
        if self.disposition == ValidationDisposition.COMMIT:
            if self.reason is not None:
                raise ValueError(
                    "commit validation has no failure reason")
            if self.released_packets:
                raise ValueError(
                    "commit validation cannot release packets")
        elif (not isinstance(self.reason, str)
              or not self.reason):
            raise ValueError(
                "non-commit validation requires reason")
        if any(not isinstance(row, PacketCost)
               for row in self.released_packets):
            raise TypeError(
                "released packets must contain PacketCost")
        if (self.refreshed_candidate_key is not None
                and (not isinstance(
                    self.refreshed_candidate_key, str)
                     or not self.refreshed_candidate_key)):
            raise ValueError(
                "refreshed candidate key must be nonempty")
        if (len(set(self.checks)) != len(self.checks)
                or any(not isinstance(value, str) or not value
                       for value in self.checks)):
            raise ValueError(
                "validation checks must be unique")

    @property
    def plan_materialization_authorized(self):
        return self.disposition == (
            ValidationDisposition.COMMIT)

    @property
    def execution_authority(self):
        # ExecutionGate remains final authority after plan materialization.
        return False

    @property
    def result_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "checks": list(self.checks),
            "current_legal_actions_digest": (
                self.current_legal_actions_digest),
            "current_snapshot_id": self.current_snapshot_id,
            "disposition": self.disposition.value,
            "execution_authority": self.execution_authority,
            "plan_materialization_authorized": (
                self.plan_materialization_authorized),
            "reason": self.reason,
            "refreshed_candidate_key": (
                self.refreshed_candidate_key),
            "released_packets": [
                row.to_dict() for row in self.released_packets],
            "validator_identity": self.validator_identity,
        }


class ImpactCommitValidator:
    """Fail closed while preserving the existing final execution gate."""

    VALIDATOR_IDENTITY = "impact-commit-validator/1.0"

    def __init__(
            self, require_packet_reservation=True,
            cost_tolerance=1e-9):
        if not isinstance(
                require_packet_reservation, bool):
            raise TypeError(
                "packet reservation policy must be boolean")
        cost_tolerance = float(cost_tolerance)
        if (not math.isfinite(cost_tolerance)
                or cost_tolerance < 0.0):
            raise ValueError(
                "cost tolerance must be non-negative")
        self.require_packet_reservation = (
            require_packet_reservation)
        self.cost_tolerance = cost_tolerance

    @staticmethod
    def _legal_form(action):
        normalized = dict(action)
        normalized.pop("reason", None)
        normalized.pop("is_valid", None)
        return canonical_json_bytes(
            normalized).decode("utf-8")

    @staticmethod
    def _released(reservation):
        if not isinstance(
                reservation, PacketReservation):
            return ()
        return tuple(reservation.reserved)

    @staticmethod
    def _result(
            disposition, reason, snapshot,
            reservation, refreshed_key, checks):
        return ValidationResult(
            disposition=disposition,
            reason=reason,
            current_snapshot_id=str(
                snapshot.snapshot_id),
            current_legal_actions_digest=str(
                snapshot.legal_actions_digest),
            released_packets=(
                () if disposition
                == ValidationDisposition.COMMIT
                else ImpactCommitValidator._released(
                    reservation)),
            refreshed_candidate_key=refreshed_key,
            checks=tuple(checks))

    @staticmethod
    def _refresh_target(
            candidate_key, accepted_refresh):
        if isinstance(accepted_refresh, dict):
            return accepted_refresh.get(candidate_key)
        if accepted_refresh is True:
            return candidate_key
        if accepted_refresh in (False, None):
            return None
        raise TypeError(
            "accepted refresh must be boolean or mapping")

    def validate(
            self, source_query, candidate_key,
            current_snapshot, current_candidates,
            reservation=None,
            reservation_operation_id=None,
            accepted_refresh=False,
            current_context_digest=None,
            current_clone_generation=0,
            evidence_overlap_valid=True,
            quarantined=False,
            consumed_operation_ids=(),
            exact_guard=None,
            source_predicted_cost=None,
            current_predicted_cost=None):
        if not isinstance(source_query, ControlQuery):
            raise TypeError(
                "commit validation requires ControlQuery")
        current_candidates = tuple(
            current_candidates)
        if any(not isinstance(row, ImpactCandidate)
               for row in current_candidates):
            raise TypeError(
                "current candidates must be ImpactCandidate")
        current_by_key = dict(
            (row.action_key, row)
            for row in current_candidates)
        if len(current_by_key) != len(current_candidates):
            raise ValueError(
                "current candidate keys must be unique")
        source_by_key = dict(
            (row.action_key, row)
            for row in source_query.grounded_candidates)
        checks = []
        if candidate_key not in source_by_key:
            return self._result(
                ValidationDisposition.REJECT,
                "candidate-not-in-source-query",
                current_snapshot, reservation, None,
                ("source-candidate-resolution",))
        source_candidate = source_by_key[candidate_key]
        checks.append("source-candidate-resolution")

        refresh_target = self._refresh_target(
            candidate_key, accepted_refresh)
        refreshed = False
        current_key = candidate_key
        if current_key not in current_by_key:
            if (refresh_target is None
                    or refresh_target not in current_by_key):
                return self._result(
                    ValidationDisposition.REJECT,
                    "action-retired-or-not-authoritative",
                    current_snapshot, reservation, None,
                    checks + [
                        "authoritative-candidate-membership"])
            current_key = refresh_target
            refreshed = True
        current_candidate = current_by_key[current_key]
        checks.append(
            "authoritative-candidate-membership")

        identity_changed = (
            str(current_snapshot.snapshot_id)
            != source_query.snapshot_id
            or str(current_snapshot.legal_actions_digest)
            != source_query.legal_actions_digest)
        if identity_changed:
            if refresh_target is None:
                return self._result(
                    ValidationDisposition.REGENERATE,
                    "stale-snapshot-or-legal-actions",
                    current_snapshot, reservation, None,
                    checks + [
                        "snapshot-and-legal-action-refresh"])
            refreshed = True
        checks.append(
            "snapshot-and-legal-action-refresh")

        legal_rows = getattr(
            current_snapshot, "legal_action_json", None)
        if legal_rows is not None:
            legal = self._legal_form(
                current_candidate.action)
            if legal not in frozenset(legal_rows):
                return self._result(
                    ValidationDisposition.REJECT,
                    "action-not-in-server-legal-set",
                    current_snapshot, reservation, None,
                    checks + [
                        "server-legal-action-membership"])
        checks.append(
            "server-legal-action-membership")

        if (source_candidate.category
                != current_candidate.category):
            return self._result(
                ValidationDisposition.REGENERATE,
                "candidate-category-changed",
                current_snapshot, reservation,
                current_key if refreshed else None,
                checks + ["category-specific-guards"])
        if exact_guard is not None:
            if not callable(exact_guard):
                raise TypeError(
                    "exact guard must be callable")
            guarded = exact_guard(
                current_candidate, current_snapshot)
            if isinstance(guarded, tuple):
                valid, guard_reason = guarded
            else:
                valid, guard_reason = guarded, None
            if not isinstance(valid, bool) or not valid:
                return self._result(
                    ValidationDisposition.REJECT,
                    str(guard_reason or
                        "category-specific-guard-failed"),
                    current_snapshot, reservation, None,
                    checks + [
                        "category-specific-guards"])
        checks.append("category-specific-guards")

        if (isinstance(current_clone_generation, bool)
                or not isinstance(
                    current_clone_generation, int)
                or current_clone_generation < 0):
            raise ValueError(
                "current clone generation must be non-negative")
        if (current_clone_generation
                != source_query.lifecycle_clone_generation):
            return self._result(
                ValidationDisposition.REJECT,
                "lifecycle-clone-generation-changed",
                current_snapshot, reservation, None,
                checks + [
                    "context-and-clone-generation"])
        if current_context_digest is None:
            material = (
                current_snapshot.event_payload()
                if hasattr(
                    current_snapshot, "event_payload")
                else {
                    "legal_actions_digest":
                        current_snapshot
                        .legal_actions_digest,
                    "snapshot_id":
                        current_snapshot.snapshot_id,
                    "turn": current_snapshot.turn,
                })
            current_context_digest = structural_hash(
                material)
        if (current_context_digest
                != source_query.context_digest
                and refresh_target is None):
            return self._result(
                ValidationDisposition.REGENERATE,
                "control-context-changed",
                current_snapshot, reservation, None,
                checks + [
                    "context-and-clone-generation"])
        checks.append(
            "context-and-clone-generation")

        if not isinstance(
                evidence_overlap_valid, bool):
            raise TypeError(
                "evidence overlap status must be boolean")
        if not isinstance(quarantined, bool):
            raise TypeError(
                "quarantine status must be boolean")
        if quarantined or not evidence_overlap_valid:
            return self._result(
                ValidationDisposition.REJECT,
                ("candidate-quarantined"
                 if quarantined
                 else "evidence-overlap-invalid"),
                current_snapshot, reservation, None,
                checks + [
                    "evidence-overlap-and-quarantine"])
        checks.append(
            "evidence-overlap-and-quarantine")

        expected_operation = (
            str(reservation_operation_id)
            if reservation_operation_id is not None
            else candidate_key)
        if self.require_packet_reservation:
            if not isinstance(
                    reservation, PacketReservation):
                return self._result(
                    ValidationDisposition.REJECT,
                    "complete-packet-reservation-required",
                    current_snapshot, reservation, None,
                    checks + [
                        "packet-reservation-and-double-spend"])
            if (not reservation.complete
                    or reservation.operation_id
                    != expected_operation):
                return self._result(
                    ValidationDisposition.REJECT,
                    "packet-reservation-incomplete-or-mismatched",
                    current_snapshot, reservation, None,
                    checks + [
                        "packet-reservation-and-double-spend"])
            if expected_operation in frozenset(
                    str(value)
                    for value in consumed_operation_ids):
                return self._result(
                    ValidationDisposition.REJECT,
                    "packet-reservation-double-spend",
                    current_snapshot, reservation, None,
                    checks + [
                        "packet-reservation-and-double-spend"])
        checks.append(
            "packet-reservation-and-double-spend")

        if ((source_predicted_cost is None)
                != (current_predicted_cost is None)):
            raise ValueError(
                "predicted cost comparison requires both values")
        if source_predicted_cost is not None:
            source_cost = float(source_predicted_cost)
            current_cost = float(current_predicted_cost)
            if (not math.isfinite(source_cost)
                    or not math.isfinite(current_cost)
                    or source_cost < 0.0
                    or current_cost < 0.0):
                raise ValueError(
                    "predicted costs must be finite and non-negative")
            if abs(
                    source_cost - current_cost
            ) > self.cost_tolerance:
                return self._result(
                    ValidationDisposition.REGENERATE,
                    "predicted-cost-materially-changed",
                    current_snapshot, reservation,
                    current_key if refreshed else None,
                    checks + ["predicted-cost-refresh"])
        checks.append("predicted-cost-refresh")

        return self._result(
            ValidationDisposition.COMMIT,
            None, current_snapshot, reservation,
            current_key if refreshed else None,
            checks)
