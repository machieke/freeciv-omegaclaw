"""Continuous flow readout integrated with atomic packet execution gates."""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash
from ..pressure.coalitions import RequirementSet
from ..pressure.model import CostVector, Operation
from ..pressure.packets import (
    PacketBudget,
    PacketCost,
    PacketReservation,
    PacketSchedule,
    PacketScheduler,
)
from ..pressure.risk import RiskEstimate, estimate_uncertain_loss
from ..pressure.scheduler import OperationScore
from .advection import PacketReservationLedger, ReservationMass
from .model import CandidateGrounding, FlowNodeKind, FlowView


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


def _finite_nonnegative(value, name):
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(
            "{} must be finite and non-negative".format(name))
    return value


@dataclass(frozen=True)
class FlowCandidate:
    candidate_id: str
    flow_view_id: str
    semantic_epoch: int
    topology_generation: int
    node_semantic_id: str
    operation_id: str
    per_goal_expected_relief: tuple
    overlap_score: float
    bridge_diagnostics: tuple
    congestion_delta: float
    risk: RiskEstimate
    cost_vector: CostVector
    packet_costs: tuple
    packet_threshold: int
    selection_propensity: object
    reason_codes: tuple

    def __post_init__(self):
        for value, name in (
                (self.candidate_id, "flow candidate ID"),
                (self.flow_view_id, "flow view ID"),
                (self.node_semantic_id, "candidate node ID"),
                (self.operation_id, "candidate operation ID")):
            _required_text(value, name)
        for value, name in (
                (self.semantic_epoch, "candidate semantic epoch"),
                (self.topology_generation,
                 "candidate topology generation")):
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0):
                raise ValueError(
                    "{} must be non-negative".format(name))
        goals = [row[0] for row in self.per_goal_expected_relief]
        if (len(goals) != len(set(goals))
                or any(not isinstance(goal_id, str) or not goal_id
                       for goal_id in goals)):
            raise ValueError(
                "candidate relief goals must be unique")
        for _, value in self.per_goal_expected_relief:
            _finite_nonnegative(
                value, "candidate expected relief")
        _finite_nonnegative(
            self.overlap_score, "candidate overlap")
        diagnostics = [row[0] for row in self.bridge_diagnostics]
        if (len(diagnostics) != len(set(diagnostics))
                or any(not isinstance(name, str) or not name
                       for name in diagnostics)
                or any(not math.isfinite(float(value))
                       for _, value in self.bridge_diagnostics)):
            raise ValueError(
                "bridge diagnostics require unique finite values")
        if not math.isfinite(float(self.congestion_delta)):
            raise ValueError(
                "congestion delta must be finite")
        if not isinstance(self.risk, RiskEstimate):
            raise TypeError(
                "flow candidate risk must be RiskEstimate")
        if not isinstance(self.cost_vector, CostVector):
            raise TypeError(
                "flow candidate cost must be CostVector")
        if (not self.packet_costs
                or any(not isinstance(row, PacketCost)
                       for row in self.packet_costs)):
            raise TypeError(
                "flow candidate costs must contain PacketCost")
        resources = [row.resource for row in self.packet_costs]
        if len(resources) != len(set(resources)):
            raise ValueError(
                "flow candidate packet resources must be unique")
        if (isinstance(self.packet_threshold, bool)
                or not isinstance(self.packet_threshold, int)
                or self.packet_threshold < 1):
            raise ValueError(
                "packet threshold must be positive")
        if self.selection_propensity is not None:
            propensity = float(self.selection_propensity)
            if (not math.isfinite(propensity)
                    or not 0.0 <= propensity <= 1.0):
                raise ValueError(
                    "selection propensity must be in [0, 1]")
        if (not self.reason_codes
                or len(set(self.reason_codes))
                != len(self.reason_codes)
                or any(not isinstance(value, str) or not value
                       for value in self.reason_codes)):
            raise ValueError(
                "candidate reason codes must be unique")

    @property
    def continuous_eligibility(self):
        return min(1.0, float(self.overlap_score))

    def to_dict(self):
        return {
            "bridge_diagnostics": dict(
                (name, float(value))
                for name, value in self.bridge_diagnostics),
            "candidate_id": self.candidate_id,
            "congestion_delta": float(
                self.congestion_delta),
            "continuous_eligibility": float(
                self.continuous_eligibility),
            "cost_vector": self.cost_vector.to_dict(),
            "flow_view_id": self.flow_view_id,
            "node_semantic_id": self.node_semantic_id,
            "operation_id": self.operation_id,
            "overlap_score": float(self.overlap_score),
            "packet_costs": [
                row.to_dict() for row in self.packet_costs],
            "packet_threshold": self.packet_threshold,
            "per_goal_expected_relief": dict(
                (goal_id, float(value))
                for goal_id, value
                in self.per_goal_expected_relief),
            "reason_codes": list(self.reason_codes),
            "risk": self.risk.to_dict(),
            "selection_propensity": (
                None if self.selection_propensity is None
                else float(self.selection_propensity)),
            "semantic_epoch": self.semantic_epoch,
            "topology_generation": (
                self.topology_generation),
        }


class FlowCandidateFactory:
    """Create a typed operation candidate from overlap diagnostics."""

    FACTORY_IDENTITY = "pf-flow-candidate/1.0"

    @staticmethod
    def _risk(operation):
        if operation.risk_estimates:
            return max(
                (row[1] for row in operation.risk_estimates),
                key=lambda row: (
                    row.cvar, row.expected_loss,
                    -row.confidence))
        variance = max(
            (float(row.relief_variance)
             for row in operation.typed_advantages),
            default=0.0)
        return estimate_uncertain_loss(
            expected_loss=0.0,
            outcome_variance=variance,
            confidence=0.5,
            provenance=(
                "typed-advantage-risk-fallback",))

    def build(
            self, view, operation_node_id, operation,
            overlap_score, bridge_diagnostics=(),
            congestion_delta=0.0,
            selection_propensity=None, risk=None,
            reason_codes=()):
        if not isinstance(view, FlowView):
            raise TypeError(
                "flow candidate requires FlowView")
        if not isinstance(operation, Operation):
            raise TypeError(
                "flow candidate requires Operation")
        node = view.node(operation_node_id)
        if (node.kind != FlowNodeKind.OPERATION
                or not node.committable):
            raise ValueError(
                "flow candidate must use committable operation node")
        grounding = next((
            row for row in view.candidate_groundings
            if row.operation_node_id == operation_node_id
        ), None)
        if grounding is None or not grounding.committable:
            raise ValueError(
                "flow candidate requires authoritative grounding")
        if not operation.typed_advantages:
            raise ValueError(
                "flow candidate requires typed PF advantage")
        risk = risk if risk is not None else self._risk(operation)
        reasons = tuple(reason_codes) + (
            "overlap-location-readout-only",
            "typed-pf-operation-authority",
            "exact-revalidation-required",
        )
        reasons = tuple(dict.fromkeys(reasons))
        view_id = view.to_dict()["view_hash"]
        material = {
            "flow_view_id": view_id,
            "node_semantic_id": operation_node_id,
            "operation_id": operation.operation_id,
            "overlap_score": float(overlap_score),
            "semantic_epoch": view.semantic_epoch,
            "topology_generation": view.topology_generation,
        }
        return FlowCandidate(
            candidate_id="flow-candidate:{}".format(
                structural_hash(material)),
            flow_view_id=view_id,
            semantic_epoch=view.semantic_epoch,
            topology_generation=view.topology_generation,
            node_semantic_id=operation_node_id,
            operation_id=operation.operation_id,
            per_goal_expected_relief=tuple(sorted(
                (row.goal_id, float(row.expected_relief))
                for row in operation.typed_advantages)),
            overlap_score=float(overlap_score),
            bridge_diagnostics=tuple(sorted(
                (str(name), float(value))
                for name, value in bridge_diagnostics)),
            congestion_delta=float(congestion_delta),
            risk=risk,
            cost_vector=operation.cost,
            packet_costs=operation.packet_costs,
            packet_threshold=operation.packet_threshold,
            selection_propensity=selection_propensity,
            reason_codes=reasons)


@dataclass(frozen=True)
class PacketStarvation:
    operation_id: str
    requirement_set_id: object
    reason: str
    missing_resources: tuple
    reservation_age: int

    def __post_init__(self):
        _required_text(
            self.operation_id, "starved operation ID")
        _required_text(
            self.reason, "packet-starvation reason")
        if (self.requirement_set_id is not None
                and (not isinstance(
                    self.requirement_set_id, str)
                     or not self.requirement_set_id)):
            raise ValueError(
                "starvation requirement-set ID must be nonempty")
        if (len(set(self.missing_resources))
                != len(self.missing_resources)
                or any(not isinstance(value, str) or not value
                       for value in self.missing_resources)):
            raise ValueError(
                "missing resource IDs must be unique")
        if (isinstance(self.reservation_age, bool)
                or not isinstance(self.reservation_age, int)
                or self.reservation_age < 0):
            raise ValueError(
                "reservation age must be non-negative")

    def to_dict(self):
        return {
            "missing_resources": list(
                self.missing_resources),
            "operation_id": self.operation_id,
            "reason": self.reason,
            "requirement_set_id": (
                self.requirement_set_id),
            "reservation_age": self.reservation_age,
        }


@dataclass(frozen=True)
class FlowIntegralityDiagnostics:
    relaxed_continuous_value: float
    packet_feasible_value: float
    integrality_gap: float
    stranded_mass: float
    incomplete_reservations: tuple
    packet_starvation: tuple
    reservation_ages: tuple
    returned_mass: float
    return_rate: float
    exact_revalidation_failures: tuple

    def __post_init__(self):
        for value, name in (
                (self.relaxed_continuous_value,
                 "relaxed continuous value"),
                (self.packet_feasible_value,
                 "packet feasible value"),
                (self.integrality_gap, "integrality gap"),
                (self.stranded_mass, "stranded mass"),
                (self.returned_mass, "returned mass"),
                (self.return_rate, "return rate")):
            _finite_nonnegative(value, name)
        if self.return_rate > 1.0:
            raise ValueError(
                "reservation return rate must be at most one")
        if any(not isinstance(row, PacketStarvation)
               for row in self.packet_starvation):
            raise TypeError(
                "packet starvation has wrong type")
        expected_gap = max(
            0.0,
            float(self.relaxed_continuous_value)
            - float(self.packet_feasible_value))
        if abs(float(self.integrality_gap) - expected_gap) > 1e-9:
            raise ValueError(
                "integrality gap is inconsistent")

    def to_dict(self):
        return {
            "exact_revalidation_failures": list(
                self.exact_revalidation_failures),
            "incomplete_reservations": list(
                self.incomplete_reservations),
            "integrality_gap": float(self.integrality_gap),
            "packet_feasible_value": float(
                self.packet_feasible_value),
            "packet_starvation": [
                row.to_dict() for row in self.packet_starvation],
            "relaxed_continuous_value": float(
                self.relaxed_continuous_value),
            "reservation_ages": dict(
                self.reservation_ages),
            "return_rate": float(self.return_rate),
            "returned_mass": float(self.returned_mass),
            "stranded_mass": float(self.stranded_mass),
        }


@dataclass(frozen=True)
class FlowPacketDecision:
    candidates: tuple
    eligible_operation_ids: tuple
    packet_schedule: PacketSchedule
    reservation_ledger: PacketReservationLedger
    diagnostics: FlowIntegralityDiagnostics
    integrator_identity: str

    def __post_init__(self):
        if any(not isinstance(row, FlowCandidate)
               for row in self.candidates):
            raise TypeError(
                "decision candidates have wrong type")
        if not isinstance(
                self.packet_schedule, PacketSchedule):
            raise TypeError(
                "decision schedule has wrong type")
        if not isinstance(
                self.reservation_ledger,
                PacketReservationLedger):
            raise TypeError(
                "decision reservation ledger has wrong type")
        if not isinstance(
                self.diagnostics,
                FlowIntegralityDiagnostics):
            raise TypeError(
                "decision diagnostics have wrong type")
        _required_text(
            self.integrator_identity,
            "flow packet integrator identity")

    @property
    def decision_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "candidates": [
                row.to_dict() for row in self.candidates],
            "diagnostics": self.diagnostics.to_dict(),
            "eligible_operation_ids": list(
                self.eligible_operation_ids),
            "integrator_identity": self.integrator_identity,
            "packet_schedule": (
                self.packet_schedule.to_dict()),
            "reservation_ledger": (
                self.reservation_ledger.to_dict()),
        }


class FlowPacketIntegrator:
    """Use flow for eligibility and typed PF plus packets for authority."""

    INTEGRATOR_IDENTITY = "pf-flow-packet-integrator/1.0"

    def __init__(self, eligibility_floor=1e-9):
        self.eligibility_floor = _finite_nonnegative(
            eligibility_floor, "flow eligibility floor")
        self.scheduler = PacketScheduler()

    @staticmethod
    def _returned(operation, reason):
        costs = tuple(sorted(
            (PacketCost(
                row.resource,
                row.quanta * operation.packet_threshold)
             for row in operation.packet_costs),
            key=lambda row: row.resource.value))
        return PacketReservation(
            operation_id=operation.operation_id,
            costs=costs,
            reserved=costs,
            state="returned",
            requirement_set_id=(
                operation.requirement_set_id),
            reason=reason)

    @staticmethod
    def _rebuild_schedule(
            provisional, returned,
            score_by_operation, relaxed_value):
        reservations = (
            tuple(returned)
            + provisional.reservations)
        committed_ids = tuple(
            row.operation_id for row in reservations
            if row.state == "committed")
        committed_value = sum(
            max(0.0, float(
                score_by_operation[row].priority))
            for row in committed_ids)
        declared = dict(
            (row.resource, row.available)
            for row in provisional.budgets)
        consumed = dict(
            (resource, 0) for resource in declared)
        for reservation in reservations:
            if reservation.state != "committed":
                continue
            for cost in reservation.reserved:
                consumed[cost.resource] = (
                    consumed.get(cost.resource, 0)
                    + cost.quanta)
        stranded = tuple(
            PacketCost(
                resource,
                available - consumed.get(resource, 0))
            for resource, available in sorted(
                declared.items(),
                key=lambda row: row[0].value)
            if available - consumed.get(resource, 0) > 0)
        return PacketSchedule(
            budgets=provisional.budgets,
            reservations=reservations,
            committed_operation_ids=committed_ids,
            stranded_quanta=stranded,
            integrality_gap=max(
                0.0, relaxed_value - committed_value),
            relaxed_value=relaxed_value,
            committed_value=committed_value,
            scheduler_identity=(
                "{}+{}".format(
                    provisional.scheduler_identity,
                    FlowPacketIntegrator.INTEGRATOR_IDENTITY)))

    @staticmethod
    def _starvation(
            schedule, budgets, ages):
        available = dict(
            (row.resource, row.available)
            for row in budgets)
        for reservation in schedule.reservations:
            if reservation.state != "committed":
                continue
            for cost in reservation.reserved:
                available[cost.resource] = (
                    available.get(cost.resource, 0)
                    - cost.quanta)
        rows = []
        for reservation in schedule.reservations:
            if reservation.state == "committed":
                continue
            missing = (
                tuple(sorted(
                    row.resource.value
                    for row in reservation.costs
                    if row.quanta > available.get(
                        row.resource, 0)))
                if reservation.reason
                == "insufficient-whole-packets"
                else ())
            rows.append(PacketStarvation(
                operation_id=reservation.operation_id,
                requirement_set_id=(
                    reservation.requirement_set_id),
                reason=reservation.reason or reservation.state,
                missing_resources=missing,
                reservation_age=int(
                    ages.get(reservation.operation_id, 0))))
        return tuple(rows)

    def integrate(
            self, view, candidates, scores, budgets,
            revalidate, requirement_sets=(),
            premise_packets=None, reservation_ages=None):
        if not isinstance(view, FlowView):
            raise TypeError(
                "flow packet integration requires FlowView")
        candidates = tuple(candidates)
        scores = tuple(scores)
        budgets = tuple(budgets)
        requirement_sets = tuple(requirement_sets)
        if any(not isinstance(row, FlowCandidate)
               for row in candidates):
            raise TypeError(
                "flow packet candidates have wrong type")
        if any(not isinstance(row, OperationScore)
               for row in scores):
            raise TypeError(
                "flow packet scores have wrong type")
        if any(not isinstance(row, PacketBudget)
               for row in budgets):
            raise TypeError(
                "flow packet budgets have wrong type")
        if any(not isinstance(row, RequirementSet)
               for row in requirement_sets):
            raise TypeError(
                "flow packet requirement sets have wrong type")
        if not callable(revalidate):
            raise TypeError(
                "exact candidate revalidation is required")
        view_id = view.to_dict()["view_hash"]
        if any(
                row.flow_view_id != view_id
                or row.semantic_epoch != view.semantic_epoch
                or row.topology_generation
                != view.topology_generation
                for row in candidates):
            raise ValueError(
                "stale flow candidate view identity")
        operation_ids = [row.operation_id for row in candidates]
        node_ids = [row.node_semantic_id for row in candidates]
        if (len(operation_ids) != len(set(operation_ids))
                or len(node_ids) != len(set(node_ids))):
            raise ValueError(
                "flow candidates must be unique")
        candidate_by_operation = dict(
            (row.operation_id, row) for row in candidates)
        score_by_operation = dict(
            (row.operation_id, row) for row in scores)
        if len(score_by_operation) != len(scores):
            raise ValueError(
                "operation scores must be unique")
        if set(candidate_by_operation) - set(score_by_operation):
            raise ValueError(
                "candidate is missing typed PF score")
        grounding_by_node = dict(
            (row.operation_node_id, row)
            for row in view.candidate_groundings)
        for candidate in candidates:
            score = score_by_operation[candidate.operation_id]
            operation = score.operation
            if (candidate.cost_vector != operation.cost
                    or candidate.packet_costs
                    != operation.packet_costs
                    or candidate.packet_threshold
                    != operation.packet_threshold):
                raise ValueError(
                    "candidate and operation contracts disagree")
            grounding = grounding_by_node.get(
                candidate.node_semantic_id)
            if (not isinstance(grounding, CandidateGrounding)
                    or not grounding.committable):
                raise ValueError(
                    "candidate lost authoritative grounding")

        eligible = tuple(
            row for row in candidates
            if row.overlap_score > self.eligibility_floor
            and score_by_operation[row.operation_id].admissible
            and score_by_operation[row.operation_id].priority > 0.0)
        eligible_ids = tuple(
            row.operation_id for row in eligible)
        # Overlap only admits a location. It is deliberately not multiplied
        # into typed PF value, so the continuous relaxation remains an upper
        # bound on any whole-packet subset.
        relaxed_value = sum(
            max(0.0, float(
                score_by_operation[row.operation_id].priority))
            for row in eligible)
        active_ids = set(eligible_ids)
        invalid = []
        invalid_ids = set()
        final = None
        for _ in range(len(active_ids) + 1):
            active_scores = tuple(
                score_by_operation[row.operation_id]
                for row in eligible
                if row.operation_id in active_ids)
            active_operations = tuple(
                row.operation for row in active_scores)
            provisional = self.scheduler.schedule(
                active_operations, active_scores, budgets,
                requirement_sets=requirement_sets,
                premise_packets=premise_packets)
            newly_invalid = []
            for operation_id in (
                    provisional.committed_operation_ids):
                candidate = candidate_by_operation[operation_id]
                operation = score_by_operation[
                    operation_id].operation
                grounding = grounding_by_node[
                    candidate.node_semantic_id]
                try:
                    valid = revalidate(
                        operation, grounding)
                except Exception:
                    valid = False
                if not isinstance(valid, bool):
                    valid = False
                if not valid and operation_id not in invalid_ids:
                    newly_invalid.append(operation_id)
            if not newly_invalid:
                final = provisional
                break
            for operation_id in newly_invalid:
                invalid_ids.add(operation_id)
                active_ids.remove(operation_id)
                invalid.append(self._returned(
                    score_by_operation[
                        operation_id].operation,
                    "exact-revalidation-failed"))
        if final is None:
            raise RuntimeError(
                "packet revalidation retry bound exhausted")
        schedule = self._rebuild_schedule(
            final, invalid, score_by_operation,
            relaxed_value)
        committed = frozenset(
            schedule.committed_operation_ids)
        ages = dict(reservation_ages or {})
        if any(
                not isinstance(key, str) or not key
                or isinstance(value, bool)
                or not isinstance(value, int) or value < 0
                for key, value in ages.items()):
            raise ValueError(
                "reservation ages require non-negative turns")
        noncommitted = tuple(
            row for row in candidates
            if row.operation_id not in committed)
        pending_ids = frozenset(
            row.operation_id
            for row in schedule.reservations
            if row.state == "pending")
        ledger = PacketReservationLedger(tuple(
            ReservationMass(
                reservation_id="flow-reservation:{}".format(
                    row.candidate_id),
                mass=float(row.overlap_score),
                operation_id=row.operation_id,
                requirement_set_id=(
                    score_by_operation[
                        row.operation_id].operation
                    .requirement_set_id))
            for row in noncommitted
            if row.operation_id in pending_ids))
        returned_ids = frozenset(
            row.operation_id
            for row in schedule.reservations
            if row.state in ("returned", "expired"))
        stranded_mass = sum(
            float(row.overlap_score)
            for row in noncommitted)
        returned_mass = sum(
            float(candidate_by_operation[value].overlap_score)
            for value in returned_ids
            if value in candidate_by_operation)
        incomplete = tuple(
            row.operation_id
            for row in schedule.reservations
            if row.state != "committed")
        starvation = self._starvation(
            schedule, budgets, ages)
        reservation_ages = tuple(sorted(
            (row.operation_id, int(
                ages.get(row.operation_id, 0)))
            for row in schedule.reservations
            if row.state != "committed"))
        return FlowPacketDecision(
            candidates=candidates,
            eligible_operation_ids=eligible_ids,
            packet_schedule=schedule,
            reservation_ledger=ledger,
            diagnostics=FlowIntegralityDiagnostics(
                relaxed_continuous_value=relaxed_value,
                packet_feasible_value=(
                    schedule.committed_value),
                integrality_gap=schedule.integrality_gap,
                stranded_mass=stranded_mass,
                incomplete_reservations=incomplete,
                packet_starvation=starvation,
                reservation_ages=reservation_ages,
                returned_mass=returned_mass,
                return_rate=(
                    len(returned_ids)
                    / float(len(schedule.reservations))
                    if schedule.reservations else 0.0),
                exact_revalidation_failures=tuple(
                    sorted(invalid_ids))),
            integrator_identity=self.INTEGRATOR_IDENTITY)
