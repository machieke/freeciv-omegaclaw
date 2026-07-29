"""Forward reachability, backward usefulness, and bridge estimators."""

import heapq
import math
import random
from dataclasses import dataclass
from typing import Protocol

from ..events.schema import structural_hash
from .model import (
    FlowNodeKind,
    FlowProcess,
    FlowView,
)
from .topology import FlowTopologyIndex


POTENTIAL_PROCESS_SEMANTICS = frozenset((
    "current-steered-behavior",
    "fixed-reference-process",
    "holdout-calibrated-approximation",
    "learned-process-predictor",
))


def _positive_finite(value, name):
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(
            "{} must be finite and positive".format(name))
    return value


def _nonnegative_finite(value, name):
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(
            "{} must be finite and non-negative".format(name))
    return value


def _unit_interval(value, name):
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(
            "{} must be in [0,1]".format(name))
    return value


@dataclass(frozen=True)
class PotentialEstimate:
    goal_id: str
    node_id: str
    forward_factor: float
    backward_factor: float
    log_forward: float
    log_backward: float
    bridge_height: float
    forward_uncertainty: float
    backward_uncertainty: float
    estimator_policy: str
    effective_sample_size: object
    clipped_weight_fraction: object
    estimator_id: str
    process_semantics: str
    topology_generation: int

    def __post_init__(self):
        if not isinstance(self.goal_id, str) or not self.goal_id:
            raise ValueError(
                "potential goal ID is required")
        if not isinstance(self.node_id, str) or not self.node_id:
            raise ValueError(
                "potential node ID is required")
        forward = _positive_finite(
            self.forward_factor, "forward factor")
        backward = _positive_finite(
            self.backward_factor, "backward factor")
        for name in (
                "log_forward", "log_backward",
                "bridge_height"):
            if not math.isfinite(float(getattr(self, name))):
                raise ValueError(
                    "{} must be finite".format(name))
        if abs(float(self.log_forward) - math.log(forward)) > 1e-9:
            raise ValueError(
                "log forward must match forward factor")
        if abs(float(self.log_backward) - math.log(backward)) > 1e-9:
            raise ValueError(
                "log backward must match backward factor")
        if abs(
                float(self.bridge_height)
                - float(self.log_forward)
                - float(self.log_backward)) > 1e-9:
            raise ValueError(
                "bridge height must equal log f plus log g")
        _nonnegative_finite(
            self.forward_uncertainty,
            "forward uncertainty")
        _nonnegative_finite(
            self.backward_uncertainty,
            "backward uncertainty")
        if self.effective_sample_size is not None:
            _nonnegative_finite(
                self.effective_sample_size,
                "effective sample size")
        if self.clipped_weight_fraction is not None:
            _unit_interval(
                self.clipped_weight_fraction,
                "clipped weight fraction")
        if (not isinstance(self.estimator_policy, str)
                or not self.estimator_policy):
            raise ValueError(
                "potential estimator policy is required")
        if (not isinstance(self.estimator_id, str)
                or not self.estimator_id):
            raise ValueError(
                "potential estimator ID is required")
        if self.process_semantics not in (
                POTENTIAL_PROCESS_SEMANTICS):
            raise ValueError(
                "unknown potential process semantics")
        if (isinstance(self.topology_generation, bool)
                or not isinstance(self.topology_generation, int)
                or self.topology_generation < 0):
            raise ValueError(
                "potential topology generation must be non-negative")

    @property
    def bridge_factor(self):
        return (
            float(self.forward_factor)
            * float(self.backward_factor))

    def to_dict(self):
        return {
            "backward_factor": float(self.backward_factor),
            "backward_uncertainty": float(
                self.backward_uncertainty),
            "bridge_factor": self.bridge_factor,
            "bridge_height": float(self.bridge_height),
            "clipped_weight_fraction": (
                None if self.clipped_weight_fraction is None
                else float(self.clipped_weight_fraction)),
            "effective_sample_size": (
                None if self.effective_sample_size is None
                else float(self.effective_sample_size)),
            "estimator_id": self.estimator_id,
            "estimator_policy": self.estimator_policy,
            "forward_factor": float(self.forward_factor),
            "forward_uncertainty": float(
                self.forward_uncertainty),
            "goal_id": self.goal_id,
            "log_backward": float(self.log_backward),
            "log_forward": float(self.log_forward),
            "node_id": self.node_id,
            "process_semantics": self.process_semantics,
            "topology_generation": self.topology_generation,
        }


@dataclass(frozen=True)
class PotentialBudget:
    max_iterations: int = 64
    max_probe_steps: int = 32
    sample_count: int = 512
    minimum_factor: float = 1e-12
    maximum_factor: float = 1.0
    hop_retention: float = 0.95
    convergence_tolerance: float = 1e-12

    def __post_init__(self):
        for name in (
                "max_iterations", "max_probe_steps",
                "sample_count"):
            value = getattr(self, name)
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 1):
                raise ValueError(
                    "{} must be a positive integer".format(name))
        minimum = _positive_finite(
            self.minimum_factor, "minimum factor")
        maximum = _positive_finite(
            self.maximum_factor, "maximum factor")
        if minimum >= maximum:
            raise ValueError(
                "minimum factor must be below maximum factor")
        _unit_interval(
            self.hop_retention, "hop retention")
        if self.hop_retention == 0.0:
            raise ValueError("hop retention must be positive")
        _positive_finite(
            self.convergence_tolerance,
            "convergence tolerance")

    def to_dict(self):
        return {
            "convergence_tolerance": (
                self.convergence_tolerance),
            "hop_retention": self.hop_retention,
            "max_iterations": self.max_iterations,
            "max_probe_steps": self.max_probe_steps,
            "maximum_factor": self.maximum_factor,
            "minimum_factor": self.minimum_factor,
            "sample_count": self.sample_count,
        }


class PotentialEstimator(Protocol):
    def estimate(self, view, goal_bundle, budget=None):
        ...


def _goals(view, goal_bundle):
    goals = tuple(sorted(set(str(value) for value in goal_bundle)))
    if not goals or any(not value for value in goals):
        raise ValueError(
            "at least one potential goal is required")
    available = dict(
        (row.provenance_ids[0], row.stable_id)
        for row in view.nodes
        if (row.kind == FlowNodeKind.BACKWARD_BOUNDARY
            and row.provenance_ids))
    missing = tuple(
        value for value in goals
        if value not in available)
    if missing:
        raise ValueError(
            "potential goals lack backward boundaries: {}".format(
                ", ".join(missing)))
    return goals, available


def _bounded_factor(value, budget):
    return min(
        float(budget.maximum_factor),
        max(float(budget.minimum_factor), float(value)))


def _enforce_forward_constraints(view, factors, budget):
    """Cap sampled/path factors by explicit dependency and AND structure."""
    index = FlowTopologyIndex(view)
    values = dict(factors)
    for _ in range(budget.max_iterations):
        following = dict(values)
        maximum_change = 0.0
        for node in view.nodes:
            if node.kind == FlowNodeKind.FORWARD_BOUNDARY:
                continue
            if node.kind == FlowNodeKind.REQUIREMENT_SET:
                premises = tuple(
                    edge.target_node_id
                    for edge in index.outgoing(
                        node.stable_id,
                        FlowProcess.BACKWARD_DEMAND))
                if premises:
                    cap = _bounded_factor(
                        min(values[value]
                            for value in premises)
                        * budget.hop_retention,
                        budget)
                else:
                    cap = float(budget.minimum_factor)
            else:
                incoming = index.incoming(
                    node.stable_id,
                    FlowProcess.PROBE_FORWARD)
                if not incoming:
                    continue
                cap = max(
                    _bounded_factor(
                        values[edge.source_node_id]
                        * min(1.0, edge.control_weight)
                        * budget.hop_retention,
                        budget)
                    for edge in incoming)
            following[node.stable_id] = min(
                following[node.stable_id], cap)
            maximum_change = max(
                maximum_change,
                abs(
                    following[node.stable_id]
                    - values[node.stable_id]))
        values = following
        if maximum_change <= budget.convergence_tolerance:
            break
    return values


def _estimate_rows(
        view, goals, forward, backwards,
        forward_uncertainty, backward_uncertainties,
        estimator_policy, estimator_id,
        process_semantics, effective_sample_size=None,
        clipped_weight_fraction=None):
    rows = []
    for goal_id in goals:
        backward = backwards[goal_id]
        backward_uncertainty = backward_uncertainties[goal_id]
        for node in sorted(
                view.nodes, key=lambda row: row.stable_id):
            f = float(forward[node.stable_id])
            g = float(backward[node.stable_id])
            log_f = math.log(f)
            log_g = math.log(g)
            rows.append(PotentialEstimate(
                goal_id=goal_id,
                node_id=node.stable_id,
                forward_factor=f,
                backward_factor=g,
                log_forward=log_f,
                log_backward=log_g,
                bridge_height=log_f + log_g,
                forward_uncertainty=float(
                    forward_uncertainty[node.stable_id]),
                backward_uncertainty=float(
                    backward_uncertainty[node.stable_id]),
                estimator_policy=estimator_policy,
                effective_sample_size=effective_sample_size,
                clipped_weight_fraction=(
                    clipped_weight_fraction),
                estimator_id=estimator_id,
                process_semantics=process_semantics,
                topology_generation=(
                    view.topology_generation)))
    return tuple(rows)


class DeterministicMessagePotentialEstimator:
    """Bounded max-product messages with AND requirement bottlenecks."""

    ESTIMATOR_ID = "bounded-deterministic-message/1.0"

    def __init__(
            self, process_semantics="fixed-reference-process"):
        if process_semantics not in POTENTIAL_PROCESS_SEMANTICS:
            raise ValueError(
                "unknown potential process semantics")
        self.process_semantics = process_semantics

    @staticmethod
    def _forward(view, index, budget):
        factors = dict(
            (row.stable_id, float(budget.minimum_factor))
            for row in view.nodes)
        node_kinds = dict(
            (row.stable_id, row.kind)
            for row in view.nodes)
        for node in view.nodes:
            if node.kind == FlowNodeKind.FORWARD_BOUNDARY:
                factors[node.stable_id] = float(
                    budget.maximum_factor)
        requirement_premises = {}
        for node in view.nodes:
            if node.kind != FlowNodeKind.REQUIREMENT_SET:
                continue
            requirement_premises[node.stable_id] = tuple(
                edge.target_node_id
                for edge in index.outgoing(
                    node.stable_id,
                    FlowProcess.BACKWARD_DEMAND))
        for _ in range(budget.max_iterations):
            following = dict(factors)
            for node in view.nodes:
                if node.kind != FlowNodeKind.REQUIREMENT_SET:
                    continue
                premises = requirement_premises.get(
                    node.stable_id, ())
                if premises:
                    following[node.stable_id] = max(
                        following[node.stable_id],
                        _bounded_factor(
                            min(factors[value]
                                for value in premises)
                            * budget.hop_retention,
                            budget))
            for edge in view.legal_edges(
                    FlowProcess.PROBE_FORWARD):
                if node_kinds[edge.target_node_id] == (
                        FlowNodeKind.REQUIREMENT_SET):
                    continue
                source = factors[edge.source_node_id]
                proposed = _bounded_factor(
                    source
                    * min(1.0, edge.control_weight)
                    * budget.hop_retention,
                    budget)
                following[edge.target_node_id] = max(
                    following[edge.target_node_id],
                    proposed)
            difference = max(
                abs(following[key] - factors[key])
                for key in factors)
            factors = following
            if difference <= budget.convergence_tolerance:
                break
        return _enforce_forward_constraints(
            view, factors, budget)

    @staticmethod
    def _backward(view, index, goal_node_id, budget):
        factors = dict(
            (row.stable_id, float(budget.minimum_factor))
            for row in view.nodes)
        factors[goal_node_id] = float(
            budget.maximum_factor)
        for _ in range(budget.max_iterations):
            following = dict(factors)
            for edge in view.legal_edges(
                    FlowProcess.PROBE_BACKWARD):
                source = factors[edge.source_node_id]
                proposed = _bounded_factor(
                    source
                    * min(1.0, edge.control_weight)
                    * budget.hop_retention,
                    budget)
                following[edge.target_node_id] = max(
                    following[edge.target_node_id],
                    proposed)
            difference = max(
                abs(following[key] - factors[key])
                for key in factors)
            factors = following
            if difference <= budget.convergence_tolerance:
                break
        return factors

    def estimate(self, view, goal_bundle, budget=None):
        if not isinstance(view, FlowView):
            raise TypeError(
                "potential estimator requires FlowView")
        budget = (
            budget if budget is not None else PotentialBudget())
        if not isinstance(budget, PotentialBudget):
            raise TypeError(
                "potential budget must be PotentialBudget")
        goals, goal_nodes = _goals(view, goal_bundle)
        index = FlowTopologyIndex(view)
        forward = self._forward(view, index, budget)
        backwards = dict(
            (goal_id, self._backward(
                view, index, goal_nodes[goal_id], budget))
            for goal_id in goals)
        forward_uncertainty = dict(
            (key, 1.0 - value / budget.maximum_factor)
            for key, value in forward.items())
        backward_uncertainties = dict(
            (goal_id, dict(
                (key, 1.0 - value / budget.maximum_factor)
                for key, value in values.items()))
            for goal_id, values in backwards.items())
        policy = (
            "bounded max-product messages; requirement sets use "
            "the least reachable declared premise")
        return _estimate_rows(
            view, goals, forward, backwards,
            forward_uncertainty, backward_uncertainties,
            policy, self.ESTIMATOR_ID,
            self.process_semantics)


class ShortestMeetPotentialEstimator:
    """Minimum-cost reachability/usefulness heuristic on explicit edges."""

    ESTIMATOR_ID = "shortest-meet/1.0"

    def __init__(
            self, process_semantics="fixed-reference-process"):
        if process_semantics not in POTENTIAL_PROCESS_SEMANTICS:
            raise ValueError(
                "unknown potential process semantics")
        self.process_semantics = process_semantics

    @staticmethod
    def _distances(view, starts, process, budget):
        index = FlowTopologyIndex(view)
        distances = dict(
            (row.stable_id, float("inf"))
            for row in view.nodes)
        frontier = []
        for stable_id in sorted(starts):
            distances[stable_id] = 0.0
            heapq.heappush(frontier, (0.0, stable_id))
        while frontier:
            distance, stable_id = heapq.heappop(frontier)
            if distance != distances[stable_id]:
                continue
            for edge in index.outgoing(stable_id, process):
                retained = max(
                    budget.minimum_factor,
                    min(1.0, edge.control_weight)
                    * budget.hop_retention)
                proposed = distance - math.log(retained)
                if proposed < distances[edge.target_node_id]:
                    distances[edge.target_node_id] = proposed
                    heapq.heappush(
                        frontier,
                        (proposed, edge.target_node_id))
        return distances

    @staticmethod
    def _factors(distances, budget):
        return dict(
            (key, _bounded_factor(
                budget.minimum_factor
                if not math.isfinite(value)
                else math.exp(-value),
                budget))
            for key, value in distances.items())

    def estimate(self, view, goal_bundle, budget=None):
        if not isinstance(view, FlowView):
            raise TypeError(
                "potential estimator requires FlowView")
        budget = (
            budget if budget is not None else PotentialBudget())
        if not isinstance(budget, PotentialBudget):
            raise TypeError(
                "potential budget must be PotentialBudget")
        goals, goal_nodes = _goals(view, goal_bundle)
        forward_starts = tuple(
            row.stable_id for row in view.nodes
            if row.kind == FlowNodeKind.FORWARD_BOUNDARY)
        forward = self._factors(
            self._distances(
                view, forward_starts,
                FlowProcess.PROBE_FORWARD, budget),
            budget)
        forward = _enforce_forward_constraints(
            view, forward, budget)
        backwards = dict(
            (goal_id, self._factors(
                self._distances(
                    view, (goal_nodes[goal_id],),
                    FlowProcess.PROBE_BACKWARD,
                    budget),
                budget))
            for goal_id in goals)
        forward_uncertainty = dict(
            (key, float(value <= budget.minimum_factor))
            for key, value in forward.items())
        backward_uncertainties = dict(
            (goal_id, dict(
                (key, float(value <= budget.minimum_factor))
                for key, value in values.items()))
            for goal_id, values in backwards.items())
        return _estimate_rows(
            view, goals, forward, backwards,
            forward_uncertainty, backward_uncertainties,
            "minimum multiplicative path cost with explicit legalities",
            self.ESTIMATOR_ID, self.process_semantics)


class MonteCarloMeetPotentialEstimator:
    """Fixed-seed visit-frequency estimator for reference processes."""

    ESTIMATOR_ID = "monte-carlo-meet/1.0"

    def __init__(
            self, seed=1729,
            process_semantics="fixed-reference-process"):
        if (isinstance(seed, bool)
                or not isinstance(seed, int)):
            raise ValueError(
                "Monte Carlo seed must be an integer")
        if process_semantics not in POTENTIAL_PROCESS_SEMANTICS:
            raise ValueError(
                "unknown potential process semantics")
        self.seed = seed
        self.process_semantics = process_semantics

    @staticmethod
    def _walk_counts(
            view, starts, process, budget, rng):
        index = FlowTopologyIndex(view)
        counts = dict(
            (row.stable_id, 0) for row in view.nodes)
        start_values = tuple(sorted(starts))
        for sample in range(budget.sample_count):
            current = start_values[
                sample % len(start_values)]
            visited = {current}
            for _ in range(budget.max_probe_steps):
                options = index.outgoing(current, process)
                if not options:
                    break
                weights = tuple(
                    max(
                        budget.minimum_factor,
                        float(edge.control_weight))
                    for edge in options)
                draw = rng.random() * sum(weights)
                selected = options[-1]
                cumulative = 0.0
                for edge, weight in zip(options, weights):
                    cumulative += weight
                    if draw <= cumulative:
                        selected = edge
                        break
                current = selected.target_node_id
                visited.add(current)
            for stable_id in visited:
                counts[stable_id] += 1
        return counts

    @staticmethod
    def _factors_and_uncertainty(counts, budget):
        factors = {}
        uncertainty = {}
        count = float(budget.sample_count)
        for stable_id, visits in counts.items():
            probability = visits / count
            factors[stable_id] = _bounded_factor(
                probability, budget)
            uncertainty[stable_id] = math.sqrt(
                probability * (1.0 - probability)
                / count)
        return factors, uncertainty

    def estimate(self, view, goal_bundle, budget=None):
        if not isinstance(view, FlowView):
            raise TypeError(
                "potential estimator requires FlowView")
        budget = (
            budget if budget is not None else PotentialBudget())
        if not isinstance(budget, PotentialBudget):
            raise TypeError(
                "potential budget must be PotentialBudget")
        goals, goal_nodes = _goals(view, goal_bundle)
        seed_material = {
            "budget": budget.to_dict(),
            "seed": self.seed,
            "view_hash": view.to_dict()["view_hash"],
        }
        base_seed = int(
            structural_hash(seed_material)[:16], 16)
        forward_starts = tuple(
            row.stable_id for row in view.nodes
            if row.kind == FlowNodeKind.FORWARD_BOUNDARY)
        forward, forward_uncertainty = (
            self._factors_and_uncertainty(
                self._walk_counts(
                    view, forward_starts,
                    FlowProcess.PROBE_FORWARD,
                    budget, random.Random(base_seed)),
                budget))
        forward = _enforce_forward_constraints(
            view, forward, budget)
        forward_uncertainty = dict(
            (key, max(
                forward_uncertainty[key],
                1.0 - value / budget.maximum_factor))
            for key, value in forward.items())
        backwards = {}
        backward_uncertainties = {}
        for index, goal_id in enumerate(goals):
            values, uncertainty = (
                self._factors_and_uncertainty(
                    self._walk_counts(
                        view, (goal_nodes[goal_id],),
                        FlowProcess.PROBE_BACKWARD,
                        budget,
                        random.Random(base_seed + index + 1)),
                    budget))
            backwards[goal_id] = values
            backward_uncertainties[goal_id] = uncertainty
        return _estimate_rows(
            view, goals, forward, backwards,
            forward_uncertainty, backward_uncertainties,
            "fixed-seed reference-kernel visit frequency",
            "{}:seed={}".format(
                self.ESTIMATOR_ID, self.seed),
            self.process_semantics,
            effective_sample_size=float(
                budget.sample_count),
            clipped_weight_fraction=0.0)
