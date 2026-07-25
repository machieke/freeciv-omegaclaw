"""Canonical PF-PLN Phase 9 conflicting-goal acceptance."""

import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for candidate in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks"),
):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from freeciv.pf_multi_goal_benchmark import (  # noqa: E402
    run_multi_goal_benchmark,
)


def test_multi_goal_scheduler_beats_independent_goal_scheduling():
    first = run_multi_goal_benchmark()
    second = run_multi_goal_benchmark()
    assert first == second
    assert all(first["acceptance"].values())
    assert first["multi_goal_wins"] == 64
    assert first["mean_joint_relief_gain"] > 0
    with open(os.path.join(
            REPO, "docs", "freeciv", "evidence",
            "pf-multi-goal-phase-9.json"), encoding="utf-8") as stream:
        assert json.load(stream) == first
