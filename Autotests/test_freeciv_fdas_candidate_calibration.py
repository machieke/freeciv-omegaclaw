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
from freeciv_agent.flow_control import ProbeConfig  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    DEFENSE_CANDIDATE_CHOICE_SURFACE,
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    FdasCandidateCalibrationModel,
    FdasCandidateChoiceCalibrationExport,
    OperationParticipant,
    OperationSpec,
    OperationStep,
    ShadowOperationCandidate,
    FdasPathPersistenceCandidateController,
    build_calibrated_candidate_union,
    build_probe_candidate_union,
    fit_candidate_calibration,
)
from freeciv_agent.pressure import (  # noqa: E402
    CostVector,
    GoalEffect,
    InductionEpisode,
    InductionFeatureQuery,
    Operation,
    OperationScore,
    ScalarBaselineConfig,
)
from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.snapshot import SnapshotIdentity  # noqa: E402


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


def _probe_snapshot(candidates):
    path = os.path.join(
        REPO, "benchmarks", "freeciv", "samples", "real_state_turn1.json")
    with open(path, encoding="utf-8") as stream:
        snapshot = ProxyStateDTO.parse(
            "fdas-probe-union", 1, json.load(stream)).to_snapshot()
    action_keys = tuple(sorted(value.action_key for value in candidates))
    return replace(
        snapshot,
        legal_action_json=action_keys,
        legal_actions_digest=structural_hash(action_keys),
        legal_action_kinds=("unit_fortify", "unit_move"))


def _probe_union_fixture(config):
    model = fit_candidate_calibration(
        _fixture_exports(), "probe-candidate-union-model",
        minimum_action_lineages=5, minimum_lifecycle_lineages=3)
    candidates = (
        _candidate("fortify-a", FORTIFY, 102),
        _candidate("move-a", MOVE, 110),
        _candidate("fortify-b", FORTIFY, 111),
        _candidate("move-b", MOVE, 112),
    )
    scores = tuple(
        _score(candidate, priority)
        for candidate, priority in zip(candidates, (1.0, 0.9, 0.8, 0.7)))
    queries = dict(
        (candidate.operation.operation_id,
         _query(candidate.operation.operation_type, "0-31"))
        for candidate in candidates)
    snapshot = _probe_snapshot(candidates)
    calibrated = build_calibrated_candidate_union(
        model, candidates, scores, queries, snapshot.snapshot_id,
        "probe-revision", scalar_top_k=1, calibrated_per_action=1,
        maximum_interval_width=1.0)
    return build_probe_candidate_union(
        calibrated, candidates, snapshot, "probe-revision",
        DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
        probe_config=config, maximum_probe_regions=4,
        probe_per_action=1)


def test_probe_union_adds_bounded_recall_without_displacing_scalar_authority():
    config = ProbeConfig(
        path_count=128, max_steps=16, reference_fraction=0.25,
        minimum_path_diversity=0.0)

    union = _probe_union_fixture(config)

    assert union.graph_complete
    assert union.probe_healthy
    assert not union.fallback_required
    assert union.baseline_selected_operation_id == "fortify-a"
    assert union.base_calibrated_operation_ids == ("fortify-a", "move-a")
    assert union.operation_ids == (
        "fortify-a", "move-a", "fortify-b", "move-b")
    assert union.probe_added_operation_ids == ("fortify-b", "move-b")
    assert union == _probe_union_fixture(config)
    details = union.to_dict()
    assert details["action_selection_changed"] is False
    assert details["scalar_final_score_authority"] is True
    assert details["flow_advection_enabled"] is False
    assert details["capacity_solver_enabled"] is False
    assert details["policy_authority"] is False
    assert details["readout_authority"] is False
    assert details["truth_mutated"] is False
    assert not any(
        value["used_in_final_score"]
        for value in details["signal_ledger"]["uses"]
        if value["signal_name"] in (
            "calibrated_transition_estimate", "corrected_bridge_overlap",
            "corrected_probe_weight", "raw_probe_count"))


def test_probe_union_falls_back_to_calibrated_membership_when_unhealthy():
    # Four direct backward routes cannot satisfy a 10% diversity floor over
    # 128 draws. This deliberately exercises the sampling-health fallback.
    union = _probe_union_fixture(ProbeConfig(
        path_count=128, max_steps=16, reference_fraction=0.25,
        minimum_path_diversity=0.1))

    assert union.graph_complete
    assert not union.probe_healthy
    assert union.fallback_required
    assert union.fallback_reason == "collapsed_path_diversity"
    assert union.operation_ids == union.base_calibrated_operation_ids
    assert union.probe_selected_operation_ids == ()
    assert union.probe_added_operation_ids == ()


def _persistence_surface(model, turn, coordinates):
    actors = (102, 110, 111)
    candidates = []
    for index, (actor_id, target) in enumerate(zip(actors, coordinates)):
        operation_id = "{}-t{}".format(chr(ord("a") + index), turn)
        candidate = _candidate(operation_id, MOVE, actor_id)
        action = dict(candidate.action, target={
            "x": target[0], "y": target[1]})
        action_key = json.dumps(
            action, sort_keys=True, separators=(",", ":"))
        candidates.append(ShadowOperationCandidate(
            candidate.operation, action, action_key,
            candidate.resource_keys, True, False, (),
            candidate.provenance,
            candidate.candidate_hash + structural_hash(target)[:8]))
    candidates = tuple(candidates)
    path = os.path.join(
        REPO, "benchmarks", "freeciv", "samples", "real_state_turn1.json")
    with open(path, encoding="utf-8") as stream:
        snapshot = ProxyStateDTO.parse(
            "fdas-persistence", 1, json.load(stream)).to_snapshot()
    identity = SnapshotIdentity(
        "fdas-persistence", turn, turn,
        structural_hash([turn, coordinates]))
    action_keys = tuple(sorted(value.action_key for value in candidates))
    snapshot = replace(
        snapshot, identity=identity,
        legal_action_json=action_keys,
        legal_actions_digest=structural_hash(action_keys),
        legal_action_kinds=("unit_move",))
    scores = tuple(
        _score(candidate, priority)
        for candidate, priority in zip(candidates, (0.8, 0.9, 1.0)))
    queries = dict(
        (candidate.operation.operation_id,
         _query(candidate.operation.operation_type, "0-31"))
        for candidate in candidates)
    revision_id = "persistence-revision-{}".format(turn)
    calibrated = build_calibrated_candidate_union(
        model, candidates, scores, queries, snapshot.snapshot_id,
        revision_id, scalar_top_k=1, calibrated_per_action=1,
        maximum_interval_width=1.0)
    probe = build_probe_candidate_union(
        calibrated, candidates, snapshot, revision_id,
        DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
        probe_config=ProbeConfig(
            path_count=128, max_steps=16, reference_fraction=0.25,
            minimum_path_diversity=0.0),
        maximum_probe_regions=1, probe_per_action=1)
    return candidates, queries, snapshot, revision_id, probe


def _persistence_controller(maximum_regret=0.05):
    return FdasPathPersistenceCandidateController(
        ScalarBaselineConfig(
            smoothing=1.0, route_momentum=0.0,
            minimum_dwell_steps=2, dwell_bonus=0.0,
            switch_margin=0.0, diversity_floor=0.0),
        maximum_reachability_regret=maximum_regret)


def test_path_persistence_adds_only_a_current_near_tied_corridor_member():
    model = fit_candidate_calibration(
        _fixture_exports(), "path-persistence-model",
        minimum_action_lineages=5, minimum_lifecycle_lineages=3)
    first = _persistence_surface(
        model, 1, ((0, 0), (3, 0), (6, 0)))
    second = _persistence_surface(
        model, 2, ((3, 0), (6, 0), (9, 0)))
    controller = _persistence_controller()

    first_union = controller.build_union(
        first[4], first[0], first[1], first[2], first[3])
    second_union = controller.build_union(
        second[4], second[0], second[1], second[2], second[3])

    assert first[4].probe_selected_operation_ids == ("b-t1",)
    assert second[4].probe_selected_operation_ids == ("a-t2",)
    assert first_union.persistence_selected_operation_id == "b-t1"
    assert first_union.persistence_added_operation_ids == ()
    assert second_union.persistence_selected_operation_id == "b-t2"
    assert second_union.persistence_added_operation_ids == ("b-t2",)
    assert not second_union.retained_by_smoothing
    assert second_union.retained_by_dwell
    assert not second_union.retained_by_hysteresis
    assert not second_union.regret_rejected
    assert second_union.reachability_regret < 0.05
    assert second_union.operation_ids == ("c-t2", "b-t2", "a-t2")
    assert controller.build_union(
        second[4], second[0], second[1], second[2], second[3]) == second_union
    details = second_union.to_dict()
    assert details["action_selection_changed"] is False
    assert details["path_persistence_authority"] is False
    assert details["source_sink_flow_enabled"] is False
    assert details["flow_advection_enabled"] is False
    assert details["capacity_solver_enabled"] is False
    assert details["scalar_final_score_authority"] is True


def test_path_persistence_attributes_smoothing_retention_separately():
    model = fit_candidate_calibration(
        _fixture_exports(), "path-persistence-smoothing-model",
        minimum_action_lineages=5, minimum_lifecycle_lineages=3)
    first = _persistence_surface(
        model, 1, ((0, 0), (3, 0), (6, 0)))
    second = _persistence_surface(
        model, 2, ((3, 0), (6, 0), (9, 0)))
    controller = FdasPathPersistenceCandidateController(
        ScalarBaselineConfig(
            smoothing=0.35, route_momentum=0.15,
            minimum_dwell_steps=2, dwell_bonus=0.05,
            switch_margin=0.01, diversity_floor=0.0),
        maximum_reachability_regret=0.05)
    controller.build_union(
        first[4], first[0], first[1], first[2], first[3])

    union = controller.build_union(
        second[4], second[0], second[1], second[2], second[3])

    assert union.persistence_selected_operation_id == "b-t2"
    assert union.persistence_added_operation_ids == ("b-t2",)
    assert union.retained_by_smoothing
    assert not union.retained_by_dwell
    assert not union.retained_by_hysteresis
    assert union.switch_cause == "retained-by-smoothing"
    assert union.to_dict()["retained_by_smoothing"] is True


def test_path_persistence_regret_gate_reanchors_on_current_probe_region():
    model = fit_candidate_calibration(
        _fixture_exports(), "path-persistence-regret-model",
        minimum_action_lineages=5, minimum_lifecycle_lineages=3)
    first = _persistence_surface(
        model, 1, ((0, 0), (3, 0), (6, 0)))
    second = _persistence_surface(
        model, 2, ((3, 0), (6, 0), (9, 0)))
    controller = _persistence_controller(maximum_regret=0.0)
    controller.build_union(
        first[4], first[0], first[1], first[2], first[3])

    union = controller.build_union(
        second[4], second[0], second[1], second[2], second[3])

    assert union.regret_rejected
    assert union.switch_cause == "reachability-regret-rejected"
    assert union.persistence_selected_operation_id == "a-t2"
    assert union.persistence_added_operation_ids == ()
    assert not union.retained_by_dwell
