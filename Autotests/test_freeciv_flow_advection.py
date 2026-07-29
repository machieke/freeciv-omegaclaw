"""Stage-S4 conservative asymmetric two-dye advection gates."""

import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.flow_control import (  # noqa: E402
    AttentionState,
    FlowEdge,
    FlowEdgeKind,
    FlowLegality,
    FlowNode,
    FlowNodeKind,
    FlowView,
    PacketReservationLedger,
    ReservationMass,
    TwoDyeAdvectionKernel,
)


def _corridor(length):
    names = tuple(
        "node-{}".format(index)
        for index in range(length))
    nodes = tuple(
        FlowNode(
            local_id=index,
            stable_id=name,
            kind=FlowNodeKind.PROPOSITION,
            semantic_generation=1,
            topology_generation=3,
            context_digest="advection-context",
            clone_generation=0,
            source="advection-test")
        for index, name in enumerate(names))
    edge_specs = []
    for index in range(length - 1):
        edge_specs.extend((
            (
                "forward-{}".format(index),
                names[index], names[index + 1],
                FlowEdgeKind.PROBE_FORWARD,
                FlowLegality(probe_forward=True)),
            (
                "backward-{}".format(index),
                names[index + 1], names[index],
                FlowEdgeKind.PROBE_BACKWARD,
                FlowLegality(probe_backward=True)),
        ))
    edges = tuple(
        FlowEdge(
            local_id=index,
            stable_id=edge_id,
            source_node_id=source,
            target_node_id=target,
            kind=kind,
            legality=legality,
            semantic_generation=1,
            topology_generation=3,
            context_digest="advection-context",
            clone_generation=0,
            source="advection-test")
        for index, (
            edge_id, source, target,
            kind, legality) in enumerate(edge_specs))
    return FlowView(
        query_id="advection-query",
        snapshot_id="advection-snapshot",
        legal_action_digest="legal",
        semantic_epoch=1,
        topology_generation=3,
        context_digest="advection-context",
        clone_generation=0,
        nodes=nodes,
        edges=edges)


def _state(view, auxiliary=False):
    size = len(view.nodes)
    return AttentionState(
        node_ids=tuple(
            row.stable_id for row in view.nodes),
        forward_mass=(1.0,) + (0.0,) * (size - 1),
        backward_mass=(0.0,) * (size - 1) + (1.0,),
        reservoir_mass=(
            {"cpu": 2.0} if auxiliary else {}),
        inflight_mass=(
            {"probe": 3.0} if auxiliary else {}),
        reservations=PacketReservationLedger((
            ReservationMass(
                "reservation-1", 4.0,
                "operation-1", "requirements-1"),
        ) if auxiliary else ()))


def _fields(view, velocity=0.5):
    forward = {}
    backward = {}
    for edge in view.edges:
        if edge.stable_id.startswith("forward"):
            forward[edge.stable_id] = velocity
            backward[edge.stable_id] = 100.0
        else:
            backward[edge.stable_id] = velocity
            forward[edge.stable_id] = 100.0
    return forward, backward


def test_attention_mass_is_conserved_without_declared_reactions():
    view = _corridor(5)
    forward, backward = _fields(view)
    result = TwoDyeAdvectionKernel().step(
        view, _state(view), forward, backward)

    assert result.healthy
    assert result.total_mass_before == pytest.approx(2.0)
    assert result.total_mass_after == pytest.approx(2.0)
    assert result.mass_error == pytest.approx(0.0)


def test_forward_backward_masses_use_separate_legalities():
    view = _corridor(3)
    forward, backward = _fields(view, velocity=0.5)
    result = TwoDyeAdvectionKernel(
        cfl_limit=1.0).step(
            view, _state(view), forward, backward)

    assert result.forward_edges_used == (
        "forward-0", "forward-1")
    assert result.backward_edges_used == (
        "backward-0", "backward-1")
    assert result.state.forward_mass == pytest.approx(
        (0.5, 0.5, 0.0))
    assert result.state.backward_mass == pytest.approx(
        (0.0, 0.5, 0.5))


def test_valid_cfl_preserves_nonnegative_mass():
    view = _corridor(4)
    forward, backward = _fields(view, velocity=0.8)
    result = TwoDyeAdvectionKernel(
        cfl_limit=0.9).step(
            view, _state(view), forward, backward)

    assert result.raw_local_cfl == pytest.approx(0.8)
    assert not result.cfl_rescaled
    assert min(
        result.state.forward_mass
        + result.state.backward_mass) >= 0.0
    assert result.positivity_corrections == 0


def test_cfl_rescaling_is_reported():
    view = _corridor(3)
    forward, backward = _fields(view, velocity=4.0)
    result = TwoDyeAdvectionKernel(
        cfl_limit=0.8).step(
            view, _state(view), forward, backward)

    assert result.cfl_rescaled
    assert result.raw_local_cfl == pytest.approx(4.0)
    assert result.applied_velocity_scale == pytest.approx(0.2)
    assert result.total_mass_after == pytest.approx(
        result.total_mass_before)


def test_overlap_peaks_on_true_meeting_corridor():
    view = _corridor(5)
    forward, backward = _fields(view, velocity=0.5)
    run = TwoDyeAdvectionKernel(
        cfl_limit=1.0).run(
            view, _state(view), forward, backward,
            microsteps=4)
    overlap = TwoDyeAdvectionKernel().overlap(
        run.final_state)

    assert max(
        range(len(overlap)),
        key=overlap.__getitem__) == 2
    assert overlap[2] > overlap[0]
    assert overlap[2] > overlap[-1]


def test_transport_latency_scales_with_corridor_length():
    short = _corridor(4)
    long = _corridor(12)
    short_fields = _fields(short, velocity=0.25)
    long_fields = _fields(long, velocity=0.25)
    kernel = TwoDyeAdvectionKernel()
    short_run = kernel.run(
        short, _state(short), *short_fields,
        microsteps=5)
    long_run = kernel.run(
        long, _state(long), *long_fields,
        microsteps=5)

    assert long_run.corridor_length > short_run.corridor_length
    assert long_run.edge_updates > short_run.edge_updates
    assert short_run.wall_ms >= 0.0
    assert long_run.wall_ms >= 0.0
    assert long_run.microseconds_per_edge_update >= 0.0


def test_reservoir_and_reservation_mass_are_in_total_accounting():
    view = _corridor(3)
    state = _state(view, auxiliary=True)
    forward, backward = _fields(view)
    result = TwoDyeAdvectionKernel().step(
        view, state, forward, backward)

    assert state.reservations.total_mass == pytest.approx(4.0)
    assert result.total_mass_before == pytest.approx(11.0)
    assert result.total_mass_after == pytest.approx(11.0)
    assert result.state.reservoir_mass == {"cpu": 2.0}
    assert result.state.inflight_mass == {"probe": 3.0}
