"""Deterministic sparse bridge graphs with exact requested work counts."""

import math
import time
from dataclasses import dataclass
from dataclasses import replace

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.flow_control.model import (
    CandidateGrounding,
    FlowEdge,
    FlowEdgeKind,
    FlowLegality,
    FlowNode,
    FlowNodeKind,
    FlowProcess,
    FlowView,
)
from freeciv_agent.flow_control.advection import (
    AttentionState,
    PacketReservationLedger,
    TwoDyeAdvectionKernel,
)
from freeciv_agent.flow_control.potentials import (
    DeterministicMessagePotentialEstimator,
    PotentialBudget,
)
from freeciv_agent.flow_control.candidate_selector import (
    BridgeCandidateSelector,
    DecisionSafeCandidateSelector,
)
from freeciv_agent.flow_control.probes import (
    CorrectedProbeEstimator,
    ProbeConfig,
)


@dataclass(frozen=True)
class BridgeCase:
    view: FlowView
    goal_ids: tuple
    expected_bridge_node_id: str
    node_count: int
    edge_count: int
    candidate_count: int
    artifact_hash: str
    topology: str = "disconnected_distractors"
    failed_edge_ids: tuple = ()


@dataclass(frozen=True)
class BridgeEvaluation:
    estimate_count: int
    bridge_factor: float
    one_sided_max_factor: float
    elapsed_ms: float
    deterministic_hash: str
    bridge_separated: bool
    ranked_operation_ids: tuple

    def to_dict(self):
        return {
            "bridge_factor": self.bridge_factor,
            "bridge_separated": self.bridge_separated,
            "deterministic_hash": self.deterministic_hash,
            "elapsed_ms": self.elapsed_ms,
            "estimate_count": self.estimate_count,
            "one_sided_max_factor": self.one_sided_max_factor,
            "ranked_operation_ids": list(self.ranked_operation_ids),
        }


@dataclass(frozen=True)
class ProtectedReadoutEvaluation:
    fallback_required: bool
    fallback_reason: object
    scalar_winner: str
    protected_operation_ids: tuple
    bridge_added_operation_ids: tuple
    scalar_winner_recalled: bool
    expected_bridge_recalled: bool
    scalar_order_preserved: bool
    signal_ledger_hash: str
    artifact_hash: str


@dataclass(frozen=True)
class CorrectedProbeReadoutEvaluation:
    protected_readout: ProtectedReadoutEvaluation
    probe_healthy: bool
    fallback_to_messages: bool
    fallback_reasons: tuple
    path_count: int
    minimum_effective_sample_fraction: float
    minimum_path_diversity: float
    artifact_hash: str


@dataclass(frozen=True)
class PathPersistenceEvaluation:
    protected_readout: ProtectedReadoutEvaluation
    iterations: int
    momentum: float
    dwell_threshold: int
    maximum_state_entries: int
    persisted_operation_ids: tuple
    artifact_hash: str


@dataclass(frozen=True)
class SourceSinkFlowEvaluation:
    protected_readout: ProtectedReadoutEvaluation
    microsteps: int
    edge_updates: int
    wall_ms: float
    healthy: bool
    maximum_normalized_mass_error: float
    positivity_corrections: int
    fallback_to_messages: bool
    artifact_hash: str


def _count(value, name, minimum):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError("{} must be an integer >= {}".format(name, minimum))
    return value


def build_bridge_case(
        node_count, edge_count, candidate_count, goal_count=1, seed=1729,
        topology="disconnected_distractors"):
    node_count = _count(node_count, "node count", 4)
    edge_count = _count(edge_count, "edge count", goal_count + 1)
    candidate_count = _count(candidate_count, "candidate count", 1)
    goal_count = _count(goal_count, "goal count", 1)
    if candidate_count + goal_count + 1 > node_count:
        raise ValueError("node count cannot represent boundaries and candidates")
    if topology not in (
            "sparse_dag", "shared_dag", "cyclic",
            "disconnected_distractors", "asymmetric_legality",
            "bottleneck", "dynamic_failure"):
        raise ValueError("unknown bridge topology")
    context = "scaling-bridge-{}-{}-{}-{}-{}".format(
        node_count, edge_count, candidate_count, goal_count,
        "{}-{}".format(seed, topology))
    goal_ids = tuple("scale-goal-{:04d}".format(i) for i in range(goal_count))
    rows = [("forward", FlowNodeKind.FORWARD_BOUNDARY, ("snapshot",), False)]
    rows.extend(
        ("goal-{:04d}".format(i), FlowNodeKind.BACKWARD_BOUNDARY,
         (goal_ids[i],), False)
        for i in range(goal_count))
    rows.extend(
        ("candidate-{:06d}".format(i), FlowNodeKind.OPERATION, (), True)
        for i in range(candidate_count))
    rows.extend(
        ("distractor-{:06d}".format(i), FlowNodeKind.PROPOSITION, (), False)
        for i in range(node_count - len(rows)))
    nodes = tuple(FlowNode(
        local_id=index,
        stable_id=stable_id,
        kind=kind,
        semantic_generation=1,
        topology_generation=1,
        context_digest=context,
        clone_generation=0,
        source="scaling-generator",
        provenance_ids=provenance,
        committable=committable,
    ) for index, (stable_id, kind, provenance, committable) in enumerate(rows))
    bridge_id = "candidate-000000"

    specs = []
    seen = set()

    def add(source, target, direction):
        key = (source, target, direction)
        if source == target or key in seen or len(specs) >= edge_count:
            return
        seen.add(key)
        specs.append(key)

    add("forward", bridge_id, "forward")
    for index in range(goal_count):
        add("goal-{:04d}".format(index), bridge_id, "backward")

    nonboundary = [row[0] for row in rows if not row[0].startswith("goal-")
                   and row[0] != "forward" and row[0] != bridge_id]
    split = (len(nonboundary) + 1) // 2
    forward_nodes = nonboundary[:split]
    backward_nodes = nonboundary[split:]
    if forward_nodes:
        add("forward", forward_nodes[0], "forward")
    if backward_nodes:
        add("goal-0000", backward_nodes[0], "backward")

    def fill_group(boundary, group, direction):
        if not group:
            return
        for target in group:
            add(boundary, target, direction)
        if topology in ("sparse_dag", "shared_dag"):
            pairs = (
                (group[left], group[right])
                for right in range(1, len(group))
                for left in range(right))
            for source, target in pairs:
                add(source, target, direction)
                if len(specs) >= edge_count:
                    return
        else:
            for offset in range(1, len(group)):
                for index, source in enumerate(group):
                    add(source, group[(index + offset) % len(group)], direction)
                    if len(specs) >= edge_count:
                        return

    fill_group("forward", forward_nodes, "forward")
    for goal_index in range(goal_count):
        fill_group(
            "goal-{:04d}".format(goal_index), backward_nodes, "backward")
    if len(specs) < edge_count:
        raise ValueError(
            "requested edge count exceeds separated graph capacity; "
            "increase node count")
    edges = tuple(FlowEdge(
        local_id=index,
        stable_id="scale-edge-{:09d}".format(index),
        source_node_id=source,
        target_node_id=target,
        kind=(FlowEdgeKind.PROBE_FORWARD
              if direction == "forward" else FlowEdgeKind.PROBE_BACKWARD),
        legality=(FlowLegality(probe_forward=True)
                  if direction == "forward" else FlowLegality(probe_backward=True)),
        semantic_generation=1,
        topology_generation=1,
        context_digest=context,
        clone_generation=0,
        source="scaling-generator",
    ) for index, (source, target, direction) in enumerate(specs))
    groundings = tuple(CandidateGrounding(
        snapshot_id="scaling-bridge-snapshot",
        legal_action_digest="scaling-legal-actions",
        action_digest="scale-action-{:06d}".format(index),
        semantic_epoch=1,
        topology_generation=1,
        actor_id="player",
        target_digest="target-{:06d}".format(index),
        category="scaling",
        operation_node_id="candidate-{:06d}".format(index),
    ) for index in range(candidate_count))
    view = FlowView(
        query_id="scaling-bridge-query",
        snapshot_id="scaling-bridge-snapshot",
        legal_action_digest="scaling-legal-actions",
        semantic_epoch=1,
        topology_generation=1,
        context_digest=context,
        clone_generation=0,
        nodes=nodes,
        edges=edges,
        candidate_groundings=groundings,
    )
    material = view.to_dict()
    return BridgeCase(
        view=view,
        goal_ids=goal_ids,
        expected_bridge_node_id=bridge_id,
        node_count=node_count,
        edge_count=edge_count,
        candidate_count=candidate_count,
        artifact_hash=structural_hash(material),
        topology=topology,
    )


def apply_bridge_edge_failure(case, edge_id=None):
    """Retire one edge into a new topology generation for fallback testing."""
    if not isinstance(case, BridgeCase):
        raise TypeError("bridge failure requires BridgeCase")
    edge_id = str(edge_id or case.view.edges[0].stable_id)
    if edge_id not in {row.stable_id for row in case.view.edges}:
        raise ValueError("failed bridge edge is not in the view")
    generation = case.view.topology_generation + 1
    nodes = tuple(replace(
        row, local_id=index, topology_generation=generation)
        for index, row in enumerate(case.view.nodes))
    remaining = [row for row in case.view.edges if row.stable_id != edge_id]
    edges = tuple(replace(
        row, local_id=index, topology_generation=generation,
        retired_generation=None)
        for index, row in enumerate(remaining))
    groundings = tuple(replace(
        row, topology_generation=generation)
        for row in case.view.candidate_groundings)
    view = FlowView(
        query_id=case.view.query_id,
        snapshot_id=case.view.snapshot_id,
        legal_action_digest=case.view.legal_action_digest,
        semantic_epoch=case.view.semantic_epoch,
        topology_generation=generation,
        context_digest=case.view.context_digest,
        clone_generation=case.view.clone_generation,
        nodes=nodes,
        edges=edges,
        candidate_groundings=groundings,
    )
    return BridgeCase(
        view=view,
        goal_ids=case.goal_ids,
        expected_bridge_node_id=case.expected_bridge_node_id,
        node_count=len(nodes),
        edge_count=len(edges),
        candidate_count=case.candidate_count,
        artifact_hash=structural_hash(view.to_dict()),
        topology="dynamic_failure",
        failed_edge_ids=(edge_id,),
    )


def evaluate_bridge_case(case, max_iterations=64):
    if not isinstance(case, BridgeCase):
        raise TypeError("bridge evaluation requires BridgeCase")
    started = time.perf_counter()
    estimates = DeterministicMessagePotentialEstimator().estimate(
        case.view,
        case.goal_ids,
        PotentialBudget(max_iterations=max_iterations),
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    rows = [row for row in estimates
            if row.node_id == case.expected_bridge_node_id]
    bridge_factor = min(row.bridge_factor for row in rows)
    one_sided = [row.bridge_factor for row in estimates
                 if row.node_id.startswith("distractor-")]
    one_sided_max = max(one_sided) if one_sided else 0.0
    deterministic_hash = structural_hash([row.to_dict() for row in estimates])
    operation_scores = {}
    for row in estimates:
        if row.node_id.startswith("candidate-"):
            operation_scores[row.node_id] = max(
                operation_scores.get(row.node_id, 0.0), row.bridge_factor)
    ranked_operations = tuple(sorted(
        operation_scores,
        key=lambda operation_id: (
            -operation_scores[operation_id], operation_id)))
    return BridgeEvaluation(
        estimate_count=len(estimates),
        bridge_factor=bridge_factor,
        one_sided_max_factor=one_sided_max,
        elapsed_ms=elapsed_ms,
        deterministic_hash=deterministic_hash,
        bridge_separated=bridge_factor > one_sided_max,
        ranked_operation_ids=ranked_operations,
    )


def evaluate_protected_readout(
        case, bridge_evaluation=None, scalar_top_k=3, bridge_top_k=8,
        maximum_nodes=None, maximum_edges=None,
        readout_policy="protected-message-union"):
    """Form a bridge-only candidate union while retaining scalar authority."""
    if not isinstance(case, BridgeCase):
        raise TypeError("protected readout requires BridgeCase")
    exhausted = (
        (maximum_nodes is not None and case.node_count > int(maximum_nodes))
        or (maximum_edges is not None and case.edge_count > int(maximum_edges))
        or bool(case.failed_edge_ids))
    all_operations = tuple(
        row.operation_node_id for row in case.view.candidate_groundings)
    # A deliberately different scalar winner makes protection observable.
    scalar_ranked = tuple(reversed(all_operations))
    if exhausted:
        bridge_ids = ()
        fallback_reason = (
            "topology-edge-failure"
            if case.failed_edge_ids else
            "materialization-budget-exhausted")
    else:
        evaluation = bridge_evaluation or evaluate_bridge_case(case)
        bridge_ids = evaluation.ranked_operation_ids[:bridge_top_k]
        fallback_reason = None
    union = DecisionSafeCandidateSelector().select(
        scalar_ranked_operation_ids=scalar_ranked,
        all_operation_ids=all_operations,
        bridge_operation_ids=bridge_ids,
        scalar_top_k=scalar_top_k,
        readout_policy=readout_policy,
    )
    scalar_prefix = scalar_ranked[:scalar_top_k]
    material = {
        "bridge_added_operation_ids": list(
            union.bridge_added_operation_ids),
        "fallback_reason": fallback_reason,
        "fallback_required": exhausted,
        "operation_ids": list(union.operation_ids),
        "readout_policy": readout_policy,
        "scalar_ranked_operation_ids": list(scalar_ranked),
        "signal_ledger": union.signal_ledger.to_dict(),
    }
    return ProtectedReadoutEvaluation(
        fallback_required=exhausted,
        fallback_reason=fallback_reason,
        scalar_winner=scalar_ranked[0],
        protected_operation_ids=union.operation_ids,
        bridge_added_operation_ids=union.bridge_added_operation_ids,
        scalar_winner_recalled=scalar_ranked[0] in union.operation_ids,
        expected_bridge_recalled=(
            exhausted or case.expected_bridge_node_id in union.operation_ids),
        scalar_order_preserved=(
            union.scalar_ranked_operation_ids == scalar_ranked
            and union.operation_ids[:len(scalar_prefix)] == scalar_prefix),
        signal_ledger_hash=union.signal_ledger.to_dict()["ledger_hash"],
        artifact_hash=structural_hash(material),
    )


def evaluate_scalar_readout(case, scalar_top_k=3):
    """Frozen scalar candidate prefix with no bridge/probe/flow compute."""
    if not isinstance(case, BridgeCase):
        raise TypeError("scalar readout requires BridgeCase")
    operations = tuple(
        row.operation_node_id for row in case.view.candidate_groundings)
    scalar_ranked = tuple(reversed(operations))
    union = DecisionSafeCandidateSelector().select(
        scalar_ranked_operation_ids=scalar_ranked,
        all_operation_ids=operations,
        bridge_operation_ids=(),
        scalar_top_k=scalar_top_k,
        readout_policy="protected-message-union",
    )
    scalar_prefix = scalar_ranked[:scalar_top_k]
    material = {
        "operation_ids": list(union.operation_ids),
        "readout_policy": "scalar-pf-v2-packets",
        "scalar_ranked_operation_ids": list(scalar_ranked),
        "signal_ledger": union.signal_ledger.to_dict(),
    }
    return ProtectedReadoutEvaluation(
        fallback_required=False,
        fallback_reason=None,
        scalar_winner=scalar_ranked[0],
        protected_operation_ids=union.operation_ids,
        bridge_added_operation_ids=union.bridge_added_operation_ids,
        scalar_winner_recalled=scalar_ranked[0] in union.operation_ids,
        expected_bridge_recalled=False,
        scalar_order_preserved=(
            union.scalar_ranked_operation_ids == scalar_ranked
            and union.operation_ids == scalar_prefix),
        signal_ledger_hash=union.signal_ledger.to_dict()["ledger_hash"],
        artifact_hash=structural_hash(material),
    )


def evaluate_source_sink_flow_readout(
        case, microsteps=1, velocity=0.25, maximum_regions=8):
    """Numerical source/sink transport used only for candidate-union readout."""
    if not isinstance(case, BridgeCase):
        raise TypeError("source-sink flow readout requires BridgeCase")
    if (isinstance(microsteps, bool) or not isinstance(microsteps, int)
            or microsteps < 1):
        raise ValueError("source-sink microsteps must be positive")
    velocity = float(velocity)
    if not math.isfinite(velocity) or velocity < 0.0:
        raise ValueError("source-sink velocity must be finite and nonnegative")
    operations = tuple(
        row.operation_node_id for row in case.view.candidate_groundings)
    scalar_ranked = tuple(reversed(operations))
    if case.failed_edge_ids:
        scalar = evaluate_scalar_readout(case)
        material = {
            "case_hash": case.artifact_hash,
            "fallback_reason": "topology-edge-failure",
            "protected_readout_hash": scalar.artifact_hash,
        }
        protected = ProtectedReadoutEvaluation(
            fallback_required=True,
            fallback_reason="topology-edge-failure",
            scalar_winner=scalar.scalar_winner,
            protected_operation_ids=scalar.protected_operation_ids,
            bridge_added_operation_ids=(),
            scalar_winner_recalled=scalar.scalar_winner_recalled,
            expected_bridge_recalled=True,
            scalar_order_preserved=scalar.scalar_order_preserved,
            signal_ledger_hash=scalar.signal_ledger_hash,
            artifact_hash=structural_hash(material),
        )
        return SourceSinkFlowEvaluation(
            protected, microsteps, 0, 0.0, True, 0.0, 0, True,
            structural_hash(material))
    node_ids = tuple(
        row.stable_id for row in sorted(
            case.view.nodes, key=lambda row: row.local_id))
    node_index = dict((node_id, index)
                      for index, node_id in enumerate(node_ids))
    forward_mass = [0.0] * len(node_ids)
    backward_mass = [0.0] * len(node_ids)
    forward_mass[node_index["forward"]] = 1.0
    goal_nodes = tuple(
        "goal-{:04d}".format(index) for index in range(len(case.goal_ids)))
    for goal_node in goal_nodes:
        backward_mass[node_index[goal_node]] = 1.0 / len(goal_nodes)
    state = AttentionState(
        node_ids=node_ids,
        forward_mass=tuple(forward_mass),
        backward_mass=tuple(backward_mass),
        reservoir_mass={}, inflight_mass={},
        reservations=PacketReservationLedger(),
    )
    forward = dict((
        edge.stable_id,
        velocity if edge.legality.allows(FlowProcess.PROBE_FORWARD) else 0.0)
        for edge in case.view.edges)
    backward = dict((
        edge.stable_id,
        velocity if edge.legality.allows(FlowProcess.PROBE_BACKWARD) else 0.0)
        for edge in case.view.edges)
    run = TwoDyeAdvectionKernel().run_aggregate(
        case.view, state, forward, backward, microsteps=microsteps)
    final_index = dict((node_id, index)
                       for index, node_id in enumerate(run.final_state.node_ids))
    overlap = dict((operation_id, math.sqrt(
        run.final_state.forward_mass[final_index[operation_id]]
        * run.final_state.backward_mass[final_index[operation_id]]))
        for operation_id in operations)
    selected = tuple(sorted(
        (operation_id for operation_id in operations
         if overlap[operation_id] > 0.0),
        key=lambda operation_id: (-overlap[operation_id], operation_id)
    ))[:maximum_regions]
    fallback = not run.healthy or not selected
    if fallback:
        messages = evaluate_bridge_case(case)
        selected = messages.ranked_operation_ids[:maximum_regions]
    union = DecisionSafeCandidateSelector().select(
        scalar_ranked_operation_ids=scalar_ranked,
        all_operation_ids=operations,
        bridge_operation_ids=selected,
        scalar_top_k=3,
        readout_policy="protected-message-union",
    )
    scalar_prefix = scalar_ranked[:3]
    mass_before = state.accounted_total
    mass_after = run.final_state.accounted_total
    normalized_error = abs(mass_after - mass_before) / max(1.0, mass_before)
    reason = "flow-unhealthy" if not run.healthy else (
        "zero-flow-overlap" if fallback else None)
    material = {
        "case_hash": case.artifact_hash,
        "edge_updates": run.edge_updates,
        "fallback_reason": reason,
        "microsteps": microsteps,
        "operation_ids": list(union.operation_ids),
        "overlap": overlap,
        "signal_ledger": union.signal_ledger.to_dict(),
        "state_hash": run.final_state.state_hash,
    }
    protected = ProtectedReadoutEvaluation(
        fallback_required=fallback,
        fallback_reason=reason,
        scalar_winner=scalar_ranked[0],
        protected_operation_ids=union.operation_ids,
        bridge_added_operation_ids=union.bridge_added_operation_ids,
        scalar_winner_recalled=scalar_ranked[0] in union.operation_ids,
        expected_bridge_recalled=(
            case.expected_bridge_node_id in union.operation_ids),
        scalar_order_preserved=(
            union.scalar_ranked_operation_ids == scalar_ranked
            and union.operation_ids[:len(scalar_prefix)] == scalar_prefix),
        signal_ledger_hash=union.signal_ledger.to_dict()["ledger_hash"],
        artifact_hash=structural_hash(material),
    )
    return SourceSinkFlowEvaluation(
        protected_readout=protected,
        microsteps=microsteps,
        edge_updates=run.edge_updates,
        wall_ms=run.wall_ms,
        healthy=run.healthy,
        maximum_normalized_mass_error=max(
            normalized_error, run.maximum_normalized_mass_error),
        positivity_corrections=run.positivity_corrections,
        fallback_to_messages=fallback,
        artifact_hash=structural_hash(material),
    )


def evaluate_corrected_probe_readout(
        case, path_count=128, max_steps=16,
        maximum_regions=8, seed=1729):
    """Probe-informed union with deterministic-message fallback on ill health."""
    if not isinstance(case, BridgeCase):
        raise TypeError("corrected probe readout requires BridgeCase")
    config = ProbeConfig(
        path_count=path_count,
        max_steps=max_steps,
        seed=seed,
    )
    estimator = CorrectedProbeEstimator(config)
    operations = tuple(
        row.operation_node_id for row in case.view.candidate_groundings)
    forward = estimator.run(
        case.view, "forward", ("forward",), operations)
    selected = set()
    health = [forward.health]
    reasons = set(forward.health.reasons)
    selector = BridgeCandidateSelector()
    for index, goal_id in enumerate(case.goal_ids):
        backward = estimator.run(
            case.view, "backward",
            ("goal-{:04d}".format(index),), operations)
        health.append(backward.health)
        reasons.update(backward.health.reasons)
        selection = selector.select(
            case.view, goal_id, operations,
            forward, backward,
            maximum_regions=maximum_regions)
        selected.update(selection.selected_operation_node_ids)
    healthy = all(row.healthy for row in health)
    if not healthy:
        messages = evaluate_bridge_case(case)
        selected = set(messages.ranked_operation_ids[:maximum_regions])
    scalar_ranked = tuple(reversed(operations))
    union = DecisionSafeCandidateSelector().select(
        scalar_ranked_operation_ids=scalar_ranked,
        all_operation_ids=operations,
        bridge_operation_ids=tuple(sorted(selected)),
        scalar_top_k=3,
        readout_policy="corrected-probe-union",
    )
    scalar_prefix = scalar_ranked[:3]
    material = {
        "fallback_reasons": sorted(reasons),
        "fallback_to_messages": not healthy,
        "health": [row.to_dict() for row in health],
        "operation_ids": list(union.operation_ids),
        "signal_ledger": union.signal_ledger.to_dict(),
    }
    protected = ProtectedReadoutEvaluation(
        fallback_required=not healthy,
        fallback_reason=(
            None if healthy else "corrected-probe-unhealthy:" + ",".join(
                sorted(reasons))),
        scalar_winner=scalar_ranked[0],
        protected_operation_ids=union.operation_ids,
        bridge_added_operation_ids=union.bridge_added_operation_ids,
        scalar_winner_recalled=scalar_ranked[0] in union.operation_ids,
        expected_bridge_recalled=(
            case.expected_bridge_node_id in union.operation_ids),
        scalar_order_preserved=(
            union.scalar_ranked_operation_ids == scalar_ranked
            and union.operation_ids[:len(scalar_prefix)] == scalar_prefix),
        signal_ledger_hash=union.signal_ledger.to_dict()["ledger_hash"],
        artifact_hash=structural_hash(material),
    )
    return CorrectedProbeReadoutEvaluation(
        protected_readout=protected,
        probe_healthy=healthy,
        fallback_to_messages=not healthy,
        fallback_reasons=tuple(sorted(reasons)),
        path_count=sum(row.reference_path_count + (
            path_count - row.reference_path_count) for row in health),
        minimum_effective_sample_fraction=min(
            row.effective_sample_fraction for row in health),
        minimum_path_diversity=min(row.path_diversity for row in health),
        artifact_hash=structural_hash(material),
    )


def evaluate_path_persistence(
        case, iterations=8, momentum=0.8,
        dwell_threshold=3, maximum_regions=8):
    """Cheap smoothed-corridor comparator without fluid transport."""
    if not isinstance(case, BridgeCase):
        raise TypeError("path persistence requires BridgeCase")
    if (isinstance(iterations, bool) or not isinstance(iterations, int)
            or iterations < 1):
        raise ValueError("path persistence iterations must be positive")
    momentum = float(momentum)
    if not 0.0 <= momentum < 1.0:
        raise ValueError("path persistence momentum must be in [0,1)")
    if (isinstance(dwell_threshold, bool)
            or not isinstance(dwell_threshold, int)
            or dwell_threshold < 1):
        raise ValueError("path persistence dwell threshold must be positive")
    messages = evaluate_bridge_case(case)
    ranking = messages.ranked_operation_ids
    raw = dict(
        (operation_id, float(len(ranking) - index))
        for index, operation_id in enumerate(ranking))
    smoothed = dict((operation_id, 0.0) for operation_id in ranking)
    dwell = dict((operation_id, 0) for operation_id in ranking)
    persisted = ()
    for _ in range(iterations):
        for operation_id in ranking:
            smoothed[operation_id] = (
                momentum * smoothed[operation_id]
                + (1.0 - momentum) * raw[operation_id])
        current = tuple(sorted(
            ranking,
            key=lambda operation_id: (
                -smoothed[operation_id], operation_id)))[:maximum_regions]
        current_set = frozenset(current)
        for operation_id in ranking:
            dwell[operation_id] = (
                dwell[operation_id] + 1
                if operation_id in current_set else 0)
        persisted = tuple(
            operation_id for operation_id in current
            if dwell[operation_id] >= dwell_threshold)
    scalar_ranked = tuple(reversed(ranking))
    union = DecisionSafeCandidateSelector().select(
        scalar_ranked_operation_ids=scalar_ranked,
        all_operation_ids=tuple(
            row.operation_node_id for row in case.view.candidate_groundings),
        bridge_operation_ids=persisted,
        scalar_top_k=3,
        readout_policy="protected-message-union",
    )
    scalar_prefix = scalar_ranked[:3]
    material = {
        "dwell_threshold": dwell_threshold,
        "iterations": iterations,
        "momentum": momentum,
        "persisted_operation_ids": list(persisted),
        "smoothed": dict(sorted(smoothed.items())),
        "union": union.to_dict(),
    }
    protected = ProtectedReadoutEvaluation(
        fallback_required=False,
        fallback_reason=None,
        scalar_winner=scalar_ranked[0],
        protected_operation_ids=union.operation_ids,
        bridge_added_operation_ids=union.bridge_added_operation_ids,
        scalar_winner_recalled=scalar_ranked[0] in union.operation_ids,
        expected_bridge_recalled=(
            case.expected_bridge_node_id in union.operation_ids),
        scalar_order_preserved=(
            union.scalar_ranked_operation_ids == scalar_ranked
            and union.operation_ids[:len(scalar_prefix)] == scalar_prefix),
        signal_ledger_hash=union.signal_ledger.to_dict()["ledger_hash"],
        artifact_hash=structural_hash(material),
    )
    return PathPersistenceEvaluation(
        protected_readout=protected,
        iterations=iterations,
        momentum=momentum,
        dwell_threshold=dwell_threshold,
        maximum_state_entries=len(smoothed) + len(dwell),
        persisted_operation_ids=persisted,
        artifact_hash=structural_hash(material),
    )
