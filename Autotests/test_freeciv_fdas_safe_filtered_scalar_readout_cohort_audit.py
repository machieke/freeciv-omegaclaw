import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_safe_filtered_scalar_readout_cohort import (  # noqa: E402
    _cohort_gates,
)


def test_safe_filtered_cohort_requires_real_grounded_alternative():
    parent = {
        "games": [
            {"measures": {
                "grounded_controls": 2,
                "readout_grounded_alternatives": 1,
            }},
            {"measures": {
                "grounded_controls": 0,
                "readout_grounded_alternatives": 0,
            }},
        ],
        "passed": True,
        "totals": {
            "readout_grounded_alternatives": 1,
            "union_additions": 1,
        },
    }

    gates, alternative_games, control_games = _cohort_gates(parent)

    assert all(gates.values())
    assert alternative_games == 1
    assert control_games == 1


def test_safe_filtered_cohort_rejects_addition_without_grounded_comparison():
    parent = {
        "games": [{"measures": {
            "grounded_controls": 1,
            "readout_grounded_alternatives": 0,
        }}],
        "passed": True,
        "totals": {
            "readout_grounded_alternatives": 0,
            "union_additions": 3,
        },
    }

    gates, _alternative_games, _control_games = _cohort_gates(parent)

    assert gates["calibrated_addition_observed"] is True
    assert gates["grounded_alternative_compared"] is False
    assert gates["grounded_alternative_game_observed"] is False
