"""Atomic GDO-5 combat assembly, reservation, and conditional readout."""

import copy
import json
import os
import sys
import tempfile
from dataclasses import replace
from types import SimpleNamespace

import pytest

REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (
    CombatOperationAssembler,
    CombatOperationLifecycle,
    ControlEventEmitter,
    ConditionalProbabilityInterval,
    GroundedImpactPlanner,
    OperationAuthorityKind,
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
from freeciv_agent.events.schema import structural_hash


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


def _next_snapshot(
        snapshot, source_seq,
        **changes):
    return replace(
        snapshot,
        identity=replace(
            snapshot.identity,
            source_seq=source_seq,
            state_hash=structural_hash({
                "changes": sorted(
                    changes),
                "source_seq":
                    source_seq,
            })),
        **changes)


def _assembly_schedule(snapshot):
    assembly = (
        CombatOperationAssembler()
        .assemble(
            snapshot,
            "ruleset-proof")[0])
    capacities = (
        ResourceCapacityExtractor()
        .extract(
            snapshot,
            action_budget=8)
        .capacities
        + combat_target_capacities(
            (assembly,), snapshot))
    schedule = (
        GreedyIdentityScheduler()
        .schedule(
            (assembly.resource_request,),
            capacities,
            requirement_sets=(
                assembly
                .requirement_set,),
            premise_packets=dict(
                assembly
                .initial_premise_packets)))
    return assembly, schedule


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
    ) == 6
    action_budget_claim = next(
        claim
        for claim in
        assembly.resource_request.claims
        if claim.resource.kind.value
        == "action_budget")
    assert action_budget_claim.quantity == 2
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
    readout = (
        CombatOperationAssembler
        .readout(
            supported[0],
            sentinel_snapshot,
            0))
    assert readout.disposition == (
        "reservable")

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
        .extract(
            snapshot,
            action_budget=8)
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


def test_atomic_operation_does_not_partially_activate_under_action_budget():
    snapshot = _snapshot()
    assemblies = (
        CombatOperationAssembler()
        .assemble(
            snapshot,
            "ruleset-proof"))
    assert len(assemblies) == 1
    capacities = (
        ResourceCapacityExtractor()
        .extract(
            snapshot,
            action_budget=1)
        .capacities
        + combat_target_capacities(
            assemblies, snapshot))
    assembly = assemblies[0]

    schedule = (
        GreedyIdentityScheduler()
        .schedule(
            (assembly.resource_request,),
            capacities,
            requirement_sets=(
                assembly
                .requirement_set,),
            premise_packets=dict(
                assembly
                .initial_premise_packets)))

    assert (
        schedule
        .selected_operation_ids
    ) == ()
    assert schedule.entries[
        0].reason == (
            "resource-capacity-exceeded")


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
                "ruleset-proof",
                action_budget=8))
        duplicate = (
            emitter
            .emit_combat_operation_shadow(
                writer,
                snapshot,
                "ruleset-proof",
                action_budget=8))
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


def test_combat_lifecycle_completes_and_releases_when_first_attack_kills():
    snapshot = _snapshot()
    assembly, schedule = (
        _assembly_schedule(
            snapshot))
    lifecycle = (
        CombatOperationLifecycle(
            "game-proof"))

    registered = (
        lifecycle
        .register_schedule(
            (assembly,),
            schedule,
            snapshot))
    committed = (
        lifecycle
        .commit_matching_action(
            snapshot,
            assembly.action_for_step(0),
            accepted=True))
    target_destroyed = (
        _next_snapshot(
            snapshot, 20,
            visible_enemy_units=()))
    resolved = lifecycle.observe(
        target_destroyed)

    assert registered[0].state == (
        "reserved")
    assert committed[0].disposition == (
        "step_committed")
    assert not lifecycle.ledger.reservation(
        assembly.spec.operation_id
    ).active
    assert resolved[0].state == (
        "completed")
    assert resolved[0].reason == (
        "target-neutralized")
    assert lifecycle.store.get(
        assembly.spec.operation_id
    ).progress.current_step_index == 0


def test_reserved_combat_operation_completes_if_target_is_removed_externally():
    snapshot = _snapshot()
    assembly, schedule = (
        _assembly_schedule(
            snapshot))
    lifecycle = (
        CombatOperationLifecycle(
            "game-proof"))
    lifecycle.register_schedule(
        (assembly,), schedule,
        snapshot)

    resolved = lifecycle.observe(
        _next_snapshot(
            snapshot, 19,
            visible_enemy_units=()))

    assert resolved[0].previous_state == (
        "reserved")
    assert resolved[0].state == (
        "completed")
    assert resolved[0].reason == (
        "target-neutralized")
    assert resolved[
        0].released_reservation is not None
    assert lifecycle.ledger.active_claims() == ()


def test_new_combat_schedule_fails_closed_beside_active_reservation():
    snapshot = _snapshot(
        actor_count=3)
    assemblies = (
        CombatOperationAssembler()
        .assemble(
            snapshot,
            "ruleset-proof"))
    assert len(assemblies) >= 2
    capacities = (
        ResourceCapacityExtractor()
        .extract(
            snapshot,
            action_budget=8)
        .capacities
        + combat_target_capacities(
            assemblies, snapshot))

    def single_schedule(assembly):
        return (
            GreedyIdentityScheduler()
            .schedule(
                (assembly.resource_request,),
                capacities,
                requirement_sets=(
                    assembly
                    .requirement_set,),
                premise_packets=dict(
                    assembly
                    .initial_premise_packets)))

    lifecycle = (
        CombatOperationLifecycle(
            "active-conflict-proof"))
    first = lifecycle.register_schedule(
        (assemblies[0],),
        single_schedule(
            assemblies[0]),
        snapshot)
    second = lifecycle.register_schedule(
        (assemblies[1],),
        single_schedule(
            assemblies[1]),
        snapshot)

    assert len(first) == 1
    assert second == ()
    assert lifecycle.ledger.reservation(
        assemblies[0].spec.operation_id
    ).active
    assert lifecycle.ledger.reservation(
        assemblies[1].spec.operation_id
    ) is None


def test_shadow_emitter_attributes_cross_snapshot_reservation_conflict():
    snapshot = _snapshot(
        actor_count=3)
    next_snapshot = replace(
        _next_snapshot(
            snapshot, 31),
        identity=replace(
            snapshot.identity,
            turn=snapshot.turn + 1,
            source_seq=31,
            state_hash=structural_hash(
                "cross-snapshot-conflict")))
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory,
            "events.jsonl")
        writer = EventWriter(
            path,
            "combat-active-conflict",
            durable=False)
        emitter = ControlEventEmitter()
        emitter.emit_combat_operation_shadow(
            writer, snapshot,
            "ruleset-proof",
            action_budget=8)
        events = (
            emitter
            .emit_combat_operation_shadow(
                writer, next_snapshot,
                "ruleset-proof",
                action_budget=8))
        report = validate_file(path)

    conflicts = [
        row for row in events
        if row["type"]
        == "operation_blocked"
        and row["payload"][
            "reason_code"]
        == "active-reservation-conflict"]
    assert conflicts
    assert report.valid, [
        row.to_dict()
        for row in report.errors]


def test_combat_lifecycle_reestimates_and_reserves_only_the_next_step():
    snapshot = _snapshot()
    assembly, schedule = (
        _assembly_schedule(
            snapshot))
    lifecycle = (
        CombatOperationLifecycle(
            "game-proof"))
    lifecycle.register_schedule(
        (assembly,), schedule,
        snapshot)
    lifecycle.commit_matching_action(
        snapshot,
        assembly.action_for_step(0),
        accepted=True)
    after_first = _next_snapshot(
        snapshot, 21)

    reestimated = lifecycle.observe(
        after_first)

    assert len(reestimated) == 1
    update = reestimated[0]
    assert update.disposition == (
        "step_reestimated")
    assert update.step_index == 1
    assert update.next_action[
        "actor_id"] == 103
    assert update.probability_interval.source.endswith(
        "current-snapshot")
    assert len(
        update.reservation.claims
    ) == 4
    action_claim = next(
        claim for claim in
        update.reservation.claims
        if claim.resource.kind.value
        == "action_budget")
    assert action_claim.quantity == 1
    assert update.reservation.snapshot_id == (
        after_first.snapshot_id)

    lifecycle.commit_matching_action(
        after_first,
        assembly.action_for_step(1),
        accepted=True)
    target_survived = _next_snapshot(
        after_first, 22)
    terminal = lifecycle.observe(
        target_survived)

    assert terminal[0].state == (
        "failed")
    assert terminal[0].reason == (
        "all-attacks-resolved-target-survived")
    assert lifecycle.ledger.active_claims() == ()


def test_combat_lifecycle_blocks_repairs_and_abandons_removed_participant():
    snapshot = _snapshot()
    assembly, schedule = (
        _assembly_schedule(
            snapshot))
    lifecycle = (
        CombatOperationLifecycle(
            "game-proof"))
    lifecycle.register_schedule(
        (assembly,), schedule,
        snapshot)
    lifecycle.commit_matching_action(
        snapshot,
        assembly.action_for_step(0),
        accepted=True)
    illegal = _next_snapshot(
        snapshot, 23,
        legal_action_json=tuple(
            value for value in
            snapshot.legal_action_json
            if json.loads(value).get(
                "actor_id") != 103))

    blocked = lifecycle.observe(
        illegal)

    assert blocked[0].state == (
        "blocked")
    assert blocked[0].step_index == 1
    assert blocked[0].reason == (
        "current-step-action-no-longer-legal")
    assert lifecycle.ledger.active_claims() == ()

    repaired_snapshot = _next_snapshot(
        snapshot, 24)
    repaired = lifecycle.observe(
        repaired_snapshot)

    assert repaired[0].disposition == (
        "repaired")
    assert repaired[0].state == (
        "reserved")
    assert repaired[0].step_index == 1
    assert repaired[0].reservation.active

    removed = _next_snapshot(
        repaired_snapshot, 25,
        units=tuple(
            unit for unit in
            repaired_snapshot.units
            if unit.unit_id != 103))
    abandoned = lifecycle.observe(
        removed)

    assert abandoned[0].state == (
        "abandoned")
    assert abandoned[0].reason == (
        "required-participant-removed")
    assert lifecycle.ledger.active_claims() == ()


def test_combat_lifecycle_events_are_causal_valid_and_release_every_claim():
    snapshot = _snapshot()
    assembly, _ = (
        _assembly_schedule(
            snapshot))
    target_destroyed = _next_snapshot(
        snapshot, 30,
        visible_enemy_units=())
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory, "events.jsonl")
        writer = EventWriter(
            path,
            "combat-lifecycle-events",
            durable=False)
        emitter = ControlEventEmitter()
        proposed = (
            emitter
            .emit_combat_operation_shadow(
                writer, snapshot,
                "ruleset-proof",
                action_budget=8))
        committed = (
            emitter
            .emit_combat_action_outcome(
                writer, snapshot,
                assembly.action_for_step(0),
                SimpleNamespace(
                    submitted=True,
                    status="accepted",
                    action_id="action-proof",
                    reason=None),
                caused_by=(
                    proposed[-1][
                        "event_id"],)))
        resolved = (
            emitter
            .resolve_combat_operations(
                writer,
                target_destroyed,
                caused_by=(
                    committed[-1][
                        "event_id"],)))
        report = validate_file(
            path)
        with open(
                path,
                encoding="utf-8") as stream:
            events = [
                json.loads(line)
                for line in stream
                if line.strip()]

    event_types = [
        row["type"]
        for row in events
    ]
    assert "operation_reserved" in (
        event_types)
    assert "operation_activated" in (
        event_types)
    assert "operation_step_committed" in (
        event_types)
    assert "operation_completed" in (
        event_types)
    releases = [
        row for row in events
        if row["type"]
        == "resource_claim_released"]
    assert len(releases) == len(
        assembly.resource_request
        .claims)
    assert {
        row["payload"]["reason"]
        for row in releases
    } == {
        "step-0-committed-reestimate-required"
    }
    assert resolved[-1]["payload"][
        "resolution_status"
    ] == "resolved_success"
    assert report.valid, [
        row.to_dict()
        for row in report.errors]


def test_bounded_combat_authority_reads_out_and_commits_exact_reserved_step():
    snapshot = _snapshot()
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory,
            "events.jsonl")
        writer = EventWriter(
            path,
            "combat-operation-authority",
            durable=False)
        emitter = ControlEventEmitter()
        proposed = (
            emitter
            .emit_combat_operation_shadow(
                writer, snapshot,
                "ruleset-proof",
                action_budget=8))
        readout = (
            emitter
            .operation_authority_readout(
                writer, snapshot,
                combat_enabled=True))

        assert readout is not None
        assert readout.authority_kind == (
            OperationAuthorityKind.COMBAT)
        assert readout.action_key in (
            snapshot.legal_action_json)

        planner = GroundedImpactPlanner({
            "pressure_achievement_uncertainty_split_enabled": True,
            "pressure_combat_operation_authority_enabled": True,
            "pressure_combat_operations_enabled": True,
            "pressure_commit_revalidation_enabled": True,
            "pressure_controller_mode": "scalar_v2",
            "pressure_distributional_risk_enabled": True,
            "pressure_domain_estimates_enabled": True,
            "pressure_enabled": True,
            "pressure_native_combat_probabilities_enabled": True,
            "pressure_operation_lifecycle_enabled": True,
            "pressure_packet_scheduler_enabled": True,
            "pressure_requirement_sets_enabled": True,
            "pressure_resource_scheduler_enabled": True,
            "pressure_semantics_version": "v2",
            "pressure_signed_channels_enabled": True,
        })
        decision = planner.plan(
            snapshot,
            operation_authority=readout)

        assert decision.candidate.action_key == (
            readout.action_key)
        assert planner.last_control_decision\
            .selected_candidate_key == (
                readout.action_key)
        assert decision.operation_authority[
            "applied"]
        assert decision.pressure_artifact[
            "operation_authority"][
                "authority_active"]

        selected = (
            emitter
            .emit_operation_authority_selection(
                writer, snapshot.turn,
                readout,
                decision
                .operation_authority[
                    "baseline_candidate_key"],
                caused_by=(
                    proposed[-1][
                        "event_id"],)))
        committed = (
            emitter
            .emit_combat_action_outcome(
                writer, snapshot,
                decision.candidate.action,
                SimpleNamespace(
                    submitted=True,
                    status="accepted",
                    action_id=(
                        "authority-action"),
                    reason=None),
                caused_by=(
                    selected[-1][
                        "event_id"],)))
        report = validate_file(path)

    assert report.valid
    assert any(
        row["type"]
        == "operation_step_committed"
        for row in committed)
    assert all(
        row["payload"][
            "policy_authority"]
        and not row["payload"][
            "shadow_only"]
        for row in committed
        if row["type"].startswith(
            "operation_"))
