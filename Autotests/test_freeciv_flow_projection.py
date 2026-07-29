"""Stage-S4 uncapacitated source-sink projection gates."""

import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.flow_control import (  # noqa: E402
    FlowEdge,
    FlowEdgeKind,
    FlowLegality,
    FlowNode,
    FlowNodeKind,
    FlowProcess,
    FlowView,
    ProjectionSolver,
    RequestedCurrentBuilder,
)


def _view(include_return=False, disconnected=False, long_chain=0):
    if long_chain:
        names = tuple(
            "node-{}".format(index)
            for index in range(long_chain))
    else:
        names = ("source", "target")
    nodes = tuple(
        FlowNode(
            local_id=index,
            stable_id=name,
            kind=(
                FlowNodeKind.FORWARD_BOUNDARY
                if index == 0
                else FlowNodeKind.OPERATION),
            semantic_generation=1,
            topology_generation=2,
            context_digest="projection-context",
            clone_generation=0,
            source="projection-test")
        for index, name in enumerate(names))
    edge_specs = []
    if not disconnected:
        for index in range(len(names) - 1):
            edge_specs.append((
                "edge-{}".format(index),
                names[index], names[index + 1],
                FlowEdgeKind.PROBE_FORWARD,
                FlowLegality(
                    probe_forward=True,
                    resource_accounting=True)))
    if include_return:
        edge_specs.append((
            "resource-return", names[-1], names[0],
            FlowEdgeKind.RESOURCE_RETURN,
            FlowLegality(resource_accounting=True)))
    edges = tuple(
        FlowEdge(
            local_id=index,
            stable_id=edge_id,
            source_node_id=source,
            target_node_id=target,
            kind=kind,
            legality=legality,
            semantic_generation=1,
            topology_generation=2,
            context_digest="projection-context",
            clone_generation=0,
            source="projection-test")
        for index, (
            edge_id, source, target,
            kind, legality) in enumerate(edge_specs))
    return FlowView(
        query_id="projection-query",
        snapshot_id="projection-snapshot",
        legal_action_digest="legal",
        semantic_epoch=1,
        topology_generation=2,
        context_digest="projection-context",
        clone_generation=0,
        nodes=nodes,
        edges=edges)


def _request(
        view, boundary, process=FlowProcess.PROBE_FORWARD,
        raw=None):
    raw = raw or dict(
        (edge.stable_id, 0.0) for edge in view.edges)
    return RequestedCurrentBuilder().build(
        view=view,
        commodity_id="goal:act:cpu",
        semantic_edge_values=raw,
        successful_probe_paths=(),
        boundary_vector=boundary,
        legal_process=process,
        semantic_weight=1.0,
        probe_weight=0.0,
        outer_packet_allocation=1.0)


def _divergence(view, current):
    result = dict(
        (node.stable_id, 0.0) for node in view.nodes)
    for edge, value in zip(view.edges, current):
        result[edge.source_node_id] += value
        result[edge.target_node_id] -= value
    return result


def test_projection_satisfies_source_sink_balance():
    view = _view(long_chain=4)
    boundary = {"node-0": 1.0, "node-3": -1.0}
    result = ProjectionSolver().solve(
        view, _request(view, boundary))

    assert result.healthy
    assert result.balance_residual <= 1e-9
    assert _divergence(
        view, result.feasible_current) == pytest.approx(
            {
                "node-0": 1.0,
                "node-1": 0.0,
                "node-2": 0.0,
                "node-3": -1.0,
            })


def test_projection_gauge_does_not_change_current():
    view = _view(long_chain=4)
    requested = _request(
        view, {"node-0": 1.0, "node-3": -1.0},
        raw={"edge-0": 4.0, "edge-1": -2.0, "edge-2": 0.5})
    first = ProjectionSolver(
        gauge_policy="first_node_zero").solve(
            view, requested)
    last = ProjectionSolver(
        gauge_policy="last_node_zero").solve(
            view, requested)

    assert first.healthy and last.healthy
    assert first.feasible_current == pytest.approx(
        last.feasible_current)
    assert first.congestion_dual != last.congestion_dual


def test_tree_source_sink_flow_is_nonzero():
    view = _view()
    result = ProjectionSolver().solve(
        view, _request(
            view, {"source": 1.0, "target": -1.0}))

    assert result.healthy
    assert result.feasible_current == pytest.approx((1.0,))


def test_virtual_return_lift_matches_source_sink_restriction():
    view = _view(include_return=True)
    accounting_lift = ProjectionSolver().solve(
        view,
        _request(
            view, {},
            FlowProcess.RESOURCE_ACCOUNTING,
            {"edge-0": 1.0, "resource-return": 1.0}))
    amount = accounting_lift.feasible_current[0]
    source_sink = ProjectionSolver().solve(
        view,
        _request(
            view, {"source": amount, "target": -amount},
            FlowProcess.RESOURCE_ACCOUNTING,
            {"edge-0": amount, "resource-return": 0.0}),
        mobility={"edge-0": 1.0, "resource-return": 0.0})

    assert source_sink.healthy and accounting_lift.healthy
    assert source_sink.feasible_current[0] == pytest.approx(
        accounting_lift.feasible_current[0])
    assert accounting_lift.feasible_current[0] == pytest.approx(
        accounting_lift.feasible_current[1])
    assert accounting_lift.feasible_current[0] > 0.0


def test_projection_failure_returns_unhealthy_not_candidate_authority():
    view = _view(disconnected=True)
    result = ProjectionSolver().solve(
        view, _request(
            view, {"source": 1.0, "target": -1.0}))

    assert not result.healthy
    assert result.health == "unhealthy:disconnected-boundary"
    assert not result.candidate_authority
    assert result.balance_residual == pytest.approx(1.0)


def test_mobility_zero_blocks_illegal_edge():
    view = _view(include_return=True)
    requested = _request(
        view, {"source": 1.0, "target": -1.0},
        FlowProcess.PROBE_FORWARD,
        {"edge-0": 1.0, "resource-return": 100.0})
    result = ProjectionSolver().solve(
        view, requested,
        mobility={"edge-0": 1.0, "resource-return": 100.0})

    assert result.healthy
    assert result.mobility == pytest.approx((1.0, 0.0))
    assert result.feasible_current == pytest.approx((1.0, 0.0))
    assert result.blocked_edge_ids == ("resource-return",)


def test_large_component_uses_diagonal_pcg():
    view = _view(long_chain=12)
    requested = _request(
        view, {"node-0": 1.0, "node-11": -1.0})
    result = ProjectionSolver(
        dense_fixture_limit=3).solve(view, requested)

    assert result.healthy
    assert result.solver in (
        "diagonal-pcg", "scipy-diagonal-pcg")
    assert result.iterations > 0
    assert result.feasible_current == pytest.approx(
        (1.0,) * 11)
