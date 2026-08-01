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
        "settlement-site-contested-by",
    }.issubset(predicates)
    requirement = next(
        value for value in contested.records
        if value.key.predicate == "settlement-escort-required")
    assert [value.entity_id for value in requirement.key.arguments] == [
        "7", "tile:83", "90"]
    assert any(
        value.key.path == "visible_enemy_units.90.tile"
        for value in requirement.supports[0].dependencies)


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
        and value["name"].startswith(("founder-", "settlement-"))}
    expected = {
        value for value in settlement_predicate_registry().predicates
        if value.startswith(("founder-", "settlement-"))}

    assert names == expected
