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


def _research_payload(operation_id, request_id):
    payload = _payload(
        operation_id,
        "gdo7b-research-enabling")
    payload.update({
        "claims": [{
            "hardness": "hard_current",
            "resource": {
                "kind": "research_slot",
                "owner_id": "player:0",
                "subresource": "current_target",
            },
        }],
        "deadline_turn": 10,
        "domain_estimate_request_id": request_id,
        "downstream_operation_id": "downstream-research",
        "requirement_set": {
            "requirement_set_id": "requirements-research",
            "role_ids": [
                "completion_forecast_supported",
                "immediate_dependency_researchable",
            ],
        },
    })
    return payload


def _research_estimate(request_id, immediate="Alphabet", **dependency):
    profile = {
        "currently_researchable_frontier": ["Alphabet"],
        "legacy_tech_want_applied": False,
        "propagation_mode": (
            "decomposed_ruleset_dependency_graph"),
    }
    profile.update(dependency)
    return _event("domain_estimate_emitted", {
        "estimator_id": "grounded_research_selection",
        "model_artifact": {
            "dependency_profile": profile,
            "immediate_target_tech": immediate,
        },
        "request_id": request_id,
    })


def test_trace_audit_proves_research_confirmation_contract():
    research = _research_payload(
        "operation-research", "request-research")
    completed = dict(
        research,
        downstream_ready=True,
        released_downstream_operation_id=(
            "downstream-research"),
        technology_ref="technology:Alphabet")

    result = analyze_trace([
        _research_estimate("request-research"),
        _event("operation_proposed", research),
        _event("operation_step_committed", research),
        _event("operation_completed", completed),
    ])

    contract = result["mechanisms"][
        "gdo7b-research-enabling"][
            "contract_observations"]
    assert contract["frontier_admission_unique"] == 1
    assert contract["decomposed_dependency_unique"] == 1
    assert contract["legacy_tech_want_free_unique"] == 1
    assert contract["completion_before_deadline_unique"] == 1
    assert contract["downstream_release_unique"] == 1
    assert result["semantic_violations"] == []


def test_trace_audit_rejects_off_frontier_and_slot_overallocation():
    first = _research_payload(
        "operation-research-a", "request-research-a")
    second = _research_payload(
        "operation-research-b", "request-research-b")

    result = analyze_trace([
        _research_estimate(
            "request-research-a",
            immediate="Writing",
            legacy_tech_want_applied=True),
        _research_estimate("request-research-b"),
        _event("operation_proposed", first),
        _event("operation_proposed", second),
    ])

    violations = result["semantic_violations"]
    assert any(
        value.endswith("off-frontier-research-admission")
        for value in violations)
    assert any(
        value.endswith("legacy-tech-want-applied")
        for value in violations)
    assert any(
        "hard-slot-overallocated" in value
        for value in violations)
    assert result["mechanisms"][
        "gdo7b-research-enabling"][
            "contract_observations"][
                "hard_slot_overallocation_violations"] == 2
