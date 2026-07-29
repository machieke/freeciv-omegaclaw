"""Expected-transition, residual-risk, isolation, and calibration gates."""

import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    CostVector,
    DeclaredFallbackTransitionModel,
    ExpectedTransition,
    Operation,
    PredictedOutcome,
    ProjectionTransitionModel,
    TransitionCalibrationLedger,
    TransitionCalibrationRecord,
    TransitionModelRegistry,
    TruthState,
)


def _operation(category="production_economy", probability=0.75):
    return Operation(
        "operation-1", "target-1", "act",
        CostVector(compute=1.0),
        causal_kind="procedural",
        success_probability=probability,
        payload={
            "category": category,
            "projection": {
                "completion_eta_turns": 4,
                "cost_source": "ruleset-ir",
                "next_goal_cost_to_go": {"pf-impact:score": 0.25},
                "resource_delta": {"shields": -20},
                "risk_estimate": {"expected_loss": 0.1},
            },
        })


def test_expected_transition_probabilities_and_residual_sum_to_one():
    registry = TransitionModelRegistry()
    registry.register(
        "production_economy",
        ProjectionTransitionModel(
            "production-transition/1.0",
            "production-economy",
            fallback_loss=2.0))

    transition = registry.predict({"turn": 10}, _operation())

    assert transition.modeled_probability == 0.75
    assert transition.residual_probability == 0.25
    assert (
        transition.modeled_probability
        + transition.residual_probability == 1.0)
    assert transition.outcomes[0].completion_turn == 14
    assert transition.outcomes[0].resource_delta == (
        ("shields", -20.0),)


def test_unknown_outcome_mass_receives_conservative_loss():
    outcome = PredictedOutcome(
        "success", 0.5, (), (("goal", 1.0),), (),
        None, 0.0, ("grounded-test",))
    transition = ExpectedTransition(
        "operation", (outcome,), 0.5,
        "model", "group",
        residual_goal_losses=(("*", 8.0),))

    assert transition.expected_cost_to_go("goal") == 4.5
    assert transition.expected_cost_to_go("unmodeled-goal") == 8.0


def test_transition_model_does_not_mutate_snapshot():
    class MutatingModel:
        model_id = "mutating-test-model"

        def predict(self, snapshot, operation):
            snapshot["turn"] = 999
            return ExpectedTransition(
                operation.operation_id, (), 1.0,
                self.model_id, "test",
                residual_goal_losses=(("*", 1.0),))

    snapshot = {"turn": 10, "cities": {"1": {"size": 3}}}
    registry = TransitionModelRegistry()
    registry.register("production_economy", MutatingModel())

    registry.predict(snapshot, _operation())

    assert snapshot == {"turn": 10, "cities": {"1": {"size": 3}}}


def test_realized_outcome_calibrates_control_model_not_truth():
    truth = TruthState(0.4, 0.7)
    ledger = TransitionCalibrationLedger()
    record = TransitionCalibrationRecord(
        operation_id="operation-1",
        operation_kind="production_economy",
        model_id="production-transition/1.0",
        calibration_group="production-economy",
        horizon="short",
        context="peace",
        risk_class="routine",
        predicted_success_probability=0.75,
        realized_success=True,
        predicted_completion_turn=14,
        realized_completion_turn=15,
        predicted_goal_relief=(("pf-impact:score", 0.75),),
        realized_goal_relief=(("pf-impact:score", 0.5),),
        predicted_resource_use=(("shields", 20.0),),
        realized_resource_use=(("shields", 21.0),),
        predicted_adverse_loss=0.1,
        realized_adverse_loss=0.0,
        predicted_information_gain=0.0,
        realized_information_gain=0.0,
    )

    ledger.append(record)

    assert truth == TruthState(0.4, 0.7)
    assert record.update_scope == "control-model-only"
    assert ledger.reliability_curves()[
        "production_economy|short|peace|routine"][
            "mean_realized_success"] == 1.0


def test_missing_model_uses_declared_fallback():
    registry = TransitionModelRegistry(
        DeclaredFallbackTransitionModel(fallback_loss=3.5))

    transition = registry.predict(
        {"turn": 10}, _operation(category="unregistered"))

    assert transition.model_id == (
        "declared-conservative-fallback/1.0")
    assert transition.outcomes == ()
    assert transition.residual_probability == 1.0
    assert transition.expected_cost_to_go("any-goal") == 3.5
    assert transition.calibration_group == (
        "missing-model:unregistered")


def test_invalid_distribution_and_zero_unknown_loss_are_rejected():
    outcome = PredictedOutcome(
        "success", 0.7, (), (), (), None, 0.0,
        ("grounded-test",))

    try:
        ExpectedTransition(
            "operation", (outcome,), 0.2,
            "model", "group", (("*", 1.0),))
    except ValueError as error:
        assert "sum to one" in str(error)
    else:
        raise AssertionError("invalid distribution was accepted")

    try:
        ExpectedTransition(
            "operation", (), 1.0,
            "model", "group", (("*", 0.0),))
    except ValueError as error:
        assert "positive" in str(error)
    else:
        raise AssertionError("zero unknown loss was accepted")
