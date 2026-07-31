"""Tests for the GDO-4 paired engine-cohort mechanism audit."""

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

from scripts.run_gdo_city_defense_cohort_audit import (  # noqa: E402
    _combine_arm,
    analyze_trace,
)


def _payload(
        operation_id="operation-a",
        operation_type="move_defender_to_city",
        actor_id="11",
        snapshot_id="snapshot-a",
        policy_authority=True):
    return {
        "actor_id": actor_id,
        "claims": [{
            "exclusive": True,
            "hardness": "hard_current",
            "quantity": 1,
            "resource": {
                "kind": "actor",
                "owner_id":
                    "unit:{}".format(
                        actor_id),
                "scope": "player:0",
                "subresource": "whole_actor",
            },
            "window": {
                "end_turn_exclusive": 8,
                "start_turn": 7,
            },
        }],
        "next_action": {
            "action_type":
                "unit_move",
            "actor_id":
                int(actor_id),
            "target": {
                "x": 4,
                "y": 5,
            },
        },
        "operation_id":
            operation_id,
        "operation_type":
            operation_type,
        "policy_authority":
            policy_authority,
        "reason_code": None,
        "selected": True,
        "snapshot_id":
            snapshot_id,
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


def _snapshot(
        snapshot_id,
        city_ids,
        turn):
    return _event(
        "state_snapshot", {
            "own_state": {
                "cities": [
                    {"city_id": city_id}
                    for city_id in
                    city_ids
                ],
            },
            "snapshot_id":
                snapshot_id,
        },
        turn=turn)


def test_trace_audit_resolves_covered_safe_defense_response():
    payload = _payload()
    events = [
        _snapshot(
            "snapshot-0",
            (101,), 6),
        _event(
            "operation_proposed",
            payload),
        _event(
            "operation_reserved",
            payload),
        _event(
            "operation_step_selected",
            payload),
        _event(
            "operation_step_selected",
            payload),
        _event(
            "operation_activated",
            payload),
        _event(
            "operation_completed",
            payload),
        _event(
            "metric_sample", {
                "labels": {
                    "authority_kind":
                        "city_defense",
                    "changed_winner":
                        "true",
                    "operation_type":
                        "move_defender_to_city",
                },
                "name":
                    "operation_authority_selection",
                "value": 1.0,
            }),
        _event(
            "metric_sample", {
                "name":
                    "city_defense_authority_preparation_latency_ms",
                "value": 4.0,
            }),
        _event(
            "metric_sample", {
                "name":
                    "turn_full_loop_latency_ms",
                "value": 20.0,
            }),
        _snapshot(
            "snapshot-1",
            (101,), 8),
    ]

    result = analyze_trace(
        events)

    assert result[
        "city_losses"] == []
    assert result[
        "hard_current_reservation_conflicts"] == []
    assert result[
        "sole_defender_violations"] == []
    assert result[
        "unsupported_authority"] == []
    assert result["lifecycle"][
        "selected_response_turns"] == 2
    assert result["lifecycle"][
        "activated_response_turns"] == 1
    assert result["lifecycle"][
        "uncovered_threat_turns"] == 1
    assert result[
        "winner_changing_rows"] == [{
            "authority_kind":
                "city_defense",
            "operation_type":
                "move_defender_to_city",
            "typed": True,
        }]
    assert result[
        "preparation_latency_ms"] == [
            4.0]
    assert result[
        "full_loop_latency_ms"] == [
            20.0]


def test_trace_audit_detects_city_loss_conflict_and_sole_defender_move():
    move = _payload()
    other = _payload(
        operation_id="operation-b")
    protected = _payload(
        operation_id="operation-hold",
        operation_type=(
            "hold_sole_defender"),
        policy_authority=False)
    protected["next_action"] = None
    protected["reason_code"] = (
        "protected-constraint")
    events = [
        _snapshot(
            "snapshot-0",
            (101, 102), 6),
        _event(
            "operation_proposed",
            protected),
        _event(
            "operation_reserved",
            move),
        _event(
            "operation_reserved",
            other),
        _event(
            "operation_activated",
            move),
        _snapshot(
            "snapshot-1",
            (101,), 8),
    ]

    result = analyze_trace(
        events)

    assert [
        row["city_id"]
        for row in
        result["city_losses"]
    ] == [102]
    assert len(
        result[
            "hard_current_reservation_conflicts"]) == 1
    assert len(
        result[
            "sole_defender_violations"]) == 1


def test_arm_combination_computes_completion_coverage_and_latency():
    payload = _payload()
    row = analyze_trace([
        _event(
            "operation_step_selected",
            payload),
        _event(
            "operation_activated",
            payload),
        _event(
            "operation_completed",
            payload),
        _event(
            "metric_sample", {
                "labels": {
                    "authority_kind":
                        "city_defense",
                    "changed_winner":
                        "true",
                    "operation_type":
                        "move_defender_to_city",
                },
                "name":
                    "operation_authority_selection",
                "value": 1.0,
            }),
        _event(
            "metric_sample", {
                "name":
                    "city_defense_authority_preparation_latency_ms",
                "value": 6.0,
            }),
        _event(
            "metric_sample", {
                "name":
                    "turn_full_loop_latency_ms",
                "value": 30.0,
            }),
    ])

    combined = _combine_arm(
        [row])

    assert combined[
        "lifecycle"][
            "completion_rate_per_selection"] == 1.0
    assert combined[
        "typed_winner_changing_coverage"][
            "coverage"] == 1.0
    assert combined[
        "preparation_latency_ms"][
            "p95"] == 6.0
    assert combined[
        "full_loop_latency_ms"][
            "p95"] == 30.0
