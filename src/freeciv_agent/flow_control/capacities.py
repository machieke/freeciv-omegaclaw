"""Provenance-typed capacities and multi-commodity flow allocation."""

import math
from dataclasses import dataclass
from enum import Enum

from ..events.schema import structural_hash
from ..pressure.packets import ResourceKind


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


class CapacityKind(str, Enum):
    MEASURED = "measured"
    ALLOCATED = "allocated"
    SHAPING = "shaping"
    NONE = "none"


@dataclass(frozen=True)
class CapacityRecord:
    edge_or_node_id: str
    resource: ResourceKind
    value: float
    kind: CapacityKind
    provenance_id: object
    measured_window: object
    confidence: float

    def __post_init__(self):
        _required_text(
            self.edge_or_node_id, "capacity target ID")
        if not isinstance(self.resource, ResourceKind):
            object.__setattr__(
                self, "resource", ResourceKind(self.resource))
        if not isinstance(self.kind, CapacityKind):
            object.__setattr__(
                self, "kind", CapacityKind(self.kind))
        value = _finite_nonnegative(
            self.value, "capacity value")
        confidence = float(self.confidence)
        if (not math.isfinite(confidence)
                or not 0.0 <= confidence <= 1.0):
            raise ValueError(
                "capacity confidence must be in [0, 1]")
        if self.kind == CapacityKind.NONE:
            if value != 0.0:
                raise ValueError(
                    "unconstrained capacity must use zero sentinel")
            if (self.provenance_id is not None
                    or self.measured_window is not None):
                raise ValueError(
                    "unconstrained capacity has no provenance")
        else:
            _required_text(
                self.provenance_id,
                "capacity provenance ID")
        if self.kind == CapacityKind.MEASURED:
            if (not isinstance(self.measured_window, tuple)
                    or len(self.measured_window) != 2):
                raise ValueError(
                    "measured capacity requires a two-bound window")
        elif self.measured_window is not None:
            raise ValueError(
                "only measured capacity has a measurement window")

    @property
    def capacity_id(self):
        return "{}:{}:{}".format(
            self.edge_or_node_id,
            self.resource.value, self.kind.value)

    def to_dict(self):
        return {
            "confidence": float(self.confidence),
            "edge_or_node_id": self.edge_or_node_id,
            "kind": self.kind.value,
            "measured_window": (
                list(self.measured_window)
                if self.measured_window is not None else None),
            "provenance_id": self.provenance_id,
            "resource": self.resource.value,
            "value": float(self.value),
        }


@dataclass(frozen=True)
class CommodityFlowRequest:
    commodity_id: str
    resource: ResourceKind
    edge_ids: tuple
    requested_flow: tuple
    objective_weight: float = 1.0

    def __post_init__(self):
        _required_text(
            self.commodity_id, "flow commodity ID")
        if not isinstance(self.resource, ResourceKind):
            object.__setattr__(
                self, "resource", ResourceKind(self.resource))
        if len(self.edge_ids) != len(self.requested_flow):
            raise ValueError(
                "commodity edge and flow arrays must align")
        if (len(set(self.edge_ids)) != len(self.edge_ids)
                or any(not isinstance(value, str) or not value
                       for value in self.edge_ids)):
            raise ValueError(
                "commodity edge IDs must be unique nonempty text")
        if any(not math.isfinite(float(value))
               for value in self.requested_flow):
            raise ValueError(
                "requested commodity flow must be finite")
        weight = float(self.objective_weight)
        if not math.isfinite(weight) or weight <= 0.0:
            raise ValueError(
                "commodity objective weight must be positive")

    @property
    def request_id(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "commodity_id": self.commodity_id,
            "edge_ids": list(self.edge_ids),
            "objective_weight": float(
                self.objective_weight),
            "requested_flow": [
                float(value) for value in self.requested_flow],
            "resource": self.resource.value,
        }


@dataclass(frozen=True)
class CommodityFlowAllocation:
    commodity_id: str
    resource: ResourceKind
    edge_ids: tuple
    allocated_flow: tuple
    requested_flow: tuple

    def __post_init__(self):
        if not isinstance(self.resource, ResourceKind):
            raise TypeError(
                "allocation resource must be ResourceKind")
        if (len(self.edge_ids) != len(self.allocated_flow)
                or len(self.edge_ids) != len(self.requested_flow)):
            raise ValueError(
                "allocation arrays must align")
        if any(not math.isfinite(float(value))
               for value in (
                   self.allocated_flow + self.requested_flow)):
            raise ValueError(
                "allocated flow must be finite")

    def to_dict(self):
        return {
            "allocated_flow": [
                float(value) for value in self.allocated_flow],
            "commodity_id": self.commodity_id,
            "edge_ids": list(self.edge_ids),
            "requested_flow": [
                float(value) for value in self.requested_flow],
            "resource": self.resource.value,
        }


@dataclass(frozen=True)
class CapacityDual:
    capacity_id: str
    edge_or_node_id: str
    resource: ResourceKind
    value: float
    kind: CapacityKind
    provenance_id: str
    converged: bool
    economic_price: bool
    permitted_response: str

    def __post_init__(self):
        if not isinstance(self.resource, ResourceKind):
            raise TypeError(
                "dual resource must be ResourceKind")
        if not isinstance(self.kind, CapacityKind):
            raise TypeError(
                "dual kind must be CapacityKind")
        value = _finite_nonnegative(
            self.value, "capacity dual")
        _required_text(
            self.provenance_id, "dual capacity provenance")
        if self.economic_price and (
                not self.converged
                or self.kind != CapacityKind.MEASURED
                or value <= 0.0):
            raise ValueError(
                "only converged positive measured dual is an "
                "economic price")
        allowed = {
            "structural_bottleneck_candidate",
            "request_arbiter_reconsideration",
            "numerical_shaping_only",
            "exploration_guidance_only",
            "none",
        }
        if self.permitted_response not in allowed:
            raise ValueError(
                "unknown capacity-dual response")
        if (self.kind == CapacityKind.SHAPING
                and self.permitted_response
                == "structural_bottleneck_candidate"):
            raise ValueError(
                "shaping dual cannot trigger structural change")
        if (self.kind == CapacityKind.ALLOCATED
                and self.permitted_response
                != (
                    "request_arbiter_reconsideration"
                    if self.converged and value > 0.0
                    else "none")
                and self.permitted_response
                != "exploration_guidance_only"):
            raise ValueError(
                "allocated dual may only address the arbiter")

    def to_dict(self):
        return {
            "capacity_id": self.capacity_id,
            "converged": self.converged,
            "economic_price": self.economic_price,
            "edge_or_node_id": self.edge_or_node_id,
            "kind": self.kind.value,
            "permitted_response": self.permitted_response,
            "provenance_id": self.provenance_id,
            "resource": self.resource.value,
            "value": float(self.value),
        }


@dataclass(frozen=True)
class MultiCommodityResult:
    allocations: tuple
    capacity_duals: tuple
    primal_residual: float
    dual_residual: float
    complementarity_gap: float
    active_set_changes: int
    dual_autocorrelation: object
    converged: bool
    iterations: int
    health: str
    unused_capacity_ids: tuple
    solver_identity: str

    def __post_init__(self):
        if any(not isinstance(row, CommodityFlowAllocation)
               for row in self.allocations):
            raise TypeError(
                "multi-commodity allocations have wrong type")
        if any(not isinstance(row, CapacityDual)
               for row in self.capacity_duals):
            raise TypeError(
                "capacity duals have wrong type")
        for value, name in (
                (self.primal_residual, "primal residual"),
                (self.dual_residual, "dual residual"),
                (self.complementarity_gap,
                 "complementarity gap")):
            _finite_nonnegative(value, name)
        if self.dual_autocorrelation is not None:
            value = float(self.dual_autocorrelation)
            if not math.isfinite(value) or not -1.0 <= value <= 1.0:
                raise ValueError(
                    "dual autocorrelation must be in [-1, 1]")
        if self.active_set_changes < 0 or self.iterations < 0:
            raise ValueError(
                "solver counts must be non-negative")
        if self.converged != (self.health == "healthy"):
            raise ValueError(
                "multi-commodity health must match convergence")
        if any(
                row.economic_price
                for row in self.capacity_duals
                if not self.converged):
            raise ValueError(
                "nonconverged solve cannot report prices")

    @property
    def result_hash(self):
        return structural_hash(self.to_dict())

    @property
    def warm_start(self):
        return tuple(
            (row.capacity_id, float(row.value))
            for row in self.capacity_duals)

    def total_edge_flow(self, edge_id, resource):
        if not isinstance(resource, ResourceKind):
            resource = ResourceKind(resource)
        return sum(
            abs(float(value))
            for row in self.allocations
            if row.resource == resource
            for current_edge, value in zip(
                row.edge_ids, row.allocated_flow)
            if current_edge == edge_id)

    def to_dict(self):
        return {
            "active_set_changes": self.active_set_changes,
            "allocations": [
                row.to_dict() for row in self.allocations],
            "capacity_duals": [
                row.to_dict() for row in self.capacity_duals],
            "complementarity_gap": float(
                self.complementarity_gap),
            "converged": self.converged,
            "dual_autocorrelation": (
                float(self.dual_autocorrelation)
                if self.dual_autocorrelation is not None
                else None),
            "dual_residual": float(self.dual_residual),
            "health": self.health,
            "iterations": self.iterations,
            "primal_residual": float(
                self.primal_residual),
            "solver_identity": self.solver_identity,
            "unused_capacity_ids": list(
                self.unused_capacity_ids),
        }


class MultiCommodityCapacitySolver:
    """Separable convex dual solve for shared absolute-flow capacities."""

    SOLVER_IDENTITY = "pf-multi-commodity-capacity-dual/1.0"

    def __init__(self, maximum_iterations=80):
        if (isinstance(maximum_iterations, bool)
                or not isinstance(maximum_iterations, int)
                or maximum_iterations < 1):
            raise ValueError(
                "capacity maximum iterations must be positive")
        self.maximum_iterations = maximum_iterations

    @staticmethod
    def _warm_start(values):
        if values is None:
            return {}
        if isinstance(values, dict):
            rows = values.items()
        else:
            rows = values
        result = {}
        for capacity_id, value in rows:
            value = _finite_nonnegative(
                value, "warm-start dual")
            if capacity_id in result:
                raise ValueError(
                    "warm-start capacity IDs must be unique")
            result[str(capacity_id)] = value
        return result

    @staticmethod
    def _response(record, dual, converged):
        if dual <= 0.0:
            return "none"
        if not converged:
            return "exploration_guidance_only"
        if record.kind == CapacityKind.MEASURED:
            return "structural_bottleneck_candidate"
        if record.kind == CapacityKind.ALLOCATED:
            return "request_arbiter_reconsideration"
        return "numerical_shaping_only"

    @staticmethod
    def _autocorrelation(previous, current):
        if not previous or not current:
            return None
        keys = tuple(sorted(set(previous) | set(current)))
        left = tuple(previous.get(key, 0.0) for key in keys)
        right = tuple(current.get(key, 0.0) for key in keys)
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return max(-1.0, min(1.0, sum(
            a * b for a, b in zip(left, right))
            / (left_norm * right_norm)))

    def solve(
            self, requests, capacities,
            tolerance=1e-9, warm_start=None):
        requests = tuple(requests)
        capacities = tuple(capacities)
        if any(not isinstance(row, CommodityFlowRequest)
               for row in requests):
            raise TypeError(
                "capacity solver requires commodity requests")
        request_ids = [row.commodity_id for row in requests]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError(
                "commodity IDs must be unique")
        if any(not isinstance(row, CapacityRecord)
               for row in capacities):
            raise TypeError(
                "capacity solver requires capacity records")
        capacity_keys = [
            (row.edge_or_node_id, row.resource)
            for row in capacities]
        if len(capacity_keys) != len(set(capacity_keys)):
            raise ValueError(
                "capacity target-resource pairs must be unique")
        tolerance = float(tolerance)
        if not math.isfinite(tolerance) or tolerance <= 0.0:
            raise ValueError(
                "capacity tolerance must be positive")
        previous = self._warm_start(warm_start)

        allocated = [
            [float(value) for value in row.requested_flow]
            for row in requests]
        locations = {}
        used_targets = set()
        for request_index, request in enumerate(requests):
            for edge_index, edge_id in enumerate(request.edge_ids):
                locations.setdefault(
                    (edge_id, request.resource), []).append((
                        request_index, edge_index,
                        float(request.requested_flow[edge_index]),
                        float(request.objective_weight)))

        dual_rows = []
        iterations = 0
        dual_residual = 0.0
        primal_residual = 0.0
        complementarity_gap = 0.0
        all_converged = True
        current_duals = {}
        for record in capacities:
            if record.kind == CapacityKind.NONE:
                continue
            key = (record.edge_or_node_id, record.resource)
            entries = locations.get(key, ())
            if not entries:
                continue
            used_targets.add(key)
            capacity = float(record.value)

            def demand(dual):
                return sum(max(
                    0.0,
                    abs(raw) - dual / weight)
                    for _, _, raw, weight in entries)

            unconstrained = demand(0.0)
            if unconstrained <= capacity + tolerance:
                dual = 0.0
                width = 0.0
                edge_iterations = 0
                converged = True
            else:
                low = 0.0
                high = max(
                    weight * abs(raw)
                    for _, _, raw, weight in entries)
                prior = min(
                    high, previous.get(
                        record.capacity_id, 0.0))
                if prior > 0.0:
                    if demand(prior) > capacity:
                        low = prior
                    else:
                        high = prior
                converged = False
                edge_iterations = 0
                for edge_iterations in range(
                        1, self.maximum_iterations + 1):
                    midpoint = 0.5 * (low + high)
                    if demand(midpoint) > capacity:
                        low = midpoint
                    else:
                        high = midpoint
                    width = high - low
                    if width <= tolerance:
                        converged = True
                        break
                dual = high
                width = high - low
            total = 0.0
            for (
                    request_index, edge_index,
                    raw, weight) in entries:
                magnitude = max(
                    0.0, abs(raw) - dual / weight)
                value = math.copysign(magnitude, raw)
                allocated[request_index][edge_index] = value
                total += magnitude
            edge_primal = max(0.0, total - capacity)
            edge_gap = dual * abs(capacity - total)
            primal_residual = max(
                primal_residual, edge_primal)
            dual_residual = max(
                dual_residual, width)
            complementarity_gap = max(
                complementarity_gap, edge_gap)
            iterations = max(iterations, edge_iterations)
            edge_converged = (
                converged
                and edge_primal <= tolerance
                and width <= tolerance
                and edge_gap <= tolerance
                    * max(1.0, dual, capacity))
            all_converged = all_converged and edge_converged
            current_duals[record.capacity_id] = dual
            response = self._response(
                record, dual, edge_converged)
            dual_rows.append(CapacityDual(
                capacity_id=record.capacity_id,
                edge_or_node_id=record.edge_or_node_id,
                resource=record.resource,
                value=dual,
                kind=record.kind,
                provenance_id=record.provenance_id,
                converged=edge_converged,
                economic_price=(
                    edge_converged
                    and dual > tolerance
                    and record.kind == CapacityKind.MEASURED),
                permitted_response=response))

        prior_active = frozenset(
            key for key, value in previous.items()
            if value > tolerance)
        current_active = frozenset(
            key for key, value in current_duals.items()
            if value > tolerance)
        allocations = tuple(
            CommodityFlowAllocation(
                commodity_id=request.commodity_id,
                resource=request.resource,
                edge_ids=request.edge_ids,
                allocated_flow=tuple(values),
                requested_flow=tuple(
                    float(value)
                    for value in request.requested_flow))
            for request, values in zip(requests, allocated))
        unused = tuple(sorted(
            row.capacity_id for row in capacities
            if row.kind != CapacityKind.NONE
            and (row.edge_or_node_id, row.resource)
            not in used_targets))
        return MultiCommodityResult(
            allocations=allocations,
            capacity_duals=tuple(dual_rows),
            primal_residual=primal_residual,
            dual_residual=dual_residual,
            complementarity_gap=complementarity_gap,
            active_set_changes=len(
                prior_active ^ current_active),
            dual_autocorrelation=self._autocorrelation(
                previous, current_duals),
            converged=all_converged,
            iterations=iterations,
            health=(
                "healthy" if all_converged
                else "unhealthy:nonconverged"),
            unused_capacity_ids=unused,
            solver_identity=self.SOLVER_IDENTITY)
