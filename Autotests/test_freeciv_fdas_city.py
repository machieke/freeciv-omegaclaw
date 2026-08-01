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
    ImpactCandidate,
    compare_shadow_candidates,
)
from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atoms import _build_legacy_atomspaces  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    AtomQuery,
    AtomNamespace,
    AuthorityClass,
    CITY_ECONOMY_GROUNDING_SPECS,
    CityEconomyProjector,
    DependentAtomSpaceStore,
    EntityRef,
    SymbolRef,
    TypedGroundingRegistry,
    city_economy_predicate_registry,
    legacy_predicate_registry,
    legacy_view_from_revision,
    ruleset_digest,
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
    pytest.skip("set FREECIV_RULESET_ROOT for FDAS city integration")


@pytest.fixture(scope="module")
def ir():
    return compile_ruleset(_root(), "civ2civ3")


def _payload():
    with open(FIXTURE, encoding="utf-8") as stream:
        return json.load(stream)


def _snapshot(payload=None, seq=431):
    return ProxyStateDTO.parse(
        "fdas-city-economy", seq, payload or _payload()).to_snapshot()


def _predicates(revision):
    return {value.key.predicate for value in revision.records}


def test_phase4_catalog_matches_component_registry():
    with open(os.path.join(REPO, "profile", "fdas_catalog.json"),
              encoding="utf-8") as stream:
        catalog = json.load(stream)
    component_groundings = {
        value["name"] for value in catalog["groundings"]
        if value["status"] == "component-only"}
    component_predicates = {
        value["name"] for value in catalog["predicates"]
        if (value["status"] == "component-only"
            and value["namespace"] != "operation")}

    assert component_groundings == {
        value.grounding_id for value in CITY_ECONOMY_GROUNDING_SPECS}
    assert component_predicates == set(
        city_economy_predicate_registry().predicates
    ).difference(legacy_predicate_registry().predicates)


def test_typed_city_economy_groundings_match_authoritative_fields(ir):
    snapshot = _snapshot()
    registry = TypedGroundingRegistry(
        ir, ruleset_digest=ruleset_digest(ir))
    checks = {
        "city.food-stock": 11,
        "city.food-produced": 8,
        "city.food-surplus": 2,
        "city.shield-stock": 6,
        "city.shield-produced": 5,
        "city.shield-surplus": 3,
    }
    for name, expected in checks.items():
        result = registry.evaluate(name, snapshot, 3)
        assert result.available
        assert result.value == expected
        assert result.dependencies
        assert result.result_hash
        assert registry.evaluate(name, snapshot, 3) is result

    assert registry.evaluate(
        "city.buildability", snapshot, 3, "unit", "Warriors").value is True
    assert registry.evaluate(
        "city.buildability", snapshot, 3, "unit", "Battleship").value is False
    assert registry.evaluate(
        "city.production-cost", snapshot, 3, "unit", "Warriors").value == 10
    assert registry.evaluate(
        "city.production-eta", snapshot, 3, "unit", "Warriors").value == 2
    assert registry.evaluate(
        "economy.gold-stockpile", snapshot, 0).value == 37
    # The capture predates the explicit upkeep-style contract, so parity with
    # Impact uses city gold surplus minus nation-paid unit upkeep.
    assert registry.evaluate("economy.net-gpt", snapshot, 0).value == 1
    assert registry.evaluate(
        "economy.rate-tuple", snapshot, 0).value == (30, 60, 10)
    assert registry.evaluate("research.progress", snapshot, 0).value == 24
    assert registry.evaluate("research.cost", snapshot, 0).value == 80
    assert registry.evaluate(
        "research.beakers-per-turn", snapshot, 0).value == 9
    assert registry.evaluate(
        "research.completion-eta", snapshot, 0).value == 7


def test_unavailable_grounding_is_explicit_not_false(ir):
    snapshot = _snapshot()
    result = TypedGroundingRegistry(
        ir, ruleset_digest=ruleset_digest(ir)).evaluate(
            "city.food-used", snapshot, 3)

    assert not result.available
    assert result.value is None
    assert "unavailable" in result.diagnostic
    assert result.dependencies


def test_rich_projection_is_symbolic_supported_and_legacy_exact(ir):
    snapshot = _snapshot()
    projector = CityEconomyProjector(ir, ruleset_digest(ir))
    revision = DependentAtomSpaceStore(
        domain_projector=projector).build(snapshot)
    legacy = legacy_view_from_revision(revision)

    assert legacy == _build_legacy_atomspaces(snapshot)
    assert len(revision.scopes) == 2 + len(snapshot.cities)
    assert {
        "city-food-secure",
        "city-production-active",
        "current-player",
        "current-turn",
        "legal-action-for",
        "legal-action-type",
        "research-target",
        "research-throughput-active",
        "treasury-structurally-safe",
    }.issubset(_predicates(revision))
    assert all(
        isinstance(argument, (EntityRef, SymbolRef))
        for record in revision.records for argument in record.key.arguments)
    assert all(record.supports for record in revision.records)
    assert all(
        record.authority == AuthorityClass.DETERMINISTIC_DERIVED
        for record in revision.records
        if record.key.namespace == AtomNamespace.DERIVED)
    assert not any(
        record.authority in (AuthorityClass.POLICY, AuthorityClass.CONTROL_MODEL)
        for record in revision.records)
    assert sum(
        record.key.predicate == "legal-action-type"
        for record in revision.records) == len(snapshot.legal_action_json)


def test_deficit_derivations_use_exact_fields_and_named_policy(ir):
    payload = copy.deepcopy(_payload())
    payload["cities"]["3"].update({
        "disorder": True,
        "had_famine": True,
        "surplus": [0, 0, 4, 1, 0, 9],
    })
    payload["authoritative"]["player"].update({
        "gold": 0,
        "gold_per_turn": -2,
        "gold_upkeep_reserve": 3,
        "gold_upkeep_style": "Mixed",
        "unit_gold_upkeep": 3,
    })
    payload["authoritative"]["research"]["beakers_per_turn"] = 0
    snapshot = _snapshot(payload, 432)
    revision = DependentAtomSpaceStore(domain_projector=CityEconomyProjector(
        ir, ruleset_digest(ir))).build(snapshot)
    predicates = _predicates(revision)

    assert {
        "city-famine-recorded",
        "city-food-deficit",
        "city-in-disorder",
        "city-order-deficit",
        "city-production-stalled",
        "research-throughput-stalled",
        "treasury-below-reserve",
    }.issubset(predicates)
    assert "city-food-secure" not in predicates
    food = next(
        record for record in revision.records
        if record.key.predicate == "city-food-deficit")
    assert food.key.arguments[1] == SymbolRef(
        "food-policy", "food-surplus-reserve:1:v1.0")
    assert any(
        dependency.key.kind == "policy"
        for dependency in food.supports[0].dependencies)


def test_rich_incremental_and_cold_builds_are_equivalent(ir):
    first = _snapshot()
    payload = copy.deepcopy(_payload())
    payload["cities"]["3"]["surplus"][0] = 0
    payload["authoritative"]["source_seq"] = 432
    second = _snapshot(payload, 432)
    store = DependentAtomSpaceStore(domain_projector=CityEconomyProjector(
        ir, ruleset_digest(ir)))
    prior = store.build(first)
    verification = store.verify_incremental(second, first, prior)

    assert verification.equivalent, verification.to_dict()
    updated = store.update(second)
    assert "city-food-deficit" in _predicates(updated)
    assert "city-food-secure" not in _predicates(updated)
    assert legacy_view_from_revision(updated) == _build_legacy_atomspaces(second)


def test_current_queue_funding_uses_cost_progress_food_and_treasury(ir):
    payload = copy.deepcopy(_payload())
    payload["cities"]["3"]["production_kind"] = 6
    payload["authoritative"]["player"].update({
        "gold_upkeep_style": "Mixed",
        "gold_upkeep_reserve": 0,
        "unit_gold_upkeep": 0,
    })
    digest = ruleset_digest(ir)
    funded = DependentAtomSpaceStore(domain_projector=CityEconomyProjector(
        ir, digest)).build(_snapshot(payload, 434))
    row = next(
        value for value in funded.records
        if value.key.predicate == "city-queue-funded")

    assert row.key.arguments[1] == EntityRef("production-target", "Warriors")
    assert any(
        dependency.key.kind == "ruleset-digest"
        for dependency in row.supports[0].dependencies)

    payload["cities"]["3"]["surplus"][1] = 0
    payload["cities"]["3"]["prod"][1] = 0
    payload["authoritative"]["source_seq"] = 435
    unfunded = DependentAtomSpaceStore(domain_projector=CityEconomyProjector(
        ir, digest)).build(_snapshot(payload, 435))
    assert "city-queue-unfunded" in _predicates(unfunded)
    assert "city-queue-funded" not in _predicates(unfunded)


def test_explain_and_why_not_are_revision_bound_and_deterministic(ir):
    snapshot = _snapshot()
    store = DependentAtomSpaceStore(domain_projector=CityEconomyProjector(
        ir, ruleset_digest(ir)))
    revision = store.build(snapshot)
    view = store.query_current(snapshot.identity.game_id, snapshot.player_id)
    secure = next(
        record for record in revision.records
        if record.key.predicate == "city-food-secure")

    first = view.explain(secure.atom_id)
    second = view.explain(secure.atom_id)
    blocked = view.why_not(AtomQuery(
        predicate="city-food-deficit",
        namespace=AtomNamespace.DERIVED,
        arguments=secure.key.arguments,
        scope_id=secure.key.scope_id,
    ))

    assert first == second
    assert first["structural_hash"]
    assert first["supports"][0]["dependencies"]
    assert blocked["status"] == "BLOCKED"
    assert blocked["blockers"][0]["atom_id"] == secure.atom_id
    unknown = view.why_not(AtomQuery(
        predicate="city-order-deficit",
        namespace=AtomNamespace.DERIVED,
        arguments=(EntityRef("city", "3"),),
        scope_id=secure.key.scope_id,
    ))
    assert unknown["status"] == "UNKNOWN"
    assert unknown["unknown"]


def test_local_goals_and_shadow_operations_are_legal_bound_without_authority(ir):
    payload = copy.deepcopy(_payload())
    payload["cities"]["3"].update({
        "disorder": True,
        "surplus": [0, 0, 4, 1, 0, 9],
    })
    payload["authoritative"]["player"].update({
        "gold": 0,
        "gold_per_turn": -2,
        "gold_upkeep_reserve": 3,
        "gold_upkeep_style": "Mixed",
        "unit_gold_upkeep": 3,
    })
    payload["authoritative"]["research"]["beakers_per_turn"] = 0
    payload["legal_actions"].extend(({
        "type": "city_governor",
        "city_id": 3,
        "target": {
            "food_surplus_reserve": 1,
            "require_happy": True,
        },
        "is_valid": True,
    }, {
        "type": "player_rates",
        "player_id": 0,
        "target": {
            "tax_rate": 50,
            "science_rate": 40,
            "luxury_rate": 10,
        },
        "is_valid": True,
    }))
    snapshot = _snapshot(payload, 433)
    digest = ruleset_digest(ir)
    store = DependentAtomSpaceStore(domain_projector=CityEconomyProjector(
        ir, digest))
    revision = store.build(snapshot)
    goals = GoalFactory().instantiate(
        revision,
        store.query_current(snapshot.identity.game_id, snapshot.player_id),
    )
    candidates = CandidateOperationFactory(ir, digest).instantiate(
        snapshot, goals)

    assert {value.deficit_predicate for value in goals} == {
        "city-food-deficit",
        "city-order-deficit",
        "city-production-stalled",
        "research-throughput-stalled",
        "treasury-below-reserve",
    }
    assert {value.global_goal_kind for value in goals} == {
        "food_sustainability",
        "governance",
        "production_continuity",
        "research_sustainability",
        "treasury_sustainability",
    }
    assert len(candidates) == 4
    assert all(value.legal_bound for value in candidates)
    assert all(value.action_key in snapshot.legal_action_json
               for value in candidates)
    assert all(not value.authority_eligible for value in candidates)
    assert all(value.blockers == ("uncompiled-action-effect",)
               for value in candidates)
    assert all(value.resource_keys for value in candidates)
    assert candidates == CandidateOperationFactory(ir, digest).instantiate(
        snapshot, goals)
    legacy = tuple(
        ImpactCandidate(
            value.action,
            "legacy_{}".format(value.action["action_type"]),
            1.0,
            "test comparison",
        )
        for value in candidates[:2]) + (ImpactCandidate(
            {
                "action_type": "tech_research",
                "actor_id": 0,
                "target": {"tech_name": "Alphabet"},
            },
            "research",
            1.0,
            "legacy-only comparison route",
        ),)
    comparison = compare_shadow_candidates(snapshot, legacy, candidates)
    assert comparison.overlapping_action_keys
    assert len(comparison.missing_legacy) == 1
    assert comparison.missing_legacy[0]["reason"] == (
        "no-active-fdas-deficit-route")
    assert comparison.extra_fdas
    assert comparison.legal_binding_failures == ()
    assert comparison.authority_violations == ()
    assert comparison.safety_downgrades == ()
    assert comparison.comparison_hash
