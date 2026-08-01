"""Grounded founder/ferry operation assembly and current-step readout."""

import copy
import json
import os
import sys
from dataclasses import replace
from types import SimpleNamespace


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import (  # noqa: E402
    FdasFounderTransportProjectionAdapter,
    FounderTransportIntent,
    FounderTransportOperationAssembler,
    FounderTransportOperationLifecycle,
    OperationState,
    SettlementRetentionTracker,
)
from freeciv_agent.pressure import (  # noqa: E402
    BoundedExactScheduler,
    ClaimHardness,
    GameResourceKind,
    ResourceCapacityExtractor,
)
from freeciv_agent.state import (  # noqa: E402
    CityState,
    MovementRouteState,
    ProxyStateDTO,
    SnapshotIdentity,
)
from freeciv_agent.state.atomspace import (  # noqa: E402
    DependentAtomSpaceStore,
    OperationProjector,
)


def _rule(
        name, unit_class,
        capacity=0, cargo=(),
        flags=()):
    return SimpleNamespace(
        target_kind="unit",
        display_name=name,
        rule_name=name,
        quantitative={
            "transport_cap": {
                "value": capacity,
            },
        },
        traits={
            "cargo": {
                "values": list(cargo),
            },
            "class": {
                "values": [unit_class],
            },
            "flags": {
                "values": list(flags),
            },
        })


def _ruleset(capacity=2):
    return SimpleNamespace(rules=(
        _rule(
            "Settlers",
            "Small Land",
            flags=("Cities",)),
        _rule(
            "Trireme",
            "Trireme",
            capacity=capacity,
            cargo=(
                "Land",
                "Merchant",
                "Small Land")),
    ))


def _move(
        actor_id, target_tile,
        transport_required=False):
    return {
        "action_type": "unit_move",
        "actor_id": actor_id,
        "is_valid": True,
        "movement_cost": 3,
        "target": {
            "direction": "e",
            "x": target_tile % 48,
            "y": target_tile // 48,
        },
        "transport_required":
            transport_required,
    }


def _route_payload(
        unit_id, origin,
        destination, first_step,
        estimated_turns,
        transported=False):
    return {
        "authority":
            "freeciv-server-pathfinder",
        "destination_tile":
            destination,
        "estimated_turns":
            estimated_turns,
        "first_step_movement_cost": 3,
        "first_step_tile":
            first_step,
        "initially_transported":
            transported,
        "movement_points_remaining": 0,
        "moves_left_at_request": 3,
        "origin_tile": origin,
        "path_directions": [
            1 for _ in
            range(estimated_turns)],
        "path_length":
            estimated_turns,
        "reachable": True,
        "schema_version": "1.0",
        "source_seq": 1,
        "total_movement_cost":
            estimated_turns * 3,
        "transported_at_request":
            transported,
        "turn": 1,
        "unit_id": unit_id,
    }


def _unit(
        unit_id, unit_type,
        tile, carrying=0):
    return {
        "activity": "idle",
        "carrying": carrying,
        "done_moving": False,
        "homecity": 0,
        "hp": 20,
        "id": unit_id,
        "moves_left": 3,
        "owner": 0,
        "tile": tile,
        "transported": False,
        "transported_by": 0,
        "type": unit_type,
        "type_id": (
            34 if unit_type
            == "Trireme" else 0),
        "upkeep": [],
        "veteran": 0,
        "x": tile % 48,
        "y": tile // 48,
    }


def _base_payload():
    with open(os.path.join(
            REPO, "benchmarks",
            "freeciv", "samples",
            "real_state_turn1.json"),
            encoding="utf-8") as stream:
        return json.load(stream)


def _known_tiles(*extra):
    return tuple(sorted(set((
        100, 101, 200, 201,
        202, 300, 301, 302,
    ) + tuple(extra))))


def _snapshot(
        embark=False,
        two_founders=False):
    payload = copy.deepcopy(
        _base_payload())
    founder_tile = (
        200 if embark else 100)
    units = {
        "102": _unit(
            102, "Settlers",
            founder_tile),
        "200": _unit(
            200, "Trireme",
            201 if embark else 200),
    }
    legal = {}
    routes = []
    if embark:
        legal["102"] = [
            _move(
                102, 201, True)]
        if two_founders:
            units["103"] = _unit(
                103, "Settlers", 200)
            legal["103"] = [
                _move(
                    103, 201, True)]
    else:
        legal = {
            "102": [
                _move(102, 101)],
            "200": [
                _move(200, 201)],
        }
        routes = [
            _route_payload(
                102, 100, 201,
                101, 4),
            _route_payload(
                200, 200, 201,
                201, 1),
        ]
    payload["units"] = units
    payload["legal_actions"] = legal
    payload["authoritative"] = {
        "movement_routes": routes,
    }
    tiles = _known_tiles(
        303 if two_founders else 302)
    payload["map"].update({
        "tiles": [
            {
                "index": tile,
                "known": 2,
                "terrain": 1,
            }
            for tile in tiles
        ],
        "visibility": {
            str(tile): True
            for tile in tiles
        },
        "wrap_x": True,
        "wrap_y": False,
    })
    return ProxyStateDTO.parse(
        "transport-operation",
        1, payload).to_snapshot()


def _intent(
        founder_id=102,
        settlement_tile=302,
        rendezvous_deadline=8):
    return FounderTransportIntent(
        founder_unit_id=founder_id,
        ferry_unit_id=200,
        pickup_tile_id=201,
        landing_carrier_tile_id=300,
        landing_tile_id=301,
        settlement_tile_id=(
            settlement_tile),
        rendezvous_deadline_turn=(
            rendezvous_deadline),
        settlement_deadline_turn=20)


def _canonical_actions(actions):
    return tuple(sorted(
        canonical_json_bytes(
            action).decode("utf-8")
        for action in actions))


def _route(
        unit_id, origin,
        destination, first_step,
        estimated_turns,
        transported=False,
        source_seq=2):
    return MovementRouteState(
        unit_id=unit_id,
        origin_tile=origin,
        destination_tile=destination,
        reachable=True,
        first_step_tile=first_step,
        first_step_movement_cost=3,
        path_length=estimated_turns,
        path_directions=tuple(
            1 for _ in
            range(estimated_turns)),
        estimated_turns=(
            estimated_turns),
        total_movement_cost=(
            estimated_turns * 3),
        movement_points_remaining=0,
        moves_left_at_request=3,
        transported_at_request=(
            transported),
        initially_transported=(
            transported),
        turn=1,
        source_seq=source_seq)


def _revision(
        snapshot, seq,
        units, actions,
        routes=(), cities=None):
    action_json = _canonical_actions(
        actions)
    return replace(
        snapshot,
        identity=SnapshotIdentity(
            snapshot.identity.game_id,
            snapshot.turn,
            seq,
            structural_hash({
                "actions": list(
                    action_json),
                "seq": seq,
                "units": [
                    unit.grounded_dict()
                    for unit in units],
            })),
        units=tuple(sorted(
            units,
            key=lambda unit:
                unit.unit_id)),
        legal_action_json=(
            action_json),
        legal_actions_digest=(
            structural_hash(
                list(action_json))),
        legal_action_kinds=tuple(sorted({
            action["action_type"]
            for action in actions
        })),
        movement_routes=tuple(
            routes),
        cities=(
            snapshot.cities
            if cities is None
            else tuple(cities)))


def _with_turn(
        snapshot, turn, seq=None):
    source_seq = (
        int(turn)
        if seq is None
        else int(seq))
    return replace(
        snapshot,
        identity=SnapshotIdentity(
            snapshot.identity.game_id,
            int(turn),
            source_seq,
            structural_hash({
                "prior":
                    snapshot.identity
                    .state_hash,
                "source_seq":
                    source_seq,
                "turn": int(turn),
            })))


def test_partner_locked_assembly_uses_native_rendezvous_and_future_claims():
    snapshot = _snapshot()

    decision = (
        FounderTransportOperationAssembler()
        .assemble(
            snapshot,
            _ruleset(),
            "ruleset-proof",
            _intent()))

    assert decision.disposition == (
        "assembled")
    assembly = decision.assembly
    assert assembly.rendezvous_eta_turns == 4
    assert assembly.initial_step_index == 0
    assert assembly.initial_readout.phase == (
        "founder_to_pickup")
    assert assembly.initial_readout.next_action == (
        json.loads(
            snapshot
            .legal_action_json[0]))
    assert tuple(
        row.role for row
        in assembly.spec.participants
    ) == ("founder", "ferry")
    assert len(assembly.spec.steps) == 7
    assert tuple(
        row.actor_id
        for row in
        assembly.initial_corridors
    ) == ("unit:102", "unit:200")
    assert assembly.requirement_set.complete(
        dict(
            assembly
            .initial_premise_packets))
    assert any(
        claim.hardness
        == ClaimHardness.HARD_CURRENT
        and claim.resource.kind
        == GameResourceKind.ACTOR
        and claim.resource.owner_id
        == "unit:102"
        for claim in
        assembly.resource_request
        .claims)
    assert any(
        claim.hardness
        == ClaimHardness.CONDITIONAL_FUTURE
        and claim.resource.kind
        == GameResourceKind.TRANSPORT_SEAT
        and claim.resource.owner_id
        == "unit:200"
        for claim in
        assembly.resource_request
        .claims)
    assert len({
        claim.resource.owner_id
        for claim in
        assembly.resource_request
        .claims
        if claim.resource.kind
        == GameResourceKind.TILE_OCCUPANCY
    }) == 4


def test_assembly_abstains_when_deadline_cargo_or_escort_is_not_grounded():
    snapshot = _snapshot()
    assembler = (
        FounderTransportOperationAssembler())

    late = assembler.assemble(
        snapshot, _ruleset(),
        "ruleset-proof",
        _intent(
            rendezvous_deadline=3))
    incompatible = assembler.assemble(
        snapshot,
        _ruleset(capacity=0),
        "ruleset-proof",
        _intent())
    escorted = assembler.assemble(
        snapshot, _ruleset(),
        "ruleset-proof",
        replace(
            _intent(),
            escort_unit_id=300))

    assert late.reason == (
        "rendezvous-route-misses-deadline")
    assert incompatible.reason == (
        "ferry-profile-load-or-cargo-incompatible")
    assert escorted.reason == (
        "grounded-escort-risk-model-required")
    assert escorted.missing_inputs == (
        "escort_survival_estimate",)


def test_embark_abstains_when_locked_ferry_is_not_unique_at_pickup():
    initial = _snapshot(
        embark=True)
    second_ferry = replace(
        initial.unit(200),
        unit_id=201)
    ambiguous = _revision(
        initial, 2,
        initial.units
        + (second_ferry,),
        (
            json.loads(
                initial
                .legal_action_json[0]),))

    decision = (
        FounderTransportOperationAssembler()
        .assemble(
            ambiguous,
            _ruleset(),
            "ruleset-proof",
            _intent()))

    assert decision.disposition == (
        "abstain")
    assert decision.reason == (
        "initial-transport-step-not-grounded")
    assert decision.missing_inputs == (
        "locked-ferry-not-unique-compatible-carrier",)


def test_one_free_seat_cannot_activate_two_founders():
    snapshot = _snapshot(
        embark=True,
        two_founders=True)
    ruleset = _ruleset(
        capacity=1)
    assembler = (
        FounderTransportOperationAssembler())
    first = assembler.assemble(
        snapshot, ruleset,
        "ruleset-proof",
        _intent(102, 302))
    second = assembler.assemble(
        snapshot, ruleset,
        "ruleset-proof",
        _intent(103, 303))

    assert first.disposition == (
        "assembled")
    assert second.disposition == (
        "assembled")
    requirements = (
        first.assembly
        .requirement_set,
        second.assembly
        .requirement_set)
    packets = {}
    for assembly in (
            first.assembly,
            second.assembly):
        packets.update(dict(
            assembly
            .initial_premise_packets))
    capacities = (
        ResourceCapacityExtractor()
        .extract(
            snapshot,
            ruleset_ir=ruleset,
            action_budget=2)
        .capacities)
    schedule = (
        BoundedExactScheduler()
        .schedule(
            (
                first.assembly
                .resource_request,
                second.assembly
                .resource_request),
            capacities,
            requirement_sets=(
                requirements),
            premise_packets=(
                packets)))

    assert len(
        schedule
        .selected_operation_ids
    ) == 1
    hard_seats = [
        claim
        for claim in
        schedule.selected_claims()
        if (
            claim.hardness
            == ClaimHardness.HARD_CURRENT
            and claim.resource.kind
            == GameResourceKind.TRANSPORT_SEAT)
    ]
    assert len(hard_seats) == 1
    assert hard_seats[0].quantity == 1


def test_readout_revalidates_every_phase_and_rejects_partner_switch():
    initial = _snapshot(
        embark=True)
    decision = (
        FounderTransportOperationAssembler()
        .assemble(
            initial,
            _ruleset(),
            "ruleset-proof",
            _intent()))
    assembly = decision.assembly
    assert assembly.initial_step_index == 2
    founder = initial.unit(102)
    ferry = initial.unit(200)

    carried_founder = replace(
        founder,
        transported=True,
        transported_by=200,
        tile=201, x=9, y=4)
    loaded_ferry = replace(
        ferry, carrying=1)
    landing_action = _move(
        200, 202)
    carried = _revision(
        initial, 2,
        (
            carried_founder,
            loaded_ferry),
        (landing_action,),
        routes=(
            _route(
                200, 201, 300,
                202, 3,
                source_seq=2),))
    embark_done = (
        FounderTransportOperationAssembler
        .readout(
            assembly, carried, 2))
    landing_move = (
        FounderTransportOperationAssembler
        .readout(
            assembly, carried, 3))
    assert embark_done.disposition == (
        "step_complete")
    assert landing_move.disposition == (
        "reservable")
    assert landing_move.corridor.destination_tile == 300

    partner_switch = _revision(
        carried, 3,
        (
            replace(
                carried_founder,
                transported_by=999),
            loaded_ferry),
        ())
    switched = (
        FounderTransportOperationAssembler
        .readout(
            assembly,
            partner_switch, 3))
    assert switched.disposition == (
        "abandoned")
    assert switched.reason == (
        "founder-carrier-partner-mismatch")

    landed_ferry = replace(
        loaded_ferry,
        tile=300, x=12, y=6)
    at_landing = _revision(
        carried, 4,
        (
            replace(
                carried_founder,
                tile=300, x=12, y=6),
            landed_ferry),
        (
            _move(
                102, 301,
                transport_required=False),))
    ferry_leg_done = (
        FounderTransportOperationAssembler
        .readout(
            assembly, at_landing, 3))
    disembark = (
        FounderTransportOperationAssembler
        .readout(
            assembly, at_landing, 4))
    assert ferry_leg_done.disposition == (
        "step_complete")
    assert disembark.disposition == (
        "reservable")

    landed_founder = replace(
        founder,
        tile=301, x=13, y=6,
        transported=False,
        transported_by=0)
    settlement_move_action = (
        _move(102, 302))
    landed = _revision(
        at_landing, 5,
        (
            landed_founder,
            replace(
                landed_ferry,
                carrying=0)),
        (settlement_move_action,),
        routes=(
            _route(
                102, 301, 302,
                302, 1,
                source_seq=5),))
    assert (
        FounderTransportOperationAssembler
        .readout(
            assembly, landed, 4)
        .disposition
        == "step_complete")
    assert (
        FounderTransportOperationAssembler
        .readout(
            assembly, landed, 5)
        .disposition
        == "reservable")

    settlement_action = {
        "action_type":
            "unit_build_city",
        "actor_id": 102,
    }
    at_target = _revision(
        landed, 6,
        (
            replace(
                landed_founder,
                tile=302,
                x=14, y=6),
            replace(
                landed_ferry,
                carrying=0)),
        (settlement_action,))
    assert (
        FounderTransportOperationAssembler
        .readout(
            assembly, at_target, 5)
        .disposition
        == "step_complete")
    assert (
        FounderTransportOperationAssembler
        .readout(
            assembly, at_target, 6)
        .disposition
        == "reservable")

    city = CityState(
        city_id=900,
        owner=0,
        name="Landing",
        tile=302,
        x=14,
        y=6,
        size=1,
        production_kind=None,
        production_value=None,
        food_stock=0,
        shield_stock=0,
        surplus=(),
        production=(),
        buildability_available=False,
        buildable=())
    completed = _revision(
        at_target, 7,
        (
            replace(
                landed_ferry,
                carrying=0),),
        (),
        cities=(city,))
    final = (
        FounderTransportOperationAssembler
        .readout(
            assembly,
            completed, 6))
    assert final.disposition == (
        "completed")
    assert final.reason == (
        "settlement-created")


def test_lifecycle_reserves_commits_and_reestimates_the_next_exact_step():
    initial = _snapshot(
        embark=True)
    assembly = (
        FounderTransportOperationAssembler()
        .assemble(
            initial, _ruleset(),
            "ruleset-proof",
            _intent())
        .assembly)
    lifecycle = (
        FounderTransportOperationLifecycle(
            "proof", _ruleset()))

    registered = lifecycle.register(
        assembly, initial)
    committed = (
        lifecycle
        .commit_matching_action(
            initial,
            assembly.initial_readout
            .next_action,
            accepted=True))

    assert registered[0].state == (
        "reserved")
    assert registered[0].phase == (
        "embark")
    assert committed[0].disposition == (
        "step_committed")
    assert lifecycle.store.get(
        assembly.spec.operation_id
    ).progress.state == (
        OperationState.ACTIVE)
    assert not lifecycle.ledger.reservation(
        assembly.spec.operation_id
    ).active

    founder = replace(
        initial.unit(102),
        transported=True,
        transported_by=200,
        tile=201, x=9, y=4)
    ferry = replace(
        initial.unit(200),
        carrying=1)
    action = _move(
        200, 202)
    carried = _revision(
        initial, 2,
        (founder, ferry),
        (action,),
        routes=(
            _route(
                200, 201, 300,
                202, 3,
                source_seq=2),))

    updates = lifecycle.observe(
        carried)

    assert [
        row.disposition
        for row in updates
    ] == [
        "step_completed",
        "step_reestimated",
    ]
    assert updates[-1].phase == (
        "ferry_to_landing")
    assert updates[-1].next_action == (
        json.loads(
            carried
            .legal_action_json[0]))
    assert lifecycle.ledger.reservation(
        assembly.spec.operation_id
    ).active


def test_fdas_transport_adapter_projects_current_step_claims_and_binding():
    initial = _snapshot(embark=True)
    ruleset = _ruleset()
    assembly = (
        FounderTransportOperationAssembler()
        .assemble(initial, ruleset, "ruleset-proof", _intent())
        .assembly)
    lifecycle = FounderTransportOperationLifecycle(
        "fdas-projection-proof", ruleset)
    adapter = FdasFounderTransportProjectionAdapter(
        lifecycle, "ruleset-proof")

    registered = adapter.register(assembly, initial)
    operation_id = assembly.spec.operation_id
    binding = adapter.binding(operation_id)
    context = adapter.requirement_context(operation_id)

    assert registered[-1].state == "reserved"
    assert binding.action == assembly.initial_readout.next_action
    assert binding.action_key in initial.legal_action_json
    assert context.blocked_premises == ()
    assert GameResourceKind.TRANSPORT_SEAT in {
        value.resource.kind for value in context.resource_claims}
    revision = DependentAtomSpaceStore(
        domain_projector=OperationProjector(
            lifecycle.store, adapter.bindings,
            adapter.requirement_contexts)).build(initial)
    predicates = {value.key.predicate for value in revision.records}
    assert {
        "operation-current-action",
        "operation-current-action-legal",
        "operation-requirement-set",
        "operation-resource-claim",
        "resource-claim-resource",
    }.issubset(predicates)

    committed = adapter.commit_matching_action(
        initial, binding.action, accepted=True)
    assert committed[-1].disposition == "step_committed"
    assert adapter.binding(operation_id) is None
    assert dict(adapter.requirement_context(
        operation_id).blocked_premises) == {
            "phase:embark:current-precondition":
                "awaiting-authoritative-step-effect",
        }
    assert adapter.requirement_context(operation_id).resource_claims == ()


def test_fdas_transport_adapter_advances_and_rebinds_authoritatively():
    initial = _snapshot(embark=True)
    ruleset = _ruleset()
    assembly = (
        FounderTransportOperationAssembler()
        .assemble(initial, ruleset, "ruleset-proof", _intent())
        .assembly)
    lifecycle = FounderTransportOperationLifecycle(
        "fdas-rebind-proof", ruleset)
    adapter = FdasFounderTransportProjectionAdapter(
        lifecycle, "ruleset-proof")
    adapter.register(assembly, initial)
    adapter.commit_matching_action(
        initial, assembly.initial_readout.next_action, accepted=True)

    founder = replace(
        initial.unit(102), transported=True, transported_by=200,
        tile=201, x=9, y=4)
    ferry = replace(initial.unit(200), carrying=1)
    action = _move(200, 202)
    carried = _revision(
        initial, 2, (founder, ferry), (action,),
        routes=(_route(200, 201, 300, 202, 3, source_seq=2),))

    updates = adapter.observe(carried)
    operation_id = assembly.spec.operation_id
    record = lifecycle.store.get(operation_id)

    assert [value.disposition for value in updates] == [
        "step_completed", "step_reestimated"]
    assert record.progress.current_step_index == 3
    assert adapter.binding(operation_id).action == action
    assert adapter.requirement_context(operation_id).blocked_premises == ()
    revision = DependentAtomSpaceStore(
        domain_projector=OperationProjector(
            lifecycle.store, adapter.bindings,
            adapter.requirement_contexts)).build(carried)
    current_step = next(
        value for value in revision.records
        if value.key.predicate == "operation-current-step")
    assert current_step.key.arguments[1].entity_id == (
        record.spec.steps[3].step_id)


def test_lifecycle_fails_closed_on_stale_commit_and_releases_claims():
    initial = _snapshot(
        embark=True)
    assembly = (
        FounderTransportOperationAssembler()
        .assemble(
            initial, _ruleset(),
            "ruleset-proof",
            _intent())
        .assembly)
    lifecycle = (
        FounderTransportOperationLifecycle(
            "stale-proof",
            _ruleset()))
    lifecycle.register(
        assembly, initial)
    stale = _revision(
        initial, 2,
        initial.units,
        (
            assembly
            .initial_readout
            .next_action,))

    result = lifecycle.commit_matching_action(
        stale,
        assembly.initial_readout
        .next_action,
        accepted=True)

    assert result[0].disposition == (
        "failed")
    assert result[0].reason == (
        "transport-commit-revalidation-failed")
    assert lifecycle.store.get(
        assembly.spec.operation_id
    ).progress.state == (
        OperationState.FAILED)
    assert not lifecycle.ledger.reservation(
        assembly.spec.operation_id
    ).active


def test_lifecycle_blocks_and_repairs_only_after_new_grounded_route():
    initial = _snapshot(
        embark=True)
    assembly = (
        FounderTransportOperationAssembler()
        .assemble(
            initial, _ruleset(),
            "ruleset-proof",
            _intent())
        .assembly)
    lifecycle = (
        FounderTransportOperationLifecycle(
            "repair-proof",
            _ruleset()))
    lifecycle.register(
        assembly, initial)
    lifecycle.commit_matching_action(
        initial,
        assembly.initial_readout
        .next_action,
        accepted=True)
    founder = replace(
        initial.unit(102),
        transported=True,
        transported_by=200,
        tile=201, x=9, y=4)
    ferry = replace(
        initial.unit(200),
        carrying=1)
    blocked_snapshot = _revision(
        initial, 2,
        (founder, ferry), ())

    blocked = lifecycle.observe(
        blocked_snapshot)

    assert blocked[-1].disposition == (
        "blocked")
    assert blocked[-1].reason == (
        "ferry-landing-route-or-action-unavailable")
    assert lifecycle.store.get(
        assembly.spec.operation_id
    ).progress.state == (
        OperationState.BLOCKED)

    action = _move(
        200, 202)
    repaired_snapshot = _revision(
        blocked_snapshot, 3,
        (founder, ferry),
        (action,),
        routes=(
            _route(
                200, 201, 300,
                202, 3,
                source_seq=3),))
    repaired = lifecycle.observe(
        repaired_snapshot)

    assert repaired[-1].disposition == (
        "repaired")
    assert repaired[-1].next_action == (
        action)
    assert lifecycle.ledger.reservation(
        assembly.spec.operation_id
    ).active


def test_completion_releases_claims_and_fixed_horizon_retention_resolves():
    initial = _snapshot(
        embark=True)
    assembly = (
        FounderTransportOperationAssembler()
        .assemble(
            initial, _ruleset(),
            "ruleset-proof",
            _intent())
        .assembly)
    lifecycle = (
        FounderTransportOperationLifecycle(
            "completion-proof",
            _ruleset()))
    lifecycle.register(
        assembly, initial)
    operation_id = (
        assembly.spec.operation_id)
    # The retained completion fixture starts at embark (step 2). Advance the
    # four already-satisfied post-embark predicates to the settlement step.
    for index in range(4):
        lifecycle.store.advance_satisfied_step(
            operation_id,
            "predicate-{}".format(
                index),
            1)
    city = CityState(
        city_id=900,
        owner=0,
        name="Landing",
        tile=302,
        x=14,
        y=6,
        size=1,
        production_kind=None,
        production_value=None,
        food_stock=0,
        shield_stock=0,
        surplus=(),
        production=(),
        buildability_available=False,
        buildable=())
    completed = _revision(
        initial, 9,
        (
            initial.unit(200),),
        (),
        cities=(city,))

    updates = lifecycle.observe(
        completed)

    assert updates[-1].disposition == (
        "completed")
    assert lifecycle.store.get(
        operation_id
    ).progress.state == (
        OperationState.COMPLETED)
    assert not lifecycle.ledger.reservation(
        operation_id
    ).active
    retained = lifecycle.retention.observe(
        _with_turn(
            completed, 11))
    assert retained[0].retained
    assert retained[0].reason == (
        "city-retained-at-settlement")

    lost_tracker = (
        SettlementRetentionTracker(
            horizon_turns=2))
    lost_tracker.register_completion(
        assembly, completed)
    lost = lost_tracker.observe(
        _with_turn(
            replace(
                completed,
                cities=()),
            3))
    assert not lost[0].retained


def test_blocked_operation_adopts_only_grounded_margin_improving_replacement():
    initial = _snapshot()
    original = (
        FounderTransportOperationAssembler()
        .assemble(
            initial, _ruleset(),
            "ruleset-proof",
            _intent())
        .assembly)
    lifecycle = (
        FounderTransportOperationLifecycle(
            "bounded-repair-proof",
            _ruleset()))
    lifecycle.register(
        original, initial)
    operation_id = (
        original.spec.operation_id)
    lifecycle.store.transition(
        operation_id,
        OperationState.BLOCKED,
        initial.snapshot_id,
        initial.turn,
        reason=(
            "original-corridor-blocked"))
    lifecycle.ledger.release(
        operation_id,
        "original-corridor-blocked")

    founder = replace(
        initial.unit(102),
        tile=200, x=8, y=4)
    replacement_ferry = replace(
        initial.unit(200),
        unit_id=201,
        tile=202, x=10, y=4)
    embark = _move(
        102, 202, True)
    replacement_snapshot = (
        _revision(
            initial, 2,
            (
                founder,
                replacement_ferry),
            (embark,)))
    replacement_intent = replace(
        _intent(),
        ferry_unit_id=201,
        pickup_tile_id=202)

    repaired = lifecycle.repair_blocked(
        operation_id,
        replacement_snapshot,
        replacement_intent,
        "ruleset-proof")

    assert repaired.disposition == (
        "replaced")
    assert repaired.partner_switched
    assert lifecycle.store.get(
        operation_id
    ).progress.state == (
        OperationState.ABANDONED)
    replacement_record = (
        lifecycle.store.get(
            repaired
            .replacement_operation_id))
    assert replacement_record.progress.state == (
        OperationState.RESERVED)
    assert repaired.registration_updates[
        0].phase == "embark"
