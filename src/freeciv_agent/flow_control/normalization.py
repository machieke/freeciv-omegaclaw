"""Versioned normalization and units contract for resource flow."""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash


REQUIRED_ROBUST_SCALES = (
    "bridge_height_difference",
    "congestion_dual",
    "edge_cost",
    "probe_deposit_energy",
    "risk",
    "typed_advantage",
)
SUPPORTED_METRICS = ("l1", "l2", "linf")


def _finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("{} must be finite".format(name))
    return value


def _positive(value, name):
    value = _finite(value, name)
    if value <= 0.0:
        raise ValueError(
            "{} must be positive".format(name))
    return value


def _unit_interval(value, name, allow_zero=True):
    value = _finite(value, name)
    lower_ok = value >= 0.0 if allow_zero else value > 0.0
    if not lower_ok or value > 1.0:
        raise ValueError(
            "{} must be {}0 and <= 1".format(
                name, ">=" if allow_zero else ">"))
    return value


def _pairs(values, name):
    values = tuple(values)
    if any(not isinstance(row, tuple) or len(row) != 2
           or not isinstance(row[0], str) or not row[0]
           for row in values):
        raise ValueError(
            "{} must contain named pairs".format(name))
    keys = [row[0] for row in values]
    if len(keys) != len(set(keys)):
        raise ValueError(
            "{} keys must be unique".format(name))
    return tuple(sorted(values))


def _median(values):
    values = tuple(sorted(float(value) for value in values))
    if not values:
        raise ValueError("median requires values")
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return 0.5 * (values[middle - 1] + values[middle])


def _quantile(values, probability):
    values = tuple(sorted(float(value) for value in values))
    if not values:
        raise ValueError("quantile requires values")
    position = (len(values) - 1) * float(probability)
    lower = int(position)
    upper = min(len(values) - 1, lower + 1)
    fraction = position - lower
    return (
        values[lower] * (1.0 - fraction)
        + values[upper] * fraction)


def _norm(values, metric):
    values = tuple(float(value) for value in values)
    if metric == "l1":
        return sum(abs(value) for value in values)
    if metric == "l2":
        return math.sqrt(sum(value * value for value in values))
    if metric == "linf":
        return max((abs(value) for value in values), default=0.0)
    raise ValueError("unknown normalization metric")


@dataclass(frozen=True)
class NormalizationContract:
    contract_id: str
    goal_loss_scales: tuple
    robust_scale_policy: str
    clipping_ranges: tuple
    scale_update_cadence: int
    semantic_metric: str
    probe_metric: str
    turnover_fraction: float
    packet_quanta: tuple
    capacity_policy: str
    precision_policy: str
    fallback_scales: tuple
    sign_convention: str = "positive-source-to-sink"

    def __post_init__(self):
        if not isinstance(self.contract_id, str) or not self.contract_id:
            raise ValueError(
                "normalization contract ID is required")
        goals = _pairs(
            self.goal_loss_scales, "goal loss scales")
        for _, value in goals:
            _positive(value, "goal loss scale")
        if self.robust_scale_policy not in (
                "median-absolute-deviation",
                "interquartile-range",
                "declared-fixed"):
            raise ValueError(
                "unknown robust scale policy")
        clipping = tuple(self.clipping_ranges)
        if any(not isinstance(row, tuple) or len(row) != 3
               or not isinstance(row[0], str) or not row[0]
               for row in clipping):
            raise ValueError(
                "clipping ranges must contain named triples")
        clipping_keys = [row[0] for row in clipping]
        if len(clipping_keys) != len(set(clipping_keys)):
            raise ValueError(
                "clipping range keys must be unique")
        for _, lower, upper in clipping:
            lower = _finite(lower, "clipping lower bound")
            upper = _finite(upper, "clipping upper bound")
            if lower >= upper:
                raise ValueError(
                    "clipping lower bound must be below upper")
        if (isinstance(self.scale_update_cadence, bool)
                or not isinstance(
                    self.scale_update_cadence, int)
                or self.scale_update_cadence < 1):
            raise ValueError(
                "scale update cadence must be positive")
        if (self.semantic_metric not in SUPPORTED_METRICS
                or self.probe_metric not in SUPPORTED_METRICS):
            raise ValueError(
                "unknown normalization metric")
        if self.semantic_metric != self.probe_metric:
            raise ValueError(
                "semantic and probe directions require same metric")
        _unit_interval(
            self.turnover_fraction,
            "turnover fraction", allow_zero=False)
        packets = _pairs(
            self.packet_quanta, "packet quanta")
        for _, value in packets:
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 1):
                raise ValueError(
                    "packet quanta must be positive integers")
        if (not isinstance(self.capacity_policy, str)
                or not self.capacity_policy):
            raise ValueError(
                "capacity policy is required")
        if self.precision_policy not in (
                "float64", "decimal-reference"):
            raise ValueError(
                "unknown precision policy")
        fallback = _pairs(
            self.fallback_scales, "fallback scales")
        for _, value in fallback:
            _positive(value, "fallback scale")
        missing = set(REQUIRED_ROBUST_SCALES) - {
            key for key, _ in fallback}
        if missing:
            raise ValueError(
                "missing required fallback scales: {}".format(
                    ", ".join(sorted(missing))))
        if (not isinstance(self.sign_convention, str)
                or not self.sign_convention):
            raise ValueError(
                "sign convention is required")

    @property
    def contract_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "capacity_policy": self.capacity_policy,
            "clipping_ranges": [
                {
                    "field": field,
                    "lower": float(lower),
                    "upper": float(upper),
                }
                for field, lower, upper
                in sorted(self.clipping_ranges)],
            "contract_id": self.contract_id,
            "fallback_scales": dict(
                sorted(self.fallback_scales)),
            "goal_loss_scales": dict(
                sorted(self.goal_loss_scales)),
            "packet_quanta": dict(
                sorted(self.packet_quanta)),
            "precision_policy": self.precision_policy,
            "probe_metric": self.probe_metric,
            "robust_scale_policy": (
                self.robust_scale_policy),
            "scale_update_cadence": (
                self.scale_update_cadence),
            "semantic_metric": self.semantic_metric,
            "sign_convention": self.sign_convention,
            "turnover_fraction": float(
                self.turnover_fraction),
        }


def default_normalization_contract():
    return NormalizationContract(
        contract_id="pf-flow-normalization/1.0",
        goal_loss_scales=(),
        robust_scale_policy=(
            "median-absolute-deviation"),
        clipping_ranges=tuple(
            (field, -6.0, 6.0)
            for field in REQUIRED_ROBUST_SCALES),
        scale_update_cadence=32,
        semantic_metric="l2",
        probe_metric="l2",
        turnover_fraction=0.25,
        packet_quanta=(
            ("action", 1), ("cpu", 1)),
        capacity_policy="provenance-required",
        precision_policy="float64",
        fallback_scales=tuple(
            (field, 1.0)
            for field in REQUIRED_ROBUST_SCALES))


@dataclass(frozen=True)
class RobustScale:
    field_name: str
    value: float
    policy: str
    sample_count: int
    fallback_used: bool

    def __post_init__(self):
        if not isinstance(self.field_name, str) or not self.field_name:
            raise ValueError(
                "robust scale field is required")
        _positive(self.value, "robust scale")
        if (isinstance(self.sample_count, bool)
                or not isinstance(self.sample_count, int)
                or self.sample_count < 0):
            raise ValueError(
                "scale sample count must be non-negative")
        if not isinstance(self.fallback_used, bool):
            raise TypeError(
                "scale fallback state must be boolean")

    def to_dict(self):
        return {
            "fallback_used": self.fallback_used,
            "field_name": self.field_name,
            "policy": self.policy,
            "sample_count": self.sample_count,
            "value": float(self.value),
        }


@dataclass(frozen=True)
class NormalizedDirection:
    values: tuple
    norm: float
    metric_id: str
    field_name: str
    source_component: str
    scale: RobustScale

    def __post_init__(self):
        if self.metric_id not in SUPPORTED_METRICS:
            raise ValueError(
                "unknown normalized direction metric")
        if any(not math.isfinite(float(value))
               for value in self.values):
            raise ValueError(
                "normalized direction values must be finite")
        actual = _norm(self.values, self.metric_id)
        if abs(actual - float(self.norm)) > 1e-12:
            raise ValueError(
                "normalized direction norm is inconsistent")
        if actual > 0.0 and abs(actual - 1.0) > 1e-12:
            raise ValueError(
                "nonzero direction must have unit norm")
        if not isinstance(self.scale, RobustScale):
            raise TypeError(
                "normalized direction requires RobustScale")

    def to_dict(self):
        return {
            "field_name": self.field_name,
            "metric_id": self.metric_id,
            "norm": float(self.norm),
            "scale": self.scale.to_dict(),
            "source_component": self.source_component,
            "values": [float(value) for value in self.values],
        }


@dataclass(frozen=True)
class MixedDirection:
    unit_values: tuple
    velocity: tuple
    turnover_rate: float
    raw_cfl_bound: float
    metric_id: str
    semantic_weight: float
    probe_weight: float
    input_norms: tuple
    normalization_contract_id: str
    normalization_contract_hash: str

    def __post_init__(self):
        _unit_interval(
            self.turnover_rate,
            "turnover rate")
        _unit_interval(
            self.raw_cfl_bound,
            "raw CFL bound")
        if self.raw_cfl_bound > self.turnover_rate + 1e-12:
            raise ValueError(
                "raw CFL cannot exceed turnover rate")
        if abs(
                self.semantic_weight
                + self.probe_weight - 1.0) > 1e-12:
            raise ValueError(
                "direction weights must sum to one")

    def to_dict(self):
        return {
            "input_norms": dict(self.input_norms),
            "metric_id": self.metric_id,
            "normalization_contract_hash": (
                self.normalization_contract_hash),
            "normalization_contract_id": (
                self.normalization_contract_id),
            "probe_weight": float(self.probe_weight),
            "raw_cfl_bound": float(self.raw_cfl_bound),
            "semantic_weight": float(
                self.semantic_weight),
            "turnover_rate": float(self.turnover_rate),
            "unit_values": [
                float(value) for value in self.unit_values],
            "velocity": [
                float(value) for value in self.velocity],
        }


class RobustNormalizer:
    """Normalize semantic/probe directions before any convex mixing."""

    def __init__(self, contract=None):
        self.contract = (
            contract if contract is not None
            else default_normalization_contract())
        if not isinstance(
                self.contract, NormalizationContract):
            raise TypeError(
                "normalizer requires NormalizationContract")
        self._fallbacks = dict(
            self.contract.fallback_scales)
        self._clipping = dict(
            (field, (float(lower), float(upper)))
            for field, lower, upper
            in self.contract.clipping_ranges)

    def robust_scale(self, field_name, values):
        if field_name not in self._fallbacks:
            raise ValueError(
                "field lacks declared fallback scale")
        values = tuple(
            _finite(value, "{} sample".format(field_name))
            for value in values)
        policy = self.contract.robust_scale_policy
        scale = None
        if policy == "declared-fixed":
            scale = self._fallbacks[field_name]
        elif len(values) >= 3:
            if policy == "median-absolute-deviation":
                center = _median(values)
                scale = 1.4826 * _median(tuple(
                    abs(value - center)
                    for value in values))
            elif policy == "interquartile-range":
                scale = (
                    _quantile(values, 0.75)
                    - _quantile(values, 0.25)) / 1.349
        fallback = (
            scale is None
            or not math.isfinite(float(scale))
            or float(scale) <= 1e-12)
        if fallback:
            scale = self._fallbacks[field_name]
        return RobustScale(
            field_name, float(scale), policy,
            len(values), fallback)

    def normalize(
            self, values, field_name,
            source_component, metric_id=None):
        values = tuple(values)
        scale = self.robust_scale(field_name, values)
        lower, upper = self._clipping[field_name]
        scaled = tuple(
            max(lower, min(upper, float(value) / scale.value))
            for value in values)
        metric = metric_id or self.contract.semantic_metric
        magnitude = _norm(scaled, metric)
        unit = (
            tuple(0.0 for _ in scaled)
            if magnitude == 0.0 else
            tuple(value / magnitude for value in scaled))
        return NormalizedDirection(
            unit, _norm(unit, metric), metric,
            field_name, str(source_component), scale)

    def mean_probe_direction(
            self, path_directions,
            field_name="probe_deposit_energy"):
        rows = tuple(
            tuple(float(value) for value in row)
            for row in path_directions)
        if not rows:
            return self.normalize(
                (), field_name,
                "corrected-probe-path-mean",
                self.contract.probe_metric)
        width = len(rows[0])
        if any(len(row) != width for row in rows):
            raise ValueError(
                "probe path directions require equal width")
        mean = tuple(
            sum(row[index] for row in rows) / len(rows)
            for index in range(width))
        return self.normalize(
            mean, field_name,
            "corrected-probe-path-mean",
            self.contract.probe_metric)

    def mix(
            self, semantic, probe,
            semantic_weight, probe_weight,
            outer_packet_allocation=1.0):
        if (not isinstance(semantic, NormalizedDirection)
                or not isinstance(probe, NormalizedDirection)):
            raise TypeError(
                "mixed directions must be normalized")
        if semantic.metric_id != probe.metric_id:
            raise ValueError(
                "mixed directions require same metric")
        if len(semantic.values) != len(probe.values):
            raise ValueError(
                "mixed directions require same width")
        semantic_weight = _unit_interval(
            semantic_weight, "semantic weight")
        probe_weight = _unit_interval(
            probe_weight, "probe weight")
        if abs(
                semantic_weight + probe_weight - 1.0) > 1e-12:
            raise ValueError(
                "semantic and probe weights must sum to one")
        allocation = _unit_interval(
            outer_packet_allocation,
            "outer packet allocation")
        combined = tuple(
            semantic_weight * left
            + probe_weight * right
            for left, right in zip(
                semantic.values, probe.values))
        magnitude = _norm(combined, semantic.metric_id)
        unit = (
            tuple(0.0 for _ in combined)
            if magnitude == 0.0 else
            tuple(value / magnitude for value in combined))
        rate = (
            self.contract.turnover_fraction
            * allocation)
        velocity = tuple(rate * value for value in unit)
        raw_cfl = max(
            (abs(value) for value in velocity),
            default=0.0)
        return MixedDirection(
            unit_values=unit,
            velocity=velocity,
            turnover_rate=rate,
            raw_cfl_bound=raw_cfl,
            metric_id=semantic.metric_id,
            semantic_weight=semantic_weight,
            probe_weight=probe_weight,
            input_norms=(
                ("probe", probe.norm),
                ("semantic", semantic.norm)),
            normalization_contract_id=(
                self.contract.contract_id),
            normalization_contract_hash=(
                self.contract.contract_hash))
