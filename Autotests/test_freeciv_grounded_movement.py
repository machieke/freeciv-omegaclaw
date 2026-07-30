"""Grounded adjacent-movement estimates and corridor identity."""

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

from freeciv_agent.planning import ImpactCandidate  # noqa: E402
from freeciv_agent.planning.domain_models import (  # noqa: E402
    DomainEstimateRequest,
    EstimateAuthority,
    EstimateValidity,
    GroundedMovementTransitionModel,
)
from freeciv_agent.planning.path_corridors import (  # noqa: E402
    adjacent_action_corridor,
)
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


def _payload():
    path = os.path.join(
        REPO, "benchmarks", "freeciv",
        "samples", "real_state_turn1.json")
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _snapshot(explicit_cost=True, visible=True):
    payload = copy.deepcopy(_payload())
    action = next(
        row for row in payload[
            "legal_actions"]["102"]
        if (row.get("action_type") == "unit_move"
            and row.get("target", {}).get(
                "direction") == "n"))
    if explicit_cost:
        action["movement_cost"] = 3
        action["transport_required"] = False
    payload["map"].update({
        "tiles": [
            {
                "index": 2030,
                "known": 2,
                "terrain": 1,
            },
            {
                "index": 1982,
                "known": 2 if visible else 1,
                "terrain": 1,
            },
        ],
        "visibility": (
            {"1982": True, "2030": True}
            if visible else
            {"2030": True}),
        "wrap_x": True,
        "wrap_y": False,
    })
    snapshot = ProxyStateDTO.parse(
        "grounded-movement", 1,
        payload).to_snapshot()
    normalized = next(
        json.loads(value)
        for value in snapshot.legal_action_json
        if (
            json.loads(value).get(
                "action_type") == "unit_move"
            and json.loads(value).get(
                "actor_id") == 102
            and json.loads(value).get(
                "target", {}).get(
                    "direction") == "n"))
    return snapshot, normalized


def _request(snapshot, action, utility=100.0):
    candidate = ImpactCandidate(
        action=action,
        category="expansion_move",
        utility=utility,
        rationale="test")
    return DomainEstimateRequest(
        request_id="m" * 64,
        snapshot=snapshot,
        ruleset_ir=None,
        legal_action=action,
        candidate=candidate,
        goal_losses=(
            ("pf-impact:expansion", 1.0),),
        operation_context=None,
        validity=EstimateValidity(
            snapshot.snapshot_id,
            snapshot.legal_actions_digest,
            "ruleset",
            snapshot.turn,
            snapshot.turn),
        horizon_turn=snapshot.turn + 10)


def test_snapshot_retains_movement_topology_and_transport_state():
    snapshot, _ = _snapshot()
    unit = snapshot.unit(102)
    grounded = snapshot.event_payload()[
        "grounded_context"]

    assert snapshot.map_wrap_x is True
    assert snapshot.map_wrap_y is False
    assert unit.veteran == 0
    assert unit.transported is False
    assert unit.done_moving is False
    assert grounded["map_topology"] == {
        "wrap_x": True,
        "wrap_y": False,
    }
    assert len(
        grounded["legal_actions"]
    ) == len(
        snapshot.legal_action_json)
    grounded_unit = next(
        row for row
        in grounded["own_units"]
        if row["unit_id"] == 102)
    assert grounded_unit[
        "transported"] is False
    assert grounded_unit[
        "done_moving"] is False
    assert grounded_unit[
        "veteran"] == 0


def test_visible_explicit_cost_adjacent_move_is_parity_gated_heuristic():
    snapshot, action = _snapshot()
    estimate = GroundedMovementTransitionModel().estimate(
        _request(snapshot, action))
    artifact = estimate.to_dict()[
        "model_artifact"]

    assert estimate.authority == (
        EstimateAuthority.HEURISTIC)
    assert not estimate.live_eligible(
        snapshot.snapshot_id,
        snapshot.legal_actions_digest,
        "ruleset", snapshot.turn)
    assert estimate.transition.residual_probability == 0.0
    assert estimate.transition.modeled_probability == 1.0
    assert artifact["reachable"] is True
    assert artifact[
        "minimum_current_turn_movement_cost"] == 3.0
    assert artifact[
        "movement_points_remaining"] == 0.0
    assert artifact["transport_requirement"] is False
    assert artifact["corridor"][
        "visibility"] == "visible"
    assert artifact["parity_status"] == "unverified"


def test_movement_abstains_when_cost_or_visibility_is_missing():
    no_cost_snapshot, no_cost_action = (
        _snapshot(explicit_cost=False))
    hidden_snapshot, hidden_action = (
        _snapshot(visible=False))

    no_cost = GroundedMovementTransitionModel().estimate(
        _request(
            no_cost_snapshot,
            no_cost_action))
    hidden = GroundedMovementTransitionModel().estimate(
        _request(
            hidden_snapshot,
            hidden_action))

    assert no_cost.authority == (
        EstimateAuthority.ABSTAIN)
    assert (
        "authoritative_movement_cost"
        in no_cost.to_dict()[
            "model_artifact"][
                "missing_fields"])
    assert hidden.authority == (
        EstimateAuthority.ABSTAIN)
    assert (
        "visible_target_occupancy"
        in hidden.to_dict()[
            "model_artifact"][
                "missing_fields"])


def test_corridor_and_intrinsic_estimate_ignore_utility():
    snapshot, action = _snapshot()
    corridor = adjacent_action_corridor(
        snapshot, action)
    model = GroundedMovementTransitionModel()
    first = model.estimate(
        _request(snapshot, action, 1.0))
    second = model.estimate(
        _request(snapshot, action, 100000.0))

    assert corridor.corridor_digest == (
        first.to_dict()["model_artifact"][
            "corridor"]["corridor_digest"])
    assert first == second


def test_snapshot_change_invalidates_movement_authority():
    snapshot, action = _snapshot()
    estimate = GroundedMovementTransitionModel().estimate(
        _request(snapshot, action))
    changed = replace(
        snapshot.identity, source_seq=2)

    assert not estimate.live_eligible(
        changed.snapshot_id,
        snapshot.legal_actions_digest,
        "ruleset", snapshot.turn)


def test_movement_rejects_transport_and_non_adjacent_targets():
    transport_snapshot, transport_action = _snapshot()
    transport_action["transport_required"] = True
    transport_snapshot = replace(
        transport_snapshot,
        legal_action_json=tuple(sorted(
            set(transport_snapshot.legal_action_json)
            | {
                json.dumps(
                    transport_action,
                    sort_keys=True,
                    separators=(",", ":"))
            })))
    transport = GroundedMovementTransitionModel().estimate(
        _request(
            transport_snapshot,
            transport_action))

    assert transport.authority == EstimateAuthority.ABSTAIN
    assert transport.abstention_reason == (
        "movement-transport-unsupported")

    snapshot, action = _snapshot()
    action["target"]["y"] -= 2
    with pytest.raises(
            ValueError,
            match="one adjacent edge"):
        adjacent_action_corridor(
            snapshot, action)


def test_movement_abstains_for_completed_or_non_idle_actor():
    snapshot, action = _snapshot()
    unit = snapshot.unit(102)
    done_snapshot = replace(
        snapshot,
        units=tuple(
            replace(
                row, done_moving=True)
            if row.unit_id == unit.unit_id
            else row
            for row in snapshot.units))
    active_snapshot = replace(
        snapshot,
        units=tuple(
            replace(
                row, activity="goto")
            if row.unit_id == unit.unit_id
            else row
            for row in snapshot.units))

    done = GroundedMovementTransitionModel().estimate(
        _request(
            done_snapshot, action))
    active = GroundedMovementTransitionModel().estimate(
        _request(
            active_snapshot, action))

    assert done.authority == EstimateAuthority.ABSTAIN
    assert done.abstention_reason == (
        "movement-actor-done")
    assert active.authority == EstimateAuthority.ABSTAIN
    assert "actor_idle_activity" in (
        active.to_dict()[
            "model_artifact"][
                "missing_fields"])
