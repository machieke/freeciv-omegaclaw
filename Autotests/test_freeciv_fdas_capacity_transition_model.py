import copy
import json
import os

import pytest

from freeciv.harness.fdas_retained_capacity_transition_model_fit import (
    audit_fdas_retained_capacity_transition_model_fit,
)
from freeciv_agent.planning import (
    FdasRetainedCapacityTargetPrediction,
    FdasRetainedCapacityTransitionModel,
    RETAINED_CAPACITY_PRODUCT_TARGET,
)
from freeciv_agent.planning.fdas_capacity_transition_model import (
    _bootstrap_interval,
    fit_retained_capacity_transition_model,
)


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(
    REPO, "docs", "freeciv", "evidence",
    "fdas-pr98-retained-capacity-transition-discovery.json")


@pytest.fixture(scope="module")
def source_report():
    with open(SOURCE, encoding="utf-8") as stream:
        return json.load(stream)


@pytest.fixture(scope="module")
def fit_report(source_report):
    return audit_fdas_retained_capacity_transition_model_fit(source_report)


def test_pr99_transition_model_fit_is_complete_and_authority_free(fit_report):
    assert fit_report["acceptance"]["accepted"] is True
    assert fit_report["summary"] == {
        "excluded_censored_rows": 1,
        "fitted_bins": 156,
        "goal_relief_predictions": {"abstained": 0, "estimated": 163},
        "numerically_usable_bins": 12,
        "prediction_selected_levels": {
            "category-lifecycle": 22,
            "category-lifecycle-product": 17,
            "category-lifecycle-product-phase-horizon": 124,
        },
        "product_effect_predictions": {"abstained": 0, "estimated": 163},
        "sample_eligible_bins": 12,
        "source_games": 301,
        "source_query_rows": 163,
        "training_terminal_rows": 162,
    }
    assert fit_report["model"]["result_hash"] == (
        "909e8170d9dc797f69b71337243633ddd5fd5e007a7627c44e150d0a05439a6f")
    assert all(fit_report[name] is False for name in (
        "action_authority", "calibrated", "learning_write_through",
        "policy_authority", "readout_authority", "truth_mutated"))


def test_pr99_transition_model_roundtrips_and_recomputes_bins(fit_report):
    model = FdasRetainedCapacityTransitionModel.from_dict(fit_report["model"])

    assert model.to_dict() == fit_report["model"]
    assert len(model.source_games) == 301
    assert len(model.training_rows) == 162
    assert len(model.excluded_rows) == 1
    assert sum(value.sample_eligible for value in model.bins) == 12
    assert sum(value.numerically_usable for value in model.bins) == 12


def test_pr99_transition_model_rejects_source_target_and_interval_tampering(
        source_report, fit_report):
    changed_source = copy.deepcopy(source_report)
    changed_source["summary"]["terminal_rows"] += 1
    with pytest.raises(ValueError, match="PR98 source differs"):
        fit_retained_capacity_transition_model(changed_source)

    changed_model_source = copy.deepcopy(fit_report["model"])
    changed_model_source["source"]["dataset_hash"] = "tampered"
    with pytest.raises(ValueError, match="model contract differs"):
        FdasRetainedCapacityTransitionModel.from_dict(changed_model_source)

    changed_target = copy.deepcopy(fit_report["model"])
    changed_target["training_rows"][0]["durable_goal_relief"] = 1
    with pytest.raises(ValueError, match="training target differs"):
        FdasRetainedCapacityTransitionModel.from_dict(changed_target)

    changed_interval = copy.deepcopy(fit_report["model"])
    eligible = next(
        value for value in changed_interval["bins"]
        if value["sample_eligible"])
    eligible["interval_upper"] -= 0.01
    eligible["interval_width"] -= 0.01
    with pytest.raises(ValueError, match="model interval differs"):
        FdasRetainedCapacityTransitionModel.from_dict(changed_interval)


def test_pr99_bootstrap_is_exact_and_abstention_cannot_leak_value():
    first = _bootstrap_interval((0.0, 1.0, 1.0, 0.0))
    second = _bootstrap_interval((0.0, 1.0, 1.0, 0.0))

    assert first == second == (0.5, 0.0, 1.0)
    with pytest.raises(ValueError, match="leaks value"):
        FdasRetainedCapacityTargetPrediction(
            RETAINED_CAPACITY_PRODUCT_TARGET, "abstained",
            "selected-level-interval-too-wide", "bin", 0.5, 0.2, 0.8, 20)
