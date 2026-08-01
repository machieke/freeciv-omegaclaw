import copy
import json
import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    DependentAtomSpaceStore,
    PopulationRecoveryProjector,
    population_recovery_predicate_registry,
    population_recovery_profile,
)


FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")


def _rule(flags=("Cities", "AddToCity"), pop_cost=2):
    return SimpleNamespace(
        target_kind="unit",
        display_name="Settlers",
        rule_name="Settlers",
        quantitative={"pop_cost": {"value": pop_cost}},
        traits={"flags": {"values": list(flags)}},
    )


def _ruleset(flags=("Cities", "AddToCity"), pop_cost=2):
    return SimpleNamespace(rules=(_rule(flags, pop_cost),))


def _payload(join=True, colocated=True):
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    payload["units"]["7"]["type"] = "Settlers"
    payload["units"]["7"]["type_id"] = 0
    if not colocated:
        payload["units"]["7"]["tile"] = 83
        payload["units"]["7"]["x"] = 3
    payload["legal_actions"] = []
    if join:
        payload["legal_actions"].append({
            "action_type": "unit_join_city",
            "actor_id": 7,
            "is_valid": True,
            "target": {"city_id": 3},
        })
    return payload


def _snapshot(payload, source_seq):
    return ProxyStateDTO.parse(
        "fdas-recovery", source_seq, payload).to_snapshot()


def _revision(payload, source_seq, ruleset=None):
    ruleset = ruleset or _ruleset()
    snapshot = _snapshot(payload, source_seq)
    projector = PopulationRecoveryProjector(ruleset, "ruleset-proof")
    revision = DependentAtomSpaceStore(
        domain_projector=projector).build(snapshot)
    return snapshot, revision


def _records(revision):
    scope = next(
        value for value in revision.scopes
        if value.scope_kind == "population-recovery")
    return tuple(
        value for value in revision.records
        if value.key.scope_id == scope.scope_id)


def test_population_recovery_requires_exact_ruleset_and_current_action():
    snapshot, revision = _revision(_payload(), 700)
    records = _records(revision)

    assert {value.key.predicate for value in records} == {
        "founder-population-recovery-capable",
        "founder-population-recovery-colocated",
        "population-recovery-current-legal-action",
        "population-recovery-expected-city-gain",
        "population-recovery-founder",
        "population-recovery-target-city",
    }
    assert population_recovery_profile(
        _ruleset(), "settlers")["population_gain"] == 2
    dependencies = {
        value.key.kind + ":" + value.key.owner_id + ":" + value.key.path
        for record in records for support in record.supports
        for value in support.dependencies
    }
    assert any("cities.3.size" in value for value in dependencies)
    assert any("legal_actions." in value for value in dependencies)
    assert any(value.startswith("ruleset-digest:ruleset-proof")
               for value in dependencies)
    assert all(record.validity.ruleset_digest == "ruleset-proof"
               for record in records)
    assert snapshot.city(3).size == 3


def test_missing_capability_cost_legality_or_colocation_stays_unknown():
    cases = (
        (_payload(), _ruleset(flags=("Cities",))),
        (_payload(), _ruleset(pop_cost=0)),
        (_payload(join=False), _ruleset()),
        (_payload(colocated=False), _ruleset()),
    )
    for index, (payload, ruleset) in enumerate(cases):
        _snapshot_value, revision = _revision(
            payload, 710 + index, ruleset)
        assert not any(
            value.scope_kind == "population-recovery"
            for value in revision.scopes)
        assert not any(
            value.key.predicate.startswith((
                "population-recovery-",
                "founder-population-recovery-"))
            for value in revision.records)


def test_population_recovery_retracts_incrementally_with_legal_action():
    ruleset = _ruleset()
    projector = PopulationRecoveryProjector(ruleset, "ruleset-proof")
    store = DependentAtomSpaceStore(domain_projector=projector)
    first = _snapshot(_payload(), 720)
    second = _snapshot(_payload(join=False), 721)
    prior = store.build(first)

    verification = store.verify_incremental(second, first, prior)
    current = store.update(second)

    assert verification.equivalent, verification.to_dict()
    assert not any(
        value.scope_kind == "population-recovery"
        for value in current.scopes)


def test_population_recovery_catalog_matches_component_registry():
    with open(os.path.join(REPO, "profile", "fdas_catalog.json"),
              encoding="utf-8") as stream:
        catalog = json.load(stream)
    names = {
        value["name"] for value in catalog["predicates"]
        if value["status"] == "component-only"
        and value["name"].startswith((
            "population-recovery-", "founder-population-recovery-"))}
    expected = {
        value for value in population_recovery_predicate_registry().predicates
        if value.startswith((
            "population-recovery-", "founder-population-recovery-"))}

    assert names == expected
