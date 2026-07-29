"""Stage-S4 capacity provenance and multi-commodity solver gates."""

import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.flow_control import (  # noqa: E402
    CapacityKind,
    CapacityRecord,
    CommodityFlowRequest,
    MultiCommodityCapacitySolver,
)
from freeciv_agent.pressure import ResourceKind  # noqa: E402


def _capacity(kind, value=1.0):
    return CapacityRecord(
        edge_or_node_id="shared-edge",
        resource=ResourceKind.CPU,
        value=value,
        kind=kind,
        provenance_id="capacity-source",
        measured_window=(
            ("turn-10", "turn-20")
            if kind == CapacityKind.MEASURED else None),
        confidence=0.9)


def _requests(first=1.0, second=1.0):
    return (
        CommodityFlowRequest(
            "goal-a:act:cpu", ResourceKind.CPU,
            ("shared-edge",), (first,)),
        CommodityFlowRequest(
            "goal-b:act:cpu", ResourceKind.CPU,
            ("shared-edge",), (second,)),
    )


def test_measured_allocated_and_shaping_capacities_are_distinct():
    records = tuple(
        _capacity(kind) for kind in (
            CapacityKind.MEASURED,
            CapacityKind.ALLOCATED,
            CapacityKind.SHAPING))

    assert tuple(row.kind for row in records) == (
        CapacityKind.MEASURED,
        CapacityKind.ALLOCATED,
        CapacityKind.SHAPING)
    assert len(set(row.capacity_id for row in records)) == 3


def test_shaping_dual_cannot_trigger_structural_change():
    result = MultiCommodityCapacitySolver().solve(
        _requests(), (_capacity(CapacityKind.SHAPING),))
    dual = result.capacity_duals[0]

    assert result.converged
    assert dual.value > 0.0
    assert not dual.economic_price
    assert dual.permitted_response == "numerical_shaping_only"


def test_allocated_dual_requests_arbiter_reconsideration_only():
    result = MultiCommodityCapacitySolver().solve(
        _requests(), (_capacity(CapacityKind.ALLOCATED),))
    dual = result.capacity_duals[0]

    assert result.converged
    assert not dual.economic_price
    assert dual.permitted_response == (
        "request_arbiter_reconsideration")


def test_measured_capacity_dual_tracks_service_bottleneck():
    result = MultiCommodityCapacitySolver().solve(
        _requests(), (_capacity(CapacityKind.MEASURED),))
    dual = result.capacity_duals[0]

    assert result.converged
    assert dual.economic_price
    assert dual.value == pytest.approx(0.5, abs=1e-8)
    assert dual.permitted_response == (
        "structural_bottleneck_candidate")


def test_nonconverged_dual_is_not_economic_price():
    result = MultiCommodityCapacitySolver(
        maximum_iterations=1).solve(
            _requests(),
            (_capacity(CapacityKind.MEASURED, value=0.7),),
            tolerance=1e-15)
    dual = result.capacity_duals[0]

    assert not result.converged
    assert result.health == "unhealthy:nonconverged"
    assert not dual.economic_price
    assert dual.permitted_response == (
        "exploration_guidance_only")


def test_multi_commodity_total_edge_flow_respects_capacity():
    solver = MultiCommodityCapacitySolver()
    capacity = _capacity(CapacityKind.ALLOCATED, value=0.75)
    first = solver.solve(_requests(2.0, -1.0), (capacity,))
    replay = solver.solve(
        _requests(2.0, -1.0), (capacity,),
        warm_start=first.warm_start)

    assert first.converged and replay.converged
    assert first.total_edge_flow(
        "shared-edge", ResourceKind.CPU) <= (
            capacity.value + 1e-9)
    assert replay.total_edge_flow(
        "shared-edge", ResourceKind.CPU) == pytest.approx(
            first.total_edge_flow(
                "shared-edge", ResourceKind.CPU))
    assert replay.dual_autocorrelation == pytest.approx(1.0)
    assert replay.active_set_changes == 0
