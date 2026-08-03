import copy
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    FdasCoordinatedReplacementAdapter,
    OPERATION_SCHEMA_VERSION,
    OperationParticipant,
    OperationSpec,
    OperationState,
    OperationStep,
    OperationStore,
    ShadowOperationCandidate,
)
from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    DependentAtomSpaceStore,
    OperationProjector,
)


FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")


def _payload(turn, replacement_tile=81, replacement_x=1,
             reinforcement_tile=82, reinforcement_x=2):
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    target = copy.deepcopy(payload["cities"]["3"])
    target.update({"id": 4, "name": "Antium", "tile": 84, "x": 4, "y": 2})
    payload["cities"]["4"] = target
    payload["turn"] = turn
    payload["units"]["7"].update({
        "tile": reinforcement_tile, "transported": False,
        "x": reinforcement_x, "y": 2})
    replacement = copy.deepcopy(payload["units"]["7"])
    replacement.update({
        "id": 8, "tile": replacement_tile, "x": replacement_x, "y": 2})
    payload["units"]["8"] = replacement
    payload["legal_actions"] = []
    payload["authoritative"]["movement_routes"] = []
    return payload


def _route(unit_id, origin, destination, first_step, turn, source_seq):
    return {
        "authority": "freeciv-server-pathfinder",
        "destination_tile": destination,
        "estimated_turns": 1,
        "first_step_movement_cost": 1,
        "first_step_tile": first_step,
        "initially_transported": False,
        "movement_points_remaining": 2,
        "moves_left_at_request": 3,
        "origin_tile": origin,
        "path_directions": [0],
        "path_length": 1,
        "reachable": True,
        "schema_version": "1.0",
        "source_seq": source_seq,
        "total_movement_cost": 1,
        "transported_at_request": False,
        "turn": turn,
        "unit_id": unit_id,
    }


def _move(actor_id, x):
    return {
        "action_type": "unit_move",
        "actor_id": actor_id,
        "is_valid": True,
        "target": {"direction": "e", "x": x, "y": 2},
    }


def _snapshot(payload, seq):
    return ProxyStateDTO.parse(
        "fdas-replacement-lifecycle", seq, payload).to_snapshot()


def _candidate(snapshot, operation_id="fdas-coordinated-replacement-proof"):
    participants = (
        OperationParticipant("replacement", "8", "unit", True),
        OperationParticipant("reinforcement", "7", "unit", True),
    )
    steps = (
        OperationStep(
            "step-replacement", "unit_move", "replacement", "city:3",
            "requirements-replacement", "replacement-at-source", 3),
        OperationStep(
            "step-reinforcement", "unit_move", "reinforcement", "city:4",
            "requirements-reinforcement", "reinforcement-at-target", 3),
    )
    spec = OperationSpec(
        OPERATION_SCHEMA_VERSION, operation_id,
        "fdas-defense:coordinated-replacement",
        ("pf-impact:survival",), participants, "city:4", steps,
        12, 15, 0.0,
        ("fdas-coordinated-replacement-shadow/1.0",), "ruleset-proof")
    action_key = next(
        value for value in snapshot.legal_action_json
        if json.loads(value).get("actor_id") == 8)
    action = json.loads(action_key)
    semantic = {
        "action_key": action_key,
        "operation": spec.to_dict(),
    }
    return ShadowOperationCandidate(
        spec, action, action_key,
        ("unit-action:8:current", "unit-action:7:conditional-future"),
        True, False, ("uncompiled-action-effect",),
        ("fdas-coordinated-replacement-shadow/1.0",),
        structural_hash(semantic))


def test_replacement_deduplicates_snapshot_specific_operation_ids():
    payload = _payload(12)
    payload["legal_actions"] = [_move(8, 2)]
    payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 12, 500)]
    snapshot = _snapshot(payload, 500)
    store = OperationStore("fdas-replacement:logical-deduplication")
    adapter = FdasCoordinatedReplacementAdapter(store, "ruleset-proof")

    adapter.reconcile(snapshot, (_candidate(snapshot, "replacement-a"),))
    first_digest = store.store_digest
    updates = adapter.reconcile(
        snapshot, (_candidate(snapshot, "replacement-b"),))

    assert len(store.records()) == 1
    assert store.records()[0].spec.operation_id == "replacement-a"
    assert store.store_digest == first_digest
    assert updates[-1].operation_id == "replacement-a"
    assert adapter.lifecycle_key(store.records()[0].spec) == (
        8, 7, "city:3", "city:4")


def test_two_step_replacement_persists_refreshes_and_completes_exactly():
    first_payload = _payload(12)
    first_payload["legal_actions"] = [_move(8, 2)]
    first_payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 12, 501)]
    first = _snapshot(first_payload, 501)
    store = OperationStore("fdas-replacement:proof")
    adapter = FdasCoordinatedReplacementAdapter(store, "ruleset-proof")

    registered = adapter.reconcile(first, (_candidate(first),))
    operation_id = registered[-1].operation_id
    first_record = store.get(operation_id)

    assert registered[-1].state == "reservable"
    assert first_record.progress.current_step_index == 0
    assert adapter.binding(operation_id).action["actor_id"] == 8
    assert {
        value.resource.kind.value
        for value in adapter.requirement_context(
            operation_id).resource_claims
    } == {"actor", "move_points"}

    second_payload = _payload(
        13, replacement_tile=82, replacement_x=2,
        reinforcement_tile=82, reinforcement_x=2)
    second_payload["legal_actions"] = [_move(7, 3)]
    second_payload["authoritative"]["movement_routes"] = [
        _route(7, 82, 84, 83, 13, 502)]
    second = _snapshot(second_payload, 502)
    refreshed = adapter.reconcile(second)
    second_record = store.get(operation_id)

    assert len(store.records()) == 1
    assert [value.disposition for value in refreshed] == [
        "step-advanced", "reconciled"]
    assert second_record.progress.current_step_index == 1
    assert adapter.binding(operation_id).action["actor_id"] == 7
    revision = DependentAtomSpaceStore(
        domain_projector=OperationProjector(
            store, adapter.bindings,
            adapter.requirement_contexts)).build(second)
    current_step = next(
        value for value in revision.records
        if value.key.predicate == "operation-current-step")
    assert current_step.key.arguments[1].entity_id == "step-reinforcement"
    assert {
        "operation-current-action", "operation-requirement-set",
        "operation-resource-claim",
    }.issubset({value.key.predicate for value in revision.records})

    third_payload = _payload(
        14, replacement_tile=82, replacement_x=2,
        reinforcement_tile=84, reinforcement_x=4)
    third = _snapshot(third_payload, 503)
    completed = adapter.reconcile(third)
    final_record = store.get(operation_id)

    assert completed[-1].disposition == "completed"
    assert final_record.progress.state == OperationState.COMPLETED
    assert final_record.progress.current_step_index == 1
    assert adapter.binding(operation_id) is None
    assert adapter.requirement_context(operation_id) is None


def test_replacement_blocks_when_protected_source_is_not_covered():
    first_payload = _payload(
        12, replacement_tile=81, replacement_x=1,
        reinforcement_tile=83, reinforcement_x=3)
    first_payload["legal_actions"] = [_move(8, 2)]
    first_payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 12, 504)]
    snapshot = _snapshot(first_payload, 504)
    store = OperationStore("fdas-replacement:source-guard")
    adapter = FdasCoordinatedReplacementAdapter(store, "ruleset-proof")

    update = adapter.reconcile(snapshot, (_candidate(snapshot),))[-1]
    context = adapter.requirement_context(update.operation_id)

    assert update.state == "blocked"
    assert update.reason == "protected-source-garrison-not-covered"
    assert adapter.binding(update.operation_id) is None
    assert dict(context.blocked_premises) == {
        "availability:source-garrison-covered":
            "protected-source-garrison-not-covered",
    }
    assert context.resource_claims == ()


def test_target_occupancy_never_completes_if_replacement_left_source():
    first_payload = _payload(12)
    first_payload["legal_actions"] = [_move(8, 2)]
    first_payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 12, 505)]
    first = _snapshot(first_payload, 505)
    store = OperationStore("fdas-replacement:completion-source-guard")
    adapter = FdasCoordinatedReplacementAdapter(store, "ruleset-proof")
    operation_id = adapter.reconcile(first, (_candidate(first),))[-1].operation_id

    second_payload = _payload(
        13, replacement_tile=82, replacement_x=2,
        reinforcement_tile=82, reinforcement_x=2)
    second_payload["legal_actions"] = [_move(7, 3)]
    second_payload["authoritative"]["movement_routes"] = [
        _route(7, 82, 84, 83, 13, 506)]
    adapter.reconcile(_snapshot(second_payload, 506))

    unsafe_payload = _payload(
        14, replacement_tile=81, replacement_x=1,
        reinforcement_tile=84, reinforcement_x=4)
    update = adapter.reconcile(_snapshot(unsafe_payload, 507))[-1]

    assert update.state == "blocked"
    assert update.reason == "protected-source-garrison-not-covered"
    assert store.get(operation_id).progress.state == OperationState.BLOCKED
    assert store.get(operation_id).progress.terminal_reason is None
