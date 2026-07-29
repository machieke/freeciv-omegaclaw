"""Corrected forward/backward probes with explicit sampling health."""

import math
import random
from dataclasses import dataclass

from ..events.schema import structural_hash
from .model import FlowProcess, FlowView
from .topology import FlowTopologyIndex


def _finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("{} must be finite".format(name))
    return value


def _nonnegative(value, name):
    value = _finite(value, name)
    if value < 0.0:
        raise ValueError(
            "{} must be non-negative".format(name))
    return value


def _unit_interval(value, name):
    value = _finite(value, name)
    if not 0.0 <= value <= 1.0:
        raise ValueError(
            "{} must be in [0,1]".format(name))
    return value


@dataclass(frozen=True)
class ProbeNodeFeatures:
    node_id: str
    local_advantage: float = 0.0
    cost: float = 0.0
    congestion: float = 0.0
    risk: float = 0.0
    current_following: float = 0.0

    def __post_init__(self):
        if not isinstance(self.node_id, str) or not self.node_id:
            raise ValueError(
                "probe feature node ID is required")
        _finite(
            self.local_advantage, "probe local advantage")
        _nonnegative(self.cost, "probe cost")
        _nonnegative(self.congestion, "probe congestion")
        _nonnegative(self.risk, "probe risk")
        _finite(
            self.current_following,
            "probe current following")

    def to_dict(self):
        return {
            "congestion": float(self.congestion),
            "cost": float(self.cost),
            "current_following": float(
                self.current_following),
            "local_advantage": float(
                self.local_advantage),
            "node_id": self.node_id,
            "risk": float(self.risk),
        }


@dataclass(frozen=True)
class ProbeConfig:
    mode: str = "two_stream"
    path_count: int = 128
    max_steps: int = 16
    reference_fraction: float = 0.2
    temperature: float = 1.0
    advantage_gain: float = 1.0
    cost_gain: float = 1.0
    congestion_gain: float = 1.0
    risk_gain: float = 1.0
    current_following_gain: float = 0.0
    maximum_importance_weight: float = 10.0
    minimum_ess_fraction: float = 0.2
    maximum_clipped_fraction: float = 0.25
    minimum_path_diversity: float = 0.1
    seed: int = 1729

    def __post_init__(self):
        if self.mode not in ("importance", "two_stream"):
            raise ValueError("unknown probe correction mode")
        for name in ("path_count", "max_steps"):
            value = getattr(self, name)
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 1):
                raise ValueError(
                    "{} must be a positive integer".format(name))
        _unit_interval(
            self.reference_fraction,
            "probe reference fraction")
        if (self.mode == "two_stream"
                and self.reference_fraction <= 0.0):
            raise ValueError(
                "two-stream probes require reference paths")
        if _nonnegative(
                self.temperature,
                "probe temperature") <= 0.0:
            raise ValueError(
                "probe temperature must be positive")
        for name in (
                "advantage_gain", "cost_gain",
                "congestion_gain", "risk_gain",
                "current_following_gain"):
            _nonnegative(
                getattr(self, name),
                name.replace("_", " "))
        if _nonnegative(
                self.maximum_importance_weight,
                "maximum importance weight") < 1.0:
            raise ValueError(
                "maximum importance weight must be >= 1")
        _unit_interval(
            self.minimum_ess_fraction,
            "minimum ESS fraction")
        _unit_interval(
            self.maximum_clipped_fraction,
            "maximum clipped fraction")
        _unit_interval(
            self.minimum_path_diversity,
            "minimum path diversity")
        if (isinstance(self.seed, bool)
                or not isinstance(self.seed, int)):
            raise ValueError("probe seed must be an integer")

    def to_dict(self):
        return {
            "advantage_gain": self.advantage_gain,
            "congestion_gain": self.congestion_gain,
            "cost_gain": self.cost_gain,
            "current_following_gain": (
                self.current_following_gain),
            "max_steps": self.max_steps,
            "maximum_clipped_fraction": (
                self.maximum_clipped_fraction),
            "maximum_importance_weight": (
                self.maximum_importance_weight),
            "minimum_ess_fraction": (
                self.minimum_ess_fraction),
            "minimum_path_diversity": (
                self.minimum_path_diversity),
            "mode": self.mode,
            "path_count": self.path_count,
            "reference_fraction": self.reference_fraction,
            "risk_gain": self.risk_gain,
            "seed": self.seed,
            "temperature": self.temperature,
        }


@dataclass(frozen=True)
class ProbePath:
    path_id: str
    side: str
    start_node_id: str
    node_ids: tuple
    edge_ids: tuple
    total_cost: float
    met_opposite_frontier: bool
    meet_node_id: object
    novelty: float
    evidence_risk: float
    reliability: float
    behavior_log_probability: float
    reference_log_probability: float
    importance_weight: float
    topology_generation: int
    rng_substream: int
    sampling_stream: str
    clipped: bool = False

    def __post_init__(self):
        if not isinstance(self.path_id, str) or not self.path_id:
            raise ValueError("probe path ID is required")
        if self.side not in ("forward", "backward"):
            raise ValueError("probe side must be forward or backward")
        if (not isinstance(self.start_node_id, str)
                or not self.start_node_id):
            raise ValueError(
                "probe start node ID is required")
        if (not isinstance(self.node_ids, tuple)
                or not self.node_ids
                or self.node_ids[0] != self.start_node_id):
            raise ValueError(
                "probe node path must begin at start node")
        if len(self.edge_ids) != len(self.node_ids) - 1:
            raise ValueError(
                "probe edge and node path lengths disagree")
        _nonnegative(self.total_cost, "probe total cost")
        if not isinstance(self.met_opposite_frontier, bool):
            raise TypeError(
                "probe meet status must be boolean")
        if self.met_opposite_frontier != (
                self.meet_node_id is not None):
            raise ValueError(
                "probe meet node must match meet status")
        _unit_interval(self.novelty, "probe novelty")
        _nonnegative(
            self.evidence_risk, "probe evidence risk")
        _unit_interval(
            self.reliability, "probe reliability")
        _finite(
            self.behavior_log_probability,
            "probe behavior log probability")
        _finite(
            self.reference_log_probability,
            "probe reference log probability")
        _nonnegative(
            self.importance_weight,
            "probe importance weight")
        if (isinstance(self.topology_generation, bool)
                or not isinstance(self.topology_generation, int)
                or self.topology_generation < 0):
            raise ValueError(
                "probe topology generation must be non-negative")
        if (isinstance(self.rng_substream, bool)
                or not isinstance(self.rng_substream, int)
                or self.rng_substream < 0):
            raise ValueError(
                "probe RNG substream must be non-negative")
        if self.sampling_stream not in (
                "behavior", "reference"):
            raise ValueError(
                "unknown probe sampling stream")
        if not isinstance(self.clipped, bool):
            raise TypeError(
                "probe clipped status must be boolean")

    def to_dict(self):
        return {
            "behavior_log_probability": float(
                self.behavior_log_probability),
            "clipped": self.clipped,
            "edge_ids": list(self.edge_ids),
            "evidence_risk": float(self.evidence_risk),
            "importance_weight": float(
                self.importance_weight),
            "meet_node_id": self.meet_node_id,
            "met_opposite_frontier": (
                self.met_opposite_frontier),
            "node_ids": list(self.node_ids),
            "novelty": float(self.novelty),
            "path_id": self.path_id,
            "reference_log_probability": float(
                self.reference_log_probability),
            "reliability": float(self.reliability),
            "rng_substream": self.rng_substream,
            "sampling_stream": self.sampling_stream,
            "side": self.side,
            "start_node_id": self.start_node_id,
            "topology_generation": self.topology_generation,
            "total_cost": float(self.total_cost),
        }


@dataclass(frozen=True)
class ProbeHealth:
    healthy: bool
    reasons: tuple
    effective_sample_size: float
    effective_sample_fraction: float
    clipped_weight_fraction: float
    path_diversity: float
    reference_path_count: int
    recommended_fallback: object
    recovery_actions: tuple

    def __post_init__(self):
        if not isinstance(self.healthy, bool):
            raise TypeError(
                "probe health must be boolean")
        _nonnegative(
            self.effective_sample_size,
            "probe effective sample size")
        _unit_interval(
            self.effective_sample_fraction,
            "probe effective sample fraction")
        _unit_interval(
            self.clipped_weight_fraction,
            "probe clipped weight fraction")
        _unit_interval(
            self.path_diversity,
            "probe path diversity")
        if (isinstance(self.reference_path_count, bool)
                or not isinstance(
                    self.reference_path_count, int)
                or self.reference_path_count < 0):
            raise ValueError(
                "reference path count must be non-negative")
        if self.healthy and (
                self.reasons
                or self.recommended_fallback is not None):
            raise ValueError(
                "healthy probes cannot declare fallback")
        if not self.healthy and not self.reasons:
            raise ValueError(
                "unhealthy probes require reasons")

    def to_dict(self):
        return {
            "clipped_weight_fraction": float(
                self.clipped_weight_fraction),
            "effective_sample_fraction": float(
                self.effective_sample_fraction),
            "effective_sample_size": float(
                self.effective_sample_size),
            "healthy": self.healthy,
            "path_diversity": float(self.path_diversity),
            "reasons": list(self.reasons),
            "recommended_fallback": (
                self.recommended_fallback),
            "recovery_actions": list(
                self.recovery_actions),
            "reference_path_count": (
                self.reference_path_count),
        }


@dataclass(frozen=True)
class ProbeBatch:
    side: str
    paths: tuple
    health: ProbeHealth
    config: ProbeConfig
    estimator_id: str
    topology_generation: int

    def __post_init__(self):
        if self.side not in ("forward", "backward"):
            raise ValueError("unknown probe batch side")
        if any(not isinstance(row, ProbePath)
               for row in self.paths):
            raise TypeError(
                "probe batch paths must contain ProbePath")
        if not isinstance(self.health, ProbeHealth):
            raise TypeError(
                "probe batch health must be ProbeHealth")
        if not isinstance(self.config, ProbeConfig):
            raise TypeError(
                "probe batch config must be ProbeConfig")

    def to_dict(self):
        material = {
            "config": self.config.to_dict(),
            "estimator_id": self.estimator_id,
            "health": self.health.to_dict(),
            "paths": [row.to_dict() for row in self.paths],
            "schema_version": "1.0",
            "side": self.side,
            "topology_generation": self.topology_generation,
        }
        material["artifact_hash"] = structural_hash(material)
        return material


class CorrectedProbeEstimator:
    """Sample legal paths and expose behavior/reference correction."""

    ESTIMATOR_ID = "corrected-query-local-probe/1.0"

    def __init__(self, config=None):
        self.config = (
            config if config is not None else ProbeConfig())
        if not isinstance(self.config, ProbeConfig):
            raise TypeError(
                "probe config must be ProbeConfig")

    @staticmethod
    def _normalized(weights):
        total = sum(weights)
        if total <= 0.0:
            raise ValueError(
                "probe transition weights must be positive")
        return tuple(value / total for value in weights)

    @staticmethod
    def _draw(options, probabilities, rng):
        draw = rng.random()
        cumulative = 0.0
        for edge, probability in zip(
                options, probabilities):
            cumulative += probability
            if draw <= cumulative:
                return edge, probability
        return options[-1], probabilities[-1]

    def _kernels(self, options, feature_by_node):
        reference_weights = tuple(
            max(1e-12, float(edge.control_weight))
            for edge in options)
        reference = self._normalized(reference_weights)
        logits = []
        for edge, reference_weight in zip(
                options, reference_weights):
            features = feature_by_node.get(
                edge.target_node_id,
                ProbeNodeFeatures(edge.target_node_id))
            score = (
                self.config.advantage_gain
                * features.local_advantage
                - self.config.cost_gain * features.cost
                - self.config.congestion_gain
                * features.congestion
                - self.config.risk_gain * features.risk
                + self.config.current_following_gain
                * features.current_following)
            logits.append(
                math.log(reference_weight)
                + score / self.config.temperature)
        maximum = max(logits)
        behavior = self._normalized(tuple(
            math.exp(value - maximum)
            for value in logits))
        return behavior, reference

    def _path(
            self, view, index, side, start,
            opposite, feature_by_node, rng,
            substream, sampling_stream, endpoint_counts):
        process = (
            FlowProcess.PROBE_FORWARD
            if side == "forward"
            else FlowProcess.PROBE_BACKWARD)
        node_ids = [start]
        edge_ids = []
        behavior_log = 0.0
        reference_log = 0.0
        total_cost = 0.0
        evidence_risk = 0.0
        reliability = 1.0
        meet_node_id = (
            start if start in opposite else None)
        current = start
        for _ in range(self.config.max_steps):
            if meet_node_id is not None:
                break
            options = index.outgoing(current, process)
            if not options:
                break
            behavior, reference = self._kernels(
                options, feature_by_node)
            sampling = (
                reference if sampling_stream == "reference"
                else behavior)
            selected, sampled_probability = self._draw(
                options, sampling, rng)
            selected_index = options.index(selected)
            behavior_probability = (
                sampled_probability
                if sampling_stream == "reference"
                else behavior[selected_index])
            reference_probability = reference[selected_index]
            behavior_log += math.log(
                max(1e-300, behavior_probability))
            reference_log += math.log(
                max(1e-300, reference_probability))
            edge_ids.append(selected.stable_id)
            current = selected.target_node_id
            node_ids.append(current)
            features = feature_by_node.get(
                current, ProbeNodeFeatures(current))
            total_cost += features.cost
            evidence_risk += features.risk
            reliability *= min(
                1.0, float(selected.control_weight))
            if current in opposite:
                meet_node_id = current
        raw_weight = math.exp(max(
            -700.0, min(
                700.0,
                reference_log - behavior_log)))
        clipped = (
            raw_weight
            > self.config.maximum_importance_weight)
        importance_weight = min(
            raw_weight,
            self.config.maximum_importance_weight)
        endpoint = node_ids[-1]
        prior = endpoint_counts.get(endpoint, 0)
        endpoint_counts[endpoint] = prior + 1
        novelty = 1.0 / (1.0 + prior)
        material = {
            "edge_ids": edge_ids,
            "node_ids": node_ids,
            "rng_substream": substream,
            "sampling_stream": sampling_stream,
            "side": side,
            "topology_generation": (
                view.topology_generation),
        }
        return ProbePath(
            path_id="probe:{}".format(
                structural_hash(material)),
            side=side,
            start_node_id=start,
            node_ids=tuple(node_ids),
            edge_ids=tuple(edge_ids),
            total_cost=total_cost,
            met_opposite_frontier=(
                meet_node_id is not None),
            meet_node_id=meet_node_id,
            novelty=novelty,
            evidence_risk=evidence_risk,
            reliability=reliability,
            behavior_log_probability=behavior_log,
            reference_log_probability=reference_log,
            importance_weight=importance_weight,
            topology_generation=view.topology_generation,
            rng_substream=substream,
            sampling_stream=sampling_stream,
            clipped=clipped)

    def run(
            self, view, side, start_node_ids,
            opposite_frontier_ids, node_features=()):
        if not isinstance(view, FlowView):
            raise TypeError(
                "probe estimator requires FlowView")
        if side not in ("forward", "backward"):
            raise ValueError(
                "probe side must be forward or backward")
        starts = tuple(sorted(set(
            str(value) for value in start_node_ids)))
        opposite = frozenset(str(value)
                             for value in opposite_frontier_ids)
        node_ids = frozenset(
            row.stable_id for row in view.nodes)
        if not starts or any(
                value not in node_ids for value in starts):
            raise ValueError(
                "probe starts must be nodes in the view")
        if any(value not in node_ids for value in opposite):
            raise ValueError(
                "opposite frontier must be nodes in the view")
        features = tuple(node_features)
        if any(not isinstance(row, ProbeNodeFeatures)
               for row in features):
            raise TypeError(
                "probe node features must contain ProbeNodeFeatures")
        feature_by_node = dict(
            (row.node_id, row) for row in features)
        if len(feature_by_node) != len(features):
            raise ValueError(
                "probe node features must be unique")
        if any(value not in node_ids
               for value in feature_by_node):
            raise ValueError(
                "probe features reference unknown node")
        seed_material = {
            "config": self.config.to_dict(),
            "side": side,
            "starts": list(starts),
            "view_hash": view.to_dict()["view_hash"],
        }
        seed = (
            self.config.seed
            + int(structural_hash(seed_material)[:16], 16))
        rng = random.Random(seed)
        reference_count = (
            int(math.ceil(
                self.config.path_count
                * self.config.reference_fraction))
            if self.config.mode == "two_stream" else 0)
        index = FlowTopologyIndex(view)
        endpoint_counts = {}
        paths = []
        for substream in range(self.config.path_count):
            sampling_stream = (
                "reference"
                if substream < reference_count
                else "behavior")
            start = starts[substream % len(starts)]
            paths.append(self._path(
                view, index, side, start, opposite,
                feature_by_node, rng, substream,
                sampling_stream, endpoint_counts))
        weights = tuple(
            row.importance_weight for row in paths)
        weight_sum = sum(weights)
        squared_sum = sum(value * value for value in weights)
        ess = (
            weight_sum * weight_sum / squared_sum
            if squared_sum > 0.0 else 0.0)
        ess_fraction = min(1.0, ess / len(paths))
        clipped_fraction = (
            sum(row.clipped for row in paths)
            / float(len(paths)))
        diversity = (
            len(set(row.node_ids for row in paths))
            / float(len(paths)))
        reasons = []
        if ess_fraction < self.config.minimum_ess_fraction:
            reasons.append("low_effective_sample_size")
        if (clipped_fraction
                > self.config.maximum_clipped_fraction):
            reasons.append("high_clipped_weight_fraction")
        if diversity < self.config.minimum_path_diversity:
            reasons.append("collapsed_path_diversity")
        healthy = not reasons
        health = ProbeHealth(
            healthy=healthy,
            reasons=tuple(reasons),
            effective_sample_size=ess,
            effective_sample_fraction=ess_fraction,
            clipped_weight_fraction=clipped_fraction,
            path_diversity=diversity,
            reference_path_count=reference_count,
            recommended_fallback=(
                None if healthy
                else "deterministic_messages"),
            recovery_actions=(
                () if healthy else (
                    "increase_reference_probes",
                    "increase_temperature",
                    "weaken_route_momentum",
                    "increase_exploration",
                )))
        return ProbeBatch(
            side=side,
            paths=tuple(paths),
            health=health,
            config=self.config,
            estimator_id=self.ESTIMATOR_ID,
            topology_generation=view.topology_generation)
