"""GDO-7 production/research fresh-cohort audit contracts."""

import os
import sys


REPO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from run_gdo_enabling_cohort_audit import (  # noqa: E402
    _combine,
    analyze_trace,
)


def _event(event_type, payload):
    return {
        "type": event_type,
        "turn": 4,
        "payload": dict(payload),
    }


def _payload(
        operation_id="operation-production",
        mechanism="gdo7a-production-enabling"):
    return {
        "claims": [{
            "hardness": "hard_current",
        }],
        "domain_estimate_request_id": "request-1",
        "mechanism": mechanism,
        "operation_id": operation_id,
        "policy_authority": False,
        "requirement_set": {
            "requirement_set_id": "requirements-1",
        },
        "shadow_only": True,
    }


def test_trace_audit_separates_production_and_research_lifecycles():
    production = _payload()
    research = _payload(
        "operation-research",
        "gdo7b-research-enabling")
    events = [
        _event("domain_estimate_emitted", {
            "estimator_id":
                "grounded_city_production_queue",
        }),
        _event("domain_estimate_emitted", {
            "estimator_id":
                "grounded_research_selection",
        }),
        _event("operation_proposed", production),
        _event("operation_reserved", production),
        _event("operation_step_committed", production),
        _event("resource_claim_reserved", production),
        _event("operation_completed", dict(
            production,
            product_ref="unit:10")),
        _event("operation_proposed", research),
        _event("operation_reserved", research),
        _event("operation_step_committed", research),
        _event("operation_blocked", dict(
            research,
            reason_code=(
                "research-beaker-output-stalled"))),
        _event("operation_completed", dict(
            research,
            technology_ref=(
                "technology:Alphabet"))),
    ]

    result = analyze_trace(events)

    production_result = result["mechanisms"][
        "gdo7a-production-enabling"]
    research_result = result["mechanisms"][
        "gdo7b-research-enabling"]
    assert production_result["proposed_unique"] == 1
    assert production_result["committed_unique"] == 1
    assert production_result["completed_unique"] == 1
    assert research_result["proposed_unique"] == 1
    assert research_result["committed_unique"] == 1
    assert research_result["completed_unique"] == 1
    assert research_result["reason_codes"][
        "research-beaker-output-stalled"] == 1
    assert result["duplicate_proposals"] == []
    assert result["malformed_proposals"] == []


def test_arm_combination_reports_attribution_completion_and_censoring():
    payload = _payload()
    completed = analyze_trace([
        _event("operation_proposed", payload),
        _event("operation_step_committed", payload),
        _event("operation_completed", payload),
    ])
    censored = analyze_trace([
        _event("operation_proposed", dict(
            payload,
            operation_id="operation-production-2")),
    ])

    result = _combine((completed, censored))
    production = result["mechanisms"][
        "gdo7a-production-enabling"]

    assert production["proposed_unique"] == 2
    assert production["committed_unique"] == 1
    assert production["completed_unique"] == 1
    assert production["attribution_rate_per_proposal"] == 0.5
    assert production["completion_rate_per_commit"] == 1.0
    assert production["terminal_coverage"] == 0.5
    assert production["nonterminal_at_trace_end"] == 1
