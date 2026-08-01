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
    AuthorityClass,
    DependentAtomSpaceStore,
    RouteCorridorProjector,
    route_corridor_predicate_registry,
)


FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")


def _payload(seq=510, reachable=True):
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    payload["units"]["7"]["transported"] = False
    payload["authoritative"]["movement_routes"] = [{
        "authority": "freeciv-server-pathfinder",
        "destination_tile": 84,
        "estimated_turns": 1 if reachable else 0,
        "first_step_movement_cost": 1 if reachable else 0,
        "first_step_tile": 83 if reachable else 82,
        "initially_transported": False,
        "movement_points_remaining": 2 if reachable else 3,
        "moves_left_at_request": 3,
        "origin_tile": 82,
        "path_directions": [0, 0] if reachable else [],
        "path_length": 2 if reachable else 0,
        "reachable": reachable,
        "schema_version": "1.0",
        "source_seq": seq,
        "total_movement_cost": 2 if reachable else 0,
        "transported_at_request": False,
        "turn": 12,
        "unit_id": 7,
    }]
    return payload


def _snapshot(payload, seq):
    return ProxyStateDTO.parse(
        "fdas-route-corridor", seq, payload).to_snapshot()


def test_exact_native_route_gets_one_bounded_dependency_backed_scope():
    snapshot = _snapshot(_payload(), 510)
    revision = DependentAtomSpaceStore(
        domain_projector=RouteCorridorProjector()).build(snapshot)
    scopes = [
        value for value in revision.scopes
        if value.scope_kind == "route-corridor"]
    records = [
        value for value in revision.records
        if value.key.scope_id == scopes[0].scope_id]

    assert len(scopes) == 1
    assert scopes[0].maximum_atoms == 50
    assert scopes[0].retention_policy == "snapshot-revision"
    assert {
        "route-corridor-current-legal-step",
        "route-corridor-destination",
        "route-corridor-first-step",
        "route-corridor-for",
        "route-corridor-origin",
        "route-corridor-reachable",
        "route-corridor-visibility",
    } == {value.key.predicate for value in records}
    assert all(
        value.authority == AuthorityClass.DETERMINISTIC_DERIVED
        for value in records)
    legal = next(
        value for value in records
        if value.key.predicate == "route-corridor-current-legal-step")
    assert any(
        value.key.path == "movement_routes.7:84.first_step_tile"
        for value in legal.supports[0].dependencies)
    assert any(
        value.key.path.startswith("legal_actions.")
        for value in legal.supports[0].dependencies)
    destination = next(
        value for value in records
        if value.key.predicate == "route-corridor-destination")
    assert destination.key.arguments[1].entity_id == "84"


def test_missing_legal_step_and_unreachable_route_fail_closed():
    no_action = _payload(511)
    no_action["legal_actions"] = []
    no_action_revision = DependentAtomSpaceStore(
        domain_projector=RouteCorridorProjector()).build(
            _snapshot(no_action, 511))
    assert "route-corridor-current-legal-step" not in {
        value.key.predicate for value in no_action_revision.records}
    assert "route-corridor-reachable" in {
        value.key.predicate for value in no_action_revision.records}

    unreachable = DependentAtomSpaceStore(
        domain_projector=RouteCorridorProjector()).build(
            _snapshot(_payload(512, reachable=False), 512))
    assert not any(
        value.scope_kind == "route-corridor"
        for value in unreachable.scopes)
    assert not any(
        value.key.predicate.startswith("route-corridor-")
        for value in unreachable.records)


def test_same_turn_legal_step_retraction_matches_cold_projection():
    store = DependentAtomSpaceStore(
        domain_projector=RouteCorridorProjector())
    first = _snapshot(_payload(513), 513)
    before = store.build(first)
    changed_payload = _payload(514)
    changed_payload["legal_actions"] = []
    changed = _snapshot(changed_payload, 514)

    after = store.update(changed)
    verification = store.verify_incremental(changed, first, before)

    assert verification.equivalent
    assert after.metrics.invalidated_supports >= 1
    assert "route-corridor-current-legal-step" not in {
        value.key.predicate for value in after.records}
    assert "route-corridor-reachable" in {
        value.key.predicate for value in after.records}


def test_route_corridor_catalog_matches_component_registry():
    with open(os.path.join(REPO, "profile", "fdas_catalog.json"),
              encoding="utf-8") as stream:
        catalog = json.load(stream)
    names = {
        value["name"] for value in catalog["predicates"]
        if value["status"] == "component-only"
        and value["name"].startswith("route-corridor-")}

    assert names == {
        value for value in route_corridor_predicate_registry().predicates
        if value.startswith("route-corridor-")}
