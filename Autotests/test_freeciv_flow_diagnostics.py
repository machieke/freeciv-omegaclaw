"""Stage-S4 flow health and truth-preserving fallback gates."""

import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.flow_control import (  # noqa: E402
    DIAGNOSTIC_NAMES,
    FlowHealthMonitor,
    FlowHealthSample,
    FlowRepairPlanner,
)


def _sample(**changes):
    values = {
        "forward_total_mass": 1.0,
        "backward_total_mass": 1.0,
        "mass_error": 0.0,
        "balance_residual": 0.0,
        "projection_healthy": True,
        "local_cfl": 0.5,
        "cfl_rescaled": False,
        "advection_healthy": True,
        "bridge_overlap": 0.2,
        "probe_meet_rate": 0.5,
        "ess_fraction": 0.8,
        "clipped_fraction": 0.0,
        "path_diversity": 0.5,
        "probes_healthy": True,
        "feedback_ratio": 0.1,
        "pressure_peak": 1.0,
        "dual_converged": True,
        "integrality_gap": 1.0,
        "relaxed_value": 10.0,
        "packet_starvation_count": 0,
        "stale_view_lag": 0,
        "relief_mae": 0.1,
        "expected_normalization_hash": "normalization-hash",
        "observed_normalization_hash": "normalization-hash",
        "controller_overhead_ms": 100.0,
    }
    values.update(changes)
    return FlowHealthSample(**values)


def test_complete_healthy_report_covers_every_required_diagnostic():
    first = FlowHealthMonitor().evaluate(
        _sample(), require_complete=True)
    second = FlowHealthMonitor().evaluate(
        _sample(), require_complete=True)

    assert first.healthy
    assert first.complete
    assert tuple(row.name for row in first.readings) == (
        DIAGNOSTIC_NAMES)
    assert first.report_hash == second.report_hash


def test_cfl_rescaling_is_a_logged_repair_not_silent_failure():
    report = FlowHealthMonitor().evaluate(
        _sample(
            local_cfl=4.0, cfl_rescaled=True),
        require_complete=True)
    reading = next(
        row for row in report.readings
        if row.name == "local_cfl")

    assert report.healthy
    assert reading.status == "repaired"
    assert reading.reason == "velocity-rescaled-before-step"


def test_numerical_failure_selects_local_repair_first():
    report = FlowHealthMonitor().evaluate(
        _sample(
            mass_error=0.1,
            advection_healthy=False),
        require_complete=True)
    decision = FlowRepairPlanner().decide(report)

    assert not report.healthy
    assert decision.selected_action == (
        "local_numerical_repair")
    assert not decision.truth_mutation_allowed
    assert not decision.candidate_authority


def test_probe_lock_in_selects_exploration_feedback_repair():
    report = FlowHealthMonitor().evaluate(
        _sample(
            probe_meet_rate=0.0,
            path_diversity=0.0,
            probes_healthy=False),
        require_complete=True)
    decision = FlowRepairPlanner().decide(report)

    assert decision.selected_action == (
        "adjust_exploration_or_feedback")
    assert "probe_meet_rate" in (
        decision.unhealthy_diagnostics)


def test_stale_view_selects_patch_then_rebuild_then_fallback():
    report = FlowHealthMonitor().evaluate(
        _sample(stale_view_lag=2),
        require_complete=True)
    planner = FlowRepairPlanner()
    patch = planner.decide(report)
    rebuild = planner.decide(
        report, (patch.selected_action,))
    bridge = planner.decide(
        report, (
            patch.selected_action,
            rebuild.selected_action))
    scalar = planner.decide(
        report, (
            patch.selected_action,
            rebuild.selected_action,
            bridge.selected_action))

    assert patch.selected_action == (
        "apply_pending_topology_patches")
    assert rebuild.selected_action == (
        "rebuild_affected_view")
    assert bridge.fallback_mode == "bridge_scalar"
    assert scalar.fallback_mode == "scalar_v2"


def test_unknown_required_diagnostic_fails_closed():
    report = FlowHealthMonitor().evaluate(
        FlowHealthSample(),
        require_complete=True)
    decision = FlowRepairPlanner().decide(report)

    assert not report.complete
    assert not report.healthy
    assert set(report.unhealthy_names) == set(
        DIAGNOSTIC_NAMES)
    assert decision.selected_action == (
        "local_numerical_repair")


def test_unconverged_dual_and_normalization_drift_are_explicit():
    report = FlowHealthMonitor().evaluate(
        _sample(
            dual_converged=False,
            observed_normalization_hash="changed"),
        require_complete=True)
    readings = dict(
        (row.name, row) for row in report.readings)

    assert not report.healthy
    assert readings["dual_health"].recommended_response == (
        "suppress-economic-interpretation")
    assert readings["normalization_drift"].reason == (
        "normalization-contract-changed")
