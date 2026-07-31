"""Tests for the GDO-5 paired engine-cohort mechanism audit."""

import os
import sys


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
for path in (
        REPO,
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from scripts.run_gdo_combat_cohort_audit import (  # noqa: E402
    _combine_arm,
    analyze_trace,
)


def _payload(
        operation_id="operation-a",
        snapshot_id="snapshot-a",
        selected=True,
        advantage=7.0):
    return {
        "actor_id": "unit:11",
        "claims": [
            {
                "exclusive": True,
                "hardness": "hard_current",
                "quantity": 1,
                "resource": {
                    "kind": "actor",
                    "owner_id": "unit:11",
                    "scope": "player:0",
                    "subresource": "whole_actor",
                },
                "window": {
                    "end_turn_exclusive": 8,
                    "start_turn": 7,
                },
            },
            {
                "exclusive": True,
                "hardness": "hard_current",
                "quantity": 1,
                "resource": {
                    "kind": "actor",
                    "owner_id": "unit:12",
                    "scope": "player:0",
                    "subresource": "whole_actor",
                },
                "window": {
                    "end_turn_exclusive": 8,
                    "start_turn": 7,
                },
            },
        ],
        "material_estimate": {
            "attacker_remaining_value": 10.0,
            "expected_friendly_terminal_loss": {
                "lower": 2.0,
                "upper": 3.0,
            },
            "expected_terminal_material_advantage": {
                "lower": advantage,
                "upper": advantage + 1.0,
            },
        },
        "next_action": {
            "action_type": "unit_attack",
            "actor_id": 11,
            "target": {"x": 4, "y": 5},
        },
        "operation_id": operation_id,
        "operation_type": "attack_then_conditional_attack",
        "participants": [
            {
                "actor_class": "unit",
                "actor_id": "unit:11",
                "required": True,
                "role": "primary_attacker",
            },
            {
                "actor_class": "unit",
                "actor_id": "unit:12",
                "required": True,
                "role": "conditional_attacker",
            },
        ],
        "policy_authority": True,
        "selected": selected,
        "snapshot_id": snapshot_id,
        "target_id": "unit:91@tile:37",
    }


def _event(
        event_type,
        payload=None,
        turn=7):
    return {
        "payload": payload or {},
        "turn": turn,
        "type": event_type,
    }


def test_trace_audit_resolves_safe_complete_operation():
    payload = _payload()
    events = [
        _event("operation_proposed", payload),
        _event("operation_reserved", payload),
        _event("operation_step_selected", payload),
        _event("operation_activated", payload),
        _event(
            "operation_step_committed",
            dict(
                payload,
                action_id="engine-action-a")),
        _event(
            "state_snapshot",
            {
                "own_state": {
                    "units": [
                        {"unit_id": 11},
                        {"unit_id": 12},
                    ],
                },
                "snapshot_id": "snapshot-b",
            }),
        _event("operation_completed", payload),
        _event(
            "metric_sample",
            {
                "name":
                    "combat_operation_scheduler_latency_ms",
                "unit": "ms",
                "value": 4.0,
            }),
    ]

    result = analyze_trace(events)

    assert result["partial_activations"] == []
    assert result["nonpositive_activations"] == []
    assert result[
        "hard_current_reservation_conflicts"] == []
    assert result[
        "duplicate_selected_targets"] == []
    assert result["lifecycle"] == {
        "activated_adverse": 0,
        "activated_completed": 1,
        "activated_unique": 1,
        "committed_unique": 1,
        "selected_adverse": 0,
        "selected_completed": 1,
        "selected_unique": 1,
    }
    loss = result[
        "immediate_terminal_loss"]
    assert loss["censored_commits"] == 0
    assert loss["observations"][0][
        "realized_friendly_terminal_loss"] == 0.0
    assert result[
        "scheduler_latency_ms"] == [4.0]


def test_trace_audit_detects_partial_nonpositive_conflicting_activation():
    first = _payload(
        advantage=0.0)
    first["claims"] = first[
        "claims"][:1]
    second = _payload(
        operation_id="operation-b")
    events = [
        _event(
            "operation_proposed",
            first),
        _event(
            "operation_proposed",
            second),
        _event(
            "operation_reserved",
            first),
        _event(
            "operation_reserved",
            second),
        _event(
            "operation_activated",
            first),
    ]

    result = analyze_trace(events)

    assert len(
        result[
            "partial_activations"]) == 1
    assert len(
        result[
            "nonpositive_activations"]) == 1
    assert len(
        result[
            "duplicate_selected_targets"]) == 1
    assert len(
        result[
            "hard_current_reservation_conflicts"]) == 1


def test_arm_combination_computes_lifecycle_and_loss_calibration():
    payload = _payload()
    safe = analyze_trace([
        _event(
            "operation_step_selected",
            payload),
        _event(
            "operation_activated",
            payload),
        _event(
            "operation_step_committed",
            payload),
        _event(
            "state_snapshot",
            {
                "own_state": {
                    "units": [
                        {"unit_id": 12},
                    ],
                },
                "snapshot_id": "snapshot-b",
            }),
        _event(
            "operation_completed",
            payload),
    ])

    combined = _combine_arm([safe])

    assert combined["lifecycle"][
        "completion_rate_per_selection"] == 1.0
    assert combined["lifecycle"][
        "adverse_terminal_rate_per_selection"] == 0.0
    assert combined[
        "immediate_terminal_loss"][
            "realized_mean"] == 10.0
    assert combined[
        "immediate_terminal_loss"][
            "calibration_residual_vs_expected_upper"] == 7.0


def test_unobserved_commit_remains_censored_across_later_turn_snapshot():
    payload = _payload()
    result = analyze_trace([
        _event(
            "operation_step_committed",
            payload),
        _event(
            "state_snapshot",
            {
                "own_state": {
                    "units": [],
                },
                "snapshot_id": "snapshot-next-turn",
            },
            turn=8),
    ])

    assert result[
        "immediate_terminal_loss"][
            "censored_commits"] == 1
    assert result[
        "immediate_terminal_loss"][
            "observations"] == []
