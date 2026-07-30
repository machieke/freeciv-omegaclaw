"""Production enabling assembly, reservation, and observed completion."""

import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    ImpactCandidate,
    OperationState,
    ProductionEnablingIntent,
    ProductionEnablingOperationAssembler,
    ProductionOperationLifecycle,
)
from freeciv_agent.planning.domain_models import (  # noqa: E402
    DomainEstimateRequest,
    EstimateValidity,
    GroundedProductionTransitionModel,
)
from freeciv_agent.pressure import (  # noqa: E402
    ClaimHardness,
    GameResourceKind,
)


def _rule(
        name="Riflemen",
        target_kind="unit",
        cost=50,
        gold_upkeep=1):
    return SimpleNamespace(
        target_kind=target_kind,
        display_name=name,
        rule_name=name,
        rule_id="rule:{}".format(name),
        quantitative={
            "build_cost": {
                "value": cost,
            },
            "happy_cost": {
                "value": 0,
            },
            "pop_cost": {
                "value": 0,
            },
            "uk_food": {
                "value": (
                    1 if target_kind
                    == "unit" else 0),
            },
            "uk_gold": {
                "value": gold_upkeep,
            },
            "uk_shield": {
                "value": (
                    1 if target_kind
                    == "unit" else 0),
            },
            "upkeep": {
                "value": (
                    1 if target_kind
                    != "unit" else 0),
            },
        },
        traits={
            "class": {
                "values": (
                    ["Land"]
                    if target_kind
                    == "unit" else []),
            },
            "flags": {
                "values": [],
            },
            "roles": {
                "values": (
                    ["DefendGood"]
                    if target_kind
                    == "unit" else []),
            },
        })


def _intent(
        deadline=100,
        target_name="Riflemen",
        production_kind=6,
        production_value=10,
        operation_type="BUILD_DEFENDER",
        emergency=True):
    return ProductionEnablingIntent(
        operation_type=operation_type,
        city_id=103,
        production_kind=(
            production_kind),
        production_value=(
            production_value),
        target_name=target_name,
        downstream_operation_id=(
            "defense-operation:city:103"),
        completion_deadline_turn=(
            deadline),
        scheduling_bid=4.0,
        emergency=emergency)


def _action(intent):
    return intent.action()


def _unit(
        unit_id, target_name,
        homecity=103):
    return SimpleNamespace(
        unit_id=unit_id,
        unit_type=target_name,
        homecity=homecity,
        moves_left=3,
        carrying=None)


def _building(
        improvement_id, name):
    return SimpleNamespace(
        improvement_id=(
            improvement_id),
        name=name)


def _snapshot(
        intent, turn=72,
        current_kind=3,
        current_value=14,
        stock=30, rate=2,
        units=(), buildings=(),
        advertise=True,
        snapshot_suffix="a"):
    action = _action(intent)
    option_kind = (
        "unit"
        if intent.production_kind
        == 6 else "improvement")
    city = SimpleNamespace(
        city_id=103,
        owner=0,
        name="Roma",
        production_kind=current_kind,
        production_value=current_value,
        shield_stock=stock,
        surplus=(
            3, rate, 4, 3, 0, 2),
        buildability_available=True,
        buildable=((
            option_kind,
            intent.production_value,
            intent.target_name),),
        buildings=tuple(buildings))
    actions = (
        (canonical_json_bytes(
            action).decode("utf-8"),)
        if advertise else ())
    return SimpleNamespace(
        player_id=0,
        turn=turn,
        snapshot_id=(
            "snapshot:{}:{}".format(
                turn, snapshot_suffix)),
        legal_actions_digest=(
            "legal:{}:{}".format(
                turn, snapshot_suffix)),
        legal_action_json=actions,
        units=tuple(units),
        cities=(city,),
        economy=SimpleNamespace(
            gold=200),
        research=SimpleNamespace(
            available=False),
        city=lambda city_id: (
            city if city_id == 103
            else None))


def _estimate(
        snapshot, intent,
        ruleset=None):
    action = intent.action()
    ruleset = ruleset or (
        SimpleNamespace(
            rules=(_rule(
                intent.target_name,
                "unit"
                if intent
                .production_kind == 6
                else "building"),)))
    request = DomainEstimateRequest(
        request_id="e" * 64,
        snapshot=snapshot,
        ruleset_ir=ruleset,
        legal_action=action,
        candidate=ImpactCandidate(
            action,
            "production_defense",
            9999.0,
            "candidate utility is not model input"),
        goal_losses=((
            "pf-impact:defense",
            3.0),),
        operation_context=None,
        validity=EstimateValidity(
            snapshot.snapshot_id,
            snapshot
            .legal_actions_digest,
            "ruleset", snapshot.turn,
            snapshot.turn),
        horizon_turn=(
            intent
            .completion_deadline_turn))
    return (
        GroundedProductionTransitionModel()
        .estimate(request))


def _assembly(snapshot, intent):
    return (
        ProductionEnablingOperationAssembler
        .assemble(
            snapshot, intent,
            _estimate(
                snapshot, intent),
            ("pf-impact:defense",),
            "ruleset"))


def test_switch_assembly_has_hard_now_and_conditional_future_claims():
    intent = _intent()
    snapshot = _snapshot(
        intent)
    assembly = _assembly(
        snapshot, intent)

    assert assembly is not None
    assert assembly.initial_step_index == 0
    assert len(
        assembly.spec.steps) == 2
    assert assembly.spec.steps[
        0].action_type == (
            "city_production")
    assert assembly.spec.steps[
        1].action_type == (
            "observe_production_completion")
    assert assembly.spec.target_ref == (
        intent.target_ref)
    assert assembly.intent.downstream_operation_id == (
        "defense-operation:city:103")
    hard = tuple(
        row for row in
        assembly.resource_request.claims
        if row.hardness
        == ClaimHardness.HARD_CURRENT)
    future = tuple(
        row for row in
        assembly.resource_request.claims
        if row.hardness
        == ClaimHardness.CONDITIONAL_FUTURE)
    assert {
        row.resource.kind
        for row in hard
    } == {
        GameResourceKind
        .CITY_PRODUCTION_SLOT,
        GameResourceKind
        .ACTION_BUDGET,
    }
    assert {
        row.resource.kind
        for row in future
    } == {
        GameResourceKind
        .CITY_PRODUCTION_SLOT,
        GameResourceKind.TREASURY,
    }
    assert not assembly.model_artifact[
        "availability"][
            "unit_under_construction_is_participant"]


def test_emergency_assembly_requires_guaranteed_deadline_fit():
    intent = _intent(
        deadline=80)
    snapshot = _snapshot(
        intent)

    assembly = _assembly(
        snapshot, intent)

    assert assembly is None


def test_already_selected_queue_starts_at_observation_step():
    intent = _intent()
    snapshot = _snapshot(
        intent,
        current_kind=6,
        current_value=10)
    assembly = _assembly(
        snapshot, intent)
    lifecycle = (
        ProductionOperationLifecycle(
            "already-selected"))

    update = lifecycle.register(
        assembly, snapshot)[0]
    record = lifecycle.store.get(
        assembly.spec.operation_id)

    assert assembly.initial_step_index == 1
    assert update.disposition == (
        "waiting")
    assert update.next_action is None
    assert record.progress.state == (
        OperationState.ACTIVE)
    assert record.progress.current_step_index == 1


def test_queue_commit_then_new_unit_identity_completes_dependency():
    intent = _intent()
    before = _snapshot(
        intent)
    assembly = _assembly(
        before, intent)
    lifecycle = (
        ProductionOperationLifecycle(
            "unit-completion"))

    registered = lifecycle.register(
        assembly, before)[0]
    committed = lifecycle.commit_matching_action(
        before, intent.action(),
        accepted=True)[0]
    queued = _snapshot(
        intent, turn=73,
        current_kind=6,
        current_value=10,
        snapshot_suffix="queued")
    waiting = lifecycle.observe(
        queued)[0]
    completed_snapshot = _snapshot(
        intent, turn=74,
        current_kind=6,
        current_value=10,
        units=(
            _unit(
                501, "Riflemen"),),
        snapshot_suffix="complete")
    completed = lifecycle.observe(
        completed_snapshot)[0]

    assert registered.disposition == (
        "reserved")
    assert committed.disposition == (
        "step_committed")
    assert waiting.disposition == (
        "waiting")
    assert waiting.step_index == 1
    assert waiting.product_ref is None
    assert completed.disposition == (
        "completed")
    assert completed.product_ref == (
        "unit:501")
    assert completed.downstream_ready
    assert completed.downstream_operation_id == (
        intent
        .downstream_operation_id)
    assert lifecycle.store.get(
        assembly.spec.operation_id
    ).progress.state == (
        OperationState.COMPLETED)


def test_accepted_queue_action_must_appear_in_next_snapshot():
    intent = _intent()
    before = _snapshot(
        intent)
    assembly = _assembly(
        before, intent)
    lifecycle = (
        ProductionOperationLifecycle(
            "queue-no-effect"))
    lifecycle.register(
        assembly, before)
    lifecycle.commit_matching_action(
        before, intent.action(),
        accepted=True)
    no_effect = _snapshot(
        intent, turn=73,
        current_kind=3,
        current_value=14,
        advertise=False,
        snapshot_suffix="no-effect")

    update = lifecycle.observe(
        no_effect)[0]

    assert update.disposition == (
        "blocked")
    assert update.reason == (
        "accepted-queue-action-not-observed")


def test_stalled_production_blocks_and_recovers_without_completion():
    intent = _intent(
        emergency=False)
    initial = _snapshot(
        intent,
        current_kind=6,
        current_value=10,
        rate=2)
    assembly = _assembly(
        initial, intent)
    lifecycle = (
        ProductionOperationLifecycle(
            "stall-repair"))
    lifecycle.register(
        assembly, initial)
    stalled = _snapshot(
        intent, turn=73,
        current_kind=6,
        current_value=10,
        stock=30, rate=0,
        snapshot_suffix="stalled")
    blocked = lifecycle.observe(
        stalled)[0]
    recovered = _snapshot(
        intent, turn=74,
        current_kind=6,
        current_value=10,
        stock=32, rate=2,
        snapshot_suffix="recovered")
    repaired = lifecycle.observe(
        recovered)[0]

    assert blocked.disposition == (
        "blocked")
    assert blocked.reason == (
        "production-shield-output-stalled")
    assert repaired.disposition == (
        "repaired")
    assert not repaired.downstream_ready


def test_building_completion_requires_new_authoritative_building():
    intent = _intent(
        target_name="Library",
        production_kind=3,
        production_value=17,
        operation_type=(
            "BUILD_RESEARCH_ENABLER"),
        emergency=False)
    initial = _snapshot(
        intent,
        current_kind=3,
        current_value=17,
        buildings=())
    assembly = _assembly(
        initial, intent)
    lifecycle = (
        ProductionOperationLifecycle(
            "building-completion"))
    lifecycle.register(
        assembly, initial)
    later = _snapshot(
        intent, turn=80,
        current_kind=3,
        current_value=17,
        buildings=(
            _building(
                17, "Library"),),
        snapshot_suffix="library")

    update = lifecycle.observe(
        later)[0]

    assert update.disposition == (
        "completed")
    assert update.product_ref == (
        "building:17")
    assert update.downstream_ready
