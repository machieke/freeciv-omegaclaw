"""Deterministic whole-packet scheduling for scalar PF-v2."""

import math
from dataclasses import dataclass
from enum import Enum

from .coalitions import RequirementSet


class ResourceKind(str, Enum):
    CPU = "cpu"
    EXACT_RULE = "exact_rule"
    OBSERVATION = "observation"
    SIMULATION = "simulation"
    ACTION = "action"
    EXPANSION = "expansion"
    LLM_TOKEN = "llm_token"
    MEMORY = "memory"
    DURABLE_MUTATION = "durable_mutation"


@dataclass(frozen=True)
class PacketCost:
    resource: ResourceKind
    quanta: int

    def __post_init__(self):
        if not isinstance(self.resource, ResourceKind):
            raise TypeError("packet cost resource must be ResourceKind")
        if (isinstance(self.quanta, bool)
                or not isinstance(self.quanta, int)
                or self.quanta <= 0):
            raise ValueError("packet cost quanta must be a positive integer")

    def to_dict(self):
        return {
            "quanta": int(self.quanta),
            "resource": self.resource.value,
        }


@dataclass(frozen=True)
class PacketBudget:
    resource: ResourceKind
    available: int

    def __post_init__(self):
        if not isinstance(self.resource, ResourceKind):
            raise TypeError("packet budget resource must be ResourceKind")
        if (isinstance(self.available, bool)
                or not isinstance(self.available, int)
                or self.available < 0):
            raise ValueError(
                "packet budget must be a non-negative integer")

    def to_dict(self):
        return {
            "available": int(self.available),
            "resource": self.resource.value,
        }


@dataclass(frozen=True)
class PacketReservation:
    operation_id: str
    costs: tuple
    reserved: tuple
    state: str
    requirement_set_id: object = None
    reason: object = None

    def __post_init__(self):
        if not isinstance(self.operation_id, str) or not self.operation_id:
            raise ValueError("packet reservation requires operation ID")
        if self.state not in (
                "pending", "complete", "returned",
                "committed", "expired"):
            raise ValueError("unknown packet reservation state")
        for rows, name in (
                (self.costs, "costs"), (self.reserved, "reserved")):
            if any(not isinstance(value, PacketCost) for value in rows):
                raise TypeError(
                    "reservation {} must contain PacketCost".format(name))
            resources = [value.resource for value in rows]
            if len(resources) != len(set(resources)):
                raise ValueError(
                    "reservation {} resources must be unique".format(name))
        costs = dict(
            (value.resource, value.quanta) for value in self.costs)
        if any(value.quanta > costs.get(value.resource, 0)
               for value in self.reserved):
            raise ValueError("reserved packets cannot exceed costs")
        if self.state in ("complete", "committed"):
            if dict((row.resource, row.quanta) for row in self.reserved) != costs:
                raise ValueError(
                    "complete reservation must cover every packet cost")

    @property
    def complete(self):
        return self.state in ("complete", "committed")

    def to_dict(self):
        return {
            "costs": [row.to_dict() for row in self.costs],
            "operation_id": self.operation_id,
            "reason": self.reason,
            "requirement_set_id": self.requirement_set_id,
            "reserved": [row.to_dict() for row in self.reserved],
            "state": self.state,
        }


@dataclass(frozen=True)
class PacketSchedule:
    budgets: tuple
    reservations: tuple
    committed_operation_ids: tuple
    stranded_quanta: tuple
    integrality_gap: float
    relaxed_value: float
    committed_value: float
    scheduler_identity: str

    def __post_init__(self):
        if any(not isinstance(row, PacketBudget) for row in self.budgets):
            raise TypeError("packet schedule budgets must be PacketBudget")
        if any(not isinstance(
                row, PacketReservation) for row in self.reservations):
            raise TypeError(
                "packet schedule reservations must be PacketReservation")
        if any(not isinstance(row, PacketCost)
               for row in self.stranded_quanta):
            raise TypeError(
                "packet schedule stranded quanta must be PacketCost")
        if (float(self.integrality_gap) < 0.0
                or not math.isfinite(float(self.integrality_gap))):
            raise ValueError("packet integrality gap cannot be negative")
        for value, name in (
                (self.relaxed_value, "relaxed value"),
                (self.committed_value, "committed value")):
            if float(value) < 0.0 or not math.isfinite(float(value)):
                raise ValueError(
                    "{} must be finite and non-negative".format(name))
        committed = tuple(
            row.operation_id for row in self.reservations
            if row.state == "committed")
        if committed != self.committed_operation_ids:
            raise ValueError(
                "committed IDs must match committed reservations")

    def accounting(self):
        declared = dict(
            (row.resource, row.available) for row in self.budgets)
        consumed = dict((resource, 0) for resource in declared)
        for reservation in self.reservations:
            if reservation.state != "committed":
                continue
            for cost in reservation.reserved:
                consumed[cost.resource] = (
                    consumed.get(cost.resource, 0) + cost.quanta)
        stranded = dict(
            (row.resource, row.quanta)
            for row in self.stranded_quanta)
        return {
            resource.value: {
                "consumed": int(consumed.get(resource, 0)),
                "declared": int(available),
                "stranded": int(stranded.get(resource, 0)),
            }
            for resource, available in sorted(
                declared.items(), key=lambda row: row[0].value)
        }

    @property
    def conserved(self):
        return all(
            row["consumed"] + row["stranded"] == row["declared"]
            for row in self.accounting().values())

    def to_dict(self):
        return {
            "accounting": self.accounting(),
            "budgets": [row.to_dict() for row in self.budgets],
            "committed_operation_ids": list(
                self.committed_operation_ids),
            "committed_value": float(self.committed_value),
            "conserved": bool(self.conserved),
            "integrality_gap": float(self.integrality_gap),
            "relaxed_value": float(self.relaxed_value),
            "reservations": [
                row.to_dict() for row in self.reservations],
            "scheduler_identity": self.scheduler_identity,
            "stranded_quanta": [
                row.to_dict() for row in self.stranded_quanta],
        }


class PacketScheduler:
    """Bounded deterministic greedy scheduler with atomic reservations."""

    SOLVER_IDENTITY = "pf-pln-packet-scheduler/2.0"

    @staticmethod
    def _cost_map(operation):
        return dict(
            (row.resource, row.quanta * operation.packet_threshold)
            for row in operation.packet_costs)

    @staticmethod
    def _ordered_costs(operation):
        return tuple(sorted(
            (PacketCost(
                row.resource,
                row.quanta * operation.packet_threshold)
             for row in operation.packet_costs),
            key=lambda row: row.resource.value))

    @staticmethod
    def _fits(costs, available):
        return all(
            available.get(resource, 0) >= quanta
            for resource, quanta in costs.items())

    def schedule(
            self, operations, scores, budgets,
            requirement_sets=(), premise_packets=None,
            abandoned_operation_ids=(), expired_operation_ids=(),
            relaxed_allocations=None):
        operations = tuple(operations)
        scores = tuple(scores)
        requirement_sets = tuple(requirement_sets)
        budgets = tuple(sorted(
            budgets, key=lambda row: row.resource.value))
        if any(not isinstance(row, PacketBudget) for row in budgets):
            raise TypeError("budgets must contain PacketBudget")
        if len(set(row.resource for row in budgets)) != len(budgets):
            raise ValueError("packet budget resources must be unique")
        by_operation = dict(
            (operation.operation_id, operation)
            for operation in operations)
        if len(by_operation) != len(operations):
            raise ValueError("operation IDs must be unique")
        score_by_operation = dict(
            (score.operation_id, score) for score in scores)
        if len(score_by_operation) != len(scores):
            raise ValueError("operation scores must be unique")
        if set(score_by_operation) - set(by_operation):
            raise ValueError("scores reference unknown operations")
        if any(not isinstance(row, RequirementSet)
               for row in requirement_sets):
            raise TypeError(
                "requirement_sets must contain RequirementSet")
        requirements = dict(
            (row.requirement_set_id, row)
            for row in requirement_sets)
        if len(requirements) != len(requirement_sets):
            raise ValueError("requirement set IDs must be unique")
        premise_packets = dict(premise_packets or {})
        if any(
                not isinstance(premise_id, str) or not premise_id
                or isinstance(quanta, bool)
                or not isinstance(quanta, int) or quanta < 0
                for premise_id, quanta in premise_packets.items()):
            raise ValueError(
                "premise packets require non-negative integer quanta")
        abandoned = frozenset(str(value)
                              for value in abandoned_operation_ids)
        expired = frozenset(str(value)
                            for value in expired_operation_ids)
        available = dict(
            (row.resource, row.available) for row in budgets)

        admissible = [
            score for score in scores
            if score.admissible
            and score.operation_id in by_operation
            and by_operation[score.operation_id].packet_costs
            and math.isfinite(float(score.priority))
            and float(score.priority) > 0.0
        ]

        def scheduling_key(score):
            operation = by_operation[score.operation_id]
            total_cost = sum(
                row.quanta * operation.packet_threshold
                for row in operation.packet_costs)
            density = float(score.priority) / max(1, total_cost)
            return (
                -density, -float(score.priority),
                score.operation_id)

        ranked = sorted(admissible, key=scheduling_key)
        reservations = []
        committed_ids = []
        committed_value = 0.0
        for score in ranked:
            operation = by_operation[score.operation_id]
            costs = self._cost_map(operation)
            ordered_costs = self._ordered_costs(operation)
            requirement = (
                requirements.get(operation.requirement_set_id)
                if operation.requirement_set_id is not None else None)
            if (operation.requirement_set_id is not None
                    and requirement is None):
                reservations.append(PacketReservation(
                    operation.operation_id, ordered_costs, (),
                    "returned", operation.requirement_set_id,
                    "unknown-requirement-set"))
                continue
            if (requirement is not None
                    and not requirement.complete(premise_packets)):
                reservations.append(PacketReservation(
                    operation.operation_id, ordered_costs, (),
                    "returned", operation.requirement_set_id,
                    "incomplete-requirement-set"))
                continue
            if not self._fits(costs, available):
                reservations.append(PacketReservation(
                    operation.operation_id, ordered_costs, (),
                    "pending", operation.requirement_set_id,
                    "insufficient-whole-packets"))
                continue
            if operation.operation_id in abandoned:
                reservations.append(PacketReservation(
                    operation.operation_id, ordered_costs,
                    ordered_costs, "returned",
                    operation.requirement_set_id, "abandoned"))
                continue
            if operation.operation_id in expired:
                reservations.append(PacketReservation(
                    operation.operation_id, ordered_costs,
                    ordered_costs, "expired",
                    operation.requirement_set_id, "expired"))
                continue
            for resource, quanta in costs.items():
                available[resource] -= quanta
            reservations.append(PacketReservation(
                operation.operation_id, ordered_costs,
                ordered_costs, "committed",
                operation.requirement_set_id, None))
            committed_ids.append(operation.operation_id)
            committed_value += max(0.0, float(score.priority))

        if relaxed_allocations is None:
            relaxed_value = sum(
                max(0.0, float(score.priority))
                for score in admissible)
        else:
            relaxed_allocations = tuple(relaxed_allocations)
            allocations = dict(relaxed_allocations)
            if len(allocations) != len(relaxed_allocations):
                raise ValueError(
                    "relaxed allocation operation IDs must be unique")
            if any(
                    not math.isfinite(float(fraction))
                    or not 0.0 <= float(fraction) <= 1.0
                    for fraction in allocations.values()):
                raise ValueError(
                    "relaxed allocations must be fractions")
            relaxed_value = sum(
                max(0.0, float(score_by_operation[operation_id].priority))
                * float(fraction)
                for operation_id, fraction in allocations.items()
                if operation_id in score_by_operation)
        if not math.isfinite(relaxed_value) or relaxed_value < 0.0:
            raise ValueError("relaxed value must be finite and non-negative")
        stranded = tuple(
            PacketCost(resource, quanta)
            for resource, quanta in sorted(
                available.items(), key=lambda row: row[0].value)
            if quanta > 0)
        return PacketSchedule(
            budgets=budgets,
            reservations=tuple(reservations),
            committed_operation_ids=tuple(committed_ids),
            stranded_quanta=stranded,
            integrality_gap=max(0.0, relaxed_value - committed_value),
            relaxed_value=relaxed_value,
            committed_value=committed_value,
            scheduler_identity=self.SOLVER_IDENTITY)
