"""Explicit operation identity, lifecycle, persistence, and assembly."""

import json
import os
import tempfile

import pytest

from freeciv_agent.planning import (
    OPERATION_SCHEMA_VERSION,
    OperationParticipant,
    OperationSpec,
    OperationState,
    OperationStep,
    OperationStore,
    OperationStoreError,
    OperationTransitionError,
    assemble_city_defense_operation,
    operation_id_from_components,
)


def _spec(
        operation_id="operation-proof",
        steps=1):
    participant = OperationParticipant(
        role="defender",
        actor_id="unit:7",
        actor_class="unit",
        required=True)
    operation_steps = tuple(
        OperationStep(
            step_id="step-{}".format(
                index),
            action_type="unit_move",
            actor_role="defender",
            target_ref="city:3",
            requirement_set_id=(
                "defense:city:3"),
            completion_predicate_id=(
                "defender-at-city"),
            maximum_attempts=2)
        for index in range(steps))
    return OperationSpec(
        schema_version=(
            OPERATION_SCHEMA_VERSION),
        operation_id=operation_id,
        operation_type=(
            "move_defender_to_city"),
        goal_ids=(
            "pf-impact:survival",),
        participants=(
            participant,),
        target_ref="city:3",
        steps=operation_steps,
        created_turn=10,
        expiry_turn=13,
        replacement_margin=0.2,
        provenance=(
            "authoritative-snapshot",
            "server-advertised-action",
        ),
        ruleset_digest=(
            "ruleset-proof"))


def _activate(
        store, operation_id,
        snapshot_id="snapshot-10"):
    store.transition(
        operation_id,
        OperationState.RESERVABLE,
        snapshot_id, 10)
    store.transition(
        operation_id,
        OperationState.RESERVED,
        snapshot_id, 10)
    return store.transition(
        operation_id,
        OperationState.ACTIVE,
        snapshot_id, 10)


def test_operation_identity_excludes_volatile_score_and_is_order_stable():
    first = OperationParticipant(
        "escort", "unit:9",
        "unit", True)
    second = OperationParticipant(
        "founder", "unit:7",
        "unit", True)

    left = operation_id_from_components(
        "ferry_founder",
        ("expansion", "survival"),
        (first, second),
        "tile:8",
        "ruleset-proof", 20)
    right = operation_id_from_components(
        "ferry_founder",
        ("survival", "expansion"),
        (second, first),
        "tile:8",
        "ruleset-proof", 20)

    assert left == right
    assert left.startswith(
        "operation-")

    first_binding = operation_id_from_components(
        "ferry_founder", ("expansion", "survival"), (first, second),
        "tile:8", "ruleset-proof", 20,
        binding_identity='{"action_type":"unit_move","x":1}')
    second_binding = operation_id_from_components(
        "ferry_founder", ("expansion", "survival"), (first, second),
        "tile:8", "ruleset-proof", 20,
        binding_identity='{"action_type":"unit_move","x":2}')

    assert first_binding != second_binding
    assert first_binding != left


def test_operation_spec_round_trip_verifies_its_digest():
    expected = _spec()
    serialized = expected.to_dict()

    actual = OperationSpec.from_dict(
        serialized)

    assert actual == expected
    assert actual.spec_digest == (
        serialized["spec_digest"])
    serialized["expiry_turn"] = 99
    with pytest.raises(
            ValueError,
            match="digest mismatch"):
        OperationSpec.from_dict(
            serialized)


def test_store_enforces_lifecycle_attempt_and_terminal_boundaries():
    store = OperationStore(
        "game:proof")
    spec = _spec()
    proposed = store.propose(
        spec, "snapshot-10", 10)

    # Identical proposal recovery is idempotent.
    assert store.propose(
        spec, "snapshot-10", 10
    ) is proposed
    active = _activate(
        store, spec.operation_id)
    assert active.progress.state == (
        OperationState.ACTIVE)
    attempted = store.record_attempt(
        spec.operation_id,
        "snapshot-11", 11)
    assert attempted.progress.attempt_count == 1
    completed = store.advance_step(
        spec.operation_id,
        "snapshot-11", 11)
    assert completed.progress.state == (
        OperationState.COMPLETED)
    assert completed.progress.terminal_reason == (
        "all-steps-completed")
    with pytest.raises(
            OperationTransitionError,
            match="invalid operation transition"):
        store.transition(
            spec.operation_id,
            OperationState.ACTIVE,
            "snapshot-12", 12)


def test_store_initializes_and_advances_already_satisfied_prefix():
    store = OperationStore(
        "game:proof")
    spec = _spec(steps=3)
    store.propose(
        spec, "snapshot-10", 10)

    initialized = store.initialize_step(
        spec.operation_id, 1,
        "snapshot-10", 10)
    advanced = store.advance_satisfied_step(
        spec.operation_id,
        "snapshot-11", 11)

    assert initialized.progress.state == (
        OperationState.PROPOSED)
    assert initialized.progress.current_step_index == 1
    assert advanced.progress.current_step_index == 2
    assert advanced.progress.attempt_count == 0
    with pytest.raises(
            OperationTransitionError,
            match="fresh proposed"):
        store.initialize_step(
            spec.operation_id, 2,
            "snapshot-11", 11)


def test_store_records_new_observation_without_consuming_an_attempt():
    store = OperationStore(
        "game:proof")
    spec = _spec()
    store.propose(
        spec, "snapshot-10", 10)
    active = _activate(
        store, spec.operation_id)

    observed = store.record_observation(
        spec.operation_id,
        "snapshot-11", 11)
    identical = store.record_observation(
        spec.operation_id,
        "snapshot-11", 11)

    assert active.progress.state == (
        OperationState.ACTIVE)
    assert observed.progress.state == (
        OperationState.ACTIVE)
    assert observed.progress.current_step_index == 0
    assert observed.progress.attempt_count == 0
    assert observed.progress.last_snapshot_id == (
        "snapshot-11")
    assert identical is observed


def test_store_rejects_identity_collision_and_stale_progress():
    store = OperationStore(
        "game:proof")
    original = _spec()
    store.propose(
        original, "snapshot-10", 10)
    altered = OperationSpec(
        **{
            **original.__dict__,
            "expiry_turn": 14,
        })
    with pytest.raises(
            OperationStoreError,
            match="identity collision"):
        store.propose(
            altered, "snapshot-10", 10)
    with pytest.raises(
            OperationTransitionError,
            match="stale operation progress"):
        store.transition(
            original.operation_id,
            OperationState.RESERVABLE,
            "snapshot-11", 11,
            expected_snapshot_id=(
                "wrong-snapshot"))


def test_store_restart_round_trip_preserves_active_progress():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory,
            "operations.json")
        expected = OperationStore(
            "game:proof")
        spec = _spec(steps=2)
        expected.propose(
            spec, "snapshot-10", 10)
        _activate(
            expected,
            spec.operation_id)
        expected.record_attempt(
            spec.operation_id,
            "snapshot-11", 11)
        expected.advance_step(
            spec.operation_id,
            "snapshot-11", 11)
        expected.save(path)

        actual = OperationStore.load(
            path, "game:proof")

    assert not actual.quarantined
    assert actual.store_digest == (
        expected.store_digest)
    progress = actual.get(
        spec.operation_id).progress
    assert progress.state == (
        OperationState.ACTIVE)
    assert progress.current_step_index == 1
    assert progress.attempt_count == 0


def test_corrupt_or_wrong_identity_store_is_quarantined_without_rewrite():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory,
            "operations.json")
        original = b"{not-json\n"
        with open(path, "wb") as stream:
            stream.write(original)

        corrupt = OperationStore.load(
            path, "game:proof")

        assert corrupt.quarantined
        with open(path, "rb") as stream:
            assert stream.read() == (
                original)
        with pytest.raises(
                OperationStoreError,
                match="quarantined"):
            corrupt.propose(
                _spec(),
                "snapshot-10", 10)

        valid = OperationStore(
            "game:other")
        valid.save(path)
        wrong_identity = (
            OperationStore.load(
                path, "game:proof"))
        assert wrong_identity.quarantined
        # The mismatched durable record remains inspectable.
        with open(
                path,
                encoding="utf-8") as stream:
            assert json.load(stream)[
                "persistence_identity"
            ] == "game:other"


def test_expiry_is_deterministic_and_requires_turn_after_deadline():
    store = OperationStore(
        "game:proof")
    spec = _spec()
    store.propose(
        spec, "snapshot-10", 10)
    _activate(
        store, spec.operation_id)

    assert store.expire_due(
        13, "snapshot-13") == ()
    expired = store.expire_due(
        14, "snapshot-14")

    assert len(expired) == 1
    assert expired[0].progress.state == (
        OperationState.EXPIRED)
    assert expired[0].progress.terminal_reason == (
        "operation-deadline-passed")


def test_city_defense_assembler_retains_roles_steps_and_completion_semantics():
    operation = {
        "actor_id": 7,
        "city_id": 3,
        "deadline_turn": 12,
        "next_action": {
            "action_type": "unit_move",
            "actor_id": 7,
            "target": {
                "x": 4,
                "y": 5,
            },
        },
        "operation_id":
            "defense-operation-proof",
        "operation_type":
            "move_defender_to_city",
        "provenance": [
            "server-advertised-legal-action",
        ],
        "requirement_id":
            "defense:city:3",
    }

    spec = assemble_city_defense_operation(
        operation, 10,
        "ruleset-proof")

    assert spec.operation_id == (
        operation["operation_id"])
    assert spec.target_ref == "city:3"
    assert spec.expiry_turn == 12
    assert spec.participants[0].to_dict() == {
        "actor_class": "unit",
        "actor_id": "unit:7",
        "required": True,
        "role": "defender",
    }
    step = spec.steps[0]
    assert step.action_type == (
        "unit_move")
    assert step.requirement_set_id == (
        "defense:city:3")
    assert step.completion_predicate_id == (
        "city-defense:defender-at-city-before-deadline")
    assert step.maximum_attempts == 3
