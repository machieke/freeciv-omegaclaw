import os
import sys
from dataclasses import replace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    CANDIDATE_TRANSITION_FEATURE_KEYS,
    CANDIDATE_TRANSITION_FEATURE_SCHEMA,
    DEFENSE_CANDIDATE_CHOICE_SURFACE,
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    FdasCandidateChoiceCalibrationExport,
    FdasCandidateTransitionCalibrationModel,
    evaluate_candidate_transition_calibration,
    fit_candidate_transition_calibration,
)
from freeciv_agent.pressure import (  # noqa: E402
    InductionEpisode,
    InductionFeatureQuery,
)


MOVE = "fdas-shadow:city-garrison-deficit:unit_move"
FORTIFY = "fdas-shadow:unit-fortification-opportunity:unit_fortify"


def _values(eta, unit_type="Alpine Troops", status="complete"):
    values = {
        "actor_hp_band": "10+",
        "actor_unit_type": unit_type,
        "route_estimated_turns_band": eta,
        "route_first_step_movement_cost_band": (
            "0-2" if eta == "1" else "6+"),
        "route_path_length_band": "2-3" if eta == "1" else "4+",
        "route_total_movement_cost_band": "3-5" if eta == "1" else "6+",
        "source_city_relation": "none" if eta == "1" else "other",
        "source_other_fortified_units_band": "0" if eta == "1" else "1",
        "source_other_own_units_band": "0" if eta == "1" else "1",
        "transition_grounding_status": status,
    }
    assert set(values) == set(CANDIDATE_TRANSITION_FEATURE_KEYS)
    return values


def _query(query_id, eta, lifecycle="32-63", unit_type="Alpine Troops",
           status="complete", operation_type=MOVE):
    values = _values(eta, unit_type=unit_type, status=status)
    context = (
        ("candidate_transition_feature_schema",
         CANDIDATE_TRANSITION_FEATURE_SCHEMA),
        ("induction_feature_schema", "defense-episode-features/3.0"),
        ("operation_type", operation_type),
        ("outcome_target", DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET),
    )
    features = tuple(
        "candidate-transition:{}={}".format(key, values[key])
        for key in CANDIDATE_TRANSITION_FEATURE_KEYS) + (
            "context:turn_phase_band=" + lifecycle,)
    return InductionFeatureQuery(
        query_id, context, features,
        ("candidate-transition-feature-schema:"
         + CANDIDATE_TRANSITION_FEATURE_SCHEMA,
         "candidate-transition-grounding:" + status))


def _episode(index, eta, outcome, lineage=None):
    query = _query("query-{}".format(index), eta)
    return InductionEpisode(
        "episode-{}".format(index), query.context, query.features, outcome,
        query.provenance_ids + (
            "candidate-lineage:" + (lineage or "lineage-{}".format(index)),
            "game-id:game-{}".format(index // 2),
        ))


def _export(store_digest, examples):
    examples = tuple(examples)
    semantic = {
        "choice_set_count": len(examples),
        "examples": [value.to_dict() for value in examples],
        "no_in_scope_selection_count": 0,
        "nonselected_censored_count": len(examples),
        "operation_type": DEFENSE_CANDIDATE_CHOICE_SURFACE,
        "outcome_target": DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
        "policy_authority": False,
        "readout_authority": False,
        "selected_observed_count": len(examples),
        "selected_pending_or_censored_count": 0,
        "source_store_digest": store_digest,
        "truth_mutated": False,
    }
    return FdasCandidateChoiceCalibrationExport(
        DEFENSE_CANDIDATE_CHOICE_SURFACE,
        DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
        store_digest, examples, len(examples), len(examples), 0, 0,
        structural_hash(semantic))


def _exports():
    rows = tuple(
        _episode(index, "1", True) for index in range(12)) + tuple(
            _episode(index, "3+", False) for index in range(12, 24))
    return _export("transition-store-a", rows[:12]), _export(
        "transition-store-b", rows[12:])


def _confirmation_exports(invert=False):
    rows = tuple(
        _episode(index, "1", not invert) for index in range(100, 112)
    ) + tuple(
        _episode(index, "3+", invert) for index in range(112, 124))
    return _export("transition-store-c", rows[:12]), _export(
        "transition-store-d", rows[12:])


def test_transition_calibration_separates_supported_grounded_strata():
    model = fit_candidate_transition_calibration(
        _exports(), "transition-calibration-test")
    fast = model.predict(_query("fast-query", "1"))
    slow = model.predict(_query("slow-query", "3+"))

    assert fast.status == slow.status == "estimated"
    assert fast.level == slow.level == "full-lifecycle"
    assert fast.effective_lineages == slow.effective_lineages == 12
    assert fast.interval_lower > slow.interval_upper
    assert fast.estimate > slow.estimate
    assert FdasCandidateTransitionCalibrationModel.from_dict(
        model.to_dict()) == model
    assert model.to_dict()["policy_authority"] is False
    assert model.to_dict()["readout_authority"] is False
    assert model.to_dict()["truth_mutated"] is False


def test_transition_calibration_backs_off_without_inventing_full_support():
    model = fit_candidate_transition_calibration(
        _exports(), "transition-calibration-test")
    unseen_unit = model.predict(_query(
        "unseen-unit-query", "1", unit_type="Riflemen"))

    assert unseen_unit.status == "estimated"
    assert unseen_unit.level == "eta-lifecycle"
    assert unseen_unit.reason == "eta-lifecycle-estimate"
    assert unseen_unit.effective_lineages == 12


def test_transition_calibration_collapses_repeated_lineage_rows():
    repeated = _episode(100, "1", False, lineage="lineage-0")
    exports = _exports()
    augmented = _export(
        "transition-store-repeated",
        exports[0].examples + (repeated,))
    model = fit_candidate_transition_calibration(
        (augmented, exports[1]), "transition-calibration-repeated")
    full = model.predict(_query("fast-query", "1"))

    assert full.raw_rows == 13
    assert full.effective_lineages == 12


def test_transition_calibration_abstains_outside_complete_move_domain():
    model = fit_candidate_transition_calibration(
        _exports(), "transition-calibration-test")
    incomplete = model.predict(_query(
        "incomplete-query", "1", status="route-unavailable"))
    fortify = model.predict(_query(
        "fortify-query", "1", operation_type=FORTIFY))

    assert incomplete.status == "abstained"
    assert incomplete.reason == "missing-or-incomplete-transition-grounding"
    assert incomplete.estimate is None
    assert fortify.status == "abstained"
    assert fortify.reason == "outside-transition-move-domain"


def test_transition_calibration_rejects_tampering_overlap_and_bad_rows():
    exports = _exports()
    model = fit_candidate_transition_calibration(
        exports, "transition-calibration-test")
    tampered = model.to_dict()
    tampered["bins"][-1]["positive_mass"] += 0.5

    with pytest.raises(ValueError, match="bin hash differs"):
        FdasCandidateTransitionCalibrationModel.from_dict(tampered)
    with pytest.raises(ValueError, match="sources overlap"):
        fit_candidate_transition_calibration(
            (exports[0], exports[0]), "transition-overlap")
    incomplete = _episode(101, "1", True)
    incomplete_query = _query(
        incomplete.episode_id, "1", status="route-unavailable")
    incomplete = replace(
        incomplete, context=incomplete_query.context,
        features=incomplete_query.features)
    with pytest.raises(ValueError, match="grounding is incomplete"):
        fit_candidate_transition_calibration(
            (_export("transition-incomplete", (incomplete,)),),
            "transition-incomplete")


def test_transition_calibration_passes_disjoint_heldout_validation():
    model = fit_candidate_transition_calibration(
        _exports(), "transition-calibration-test")
    report = evaluate_candidate_transition_calibration(
        model, _confirmation_exports(), "transition-confirmation-test",
        bootstrap_samples=200, bootstrap_seed=73)

    assert report["passed"] is True
    assert report["prediction_coverage"] == 1.0
    assert report["candidate_specific_prediction_fraction"] == 1.0
    assert report["distinct_prediction_values"] == 2
    assert report["overall_metrics"][
        "brier_improvement_over_action_only"] > 0.0
    assert report["policy_authority"] is False
    assert report["readout_authority"] is False
    assert report["truth_mutated"] is False


def test_transition_validation_rejects_overlap_and_fails_adverse_holdout():
    exports = _exports()
    model = fit_candidate_transition_calibration(
        exports, "transition-calibration-test")
    with pytest.raises(ValueError, match="overlaps discovery"):
        evaluate_candidate_transition_calibration(
            model, exports, "transition-overlap", bootstrap_samples=200)

    report = evaluate_candidate_transition_calibration(
        model, _confirmation_exports(invert=True),
        "transition-adverse-confirmation", bootstrap_samples=200)
    assert report["passed"] is False
    assert report["gates"]["brier_score_bounded"] is False
