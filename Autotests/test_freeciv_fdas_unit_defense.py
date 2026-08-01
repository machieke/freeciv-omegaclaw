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
from freeciv_agent.planning import (  # noqa: E402
    CandidateOperationFactory,
    GoalFactory,
)
from freeciv_agent.pressure import DependentAtomPressureAdapter  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    AtomNamespace,
    AuthorityClass,
    CityEconomyProjector,
    CompositeDomainProjector,
    DependentAtomSpaceStore,
    TypedGroundingRegistry,
    UNIT_DEFENSE_GROUNDING_SPECS,
    UnitDefenseProjector,
    legacy_view_from_revision,
    ruleset_digest,
    unit_defense_predicate_registry,
)
from freeciv_agent.state.atoms import _build_legacy_atomspaces  # noqa: E402


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
    pytest.skip("set FREECIV_RULESET_ROOT for FDAS unit integration")


@pytest.fixture(scope="module")
def ir():
    return compile_ruleset(_root(), "civ2civ3")


def _payload():
    with open(FIXTURE, encoding="utf-8") as stream:
        return copy.deepcopy(json.load(stream))


def _snapshot(payload=None, seq=460):
    return ProxyStateDTO.parse(
        "fdas-unit-defense", seq, payload or _payload()).to_snapshot()


def _store(ir):
    digest = ruleset_digest(ir)
    return DependentAtomSpaceStore(domain_projector=CompositeDomainProjector((
        CityEconomyProjector(ir, digest),
        UnitDefenseProjector(ir, digest),
    )))


def _predicates(revision):
    return {value.key.predicate for value in revision.records}


def test_unit_catalog_matches_component_contract():
    with open(os.path.join(REPO, "profile", "fdas_catalog.json"),
              encoding="utf-8") as stream:
        catalog = json.load(stream)
    grounding_names = {
        value.grounding_id for value in UNIT_DEFENSE_GROUNDING_SPECS}
    catalog_groundings = {
        value["name"] for value in catalog["groundings"]
        if value["name"] in grounding_names
        and value["status"] == "component-only"}
    predicate_names = set(unit_defense_predicate_registry().predicates)
    city_names = {
        value["name"] for value in catalog["predicates"]
        if value["status"] in ("legacy", "component-only")
        and value["name"] in predicate_names
        and not (value["name"].startswith("unit-")
                 or value["name"].startswith("city-garrison")
                 or value["name"].startswith("city-visible-threat")
                 or value["name"].startswith("visible-enemy"))}
    unit_catalog = {
        value["name"] for value in catalog["predicates"]
        if value["status"] == "component-only"
        and value["name"] in predicate_names
    }.difference(city_names)
    unit_registry = predicate_names.difference(city_names).difference({
        "unit-activity", "unit-at", "unit-type", "owns-unit"})

    assert catalog_groundings == grounding_names
    assert unit_catalog == unit_registry


def test_unit_groundings_match_ruleset_and_local_garrison(ir):
    snapshot = _snapshot()
    registry = TypedGroundingRegistry(
        ir, ruleset_digest=ruleset_digest(ir))

    profile = registry.evaluate("unit.combat-profile", snapshot, 7)
    assert profile.available
    assert profile.value == {
        "attack": 1,
        "defense": 1,
        "firepower": 1,
        "hitpoints": 10,
        "move_rate": 1,
        "unit_class": ["Land"],
    }
    assert registry.evaluate(
        "unit.persistent-defender", snapshot, 7).value is True
    assert registry.evaluate(
        "city.required-garrison-count", snapshot, 3, 3).value == 1
    assert registry.evaluate(
        "city.local-garrison-count", snapshot, 3).value == 1


def test_garrison_projection_is_factual_supported_and_legacy_exact(ir):
    snapshot = _snapshot()
    revision = _store(ir).build(snapshot)
    predicates = _predicates(revision)

    assert legacy_view_from_revision(revision) == _build_legacy_atomspaces(snapshot)
    assert {
        "city-garrison-covered",
        "unit-has-capability",
        "unit-persistent-defender",
        "unit-protects-city",
        "unit-required-garrison",
    }.issubset(predicates)
    assert "city-garrison-deficit" not in predicates
    assert len(tuple(
        value for value in revision.scopes
        if value.scope_kind == "unit-facts")) == 1
    assert all(
        value.authority == AuthorityClass.DETERMINISTIC_DERIVED
        for value in revision.records
        if value.key.namespace == AtomNamespace.DERIVED
        and value.key.predicate.startswith("unit-"))


def test_fortification_opportunity_does_not_create_defense_deficit(ir):
    payload = _payload()
    payload["legal_actions"].append({
        "type": "unit_fortify", "unit_id": 7, "is_valid": True})
    snapshot = _snapshot(payload, 461)
    revision = _store(ir).build(snapshot)
    predicates = _predicates(revision)

    assert "unit-fortification-opportunity" in predicates
    assert "city-garrison-covered" in predicates
    assert "city-garrison-deficit" not in predicates
    opportunity = next(
        value for value in revision.records
        if value.key.predicate == "unit-fortification-opportunity")
    assert opportunity.supports
    assert any(
        dependency.key.path.startswith("legal_actions.")
        for dependency in opportunity.supports[0].dependencies)


def test_defender_removal_creates_deficit_and_incremental_matches_cold(ir):
    first = _snapshot()
    payload = _payload()
    payload["units"] = {}
    payload["authoritative"]["source_seq"] = 462
    second = _snapshot(payload, 462)
    store = _store(ir)
    prior = store.build(first)
    verification = store.verify_incremental(second, first, prior)
    revision = store.update(second)

    assert verification.equivalent, verification.to_dict()
    assert "city-garrison-deficit" in _predicates(revision)
    assert "city-garrison-covered" not in _predicates(revision)
    assert not tuple(
        value for value in revision.scopes
        if value.scope_kind == "unit-facts")


def test_visible_threat_requires_explicit_topology_and_never_proves_absence(ir):
    payload = _payload()
    payload["units"]["8"] = {
        "id": 8,
        "owner": 1,
        "type": "Warriors",
        "type_id": 4,
        "tile": 83,
        "x": 3,
        "y": 2,
        "moves_left": 3,
        "hp": 10,
        "activity": "idle",
        "upkeep": [0, 0, 0, 0, 0, 0],
    }
    unknown_topology = _store(ir).build(_snapshot(payload, 463))
    assert "visible-enemy-unit" in _predicates(unknown_topology)
    assert "city-visible-threat" not in _predicates(unknown_topology)
    assert not any(
        "not-threatened" in value.key.predicate
        for value in unknown_topology.records)

    payload["map"].update({"wrap_x": True, "wrap_y": False})
    payload["authoritative"]["source_seq"] = 464
    exact_topology = _store(ir).build(_snapshot(payload, 464))
    threat = next(
        value for value in exact_topology.records
        if value.key.predicate == "city-visible-threat")
    assert threat.key.arguments[1].entity_id == "8"
    assert any(
        dependency.key.path == "map_wrap_x"
        for dependency in threat.supports[0].dependencies)


def test_garrison_deficit_regresses_to_legal_move_but_protects_source(ir):
    payload = _payload()
    target = copy.deepcopy(payload["cities"]["3"])
    target.update({
        "id": 4,
        "name": "Antium",
        "tile": 83,
        "x": 3,
        "y": 2,
    })
    payload["cities"]["4"] = target
    snapshot = _snapshot(payload, 465)
    digest = ruleset_digest(ir)
    store = _store(ir)
    revision = store.build(snapshot)
    goals = GoalFactory().instantiate(
        revision,
        store.query_current(snapshot.identity.game_id, snapshot.player_id),
    )
    candidates = CandidateOperationFactory(ir, digest).instantiate(
        snapshot, goals)
    garrison_goals = tuple(
        value for value in goals
        if value.deficit_predicate == "city-garrison-deficit")
    routes = tuple(
        value for value in candidates
        if value.action.get("action_type") == "unit_move")

    assert len(garrison_goals) == 1
    assert garrison_goals[0].global_goal_kind == "survival"
    assert garrison_goals[0].target_key.arguments[0].entity_id == "4"
    assert len(routes) == 1
    assert routes[0].operation.participants[0].actor_class == "unit"
    assert routes[0].operation.participants[0].actor_id == "7"
    assert routes[0].resource_keys == ("unit-action:7",)
    assert set(routes[0].blockers) == {
        "protected-source-garrison", "uncompiled-action-effect"}
    evaluation = DependentAtomPressureAdapter().evaluate(
        revision, garrison_goals, routes)
    operation = evaluation.context.operations[0]
    assert operation.mode == "expand"
    assert operation.payload["authority_eligible"] is False
    assert all(
        evaluation.pressure_result.pressure(
            goal.goal_id, operation.atom_id).value("act") == 0.0
        for goal in evaluation.context.goals)
