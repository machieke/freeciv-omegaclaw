"""GDO-7A bounded production-persistence pilot audit contracts."""

import hashlib
import os
import sys


REPO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from run_gdo_production_persistence_pilot_audit import (  # noqa: E402
    _combine,
    analyze_trace,
)
from freeciv_agent.events.schema import canonical_json_bytes


def _event(event_type, payload, turn=8):
    return {
        "type": event_type,
        "turn": turn,
        "payload": {
            "mechanism": "gdo7a-production-enabling",
            "operation_id": "operation-production",
            **payload,
        },
    }


def _guard_payload(**overrides):
    protected = {
        "action_type": "city_production",
        "city_id": 103,
        "production_kind": 6,
        "production_value": 10,
    }
    excluded = {
        "action_type": "city_production",
        "city_id": 103,
        "production_kind": 3,
        "production_value": 14,
    }
    payload = {
        "actor_id": "city:103",
        "authority_effect": (
            "exclude-competing-city-production-switches"),
        "deadline_turn": 20,
        "excluded_action_ids": [hashlib.sha256(
            canonical_json_bytes(excluded)).hexdigest()],
        "excluded_actions": [excluded],
        "next_action": protected,
        "persistence_maximum_remaining_turns": 12,
        "persistence_threat_radius": 3,
        "policy_authority": True,
        "production_persistence_safety": {
            "city_disorder": False,
            "city_had_famine": False,
            "competing_active_operation_count": 1,
            "current_production_kind": 6,
            "current_production_value": 10,
            "food_surplus": 2.0,
            "future_gold_upkeep": 1,
            "gold": 20,
            "operating_gold_per_turn": 2,
            "remaining_turns": 4,
            "shield_surplus": 3.0,
            "visible_threat_count": 0,
        },
        "projected_completion_turn": 12,
        "protected_city_id": 103,
        "reason_code": (
            "bounded-production-persistence-authority"),
        "shadow_only": False,
        "snapshot_id": "snapshot-8",
    }
    payload.update(overrides)
    return payload


def test_trace_audit_accepts_in_scope_guard_and_completion():
    events = [
        _event("operation_proposed", {}),
        _event("operation_step_committed", {}),
        _event("operation_step_revalidated", {
            "next_action": _guard_payload()["next_action"],
            "state": "step_revalidated",
            "step_index": 1,
        }),
        _event("operation_step_selected", _guard_payload()),
        _event("operation_completed", {}, turn=12),
    ]

    result = analyze_trace(events)

    assert result["committed_unique"] == 1
    assert result["completed_unique"] == 1
    assert result["guarded_unique"] == 1
    assert result["guarded_diverged_unique"] == 0
    assert result["scope_violations"] == []


def test_trace_audit_rejects_unsafe_guard_and_guarded_divergence():
    events = [
        _event("operation_proposed", {}),
        _event("operation_step_committed", {}),
        _event("operation_step_revalidated", {
            "next_action": _guard_payload()["next_action"],
            "state": "step_revalidated",
            "step_index": 1,
        }),
        _event("operation_step_selected", _guard_payload(
            production_persistence_safety={
                **_guard_payload()[
                    "production_persistence_safety"],
                "visible_threat_count": 1,
            })),
        _event("operation_blocked", {
            "reason_code": (
                "production-target-diverged-before-product-observation"),
        }),
    ]

    result = analyze_trace(events)

    assert result["guarded_diverged_unique"] == 1
    assert result["scope_violations"][0]["reasons"] == [
        "visible-threat-in-radius"]


def test_arm_combination_uses_unique_operation_rates_per_trace():
    completed = analyze_trace([
        _event("operation_proposed", {}),
        _event("operation_step_committed", {}),
        _event("operation_completed", {}),
    ])
    diverged = analyze_trace([
        _event("operation_proposed", {}),
        _event("operation_step_committed", {}),
        _event("operation_blocked", {
            "reason_code": (
                "production-target-diverged-before-product-observation"),
        }),
    ])

    result = _combine((completed, diverged))

    assert result["committed_unique"] == 2
    assert result["completed_products_per_game"] == 0.5
    assert result["completion_rate_per_commit"] == 0.5
    assert result["queue_divergence_rate_per_commit"] == 0.5
