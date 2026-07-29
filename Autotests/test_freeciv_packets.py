"""Whole typed packet scheduling and accounting gates."""

import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    CostVector,
    GoalState,
    Operation,
    PacketBudget,
    PacketCost,
    PacketScheduler,
    PressureMagnitude,
    PressureScheduler,
    ResourceKind,
    SignedPressureVector,
    SmoothedScalarController,
    validate_packet_schedule,
)


def _operation(
        operation_id, costs, atom_id=None, threshold=1,
        requirement_set_id=None):
    return Operation(
        operation_id, atom_id or operation_id, "act",
        CostVector(compute=0.1), causal_kind="procedural",
        packet_costs=tuple(costs), packet_threshold=threshold,
        requirement_set_id=requirement_set_id)


def _scores(operations, pressure_by_atom=None):
    pressure_by_atom = pressure_by_atom or dict(
        (operation.atom_id, float(len(operations) - index))
        for index, operation in enumerate(operations))
    vector_by_atom = dict(
        (atom_id, SignedPressureVector(
            positive=PressureMagnitude(act=value)))
        for atom_id, value in pressure_by_atom.items())
    result = SimpleNamespace(
        goals=(GoalState("goal", "target"),),
        config=SimpleNamespace(
            cost_weights=(("compute", 1.0),),
            cost_epsilon=1e-9,
            information_gain_weight=0.10,
            coherence_weight=0.05,
            future_option_weight=0.05,
            softmax_temperature=0.15),
        artifact_hash="packet-test-pressure",
        pressure=lambda goal_id, atom_id: vector_by_atom[atom_id])
    return PressureScheduler().score_all(operations, result)


def test_fractional_eligibility_cannot_commit_operation():
    operation = _operation(
        "action", (PacketCost(ResourceKind.ACTION, 1),),
        threshold=2)
    scores = _scores((operation,))
    schedule = PacketScheduler().schedule(
        (operation,), scores,
        (PacketBudget(ResourceKind.ACTION, 1),),
        relaxed_allocations=(("action", 1.0),))

    assert schedule.committed_operation_ids == ()
    assert schedule.reservations[0].state == "pending"
    assert schedule.reservations[0].reason == (
        "insufficient-whole-packets")
    assert schedule.integrality_gap > 0.0


def test_nonpositive_relief_cannot_consume_packets():
    operation = _operation(
        "zero-value", (PacketCost(ResourceKind.ACTION, 1),))
    scores = _scores((operation,), {"zero-value": 0.0})
    schedule = PacketScheduler().schedule(
        (operation,), scores,
        (PacketBudget(ResourceKind.ACTION, 1),))

    assert schedule.committed_operation_ids == ()
    assert schedule.reservations == ()
    assert schedule.accounting()["action"]["stranded"] == 1


def test_multi_resource_operation_reserves_atomically():
    operation = _operation("combined", (
        PacketCost(ResourceKind.ACTION, 1),
        PacketCost(ResourceKind.CPU, 2),
    ))
    scores = _scores((operation,))
    schedule = PacketScheduler().schedule(
        (operation,), scores, (
            PacketBudget(ResourceKind.ACTION, 1),
            PacketBudget(ResourceKind.CPU, 1),
        ))

    assert schedule.committed_operation_ids == ()
    assert schedule.reservations[0].reserved == ()
    accounting = schedule.accounting()
    assert accounting["action"]["consumed"] == 0
    assert accounting["action"]["stranded"] == 1
    assert accounting["cpu"]["consumed"] == 0
    assert accounting["cpu"]["stranded"] == 1


def test_and_gate_requires_complete_prerequisite_packet_vector():
    from freeciv_agent.pressure import RequirementSet

    requirement = RequirementSet(
        "required", "rule", ("left", "right"),
        ("left-role", "right-role"), "context")
    operation = _operation(
        "gated", (PacketCost(ResourceKind.ACTION, 1),),
        requirement_set_id=requirement.requirement_set_id)
    scores = _scores((operation,))
    incomplete = PacketScheduler().schedule(
        (operation,), scores,
        (PacketBudget(ResourceKind.ACTION, 1),),
        requirement_sets=(requirement,),
        premise_packets={"left": 1})
    complete = PacketScheduler().schedule(
        (operation,), scores,
        (PacketBudget(ResourceKind.ACTION, 1),),
        requirement_sets=(requirement,),
        premise_packets={"left": 1, "right": 1})

    assert incomplete.committed_operation_ids == ()
    assert incomplete.reservations[0].reason == (
        "incomplete-requirement-set")
    assert complete.committed_operation_ids == ("gated",)


def test_or_routes_concentrate_packets_on_a_complete_candidate():
    primary = _operation(
        "primary", (PacketCost(ResourceKind.ACTION, 1),))
    alternative = _operation(
        "alternative", (PacketCost(ResourceKind.ACTION, 1),))
    operations = (alternative, primary)
    scores = _scores(
        operations, {"primary": 2.0, "alternative": 1.0})

    schedule = PacketScheduler().schedule(
        operations, scores,
        (PacketBudget(ResourceKind.ACTION, 1),))

    assert schedule.committed_operation_ids == ("primary",)
    states = dict(
        (row.operation_id, row.state)
        for row in schedule.reservations)
    assert states == {"alternative": "pending", "primary": "committed"}


def test_abandoned_reservation_returns_packets():
    operation = _operation(
        "abandoned", (PacketCost(ResourceKind.ACTION, 1),))
    schedule = PacketScheduler().schedule(
        (operation,), _scores((operation,)),
        (PacketBudget(ResourceKind.ACTION, 1),),
        abandoned_operation_ids=("abandoned",))

    assert schedule.committed_operation_ids == ()
    assert schedule.reservations[0].state == "returned"
    assert schedule.reservations[0].reserved == (
        PacketCost(ResourceKind.ACTION, 1),)
    assert schedule.accounting()["action"] == {
        "consumed": 0, "declared": 1, "stranded": 1}


def test_packet_accounting_is_conserved_across_resource_types():
    first = _operation("first", (
        PacketCost(ResourceKind.ACTION, 1),
        PacketCost(ResourceKind.CPU, 2),
    ))
    second = _operation(
        "second", (PacketCost(ResourceKind.CPU, 1),))
    schedule = PacketScheduler().schedule(
        (first, second), _scores((first, second)), (
            PacketBudget(ResourceKind.ACTION, 2),
            PacketBudget(ResourceKind.CPU, 4),
        ))

    assert schedule.conserved
    assert schedule.accounting() == {
        "action": {"consumed": 1, "declared": 2, "stranded": 1},
        "cpu": {"consumed": 3, "declared": 4, "stranded": 1},
    }


def test_packet_scheduler_is_deterministic_and_reports_integrality_gap():
    operations = (
        _operation("b", (PacketCost(ResourceKind.ACTION, 1),)),
        _operation("a", (PacketCost(ResourceKind.ACTION, 1),)),
    )
    scores = _scores(operations, {"a": 1.0, "b": 1.0})
    budgets = (PacketBudget(ResourceKind.ACTION, 1),)
    scheduler = PacketScheduler()

    first = scheduler.schedule(operations, scores, budgets)
    second = scheduler.schedule(
        tuple(reversed(operations)),
        tuple(reversed(scores)), budgets)

    assert first.to_dict() == second.to_dict()
    assert first.committed_operation_ids == ("a",)
    assert first.integrality_gap > 0.0
    assert first.scheduler_identity == (
        "pf-pln-packet-scheduler/2.0")


def test_strong_scalar_uses_the_same_packet_scheduler():
    operation = _operation(
        "shared", (PacketCost(ResourceKind.ACTION, 1),))
    schedule = SmoothedScalarController.schedule_packets(
        (operation,), _scores((operation,)),
        (PacketBudget(ResourceKind.ACTION, 1),))

    assert schedule.committed_operation_ids == ("shared",)
    assert schedule.scheduler_identity == (
        PacketScheduler.SOLVER_IDENTITY)
    assert validate_packet_schedule(schedule.to_dict())["valid"]
