"""First-class teleology, fallback, and cost-accounting gates."""

import os
import sys
from dataclasses import replace
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    AtomState,
    CostToGoEstimate,
    CostVector,
    GoalLoss,
    GoalState,
    ImmediateLossEstimator,
    LeverageEstimate,
    Operation,
    PressureEngineV2,
    PressureGraph,
    PressureMagnitude,
    PressureScheduler,
    Resolvability,
    SignedPressureVector,
    TruthState,
    TypedAdvantage,
)


def _result(goal, pressures):
    return SimpleNamespace(
        goals=(goal,),
        config=PressureEngineV2().config,
        artifact_hash="teleology-pressure",
        pressure=lambda goal_id, atom_id: SignedPressureVector(
            positive=PressureMagnitude(
                act=float(pressures[atom_id]))))


def test_immediate_loss_and_cost_to_go_are_distinct_types():
    estimator = ImmediateLossEstimator()
    goal = GoalState("goal", "target", utility=4.0)
    loss = estimator.goal_loss(
        goal, TruthState(0.5, 0.75))
    cost_to_go = estimator.cost_to_go(loss, horizon=5)

    assert isinstance(loss, GoalLoss)
    assert isinstance(cost_to_go, CostToGoEstimate)
    assert loss.total == 2.25
    assert cost_to_go.expected_loss == loss.total
    assert cost_to_go.lower_bound <= cost_to_go.expected_loss
    assert cost_to_go.upper_bound >= cost_to_go.expected_loss


def test_cost_to_go_fallback_matches_scalar_v2_ordering():
    estimator = ImmediateLossEstimator()
    goal = GoalState("goal", "target", utility=2.0)
    result = _result(goal, {"high": 2.0, "low": 1.0})
    operations = (
        Operation(
            "low", "low", "act", CostVector(compute=1.0),
            causal_kind="procedural"),
        Operation(
            "high", "high", "act", CostVector(compute=1.0),
            causal_kind="procedural"),
    )
    scheduler = PressureScheduler()
    scalar = scheduler.score_all(operations, result)
    typed = tuple(
        replace(
            operation,
            typed_advantages=(
                estimator.advantage(
                    operation, result, goal.goal_id),))
        for operation in operations)
    teleological = scheduler.score_all(typed, result)

    assert [row.operation_id for row in scalar] == [
        row.operation_id for row in teleological]
    assert teleological[0].operation_id == "high"


def test_typed_advantage_is_pre_cost():
    advantage = TypedAdvantage(
        "goal", "target", "act",
        expected_relief=3.0, relief_variance=0.2,
        information_gain=0.5, option_value=0.25,
        predicted_latency=2.0,
        predicted_resource_use=(("cpu", 4.0),),
        estimator_id="test-estimator")

    assert advantage.pre_cost_value == 3.75
    assert "cost" not in advantage.to_dict()
    assert advantage.to_dict()["predicted_resource_use"] == {
        "cpu": 4.0}


def test_operation_score_applies_cost_exactly_once():
    goal = GoalState("goal", "target")
    result = _result(goal, {"target": 1.0})
    advantage = TypedAdvantage(
        "goal", "target", "act",
        expected_relief=2.0, relief_variance=0.0,
        information_gain=0.0, option_value=0.0,
        predicted_latency=0.0,
        predicted_resource_use=(),
        estimator_id="test-estimator")
    operation = Operation(
        "operation", "target", "act",
        CostVector(compute=2.0), causal_kind="procedural",
        typed_advantages=(advantage,))

    score = PressureScheduler().score(operation, result)

    assert score.value == 2.0
    assert score.scalar_cost == 2.0
    assert score.priority == (
        score.value / (
            score.scalar_cost + result.config.cost_epsilon))


def test_cross_goal_loss_scales_are_not_silently_normalized_in_engine():
    graph = PressureGraph()
    graph.add_atom(
        AtomState("target", TruthState(0.0, 1.0)),
        Resolvability(act=1.0))
    small = GoalState("small", "target", utility=1.0)
    large = GoalState("large", "target", utility=10.0)

    result = PressureEngineV2().propagate(
        graph, (small, large))

    assert result.demand("small").achievement == 1.0
    assert result.demand("large").achievement == 10.0
    assert result.achievement_dependency(
        "large", "target") == 10.0 * (
        result.achievement_dependency("small", "target"))


def test_uncalibrated_estimator_is_labeled_in_artifact():
    estimator = ImmediateLossEstimator()
    loss = estimator.goal_loss(
        GoalState("goal", "target"),
        TruthState(0.0, 0.5))
    estimate = estimator.cost_to_go(loss)
    leverage = LeverageEstimate(
        "goal", "target", 1.0,
        "immediate-loss-fallback", 0.5,
        ("no-transition-model",))

    assert not estimate.calibrated
    assert estimate.estimator_id == (
        "immediate-loss-fallback/1.0")
    assert estimate.to_dict()["calibrated"] is False
    assert leverage.to_dict()["assumptions"] == [
        "no-transition-model"]
