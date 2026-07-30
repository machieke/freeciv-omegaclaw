"""Atomic GDO-5 combat assembly, reservation, and conditional readout."""

import copy
import json
import os
import sys
import tempfile
from dataclasses import replace

import pytest

REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (
    CombatOperationAssembler,
    ControlEventEmitter,
    ConditionalProbabilityInterval,
    combat_target_capacities,
    conditional_success_interval,
)
from freeciv_agent.pressure import (
    GreedyIdentityScheduler,
    ResourceCapacityExtractor,
)
from freeciv_agent.state import ProxyStateDTO
from freeciv_agent.events.validator import validate_file
from freeciv_agent.events.writer import EventWriter


def _revision(unit):
    return {
        "activity": unit.get("activity"),
        "hp": unit.get("hp"),
        "id": unit.get("id"),
        "moves_left": unit.get(
            "moves_left"),
        "owner": unit.get("owner"),
        "tile": unit.get("tile"),
        "transported": unit.get(
            "transported"),
        "transported_by": unit.get(
            "transported_by"),
        "type_id": unit.get("type_id"),
        "veteran": unit.get("veteran"),
    }


def _probability_rows(minimum, maximum):
    result = []
    for action_id, action_name in (
            (24, "capture_units"),
            (45, "attack"),
            (46, "suicide_attack"),
            (49, "conquer_city"),
            (53, "bombard")):
        if action_id == 45:
            values = (
                minimum, maximum,
                "bounded")
        else:
            values = (
                253, 0,
                "not_applicable")
        result.append({
            "action_id": action_id,
            "action_name": action_name,
            "minimum": values[0],
            "maximum": values[1],
            "status": values[2],
        })
    return result


def _combat_result(
        actor, defender,
        minimum, maximum,
        request_seq, response_seq):
    return {
        "action_probabilities":
            _probability_rows(
                minimum, maximum),
        "actor_revision":
            _revision(actor),
        "actor_unit_id": actor["id"],
        "authority":
            "freeciv-server-action-probability",
        "player_id": 0,
        "request_kind":
            "background_refresh",
        "request_source_seq":
            request_seq,
        "response_source_seq":
            response_seq,
        "schema_version": "1.0",
        "target_city_id": 0,
        "target_extra_id": -1,
        "target_stack_revision": [
            _revision(defender)],
        "target_tile_id":
            defender["tile"],
        "target_unit_id":
            defender["id"],
        "turn": 1,
    }


def _snapshot(actor_count=2, intervals=None):
    path = os.path.join(
        REPO, "benchmarks", "freeciv",
        "samples", "real_state_turn1.json")
    with open(path, encoding="utf-8") as stream:
        payload = copy.deepcopy(
            json.load(stream))
    actor_template = payload["units"][
        "102"]
    actors = []
    if intervals is None:
        intervals = (
            (140, 140),
            (80, 100),
            (120, 130),
        )
    for index in range(actor_count):
        actor_id = 102 + index
        actor = copy.deepcopy(
            actor_template)
        actor.update({
            "activity": "idle",
            "hp": 10,
            "id": actor_id,
            "moves_left": 3,
            "owner": 0,
            "tile": 2030,
            "transported": False,
            "type": "Warriors",
            "type_id": 0,
            "veteran": 0,
            "x": 14,
            "y": 42,
        })
        payload["units"][str(
            actor_id)] = actor
        payload["legal_actions"][
            str(actor_id)] = [{
                "action": "attack",
                "action_id": 45,
                "is_valid": True,
                "params": {
                    "target": {
                        "x": 14,
                        "y": 41,
                    },
                },
                "type": "unit_action",
                "unit_id": actor_id,
            }]
        actors.append(actor)
    defender = {
        "activity": "idle",
        "done_moving": False,
        "hp": 10,
        "id": 999,
        "moves_left": 3,
        "owner": 1,
        "tile": 1982,
        "transported": False,
        "type": "Phalanx",
        "type_id": 2,
        "veteran": 0,
        "x": 14,
        "y": 41,
    }
    payload["units"]["999"] = (
        defender)
    payload["authoritative"] = {
        "combat_probabilities": [
            _combat_result(
                actor,
                defender,
                intervals[index][0],
                intervals[index][1],
                index,
                index + 1)
            for index, actor
            in enumerate(actors)
        ],
    }
    return ProxyStateDTO.parse(
        "combat-operation", actor_count,
        payload).to_snapshot()


def test_conditional_probability_uses_an_explicit_failure_branch():
    first = (
        ConditionalProbabilityInterval(
            0.4, 0.5,
            "first"))
    second_given_failure = (
        ConditionalProbabilityInterval(
            0.2, 0.3,
            "conditional"))

    result = conditional_success_interval(
        first,
        second_given_failure)

    assert result.lower == pytest.approx(
        0.52)
    assert result.upper == pytest.approx(
        0.65)
    assert result.source.startswith(
        "explicit-conditional")


def test_assembler_retains_both_participants_and_deterministic_identity():
    snapshot = _snapshot()
    assembler = CombatOperationAssembler()

    first = assembler.assemble(
        snapshot, "ruleset-proof")
    second = assembler.assemble(
        snapshot, "ruleset-proof")

    assert first == second
    assert len(first) == 1
    assembly = first[0]
    assert assembly.spec.operation_type == (
        "attack_then_conditional_attack")
    assert [
        row.actor_id
        for row in
        assembly.spec.participants
    ] == ["unit:102", "unit:103"]
    assert [
        row.actor_role
        for row in assembly.spec.steps
    ] == [
        "primary_attacker",
        "conditional_attacker",
    ]
    assert (
        assembly
        .operation_probability_interval
        .lower
    ) == pytest.approx(0.7)
    assert (
        assembly
        .operation_probability_interval
        .upper
    ) == 1.0
    assert assembly.requirement_set.complete(
        dict(
            assembly
            .initial_premise_packets))
    assert len(
        assembly.resource_request.claims
    ) == 5
    assert assembly.shadow_only
    assert not assembly.policy_authority


def test_assembler_resolves_only_an_unambiguous_visible_stack_target():
    snapshot = _snapshot()
    sentinel_rows = tuple(
        replace(
            row,
            target_unit_id=0)
        for row in
        snapshot.combat_probabilities)
    sentinel_snapshot = replace(
        snapshot,
        combat_probabilities=(
            sentinel_rows))

    supported = (
        CombatOperationAssembler()
        .assemble(
            sentinel_snapshot,
            "ruleset-proof"))

    assert len(supported) == 1
    assert supported[0].target_unit_id == 999

    ambiguous_snapshot = replace(
        sentinel_snapshot,
        combat_probabilities=tuple(
            replace(
                row,
                target_unit_ids=(
                    998, 999))
            for row in
            sentinel_rows))
    assert (
        CombatOperationAssembler()
        .assemble(
            ambiguous_snapshot,
            "ruleset-proof")
    ) == ()


def test_assembler_does_not_treat_a_zero_interval_as_attack_support():
    snapshot = _snapshot(
        intervals=(
            (140, 140),
            (0, 0),
            (120, 130),
        ))

    assert (
        CombatOperationAssembler()
        .assemble(
            snapshot,
            "ruleset-proof")
    ) == ()


def test_atomic_resource_schedule_prevents_duplicate_targeting():
    snapshot = _snapshot(
        actor_count=3)
    assemblies = (
        CombatOperationAssembler()
        .assemble(
            snapshot,
            "ruleset-proof"))
    assert len(assemblies) == 3
    capacities = (
        ResourceCapacityExtractor()
        .extract(snapshot)
        .capacities
        + combat_target_capacities(
            assemblies, snapshot))
    premise_packets = {
        premise_id: 1
        for assembly in assemblies
        for premise_id in
        assembly.requirement_set
        .premise_ids
    }

    schedule = (
        GreedyIdentityScheduler()
        .schedule(
            tuple(
                assembly
                .resource_request
                for assembly
                in assemblies),
            capacities,
            requirement_sets=tuple(
                assembly
                .requirement_set
                for assembly
                in assemblies),
            premise_packets=(
                premise_packets)))

    assert len(
        schedule.selected_operation_ids
    ) == 1
    rejected = [
        row for row in schedule.entries
        if not row.selected
    ]
    assert rejected
    assert all(
        row.reason in (
            "exclusive-resource-conflict",
            "resource-capacity-exceeded")
        for row in rejected)


def test_snapshot_exposes_exact_revision_native_combat_evidence():
    snapshot = _snapshot(
        actor_count=2)

    grounded = snapshot.event_payload()[
        "grounded_context"]

    assert grounded[
        "schema_version"] == "1.3"
    assert len(grounded[
        "combat_probabilities"]) == 2
    assert all(
        row["authority"]
        == "freeciv-server-action-probability"
        for row in grounded[
            "combat_probabilities"])


def test_shadow_emitter_records_atomic_schedule_and_native_intervals():
    snapshot = _snapshot(
        actor_count=3)

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory,
            "events.jsonl")
        writer = EventWriter(
            path,
            "combat-shadow-events",
            durable=False)
        emitter = ControlEventEmitter()
        events = (
            emitter
            .emit_combat_operation_shadow(
                writer,
                snapshot,
                "ruleset-proof"))
        duplicate = (
            emitter
            .emit_combat_operation_shadow(
                writer,
                snapshot,
                "ruleset-proof"))
        report = validate_file(path)

    proposals = [
        row for row in events
        if row["type"]
        == "operation_proposed"]
    assert len(proposals) == 3
    assert sum(
        row["payload"]["selected"]
        for row in proposals) == 1
    assert all(
        row["payload"]["shadow_only"]
        and not row["payload"][
            "policy_authority"]
        and row["payload"][
            "requirement_set"]
        and len(row["payload"][
            "participants"]) == 2
        and row["payload"][
            "probability_interval"][
                "upper"] == 1.0
        for row in proposals)
    schedule = next(
        row for row in events
        if row["type"]
        == "resource_schedule_decided")
    assert len(schedule["payload"][
        "selected_operation_ids"]) == 1
    rejected = [
        row for row in events
        if row["type"]
        == "resource_claim_rejected"]
    assert rejected
    assert duplicate == ()
    assert report.valid, [
        row.to_dict()
        for row in report.errors]


def test_readout_reestimates_each_step_and_handles_target_or_actor_removal():
    snapshot = _snapshot()
    assembly = (
        CombatOperationAssembler()
        .assemble(
            snapshot,
            "ruleset-proof")[0])

    first = CombatOperationAssembler.readout(
        assembly, snapshot, 0)
    second = CombatOperationAssembler.readout(
        assembly, snapshot, 1)
    target_destroyed = replace(
        snapshot,
        visible_enemy_units=())
    participant_removed = replace(
        snapshot,
        units=tuple(
            unit for unit in snapshot.units
            if unit.unit_id != 103))

    assert first.disposition == (
        "reservable")
    assert first.next_action[
        "actor_id"] == 102
    assert second.disposition == (
        "reservable")
    assert second.next_action[
        "actor_id"] == 103
    assert (
        CombatOperationAssembler
        .readout(
            assembly,
            target_destroyed,
            1)
        .disposition
    ) == "completed"
    removed = (
        CombatOperationAssembler
        .readout(
            assembly,
            participant_removed,
            1))
    assert removed.disposition == (
        "abandoned")
    assert removed.reason == (
        "required-participant-removed")


def test_missing_joint_support_or_illegal_step_falls_back_closed():
    snapshot = _snapshot()
    assembler = (
        CombatOperationAssembler())
    assembly = assembler.assemble(
        snapshot, "ruleset-proof")[0]

    incomplete = replace(
        snapshot,
        combat_probabilities=(
            snapshot
            .combat_probabilities[:1]))
    illegal = replace(
        snapshot,
        legal_action_json=tuple(
            value for value
            in snapshot.legal_action_json
            if json.loads(value).get(
                "actor_id") != 103))

    assert assembler.assemble(
        incomplete,
        "ruleset-proof") == ()
    blocked = assembler.readout(
        assembly, illegal, 1)
    assert blocked.disposition == (
        "blocked")
    assert blocked.reason == (
        "current-step-action-no-longer-legal")
