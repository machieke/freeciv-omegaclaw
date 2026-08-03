from copy import deepcopy

import pytest

from freeciv.harness.fdas_randomized_power import (
    plan_randomized_candidate_value,
)


def _report():
    games = []
    assignments = (
        (1, 0), (3, 3), (0, 1),
        (0, 0), (0, 0), (0, 0),
        (0, 0), (0, 0), (0, 0),
        (0, 0), (0, 0), (0, 0),
    )
    for control, treatment in assignments:
        games.append({
            "status_counts": {
                "assignments": control + treatment,
                "control": control,
                "positive_outcomes": control,
                "treatment": treatment,
            },
        })
    return {
        "games": games,
        "outcome_summary": {"risk_difference": -0.75},
        "passed": True,
        "positive_outcomes": 5,
    }


def test_power_plan_uses_only_yield_and_is_outcome_direction_invariant():
    report = _report()
    plan = plan_randomized_candidate_value(
        report, mean_engine_seconds_per_game=300)
    changed = deepcopy(report)
    changed["positive_outcomes"] = 0
    changed["outcome_summary"]["risk_difference"] = 1.0
    for game in changed["games"]:
        game["status_counts"]["positive_outcomes"] = 0

    assert plan == plan_randomized_candidate_value(
        changed, mean_engine_seconds_per_game=300)
    assert plan["outcome_direction_used"] is False
    assert plan["assignments_per_arm"] == 44
    assert plan["planned_games"] == 168
    assert plan["minimum_game_clusters_per_arm"] == 20
    assert plan["estimated_wall_hours"] == pytest.approx(3.5)


def test_power_plan_rejects_failed_or_single_arm_yield():
    report = _report()
    report["passed"] = False
    with pytest.raises(ValueError, match="passed yield audit"):
        plan_randomized_candidate_value(report)

    report = _report()
    for game in report["games"]:
        game["status_counts"]["treatment"] = 0
        game["status_counts"]["assignments"] = game["status_counts"][
            "control"]
    with pytest.raises(ValueError, match="both randomized arms"):
        plan_randomized_candidate_value(report)
