import copy
import json
import os

import pytest

from freeciv.harness.fdas_retained_capacity_transition_confirmation import (
    _bootstrap_mean,
    _frozen_model,
    audit_fdas_retained_capacity_transition_confirmation,
    retained_capacity_transition_confirmation_metrics,
)
from freeciv_agent.planning.fdas_capacity_transition_model import (
    FdasRetainedCapacityTransitionPrediction,
)


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_REPORT = os.path.join(
    REPO, "docs", "freeciv", "evidence",
    "fdas-pr99-retained-capacity-transition-model.json")


@pytest.fixture(scope="module")
def model_report():
    with open(MODEL_REPORT, encoding="utf-8") as stream:
        return json.load(stream)


@pytest.fixture(scope="module")
def discovery_evaluation(model_report):
    model = _frozen_model(model_report)
    rows = tuple({
        "observation_status": value["observation_status"],
        "outcome_status": value["outcome_status"],
        "prediction": FdasRetainedCapacityTransitionPrediction.from_dict(
            value["prediction"]),
        "row_id": value["row_id"],
        "seed": value["seed"],
    } for value in model_report["prediction_rows"])
    return model, rows


def test_confirmation_metrics_reproduce_discovery_feasibility_dry_run(
        discovery_evaluation):
    model, rows = discovery_evaluation

    metrics = retained_capacity_transition_confirmation_metrics(rows, model)

    assert metrics["decision"] == "confirmed"
    assert metrics["bin_confirmation"]["contained_groups"] == 6
    assert metrics["bin_confirmation"]["containment_rate"] == 1.0
    assert metrics["bin_confirmation"]["qualifying_groups"] == 6
    assert all(metrics["checks"].values())
    assert metrics["overall"]["durable-goal-relief"][
        "model_minus_root_brier"]["estimate"] < 0.0
    assert metrics["overall"]["exact-product-effect"][
        "numerical_coverage"]["rate"] == 1.0


def test_confirmation_metrics_fail_closed_without_bin_recurrence(
        discovery_evaluation):
    model, rows = discovery_evaluation
    seeds = sorted({value["seed"] for value in rows})[:3]
    sparse = tuple(value for value in rows if value["seed"] in seeds)

    metrics = retained_capacity_transition_confirmation_metrics(sparse, model)

    assert metrics["decision"] == "not-confirmed"
    assert metrics["checks"][
        "at_least_four_selected_target_bins_have_20_confirmation_games"] is False


def test_confirmation_bootstrap_and_model_source_are_deterministic(
        model_report):
    assert _bootstrap_mean((0.0, 1.0, 1.0, 0.0)) == (
        _bootstrap_mean((0.0, 1.0, 1.0, 0.0)))
    changed = copy.deepcopy(model_report)
    changed["summary"]["fitted_bins"] += 1
    with pytest.raises(ValueError, match="frozen PR99 model differs"):
        _frozen_model(changed)


def test_confirmation_requires_exact_fixed_cohort():
    with pytest.raises(ValueError, match="requires 301 seeds"):
        audit_fdas_retained_capacity_transition_confirmation(
            "unused", tuple(range(300)), "commit", {})
