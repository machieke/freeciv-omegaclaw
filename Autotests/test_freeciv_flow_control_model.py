"""Stage-S3 query-local topology, identity, and legality gates."""

import json
import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.flow_control import (  # noqa: E402
    FlowBuildBudget,
    FlowEdge,
    FlowEdgeKind,
    FlowLegality,
    FlowNode,
    FlowNodeKind,
    FlowProcess,
    FlowTopologyIndex,
    QueryLocalFlowBuilder,
)
from freeciv_agent.planning import GroundedImpactPlanner  # noqa: E402
from freeciv_agent.planning.impact import ImpactCandidate  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


def _fixture():
    path = os.path.join(
        REPO, "benchmarks", "freeciv", "samples",
        "real_state_turn1.json")
    with open(path, encoding="utf-8") as stream:
        snapshot = ProxyStateDTO.parse(
            "flow-control-s3", 1,
            json.load(stream)).to_snapshot()
    candidates = GroundedImpactPlanner({
        "pressure_enabled": False}).candidates(snapshot)
    return snapshot, candidates


def _build(topology_generation=1, budget=None, reverse=False):
    snapshot, candidates = _fixture()
    if reverse:
        candidates = tuple(reversed(candidates))
    result = QueryLocalFlowBuilder(budget).build(
        "flow-control-test", snapshot, candidates,
        goal_ids=("expansion",),
        goal_by_category={"city_founding": "expansion"},
        semantic_epoch=4,
        topology_generation=topology_generation,
        clone_generation=2)
    return snapshot, candidates, result


def test_flow_builder_only_materializes_authoritative_legal_actions():
    snapshot, candidates = _fixture()
    invalid = ImpactCandidate(
        action={
            "action_id": 999999,
            "action_type": "unit_build_city",
            "actor_id": 999999,
        },
        category="city_founding",
        utility=9999.0,
        rationale="intentionally absent from server legal actions")
    before = snapshot.event_payload()

    result = QueryLocalFlowBuilder().build(
        "authoritative-only", snapshot,
        candidates + (invalid,),
        goal_ids=("expansion",),
        goal_by_category={"city_founding": "expansion"},
        semantic_epoch=1, topology_generation=3)

    assert snapshot.event_payload() == before
    assert result.legal_candidate_count == len(candidates)
    assert result.materialized_candidate_count == len(candidates)
    assert all(
        grounding.committable
        for grounding in result.view.candidate_groundings)
    assert {
        row.reason for row in result.rejections
    } == {"not_authoritative_legal_action"}
    assert invalid.action_key not in snapshot.legal_action_json


def test_process_legalities_are_explicit_and_directionally_distinct():
    _, _, result = _build()
    index = FlowTopologyIndex(result.view)
    operation_id = result.view.candidate_groundings[0].operation_node_id
    incoming = index.incoming(operation_id)
    invoke = next(
        row for row in incoming
        if row.kind == FlowEdgeKind.OPERATION_INVOKE)

    assert invoke.legality.allows(FlowProcess.PROBE_FORWARD)
    assert invoke.legality.allows(
        FlowProcess.OPERATION_INVOCATION)
    assert not invoke.legality.allows(
        FlowProcess.PROBE_BACKWARD)
    assert not invoke.legality.allows(
        FlowProcess.FORWARD_TRUTH)

    demand_edges = tuple(
        row for row in result.view.edges
        if row.kind == FlowEdgeKind.BACKWARD_DEMAND)
    assert demand_edges
    assert all(
        row.legality.allows(FlowProcess.PROBE_BACKWARD)
        and not row.legality.allows(FlowProcess.PROBE_FORWARD)
        and not row.legality.allows(FlowProcess.FORWARD_TRUTH)
        for row in demand_edges)


def test_resource_return_edge_cannot_become_proof_or_probe_path():
    common = {
        "local_id": 0,
        "stable_id": "edge:return",
        "source_node_id": "source",
        "target_node_id": "target",
        "kind": FlowEdgeKind.RESOURCE_RETURN,
        "semantic_generation": 1,
        "topology_generation": 1,
        "context_digest": "context",
        "clone_generation": 0,
        "source": "test",
    }

    edge = FlowEdge(
        legality=FlowLegality(resource_accounting=True),
        **common)

    assert edge.legality.enabled_processes == (
        FlowProcess.RESOURCE_ACCOUNTING.value,)
    with pytest.raises(ValueError, match="resource-return"):
        FlowEdge(
            legality=FlowLegality(
                resource_accounting=True,
                forward_truth=True),
            **common)


def test_local_handle_is_rejected_after_topology_generation_change():
    _, _, first = _build(topology_generation=7)
    _, _, second = _build(topology_generation=8)
    stable_id = first.view.nodes[0].stable_id
    handle = first.view.local_handle(stable_id)

    assert first.view.resolve(handle).stable_id == stable_id
    with pytest.raises(ValueError, match="stale local handle"):
        second.view.resolve(handle)


def test_durable_view_artifact_omits_ephemeral_local_ids():
    _, _, result = _build()

    artifact = result.view.to_dict()

    assert artifact["view_hash"]
    assert artifact["nodes"]
    assert artifact["edges"]
    assert all("local_id" not in row for row in artifact["nodes"])
    assert all("local_id" not in row for row in artifact["edges"])


def test_stage_s3_reservoir_and_shard_nodes_are_schema_only():
    common = {
        "local_id": 0,
        "stable_id": "inactive",
        "semantic_generation": 1,
        "topology_generation": 1,
        "context_digest": "context",
        "clone_generation": 0,
        "source": "test",
    }

    with pytest.raises(ValueError, match="inactive in Stage S3"):
        FlowNode(
            kind=FlowNodeKind.RESERVOIR,
            active=True,
            **common)
    node = FlowNode(
        kind=FlowNodeKind.SHARD_PORTAL,
        active=False,
        **common)
    assert not node.active


def test_materialization_budget_is_deterministic_and_leaves_frontier_stub():
    budget = FlowBuildBudget(
        max_nodes=6, max_edges=8,
        max_candidates=3, max_frontier_stubs=1)
    _, _, first = _build(budget=budget)
    _, _, reversed_result = _build(
        budget=budget, reverse=True)

    assert first.budget_exhausted
    assert first.materialized_candidate_count == 3
    assert len(first.view.frontier_stub_ids) == 1
    assert first.to_dict() == reversed_result.to_dict()
    stub = first.view.node(first.view.frontier_stub_ids[0])
    assert stub.kind == FlowNodeKind.FRONTIER_STUB
    assert stub.provenance_ids == ()
