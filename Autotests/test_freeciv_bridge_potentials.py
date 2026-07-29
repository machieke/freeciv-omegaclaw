"""Stage-S3 forward/backward potential and bridge-geometry gates."""

import math
import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.flow_control import (  # noqa: E402
    CorrectedProbeEstimator,
    DeterministicMessagePotentialEstimator,
    FlowEdge,
    FlowEdgeKind,
    FlowLegality,
    FlowNode,
    FlowNodeKind,
    FlowView,
    MonteCarloMeetPotentialEstimator,
    PotentialBudget,
    PotentialEstimate,
    ProbeConfig,
    ProbeNodeFeatures,
    ShortestMeetPotentialEstimator,
)


def _view(node_rows, edge_rows, generation=1):
    nodes = tuple(
        FlowNode(
            local_id=index,
            stable_id=stable_id,
            kind=kind,
            semantic_generation=1,
            topology_generation=generation,
            context_digest="bridge-context",
            clone_generation=0,
            source="bridge-test",
            provenance_ids=provenance)
        for index, (stable_id, kind, provenance)
        in enumerate(sorted(node_rows)))
    edges = tuple(
        FlowEdge(
            local_id=index,
            stable_id=stable_id,
            source_node_id=source,
            target_node_id=target,
            kind=kind,
            legality=legality,
            semantic_generation=1,
            topology_generation=generation,
            context_digest="bridge-context",
            clone_generation=0,
            source="bridge-test",
            control_weight=weight)
        for index, (
            stable_id, source, target,
            kind, legality, weight)
        in enumerate(sorted(edge_rows)))
    return FlowView(
        query_id="bridge-query",
        snapshot_id="bridge-snapshot",
        legal_action_digest="legal-digest",
        semantic_epoch=1,
        topology_generation=generation,
        context_digest="bridge-context",
        clone_generation=0,
        nodes=nodes,
        edges=edges)


def _bridge_fixture():
    nodes = (
        ("forward", FlowNodeKind.FORWARD_BOUNDARY, ("snapshot",)),
        ("goal", FlowNodeKind.BACKWARD_BOUNDARY, ("goal-a",)),
        ("bridge", FlowNodeKind.PROPOSITION, ()),
        ("reachable-irrelevant", FlowNodeKind.PROPOSITION, ()),
        ("useful-unreachable", FlowNodeKind.PROPOSITION, ()),
    )
    edges = (
        (
            "f-bridge", "forward", "bridge",
            FlowEdgeKind.PROBE_FORWARD,
            FlowLegality(probe_forward=True), 1.0),
        (
            "f-irrelevant", "forward", "reachable-irrelevant",
            FlowEdgeKind.PROBE_FORWARD,
            FlowLegality(probe_forward=True), 1.0),
        (
            "g-bridge", "goal", "bridge",
            FlowEdgeKind.PROBE_BACKWARD,
            FlowLegality(probe_backward=True), 1.0),
        (
            "g-unreachable", "goal", "useful-unreachable",
            FlowEdgeKind.PROBE_BACKWARD,
            FlowLegality(probe_backward=True), 1.0),
    )
    return _view(nodes, edges)


def _by_node(estimates):
    return dict((row.node_id, row) for row in estimates)


@pytest.mark.parametrize("estimator", (
    DeterministicMessagePotentialEstimator(),
    ShortestMeetPotentialEstimator(),
))
def test_bridge_separates_meet_from_one_sided_corridors(estimator):
    estimates = estimator.estimate(
        _bridge_fixture(), ("goal-a",),
        PotentialBudget(max_iterations=16))
    rows = _by_node(estimates)

    assert rows["bridge"].forward_factor > (
        rows["useful-unreachable"].forward_factor)
    assert rows["bridge"].backward_factor > (
        rows["reachable-irrelevant"].backward_factor)
    assert rows["bridge"].bridge_factor > (
        rows["useful-unreachable"].bridge_factor)
    assert rows["bridge"].bridge_factor > (
        rows["reachable-irrelevant"].bridge_factor)
    assert rows["bridge"].bridge_height == pytest.approx(
        math.log(rows["bridge"].forward_factor)
        + math.log(rows["bridge"].backward_factor))


def test_deterministic_messages_preserve_and_coalition_bottleneck():
    nodes = (
        ("forward", FlowNodeKind.FORWARD_BOUNDARY, ("snapshot",)),
        ("goal", FlowNodeKind.BACKWARD_BOUNDARY, ("goal-a",)),
        ("premise-a", FlowNodeKind.PROPOSITION, ()),
        ("premise-b", FlowNodeKind.FRONTIER_STUB, ()),
        ("requirements", FlowNodeKind.REQUIREMENT_SET, ()),
        ("operation", FlowNodeKind.OPERATION, ()),
    )
    edges = (
        (
            "f-a", "forward", "premise-a",
            FlowEdgeKind.PROBE_FORWARD,
            FlowLegality(probe_forward=True), 1.0),
        (
            "f-a-req", "premise-a", "requirements",
            FlowEdgeKind.FORWARD_TRUTH,
            FlowLegality(
                forward_truth=True, probe_forward=True), 1.0),
        (
            "f-b-req", "premise-b", "requirements",
            FlowEdgeKind.FORWARD_TRUTH,
            FlowLegality(
                forward_truth=True, probe_forward=True), 1.0),
        (
            "f-req-op", "requirements", "operation",
            FlowEdgeKind.PROBE_FORWARD,
            FlowLegality(probe_forward=True), 1.0),
        (
            "g-goal-op", "goal", "operation",
            FlowEdgeKind.BACKWARD_DEMAND,
            FlowLegality(probe_backward=True), 1.0),
        (
            "g-op-req", "operation", "requirements",
            FlowEdgeKind.BACKWARD_DEMAND,
            FlowLegality(
                backward_demand=True,
                probe_backward=True), 1.0),
        (
            "g-req-a", "requirements", "premise-a",
            FlowEdgeKind.BACKWARD_DEMAND,
            FlowLegality(
                backward_demand=True,
                probe_backward=True), 1.0),
        (
            "g-req-b", "requirements", "premise-b",
            FlowEdgeKind.BACKWARD_DEMAND,
            FlowLegality(
                backward_demand=True,
                probe_backward=True,
                expansion=True), 1.0),
    )
    budget = PotentialBudget(
        max_iterations=16, minimum_factor=1e-9)

    rows = _by_node(
        DeterministicMessagePotentialEstimator().estimate(
            _view(nodes, edges), ("goal-a",), budget))

    assert rows["premise-a"].forward_factor > 0.5
    assert rows["premise-b"].forward_factor == (
        budget.minimum_factor)
    assert rows["requirements"].forward_factor <= 1e-8
    assert rows["operation"].forward_factor <= 1e-8
    assert rows["premise-b"].backward_factor > 0.5


def test_monte_carlo_potentials_are_fixed_seed_replayable_and_uncertain():
    estimator = MonteCarloMeetPotentialEstimator(seed=43)
    budget = PotentialBudget(
        max_probe_steps=4, sample_count=256)
    view = _bridge_fixture()

    first = estimator.estimate(
        view, ("goal-a",), budget)
    second = estimator.estimate(
        view, ("goal-a",), budget)
    rows = _by_node(first)

    assert first == second
    assert rows["bridge"].effective_sample_size == 256.0
    assert rows["bridge"].clipped_weight_fraction == 0.0
    assert rows["bridge"].forward_uncertainty > 0.0
    assert rows["bridge"].process_semantics == (
        "fixed-reference-process")
    assert rows["bridge"].bridge_factor > (
        rows["reachable-irrelevant"].bridge_factor)


def test_potential_estimate_rejects_inconsistent_log_geometry():
    with pytest.raises(ValueError, match="log forward"):
        PotentialEstimate(
            goal_id="goal",
            node_id="node",
            forward_factor=0.5,
            backward_factor=0.5,
            log_forward=0.0,
            log_backward=math.log(0.5),
            bridge_height=math.log(0.5),
            forward_uncertainty=0.0,
            backward_uncertainty=0.0,
            estimator_policy="test",
            effective_sample_size=None,
            clipped_weight_fraction=None,
            estimator_id="test/1.0",
            process_semantics="fixed-reference-process",
            topology_generation=1)


def test_probe_records_behavior_reference_likelihood_and_exact_ess():
    config = ProbeConfig(
        mode="importance", path_count=256,
        max_steps=2, temperature=1.0,
        maximum_importance_weight=2.0,
        minimum_ess_fraction=0.99,
        maximum_clipped_fraction=1.0,
        minimum_path_diversity=0.0,
        seed=17)
    batch = CorrectedProbeEstimator(config).run(
        _bridge_fixture(), "forward",
        ("forward",), ("bridge",),
        node_features=(
            ProbeNodeFeatures(
                "bridge", local_advantage=2.0),
            ProbeNodeFeatures(
                "reachable-irrelevant",
                local_advantage=0.0),
        ))
    weights = tuple(
        row.importance_weight for row in batch.paths)
    expected_ess = (
        sum(weights) ** 2
        / sum(value ** 2 for value in weights))

    assert batch.health.effective_sample_size == pytest.approx(
        expected_ess)
    assert batch.health.effective_sample_fraction < 0.99
    assert not batch.health.healthy
    assert "low_effective_sample_size" in (
        batch.health.reasons)
    assert batch.health.recommended_fallback == (
        "deterministic_messages")
    for path in batch.paths:
        raw = math.exp(
            path.reference_log_probability
            - path.behavior_log_probability)
        assert path.importance_weight == pytest.approx(
            min(raw, config.maximum_importance_weight))


def test_backward_probe_cannot_traverse_forward_only_edge():
    batch = CorrectedProbeEstimator(ProbeConfig(
        mode="two_stream", path_count=32,
        max_steps=4, reference_fraction=0.25,
        minimum_path_diversity=0.0)).run(
            _bridge_fixture(), "backward",
            ("goal",), ("reachable-irrelevant",))

    assert all(
        "f-irrelevant" not in path.edge_ids
        and "f-bridge" not in path.edge_ids
        for path in batch.paths)
    assert not any(
        path.met_opposite_frontier
        for path in batch.paths)


def test_two_stream_probe_replay_is_deterministic_and_non_evidential():
    view = _bridge_fixture()
    before = view.to_dict()
    estimator = CorrectedProbeEstimator(ProbeConfig(
        mode="two_stream", path_count=40,
        max_steps=3, reference_fraction=0.25,
        minimum_path_diversity=0.0,
        seed=91))

    first = estimator.run(
        view, "forward", ("forward",),
        ("bridge",))
    second = estimator.run(
        view, "forward", ("forward",),
        ("bridge",))

    assert first == second
    assert first.health.reference_path_count == 10
    assert sum(
        row.sampling_stream == "reference"
        for row in first.paths) == 10
    assert view.to_dict() == before
    assert set(first.paths[0].to_dict()).isdisjoint({
        "evidence_ids", "truth", "confidence",
        "verified_evidence"})


def test_probe_meet_and_topology_generation_are_explicit():
    batch = CorrectedProbeEstimator(ProbeConfig(
        mode="importance", path_count=32,
        max_steps=2,
        minimum_path_diversity=0.0)).run(
            _bridge_fixture(), "forward",
            ("forward",), ("bridge",),
            node_features=(
                ProbeNodeFeatures(
                    "bridge", local_advantage=10.0),
            ))

    assert any(
        row.met_opposite_frontier
        and row.meet_node_id == "bridge"
        for row in batch.paths)
    assert all(
        row.topology_generation == 1
        and row.rng_substream >= 0
        for row in batch.paths)
