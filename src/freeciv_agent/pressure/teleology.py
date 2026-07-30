"""First-class teleological artifacts and conservative fallback estimates."""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash
from .model import (
    PRESSURE_CHANNELS,
    GoalState,
    Operation,
    SignedPressureVector,
    TruthState,
)


def _finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("{} must be finite".format(name))
    return value


def _nonnegative(value, name):
    value = _finite(value, name)
    if value < 0.0:
        raise ValueError("{} must be non-negative".format(name))
    return value


def typed_expected_relief(
        transition, goal_id, current_goal_loss,
        unknown_policy="neutral"):
    """Integrate goal relief over one canonical transition exactly once.

    Outcome probabilities already belong to ``ExpectedTransition``.  This
    helper therefore never multiplies by ``Operation.success_probability``.
    Unknown mass receives no invented positive relief.  A caller may choose
    the conservative ``adverse`` policy to charge the declared residual loss.
    """
    from .transitions import ExpectedTransition
    if not isinstance(transition, ExpectedTransition):
        raise TypeError(
            "typed expected relief requires ExpectedTransition")
    if not isinstance(goal_id, str) or not goal_id:
        raise ValueError("typed expected relief requires a goal ID")
    current = _nonnegative(
        current_goal_loss, "current goal loss")
    if unknown_policy not in ("neutral", "adverse"):
        raise ValueError(
            "unknown policy must be neutral or adverse")
    relief = 0.0
    fallback = transition.residual_loss_for(goal_id)
    for outcome in transition.outcomes:
        next_loss = outcome.cost_to_go_for(goal_id)
        if next_loss is None:
            next_loss = fallback
        relief += float(outcome.probability) * (
            current - float(next_loss)
            - float(outcome.adverse_loss))
    if unknown_policy == "adverse":
        relief -= (
            float(transition.residual_probability)
            * float(fallback))
    return float(relief)


def typed_expected_reliefs(
        transition, current_goal_losses,
        unknown_policy="neutral"):
    """Return canonically ordered expected-relief rows for several goals."""
    rows = tuple(current_goal_losses)
    keys = [row[0] for row in rows]
    if (any(not isinstance(row, tuple) or len(row) != 2
            for row in rows)
            or len(keys) != len(set(keys))):
        raise ValueError(
            "current goal losses must have unique (goal, loss) rows")
    return tuple(sorted(
        (
            str(goal_id),
            typed_expected_relief(
                transition, str(goal_id), loss,
                unknown_policy=unknown_policy),
        )
        for goal_id, loss in rows))


@dataclass(frozen=True)
class GoalLoss:
    goal_id: str
    immediate_loss: float
    uncertainty_penalty: float
    deadline_penalty: float
    safety_penalty: float
    total: float
    semantics_version: str = "goal-loss/1.0"

    def __post_init__(self):
        if not self.goal_id:
            raise ValueError("goal loss requires goal ID")
        components = (
            self.immediate_loss, self.uncertainty_penalty,
            self.deadline_penalty, self.safety_penalty)
        for value, name in zip(components, (
                "immediate loss", "uncertainty penalty",
                "deadline penalty", "safety penalty")):
            _nonnegative(value, name)
        if abs(float(self.total) - sum(components)) > 1e-9:
            raise ValueError("goal loss total must equal its components")
        if not self.semantics_version:
            raise ValueError("goal loss semantics version is required")

    def to_dict(self):
        return {
            "deadline_penalty": float(self.deadline_penalty),
            "goal_id": self.goal_id,
            "immediate_loss": float(self.immediate_loss),
            "safety_penalty": float(self.safety_penalty),
            "semantics_version": self.semantics_version,
            "total": float(self.total),
            "uncertainty_penalty": float(
                self.uncertainty_penalty),
        }


@dataclass(frozen=True)
class CostToGoEstimate:
    goal_id: str
    expected_loss: float
    lower_bound: float
    upper_bound: float
    horizon: object
    estimator_id: str
    feature_digest: str
    calibrated: bool

    def __post_init__(self):
        if not self.goal_id or not self.estimator_id:
            raise ValueError(
                "cost-to-go requires goal and estimator IDs")
        for value, name in (
                (self.expected_loss, "expected loss"),
                (self.lower_bound, "lower bound"),
                (self.upper_bound, "upper bound")):
            _nonnegative(value, name)
        if not (
                self.lower_bound <= self.expected_loss
                <= self.upper_bound):
            raise ValueError(
                "cost-to-go bounds must contain expected loss")
        if self.horizon is not None and (
                isinstance(self.horizon, bool)
                or not isinstance(self.horizon, int)
                or self.horizon < 0):
            raise ValueError(
                "cost-to-go horizon must be non-negative or absent")
        if (not isinstance(self.feature_digest, str)
                or len(self.feature_digest) != 64):
            raise ValueError(
                "cost-to-go feature digest must be a SHA-256 hash")
        if not isinstance(self.calibrated, bool):
            raise TypeError("cost-to-go calibrated must be boolean")

    def to_dict(self):
        return {
            "calibrated": bool(self.calibrated),
            "estimator_id": self.estimator_id,
            "expected_loss": float(self.expected_loss),
            "feature_digest": self.feature_digest,
            "goal_id": self.goal_id,
            "horizon": self.horizon,
            "lower_bound": float(self.lower_bound),
            "upper_bound": float(self.upper_bound),
        }


@dataclass(frozen=True)
class LeverageEstimate:
    goal_id: str
    target_id: str
    signed_leverage: float
    method: str
    confidence: float
    assumptions: tuple = ()

    def __post_init__(self):
        if not self.goal_id or not self.target_id:
            raise ValueError("leverage requires goal and target IDs")
        _finite(self.signed_leverage, "signed leverage")
        if self.method not in (
                "adjoint", "requirement", "counterfactual",
                "information", "immediate-loss-fallback"):
            raise ValueError("unknown leverage method")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("leverage confidence must be in [0,1]")
        if any(not isinstance(value, str) or not value
               for value in self.assumptions):
            raise ValueError("leverage assumptions must be strings")

    def to_dict(self):
        return {
            "assumptions": list(self.assumptions),
            "confidence": float(self.confidence),
            "goal_id": self.goal_id,
            "method": self.method,
            "signed_leverage": float(self.signed_leverage),
            "target_id": self.target_id,
        }


@dataclass(frozen=True)
class TypedAdvantage:
    goal_id: str
    target_id: str
    mode: str
    expected_relief: float
    relief_variance: float
    information_gain: float
    option_value: float
    predicted_latency: float
    predicted_resource_use: tuple
    estimator_id: str

    def __post_init__(self):
        if not self.goal_id or not self.target_id or not self.estimator_id:
            raise ValueError(
                "typed advantage requires stable IDs")
        if self.mode not in PRESSURE_CHANNELS:
            raise ValueError("unknown typed advantage mode")
        for value, name in (
                (self.expected_relief, "expected relief"),
                (self.relief_variance, "relief variance"),
                (self.information_gain, "information gain"),
                (self.option_value, "option value"),
                (self.predicted_latency, "predicted latency")):
            _nonnegative(value, name)
        resources = [row[0] for row in self.predicted_resource_use]
        if len(resources) != len(set(resources)):
            raise ValueError(
                "predicted resource names must be unique")
        if any(not isinstance(name, str) or not name
               or _nonnegative(value, "predicted resource use") < 0.0
               for name, value in self.predicted_resource_use):
            raise ValueError("invalid predicted resource use")

    @property
    def pre_cost_value(self):
        return (
            float(self.expected_relief)
            + float(self.information_gain)
            + float(self.option_value))

    def to_dict(self):
        return {
            "estimator_id": self.estimator_id,
            "expected_relief": float(self.expected_relief),
            "goal_id": self.goal_id,
            "information_gain": float(self.information_gain),
            "mode": self.mode,
            "option_value": float(self.option_value),
            "predicted_latency": float(self.predicted_latency),
            "predicted_resource_use": dict(
                (name, float(value))
                for name, value in self.predicted_resource_use),
            "relief_variance": float(self.relief_variance),
            "target_id": self.target_id,
        }


class ImmediateLossEstimator:
    """Declared uncalibrated fallback equivalent to scalar-v2 demand."""

    ESTIMATOR_ID = "immediate-loss-fallback/1.0"

    def goal_loss(
            self, goal, truth, decision_sensitivity=1.0,
            deadline_penalty=0.0, safety_penalty=0.0):
        if not isinstance(goal, GoalState) or not isinstance(
                truth, TruthState):
            raise TypeError(
                "immediate loss requires GoalState and TruthState")
        demand = goal.demand_v2(
            truth, decision_sensitivity=decision_sensitivity,
            deadline_demand=deadline_penalty,
            safety_demand=safety_penalty)
        total = (
            demand.achievement + demand.epistemic
            + demand.deadline + demand.safety)
        return GoalLoss(
            goal.goal_id, demand.achievement, demand.epistemic,
            demand.deadline, demand.safety, total)

    def cost_to_go(self, goal_loss, horizon=None):
        if not isinstance(goal_loss, GoalLoss):
            raise TypeError("cost-to-go fallback requires GoalLoss")
        uncertainty = goal_loss.uncertainty_penalty
        lower = max(0.0, goal_loss.total - uncertainty)
        upper = goal_loss.total + uncertainty
        return CostToGoEstimate(
            goal_id=goal_loss.goal_id,
            expected_loss=goal_loss.total,
            lower_bound=lower,
            upper_bound=upper,
            horizon=horizon,
            estimator_id=self.ESTIMATOR_ID,
            feature_digest=structural_hash(goal_loss.to_dict()),
            calibrated=False)

    def advantage(self, operation, pressure_result, goal_id):
        if not isinstance(operation, Operation):
            raise TypeError("advantage source must be Operation")
        goal = next(
            goal for goal in pressure_result.goals
            if goal.goal_id == goal_id)
        vector = pressure_result.pressure(
            goal_id, operation.atom_id)
        channel_pressure = (
            abs(vector.net(operation.mode))
            if isinstance(vector, SignedPressureVector)
            else vector.value(operation.mode))
        relief = (
            channel_pressure * operation.success_probability
            * operation.relief_scale)
        return TypedAdvantage(
            goal_id=goal.goal_id,
            target_id=operation.atom_id,
            mode=operation.mode,
            expected_relief=relief,
            relief_variance=0.0,
            information_gain=operation.information_gain,
            option_value=operation.future_option_value,
            predicted_latency=operation.cost.latency,
            predicted_resource_use=tuple(sorted(
                (name, value) for name, value
                in operation.cost.to_dict().items() if value > 0.0)),
            estimator_id=self.ESTIMATOR_ID)


class ExactTerminalEstimator:
    """Exact cost for a declared terminal goal state."""

    ESTIMATOR_ID = "exact-terminal/1.0"

    def estimate(
            self, goal_id, terminal_loss,
            horizon=0, terminal=True, features=()):
        if terminal is not True:
            raise ValueError(
                "exact terminal estimator requires terminal state")
        loss = _nonnegative(
            terminal_loss, "terminal loss")
        if (isinstance(horizon, bool)
                or not isinstance(horizon, int)
                or horizon < 0):
            raise ValueError(
                "terminal horizon must be non-negative")
        material = {
            "features": list(features),
            "goal_id": str(goal_id),
            "horizon": horizon,
            "terminal_loss": loss,
        }
        return CostToGoEstimate(
            str(goal_id), loss, loss, loss, horizon,
            self.ESTIMATOR_ID, structural_hash(material), True)


class OneStepTransitionEstimator:
    """Cost-to-go from one typed expected transition."""

    ESTIMATOR_ID = "expected-transition-one-step/1.0"

    def estimate(
            self, transition, goal_id, horizon=None,
            calibrated=False):
        from .transitions import ExpectedTransition
        if not isinstance(transition, ExpectedTransition):
            raise TypeError(
                "one-step estimator requires ExpectedTransition")
        goal_id = str(goal_id)
        fallback = transition.residual_loss_for(goal_id)
        values = tuple(
            (
                float(outcome.cost_to_go_for(goal_id))
                if outcome.cost_to_go_for(goal_id) is not None
                else fallback)
            + float(outcome.adverse_loss)
            for outcome in transition.outcomes)
        if transition.residual_probability > 0.0:
            values += (fallback,)
        expected = transition.expected_cost_to_go(goal_id)
        lower = min(values or (expected,))
        upper = max(values or (expected,))
        return CostToGoEstimate(
            goal_id, expected,
            min(lower, expected), max(upper, expected),
            horizon,
            "{}:{}".format(
                self.ESTIMATOR_ID, transition.model_id),
            structural_hash(transition.to_dict()),
            bool(calibrated))


class BoundedDynamicProgrammingEstimator:
    """Exact finite-horizon DP for small declared transition tables."""

    ESTIMATOR_ID = "bounded-dynamic-programming/1.0"

    def __init__(self, maximum_horizon=16, maximum_states=128):
        if (isinstance(maximum_horizon, bool)
                or not isinstance(maximum_horizon, int)
                or maximum_horizon < 1):
            raise ValueError(
                "maximum DP horizon must be positive")
        if (isinstance(maximum_states, bool)
                or not isinstance(maximum_states, int)
                or maximum_states < 1):
            raise ValueError(
                "maximum DP states must be positive")
        self.maximum_horizon = maximum_horizon
        self.maximum_states = maximum_states

    def estimate(
            self, goal_id, initial_state,
            terminal_losses, transitions, horizon):
        if (isinstance(horizon, bool)
                or not isinstance(horizon, int)
                or not 0 <= horizon <= self.maximum_horizon):
            raise ValueError(
                "DP horizon exceeds configured bound")
        terminal_losses = dict(
            (str(key), _nonnegative(value, "terminal loss"))
            for key, value in dict(terminal_losses).items())
        transitions = dict(transitions)
        states = set(terminal_losses) | set(str(key)
                                            for key in transitions)
        if str(initial_state) not in states:
            raise ValueError(
                "DP initial state is not declared")
        if len(states) > self.maximum_states:
            raise ValueError(
                "DP state count exceeds configured bound")
        value = dict(
            (state, terminal_losses.get(state, 0.0))
            for state in states)
        maximum_immediate = 0.0
        for _ in range(horizon):
            following = {}
            for state in sorted(states):
                actions = transitions.get(state, {})
                if not actions:
                    following[state] = value[state]
                    continue
                action_values = []
                for action_id, outcomes in sorted(actions.items()):
                    del action_id
                    probability = 0.0
                    expected = 0.0
                    for row in tuple(outcomes):
                        if (not isinstance(row, tuple)
                                or len(row) != 3):
                            raise TypeError(
                                "DP outcomes must be "
                                "(probability, next_state, loss)")
                        chance, next_state, immediate = row
                        chance = float(chance)
                        if (not 0.0 <= chance <= 1.0
                                or not math.isfinite(chance)):
                            raise ValueError(
                                "DP probability must be in [0,1]")
                        next_state = str(next_state)
                        if next_state not in states:
                            raise ValueError(
                                "DP outcome references unknown state")
                        immediate = _nonnegative(
                            immediate, "DP immediate loss")
                        maximum_immediate = max(
                            maximum_immediate, immediate)
                        probability += chance
                        expected += chance * (
                            immediate + value[next_state])
                    if abs(probability - 1.0) > 1e-9:
                        raise ValueError(
                            "DP outcome probabilities must sum to one")
                    action_values.append(expected)
                following[state] = min(action_values)
            value = following
        expected = value[str(initial_state)]
        upper = max(
            expected,
            max(terminal_losses.values() or (0.0,))
            + horizon * maximum_immediate)
        material = {
            "goal_id": str(goal_id),
            "horizon": horizon,
            "initial_state": str(initial_state),
            "terminal_losses": terminal_losses,
            "transitions": transitions,
        }
        return CostToGoEstimate(
            str(goal_id), expected, 0.0, upper, horizon,
            self.ESTIMATOR_ID, structural_hash(material), True)


class CalibratedHeuristicEstimator:
    """Bounded heuristic labeled by held-out calibration support."""

    ESTIMATOR_ID = "calibrated-heuristic/1.0"

    def __init__(self, minimum_calibration_samples=30):
        if (isinstance(minimum_calibration_samples, bool)
                or not isinstance(minimum_calibration_samples, int)
                or minimum_calibration_samples < 1):
            raise ValueError(
                "minimum calibration samples must be positive")
        self.minimum_calibration_samples = (
            minimum_calibration_samples)

    def estimate(
            self, goal_id, predicted_loss,
            absolute_error_bound, calibration_samples,
            horizon=None, features=()):
        predicted = _nonnegative(
            predicted_loss, "heuristic predicted loss")
        error = _nonnegative(
            absolute_error_bound,
            "heuristic absolute error bound")
        if (isinstance(calibration_samples, bool)
                or not isinstance(calibration_samples, int)
                or calibration_samples < 0):
            raise ValueError(
                "calibration samples must be non-negative")
        material = {
            "calibration_samples": calibration_samples,
            "features": list(features),
            "goal_id": str(goal_id),
            "horizon": horizon,
            "predicted_loss": predicted,
        }
        return CostToGoEstimate(
            str(goal_id), predicted,
            max(0.0, predicted - error),
            predicted + error, horizon,
            self.ESTIMATOR_ID, structural_hash(material),
            calibration_samples
            >= self.minimum_calibration_samples)
