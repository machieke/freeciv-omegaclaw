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
class TruthAssessment:
    """V2 separation of world-state strength from epistemic uncertainty."""

    strength: float
    confidence: float
    posterior_variance: object = None

    def __post_init__(self):
        _unit_interval(self.strength, "assessment strength")
        _unit_interval(self.confidence, "assessment confidence")
        if self.posterior_variance is not None:
            _unit_interval(
                self.posterior_variance, "posterior variance")

    @classmethod
    def from_truth(cls, truth, posterior_variance=None):
        if not isinstance(truth, TruthState):
            raise TypeError("assessment source must be TruthState")
        return cls(
            truth.strength, truth.confidence, posterior_variance)

    def signed_state_gap(self, target_strength):
        target_strength = _unit_interval(
            target_strength, "target strength")
        return float(target_strength) - float(self.strength)

    def achievement_deficit(self, target_strength):
        return abs(self.signed_state_gap(target_strength))

    def epistemic_uncertainty(self):
        if self.posterior_variance is not None:
            return float(self.posterior_variance)
        return 1.0 - float(self.confidence)

    def to_dict(self):
        return {
            "confidence": float(self.confidence),
            "epistemic_uncertainty": self.epistemic_uncertainty(),
            "posterior_variance": (
                None if self.posterior_variance is None
                else float(self.posterior_variance)),
            "strength": float(self.strength),
        }


@dataclass(frozen=True)
class GoalDemand:
    """Explicit scalar-v2 demand rails before pressure channel routing."""

    achievement: float
    epistemic: float
    deadline: float
    safety: float
    direction: float
    source_goal_id: str

    def __post_init__(self):
        for name in ("achievement", "epistemic", "deadline", "safety"):
            _nonnegative(getattr(self, name), "{} demand".format(name))
        if not -1.0 <= float(self.direction) <= 1.0:
            raise ValueError("demand direction must be in [-1,1]")
        if not isinstance(self.source_goal_id, str) or not self.source_goal_id:
            raise ValueError("demand source goal ID is required")

    @property
    def total(self):
        return (
            float(self.achievement) + float(self.epistemic)
            + float(self.deadline) + float(self.safety))

    def to_dict(self):
        return {
            "achievement_demand": float(self.achievement),
            "deadline_demand": float(self.deadline),
            "direction": float(self.direction),
            "epistemic_demand": float(self.epistemic),
            "safety_demand": float(self.safety),
            "source_goal_id": self.source_goal_id,
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

    @classmethod
    def from_signed(cls, pressure, conflict_policy=None):
        """Explicitly project v2 rails into the lossy v1 representation."""
        if not isinstance(pressure, SignedPressureVector):
            raise TypeError(
                "signed pressure projection requires SignedPressureVector")
        if conflict_policy != "net":
            raise ValueError(
                "v1 projection requires explicit conflict_policy='net'")
        nets = dict(
            (channel, pressure.net(channel))
            for channel in PRESSURE_CHANNELS)
        nonzero_signs = set(
            1 if value > 0.0 else -1
            for value in nets.values() if value != 0.0)
        if len(nonzero_signs) > 1:
            raise ValueError(
                "v1 pressure cannot represent mixed channel directions")
        direction = (
            0.0 if not nonzero_signs else float(next(iter(nonzero_signs))))
        return cls(
            **dict(
                (channel, abs(nets[channel]))
                for channel in PRESSURE_CHANNELS),
            direction=direction)

    def to_dict(self):
        result = dict((channel, self.value(channel)) for channel in PRESSURE_CHANNELS)
        result["direction"] = float(self.direction)
        return result


@dataclass(frozen=True)
class PressureMagnitude:
    """Unsigned per-channel pressure mass."""

    infer: float = 0.0
    observe: float = 0.0
    act: float = 0.0
    expand: float = 0.0
    retain: float = 0.0

    def __post_init__(self):
        for channel in PRESSURE_CHANNELS:
            _nonnegative(
                getattr(self, channel),
                "{} pressure magnitude".format(channel))

    def value(self, channel):
        if channel not in PRESSURE_CHANNELS:
            raise ValueError("unknown pressure channel {}".format(channel))
        return float(getattr(self, channel))

    @property
    def total(self):
        return sum(self.value(channel) for channel in PRESSURE_CHANNELS)

    def plus(self, other):
        if not isinstance(other, PressureMagnitude):
            raise TypeError(
                "pressure magnitude can only add PressureMagnitude")
        return PressureMagnitude(**dict(
            (channel, self.value(channel) + other.value(channel))
            for channel in PRESSURE_CHANNELS))

    def scaled(self, factor):
        factor = _nonnegative(factor, "pressure magnitude scale")
        return PressureMagnitude(**dict(
            (channel, self.value(channel) * factor)
            for channel in PRESSURE_CHANNELS))

    def to_dict(self):
        return dict(
            (channel, self.value(channel))
            for channel in PRESSURE_CHANNELS)


@dataclass(frozen=True)
class SignedPressureVector:
    """Commutative positive and negative demand mass per channel."""

    positive: PressureMagnitude = field(default_factory=PressureMagnitude)
    negative: PressureMagnitude = field(default_factory=PressureMagnitude)

    def __post_init__(self):
        if (not isinstance(self.positive, PressureMagnitude)
                or not isinstance(self.negative, PressureMagnitude)):
            raise TypeError(
                "signed pressure rails must be PressureMagnitude")

    @classmethod
    def from_v1(cls, pressure):
        if not isinstance(pressure, PressureVector):
            raise TypeError("v1 pressure source must be PressureVector")
        magnitude = PressureMagnitude(**dict(
            (channel, pressure.value(channel))
            for channel in PRESSURE_CHANNELS))
        if pressure.direction < 0.0:
            return cls(negative=magnitude)
        return cls(positive=magnitude)

    def plus(self, other):
        if not isinstance(other, SignedPressureVector):
            raise TypeError(
                "signed pressure can only add SignedPressureVector")
        return SignedPressureVector(
            positive=self.positive.plus(other.positive),
            negative=self.negative.plus(other.negative))

    def scaled(self, factor):
        return SignedPressureVector(
            positive=self.positive.scaled(factor),
            negative=self.negative.scaled(factor))

    def net(self, channel):
        return (
            self.positive.value(channel)
            - self.negative.value(channel))

    def conflict(self, channel):
        return min(
            self.positive.value(channel),
            self.negative.value(channel))

    def value(self, channel):
        """Return total contested mass for compatibility schedulers."""
        return (
            self.positive.value(channel)
            + self.negative.value(channel))

    @property
    def total(self):
        return self.positive.total + self.negative.total

    @property
    def total_conflict(self):
        return sum(
            self.conflict(channel) for channel in PRESSURE_CHANNELS)

    def to_dict(self):
        return {
            "negative": self.negative.to_dict(),
            "positive": self.positive.to_dict(),
        }


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
    risk_profile: object = None

    def __post_init__(self):
        if not self.goal_id or not self.target_atom_id:
            raise ValueError("goal ID and target atom are required")
        _unit_interval(self.target_strength, "target_strength")
        _nonnegative(self.utility, "goal utility")
        _nonnegative(self.urgency, "goal urgency")
        _unit_interval(self.commitment, "goal commitment")
        _unit_interval(self.risk_sensitivity, "risk sensitivity")
        if self.risk_profile is not None:
            from .risk import RiskProfile
            if not isinstance(self.risk_profile, RiskProfile):
                raise TypeError("goal risk_profile must be RiskProfile")
            if (self.risk_sensitivity
                    and self.risk_sensitivity
                    != self.risk_profile.aversion):
                raise ValueError(
                    "risk_sensitivity and risk_profile.aversion conflict")

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

    def demand_v2(
            self, truth, decision_sensitivity=1.0,
            deadline_demand=0.0, safety_demand=0.0,
            posterior_variance=None):
        """Decompose control demand without using supported strength."""
        assessment = TruthAssessment.from_truth(
            truth, posterior_variance=posterior_variance)
        sensitivity = _nonnegative(
            decision_sensitivity, "decision sensitivity")
        achievement = (
            self.weight_basis * float(self.commitment)
            * assessment.achievement_deficit(self.target_strength))
        epistemic = (
            sensitivity * assessment.epistemic_uncertainty())
        return GoalDemand(
            achievement=achievement,
            epistemic=epistemic,
            deadline=_nonnegative(deadline_demand, "deadline demand"),
            safety=_nonnegative(safety_demand, "safety demand"),
            direction=self.direction(truth),
            source_goal_id=self.goal_id)

    @property
    def effective_risk_profile(self):
        from .risk import RiskProfile
        return (
            self.risk_profile
            if self.risk_profile is not None
            else RiskProfile(aversion=self.risk_sensitivity))

    def deadline_state(
            self, current_turn, expected_completion_turn=None,
            completion_variance=0.0):
        from .time import DeadlineState
        if self.deadline is not None and (
                isinstance(self.deadline, bool)
                or not isinstance(self.deadline, int)):
            raise ValueError(
                "v2 goal deadline must be an integer turn or absent")
        return DeadlineState(
            current_turn=current_turn,
            deadline_turn=self.deadline,
            expected_completion_turn=expected_completion_turn,
            completion_variance=completion_variance)

    def to_dict(self):
        value = {
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
        if self.risk_profile is not None:
            value["risk_profile"] = self.risk_profile.to_dict()
        return value


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
    risk_estimates: tuple = ()
    reversible: bool = True
    externally_consequential: bool = False
    deadline_estimate: object = None
    packet_costs: tuple = ()
    packet_threshold: int = 1
    reservation_policy: str = "atomic"
    requirement_set_id: object = None

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
        if self.risk_estimates:
            from .risk import RiskEstimate
            if any(not isinstance(row, tuple) or len(row) != 2
                   or not isinstance(row[0], str) or not row[0]
                   or not isinstance(row[1], RiskEstimate)
                   for row in self.risk_estimates):
                raise TypeError(
                    "risk estimates must pair goal IDs with RiskEstimate")
            risk_goal_ids = [str(row[0]) for row in self.risk_estimates]
            if len(risk_goal_ids) != len(set(risk_goal_ids)):
                raise ValueError("operation risk estimates must be unique")
        if not isinstance(self.reversible, bool):
            raise TypeError("operation reversible must be boolean")
        if not isinstance(self.externally_consequential, bool):
            raise TypeError(
                "operation externally_consequential must be boolean")
        if self.deadline_estimate is not None:
            from .time import DeadlineFit
            if not isinstance(self.deadline_estimate, DeadlineFit):
                raise TypeError(
                    "operation deadline_estimate must be DeadlineFit")
        if self.packet_costs:
            from .packets import PacketCost
            if any(not isinstance(row, PacketCost)
                   for row in self.packet_costs):
                raise TypeError(
                    "operation packet_costs must contain PacketCost")
            resources = [row.resource for row in self.packet_costs]
            if len(resources) != len(set(resources)):
                raise ValueError(
                    "operation packet cost resources must be unique")
        if (isinstance(self.packet_threshold, bool)
                or not isinstance(self.packet_threshold, int)
                or self.packet_threshold < 1):
            raise ValueError(
                "operation packet_threshold must be a positive integer")
        if self.reservation_policy not in ("atomic", "primary", "backup"):
            raise ValueError("unknown packet reservation policy")
        if (self.requirement_set_id is not None
                and (not isinstance(self.requirement_set_id, str)
                     or not self.requirement_set_id)):
            raise ValueError(
                "operation requirement_set_id must be a non-empty string")

    def effect_for(self, goal_id):
        effects = dict(self.goal_effects)
        return float(effects.get(goal_id, 1.0))

    def risk_estimate_for(self, goal_id):
        estimates = dict(self.risk_estimates)
        return estimates.get(str(goal_id), estimates.get("*"))

    @property
    def effective_deadline_fit(self):
        return (
            float(self.deadline_fit)
            if self.deadline_estimate is None
            else float(self.deadline_estimate.probability))

    @property
    def artifact_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        value = {
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
        if self.risk_estimates:
            value["risk_estimates"] = dict(
                (goal_id, estimate.to_dict())
                for goal_id, estimate in self.risk_estimates)
        if not self.reversible:
            value["reversible"] = False
        if self.externally_consequential:
            value["externally_consequential"] = True
        if self.deadline_estimate is not None:
            value["deadline_estimate"] = (
                self.deadline_estimate.to_dict())
        if self.packet_costs:
            value["packet_costs"] = [
                row.to_dict() for row in self.packet_costs]
        if self.packet_threshold != 1:
            value["packet_threshold"] = int(self.packet_threshold)
        if self.reservation_policy != "atomic":
            value["reservation_policy"] = self.reservation_policy
        if self.requirement_set_id is not None:
            value["requirement_set_id"] = self.requirement_set_id
        return value


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
