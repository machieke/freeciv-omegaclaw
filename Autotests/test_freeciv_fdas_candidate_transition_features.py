import copy
import json
import os
import sys
from dataclasses import replace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (
    CANDIDATE_TRANSITION_FEATURE_KEYS,
    CANDIDATE_TRANSITION_FEATURE_SCHEMA,
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    FdasCandidateCalibrationModel,
    OperationParticipant,
    OperationSpec,
    OperationStep,
    ShadowOperationCandidate,
    candidate_transition_feature_query,
)
from freeciv_agent.pressure import InductionFeatureQuery
from freeciv_agent.state import ProxyStateDTO


FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")
MODEL = os.path.join(
    REPO, "docs", "freeciv", "evidence",
    "fdas-pr40-candidate-calibration-discovery.json")
MOVE = "fdas-shadow:city-garrison-deficit:unit_move"


def _case():
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    payload["units"]["7"].update({
        "tile": 83, "transported": False, "x": 3, "y": 2,
    })
    second = copy.deepcopy(payload["units"]["7"])
    second["id"] = 8
    second["activity"] = "fortified"
    payload["units"]["8"] = second
    payload["authoritative"]["source_seq"] = 991
    payload["authoritative"]["movement_routes"] = [{
        "authority": "freeciv-server-pathfinder",
        "destination_tile": 82,
        "estimated_turns": 2,
        "first_step_movement_cost": 3,
        "first_step_tile": 82,
        "initially_transported": False,
        "movement_points_remaining": 0,
        "moves_left_at_request": 3,
        "origin_tile": 83,
        "path_directions": [6],
        "path_length": 1,
        "reachable": True,
        "schema_version": "1.0",
        "source_seq": 990,
        "total_movement_cost": 7,
        "transported_at_request": False,
        "turn": payload["turn"],
        "unit_id": 7,
    }]
    snapshot = ProxyStateDTO.parse(
        "candidate-transition-features", 991, payload).to_snapshot()
    operation = OperationSpec(
        1, "operation-transition-test", MOVE, ("goal-defense",),
        (OperationParticipant("actor", "unit:7", "unit", True),),
        "city:3",
        (OperationStep(
            "transition-step", "unit_move", "actor", "city:3",
            "requirements", "complete", 1),),
        snapshot.turn, snapshot.turn + 2, 0.0,
        ("candidate-transition-test",), "ruleset-test")
    action = {
        "action_type": "unit_move",
        "actor_id": 7,
        "movement_cost": 3,
        "target": {"x": 2, "y": 2},
        "transport_required": False,
    }
    action_key = json.dumps(action, sort_keys=True, separators=(",", ":"))
    candidate = ShadowOperationCandidate(
        operation, action, action_key, ("unit:7",), True, False, (),
        ("candidate-transition-test",), "candidate-transition-hash")
    query = InductionFeatureQuery(
        "candidate-transition-query",
        (
            ("induction_feature_schema", "defense-episode-features/3.0"),
            ("operation_type", MOVE),
            ("outcome_target",
             DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET),
        ),
        (
            "context:actor_homecity_relation=unknown",
            "context:turn_phase_band=0-31",
        ),
        ("snapshot-id:" + snapshot.snapshot_id,),
    )
    return snapshot, candidate, query


def _transition_features(query):
    return dict(
        value[len("candidate-transition:"):].split("=", 1)
        for value in query.features
        if value.startswith("candidate-transition:"))


def test_transition_query_records_revision_bound_candidate_mechanics():
    snapshot, candidate, query = _case()
    projected = candidate_transition_feature_query(
        query, candidate, snapshot)
    features = _transition_features(projected)

    assert projected.query_id == query.query_id
    assert set(query.features).issubset(projected.features)
    assert dict(projected.context)[
        "candidate_transition_feature_schema"] == (
            CANDIDATE_TRANSITION_FEATURE_SCHEMA)
    assert set(features) == set(CANDIDATE_TRANSITION_FEATURE_KEYS)
    assert features == {
        "actor_hp_band": "10+",
        "actor_unit_type": "Warriors",
        "route_estimated_turns_band": "2",
        "route_first_step_movement_cost_band": "3-5",
        "route_path_length_band": "1",
        "route_total_movement_cost_band": "6+",
        "source_city_relation": "none",
        "source_other_fortified_units_band": "1",
        "source_other_own_units_band": "1",
        "transition_grounding_status": "complete",
    }
    assert "outcome" not in projected.to_dict()


@pytest.mark.parametrize("mutation,reason", (
    ("stale", "route-stale"),
    ("cost", "route-action-mismatch"),
    ("missing", "route-unavailable"),
))
def test_transition_query_exposes_missing_or_inconsistent_grounding(
        mutation, reason):
    snapshot, candidate, query = _case()
    if mutation == "stale":
        snapshot = replace(snapshot, movement_routes=tuple(
            replace(value, source_seq=snapshot.identity.source_seq + 1)
            for value in snapshot.movement_routes))
    elif mutation == "cost":
        candidate = replace(
            candidate,
            action={**candidate.action, "movement_cost": 2},
            action_key=json.dumps(
                {**candidate.action, "movement_cost": 2},
                sort_keys=True, separators=(",", ":")))
    else:
        snapshot = replace(snapshot, movement_routes=())

    projected = candidate_transition_feature_query(
        query, candidate, snapshot)
    features = _transition_features(projected)

    assert features["transition_grounding_status"] == reason
    assert all(
        value == "unknown"
        for key, value in features.items()
        if key != "transition_grounding_status")


def test_frozen_candidate_model_ignores_new_features_byte_for_byte():
    snapshot, candidate, query = _case()
    projected = candidate_transition_feature_query(
        query, candidate, snapshot)
    with open(MODEL, encoding="utf-8") as stream:
        model = FdasCandidateCalibrationModel.from_dict(
            json.load(stream)["calibration_model"])

    assert model.predict(projected) == model.predict(query)


def test_transition_query_rejects_wrong_domain_and_double_projection():
    snapshot, candidate, query = _case()
    projected = candidate_transition_feature_query(
        query, candidate, snapshot)
    with pytest.raises(ValueError, match="already projected"):
        candidate_transition_feature_query(projected, candidate, snapshot)
    with pytest.raises(ValueError, match="supports reinforcement moves"):
        candidate_transition_feature_query(
            replace(query, context=(
                ("induction_feature_schema", "defense-episode-features/3.0"),
                ("operation_type",
                 "fdas-shadow:unit-fortification-opportunity:unit_fortify"),
                ("outcome_target",
                 DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET),
            )), candidate, snapshot)
