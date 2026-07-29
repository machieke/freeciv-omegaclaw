"""Stage-S4 typed requested-current and path-closure gates."""

import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.flow_control import (  # noqa: E402
    ClosurePolicy,
    CycleClosurePlanner,
    FlowEdge,
    FlowEdgeKind,
    FlowLegality,
    FlowNode,
    FlowNodeKind,
    FlowProcess,
    FlowView,
    ProbePath,
    RequestedCurrentBuilder,
)


def _view():
    nodes = tuple(
        FlowNode(
            local_id=index,
            stable_id=stable_id,
            kind=kind,
            semantic_generation=1,
            topology_generation=4,
            context_digest="current-context",
            clone_generation=0,
            source="current-test")
        for index, (stable_id, kind) in enumerate((
            ("source", FlowNodeKind.FORWARD_BOUNDARY),
            ("target", FlowNodeKind.OPERATION),
        )))
    edge_specs = (
        (
            "forward", "source", "target",
            FlowEdgeKind.PROBE_FORWARD,
            FlowLegality(
                probe_forward=True,
                causal_planning=True)),
        (
            "backward", "target", "source",
            FlowEdgeKind.PROBE_BACKWARD,
            FlowLegality(probe_backward=True)),
        (
            "resource-return", "target", "source",
            FlowEdgeKind.RESOURCE_RETURN,
            FlowLegality(resource_accounting=True)),
        (
            "splice", "target", "source",
            FlowEdgeKind.SPLICE,
            FlowLegality(probe_forward=True)),
    )
    edges = tuple(
        FlowEdge(
            local_id=index,
            stable_id=stable_id,
            source_node_id=source,
            target_node_id=target,
            kind=kind,
            legality=legality,
            semantic_generation=1,
            topology_generation=4,
            context_digest="current-context",
            clone_generation=0,
            source="current-test")
        for index, (
            stable_id, source, target,
            kind, legality) in enumerate(edge_specs))
    return FlowView(
        query_id="current-query",
        snapshot_id="current-snapshot",
        legal_action_digest="legal",
        semantic_epoch=1,
        topology_generation=4,
        context_digest="current-context",
        clone_generation=0,
        nodes=nodes,
        edges=edges)


def _path(path_id="path", repeat_weight=1.0):
    return ProbePath(
        path_id=path_id,
        side="forward",
        start_node_id="source",
        node_ids=("source", "target"),
        edge_ids=("forward",),
        total_cost=1.0,
        met_opposite_frontier=True,
        meet_node_id="target",
        novelty=1.0,
        evidence_risk=0.0,
        reliability=1.0,
        behavior_log_probability=0.0,
        reference_log_probability=0.0,
        importance_weight=repeat_weight,
        topology_generation=4,
        rng_substream=0,
        sampling_stream="reference")


def test_requested_current_masks_illegal_edges_and_balances_boundary():
    view = _view()
    requested = RequestedCurrentBuilder().build(
        view,
        "goal:act:action",
        {
            "forward": 2.0,
            "backward": 50.0,
            "resource-return": 100.0,
            "splice": 100.0,
        },
        (_path(),),
        {"source": 1.0, "target": -1.0},
        FlowProcess.PROBE_FORWARD,
        semantic_weight=0.5,
        probe_weight=0.5)
    velocity = dict(zip(
        requested.edge_ids, requested.velocity))

    assert requested.legal_process == "probe_forward"
    assert velocity["forward"] > 0.0
    assert velocity["backward"] == 0.0
    assert velocity["resource-return"] == 0.0
    assert sum(
        value for _, value
        in requested.boundary_vector) == 0.0
    assert requested.current_hash


def test_probe_deposit_count_changes_variance_not_current_amplitude():
    builder = RequestedCurrentBuilder()
    view = _view()
    arguments = {
        "view": view,
        "commodity_id": "goal:act:cpu",
        "semantic_edge_values": {"forward": 1.0},
        "boundary_vector": {
            "source": 1.0, "target": -1.0},
        "legal_process": FlowProcess.PROBE_FORWARD,
        "semantic_weight": 0.5,
        "probe_weight": 0.5,
    }

    one = builder.build(
        successful_probe_paths=(_path(),),
        **arguments)
    many = builder.build(
        successful_probe_paths=tuple(
            _path("path-{}".format(index))
            for index in range(100)),
        **arguments)

    assert one.velocity == many.velocity
    assert one.turnover_rate == many.turnover_rate
    assert one.successful_probe_count == 1
    assert many.successful_probe_count == 100
    assert many.probe_variance_proxy < (
        one.probe_variance_proxy)


def test_semantic_and_probe_fields_are_unit_normalized_before_mix():
    requested = RequestedCurrentBuilder().build(
        _view(), "goal:observe:cpu",
        {"forward": 1000.0},
        (_path(),),
        {"source": 1.0, "target": -1.0},
        FlowProcess.PROBE_FORWARD,
        semantic_weight=0.7,
        probe_weight=0.3)

    assert requested.semantic_direction.norm == pytest.approx(1.0)
    assert requested.probe_direction.norm == pytest.approx(1.0)
    assert requested.semantic_weight + requested.probe_weight == (
        pytest.approx(1.0))


def test_tree_open_path_preserves_nonzero_source_sink_route():
    closure = CycleClosurePlanner().close(
        _view(), _path(),
        ClosurePolicy.PROJECTION_FALLBACK)

    assert closure.policy == ClosurePolicy.SOURCE_SINK_OPEN
    assert closure.fallback_used
    assert closure.nonzero_route_preserved
    assert closure.closure_edge_ids == ()
    assert dict(closure.boundary_vector) == {
        "source": 1.0, "target": -1.0}


def test_resource_return_closure_is_accounting_only():
    closure = CycleClosurePlanner().close(
        _view(), _path(),
        ClosurePolicy.RESERVOIR_RETURN,
        closure_edge_id="resource-return")

    assert closure.resource_accounting_only
    assert closure.boundary_vector == ()
    assert closure.closure_edge_ids == (
        "resource-return",)


def test_known_splice_closes_path_without_creating_evidence_edge():
    closure = CycleClosurePlanner().close(
        _view(), _path(),
        ClosurePolicy.KNOWN_SPLICE,
        closure_edge_id="splice")

    assert not closure.resource_accounting_only
    assert closure.closure_edge_ids == ("splice",)
    assert closure.boundary_vector == ()
    with pytest.raises(ValueError, match="known closure"):
        CycleClosurePlanner().close(
            _view(), _path(),
            ClosurePolicy.KNOWN_SPLICE,
            closure_edge_id="resource-return")


def test_probe_path_cannot_deposit_on_wrong_legal_process():
    with pytest.raises(ValueError, match="illegal edge"):
        RequestedCurrentBuilder().build(
            _view(), "goal:act:cpu",
            {"backward": 1.0},
            (_path(),),
            {"source": 1.0, "target": -1.0},
            FlowProcess.PROBE_BACKWARD)
