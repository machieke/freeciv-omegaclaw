"""Captured city-defence replay input completeness."""

import importlib.util
import os


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
        "legal_action_source"
    ] == "snapshot-grounded-context"
    # Input completeness is necessary but does not establish native parity
    # or counterfactual operation outcomes.
    assert not authority[
        "policy_authority_eligible"]
