import json
import os

from freeciv.harness.fdas_retained_capacity_decision_safe_readout import (
    audit_fdas_retained_capacity_decision_safe_readout,
)


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(
    REPO, "docs", "freeciv", "evidence",
    "fdas-pr99-retained-capacity-transition-model.json")
CONFIRMATION = os.path.join(
    REPO, "docs", "freeciv", "evidence",
    "fdas-pr100-retained-capacity-transition-confirmation.json")


def _load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def test_pr101_frozen_readout_feasibility_is_deterministic_and_closed():
    model = _load(MODEL)
    confirmation = _load(CONFIRMATION)

    first = audit_fdas_retained_capacity_decision_safe_readout(
        model, confirmation)
    second = audit_fdas_retained_capacity_decision_safe_readout(
        model, confirmation)

    assert first == second
    assert first["acceptance"]["accepted"] is True
    assert first["decision"] == "not-ready"
    assert first["summary"] == {
        "decision_safe_interval_pairs": 0,
        "joint_usable_target_bins": 6,
        "nonselected_outcomes_confirmed": False,
        "ordered_pair_checks": 30,
        "strict_relief_interval_pairs": 0,
    }
    checks = first["feasibility"]["checks"]
    assert checks["frozen_pr99_model_is_exact_and_typed"] is True
    assert checks["frozen_pr100_confirmation_is_exact_and_accepted"] is True
    assert checks["at_least_one_strict_relief_interval_pair"] is False
    assert checks["nonselected_candidate_outcomes_are_confirmed"] is False
    assert all(first[name] is False for name in (
        "action_authority", "candidate_surface_changed", "policy_authority",
        "pressure_selection_changed", "readout_authority", "truth_mutated"))
