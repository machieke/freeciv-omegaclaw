"""Expected goal relief integrates canonical outcome probabilities once."""

import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    ExpectedTransition,
    PredictedOutcome,
    typed_expected_relief,
)


def test_expected_relief_probability_is_integrated_exactly_once():
    transition = ExpectedTransition(
        "operation",
        (PredictedOutcome(
            "success", 0.5, (),
            (("goal", 2.0),), (), None, 0.0,
            ("grounded-test",)),),
        0.5, "model", "group",
        residual_goal_losses=(("*", 10.0),))

    # 0.5 * (10 - 2) = 4. Multiplying success again would incorrectly give 2.
    assert typed_expected_relief(
        transition, "goal", 10.0) == 4.0


def test_unknown_mass_gets_no_invented_positive_relief():
    transition = ExpectedTransition(
        "operation", (), 1.0, "model", "group",
        residual_goal_losses=(("*", 3.0),))

    assert typed_expected_relief(
        transition, "goal", 10.0,
        unknown_policy="neutral") == 0.0
    assert typed_expected_relief(
        transition, "goal", 10.0,
        unknown_policy="adverse") == -3.0


def test_modeled_adverse_loss_is_charged_once():
    transition = ExpectedTransition(
        "operation",
        (PredictedOutcome(
            "success", 1.0, (),
            (("goal", 4.0),), (), None, 1.5,
            ("grounded-test",)),),
        0.0, "model", "group",
        residual_goal_losses=(("*", 10.0),))

    assert typed_expected_relief(
        transition, "goal", 10.0) == 4.5
