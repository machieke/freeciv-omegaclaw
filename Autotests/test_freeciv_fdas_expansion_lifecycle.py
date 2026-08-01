import copy
import json
import os
import sys
from types import SimpleNamespace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (  # noqa: E402
    FOUND_CITY_OPERATION,
    RECOVER_POPULATION_OPERATION,
    FdasExpansionOperationAdapter,
    OperationState,
    OperationStore,
)
from freeciv_agent.pressure import GameResourceKind  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    CompositeDomainProjector,
    DependentAtomSpaceStore,
    OperationProjector,
    PopulationRecoveryProjector,
    SettlementSiteProjector,
)


FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")


def _rule():
    return SimpleNamespace(
        target_kind="unit",
        display_name="Settlers",
        rule_name="Settlers",
        quantitative={"pop_cost": {"value": 2}},
        traits={"flags": {"values": ["Cities", "AddToCity"]}},
    )


def _ruleset():
    return SimpleNamespace(rules=(_rule(),))


def _payload():
    with open(FIXTURE, encoding="utf-8") as stream:
        value = copy.deepcopy(json.load(stream))
    value["units"]["7"]["type"] = "Settlers"
    value["units"]["7"]["type_id"] = 0
    return value


def _found_payload(threat=False):
    value = _payload()
    value["units"]["7"].update({"tile": 83, "x": 3, "y": 2})
    if 83 not in value["visible_tiles"]:
        value["visible_tiles"].append(83)
    value["legal_actions"] = [{
        "action_type": "unit_build_city",
        "actor_id": 7,
        "is_valid": True,
    }]
    if threat:
        value["units"]["90"] = {
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
    return value


def _recovery_payload():
    value = _payload()
    value["legal_actions"] = [{
        "action_type": "unit_join_city",
        "actor_id": 7,
        "is_valid": True,
        "target": {"city_id": 3},
    }]
    return value


def _snapshot(payload, seq):
    return ProxyStateDTO.parse(
        "fdas-expansion-lifecycle", seq, payload).to_snapshot()


def _domain_revision(snapshot, ruleset):
    projector = CompositeDomainProjector((
        SettlementSiteProjector(ruleset, "ruleset-proof"),
        PopulationRecoveryProjector(ruleset, "ruleset-proof"),
    ))
    return DependentAtomSpaceStore(domain_projector=projector).build(snapshot)


def _adapter(ruleset):
    store = OperationStore("fdas-expansion:proof")
    return store, FdasExpansionOperationAdapter(
        store, ruleset, "ruleset-proof")


def test_found_city_projects_requirements_claims_and_waits_for_effect():
    ruleset = _ruleset()
    first = _snapshot(_found_payload(), 800)
    store, adapter = _adapter(ruleset)

    updates = adapter.reconcile(first, _domain_revision(first, ruleset))
    record = store.get(updates[0].operation_id)
    binding = adapter.binding(record.spec.operation_id)
    context = adapter.requirement_context(record.spec.operation_id)

    assert record.spec.operation_type == FOUND_CITY_OPERATION
    assert record.progress.state == OperationState.RESERVABLE
    assert binding.action == {"action_type": "unit_build_city", "actor_id": 7}
    assert binding.legal_bound
    assert {value.resource.kind for value in context.resource_claims} == {
        GameResourceKind.ACTION_BUDGET,
        GameResourceKind.ACTOR,
        GameResourceKind.TILE_OCCUPANCY,
    }
    assert set(context.requirement_set.role_ids) == {
        "capability", "legal-binding", "resource-capacity",
        "site-safety", "threat-policy",
    }
    projected = DependentAtomSpaceStore(
        domain_projector=OperationProjector(
            store, adapter.bindings, adapter.requirement_contexts)).build(first)
    predicates = {value.key.predicate for value in projected.records}
    assert {
        "operation-current-action-legal",
        "operation-requirement-set",
        "operation-resource-claim",
        "resource-claim-resource",
    }.issubset(predicates)

    committed = adapter.commit_matching_action(
        first, binding.action, accepted=True)

    assert committed[0].disposition == "committed-awaiting-effect"
    assert store.get(record.spec.operation_id).progress.state == (
        OperationState.ACTIVE)
    assert adapter.binding(record.spec.operation_id) is None
    active_context = adapter.requirement_context(record.spec.operation_id)
    assert active_context.resource_claims == ()
    assert set(dict(active_context.blocked_premises).values()) == {
        "awaiting-authoritative-expansion-effect"}

    # Acceptance in the same snapshot is not an authoritative game effect.
    repeated = adapter.reconcile(first, _domain_revision(first, ruleset))
    assert repeated[0].disposition == "awaiting-effect"
    assert store.get(record.spec.operation_id).progress.state == (
        OperationState.ACTIVE)


def test_found_city_completes_only_after_founder_consumption_and_new_city():
    ruleset = _ruleset()
    first = _snapshot(_found_payload(), 810)
    store, adapter = _adapter(ruleset)
    operation_id = adapter.reconcile(
        first, _domain_revision(first, ruleset))[0].operation_id
    adapter.commit_matching_action(
        first, adapter.binding(operation_id).action, accepted=True)

    after_payload = _found_payload()
    after_payload["turn"] = 13
    del after_payload["units"]["7"]
    after_payload["legal_actions"] = []
    city = copy.deepcopy(after_payload["cities"]["3"])
    city.update({"id": 4, "name": "Antium", "tile": 83, "x": 3, "y": 2})
    after_payload["cities"]["4"] = city
    after = _snapshot(after_payload, 811)

    updates = adapter.reconcile(after, _domain_revision(after, ruleset))

    assert updates[0].disposition == "completed"
    assert store.get(operation_id).progress.state == OperationState.COMPLETED
    assert store.get(operation_id).progress.terminal_reason == (
        "authoritative-expansion-effect-observed")


def test_visible_threat_does_not_create_a_found_city_operation():
    ruleset = _ruleset()
    snapshot = _snapshot(_found_payload(threat=True), 820)
    store, adapter = _adapter(ruleset)

    assert adapter.reconcile(
        snapshot, _domain_revision(snapshot, ruleset)) == ()
    assert store.records() == ()


def test_population_recovery_requires_consumption_and_exact_city_gain():
    ruleset = _ruleset()
    first = _snapshot(_recovery_payload(), 830)
    store, adapter = _adapter(ruleset)
    update = adapter.reconcile(first, _domain_revision(first, ruleset))[0]
    operation_id = update.operation_id
    record = store.get(operation_id)

    assert record.spec.operation_type == RECOVER_POPULATION_OPERATION
    assert record.spec.steps[0].completion_predicate_id.endswith(":5")
    context = adapter.requirement_context(operation_id)
    assert {value.resource.kind for value in context.resource_claims} == {
        GameResourceKind.ACTION_BUDGET, GameResourceKind.ACTOR}
    adapter.commit_matching_action(
        first, adapter.binding(operation_id).action, accepted=True)

    after_payload = _recovery_payload()
    after_payload["turn"] = 13
    del after_payload["units"]["7"]
    after_payload["cities"]["3"]["size"] = 5
    after_payload["legal_actions"] = []
    after = _snapshot(after_payload, 831)
    # The effect contract is persisted in OperationSpec; lifecycle recovery
    # does not depend on the original adapter's transient candidate cache.
    restarted = FdasExpansionOperationAdapter(
        store, ruleset, "ruleset-proof")
    updates = restarted.reconcile(after, _domain_revision(after, ruleset))

    assert updates[0].disposition == "completed"
    assert store.get(operation_id).progress.state == OperationState.COMPLETED


def test_consumed_founder_without_full_population_effect_fails():
    ruleset = _ruleset()
    first = _snapshot(_recovery_payload(), 840)
    store, adapter = _adapter(ruleset)
    operation_id = adapter.reconcile(
        first, _domain_revision(first, ruleset))[0].operation_id
    adapter.commit_matching_action(
        first, adapter.binding(operation_id).action, accepted=True)

    after_payload = _recovery_payload()
    after_payload["turn"] = 13
    del after_payload["units"]["7"]
    after_payload["cities"]["3"]["size"] = 4
    after_payload["legal_actions"] = []
    after = _snapshot(after_payload, 841)
    updates = adapter.reconcile(after, _domain_revision(after, ruleset))

    assert updates[0].disposition == "failed"
    assert store.get(operation_id).progress.state == OperationState.FAILED
    assert store.get(operation_id).progress.terminal_reason == (
        "founder-consumed-without-required-expansion-effect")


def test_expansion_rejects_stale_atomspace_revision():
    ruleset = _ruleset()
    snapshot = _snapshot(_found_payload(), 850)
    stale_payload = _found_payload()
    stale_payload["turn"] = 13
    stale = _snapshot(stale_payload, 851)
    _store, adapter = _adapter(ruleset)

    with pytest.raises(ValueError, match="not current"):
        adapter.reconcile(snapshot, _domain_revision(stale, ruleset))
