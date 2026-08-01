import copy
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    DependentAtomSpaceStore,
    SettlementSiteProjector,
    settlement_predicate_registry,
)


FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")


def _payload(visible_target=False, enemy_at_target=False):
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    payload["legal_actions"] = [{
        "action_type": "unit_build_city",
        "actor_id": 7,
        "is_valid": True,
    }, {
        "action_type": "unit_move",
        "actor_id": 7,
        "is_valid": True,
        "settlement_site_eligible": True,
        "target": {"x": 3, "y": 2},
    }]
    if visible_target:
        payload["visible_tiles"].append(83)
    if enemy_at_target:
        payload["units"]["90"] = {
            "activity": "idle",
            "hp": 10,
            "id": 90,
            "moves_left": 3,
            "owner": 1,
            "tile": 83,
            "type": "Warriors",
            "type_id": 4,
            "upkeep": [0, 0, 0, 0, 0, 0],
            "x": 3,
            "y": 2,
        }
    return payload


def _snapshot(payload, seq):
    return ProxyStateDTO.parse(
        "fdas-settlement-sites", seq, payload).to_snapshot()


def _escort_route(source_seq):
    return {
        "authority": "freeciv-server-pathfinder",
        "destination_tile": 82,
        "estimated_turns": 1,
        "first_step_movement_cost": 1,
        "first_step_tile": 82,
        "initially_transported": False,
        "movement_points_remaining": 2,
        "moves_left_at_request": 3,
        "origin_tile": 81,
        "path_directions": [0],
        "path_length": 1,
        "reachable": True,
        "schema_version": "1.0",
        "source_seq": source_seq,
        "total_movement_cost": 1,
        "transported_at_request": False,
        "turn": 12,
        "unit_id": 8,
    }


def _predicates(revision, tile):
    scope = next(
        value for value in revision.scopes
        if (value.scope_kind == "settlement-site"
            and value.root_entities[0].entity_id == "tile:{}".format(tile)))
    return {
        value.key.predicate for value in revision.records
        if value.key.scope_id == scope.scope_id}


def test_legal_found_and_typed_move_create_distinct_exact_sites():
    snapshot = _snapshot(_payload(visible_target=True), 520)
    revision = DependentAtomSpaceStore(
        domain_projector=SettlementSiteProjector()).build(snapshot)
    site_scopes = [
        value for value in revision.scopes
        if value.scope_kind == "settlement-site"]

    assert [value.root_entities[0].entity_id for value in site_scopes] == [
        "tile:82", "tile:83"]
    current = _predicates(revision, 82)
    adjacent = _predicates(revision, 83)
    assert {
        "founder-can-settle-now",
        "founder-current-settlement-capability",
        "settlement-site-at",
        "settlement-site-currently-uncontested",
        "settlement-site-eligible-for",
    }.issubset(current)
    assert {
        "founder-current-settlement-capability",
        "founder-legal-site-step",
        "settlement-site-at",
        "settlement-site-currently-uncontested",
        "settlement-site-eligible-for",
    }.issubset(adjacent)
    assert "founder-can-settle-now" not in adjacent
    legal_step = next(
        value for value in revision.records
        if value.key.predicate == "founder-legal-site-step")
    assert any(
        value.key.path.startswith("legal_actions.")
        for value in legal_step.supports[0].dependencies)


def test_fog_is_unknown_and_visible_enemy_creates_exact_escort_requirement():
    fog = DependentAtomSpaceStore(
        domain_projector=SettlementSiteProjector()).build(
            _snapshot(_payload(visible_target=False), 521))
    assert "settlement-site-currently-uncontested" not in _predicates(fog, 83)
    assert "settlement-escort-required" not in _predicates(fog, 83)

    contested = DependentAtomSpaceStore(
        domain_projector=SettlementSiteProjector()).build(
            _snapshot(_payload(
                visible_target=True, enemy_at_target=True), 522))
    predicates = _predicates(contested, 83)
    assert "settlement-site-currently-uncontested" not in predicates
    assert {
        "settlement-escort-required",
        "settlement-site-blocked-by-threat",
        "settlement-site-contested-by",
        "settlement-visible-threat-near",
    }.issubset(predicates)
    requirement = next(
        value for value in contested.records
        if value.key.predicate == "settlement-escort-required")
    assert [value.entity_id for value in requirement.key.arguments] == [
        "7", "tile:83", "90"]
    assert any(
        value.key.path == "visible_enemy_units.90.tile"
        for value in requirement.supports[0].dependencies)


def test_escort_is_actionable_only_with_current_exact_catch_route():
    payload = _payload(visible_target=True, enemy_at_target=True)
    escort = copy.deepcopy(payload["units"]["7"])
    escort.update({
        "id": 8, "tile": 81, "transported": False,
        "transported_by": 0, "x": 1, "y": 2})
    payload["units"]["8"] = escort
    payload["legal_actions"].append({
        "action_type": "unit_move",
        "actor_id": 8,
        "is_valid": True,
        "target": {"x": 2, "y": 2},
    })
    payload["authoritative"]["movement_routes"] = [_escort_route(526)]
    revision = DependentAtomSpaceStore(
        domain_projector=SettlementSiteProjector()).build(
            _snapshot(payload, 526))
    predicates = _predicates(revision, 83)

    assert {
        "escort-can-catch-founder",
        "settlement-actionable-escort",
        "settlement-escort-required",
    }.issubset(predicates)
    assert "settlement-site-blocked-by-threat" not in predicates
    actionable = next(
        value for value in revision.records
        if value.key.predicate == "settlement-actionable-escort")
    assert [value.entity_id for value in actionable.key.arguments] == [
        "7", "tile:83", "8"]
    assert any(
        value.key.path == "movement_routes.8:82.estimated_turns"
        for value in actionable.supports[0].dependencies)


def test_visible_nearby_threat_requires_explicit_topology():
    payload = _payload(visible_target=True, enemy_at_target=True)
    payload["map"]["wrap_x"] = False
    payload["map"]["wrap_y"] = False
    payload["units"]["90"].update({"tile": 84, "x": 4, "y": 2})
    exact = DependentAtomSpaceStore(
        domain_projector=SettlementSiteProjector()).build(
            _snapshot(payload, 527))
    predicates = _predicates(exact, 83)

    assert "settlement-site-contested-by" not in predicates
    assert "settlement-site-currently-uncontested" in predicates
    assert {
        "settlement-escort-required",
        "settlement-site-blocked-by-threat",
        "settlement-visible-threat-near",
    }.issubset(predicates)

    payload["map"].pop("wrap_x")
    payload["map"].pop("wrap_y")
    unknown = DependentAtomSpaceStore(
        domain_projector=SettlementSiteProjector()).build(
            _snapshot(payload, 528))
    unknown_predicates = _predicates(unknown, 83)
    assert "settlement-visible-threat-near" not in unknown_predicates
    assert "settlement-escort-required" not in unknown_predicates


def test_visible_uncontested_site_retracts_incrementally_when_enemy_appears():
    first = _snapshot(_payload(visible_target=True), 524)
    second = _snapshot(
        _payload(visible_target=True, enemy_at_target=True), 525)
    store = DependentAtomSpaceStore(
        domain_projector=SettlementSiteProjector())
    prior = store.build(first)

    verification = store.verify_incremental(second, first, prior)
    current = store.update(second)

    assert verification.equivalent, verification.to_dict()
    assert "settlement-site-currently-uncontested" not in _predicates(
        current, 83)
    assert "settlement-site-contested-by" in _predicates(current, 83)


def test_untyped_move_never_creates_settlement_site():
    payload = _payload()
    payload["legal_actions"] = [payload["legal_actions"][1]]
    payload["legal_actions"][0].pop("settlement_site_eligible")
    revision = DependentAtomSpaceStore(
        domain_projector=SettlementSiteProjector()).build(
            _snapshot(payload, 523))

    assert not any(
        value.scope_kind == "settlement-site" for value in revision.scopes)
    assert not any(
        value.key.predicate.startswith(("founder-", "settlement-"))
        for value in revision.records)


def test_settlement_catalog_matches_component_registry():
    with open(os.path.join(REPO, "profile", "fdas_catalog.json"),
              encoding="utf-8") as stream:
        catalog = json.load(stream)
    names = {
        value["name"] for value in catalog["predicates"]
        if value["status"] == "component-only"
        and value["name"].startswith(("founder-", "settlement-"))
        and not value["name"].startswith("founder-population-recovery-")}
    expected = {
        value for value in settlement_predicate_registry().predicates
        if value.startswith(("founder-", "settlement-"))}

    assert names == expected
