"""Typed semantic/probe directions and bounded requested currents."""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash
from .model import FlowProcess, FlowView
from .normalization import RobustNormalizer
from .probes import ProbePath


def _norm(values, metric):
    values = tuple(float(value) for value in values)
    if metric == "l1":
        return sum(abs(value) for value in values)
    if metric == "l2":
        return math.sqrt(sum(value * value for value in values))
    if metric == "linf":
        return max((abs(value) for value in values), default=0.0)
    raise ValueError("unknown current metric")


@dataclass(frozen=True)
class DirectionalField:
    commodity_id: str
    edge_values: tuple
    norm: float
    metric_id: str
    source_components: tuple

    def __post_init__(self):
        if not isinstance(self.commodity_id, str) or not self.commodity_id:
            raise ValueError("directional commodity ID is required")
        if any(not math.isfinite(float(value))
               for value in self.edge_values):
            raise ValueError("directional field values must be finite")
        actual = _norm(self.edge_values, self.metric_id)
        if abs(actual - float(self.norm)) > 1e-12:
            raise ValueError("directional field norm is inconsistent")
        if actual > 0.0 and abs(actual - 1.0) > 1e-12:
            raise ValueError(
                "nonzero directional field must be unit normalized")
        if (not isinstance(self.source_components, tuple)
                or any(not isinstance(value, str) or not value
                       for value in self.source_components)):
            raise ValueError(
                "directional source components must be named")

    def to_dict(self):
        return {
            "commodity_id": self.commodity_id,
            "edge_values": [
                float(value) for value in self.edge_values],
            "metric_id": self.metric_id,
            "norm": float(self.norm),
            "source_components": list(self.source_components),
        }


@dataclass(frozen=True)
class RequestedCurrent:
    commodity_id: str
    edge_ids: tuple
    velocity: tuple
    turnover_rate: float
    normalization_contract_id: str
    normalization_contract_hash: str
    semantic_weight: float
    probe_weight: float
    boundary_vector: tuple
    legality_mask: tuple
    legal_process: str
    semantic_direction: DirectionalField
    probe_direction: DirectionalField
    source_components: tuple
    successful_probe_count: int
    probe_effective_sample_size: float
    probe_variance_proxy: float

    def __post_init__(self):
        if not isinstance(self.commodity_id, str) or not self.commodity_id:
            raise ValueError(
                "requested current commodity ID is required")
        if (len(self.edge_ids) != len(self.velocity)
                or len(self.edge_ids) != len(self.legality_mask)):
            raise ValueError(
                "requested current edge arrays must align")
        if len(set(self.edge_ids)) != len(self.edge_ids):
            raise ValueError(
                "requested current edge IDs must be unique")
        if any(not math.isfinite(float(value))
               for value in self.velocity):
            raise ValueError("requested velocity must be finite")
        if any(not isinstance(value, bool)
               for value in self.legality_mask):
            raise TypeError(
                "requested legality mask must be boolean")
        if any(
                not legal and abs(float(value)) > 1e-15
                for value, legal in zip(
                    self.velocity, self.legality_mask)):
            raise ValueError(
                "illegal edge cannot carry requested current")
        if abs(sum(
                float(value) for _, value
                in self.boundary_vector)) > 1e-12:
            raise ValueError(
                "source-sink boundary vector must balance")
        if (isinstance(self.successful_probe_count, bool)
                or not isinstance(self.successful_probe_count, int)
                or self.successful_probe_count < 0):
            raise ValueError(
                "successful probe count must be non-negative")
        for value, name in (
                (self.probe_effective_sample_size,
                 "probe effective sample size"),
                (self.probe_variance_proxy,
                 "probe variance proxy")):
            if float(value) < 0.0 or not math.isfinite(float(value)):
                raise ValueError(
                    "{} must be finite and non-negative".format(name))
        if not isinstance(
                self.semantic_direction, DirectionalField):
            raise TypeError(
                "semantic direction must be DirectionalField")
        if not isinstance(self.probe_direction, DirectionalField):
            raise TypeError(
                "probe direction must be DirectionalField")

    @property
    def current_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "boundary_vector": [
                {"node_id": node_id, "value": float(value)}
                for node_id, value in self.boundary_vector],
            "commodity_id": self.commodity_id,
            "edge_ids": list(self.edge_ids),
            "legal_process": self.legal_process,
            "legality_mask": list(self.legality_mask),
            "normalization_contract_hash": (
                self.normalization_contract_hash),
            "normalization_contract_id": (
                self.normalization_contract_id),
            "probe_direction": self.probe_direction.to_dict(),
            "probe_effective_sample_size": float(
                self.probe_effective_sample_size),
            "probe_variance_proxy": float(
                self.probe_variance_proxy),
            "probe_weight": float(self.probe_weight),
            "semantic_direction": self.semantic_direction.to_dict(),
            "semantic_weight": float(self.semantic_weight),
            "source_components": list(self.source_components),
            "successful_probe_count": self.successful_probe_count,
            "turnover_rate": float(self.turnover_rate),
            "velocity": [float(value) for value in self.velocity],
        }


class RequestedCurrentBuilder:
    """Mix normalized semantic and corrected probe directions."""

    BUILDER_IDENTITY = "pf-requested-current/1.0"

    def __init__(
            self, normalizer=None,
            deposit_decay=0.0):
        self.normalizer = (
            normalizer if normalizer is not None
            else RobustNormalizer())
        if not isinstance(self.normalizer, RobustNormalizer):
            raise TypeError(
                "current builder requires RobustNormalizer")
        self.deposit_decay = float(deposit_decay)
        if (not math.isfinite(self.deposit_decay)
                or not 0.0 <= self.deposit_decay <= 1.0):
            raise ValueError(
                "probe deposit decay must be in [0, 1]")

    @staticmethod
    def _mapping(values, edge_ids, name):
        if isinstance(values, dict):
            unknown = set(values) - set(edge_ids)
            if unknown:
                raise ValueError(
                    "{} references unknown edges".format(name))
            return tuple(
                float(values.get(edge_id, 0.0))
                for edge_id in edge_ids)
        values = tuple(float(value) for value in values)
        if len(values) != len(edge_ids):
            raise ValueError(
                "{} must align with flow edges".format(name))
        return values

    def _probe_deposit(
            self, edge_ids, paths, legality_mask):
        edge_index = dict(
            (edge_id, index)
            for index, edge_id in enumerate(edge_ids))
        successful = tuple(
            row for row in paths
            if row.met_opposite_frontier)
        deposits = [0.0] * len(edge_ids)
        total_weight = 0.0
        squared_weight = 0.0
        for path in successful:
            path_edges = tuple(dict.fromkeys(path.edge_ids))
            energy = math.sqrt(max(1, len(path_edges)))
            weight = (
                float(path.importance_weight)
                * float(path.reliability))
            total_weight += weight
            squared_weight += weight * weight
            for offset, edge_id in enumerate(path_edges):
                if edge_id not in edge_index:
                    raise ValueError(
                        "probe path references edge outside view")
                index = edge_index[edge_id]
                if not legality_mask[index]:
                    raise ValueError(
                        "probe path traverses illegal edge")
                deposits[index] += (
                    weight / energy
                    * (
                        (1.0 - self.deposit_decay)
                        ** offset))
        if total_weight > 0.0:
            deposits = [
                value / total_weight for value in deposits]
        ess = (
            total_weight * total_weight / squared_weight
            if squared_weight > 0.0 else 0.0)
        variance = 1.0 / ess if ess > 0.0 else 1.0
        return tuple(deposits), len(successful), ess, variance

    def build(
            self, view, commodity_id,
            semantic_edge_values, successful_probe_paths,
            boundary_vector, legal_process,
            semantic_weight=0.5, probe_weight=0.5,
            outer_packet_allocation=1.0):
        if not isinstance(view, FlowView):
            raise TypeError(
                "requested current requires FlowView")
        if not isinstance(legal_process, FlowProcess):
            legal_process = FlowProcess(legal_process)
        edge_ids = tuple(row.stable_id for row in view.edges)
        legality = tuple(
            row.legality.allows(legal_process)
            for row in view.edges)
        semantic_raw = self._mapping(
            semantic_edge_values, edge_ids,
            "semantic edge direction")
        semantic_raw = tuple(
            value if legal else 0.0
            for value, legal in zip(semantic_raw, legality))
        paths = tuple(successful_probe_paths)
        if any(not isinstance(row, ProbePath) for row in paths):
            raise TypeError(
                "probe deposits must contain ProbePath")
        probe_raw, count, ess, variance = self._probe_deposit(
            edge_ids, paths, legality)
        semantic = self.normalizer.normalize(
            semantic_raw, "bridge_height_difference",
            "teleological-semantic-edge-direction",
            self.normalizer.contract.semantic_metric)
        probe = self.normalizer.normalize(
            probe_raw, "probe_deposit_energy",
            "corrected-successful-probe-current",
            self.normalizer.contract.probe_metric)
        mixed = self.normalizer.mix(
            semantic, probe, semantic_weight, probe_weight,
            outer_packet_allocation)
        boundary = tuple(sorted(
            (str(node_id), float(value))
            for node_id, value in dict(boundary_vector).items()))
        node_ids = frozenset(row.stable_id for row in view.nodes)
        if any(node_id not in node_ids
               for node_id, _ in boundary):
            raise ValueError(
                "boundary references unknown flow node")
        semantic_field = DirectionalField(
            str(commodity_id), semantic.values,
            semantic.norm, semantic.metric_id,
            (semantic.source_component,))
        probe_field = DirectionalField(
            str(commodity_id), probe.values,
            probe.norm, probe.metric_id,
            (probe.source_component,))
        return RequestedCurrent(
            commodity_id=str(commodity_id),
            edge_ids=edge_ids,
            velocity=tuple(
                value if legal else 0.0
                for value, legal in zip(mixed.velocity, legality)),
            turnover_rate=mixed.turnover_rate,
            normalization_contract_id=(
                self.normalizer.contract.contract_id),
            normalization_contract_hash=(
                self.normalizer.contract.contract_hash),
            semantic_weight=float(semantic_weight),
            probe_weight=float(probe_weight),
            boundary_vector=boundary,
            legality_mask=legality,
            legal_process=legal_process.value,
            semantic_direction=semantic_field,
            probe_direction=probe_field,
            source_components=(
                "teleological-semantic-edge-direction",
                "corrected-successful-probe-current",
                "outer-packet-allocation"),
            successful_probe_count=count,
            probe_effective_sample_size=ess,
            probe_variance_proxy=variance)
