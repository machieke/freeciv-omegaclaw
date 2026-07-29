"""Bounded integer value-of-computation arbitration across goals."""

import math
from dataclasses import dataclass

from .packets import PacketBudget, PacketCost, ResourceKind


ACTIVITY_KINDS = frozenset((
    "probe", "estimate", "infer", "observe", "simulate",
    "act", "expand", "retain"))


def _nonnegative(value, name):
    value = float(value)
    if value < 0.0 or not math.isfinite(value):
        raise ValueError(
            "{} must be finite and non-negative".format(name))
    return value


def _packet_count(value, name, minimum=0):
    if (isinstance(value, bool)
            or not isinstance(value, int)
            or value < minimum):
        raise ValueError(
            "{} must be an integer >= {}".format(name, minimum))
    return int(value)


@dataclass(frozen=True)
class ActivityBid:
    goal_id: str
    activity: str
    resource: ResourceKind
    next_packet_value: float
    uncertainty: float
    minimum_packets: int
    maximum_packets: int
    safety_class: bool

    def __post_init__(self):
        if not isinstance(self.goal_id, str) or not self.goal_id:
            raise ValueError("activity bid requires goal ID")
        if self.activity not in ACTIVITY_KINDS:
            raise ValueError("unknown activity kind")
        if not isinstance(self.resource, ResourceKind):
            raise TypeError(
                "activity bid resource must be ResourceKind")
        _nonnegative(
            self.next_packet_value, "next packet value")
        _nonnegative(self.uncertainty, "bid uncertainty")
        minimum = _packet_count(
            self.minimum_packets, "minimum packets")
        maximum = _packet_count(
            self.maximum_packets, "maximum packets")
        if minimum > maximum:
            raise ValueError(
                "minimum packets cannot exceed maximum")
        if not isinstance(self.safety_class, bool):
            raise TypeError("safety class must be boolean")

    @property
    def bid_id(self):
        return "{}:{}:{}".format(
            self.goal_id, self.activity, self.resource.value)

    def to_dict(self):
        return {
            "activity": self.activity,
            "goal_id": self.goal_id,
            "maximum_packets": int(self.maximum_packets),
            "minimum_packets": int(self.minimum_packets),
            "next_packet_value": float(
                self.next_packet_value),
            "resource": self.resource.value,
            "safety_class": bool(self.safety_class),
            "uncertainty": float(self.uncertainty),
        }


@dataclass(frozen=True)
class ActivityAllocation:
    goal_id: str
    activity: str
    resource: ResourceKind
    packets: int
    reasons: tuple
    final_marginal_value: float

    def __post_init__(self):
        if not isinstance(self.goal_id, str) or not self.goal_id:
            raise ValueError("activity allocation requires goal ID")
        if self.activity not in ACTIVITY_KINDS:
            raise ValueError("unknown allocation activity")
        if not isinstance(self.resource, ResourceKind):
            raise TypeError(
                "allocation resource must be ResourceKind")
        _packet_count(self.packets, "allocated packets", minimum=1)
        if not self.reasons or any(
                not isinstance(value, str) or not value
                for value in self.reasons):
            raise ValueError(
                "activity allocation requires reasons")
        _nonnegative(
            self.final_marginal_value,
            "final marginal value")

    @property
    def bid_id(self):
        return "{}:{}:{}".format(
            self.goal_id, self.activity, self.resource.value)

    def to_dict(self):
        return {
            "activity": self.activity,
            "final_marginal_value": float(
                self.final_marginal_value),
            "goal_id": self.goal_id,
            "packets": int(self.packets),
            "reasons": list(self.reasons),
            "resource": self.resource.value,
        }


@dataclass(frozen=True)
class ExplorationFloorAllocation:
    bid_id: str
    goal_id: str
    resource: ResourceKind
    packets: int

    def __post_init__(self):
        if not self.bid_id or not self.goal_id:
            raise ValueError(
                "exploration allocation requires IDs")
        if not isinstance(self.resource, ResourceKind):
            raise TypeError(
                "exploration resource must be ResourceKind")
        _packet_count(
            self.packets, "exploration packets", minimum=1)

    def to_dict(self):
        return {
            "bid_id": self.bid_id,
            "goal_id": self.goal_id,
            "packets": int(self.packets),
            "resource": self.resource.value,
        }


@dataclass(frozen=True)
class UnmetMinimum:
    bid_id: str
    requested: int
    allocated: int
    safety_class: bool

    def __post_init__(self):
        if not self.bid_id:
            raise ValueError("unmet minimum requires bid ID")
        requested = _packet_count(
            self.requested, "requested minimum")
        allocated = _packet_count(
            self.allocated, "allocated minimum")
        if allocated >= requested:
            raise ValueError(
                "unmet minimum must remain below request")
        if not isinstance(self.safety_class, bool):
            raise TypeError(
                "unmet safety class must be boolean")

    def to_dict(self):
        return {
            "allocated": int(self.allocated),
            "bid_id": self.bid_id,
            "requested": int(self.requested),
            "safety_class": bool(self.safety_class),
        }


@dataclass(frozen=True)
class BudgetDecision:
    allocations: tuple
    metacontrol_cost: tuple
    exploration_floor: tuple
    fallback_used: bool
    declared_budgets: tuple = ()
    unmet_minimums: tuple = ()
    solver_identity: str = "pf-pln-budget-arbiter/1.0"

    def __post_init__(self):
        if any(not isinstance(row, ActivityAllocation)
               for row in self.allocations):
            raise TypeError(
                "budget allocations must contain "
                "ActivityAllocation")
        allocation_ids = [row.bid_id for row in self.allocations]
        if len(allocation_ids) != len(set(allocation_ids)):
            raise ValueError(
                "budget decision allocations must be unique")
        if any(not isinstance(row, PacketCost)
               for row in self.metacontrol_cost):
            raise TypeError(
                "metacontrol costs must contain PacketCost")
        if any(not isinstance(row, ExplorationFloorAllocation)
               for row in self.exploration_floor):
            raise TypeError(
                "exploration floor must contain "
                "ExplorationFloorAllocation")
        if not isinstance(self.fallback_used, bool):
            raise TypeError("fallback flag must be boolean")
        if any(not isinstance(row, PacketBudget)
               for row in self.declared_budgets):
            raise TypeError(
                "declared budgets must contain PacketBudget")
        if any(not isinstance(row, UnmetMinimum)
               for row in self.unmet_minimums):
            raise TypeError(
                "unmet minimums must contain UnmetMinimum")
        if not self.solver_identity:
            raise ValueError(
                "budget decision requires solver identity")
        if not self.conserved:
            raise ValueError(
                "budget decision exceeds declared resources")

    def accounting(self):
        declared = dict(
            (row.resource, row.available)
            for row in self.declared_budgets)
        consumed = dict((resource, 0) for resource in declared)
        metacontrol = dict((resource, 0) for resource in declared)
        for row in self.allocations:
            consumed[row.resource] = (
                consumed.get(row.resource, 0) + row.packets)
        for row in self.metacontrol_cost:
            metacontrol[row.resource] = (
                metacontrol.get(row.resource, 0) + row.quanta)
        return {
            resource.value: {
                "activity_packets": int(
                    consumed.get(resource, 0)),
                "declared": int(available),
                "metacontrol_packets": int(
                    metacontrol.get(resource, 0)),
                "remaining": int(
                    available
                    - consumed.get(resource, 0)
                    - metacontrol.get(resource, 0)),
            }
            for resource, available in sorted(
                declared.items(),
                key=lambda row: row[0].value)
        }

    @property
    def conserved(self):
        return all(
            row["remaining"] >= 0
            for row in self.accounting().values())

    def allocation_for(self, goal_id, activity, resource):
        bid_id = "{}:{}:{}".format(
            goal_id, activity, resource.value)
        return next((
            row for row in self.allocations
            if row.bid_id == bid_id), None)

    def to_dict(self):
        return {
            "accounting": self.accounting(),
            "allocations": [
                row.to_dict() for row in self.allocations],
            "conserved": bool(self.conserved),
            "declared_budgets": [
                row.to_dict() for row in self.declared_budgets],
            "exploration_floor": [
                row.to_dict() for row in self.exploration_floor],
            "fallback_used": bool(self.fallback_used),
            "metacontrol_cost": [
                row.to_dict() for row in self.metacontrol_cost],
            "solver_identity": self.solver_identity,
            "unmet_minimums": [
                row.to_dict() for row in self.unmet_minimums],
        }


@dataclass(frozen=True)
class BudgetArbiterConfig:
    maximum_metacontrol_budget_fraction: float = 0.10
    metacontrol_cpu_packets: int = 1
    exploration_packets_per_goal: int = 1
    update_cadence: int = 4
    uncertainty_value_weight: float = 0.05

    def __post_init__(self):
        fraction = float(
            self.maximum_metacontrol_budget_fraction)
        if not 0.0 <= fraction <= 1.0 or not math.isfinite(
                fraction):
            raise ValueError(
                "metacontrol fraction must be in [0,1]")
        _packet_count(
            self.metacontrol_cpu_packets,
            "metacontrol CPU packets")
        _packet_count(
            self.exploration_packets_per_goal,
            "exploration packets per goal")
        _packet_count(
            self.update_cadence,
            "budget update cadence", minimum=1)
        _nonnegative(
            self.uncertainty_value_weight,
            "uncertainty value weight")


class BudgetArbiter:
    """Bounded, deterministic integer marginal-value arbiter."""

    SOLVER_IDENTITY = "pf-pln-budget-arbiter/1.0"

    def __init__(self, config=None):
        self.config = config or BudgetArbiterConfig()
        if not isinstance(self.config, BudgetArbiterConfig):
            raise TypeError(
                "budget arbiter config must be BudgetArbiterConfig")

    @staticmethod
    def _ordered_bids(bids):
        bids = tuple(bids)
        if any(not isinstance(row, ActivityBid) for row in bids):
            raise TypeError("budget bids must contain ActivityBid")
        identifiers = [row.bid_id for row in bids]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("budget bid identities must be unique")
        return tuple(sorted(bids, key=lambda row: (
            not row.safety_class,
            -float(row.next_packet_value),
            row.bid_id)))

    @staticmethod
    def _ordered_budgets(budgets):
        budgets = tuple(sorted(
            tuple(budgets), key=lambda row: row.resource.value))
        if any(not isinstance(row, PacketBudget) for row in budgets):
            raise TypeError(
                "budgets must contain PacketBudget")
        resources = [row.resource for row in budgets]
        if len(resources) != len(set(resources)):
            raise ValueError(
                "budget resources must be unique")
        return budgets

    def _metacontrol_cost(self, budgets, due):
        if not due:
            return ()
        cpu = next((
            row.available for row in budgets
            if row.resource == ResourceKind.CPU), 0)
        cap = int(math.floor(
            float(cpu)
            * self.config.maximum_metacontrol_budget_fraction))
        packets = min(
            self.config.metacontrol_cpu_packets, cap)
        return (
            (PacketCost(ResourceKind.CPU, packets),)
            if packets > 0 else ())

    def decide(
            self, bids, budgets, calibration_healthy=True,
            cycle_index=0):
        bids = self._ordered_bids(bids)
        budgets = self._ordered_budgets(budgets)
        if (isinstance(cycle_index, bool)
                or not isinstance(cycle_index, int)
                or cycle_index < 0):
            raise ValueError(
                "cycle index must be a non-negative integer")
        if not isinstance(calibration_healthy, bool):
            raise TypeError(
                "calibration health must be boolean")
        due = (
            cycle_index % self.config.update_cadence == 0)
        fallback_used = bool(
            not calibration_healthy or not due)
        metacontrol_cost = self._metacontrol_cost(
            budgets, due)
        remaining = dict(
            (row.resource, row.available)
            for row in budgets)
        for row in metacontrol_cost:
            remaining[row.resource] -= row.quanta
        allocated = dict((row.bid_id, 0) for row in bids)
        reasons = dict((row.bid_id, []) for row in bids)
        by_id = dict((row.bid_id, row) for row in bids)

        # Safety minima are lexicographically earlier than every other bid.
        for safety_class in (True, False):
            for bid in bids:
                if bid.safety_class != safety_class:
                    continue
                packets = min(
                    bid.minimum_packets,
                    bid.maximum_packets,
                    remaining.get(bid.resource, 0))
                if packets > 0:
                    allocated[bid.bid_id] += packets
                    remaining[bid.resource] -= packets
                    reasons[bid.bid_id].append(
                        "safety-minimum"
                        if safety_class else
                        "base-progress-minimum")

        # One bounded exploration reservation for each uncertain goal.
        exploration = []
        for resource in sorted(
                remaining, key=lambda value: value.value):
            resource_bids = [
                row for row in bids
                if row.resource == resource
                and row.uncertainty > 0.0
                and allocated[row.bid_id] < row.maximum_packets]
            goal_best = {}
            for bid in resource_bids:
                current = goal_best.get(bid.goal_id)
                stronger = (
                    current is None
                    or (bid.uncertainty, bid.next_packet_value)
                    > (current.uncertainty,
                       current.next_packet_value)
                    or (
                        (bid.uncertainty,
                         bid.next_packet_value)
                        == (current.uncertainty,
                            current.next_packet_value)
                        and bid.bid_id < current.bid_id))
                if stronger:
                    goal_best[bid.goal_id] = bid
            for goal_id in sorted(goal_best):
                bid = goal_best[goal_id]
                packets = min(
                    self.config.exploration_packets_per_goal,
                    bid.maximum_packets - allocated[bid.bid_id],
                    remaining[resource])
                if packets <= 0:
                    continue
                allocated[bid.bid_id] += packets
                remaining[resource] -= packets
                reasons[bid.bid_id].append("exploration-floor")
                exploration.append(ExplorationFloorAllocation(
                    bid.bid_id, bid.goal_id, resource, packets))

        if fallback_used:
            # Static bounded round-robin makes base progress without
            # recursively estimating value when calibration is unhealthy.
            eligible = [
                row for row in bids
                if allocated[row.bid_id] < row.maximum_packets]
            while eligible and any(
                    remaining.get(row.resource, 0) > 0
                    for row in eligible):
                progressed = False
                for bid in eligible:
                    if (remaining.get(bid.resource, 0) <= 0
                            or allocated[bid.bid_id]
                            >= bid.maximum_packets):
                        continue
                    allocated[bid.bid_id] += 1
                    remaining[bid.resource] -= 1
                    reasons[bid.bid_id].append(
                        "static-fallback")
                    progressed = True
                if not progressed:
                    break
        else:
            # Recompute one diminishing marginal at a time.
            while True:
                eligible = [
                    row for row in bids
                    if remaining.get(row.resource, 0) > 0
                    and allocated[row.bid_id] < row.maximum_packets]
                if not eligible:
                    break

                def marginal(bid):
                    extra = max(
                        0,
                        allocated[bid.bid_id]
                        - bid.minimum_packets)
                    return (
                        float(bid.next_packet_value)
                        / (1.0 + float(extra))
                        + self.config.uncertainty_value_weight
                        * float(bid.uncertainty)
                        / math.sqrt(1.0 + float(extra)))

                bid = min(eligible, key=lambda row: (
                    -marginal(row), row.bid_id))
                allocated[bid.bid_id] += 1
                remaining[bid.resource] -= 1
                reasons[bid.bid_id].append(
                    "calibrated-marginal-value")

        allocations = []
        for bid_id in sorted(allocated):
            packets = allocated[bid_id]
            if packets <= 0:
                continue
            bid = by_id[bid_id]
            extra = max(0, packets - bid.minimum_packets)
            final_marginal = (
                float(bid.next_packet_value)
                / (1.0 + float(extra))
                + self.config.uncertainty_value_weight
                * float(bid.uncertainty)
                / math.sqrt(1.0 + float(extra)))
            allocations.append(ActivityAllocation(
                bid.goal_id, bid.activity, bid.resource,
                packets, tuple(sorted(set(reasons[bid_id]))),
                final_marginal))
        unmet = tuple(
            UnmetMinimum(
                bid.bid_id, bid.minimum_packets,
                allocated[bid.bid_id], bid.safety_class)
            for bid in bids
            if allocated[bid.bid_id] < bid.minimum_packets)
        return BudgetDecision(
            allocations=tuple(allocations),
            metacontrol_cost=metacontrol_cost,
            exploration_floor=tuple(exploration),
            fallback_used=fallback_used,
            declared_budgets=budgets,
            unmet_minimums=unmet,
            solver_identity=self.SOLVER_IDENTITY)
