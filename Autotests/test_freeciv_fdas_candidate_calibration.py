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
    DEFENSE_CANDIDATE_CHOICE_SURFACE,
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    FdasCandidateCalibrationModel,
    FdasCandidateChoiceCalibrationExport,
    fit_candidate_calibration,
)
from freeciv_agent.pressure import (  # noqa: E402
    InductionEpisode,
    InductionFeatureQuery,
)


MOVE = "fdas-shadow:city-garrison-deficit:unit_move"
FORTIFY = "fdas-shadow:unit-fortification-opportunity:unit_fortify"


def _episode(index, operation_type, lifecycle, outcome, lineage=None):
    lineage = lineage or "{}-lineage-{}".format(operation_type, index)
    return InductionEpisode(
        "episode-{}-{}-{}".format(
            operation_type.rsplit(":", 1)[-1], lifecycle, index),
        (
            ("induction_feature_schema", "defense-episode-features/3.0"),
            ("operation_type", operation_type),
            ("outcome_target",
             DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET),
        ),
        (
            "context:turn_phase_band={}".format(lifecycle),
            "context:visible_enemy_proximity_band=near",
        ),
        outcome,
        ("candidate-lineage:" + lineage, "source-event:{}".format(index)),
    )


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
        store_digest,
        examples,
        len(examples),
        len(examples),
        0,
        0,
        structural_hash(semantic),
    )


def _fixture_exports():
    first = (
        _episode(0, MOVE, "0-31", True, "move-shared"),
        _episode(1, MOVE, "0-31", False, "move-shared"),
        _episode(2, MOVE, "0-31", True),
        _episode(3, MOVE, "0-31", True),
        _episode(4, FORTIFY, "0-31", True),
        _episode(5, FORTIFY, "0-31", False),
        _episode(6, FORTIFY, "0-31", True),
    )
    second = (
        _episode(7, MOVE, "32-95", False),
        _episode(8, MOVE, "32-95", True),
        _episode(9, MOVE, "32-95", False),
        _episode(10, FORTIFY, "32-95", True),
        _episode(11, FORTIFY, "32-95", False),
        _episode(12, FORTIFY, "32-95", True),
    )
    return _export("store-digest-a", first), _export(
        "store-digest-b", second)


def _query(operation_type, lifecycle="0-31"):
    return InductionFeatureQuery(
        "query-{}-{}".format(operation_type.rsplit(":", 1)[-1], lifecycle),
        (
            ("induction_feature_schema", "defense-episode-features/3.0"),
            ("operation_type", operation_type),
            ("outcome_target",
             DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET),
        ),
        ("context:turn_phase_band={}".format(lifecycle),),
        ("prediction-input",),
    )


def test_candidate_calibration_is_lineage_aware_and_roundtrips():
    model = fit_candidate_calibration(
        _fixture_exports(), "candidate-calibration-test",
        minimum_action_lineages=5, minimum_lifecycle_lineages=3)
    move_action = next(
        value for value in model.bins
        if value.operation_type == MOVE and value.level == "action")

    assert move_action.raw_rows == 7
    assert move_action.effective_lineages == 6
    assert move_action.positive_mass == 3.5
    assert move_action.interval_lower < move_action.estimate < (
        move_action.interval_upper)
    assert FdasCandidateCalibrationModel.from_dict(
        model.to_dict()) == model
    assert model.to_dict()["policy_authority"] is False
    assert model.to_dict()["readout_authority"] is False
    assert model.to_dict()["truth_mutated"] is False


def test_candidate_calibration_prefers_lifecycle_then_backs_off_or_abstains():
    exports = _fixture_exports()
    model = fit_candidate_calibration(
        exports, "candidate-calibration-test",
        minimum_action_lineages=5, minimum_lifecycle_lineages=3)

    lifecycle = model.predict(_query(MOVE, "0-31"))
    backoff = model.predict(_query(MOVE, "96+"))
    sparse = fit_candidate_calibration(
        exports, "candidate-calibration-sparse",
        minimum_action_lineages=20, minimum_lifecycle_lineages=10)
    abstained = sparse.predict(_query(FORTIFY, "0-31"))

    assert lifecycle.status == "estimated"
    assert lifecycle.reason == "lifecycle-stratum-estimate"
    assert lifecycle.effective_lineages == 3
    assert backoff.status == "estimated"
    assert backoff.reason == "action-stratum-backoff"
    assert backoff.effective_lineages == 6
    assert abstained.status == "abstained"
    assert abstained.reason == "insufficient-independent-lineage-support"
    assert abstained.bin_id is None
    assert abstained.to_dict()["policy_authority"] is False


def test_candidate_calibration_rejects_tampering_overlap_and_missing_lineage():
    exports = _fixture_exports()
    model = fit_candidate_calibration(exports, "candidate-calibration-test")
    tampered_model = model.to_dict()
    tampered_model["bins"][0]["positive_mass"] += 1.0

    with pytest.raises(ValueError, match="calibration bin result hash differs"):
        FdasCandidateCalibrationModel.from_dict(tampered_model)
    with pytest.raises(ValueError, match="source stores overlap"):
        fit_candidate_calibration(
            (exports[0], exports[0]), "candidate-calibration-overlap")

    missing = replace(
        exports[0].examples[0],
        provenance_ids=("source-event:missing-lineage",))
    invalid = _export("store-digest-missing-lineage", (missing,))
    with pytest.raises(ValueError, match="candidate lifecycle lineage"):
        fit_candidate_calibration(
            (invalid,), "candidate-calibration-missing-lineage")

    with pytest.raises(ValueError, match="calibration export result hash"):
        FdasCandidateChoiceCalibrationExport(
            exports[0].operation_type, exports[0].outcome_target,
            exports[0].source_store_digest, exports[0].examples,
            999, exports[0].nonselected_censored_count,
            exports[0].selected_pending_or_censored_count,
            exports[0].no_in_scope_selection_count,
            exports[0].result_hash)
