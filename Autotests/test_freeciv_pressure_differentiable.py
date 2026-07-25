"""Delimited differentiable PF-PLN truth and pressure characterization."""

import os
import sys
import tempfile

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.pressure import (  # noqa: E402
    DifferentiableTruthRule,
    LearnableRuleParameter,
    TensorTruth,
    adjoint_pressure,
    characterize_threshold,
    counterfactual_pressure,
    finite_difference_adjoint,
    learn_rule_parameter,
    requirement_pressure,
)


def test_tensor_truth_autodiff_is_pressure_free_and_exact():
    truth = TensorTruth.leaf("enemy", 0.8, 0.5, ("observation-1",))
    gradients = truth.supported.backward()
    assert truth.to_dict() == {
        "confidence": 0.5,
        "evidence_ids": ["observation-1"],
        "strength": 0.8,
    }
    assert gradients["enemy.strength"] == pytest.approx(0.5)
    assert gradients["enemy.confidence"] == pytest.approx(0.8)


@pytest.mark.parametrize("kind", ("product-and", "probabilistic-or"))
def test_smooth_adjoint_matches_centered_finite_difference(kind):
    rule = DifferentiableTruthRule("rule:" + kind, kind)
    values = (("left", 0.4), ("right", 0.8))
    exact = adjoint_pressure(rule, values, target=1.0)
    numerical = dict(finite_difference_adjoint(
        rule, values, target=1.0, epsilon=1e-6))
    assert exact.incoming > 0
    for premise_id, pressure in exact.premise_rows:
        assert pressure == pytest.approx(
            numerical[premise_id], rel=1e-9, abs=1e-9)


def test_dead_and_gate_needs_requirement_and_coalitional_counterfactual():
    rule = DifferentiableTruthRule("rule:dead-and", "product-and")
    values = (("left", 0.0), ("right", 0.0))
    adjoint = adjoint_pressure(rule, values)
    requirement = dict(requirement_pressure(values, incoming=1.0))
    counterfactual = counterfactual_pressure(rule, values)
    assert adjoint.pressure("left") == 0
    assert adjoint.pressure("right") == 0
    assert requirement == {"left": 0.5, "right": 0.5}
    assert dict(counterfactual.individual_rows) == {
        "left": 0.0, "right": 0.0}
    assert counterfactual.coalition_gain == 1.0


def test_threshold_is_explicitly_outside_adjoint_subset():
    blocked = characterize_threshold(4, threshold=5, achievable=5)
    assert not blocked.adjoint_available
    assert blocked.baseline == 0
    assert blocked.requirement == 1
    assert blocked.counterfactual_gain == 1
    ready = characterize_threshold(5, threshold=5, achievable=5)
    assert ready.requirement == 0
    assert ready.counterfactual_gain == 0
    with pytest.raises(ValueError, match="outside"):
        DifferentiableTruthRule("threshold", "threshold")


def test_reverse_mode_parameter_learning_reduces_loss_and_emits_event():
    parameter = LearnableRuleParameter("rule:reliability", 0.2)
    examples = ((0.2, 0.16), (0.5, 0.4), (0.8, 0.64), (1.0, 0.8))
    updated, record = learn_rule_parameter(
        parameter, examples, learning_rate=0.5)
    assert updated.value > parameter.value
    assert record.posterior_loss < record.prior_loss
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(
            path, "differentiable-test", durable=False,
            clock=lambda: "2026-07-25T00:00:00Z",
            id_factory=lambda: "parameter-event")
        record.emit(writer, 1)
        report = validate_file(path)
        assert report.valid, report.errors
    _, bounded = learn_rule_parameter(
        parameter, ((1.0, 0.3),), learning_rate=100.0)
    assert bounded.posterior_loss <= bounded.prior_loss
    assert bounded.learning_rate < 100.0
