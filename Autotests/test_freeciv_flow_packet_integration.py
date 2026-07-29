"""Stage-S4 continuous-eligibility/discrete-packet integration gates."""

import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.flow_control import (  # noqa: E402
    CandidateGrounding,
    FlowCandidateFactory,
    FlowNode,
    FlowNodeKind,
    FlowPacketIntegrator,
    FlowView,
)
from freeciv_agent.pressure import (  # noqa: E402
    CostVector,
    Operation,
    PacketBudget,
    PacketCost,
    RequirementSet,
    ResourceKind,
    TypedAdvantage,
)
from freeciv_agent.pressure.scheduler import (  # noqa: E402
    OperationScore,
)


def _view():
    nodes = tuple(
        FlowNode(
            local_id=index,
            stable_id="flow-op-{}".format(name),
            kind=FlowNodeKind.OPERATION,
            semantic_generation=4,
            topology_generation=8,
            context_digest="packet-context",
            clone_generation=0,
            source="packet-test",
            committable=True)
        for index, name in enumerate(("a", "b")))
    groundings = tuple(
        CandidateGrounding(
            snapshot_id="packet-snapshot",
            legal_action_digest="legal",
            action_digest="action-{}".format(name),
            semantic_epoch=4,
            topology_generation=8,
            actor_id=name,
            target_digest="target-{}".format(name),
            category="test",
            operation_node_id="flow-op-{}".format(name))
        for name in ("a", "b"))
    return FlowView(
        query_id="packet-query",
        snapshot_id="packet-snapshot",
        legal_action_digest="legal",
        semantic_epoch=4,
        topology_generation=8,
        context_digest="packet-context",
        clone_generation=0,
        nodes=nodes,
        edges=(),
        candidate_groundings=groundings)


def _operation(name, requirement_set_id=None, quanta=1):
    advantage = TypedAdvantage(
        goal_id="goal",
        target_id="atom-{}".format(name),
        mode="act",
        expected_relief=(
            10.0 if name == "a" else 1.0),
        relief_variance=0.1,
        information_gain=0.0,
        option_value=0.0,
        predicted_latency=1.0,
        predicted_resource_use=(("action", quanta),),
        estimator_id="packet-test")
    return Operation(
        operation_id="operation-{}".format(name),
        atom_id="atom-{}".format(name),
        mode="act",
        cost=CostVector(compute=1.0),
        packet_costs=(
            PacketCost(ResourceKind.ACTION, quanta),),
        requirement_set_id=requirement_set_id,
        typed_advantages=(advantage,))


def _score(operation, priority):
    return OperationScore(
        operation=operation,
        admissible=True,
        reason=None,
        priority=priority,
        value=priority,
        scalar_cost=1.0,
        conflict_penalty=0.0,
        goal_effects=())


def _candidates(view, operations, overlaps):
    factory = FlowCandidateFactory()
    return tuple(
        factory.build(
            view,
            "flow-op-{}".format(name),
            operation,
            overlap,
            bridge_diagnostics=(
                ("corrected_overlap", overlap),))
        for name, operation, overlap in zip(
            ("a", "b"), operations, overlaps))


def test_overlap_only_filters_location_typed_pf_selects_operation():
    view = _view()
    operations = (_operation("a"), _operation("b"))
    candidates = _candidates(
        view, operations, (0.2, 0.9))
    decision = FlowPacketIntegrator().integrate(
        view, candidates,
        (_score(operations[0], 10.0),
         _score(operations[1], 1.0)),
        (PacketBudget(ResourceKind.ACTION, 1),),
        revalidate=lambda operation, grounding: True)

    assert decision.packet_schedule.committed_operation_ids == (
        "operation-a",)
    assert decision.packet_schedule.conserved
    assert "overlap-location-readout-only" in (
        candidates[0].reason_codes)
    assert candidates[0].per_goal_expected_relief == (
        ("goal", 10.0),)


def test_incomplete_requirement_never_counts_as_action_progress():
    view = _view()
    requirement = RequirementSet(
        requirement_set_id="requirements-a",
        rule_id="rule-a",
        premise_ids=("premise-a",),
        role_ids=("role-a",),
        context_digest="packet-context")
    operations = (
        _operation("a", "requirements-a"),
        _operation("b"))
    candidates = _candidates(
        view, operations, (0.8, 0.0))
    decision = FlowPacketIntegrator().integrate(
        view, candidates,
        (_score(operations[0], 10.0),
         _score(operations[1], 1.0)),
        (PacketBudget(ResourceKind.ACTION, 1),),
        revalidate=lambda operation, grounding: True,
        requirement_sets=(requirement,),
        premise_packets={},
        reservation_ages={"operation-a": 3})

    assert decision.packet_schedule.committed_operation_ids == ()
    assert decision.diagnostics.incomplete_reservations == (
        "operation-a",)
    starvation = decision.diagnostics.packet_starvation[0]
    assert starvation.reason == "incomplete-requirement-set"
    assert starvation.requirement_set_id == "requirements-a"
    assert starvation.reservation_age == 3
    assert decision.diagnostics.stranded_mass == pytest.approx(0.8)


def test_exact_revalidation_returns_packets_and_tries_next_route():
    view = _view()
    operations = (_operation("a"), _operation("b"))
    candidates = _candidates(
        view, operations, (0.8, 0.8))
    decision = FlowPacketIntegrator().integrate(
        view, candidates,
        (_score(operations[0], 10.0),
         _score(operations[1], 1.0)),
        (PacketBudget(ResourceKind.ACTION, 1),),
        revalidate=lambda operation, grounding: (
            operation.operation_id != "operation-a"))

    assert decision.packet_schedule.committed_operation_ids == (
        "operation-b",)
    assert decision.packet_schedule.conserved
    returned = decision.packet_schedule.reservations[0]
    assert returned.operation_id == "operation-a"
    assert returned.state == "returned"
    assert returned.reason == "exact-revalidation-failed"
    assert decision.diagnostics.exact_revalidation_failures == (
        "operation-a",)
    assert decision.diagnostics.returned_mass == pytest.approx(0.8)


def test_relaxed_and_packet_feasible_values_report_integrality_gap():
    view = _view()
    operations = (_operation("a"), _operation("b"))
    candidates = _candidates(
        view, operations, (0.5, 0.5))
    decision = FlowPacketIntegrator().integrate(
        view, candidates,
        (_score(operations[0], 4.0),
         _score(operations[1], 2.0)),
        (PacketBudget(ResourceKind.ACTION, 1),),
        revalidate=lambda operation, grounding: True)

    assert (
        decision.diagnostics.relaxed_continuous_value
        == pytest.approx(6.0))
    assert (
        decision.diagnostics.packet_feasible_value
        == pytest.approx(4.0))
    assert decision.diagnostics.integrality_gap == pytest.approx(2.0)
    assert decision.diagnostics.stranded_mass == pytest.approx(0.5)


def test_insufficient_whole_packet_is_bounded_reservation():
    view = _view()
    operations = (_operation("a", quanta=2), _operation("b"))
    candidates = _candidates(
        view, operations, (0.7, 0.0))
    decision = FlowPacketIntegrator().integrate(
        view, candidates,
        (_score(operations[0], 4.0),
         _score(operations[1], 1.0)),
        (PacketBudget(ResourceKind.ACTION, 1),),
        revalidate=lambda operation, grounding: True)

    assert not decision.packet_schedule.committed_operation_ids
    assert decision.reservation_ledger.total_mass == pytest.approx(0.7)
    assert decision.reservation_ledger.entries[0].operation_id == (
        "operation-a")
    assert decision.diagnostics.packet_starvation[
        0].missing_resources == ("action",)


def test_stale_candidate_view_is_rejected_before_scheduling():
    view = _view()
    operations = (_operation("a"), _operation("b"))
    candidates = list(_candidates(
        view, operations, (0.8, 0.8)))
    stale = candidates[0].__class__(
        **dict(candidates[0].__dict__,
               topology_generation=9))
    candidates[0] = stale

    with pytest.raises(ValueError, match="stale"):
        FlowPacketIntegrator().integrate(
            view, candidates,
            (_score(operations[0], 4.0),
             _score(operations[1], 2.0)),
            (PacketBudget(ResourceKind.ACTION, 1),),
            revalidate=lambda operation, grounding: True)
