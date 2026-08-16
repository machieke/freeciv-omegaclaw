"""Exact-work corridor generator for conservative two-dye flow scaling."""

import math
import random
from dataclasses import dataclass

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.flow_control.advection import (
    AttentionState,
    PacketReservationLedger,
    TwoDyeAdvectionKernel,
)
from freeciv_agent.flow_control.model import (
    FlowEdge,
    FlowEdgeKind,
    FlowLegality,
    FlowNode,
    FlowNodeKind,
    FlowView,
)


@dataclass(frozen=True)
class FluidCase:
    view: FlowView
    initial_state: AttentionState
    forward_field: dict
    backward_field: dict
    microsteps: int
    expected_edge_updates: int
    artifact_hash: str
    failed_edge_ids: tuple = ()
    topology: str = "corridor"
    average_degree: float = 0.0


def build_fluid_case(length, microsteps, velocity=0.25):
    for value, name, minimum in (
            (length, "corridor length", 2),
            (microsteps, "microsteps", 1)):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError("{} must be an integer >= {}".format(name, minimum))
    velocity = float(velocity)
    if velocity < 0.0:
        raise ValueError("velocity must be nonnegative")
    context = "scaling-fluid-{}-{}".format(length, microsteps)
    names = tuple("fluid-node-{:07d}".format(i) for i in range(length))
    nodes = tuple(FlowNode(
        local_id=index,
        stable_id=name,
        kind=FlowNodeKind.PROPOSITION,
        semantic_generation=1,
        topology_generation=1,
        context_digest=context,
        clone_generation=0,
        source="scaling-generator",
    ) for index, name in enumerate(names))
    specs = []
    for index in range(length - 1):
        specs.append((
            "fluid-forward-{:07d}".format(index),
            names[index], names[index + 1],
            FlowEdgeKind.PROBE_FORWARD,
            FlowLegality(probe_forward=True),
        ))
        specs.append((
            "fluid-backward-{:07d}".format(index),
            names[index + 1], names[index],
            FlowEdgeKind.PROBE_BACKWARD,
            FlowLegality(probe_backward=True),
        ))
    edges = tuple(FlowEdge(
        local_id=index,
        stable_id=stable_id,
        source_node_id=source,
        target_node_id=target,
        kind=kind,
        legality=legality,
        semantic_generation=1,
        topology_generation=1,
        context_digest=context,
        clone_generation=0,
        source="scaling-generator",
    ) for index, (stable_id, source, target, kind, legality) in enumerate(specs))
    view = FlowView(
        query_id="scaling-fluid-query",
        snapshot_id="scaling-fluid-snapshot",
        legal_action_digest="scaling-fluid-legal",
        semantic_epoch=1,
        topology_generation=1,
        context_digest=context,
        clone_generation=0,
        nodes=nodes,
        edges=edges,
    )
    state = AttentionState(
        node_ids=names,
        forward_mass=(1.0,) + (0.0,) * (length - 1),
        backward_mass=(0.0,) * (length - 1) + (1.0,),
        reservoir_mass={},
        inflight_mass={},
        reservations=PacketReservationLedger(),
    )
    forward = {}
    backward = {}
    for edge in edges:
        if edge.kind == FlowEdgeKind.PROBE_FORWARD:
            forward[edge.stable_id] = velocity
        else:
            backward[edge.stable_id] = velocity
    material = {
        "backward_field": backward,
        "forward_field": forward,
        "microsteps": microsteps,
        "view": view.to_dict(),
    }
    return FluidCase(
        view=view,
        initial_state=state,
        forward_field=forward,
        backward_field=backward,
        microsteps=microsteps,
        expected_edge_updates=2 * (length - 1) * microsteps,
        artifact_hash=structural_hash(material),
        topology="corridor",
        average_degree=(len(edges) / float(len(nodes))),
    )


def build_fluid_graph_case(
        edge_update_budget, microsteps=50, average_degree=4,
        velocity=0.25):
    """Build a deterministic sparse DAG with an exact edge-update budget."""
    for value, name in (
            (edge_update_budget, "edge-update budget"),
            (microsteps, "microsteps"),
            (average_degree, "average degree")):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("{} must be a positive integer".format(name))
    if edge_update_budget % microsteps:
        raise ValueError("edge-update budget must be divisible by microsteps")
    edge_count = edge_update_budget // microsteps
    if edge_count < 2 or edge_count % 2:
        raise ValueError("sparse DAG requires a positive even edge count")
    velocity = float(velocity)
    if not math.isfinite(velocity) or velocity < 0.0:
        raise ValueError("velocity must be finite and nonnegative")
    pair_count = edge_count // 2
    node_count = max(2, int(math.ceil(edge_count / float(average_degree))))
    if pair_count > node_count * (node_count - 1) // 2:
        raise ValueError("requested degree cannot represent unique DAG edges")
    context = "scaling-fluid-dag-{}-{}-{}".format(
        edge_update_budget, microsteps, average_degree)
    names = tuple("fluid-dag-node-{:07d}".format(index)
                  for index in range(node_count))
    nodes = tuple(FlowNode(
        local_id=index,
        stable_id=name,
        kind=FlowNodeKind.PROPOSITION,
        semantic_generation=1,
        topology_generation=1,
        context_digest=context,
        clone_generation=0,
        source="scaling-generator",
    ) for index, name in enumerate(names))
    pairs = []
    offset = 1
    while len(pairs) < pair_count:
        for source in range(node_count - offset):
            pairs.append((source, source + offset))
            if len(pairs) == pair_count:
                break
        offset += 1
    specs = []
    for index, (source, target) in enumerate(pairs):
        specs.append((
            "fluid-dag-forward-{:07d}".format(index),
            names[source], names[target], FlowEdgeKind.PROBE_FORWARD,
            FlowLegality(probe_forward=True)))
        specs.append((
            "fluid-dag-backward-{:07d}".format(index),
            names[target], names[source], FlowEdgeKind.PROBE_BACKWARD,
            FlowLegality(probe_backward=True)))
    edges = tuple(FlowEdge(
        local_id=index,
        stable_id=stable_id,
        source_node_id=source,
        target_node_id=target,
        kind=kind,
        legality=legality,
        semantic_generation=1,
        topology_generation=1,
        context_digest=context,
        clone_generation=0,
        source="scaling-generator",
    ) for index, (stable_id, source, target, kind, legality)
        in enumerate(specs))
    view = FlowView(
        query_id="scaling-fluid-dag-query",
        snapshot_id="scaling-fluid-dag-snapshot",
        legal_action_digest="scaling-fluid-dag-legal",
        semantic_epoch=1,
        topology_generation=1,
        context_digest=context,
        clone_generation=0,
        nodes=nodes,
        edges=edges,
    )
    state = AttentionState(
        node_ids=names,
        forward_mass=(1.0,) + (0.0,) * (node_count - 1),
        backward_mass=(0.0,) * (node_count - 1) + (1.0,),
        reservoir_mass={}, inflight_mass={},
        reservations=PacketReservationLedger(),
    )
    forward = dict((edge.stable_id, velocity)
                   for edge in edges
                   if edge.kind == FlowEdgeKind.PROBE_FORWARD)
    backward = dict((edge.stable_id, velocity)
                    for edge in edges
                    if edge.kind == FlowEdgeKind.PROBE_BACKWARD)
    material = {
        "average_degree": average_degree,
        "backward_field": backward,
        "edge_update_budget": edge_update_budget,
        "forward_field": forward,
        "microsteps": microsteps,
        "topology": "sparse_dag",
        "view": view.to_dict(),
    }
    return FluidCase(
        view=view,
        initial_state=state,
        forward_field=forward,
        backward_field=backward,
        microsteps=microsteps,
        expected_edge_updates=edge_update_budget,
        artifact_hash=structural_hash(material),
        topology="sparse_dag",
        average_degree=len(edges) / float(len(nodes)),
    )


def apply_fluid_edge_failures(case, failure_fraction, seed=1729):
    """Return a deterministic zero-mobility repair for declared edge failures."""
    if not isinstance(case, FluidCase):
        raise TypeError("fluid failure repair requires FluidCase")
    failure_fraction = float(failure_fraction)
    if not 0.0 <= failure_fraction <= 1.0:
        raise ValueError("failure fraction must be in [0,1]")
    edge_ids = [row.stable_id for row in case.view.edges]
    count = int(round(len(edge_ids) * failure_fraction))
    selected = list(edge_ids)
    random.Random(seed).shuffle(selected)
    failed = frozenset(selected[:count])
    forward = dict(case.forward_field)
    backward = dict(case.backward_field)
    for edge_id in failed:
        if edge_id in forward:
            forward[edge_id] = 0.0
        if edge_id in backward:
            backward[edge_id] = 0.0
    active = sum(value > 0.0 for value in forward.values()) + sum(
        value > 0.0 for value in backward.values())
    material = {
        "backward_field": backward,
        "failed_edge_ids": sorted(failed),
        "forward_field": forward,
        "microsteps": case.microsteps,
        "view": case.view.to_dict(),
    }
    return FluidCase(
        view=case.view,
        initial_state=case.initial_state,
        forward_field=forward,
        backward_field=backward,
        microsteps=case.microsteps,
        expected_edge_updates=active * case.microsteps,
        artifact_hash=structural_hash(material),
        failed_edge_ids=tuple(sorted(failed)),
        topology=case.topology,
        average_degree=case.average_degree,
    )


def run_fluid_case(case, cfl_limit=0.9, aggregate=False):
    if not isinstance(case, FluidCase):
        raise TypeError("fluid evaluation requires FluidCase")
    kernel = TwoDyeAdvectionKernel(cfl_limit=cfl_limit)
    function = kernel.run_aggregate if aggregate else kernel.run
    return function(
        case.view, case.initial_state,
        case.forward_field, case.backward_field,
        microsteps=case.microsteps)
