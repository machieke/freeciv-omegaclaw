"""Control-facing evidence risk and selection-coverage gates."""

import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    EvidenceLedger,
    EvidenceToken,
    SelectionBiasMonitor,
)


def _ledger():
    ledger = EvidenceLedger()
    ledger.register(EvidenceToken(
        "shared", 1.0, 2.0, 1, source="scout-a"))
    ledger.register(EvidenceToken(
        "left", 1.0, 1.0, 1, source="scout-b"))
    ledger.register(EvidenceToken(
        "right", 0.0, 1.0, 1, source="scout-c"))
    return ledger


def test_probe_or_pressure_exposure_never_registers_evidence_token():
    ledger = EvidenceLedger()
    monitor = SelectionBiasMonitor()

    monitor.record_pressure("north", 12.0, "war")
    monitor.record_selection(
        "north", "probe:north", True, "war",
        reason="deterministic:probe-ranking")

    assert ledger.tokens == ()
    assert monitor.summaries()[0].pressure_exposure == 12.0


def test_overlap_risk_suppresses_duplicate_proof_operation():
    ledger = _ledger()

    summary = ledger.risk_summary(
        ("shared", "left"),
        ("shared", "right"), 1)

    assert summary.overlap_weight > 0.0
    assert summary.duplicate_suppression < 1.0
    assert summary.independent_source_count == 3


def test_audit_observation_budget_reaches_low_pressure_region():
    monitor = SelectionBiasMonitor()
    monitor.record_pressure("front", 10.0, "war")
    monitor.record_pressure("rear", 0.1, "war")

    selected = monitor.low_pressure_audit_regions("war", limit=1)
    monitor.record_selection(
        selected[0], "audit:rear", True, "war",
        reason="deterministic:low-pressure-audit",
        audit=True)

    assert selected == ("rear",)
    rear = next(
        row for row in monitor.summaries()
        if row.context_id == "war"
        and row.region_id == "rear")
    assert rear.audit_coverage == 1.0


def test_selection_coverage_metric_is_context_stratified():
    monitor = SelectionBiasMonitor()
    monitor.record_pressure("north", 5.0, "war")
    monitor.record_pressure("north", 1.0, "peace")
    monitor.record_evidence_update("north", 2.0, "war")
    monitor.record_evidence_update("north", 0.1, "peace")

    rows = monitor.summaries()

    assert {
        (row.context_id, row.pressure_exposure,
         row.evidence_update_weight)
        for row in rows
    } == {
        ("peace", 1.0, 0.1),
        ("war", 5.0, 2.0),
    }


def test_deterministic_selection_records_reason_instead_of_fake_probability():
    monitor = SelectionBiasMonitor()

    record = monitor.record_selection(
        "north", "observe:north", True, "war",
        propensity=None,
        reason="deterministic:highest-priority")

    assert record.propensity is None
    assert record.to_dict()["reason"] == (
        "deterministic:highest-priority")
    try:
        monitor.inverse_propensity_weight(
            record,
            assumption="missing-at-random-given-context")
    except ValueError as error:
        assert "deterministic" in str(error)
    else:
        raise AssertionError(
            "deterministic selection received fake propensity")
