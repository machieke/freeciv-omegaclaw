"""Typed, immutable PF-PLN control artifacts.

Truth values are deliberately passive inputs in this module.  Goals and
pressure can select work, but no pressure API can mutate or recalculate truth.
That type-level separation is the PF-PLN epistemic firewall.
"""

import math
from dataclasses import dataclass, field

from ..events.schema import structural_hash


PRESSURE_CHANNELS = ("infer", "observe", "act", "expand", "retain")
RULE_KINDS = ("and", "or", "dependency", "equivalence", "associative")
CAUSAL_KINDS = ("associative", "diagnostic", "causal", "procedural", "definitional")
ACTION_CAUSAL_KINDS = frozenset(("causal", "procedural"))


def _unit_interval(value, name):
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError("{} must be in [0,1]".format(name))
    return result


def _nonnegative(value, name):
    result = float(value)
    if result < 0.0 or not math.isfinite(result):
        raise ValueError("{} must be finite and nonnegative".format(name))
    return result


@dataclass(frozen=True)
class TruthState:
    """A pressure-free view of an atom's epistemic state."""

    strength: float
    confidence: float
    evidence_ids: tuple = ()
    crisp: bool = False

    def __post_init__(self):
        _unit_interval(self.strength, "strength")
        _unit_interval(self.confidence, "confidence")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("truth evidence IDs must be unique")

    @property
    def supported_strength(self):
        return float(self.strength) * float(self.confidence)

    def to_dict(self):
        return {
            "confidence": float(self.confidence),
            "crisp": bool(self.crisp),
            "evidence_ids": list(self.evidence_ids),
            "strength": float(self.strength),
        }


@dataclass(frozen=True)
class AtomState:
    atom_id: str
    truth: TruthState
    expression: object = None
    context: tuple = ()
    valid_time: object = None
    lifecycle: str = "active"
    clone_id: object = None

    def __post_init__(self):
        if not self.atom_id:
            raise ValueError("atom_id is required")
        if not isinstance(self.truth, TruthState):
            raise TypeError("atom truth must be TruthState")

    def to_dict(self):
        return {
            "atom_id": self.atom_id,
            "clone_id": self.clone_id,
            "context": list(self.context),
            "expression": self.expression,
            "lifecycle": self.lifecycle,
            "truth": self.truth.to_dict(),
            "valid_time": self.valid_time,
        }


@dataclass(frozen=True)
class PressureVector:
    infer: float = 0.0
    observe: float = 0.0
    act: float = 0.0
    expand: float = 0.0
    retain: float = 0.0
    direction: float = 1.0

    def __post_init__(self):
        for channel in PRESSURE_CHANNELS:
            _nonnegative(getattr(self, channel), "{} pressure".format(channel))
        if not -1.0 <= float(self.direction) <= 1.0:
            raise ValueError("pressure direction must be in [-1,1]")

    def value(self, channel):
        if channel not in PRESSURE_CHANNELS:
            raise ValueError("unknown pressure channel {}".format(channel))
        return float(getattr(self, channel))

    @property
    def total(self):
        return sum(self.value(channel) for channel in PRESSURE_CHANNELS)

    def scaled(self, factor):
        factor = _nonnegative(factor, "pressure scale")
        return PressureVector(
            **dict((channel, self.value(channel) * factor)
                   for channel in PRESSURE_CHANNELS),
            direction=self.direction)

    def plus(self, other):
        if not isinstance(other, PressureVector):
            raise TypeError("pressure can only be added to PressureVector")
        weighted_direction = self.direction
        if other.total > self.total:
            weighted_direction = other.direction
        return PressureVector(
            **dict((channel, self.value(channel) + other.value(channel))
                   for channel in PRESSURE_CHANNELS),
            direction=weighted_direction)

    def to_dict(self):
        result = dict((channel, self.value(channel)) for channel in PRESSURE_CHANNELS)
        result["direction"] = float(self.direction)
        return result


@dataclass(frozen=True)
class Resolvability:
    """Expected achievable absolute strength change, before operation cost."""

    infer: float = 0.0
    observe: float = 0.0
    act: float = 0.0
    expand: float = 0.0
    retain: float = 0.0

    def __post_init__(self):
        for channel in PRESSURE_CHANNELS:
            _unit_interval(getattr(self, channel), "{} resolvability".format(channel))

    def value(self, channel):
        if channel not in PRESSURE_CHANNELS:
            raise ValueError("unknown pressure channel {}".format(channel))
        return float(getattr(self, channel))

    @property
    def maximum(self):
        return max(self.value(channel) for channel in PRESSURE_CHANNELS)

    def operational_pressure(self, dependency_pressure, direction):
        dependency_pressure = _nonnegative(dependency_pressure, "dependency pressure")
        return PressureVector(
            **dict((channel, dependency_pressure * self.value(channel))
                   for channel in PRESSURE_CHANNELS),
            direction=direction)

    def to_dict(self):
        return dict((channel, self.value(channel)) for channel in PRESSURE_CHANNELS)


@dataclass(frozen=True)
class GoalState:
    goal_id: str
    target_atom_id: str
    target_strength: float = 1.0
    utility: float = 1.0
    urgency: float = 1.0
    commitment: float = 1.0
    deadline: object = None
    risk_sensitivity: float = 0.0
    safety: bool = False
    context: tuple = ()

    def __post_init__(self):
        if not self.goal_id or not self.target_atom_id:
            raise ValueError("goal ID and target atom are required")
        _unit_interval(self.target_strength, "target_strength")
        _nonnegative(self.utility, "goal utility")
        _nonnegative(self.urgency, "goal urgency")
        _unit_interval(self.commitment, "goal commitment")
        _unit_interval(self.risk_sensitivity, "risk sensitivity")

    def signed_gap(self, truth):
        return float(self.target_strength) - float(truth.strength)

    def gap(self, truth):
        return min(1.0, abs(self.signed_gap(truth)))

    def direction(self, truth):
        difference = self.signed_gap(truth)
        if difference == 0:
            return 0.0
        return 1.0 if difference > 0 else -1.0

    @property
    def weight_basis(self):
        return float(self.utility) * float(self.urgency)

    def demand(self, truth):
        return self.weight_basis * self.gap(truth) * float(self.commitment)

    def to_dict(self):
        return {
            "commitment": float(self.commitment),
            "context": list(self.context),
            "deadline": self.deadline,
            "goal_id": self.goal_id,
            "risk_sensitivity": float(self.risk_sensitivity),
            "safety": bool(self.safety),
            "target_atom_id": self.target_atom_id,
            "target_strength": float(self.target_strength),
            "urgency": float(self.urgency),
            "utility": float(self.utility),
        }


@dataclass(frozen=True)
class PressureRule:
    """A reverse operator declaration; it contains no truth function."""

    rule_id: str
    premise_ids: tuple
    conclusion_id: str
    kind: str = "and"
    causal_kind: str = "associative"
    conductance: float = 1.0
    compatibility: float = 1.0
    residual: float = 1.0
    success_probability: float = 1.0
    deadline_fit: float = 1.0
    route_cost: float = 1.0
    premise_weights: tuple = ()
    context_guard: tuple = ()
    source: object = None

    def __post_init__(self):
        if not self.rule_id or not self.conclusion_id or not self.premise_ids:
            raise ValueError("pressure rule requires ID, premises, and conclusion")
        if len(set(self.premise_ids)) != len(self.premise_ids):
            raise ValueError("pressure rule premises must be unique")
        if self.kind not in RULE_KINDS:
            raise ValueError("unknown pressure rule kind {}".format(self.kind))
        if self.causal_kind not in CAUSAL_KINDS:
            raise ValueError("unknown causal kind {}".format(self.causal_kind))
        for name in ("conductance", "compatibility", "residual",
                     "success_probability", "deadline_fit"):
            _unit_interval(getattr(self, name), name)
        _nonnegative(self.route_cost, "route cost")
        if self.premise_weights:
            if len(self.premise_weights) != len(self.premise_ids):
                raise ValueError("premise weights must match premises")
            if any(float(value) < 0 for value in self.premise_weights):
                raise ValueError("premise weights must be nonnegative")

    @property
    def transport_gate(self):
        return (float(self.conductance) * float(self.compatibility)
                * float(self.residual))

    def to_dict(self):
        return {
            "causal_kind": self.causal_kind,
            "compatibility": float(self.compatibility),
            "conclusion_id": self.conclusion_id,
            "conductance": float(self.conductance),
            "context_guard": list(self.context_guard),
            "deadline_fit": float(self.deadline_fit),
            "kind": self.kind,
            "premise_ids": list(self.premise_ids),
            "premise_weights": list(self.premise_weights),
            "residual": float(self.residual),
            "route_cost": float(self.route_cost),
            "rule_id": self.rule_id,
            "source": self.source,
            "success_probability": float(self.success_probability),
        }


@dataclass(frozen=True)
class CostVector:
    compute: float = 0.0
    latency: float = 0.0
    energy: float = 0.0
    resource: float = 0.0
    risk: float = 0.0
    opportunity: float = 0.0
    commitment: float = 0.0

    def __post_init__(self):
        for name in (
                "compute", "latency", "energy", "resource", "risk",
                "opportunity", "commitment"):
            _nonnegative(getattr(self, name), "{} cost".format(name))

    def scalar(self, weights):
        values = self.to_dict()
        return sum(values[name] * float(dict(weights).get(name, 1.0))
                   for name in sorted(values))

    def to_dict(self):
        return {
            "commitment": float(self.commitment),
            "compute": float(self.compute),
            "energy": float(self.energy),
            "latency": float(self.latency),
            "opportunity": float(self.opportunity),
            "resource": float(self.resource),
            "risk": float(self.risk),
        }


@dataclass(frozen=True)
class Operation:
    operation_id: str
    atom_id: str
    mode: str
    cost: CostVector
    causal_kind: str = "associative"
    success_probability: float = 1.0
    relief_scale: float = 1.0
    feasibility: float = 1.0
    deadline_fit: float = 1.0
    information_gain: float = 0.0
    coherence_gain: float = 0.0
    future_option_value: float = 0.0
    redundancy: float = 0.0
    contradiction_risk: float = 0.0
    goal_effects: tuple = ()
    safety_compatible: bool = True
    payload: object = None

    def __post_init__(self):
        if not self.operation_id or not self.atom_id:
            raise ValueError("operation ID and atom are required")
        if self.mode not in PRESSURE_CHANNELS:
            raise ValueError("unknown operation mode {}".format(self.mode))
        if not isinstance(self.cost, CostVector):
            raise TypeError("operation cost must be CostVector")
        if self.causal_kind not in CAUSAL_KINDS:
            raise ValueError("unknown causal kind {}".format(self.causal_kind))
        for name in ("success_probability", "relief_scale", "feasibility",
                     "deadline_fit"):
            _unit_interval(getattr(self, name), name)
        for name in ("information_gain", "coherence_gain", "future_option_value",
                     "redundancy", "contradiction_risk"):
            _nonnegative(getattr(self, name), name)
        keys = [row[0] for row in self.goal_effects]
        if len(keys) != len(set(keys)):
            raise ValueError("operation goal effects must be unique")
        if any(not -1.0 <= float(row[1]) <= 1.0 for row in self.goal_effects):
            raise ValueError("operation goal effects must be in [-1,1]")

    def effect_for(self, goal_id):
        effects = dict(self.goal_effects)
        return float(effects.get(goal_id, 1.0))

    @property
    def artifact_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "atom_id": self.atom_id,
            "causal_kind": self.causal_kind,
            "coherence_gain": float(self.coherence_gain),
            "contradiction_risk": float(self.contradiction_risk),
            "cost": self.cost.to_dict(),
            "deadline_fit": float(self.deadline_fit),
            "feasibility": float(self.feasibility),
            "future_option_value": float(self.future_option_value),
            "goal_effects": [list(row) for row in self.goal_effects],
            "information_gain": float(self.information_gain),
            "mode": self.mode,
            "operation_id": self.operation_id,
            "payload": self.payload,
            "redundancy": float(self.redundancy),
            "relief_scale": float(self.relief_scale),
            "safety_compatible": bool(self.safety_compatible),
            "success_probability": float(self.success_probability),
        }


@dataclass(frozen=True)
class PressureConfig:
    damping: float = 0.85
    exploration_floor: float = 0.05
    softmax_temperature: float = 0.15
    residual_floor: float = 1e-8
    materialization_floor: float = 1e-6
    max_hops: int = 64
    max_routes_per_conclusion: int = 32
    information_gain_weight: float = 0.10
    coherence_weight: float = 0.05
    future_option_weight: float = 0.05
    action_compatibility_threshold: float = 0.50
    cost_epsilon: float = 1e-9
    cost_weights: tuple = field(default_factory=lambda: (
        ("commitment", 1.0), ("compute", 1.0), ("energy", 1.0),
        ("latency", 1.0), ("opportunity", 1.0), ("resource", 1.0),
        ("risk", 1.0),
    ))

    def __post_init__(self):
        _unit_interval(self.damping, "damping")
        if self.damping >= 1.0:
            raise ValueError("damping must be less than 1")
        _unit_interval(self.exploration_floor, "exploration floor")
        _nonnegative(self.softmax_temperature, "softmax temperature")
        if self.softmax_temperature == 0:
            raise ValueError("softmax temperature must be positive")
        _nonnegative(self.residual_floor, "residual floor")
        _nonnegative(self.materialization_floor, "materialization floor")
        if isinstance(self.max_hops, bool) or not 1 <= int(self.max_hops) <= 10000:
            raise ValueError("max_hops must be in 1..10000")
        if (isinstance(self.max_routes_per_conclusion, bool)
                or not 1 <= int(self.max_routes_per_conclusion) <= 10000):
            raise ValueError(
                "max_routes_per_conclusion must be in 1..10000")
        for name in (
                "information_gain_weight", "coherence_weight",
                "future_option_weight", "cost_epsilon"):
            _nonnegative(getattr(self, name), name)
        _unit_interval(
            self.action_compatibility_threshold,
            "action compatibility threshold")
        if self.cost_epsilon == 0:
            raise ValueError("cost epsilon must be positive")
        if len(dict(self.cost_weights)) != len(self.cost_weights):
            raise ValueError("cost weight names must be unique")
        if any(float(value) < 0 for _, value in self.cost_weights):
            raise ValueError("cost weights must be nonnegative")

    def to_dict(self):
        return {
            "coherence_weight": float(self.coherence_weight),
            "action_compatibility_threshold": float(
                self.action_compatibility_threshold),
            "cost_epsilon": float(self.cost_epsilon),
            "cost_weights": dict(self.cost_weights),
            "damping": float(self.damping),
            "exploration_floor": float(self.exploration_floor),
            "future_option_weight": float(self.future_option_weight),
            "information_gain_weight": float(self.information_gain_weight),
            "materialization_floor": float(self.materialization_floor),
            "max_hops": int(self.max_hops),
            "max_routes_per_conclusion": int(
                self.max_routes_per_conclusion),
            "residual_floor": float(self.residual_floor),
            "softmax_temperature": float(self.softmax_temperature),
        }
