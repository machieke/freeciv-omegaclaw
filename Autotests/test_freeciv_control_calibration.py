"""Typed realized-relief calibration and context isolation gates."""

import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    ContextualConductanceStore,
    ControlCalibrationLedger,
    ControlCalibrationRecord,
    TruthState,
)


def _record(
        realized=0.5, success=True,
        targets=("route_conductance",),
        context="context:war", frontier="frontier:north",
        generation=4, propensity=0.25):
    return ControlCalibrationRecord(
        context_signature=context,
        rule_or_operation_id="route:defense",
        predicted_relief=0.7,
        realized_relief=realized,
        predicted_success=0.8,
        success=success,
        predicted_cost=(("cpu", 2.0), ("latency", 1.0)),
        realized_cost=(("cpu", 3.0), ("latency", 1.5)),
        selection_propensity=propensity,
        update_targets=targets,
        frontier_signature=frontier,
        generation=generation,
        relief_source="authoritative-turn-delta")


def test_credit_updates_only_declared_control_targets():
    calls = []

    def update(name):
        return lambda record: calls.append(
            (name, record.record_id))

    record = _record(
        targets=("operation_success", "cost_latency"))
    result = ControlCalibrationLedger().apply(record, {
        "operation_success": update("operation_success"),
        "cost_latency": update("cost_latency"),
        "route_conductance": update("route_conductance"),
    })

    assert set(result) == {
        "operation_success", "cost_latency"}
    assert {row[0] for row in calls} == {
        "operation_success", "cost_latency"}


def test_no_progress_decays_route_without_changing_truth():
    store = ContextualConductanceStore()
    truth = TruthState(0.4, 0.6)
    record = _record(realized=0.0, success=False)
    before = store.value(
        "route:defense", "context:war",
        "frontier:north", 4)

    update = store.update(record)

    assert update.value < before
    assert truth == TruthState(0.4, 0.6)


def test_context_mismatch_prevents_unqualified_conductance_reuse():
    store = ContextualConductanceStore()
    store.update(_record())
    store.update(_record(
        context="context:peace",
        frontier="frontier:south",
        generation=5))

    assert store.value(
        "route:defense", "context:war",
        "frontier:north", 4) != store.value(
            "route:defense", "context:unknown",
            "frontier:north", 4)
    try:
        store.unqualified_value("route:defense")
    except ValueError as error:
        assert "context-qualified" in str(error)
    else:
        raise AssertionError(
            "contextual conductance was reused unqualified")


def test_calibration_record_pairs_predicted_and_realized_relief():
    record = _record(realized=0.25)

    artifact = record.to_dict()

    assert artifact["predicted_relief"] == 0.7
    assert artifact["realized_relief"] == 0.25
    assert abs(record.relief_error + 0.45) < 1e-12
    assert artifact["relief_source"] == (
        "authoritative-turn-delta")


def test_selection_propensity_is_available_for_offpolicy_audit():
    record = _record(propensity=0.25)

    assert record.offpolicy_weight(
        "missing-at-random-given-context") == 4.0
    assert record.to_dict()["selection_propensity"] == 0.25
