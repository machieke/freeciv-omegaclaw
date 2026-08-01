import copy
import json
import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (  # noqa: E402
    FdasCityDefenseOperationAdapter,
    OperationState,
    OperationStore,
)
from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    AtomNamespace,
    DependentAtomSpaceStore,
    OperationProjector,
)


FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")


def _payload():
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    target = copy.deepcopy(payload["cities"]["3"])
    target.update({"id": 4, "name": "Antium", "tile": 84, "x": 4, "y": 2})
    payload["cities"]["4"] = target
    return payload


def _snapshot(payload, seq):
    return ProxyStateDTO.parse(
        "fdas-defense-lifecycle", seq, payload).to_snapshot()


def _move_action(snapshot):
    return next(
        json.loads(value) for value in snapshot.legal_action_json
        if json.loads(value).get("action_type") == "unit_move")


def _operation(action, operation_id="domain-route-step-1", deadline=14):
    return {
        "actor_id": 7,
        "arrival_turn": 14,
        "city_id": 4,
        "deadline_turn": deadline,
        "next_action": action,
        "operation_id": operation_id,
        "operation_type": "move_defender_to_city",
        "provenance": [
            "native-server-route-eta",
            "server-advertised-legal-action",
        ],
        "requirement_id": "defense:city:4:deadline:14",
        "support_reason": None,
    }


def test_multi_turn_route_reuses_lifecycle_and_refreshes_exact_binding():
    first_payload = _payload()
    first = _snapshot(first_payload, 480)
    operation_store = OperationStore("fdas-defense:proof")
    adapter = FdasCityDefenseOperationAdapter(
        operation_store, "ruleset-proof")

    registered = adapter.reconcile(first, (_operation(_move_action(first)),))
    operation_id = registered[0].operation_id
    first_binding = adapter.binding(operation_id)

    assert registered[0].state == "reservable"
    assert first_binding.legal_bound
    assert first_binding.action["target"] == {
        "direction": "e", "x": 3, "y": 2}

    second_payload = _payload()
    second_payload["turn"] = 13
    second_payload["units"]["7"].update({"tile": 83, "x": 3, "y": 2})
    second_payload["legal_actions"] = [{
        "action_type": "unit_move",
        "actor_id": 7,
        "is_valid": True,
        "target": {"direction": "e", "x": 4, "y": 2},
    }]
    second = _snapshot(second_payload, 481)
    refreshed = adapter.reconcile(second, (
        _operation(_move_action(second), "domain-route-step-2"),))
    second_binding = adapter.binding(operation_id)

    assert len(operation_store.records()) == 1
    assert refreshed[0].operation_id == operation_id
    assert refreshed[0].disposition == "reconciled"
    assert second_binding.snapshot_id == second.snapshot_id
    assert second_binding.domain_operation_id == "domain-route-step-2"
    assert second_binding.action["target"] == {
        "direction": "e", "x": 4, "y": 2}
    assert second_binding.binding_hash != first_binding.binding_hash
    current_revision = DependentAtomSpaceStore(
        domain_projector=OperationProjector(
            operation_store, adapter.bindings)).build(second)
    current_predicates = {
        value.key.predicate for value in current_revision.records}
    assert {
        "operation-action-binding",
        "operation-current-action",
        "operation-current-action-legal",
    }.issubset(current_predicates)
    legal_relation = next(
        value for value in current_revision.records
        if value.key.predicate == "operation-current-action-legal")
    assert any(
        value.key.path.startswith("legal_actions.")
        for value in legal_relation.supports[0].dependencies)

    third_payload = _payload()
    third_payload["turn"] = 14
    third_payload["units"]["7"].update({"tile": 84, "x": 4, "y": 2})
    third_payload["legal_actions"] = []
    third = _snapshot(third_payload, 482)
    stale_revision = DependentAtomSpaceStore(
        domain_projector=OperationProjector(
            operation_store, adapter.bindings)).build(third)
    assert "operation-current-action" not in {
        value.key.predicate for value in stale_revision.records}
    # A lagging analysis row cannot reopen a route after the authoritative
    # destination observation has already completed its persistent intent.
    completed = adapter.reconcile(third, (
        _operation(second_binding.action, "domain-route-step-3"),))
    record = operation_store.get(operation_id)

    assert len(completed) == 1
    assert len(operation_store.records()) == 1
    assert completed[0].disposition == "completed"
    assert record.progress.state == OperationState.COMPLETED
    assert record.progress.terminal_reason == "authoritative-completion-observed"
    assert adapter.binding(operation_id) is None

    revision = DependentAtomSpaceStore(
        domain_projector=OperationProjector(operation_store)).build(third)
    state = next(
        value for value in revision.records
        if value.key.predicate == "operation-state")
    assert state.key.namespace == AtomNamespace.OPERATION
    assert state.key.arguments[1].symbol == "completed"


def test_non_legal_binding_blocks_then_recovers_on_current_exact_action():
    first = _snapshot(_payload(), 483)
    operation_store = OperationStore("fdas-defense:legal-proof")
    adapter = FdasCityDefenseOperationAdapter(
        operation_store, "ruleset-proof")
    unavailable = _move_action(first)
    unavailable["target"] = {"direction": "e", "x": 9, "y": 9}

    blocked = adapter.reconcile(first, (_operation(unavailable),))
    operation_id = blocked[0].operation_id

    assert blocked[0].state == "blocked"
    assert blocked[0].reason == (
        "current-byte-identical-legal-action-unavailable")
    assert adapter.binding(operation_id) is None

    repaired_payload = _payload()
    repaired_payload["authoritative"]["source_seq"] = 484
    repaired = _snapshot(repaired_payload, 484)
    updates = adapter.reconcile(
        repaired, (_operation(_move_action(repaired), "domain-route-step-2"),))

    assert updates[0].previous_state == "blocked"
    assert updates[0].state == "reservable"
    assert adapter.binding(operation_id).legal_bound


def test_enemy_disappearance_never_completes_interception():
    snapshot = _snapshot(_payload(), 485)
    store = OperationStore("fdas-defense:fog-proof")
    adapter = FdasCityDefenseOperationAdapter(store, "ruleset-proof")
    interception = {
        "actor_id": 7,
        "arrival_turn": 13,
        "city_id": 4,
        "deadline_turn": 14,
        "next_action": None,
        "operation_id": "domain-interception",
        "operation_type": "intercept_immediate_threat",
        "provenance": ["visible-enemy-observation"],
        "requirement_id": "defense:city:4:threat:90",
        "support_reason": None,
    }
    first = adapter.reconcile(snapshot, (interception,))
    operation_id = first[0].operation_id

    later_payload = _payload()
    later_payload["turn"] = 13
    later = _snapshot(later_payload, 486)
    update = adapter.reconcile(later, ())[0]

    assert update.disposition == "blocked"
    assert store.get(operation_id).progress.state == OperationState.BLOCKED
    assert store.get(operation_id).progress.terminal_reason is None


def test_quarantined_store_cannot_reconcile():
    snapshot = _snapshot(_payload(), 487)
    adapter = FdasCityDefenseOperationAdapter(
        OperationStore("fdas-defense:quarantined",
                       quarantine_reason="integrity-check-failed"),
        "ruleset-proof")

    with pytest.raises(ValueError, match="quarantined"):
        adapter.reconcile(snapshot, ())
