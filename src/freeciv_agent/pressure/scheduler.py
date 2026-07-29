"""Cost-aware PF-PLN operation scheduling with multi-goal isolation."""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash
from .model import (
    ACTION_CAUSAL_KINDS,
    GoalState,
    Operation,
    PressureConfig,
    SignedPressureVector,
)
from .risk import RiskTrace


@dataclass(frozen=True)
class GoalEffect:
    goal_id: str
    pressure: float
    normalized_relief: float
    effect: float
    weighted_effect: float
    conflict_pressure: float = 0.0

    def to_dict(self):
        value = {
            "effect": float(self.effect),
            "goal_id": self.goal_id,
            "normalized_relief": float(self.normalized_relief),
            "pressure": float(self.pressure),
            "weighted_effect": float(self.weighted_effect),
        }
        if self.conflict_pressure:
            value["conflict_pressure"] = float(self.conflict_pressure)
        return value


@dataclass(frozen=True)
class OperationScore:
    operation: Operation
    admissible: bool
    reason: object
    priority: float
    value: float
    scalar_cost: float
    conflict_penalty: float
    goal_effects: tuple
    risk_penalty: float = 0.0
    risk_traces: tuple = ()

    @property
    def operation_id(self):
        return self.operation.operation_id

    def to_dict(self):
        value = {
            "admissible": bool(self.admissible),
            "conflict_penalty": float(self.conflict_penalty),
            "goal_effects": [row.to_dict() for row in self.goal_effects],
            "operation": self.operation.to_dict(),
            "priority": float(self.priority),
            "reason": self.reason,
            "scalar_cost": float(self.scalar_cost),
            "value": float(self.value),
        }
        if self.risk_penalty or self.risk_traces:
            value["risk_penalty"] = float(self.risk_penalty)
            value["risk_traces"] = [
                row.to_dict() for row in self.risk_traces]
        return value


@dataclass(frozen=True)
class BudgetAllocation:
    operation_id: str
    budget: float
    priority: float

    def to_dict(self):
        return {
            "budget": float(self.budget),
            "operation_id": self.operation_id,
            "priority": float(self.priority),
        }


class PressureScheduler(object):
    """Ranks expected goal-loss relief; operation cost is applied only here."""

    SOLVER_IDENTITY = "pf-pln-pressure-scheduler/1.0"

    def __init__(self, config=None):
        self.config = config or PressureConfig()
        if not isinstance(self.config, PressureConfig):
            raise TypeError("pressure scheduler config must be PressureConfig")

    @staticmethod
    def _goal_weights(goals):
        denominator = sum(goal.weight_basis for goal in goals)
        if denominator <= 0:
            return dict((goal.goal_id, 0.0) for goal in goals)
        return dict(
            (goal.goal_id, goal.weight_basis / denominator) for goal in goals)

    def score(self, operation, pressure_result):
        if not isinstance(operation, Operation):
            raise TypeError("score accepts Operation")
        goals = tuple(pressure_result.goals)
        goal_by_id = dict((goal.goal_id, goal) for goal in goals)
        weights = self._goal_weights(goals)

        if (operation.mode == "act"
                and operation.causal_kind not in ACTION_CAUSAL_KINDS):
            return OperationScore(
                operation, False, "causal_firewall", 0.0, 0.0,
                operation.cost.scalar(self.config.cost_weights), 0.0, ())
        if (operation.deadline_estimate is not None
                and operation.deadline_estimate.hard_gate):
            return OperationScore(
                operation, False,
                "deadline_firewall:{}".format(
                    operation.deadline_estimate.gate_reason),
                0.0, 0.0,
                operation.cost.scalar(self.config.cost_weights), 0.0, ())

        signed_value = 0.0
        conflict_penalty = 0.0
        risk_penalty = 0.0
        risk_traces = []
        risk_gate_reason = None
        effects = []
        safety_harm = False
        for goal_id in sorted(goal_by_id):
            goal = goal_by_id[goal_id]
            vector = pressure_result.pressure(goal_id, operation.atom_id)
            channel_conflict = 0.0
            if isinstance(vector, SignedPressureVector):
                channel_pressure = abs(vector.net(operation.mode))
                channel_conflict = vector.conflict(operation.mode)
            else:
                channel_pressure = vector.value(operation.mode)
            relief = (
                channel_pressure * operation.success_probability
                * operation.relief_scale)
            # Goal demand already contains U*h.  Divide it out before applying
            # the declared scheduling weight so utility is counted exactly once.
            normalized = relief / goal.weight_basis if goal.weight_basis else 0.0
            effect = operation.effect_for(goal_id)
            weighted = weights[goal_id] * normalized * effect
            signed_value += weighted
            if channel_conflict:
                normalized_conflict = (
                    channel_conflict / goal.weight_basis
                    if goal.weight_basis else 0.0)
                conflict_penalty += (
                    weights[goal_id] * normalized_conflict)
            if weighted < 0:
                conflict_penalty += abs(weighted)
                safety_harm = safety_harm or goal.safety
            effects.append(GoalEffect(
                goal_id, channel_pressure, normalized, effect, weighted,
                channel_conflict))
            estimate = operation.risk_estimate_for(goal_id)
            if estimate is not None:
                profile = goal.effective_risk_profile
                goal_risk_penalty = (
                    weights[goal_id] * profile.aversion
                    * estimate.tail_loss)
                risk_penalty += goal_risk_penalty
                gate_reason = None
                if (profile.max_expected_loss is not None
                        and estimate.expected_loss
                        > profile.max_expected_loss):
                    gate_reason = "max_expected_loss"
                if (profile.max_tail_loss is not None
                        and estimate.tail_loss > profile.max_tail_loss):
                    gate_reason = "max_tail_loss"
                hard_gate = bool(
                    gate_reason is not None
                    and profile.hard_gate
                    and goal.safety
                    and (not operation.reversible
                         or operation.externally_consequential))
                if hard_gate and risk_gate_reason is None:
                    risk_gate_reason = "risk_tail_firewall:{}".format(
                        gate_reason)
                risk_traces.append(RiskTrace(
                    goal_id=goal_id,
                    operation_id=operation.operation_id,
                    expected_loss=estimate.expected_loss,
                    tail_loss=estimate.tail_loss,
                    confidence=estimate.confidence,
                    aversion=profile.aversion,
                    penalty=goal_risk_penalty,
                    hard_gate=hard_gate,
                    gate_reason=gate_reason,
                    provenance=estimate.provenance))

        if (not operation.safety_compatible
                and any(goal.safety for goal in goals)):
            safety_harm = True
        if safety_harm:
            return OperationScore(
                operation, False, "safety_firewall", 0.0, 0.0,
                operation.cost.scalar(self.config.cost_weights),
                conflict_penalty, tuple(effects),
                risk_penalty, tuple(risk_traces))
        if risk_gate_reason is not None:
            return OperationScore(
                operation, False, risk_gate_reason, 0.0, 0.0,
                operation.cost.scalar(self.config.cost_weights),
                conflict_penalty, tuple(effects),
                risk_penalty, tuple(risk_traces))

        value = (
            signed_value - conflict_penalty - risk_penalty
            + self.config.information_gain_weight * operation.information_gain
            + self.config.coherence_weight * operation.coherence_gain
            + self.config.future_option_weight * operation.future_option_value)
        scalar_cost = operation.cost.scalar(self.config.cost_weights)
        priority = (
            value * operation.feasibility
            * operation.effective_deadline_fit
            / (scalar_cost + self.config.cost_epsilon)
            - operation.redundancy - operation.contradiction_risk)
        return OperationScore(
            operation, True, None, priority, value, scalar_cost,
            conflict_penalty, tuple(effects),
            risk_penalty, tuple(risk_traces))

    def score_all(self, operations, pressure_result):
        rows = [self.score(operation, pressure_result)
                for operation in operations]
        return tuple(sorted(rows, key=lambda row: (
            not row.admissible, -row.priority, row.operation_id)))

    def select(self, operations, pressure_result):
        rows = self.score_all(operations, pressure_result)
        return next((row for row in rows if row.admissible), None)

    def allocate(
            self, operations, pressure_result, total_budget,
            scores=None):
        total_budget = float(total_budget)
        if total_budget < 0 or not math.isfinite(total_budget):
            raise ValueError("budget must be finite and nonnegative")
        ranked = (
            self.score_all(operations, pressure_result)
            if scores is None else tuple(scores))
        admissible = [row for row in ranked if row.admissible]
        if not admissible or total_budget == 0:
            return ()
        maximum = max(row.priority for row in admissible)
        masses = [
            math.exp((row.priority - maximum)
                     / self.config.softmax_temperature)
            for row in admissible]
        denominator = sum(masses)
        return tuple(BudgetAllocation(
            row.operation_id, total_budget * mass / denominator, row.priority)
            for row, mass in zip(admissible, masses))

    def decision_artifact(
            self, operations, pressure_result, total_budget=1.0,
            scores=None, pressure_artifact=None):
        scores = (
            self.score_all(operations, pressure_result)
            if scores is None else tuple(scores))
        selection = next((row for row in scores if row.admissible), None)
        value = {
            "allocations": [
                row.to_dict() for row in self.allocate(
                    operations, pressure_result, total_budget,
                    scores=scores)],
            "pressure_hash": (
                pressure_result.artifact_hash
                if pressure_artifact is None else
                structural_hash(pressure_artifact)),
            "scores": [row.to_dict() for row in scores],
            "selected_operation_id": (
                None if selection is None else selection.operation_id),
            "solver_identity": self.SOLVER_IDENTITY,
        }
        value["structural_hash"] = structural_hash(value)
        return value
