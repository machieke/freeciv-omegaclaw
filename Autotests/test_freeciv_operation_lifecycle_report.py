"""Causal ordering in the grounded operation lifecycle report."""

import importlib.util
import os


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))


def _module():
    path = os.path.join(
        REPO, "scripts",
        "analyze_gdo_operation_lifecycle.py")
    spec = (
        importlib.util
        .spec_from_file_location(
            "operation_lifecycle_report",
            path))
    module = (
        importlib.util
        .module_from_spec(spec))
    spec.loader.exec_module(
        module)
    return module


def _operation_event(
        event_type, operation_id,
        action, turn,
        reason=None,
        resolution=None):
    payload = {
        "deadline_turn":
            turn + 1,
        "next_action": action,
        "operation_id":
            operation_id,
        "operation_type":
            "move_defender_to_city",
        "reason_code":
            reason,
    }
    if resolution is not None:
        payload[
            "resolution_status"
        ] = resolution
    return {
        "event_id":
            "{}:{}".format(
                operation_id,
                event_type),
        "payload": payload,
        "turn": turn,
        "type": event_type,
    }


def _action_event(action, turn):
    return {
        "payload": {
            "action": action,
        },
        "turn": turn,
        "type": "action_sent",
    }


def test_report_does_not_credit_action_before_selection_as_commit():
    first = {
        "action_type": "unit_move",
        "actor_id": 7,
        "target": {
            "x": 2,
            "y": 3,
        },
    }
    second = {
        "action_type": "unit_move",
        "actor_id": 8,
        "target": {
            "x": 4,
            "y": 5,
        },
    }
    events = [
        _operation_event(
            "operation_proposed",
            "operation-late",
            first, 10),
        _action_event(first, 10),
        _operation_event(
            "operation_step_selected",
            "operation-late",
            first, 10),
        _operation_event(
            "operation_expired",
            "operation-late",
            first, 12,
            reason=(
                "operation-deadline-passed"),
            resolution=(
                "censored_operation_abort")),
        _operation_event(
            "operation_proposed",
            "operation-causal",
            second, 20),
        _operation_event(
            "operation_step_selected",
            "operation-causal",
            second, 20),
        _action_event(second, 20),
        _operation_event(
            "operation_step_committed",
            "operation-causal",
            second, 20),
        _operation_event(
            "operation_completed",
            "operation-causal",
            second, 21,
            reason=(
                "completion-predicate-satisfied"),
            resolution=(
                "resolved_success")),
    ]

    report = _module().analyze(
        events)

    overlap = report[
        "action_overlap"]
    assert overlap[
        "selection_instances_with_exact_action_before_selection"
    ] == 1
    assert overlap[
        "selection_instances_with_exact_action_after_selection"
    ] == 1
    assert report[
        "unique_operation_counts"][
            "operation_step_selected"
    ] == 2
    assert report[
        "unique_operation_counts"][
            "operation_step_committed"
    ] == 1
    assert report["funnel"][
        "commit_rate_per_unique_selection"
    ] == 0.5
    assert report["funnel"][
        "completion_rate_per_commit"
    ] == 1.0
    assert report["funnel"][
        "terminal_observation_rate_per_unique_selection"
    ] == 1.0
