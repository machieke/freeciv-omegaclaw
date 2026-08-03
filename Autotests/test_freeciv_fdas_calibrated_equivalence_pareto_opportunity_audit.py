import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_calibrated_equivalence_pareto_opportunity import (  # noqa: E402
    _yield_classification,
)


def _measures(**overrides):
    value = {
        "equivalence_pareto_preferences": 1,
        "grounded_alternatives": 2,
        "interval_separated_preferences": 0,
        "readouts": 10,
        "shadow_preferences": 1,
        "strict_improvement_alternatives": 1,
    }
    value.update(overrides)
    return value


def test_yield_classification_reports_first_empty_stage():
    assert _yield_classification(_measures(
        strict_improvement_alternatives=0,
        equivalence_pareto_preferences=0)) == (
        "no-strict-grounded-improvement-yield")


def test_yield_classification_reports_preference():
    assert _yield_classification(_measures()) == (
        "equivalence-pareto-preference-observed")
