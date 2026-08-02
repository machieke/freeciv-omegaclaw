"""Grounded current-step transport estimates and carrier identity."""

import copy
import json
import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import ImpactCandidate  # noqa: E402
from freeciv_agent.planning.domain_models import (  # noqa: E402
    DomainEstimateRequest,
    EstimateAuthority,
    EstimateValidity,
    GroundedTransportTransitionModel,
    transport_unit_profile,
)
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


def _rule(
        name, unit_class,
        capacity=0, cargo=(),
        flags=()):
    return SimpleNamespace(
        target_kind="unit",
        display_name=name,
        rule_name=name,
        quantitative={
            "transport_cap": {
                "value": capacity,
            },
        },
        traits={
            "cargo": {
                "values": list(cargo),
            },
            "class": {
                "values": [unit_class],
            },
            "flags": {
                "values": list(flags),
            },
        })


def _ruleset():
    return SimpleNamespace(rules=(
        _rule(
            "Settlers",
            "Small Land",
            flags=("Cities",)),
        _rule(
            "Trireme",
            "Trireme",
            capacity=2,
            cargo=(
                "Land",
                "Merchant",
                "Small Land")),
    ))


def _payload():
    with open(os.path.join(
            REPO, "benchmarks",
            "freeciv", "samples",
            "real_state_turn1.json"),
            encoding="utf-8") as stream:
        return json.load(stream)


def _ferry(unit_id):
    return {
        "activity": "idle",
        "carrying": -1,
        "done_moving": False,
        "homecity": 0,
        "hp": 10,
        "id": unit_id,
        "moves_left": 9,
        "owner": 0,
        "tile": 1982,
        "transported": False,
        "transported_by": 0,
        "type": "Trireme",
        "type_id": 34,
        "upkeep": [],
        "veteran": 0,
        "x": 14,
        "y": 41,
    }


def _snapshot(
        disembark=False,
        second_ferry=False,
        cargo_count=0):
    payload = copy.deepcopy(
        _payload())
    actor = payload[
        "units"]["102"]
    actor.update({
        "carrying": 0,
        "done_moving": False,
        "transported": bool(
            disembark),
        "transported_by": (
            200 if disembark else 0),
    })
    payload["units"]["200"] = (
        _ferry(200))
    loaded = 1 if disembark else 0
    for offset in range(max(0, cargo_count - loaded)):
        cargo_id = 300 + offset
        cargo = copy.deepcopy(actor)
        cargo.update({
            "id": cargo_id,
            "tile": 1982,
            "transported": True,
            "transported_by": 200,
        })
        payload["units"][str(cargo_id)] = cargo
    if second_ferry:
        payload["units"]["201"] = (
            _ferry(201))
    if disembark:
        actor.update({
            "tile": 1982,
            "x": 14,
            "y": 41,
        })
        action = {
            "action_type": "unit_move",
            "actor_id": 102,
            "is_valid": True,
            "movement_cost": 3,
            "target": {
                "direction": "e",
                "x": 15,
                "y": 41,
            },
            "transport_required": False,
        }
        target_tile = 1983
    else:
        action = next(
            row for row in payload[
                "legal_actions"]["102"]
            if (
                row.get(
                    "action_type")
                == "unit_move"
                and row.get(
                    "target", {}).get(
                        "direction") == "n"))
        action.update({
            "movement_cost": 3,
            "transport_required": True,
        })
        target_tile = 1982
    payload["legal_actions"][
        "102"] = [action]
    tiles = [{
        "index": 1982,
        "known": 2,
        "terrain": 2,
    }]
    if target_tile != 1982:
        tiles.append({
            "index": target_tile,
            "known": 2,
            "terrain": 1,
        })
    payload["map"].update({
        "tiles": tiles,
        "visibility": {
            "1982": True,
            str(target_tile): True,
        },
        "wrap_x": True,
        "wrap_y": False,
    })
    snapshot = ProxyStateDTO.parse(
        "grounded-transport", 1,
        payload).to_snapshot()
    normalized = next(
        json.loads(row)
        for row in
        snapshot.legal_action_json
        if json.loads(row).get(
            "actor_id") == 102)
    return snapshot, normalized


def _request(
        snapshot, action,
        utility=100.0):
    return DomainEstimateRequest(
        request_id="t" * 64,
        snapshot=snapshot,
        ruleset_ir=_ruleset(),
        legal_action=action,
        candidate=ImpactCandidate(
            action=action,
            category="expansion_move",
            utility=utility,
            rationale="test transport"),
        goal_losses=(
            (
                "pf-impact:expansion",
                1.0),
        ),
        operation_context=None,
        validity=EstimateValidity(
            snapshot.snapshot_id,
            snapshot
            .legal_actions_digest,
            "ruleset",
            snapshot.turn,
            snapshot.turn),
        horizon_turn=(
            snapshot.turn + 10))


def test_ruleset_profile_retains_founder_and_ferry_compatibility():
    founder = transport_unit_profile(
        _ruleset(), "settlers")
    ferry = transport_unit_profile(
        _ruleset(), "Trireme")

    assert founder.founder_capable
    assert founder.unit_class == (
        "Small Land")
    assert ferry.transport_capacity == 2
    assert founder.unit_class in (
        ferry.cargo_classes)


def test_advertised_embark_estimate_binds_unique_ferry_and_seat():
    snapshot, action = _snapshot()

    estimate = (
        GroundedTransportTransitionModel()
        .estimate(
            _request(
                snapshot, action)))
    artifact = estimate.to_dict()[
        "model_artifact"]
    outcome = estimate.transition.outcomes[
        0]

    assert estimate.authority == (
        EstimateAuthority
        .EXACT_AUTHORITATIVE)
    assert outcome.probability == 1.0
    assert artifact["mode"] == "embark"
    assert artifact["carrier_id"] == 200
    assert artifact[
        "seat_capacity_before"] == 2
    assert artifact[
        "seat_capacity_after"] == 1
    assert artifact["founder_capable"]
    assert (
        "transport_seat:unit:200",
        -1.0) in outcome.resource_delta


def test_embark_abstains_for_ambiguous_or_full_carrier():
    ambiguous_snapshot, action = (
        _snapshot(
            second_ferry=True))
    full_snapshot, full_action = (
        _snapshot(cargo_count=2))
    model = (
        GroundedTransportTransitionModel())

    ambiguous = model.estimate(
        _request(
            ambiguous_snapshot,
            action))
    full = model.estimate(
        _request(
            full_snapshot,
            full_action))

    assert ambiguous.authority == (
        EstimateAuthority.ABSTAIN)
    assert ambiguous.abstention_reason == (
        "transport-compatible-carrier-not-unique")
    assert ambiguous.to_dict()[
        "model_artifact"][
            "compatible_carrier_ids"
        ] == [200, 201]
    assert full.authority == (
        EstimateAuthority.ABSTAIN)
    assert full.abstention_reason == (
        "transport-compatible-carrier-not-unique")


def test_advertised_disembark_releases_exact_carrier_seat():
    snapshot, action = _snapshot(
        disembark=True)

    estimate = (
        GroundedTransportTransitionModel()
        .estimate(
            _request(
                snapshot, action)))
    artifact = estimate.to_dict()[
        "model_artifact"]
    outcome = estimate.transition.outcomes[
        0]

    assert estimate.authority == (
        EstimateAuthority
        .EXACT_AUTHORITATIVE)
    assert artifact["mode"] == (
        "disembark")
    assert artifact["carrier_id"] == 200
    assert artifact[
        "seat_capacity_before"] == 1
    assert artifact[
        "seat_capacity_after"] == 2
    assert (
        "transport_seat:unit:200",
        1.0) in outcome.resource_delta


def test_transport_estimate_requires_exact_advertised_action_bytes():
    snapshot, action = _snapshot()
    changed = copy.deepcopy(
        action)
    changed["target"]["x"] += 1

    estimate = (
        GroundedTransportTransitionModel()
        .estimate(
            _request(
                snapshot, changed)))

    assert estimate.authority == (
        EstimateAuthority.ABSTAIN)
    assert estimate.abstention_reason == (
        "transport-input-missing")
    assert "advertised_legal_action" in (
        estimate.to_dict()[
            "model_artifact"][
                "missing_fields"])


def test_transport_estimate_is_candidate_utility_invariant():
    snapshot, action = _snapshot()
    model = (
        GroundedTransportTransitionModel())

    first = model.estimate(
        _request(
            snapshot, action,
            utility=1.0))
    second = model.estimate(
        _request(
            snapshot, action,
            utility=1000000.0))

    assert first == second
