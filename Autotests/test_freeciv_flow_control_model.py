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
    FreeCivFactorGraphBuilder,
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


def test_builder_semantic_identity_ignores_transport_sequence():
    path = os.path.join(
        REPO, "benchmarks", "freeciv", "samples",
        "real_state_turn1.json")
    with open(path, encoding="utf-8") as stream:
        payload = json.load(stream)
    first_snapshot = ProxyStateDTO.parse(
        "semantic-identity", 1, payload).to_snapshot()
    second_snapshot = ProxyStateDTO.parse(
        "semantic-identity", 99, payload).to_snapshot()
    first_candidates = GroundedImpactPlanner({
        "pressure_enabled": False}).candidates(
            first_snapshot)
    second_candidates = GroundedImpactPlanner({
        "pressure_enabled": False}).candidates(
            second_snapshot)
    builder = FreeCivFactorGraphBuilder()
    first = builder.build(
        "semantic-query-1", first_snapshot,
        first_candidates,
        goal_ids=("expansion", "exploration"),
        goal_by_category={
            "city_founding": "expansion",
            "expansion_move": "expansion",
            "exploration_move": "exploration",
        },
        semantic_epoch=5,
        topology_generation=11,
        clone_generation=3)
    second = builder.build(
        "semantic-query-99", second_snapshot,
        second_candidates,
        goal_ids=("expansion", "exploration"),
        goal_by_category={
            "city_founding": "expansion",
            "expansion_move": "expansion",
            "exploration_move": "exploration",
        },
        semantic_epoch=8,
        topology_generation=19,
        clone_generation=4)

    assert first_snapshot.snapshot_id != (
        second_snapshot.snapshot_id)
    assert first.view.query_id != second.view.query_id
    assert tuple(
        row.stable_id for row in first.view.nodes
    ) == tuple(
        row.stable_id for row in second.view.nodes)
    assert tuple(
        row.stable_id for row in first.view.edges
    ) == tuple(
        row.stable_id for row in second.view.edges)
    assert first.view.probe_semantic_hash == (
        second.view.probe_semantic_hash)
    assert first.view.to_dict()["view_hash"] != (
        second.view.to_dict()["view_hash"])
    assert {
        row.snapshot_id
        for row in first.view.candidate_groundings
    } == {first_snapshot.snapshot_id}
    assert {
        row.snapshot_id
        for row in second.view.candidate_groundings
    } == {second_snapshot.snapshot_id}


def _deep_build(reverse=False, budget=None, per_category=64):
    snapshot, candidates = _fixture()
    if reverse:
        candidates = tuple(reversed(candidates))
    result = FreeCivFactorGraphBuilder(
        budget=budget,
        max_candidates_per_category=per_category).build(
            "deep-factor-test", snapshot, candidates,
            goal_ids=("expansion", "exploration"),
            goal_by_category={
                "city_founding": "expansion",
                "expansion_move": "expansion",
                "exploration_move": "exploration",
            },
            semantic_epoch=5,
            topology_generation=11,
            clone_generation=3)
    return snapshot, candidates, result


def test_candidate_factorization_preserves_premise_roles():
    _, _, result = _deep_build()
    founding = next(
        row for row in result.view.candidate_groundings
        if row.category == "city_founding")
    route = next(
        row for row in result.factorizations
        if row.operation_node_id
        == founding.operation_node_id)

    assert route.complete
    assert set(route.requirement_roles) >= {
        "actor_exists_and_is_available",
        "legal_action_is_still_advertised",
        "safety_and_provenance_guards",
        "target_or_destination_remains_valid",
    }
    roles = {
        result.view.node(node_id).semantic_role
        for node_id in route.factor_node_ids}
    assert set((
        "desired_outcome_factor",
        "effect_model_factor",
        "operation_requirement_set",
    )).issubset(roles)


def test_deep_factorization_has_distinct_forward_and_backward_routes():
    _, _, result = _deep_build()
    route = result.factorizations[0]
    route_nodes = frozenset(route.factor_node_ids) | {
        route.operation_node_id}
    forward = tuple(
        row for row in result.view.edges
        if row.kind in (
            FlowEdgeKind.FORWARD_TRUTH,
            FlowEdgeKind.PROBE_FORWARD)
        and (row.source_node_id in route_nodes
             or row.target_node_id in route_nodes))
    backward = tuple(
        row for row in result.view.edges
        if row.kind == FlowEdgeKind.BACKWARD_DEMAND
        and (row.source_node_id in route_nodes
             or row.target_node_id in route_nodes))

    assert forward
    assert backward
    assert all(
        not row.legality.probe_backward
        for row in forward)
    assert all(
        not row.legality.probe_forward
        for row in backward)
    assert {
        row.stable_id for row in forward
    }.isdisjoint({
        row.stable_id for row in backward
    })


def test_unknown_requirement_is_frontier_not_proposition_or_evidence():
    _, _, result = _deep_build()
    route = next(
        row for row in result.factorizations
        if "required_observation_or_simulation_result"
        in row.frontier_roles)
    frontier = next(
        result.view.node(node_id)
        for node_id in route.factor_node_ids
        if result.view.node(node_id).semantic_role
        == "required_observation_or_simulation_result")

    assert frontier.kind == FlowNodeKind.FRONTIER_STUB
    assert not frontier.evidence_mirror
    assert not frontier.committable


def test_deep_factorization_is_order_invariant_and_category_bounded():
    budget = FlowBuildBudget(
        max_nodes=1024, max_edges=4096,
        max_candidates=512, max_frontier_stubs=64)
    _, _, first = _deep_build(
        budget=budget, per_category=1)
    _, _, second = _deep_build(
        reverse=True, budget=budget,
        per_category=1)

    assert first.to_dict() == second.to_dict()
    assert first.budget_exhausted
    complete = [
        row for row in first.factorizations
        if row.complete]
    assert len(complete) == 3
    assert first.frontier_candidate_count == (
        len(first.view.candidate_groundings) - 3)


def test_operation_grounding_keeps_authoritative_commit_identity():
    snapshot, _, result = _deep_build()

    assert result.view.candidate_groundings
    for grounding in result.view.candidate_groundings:
        operation = result.view.node(
            grounding.operation_node_id)
        assert grounding.snapshot_id == snapshot.snapshot_id
        assert grounding.legal_action_digest == (
            snapshot.legal_actions_digest)
        assert grounding.topology_generation == 11
        assert operation.kind == FlowNodeKind.OPERATION
        assert operation.committable
        assert not operation.evidence_mirror
