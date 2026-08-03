import json
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
    OperationParticipant,
    OperationSpec,
    OperationStep,
    ShadowOperationCandidate,
    build_calibrated_candidate_union,
    fit_candidate_calibration,
)
from freeciv_agent.pressure import (  # noqa: E402
    CostVector,
    GoalEffect,
    InductionEpisode,
    InductionFeatureQuery,
    Operation,
    OperationScore,
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


def _candidate(operation_id, operation_type, actor_id):
    spec = OperationSpec(
        1, operation_id, operation_type, ("goal-defense",),
        (OperationParticipant(
            "actor", "unit:{}".format(actor_id), "unit", True),),
        "city:3",
        (OperationStep(
            operation_id + "-step", operation_type.rsplit(":", 1)[-1],
            "actor", "city:3", "requirements", "complete", 1),),
        0, 2, 0.0, ("calibrated-union-test",), "ruleset-test")
    action_type = operation_type.rsplit(":", 1)[-1]
    action = {"action_type": action_type, "actor_id": actor_id}
    action_key = json.dumps(
        action, sort_keys=True, separators=(",", ":"))
    return ShadowOperationCandidate(
        spec, action, action_key, ("unit:{}".format(actor_id),),
        True, False, (), ("calibrated-union-test",),
        "candidate-hash-" + operation_id)


def _score(candidate, priority):
    operation = Operation(
        candidate.operation.operation_id,
        "atom-" + candidate.operation.operation_id, "act",
        CostVector(compute=1.0), causal_kind="causal")
    return OperationScore(
        operation, True, None, priority, priority, priority, 0.0,
        (GoalEffect("goal-defense", 1.0, 1.0, 1.0, 1.0),))


def test_calibrated_union_enlarges_recall_without_changing_scalar_winner():
    model = fit_candidate_calibration(
        _fixture_exports(), "candidate-union-model",
        minimum_action_lineages=5, minimum_lifecycle_lineages=3)
    candidates = (
        _candidate("fortify-a", FORTIFY, 7),
        _candidate("move-a", MOVE, 8),
        _candidate("fortify-b", FORTIFY, 9),
        _candidate("move-b", MOVE, 10),
    )
    priorities = (1.0, 0.9, 0.8, 0.7)
    scores = tuple(
        _score(candidate, priority)
        for candidate, priority in zip(candidates, priorities))
    queries = dict(
        (candidate.operation.operation_id,
         _query(candidate.operation.operation_type, "0-31"))
        for candidate in candidates)

    union = build_calibrated_candidate_union(
        model, candidates, scores, queries, "snapshot-test",
        "revision-test", scalar_top_k=1, calibrated_per_action=1,
        maximum_interval_width=1.0)

    assert union.baseline_selected_operation_id == "fortify-a"
    assert union.operation_ids == ("fortify-a", "move-a")
    assert union.calibrated_added_operation_ids == ("move-a",)
    assert dict((value.operation_id, value.baseline_priority)
                for value in union.readouts) == dict(zip(
                    ("fortify-a", "move-a", "fortify-b", "move-b"),
                    priorities))
    assert union.to_dict()["action_selection_changed"] is False
    assert union.to_dict()["scalar_final_score_authority"] is True
    assert union.to_dict()["flow_advection_enabled"] is False
    assert union.to_dict()["capacity_solver_enabled"] is False
    assert union.to_dict()["policy_authority"] is False
    assert union.to_dict()["readout_authority"] is False
    assert union.to_dict()["truth_mutated"] is False

    conservative = build_calibrated_candidate_union(
        model, candidates, scores, queries, "snapshot-test",
        "revision-test", scalar_top_k=1, calibrated_per_action=1,
        maximum_interval_width=0.1)
    assert conservative.operation_ids == ("fortify-a",)
    assert conservative.calibrated_added_operation_ids == ()
    assert conservative.abstained_operation_ids == (
        "fortify-a", "move-a", "fortify-b", "move-b")


def test_calibrated_union_keeps_abstained_action_only_if_scalar_protected():
    model = fit_candidate_calibration(
        _fixture_exports(), "sparse-union-model",
        minimum_action_lineages=20, minimum_lifecycle_lineages=10)
    move = _candidate("move-only", MOVE, 8)
    query = _query(MOVE, "0-31")

    union = build_calibrated_candidate_union(
        model, (move,), (_score(move, 1.0),),
        {"move-only": query}, "snapshot-test", "revision-test",
        scalar_top_k=1, maximum_interval_width=1.0)

    assert union.operation_ids == ("move-only",)
    assert union.abstained_operation_ids == ("move-only",)
    assert union.calibrated_added_operation_ids == ()
    assert union.readouts[0].eligible_for_calibrated_recall is False
