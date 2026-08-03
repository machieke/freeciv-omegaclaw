import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_ruleset_defensive_opportunity_cohort import (  # noqa: E402
    _wilson,
    _yield_classification,
)


def _measures(**overrides):
    result = {
        "cross_type_comparisons": 1,
        "cross_type_defensive_comparable": 1,
        "grounded_alternatives": 1,
        "grounded_noninferior_alternatives": 1,
        "interval_separated_alternatives": 1,
        "readouts": 10,
        "shadow_preferences": 1,
    }
    result.update(overrides)
    return result


def test_wilson_interval_bounds_sparse_game_rate():
    interval = _wilson(1, 16)

    assert interval["confidence"] == 0.95
    assert interval["lower"] < interval["point"] == 0.0625
    assert interval["point"] < interval["upper"] < 0.5


def test_yield_classification_names_first_empty_stage():
    assert _yield_classification(_measures(
        interval_separated_alternatives=0,
        shadow_preferences=0)) == "no-interval-separation-yield"
    assert _yield_classification(_measures(
        cross_type_comparisons=0,
        cross_type_defensive_comparable=0,
        grounded_noninferior_alternatives=0,
        interval_separated_alternatives=0,
        shadow_preferences=0)) == "no-cross-type-yield"


def test_yield_classification_reports_observed_preference():
    assert _yield_classification(_measures()) == (
        "shadow-preference-observed")
