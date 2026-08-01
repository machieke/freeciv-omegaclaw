import copy
import json
import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    AtomNamespace,
    AuthorityClass,
    CityEconomyProjector,
    CityRegionPolicy,
    CityRegionProjector,
    CompositeDomainProjector,
    DependentAtomSpaceStore,
    UnitDefenseProjector,
    region_predicate_registry,
    ruleset_digest,
    unit_defense_predicate_registry,
)


FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")


def _root():
    configured = os.environ.get("FREECIV_RULESET_ROOT")
    candidates = [configured] if configured else []
    candidates.append("/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data")
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(
                candidate, "civ2civ3", "techs.ruleset")):
            return candidate
    pytest.skip("set FREECIV_RULESET_ROOT for FDAS region integration")


@pytest.fixture(scope="module")
def ir():
    return compile_ruleset(_root(), "civ2civ3")


def _payload():
    with open(FIXTURE, encoding="utf-8") as stream:
        return copy.deepcopy(json.load(stream))


def _snapshot(payload, seq):
    return ProxyStateDTO.parse("fdas-region", seq, payload).to_snapshot()


def _enemy(payload, unit_id=90, x=3, y=2):
    payload["units"][str(unit_id)] = {
        "activity": "idle",
        "hp": 10,
        "id": unit_id,
        "moves_left": 3,
        "owner": 1,
        "tile": y * 40 + x,
        "type": "Warriors",
        "type_id": 4,
        "upkeep": [0, 0, 0, 0, 0, 0],
        "x": x,
        "y": y,
    }


def _store(ir, policy=None):
    digest = ruleset_digest(ir)
    return DependentAtomSpaceStore(domain_projector=CompositeDomainProjector((
        CityEconomyProjector(ir, digest),
        UnitDefenseProjector(ir, digest),
        CityRegionProjector(policy),
    )))


def test_region_catalog_matches_component_registry():
    with open(os.path.join(REPO, "profile", "fdas_catalog.json"),
              encoding="utf-8") as stream:
        catalog = json.load(stream)
    region_names = set(region_predicate_registry().predicates).difference(
        unit_defense_predicate_registry().predicates)
    component = {
        value["name"] for value in catalog["predicates"]
        if value["name"] in region_names
        and value["status"] == "component-only"
    }
    scopes = {
        value["kind"]: value["status"] for value in catalog["scopes"]}

    assert component == region_names
    assert scopes["region"] == "component-only"


def test_region_requires_exact_topology_and_activation_witness(ir):
    payload = _payload()
    _enemy(payload)
    revision = _store(ir).build(_snapshot(payload, 470))

    assert not tuple(
        value for value in revision.scopes if value.scope_kind == "region")
    assert not any(
        value.key.predicate == "region-activation-reason"
        for value in revision.records)


def test_visible_threat_activates_bounded_exact_region(ir):
    payload = _payload()
    payload["map"].update({"wrap_x": True, "wrap_y": True})
    _enemy(payload)
    snapshot = _snapshot(payload, 471)
    revision = _store(ir).build(snapshot)
    region_scopes = tuple(
        value for value in revision.scopes if value.scope_kind == "region")
    region_records = tuple(
        value for value in revision.records
        if value.key.scope_id == region_scopes[0].scope_id)
    predicates = {value.key.predicate for value in region_records}

    assert len(region_scopes) == 1
    assert region_scopes[0].maximum_atoms == 3000
    assert len(tuple(
        value for value in region_records
        if value.key.predicate == "tile-in-region")) == 49
    assert {
        "region-activation-reason",
        "region-centered-on",
        "tile-adjacent",
        "tile-in-region",
        "visible-threat-near",
    }.issubset(predicates)
    activation = next(
        value for value in region_records
        if value.key.predicate == "region-activation-reason")
    assert activation.key.namespace == AtomNamespace.DIAGNOSTIC
    assert activation.authority == AuthorityClass.POLICY
    threat = next(
        value for value in region_records
        if value.key.predicate == "visible-threat-near")
    assert threat.key.arguments[0].entity_id == "90"
    assert any(
        value.key.path == "visible_enemy_units.90.x"
        for value in threat.supports[0].dependencies)
    assert len(region_records) <= region_scopes[0].maximum_atoms


def test_region_activation_limit_is_deterministic(ir):
    payload = _payload()
    payload["map"].update({"wrap_x": True, "wrap_y": True})
    second = copy.deepcopy(payload["cities"]["3"])
    second.update({"id": 4, "name": "Antium", "tile": 84, "x": 4, "y": 2})
    payload["cities"]["4"] = second
    _enemy(payload, x=3, y=2)
    policy = CityRegionPolicy(maximum_active_regions=1)
    revision = _store(ir, policy).build(_snapshot(payload, 472))
    region_scopes = tuple(
        value for value in revision.scopes if value.scope_kind == "region")

    assert len(region_scopes) == 1
    center = next(
        value for value in revision.records
        if value.key.predicate == "region-centered-on")
    assert center.key.arguments[1].entity_id == "3"


def test_native_reinforcement_route_activates_destination_region(ir):
    payload = _payload()
    payload["map"].update({"wrap_x": True, "wrap_y": True})
    payload["units"]["7"]["transported"] = False
    second = copy.deepcopy(payload["cities"]["3"])
    second.update({"id": 4, "name": "Antium", "tile": 84, "x": 4, "y": 2})
    payload["cities"]["4"] = second
    payload["authoritative"]["movement_routes"] = [{
        "authority": "freeciv-server-pathfinder",
        "destination_tile": 84,
        "estimated_turns": 1,
        "first_step_movement_cost": 1,
        "first_step_tile": 83,
        "initially_transported": False,
        "movement_points_remaining": 2,
        "moves_left_at_request": 3,
        "origin_tile": 82,
        "path_directions": [0, 0],
        "path_length": 2,
        "reachable": True,
        "schema_version": "1.0",
        "source_seq": 475,
        "total_movement_cost": 4,
        "transported_at_request": False,
        "turn": 12,
        "unit_id": 7,
    }]
    revision = _store(ir).build(_snapshot(payload, 475))
    center = next(
        value for value in revision.records
        if value.key.predicate == "region-centered-on")
    activation = next(
        value for value in revision.records
        if value.key.predicate == "region-activation-reason")

    assert center.key.arguments[1].entity_id == "4"
    assert activation.key.arguments[1].symbol == "native-route-destination"
    assert any(
        value.key.path == "movement_routes.7:84.destination_tile"
        for value in activation.supports[0].dependencies)


def test_threat_removal_retracts_focused_region_and_matches_cold(ir):
    first_payload = _payload()
    first_payload["map"].update({"wrap_x": True, "wrap_y": True})
    _enemy(first_payload)
    first = _snapshot(first_payload, 473)
    second_payload = copy.deepcopy(first_payload)
    del second_payload["units"]["90"]
    second_payload["authoritative"]["source_seq"] = 474
    second = _snapshot(second_payload, 474)
    store = _store(ir)
    prior = store.build(first)

    verification = store.verify_incremental(second, first, prior)
    revision = store.update(second)

    assert verification.equivalent, verification.to_dict()
    assert not tuple(
        value for value in revision.scopes if value.scope_kind == "region")
    assert not any(
        value.key.predicate.startswith("region-")
        or value.key.predicate in ("tile-adjacent", "tile-in-region")
        for value in revision.records)
