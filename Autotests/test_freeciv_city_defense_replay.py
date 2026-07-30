"""Captured city-defence replay input completeness."""

import importlib.util
import json
import os
import tempfile


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))


def _extractor_module():
    path = os.path.join(
        REPO, "scripts",
        "extract_gdo_city_defense_replays.py")
    spec = (
        importlib.util
        .spec_from_file_location(
            "gdo_defense_extractor",
            path))
    module = (
        importlib.util
        .module_from_spec(spec))
    spec.loader.exec_module(
        module)
    return module


def _runner_module():
    path = os.path.join(
        REPO, "scripts",
        "run_gdo_city_defense_replay.py")
    spec = (
        importlib.util
        .spec_from_file_location(
            "gdo_defense_runner",
            path))
    module = (
        importlib.util
        .module_from_spec(spec))
    spec.loader.exec_module(
        module)
    return module


def _event(grounded_context=None):
    payload = {
        "snapshot_id": "replay",
    }
    if grounded_context is not None:
        payload[
            "grounded_context"] = (
                grounded_context)
    return {
        "payload": payload,
    }


def test_legacy_snapshot_is_explicitly_incomplete_for_grounded_replay():
    authority = (
        _extractor_module()
        ._authority(
            _event()))

    assert not authority[
        "full_legal_action_set_available"]
    assert not authority[
        "map_wrap_metadata_available"]
    assert not authority[
        "movement_runtime_fields_available"]
    assert not authority[
        "movement_action_metadata_available"]
    assert not authority[
        "native_movement_route_collection_available"]
    assert authority[
        "native_movement_route_count"] == 0
    assert not authority[
        "native_movement_routes_available"]
    assert not authority[
        "policy_authority_eligible"]


def test_grounded_snapshot_completeness_is_measured_per_input_family():
    authority = (
        _extractor_module()
        ._authority(
            _event({
                "legal_actions": [{
                    "action_type":
                        "unit_move",
                    "actor_id": 7,
                    "movement_cost": 3,
                    "target": {
                        "x": 4,
                        "y": 5,
                    },
                    "transport_required":
                        False,
                }],
                "map_topology": {
                    "wrap_x": True,
                    "wrap_y": False,
                },
                "own_units": [{
                    "done_moving": False,
                    "transported": False,
                    "unit_id": 7,
                }],
                "movement_routes": [{
                    "authority":
                        "freeciv-server-pathfinder",
                    "destination_tile": 55,
                    "estimated_turns": 2,
                    "first_step_movement_cost": 3,
                    "first_step_tile": 34,
                    "initially_transported": False,
                    "movement_points_remaining": 0,
                    "moves_left_at_request": 3,
                    "origin_tile": 33,
                    "path_directions": [2, 2],
                    "path_length": 2,
                    "reachable": True,
                    "schema_version": "1.0",
                    "source_seq": 90,
                    "total_movement_cost": 6,
                    "transported_at_request": False,
                    "turn": 7,
                    "unit_id": 7,
                }],
            })))

    assert authority[
        "full_legal_action_set_available"]
    assert authority[
        "map_wrap_metadata_available"]
    assert authority[
        "movement_runtime_fields_available"]
    assert authority[
        "movement_action_metadata_available"]
    assert authority[
        "native_movement_route_collection_available"]
    assert authority[
        "native_movement_route_count"] == 1
    assert authority[
        "native_movement_routes_available"]
    assert authority[
        "legal_action_source"
    ] == "snapshot-grounded-context"
    # Input completeness is necessary but does not establish native parity
    # or counterfactual operation outcomes.
    assert not authority[
        "policy_authority_eligible"]


def test_replay_loader_reconstructs_exact_native_route():
    route = (
        _runner_module()
        ._movement_route({
            "authority":
                "freeciv-server-pathfinder",
            "destination_tile": 55,
            "estimated_turns": 2,
            "first_step_movement_cost": 3,
            "first_step_tile": 34,
            "initially_transported": False,
            "movement_points_remaining": 0,
            "moves_left_at_request": 3,
            "origin_tile": 33,
            "path_directions": [2, 2],
            "path_length": 2,
            "reachable": True,
            "schema_version": "1.0",
            "source_seq": 90,
            "total_movement_cost": 6,
            "transported_at_request": False,
            "turn": 7,
            "unit_id": 7,
        }))

    assert route.unit_id == 7
    assert route.destination_tile == 55
    assert route.path_directions == (2, 2)
    assert route.authority == (
        "freeciv-server-pathfinder")


def test_trace_loader_retains_only_explicit_operation_proposal_snapshot_ids():
    events = [
        {
            "type": "state_snapshot",
            "turn": 4,
            "payload": {
                "snapshot_id": "snapshot-4",
            },
        },
        {
            "type": "operation_scored",
            "turn": 4,
            "payload": {
                "snapshot_id": "snapshot-4",
            },
        },
        {
            "type": "operation_proposed",
            "turn": 4,
            "payload": {
                "snapshot_id": "snapshot-4",
            },
        },
        {
            "type": "state_snapshot",
            "turn": 5,
            "payload": {
                "snapshot_id": "snapshot-5",
            },
        },
    ]
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory, "events.jsonl")
        with open(
                path, "w",
                encoding="utf-8") as stream:
            for event in events:
                stream.write(
                    json.dumps(event))
                stream.write("\n")
        (
            snapshots,
            scored,
            final_snapshot_by_turn,
            proposed_snapshot_ids,
        ) = (
            _extractor_module()
            ._load_trace(path))

    assert set(snapshots) == {
        "snapshot-4",
        "snapshot-5",
    }
    assert set(scored) == {
        "snapshot-4",
    }
    assert set(
        final_snapshot_by_turn) == {
            4, 5,
        }
    assert proposed_snapshot_ids == {
        "snapshot-4",
    }
