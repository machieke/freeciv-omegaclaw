import copy
import json
import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    FdasCoordinatedReplacementAdapter,
    FdasCoordinatedReplacementExecutionPilot,
    FdasCoordinatedReplacementReadoutEvaluator,
    FdasReplacementChainOutcomeLabel,
    FdasReplacementChainOutcomeLabeler,
    FdasReplacementChainOutcomeStore,
    FdasReplacementExecutionAssignment,
    FdasReplacementExecutionStore,
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


def _candidate(snapshot, operation_id="fdas-coordinated-replacement-proof",
               target_city_id=4):
    participants = (
        OperationParticipant("replacement", "8", "unit", True),
        OperationParticipant("reinforcement", "7", "unit", True),
    )
    steps = (
        OperationStep(
            "step-replacement", "unit_move", "replacement", "city:3",
            "requirements-replacement", "replacement-at-source", 3),
        OperationStep(
            "step-reinforcement", "unit_move", "reinforcement",
            "city:{}".format(target_city_id),
            "requirements-reinforcement", "reinforcement-at-target", 3),
    )
    spec = OperationSpec(
        OPERATION_SCHEMA_VERSION, operation_id,
        "fdas-defense:coordinated-replacement",
        ("pf-impact:survival",), participants,
        "city:{}".format(target_city_id), steps,
        snapshot.turn, snapshot.turn + 3, 0.0,
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


def _direct_candidate(snapshot, operation_id="fdas-direct-move-proof"):
    participants = (
        OperationParticipant("reinforcement", "7", "unit", True),)
    steps = (
        OperationStep(
            "step-direct", "unit_move", "reinforcement", "city:4",
            "requirements-direct", "reinforcement-at-target", 3),)
    spec = OperationSpec(
        OPERATION_SCHEMA_VERSION, operation_id,
        "fdas-shadow:city-garrison-deficit:unit_move",
        ("pf-impact:survival",), participants, "city:4", steps,
        snapshot.turn, snapshot.turn + 3, 0.0,
        ("fdas-shadow-candidate-factory/1.0",), "ruleset-proof")
    action_key = next(
        value for value in snapshot.legal_action_json
        if json.loads(value).get("actor_id") == 7)
    action = json.loads(action_key)
    semantic = {"action_key": action_key, "operation": spec.to_dict()}
    return ShadowOperationCandidate(
        spec, action, action_key, ("unit-action:7:current",),
        True, False,
        ("protected-source-garrison", "uncompiled-action-effect"),
        ("fdas-shadow-candidate-factory/1.0",),
        structural_hash(semantic))


def _completed_replacement_record(operation_id="replacement-outcome-proof"):
    first_payload = _payload(12)
    first_payload["legal_actions"] = [_move(8, 2)]
    first_payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 12, 520)]
    first = _snapshot(first_payload, 520)
    operation_store = OperationStore(
        "fdas-replacement:outcome-operation-proof")
    adapter = FdasCoordinatedReplacementAdapter(
        operation_store, "ruleset-proof")
    adapter.reconcile(first, (_candidate(first, operation_id),))

    second_payload = _payload(
        13, replacement_tile=82, replacement_x=2,
        reinforcement_tile=82, reinforcement_x=2)
    second_payload["legal_actions"] = [_move(7, 3)]
    second_payload["authoritative"]["movement_routes"] = [
        _route(7, 82, 84, 83, 13, 521)]
    adapter.reconcile(_snapshot(second_payload, 521))

    completed_payload = _payload(
        14, replacement_tile=82, replacement_x=2,
        reinforcement_tile=84, reinforcement_x=4)
    completed = _snapshot(completed_payload, 522)
    adapter.reconcile(completed)
    return operation_store.get(operation_id), completed


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


def test_replacement_terminal_reproposal_cooldown_survives_restart(tmp_path):
    first_payload = _payload(12)
    first_payload["legal_actions"] = [_move(8, 2)]
    first_payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 12, 510)]
    first = _snapshot(first_payload, 510)
    identity = "fdas-replacement:terminal-cooldown-proof"
    store = OperationStore(identity)
    adapter = FdasCoordinatedReplacementAdapter(store, "ruleset-proof")
    adapter.reconcile(first, (_candidate(first, "replacement-first"),))

    expired_payload = _payload(16)
    expired = _snapshot(expired_payload, 511)
    update = adapter.reconcile(expired)[-1]
    assert update.disposition == "expired"
    assert store.get("replacement-first").progress.last_updated_turn == 16

    within_payload = _payload(17)
    within_payload["legal_actions"] = [_move(8, 2)]
    within_payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 17, 512)]
    within = _snapshot(within_payload, 512)
    adapter.reconcile(within, (_candidate(within, "replacement-within"),))

    assert len(store.records()) == 1
    assert adapter.reproposal_suppressions() == ((
        "replacement-within", "replacement-first", 48),)

    path = tmp_path / "replacement-operations.json"
    store.save(str(path))
    restarted = OperationStore.load(str(path), identity)
    restarted_adapter = FdasCoordinatedReplacementAdapter(
        restarted, "ruleset-proof")
    restarted_adapter.reconcile(
        within, (_candidate(within, "replacement-after-restart"),))

    assert len(restarted.records()) == 1
    assert restarted_adapter.reproposal_suppressions() == ((
        "replacement-after-restart", "replacement-first", 48),)


def test_replacement_terminal_reproposal_releases_at_exact_boundary():
    first_payload = _payload(12)
    first_payload["legal_actions"] = [_move(8, 2)]
    first_payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 12, 513)]
    first = _snapshot(first_payload, 513)
    store = OperationStore("fdas-replacement:cooldown-boundary-proof")
    adapter = FdasCoordinatedReplacementAdapter(store, "ruleset-proof")
    adapter.reconcile(first, (_candidate(first, "replacement-first"),))
    adapter.reconcile(_snapshot(_payload(16), 514))

    boundary_payload = _payload(48)
    boundary_payload["legal_actions"] = [_move(8, 2)]
    boundary_payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 48, 515)]
    boundary = _snapshot(boundary_payload, 515)
    adapter.reconcile(
        boundary, (_candidate(boundary, "replacement-boundary"),))

    assert len(store.records()) == 2
    assert store.get("replacement-boundary") is not None
    assert adapter.reproposal_suppressions() == ()


def test_replacement_terminal_cooldown_does_not_suppress_independent_key():
    first_payload = _payload(12)
    first_payload["legal_actions"] = [_move(8, 2)]
    first_payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 12, 516)]
    first = _snapshot(first_payload, 516)
    store = OperationStore("fdas-replacement:cooldown-key-proof")
    adapter = FdasCoordinatedReplacementAdapter(store, "ruleset-proof")
    adapter.reconcile(first, (_candidate(first, "replacement-first"),))
    adapter.reconcile(_snapshot(_payload(16), 517))

    independent_payload = _payload(17)
    independent_payload["legal_actions"] = [_move(8, 2)]
    independent_payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 17, 518)]
    independent = _snapshot(independent_payload, 518)
    adapter.reconcile(independent, (
        _candidate(
            independent, "replacement-independent", target_city_id=3),))

    assert len(store.records()) == 2
    assert store.get("replacement-independent") is not None
    assert adapter.reproposal_suppressions() == ()


def test_replacement_chain_outcome_opens_only_after_exact_completion():
    payload = _payload(12)
    payload["legal_actions"] = [_move(8, 2)]
    payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 12, 523)]
    snapshot = _snapshot(payload, 523)
    operation_store = OperationStore(
        "fdas-replacement:pending-outcome-proof")
    adapter = FdasCoordinatedReplacementAdapter(
        operation_store, "ruleset-proof")
    adapter.reconcile(snapshot, (_candidate(snapshot),))
    label_store = FdasReplacementChainOutcomeStore(
        "fdas-replacement:outcome-proof")
    labeler = FdasReplacementChainOutcomeLabeler(label_store)

    with pytest.raises(ValueError, match="completed operation"):
        labeler.open(
            operation_store.records()[0], snapshot.identity.game_id,
            snapshot.player_id)

    completed, completion_snapshot = _completed_replacement_record()
    label = labeler.open(
        completed, completion_snapshot.identity.game_id,
        completion_snapshot.player_id)

    assert label.status == "pending"
    assert label.completion_turn == 14
    assert label.due_turn == 46
    assert label.completion_snapshot_id == completion_snapshot.snapshot_id
    assert label.replacement_actor_id == 8
    assert label.reinforcement_actor_id == 7
    assert label.source_city_id == 3
    assert label.target_city_id == 4
    assert labeler.open(
        completed, completion_snapshot.identity.game_id,
        completion_snapshot.player_id) == label


def test_replacement_chain_outcome_survives_restart_and_observes_due_turn(
        tmp_path):
    completed, completion_snapshot = _completed_replacement_record()
    identity = "fdas-replacement:durable-outcome-proof"
    store = FdasReplacementChainOutcomeStore(identity)
    labeler = FdasReplacementChainOutcomeLabeler(store)
    pending = labeler.open(
        completed, completion_snapshot.identity.game_id,
        completion_snapshot.player_id)
    path = tmp_path / "replacement-outcomes.json"
    store.save(str(path))

    restarted = FdasReplacementChainOutcomeStore.load(str(path), identity)
    restarted_labeler = FdasReplacementChainOutcomeLabeler(restarted)
    before_payload = _payload(
        45, replacement_tile=82, replacement_x=2,
        reinforcement_tile=84, reinforcement_x=4)
    before = _snapshot(before_payload, 524)
    assert restarted_labeler.observe(
        pending.label_id, before, "revision-before-due") == pending

    due_payload = _payload(
        46, replacement_tile=82, replacement_x=2,
        reinforcement_tile=84, reinforcement_x=4)
    due = _snapshot(due_payload, 525)
    observed = restarted_labeler.observe(
        pending.label_id, due, "revision-at-due")

    assert observed.status == "observed"
    assert observed.outcome is True
    assert observed.reason == (
        "completed-replacement-chain-durable-at-due-turn")
    assert dict(observed.observed_value)["replacement_at_source"] is True
    assert dict(observed.observed_value)["reinforcement_at_target"] is True

    later_payload = _payload(
        47, replacement_tile=81, replacement_x=1,
        reinforcement_tile=81, reinforcement_x=1)
    later = _snapshot(later_payload, 526)
    assert restarted_labeler.observe(
        pending.label_id, later, "revision-after-terminal") == observed


def test_replacement_chain_outcome_retains_failed_durability_conjuncts():
    completed, completion_snapshot = _completed_replacement_record()
    store = FdasReplacementChainOutcomeStore(
        "fdas-replacement:negative-outcome-proof")
    labeler = FdasReplacementChainOutcomeLabeler(store)
    pending = labeler.open(
        completed, completion_snapshot.identity.game_id,
        completion_snapshot.player_id)
    due_payload = _payload(
        46, replacement_tile=81, replacement_x=1,
        reinforcement_tile=84, reinforcement_x=4)
    due = _snapshot(due_payload, 527)
    observed = labeler.observe(
        pending.label_id, due, "revision-negative-due")

    assert observed.outcome is False
    assert "replacement-at-source" in observed.reason
    assert dict(observed.observed_value)["replacement_present"] is True
    assert dict(observed.observed_value)["replacement_at_source"] is False

    invalid = observed.to_dict()
    invalid["operation_spec_digest"] = "changed-spec"
    with pytest.raises(ValueError, match="identity mismatch"):
        FdasReplacementChainOutcomeLabel.from_dict(invalid)


def test_replacement_readout_recalls_grounded_chain_without_value_claim():
    payload = _payload(12)
    payload["legal_actions"] = [_move(8, 2), _move(7, 3)]
    payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 12, 508),
        _route(7, 82, 84, 83, 12, 508),
    ]
    snapshot = _snapshot(payload, 508)
    store = OperationStore("fdas-replacement:readout-proof")
    adapter = FdasCoordinatedReplacementAdapter(store, "ruleset-proof")
    replacement = _candidate(snapshot)
    direct = _direct_candidate(snapshot)
    adapter.reconcile(snapshot, (replacement,))
    revision = DependentAtomSpaceStore(
        domain_projector=OperationProjector(
            store, adapter.bindings,
            adapter.requirement_contexts)).build(snapshot)

    readout = FdasCoordinatedReplacementReadoutEvaluator(
        adapter).evaluate(snapshot, revision, (replacement, direct))

    assert readout.status == "eligible-shadow"
    assert readout.to_dict()["action_selection_changed"] is False
    assert readout.to_dict()["transition_value_estimated"] is False
    assert len(readout.pairs) == 1
    pair = readout.pairs[0]
    assert pair.replacement_actor_id == 8
    assert pair.reinforcement_actor_id == 7
    assert pair.source_city_id == 3
    assert pair.target_city_id == 4
    assert pair.combined_estimated_turns == 2
    assert pair.combined_movement_cost == 2
    assert pair.to_dict()["direct_unsafe_reason"] == (
        "protected-source-garrison")


def test_bounded_replacement_execution_persists_one_chain_and_completes(
        tmp_path):
    first_payload = _payload(12)
    first_payload["legal_actions"] = [_move(8, 2), _move(7, 3)]
    first_payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 12, 530),
        _route(7, 82, 84, 83, 12, 530),
    ]
    first = _snapshot(first_payload, 530)
    operation_store = OperationStore("fdas-replacement:execution-operation")
    adapter = FdasCoordinatedReplacementAdapter(
        operation_store, "ruleset-proof")
    replacement = _candidate(first, "replacement-execution-proof")
    direct = _direct_candidate(first)
    adapter.reconcile(first, (replacement,))
    revision = DependentAtomSpaceStore(
        domain_projector=OperationProjector(
            operation_store, adapter.bindings,
            adapter.requirement_contexts)).build(first)
    readout = FdasCoordinatedReplacementReadoutEvaluator(
        adapter).evaluate(first, revision, (replacement, direct))
    execution_identity = "fdas-replacement:execution-treatment"
    execution_store = FdasReplacementExecutionStore(execution_identity)
    pilot = FdasCoordinatedReplacementExecutionPilot(
        adapter, execution_store, "replacement-pilot-test",
        first.identity.game_id, first.player_id)

    first_decision = pilot.evaluate(first, readout)

    assert first_decision.status == "authorized"
    assert first_decision.assignment_created is True
    assert tuple(value.disposition for value in
                 first_decision.lifecycle_updates) == (
                     "execution-reserved", "execution-activated")
    assert first_decision.authority.action_key == replacement.action_key
    assert operation_store.get(
        replacement.operation.operation_id).progress.state == (
            OperationState.ACTIVE)

    assignment, attempt, update = pilot.record_outcome(
        first, replacement.action, True, "action-result-first")
    assert attempt.step_index == 0
    assert attempt.accepted is True
    assert update.disposition == "execution-attempt-accepted"
    assert len(assignment.attempts) == 1

    blocked_payload = _payload(
        13, replacement_tile=82, replacement_x=2,
        reinforcement_tile=82, reinforcement_x=2)
    blocked_payload["legal_actions"] = []
    blocked_payload["authoritative"]["movement_routes"] = []
    blocked = _snapshot(blocked_payload, 531)
    adapter.reconcile(blocked)
    blocked_revision = DependentAtomSpaceStore(
        domain_projector=OperationProjector(
            operation_store, adapter.bindings,
            adapter.requirement_contexts)).build(blocked)
    blocked_readout = FdasCoordinatedReplacementReadoutEvaluator(
        adapter).evaluate(blocked, blocked_revision, ())

    blocked_decision = pilot.evaluate(blocked, blocked_readout)

    assert blocked_decision.status == "abstained"
    assert blocked_decision.reason == "selected-operation-blocked"
    assert blocked_decision.authority is None
    assert operation_store.get(
        replacement.operation.operation_id).progress.state == (
            OperationState.BLOCKED)
    path = tmp_path / "replacement-execution.json"
    execution_store.save(str(path))

    restarted_store = FdasReplacementExecutionStore.load(
        str(path), execution_identity)
    assert restarted_store.quarantined is False
    assert restarted_store.assignment == assignment
    restarted_pilot = FdasCoordinatedReplacementExecutionPilot(
        adapter, restarted_store, "replacement-pilot-test",
        first.identity.game_id, first.player_id)

    second_payload = _payload(
        14, replacement_tile=82, replacement_x=2,
        reinforcement_tile=82, reinforcement_x=2)
    second_payload["legal_actions"] = [_move(7, 3)]
    second_payload["authoritative"]["movement_routes"] = [
        _route(7, 82, 84, 83, 14, 532)]
    second = _snapshot(second_payload, 532)
    adapter.reconcile(second)
    second_revision = DependentAtomSpaceStore(
        domain_projector=OperationProjector(
            operation_store, adapter.bindings,
            adapter.requirement_contexts)).build(second)
    empty_readout = FdasCoordinatedReplacementReadoutEvaluator(
        adapter).evaluate(second, second_revision, ())

    second_decision = restarted_pilot.evaluate(second, empty_readout)

    assert second_decision.status == "authorized"
    assert second_decision.assignment_created is False
    assert second_decision.authority.action["actor_id"] == 7
    assert tuple(value.disposition for value in
                 second_decision.lifecycle_updates) == (
                     "execution-reserved", "execution-activated")
    second_assignment, second_attempt, _update = (
        restarted_pilot.record_outcome(
            second, second_decision.authority.action, True,
            "action-result-second"))
    assert second_attempt.step_index == 1
    assert len(second_assignment.attempts) == 2

    completed_payload = _payload(
        15, replacement_tile=82, replacement_x=2,
        reinforcement_tile=84, reinforcement_x=4)
    completed = _snapshot(completed_payload, 533)
    adapter.reconcile(completed)
    completed_revision = DependentAtomSpaceStore(
        domain_projector=OperationProjector(
            operation_store, adapter.bindings,
            adapter.requirement_contexts)).build(completed)
    completed_readout = FdasCoordinatedReplacementReadoutEvaluator(
        adapter).evaluate(completed, completed_revision, ())

    terminal = restarted_pilot.evaluate(completed, completed_readout)

    assert terminal.status == "terminal"
    assert terminal.assignment.terminal_state == "completed"
    assert len(restarted_store.assignment.attempts) == 2
    other_material = dict(terminal.assignment.identity_material)
    other_material.update({
        "operation_id": "different-replacement-operation",
        "operation_spec_digest": "different-replacement-spec",
    })
    other = FdasReplacementExecutionAssignment(
        **{**terminal.assignment.__dict__,
           "assignment_id": "replacement-execution-assignment-" +
           structural_hash(other_material)[:24],
           "operation_id": "different-replacement-operation",
           "operation_spec_digest": "different-replacement-spec",
           "attempts": (), "terminal_state": None,
           "terminal_reason": None})
    with pytest.raises(ValueError, match="cannot reassign"):
        restarted_store.record(other)

    outcome_store = FdasReplacementChainOutcomeStore(
        "fdas-replacement:execution-outcome")
    label = FdasReplacementChainOutcomeLabeler(outcome_store).open(
        operation_store.get(replacement.operation.operation_id),
        completed.identity.game_id, completed.player_id)
    assert label.completion_turn == 15
    assert label.operation_id == terminal.assignment.operation_id


def test_bounded_replacement_execution_tamper_quarantines_restart(tmp_path):
    path = tmp_path / "replacement-execution.json"
    store = FdasReplacementExecutionStore("execution-store-original")
    store.save(str(path))

    restarted = FdasReplacementExecutionStore.load(
        str(path), "execution-store-different")

    assert restarted.quarantined is True
    assert "identity differs" in restarted.quarantine_reason


def test_replacement_readout_abstains_when_source_coverage_is_not_current():
    payload = _payload(
        12, replacement_tile=81, replacement_x=1,
        reinforcement_tile=83, reinforcement_x=3)
    payload["legal_actions"] = [_move(8, 2), _move(7, 4)]
    payload["authoritative"]["movement_routes"] = [
        _route(8, 81, 82, 82, 12, 509),
        _route(7, 83, 84, 84, 12, 509),
    ]
    snapshot = _snapshot(payload, 509)
    store = OperationStore("fdas-replacement:readout-blocked")
    adapter = FdasCoordinatedReplacementAdapter(store, "ruleset-proof")
    replacement = _candidate(snapshot)
    direct = _direct_candidate(snapshot)
    adapter.reconcile(snapshot, (replacement,))
    revision = DependentAtomSpaceStore(
        domain_projector=OperationProjector(
            store, adapter.bindings,
            adapter.requirement_contexts)).build(snapshot)

    readout = FdasCoordinatedReplacementReadoutEvaluator(
        adapter).evaluate(snapshot, revision, (replacement, direct))

    assert readout.status == "abstained"
    assert readout.pairs == ()
    assert readout.rejected == (
        replacement.operation.operation_id
        + ":current-step-not-reservable",)


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
