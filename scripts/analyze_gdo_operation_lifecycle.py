#!/usr/bin/env python3
"""Summarize the causal operation lifecycle funnel in an engine trace."""

import argparse
from collections import Counter
import hashlib
import json
import os
import sys


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SRC = os.path.join(
    REPO, "src")
if SRC not in sys.path:
    sys.path.insert(
        0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.events.validator import (  # noqa: E402
    validate_file,
)


LIFECYCLE_TYPES = (
    "operation_proposed",
    "operation_reserved",
    "operation_step_selected",
    "operation_activated",
    "operation_step_revalidated",
    "operation_step_committed",
    "operation_completed",
    "operation_failed",
    "operation_abandoned",
    "operation_expired",
    "operation_blocked",
)

TERMINAL_TYPES = frozenset((
    "operation_completed",
    "operation_failed",
    "operation_abandoned",
    "operation_expired",
))


def _fraction(numerator, denominator):
    return (
        None
        if not denominator
        else float(numerator)
        / float(denominator))


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(
                1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _operation_id(event):
    value = event.get(
        "payload", {}).get(
            "operation_id")
    return value if isinstance(
        value, str) and value else None


def analyze(events):
    """Return order-sensitive diagnostic counts without causal inference."""
    counts = Counter()
    by_type = Counter()
    terminal_reasons = Counter()
    resolution_statuses = Counter()
    operation_events = {}
    action_rows = []
    indexed_events = []
    for index, event in enumerate(
            events):
        event_type = str(
            event.get("type", ""))
        if event_type == (
                "action_sent"):
            action = event.get(
                "payload", {}).get(
                "action")
            if isinstance(action, dict):
                action_rows.append((
                    index,
                    canonical_json_bytes(
                        action),
                    int(
                        event.get(
                            "turn", 0))))
        if event_type not in (
                LIFECYCLE_TYPES):
            continue
        operation_id = (
            _operation_id(event))
        if operation_id is None:
            continue
        counts[event_type] += 1
        payload = event[
            "payload"]
        operation_type = str(
            payload.get(
                "operation_type")
            or "unknown")
        by_type[(
            event_type,
            operation_type)] += 1
        if event_type in (
                TERMINAL_TYPES):
            terminal_reasons[(
                event_type,
                str(
                    payload.get(
                        "reason_code")
                    or "none"))] += 1
        resolution = payload.get(
            "resolution_status")
        if isinstance(
                resolution, str):
            resolution_statuses[
                resolution] += 1
        operation_events.setdefault(
            operation_id, []).append(
                (index, event))
        indexed_events.append(
            (index, event))
    unique = {}
    for event_type in (
            LIFECYCLE_TYPES):
        unique[event_type] = sum(
            any(
                event["type"]
                == event_type
                for _, event
                in rows)
            for rows in
            operation_events.values())
    selected_instances = []
    for index, event in (
            indexed_events):
        if event["type"] != (
                "operation_step_selected"):
            continue
        operation_id = (
            _operation_id(event))
        payload = event["payload"]
        action = payload.get(
            "next_action")
        if not isinstance(
                action, dict):
            continue
        action_key = canonical_json_bytes(
            action)
        rows = operation_events[
            operation_id]
        terminal_indexes = [
            row_index
            for row_index, row
            in rows
            if row["type"]
            in TERMINAL_TYPES
            and row_index > index]
        limit = (
            min(terminal_indexes)
            if terminal_indexes
            else len(events))
        before = [
            row for row in action_rows
            if row[0] < index
            and row[2] == int(
                event.get(
                    "turn", 0))
            and row[1] == action_key]
        after = [
            row for row in action_rows
            if index < row[0] < limit
            and row[1] == action_key]
        selected_instances.append({
            "action_matches_after_selection":
                len(after),
            "action_matches_before_selection":
                len(before),
            "deadline_turn":
                payload.get(
                    "deadline_turn"),
            "operation_id":
                operation_id,
            "operation_type":
                payload.get(
                    "operation_type"),
            "selection_event_id":
                event.get(
                    "event_id"),
            "selection_turn": int(
                event.get(
                    "turn", 0)),
        })
    selected_unique = unique[
        "operation_step_selected"]
    committed_unique = unique[
        "operation_step_committed"]
    completed_unique = unique[
        "operation_completed"]
    terminal_unique = sum(
        any(
            event["type"]
            in TERMINAL_TYPES
            for _, event in rows)
        for rows in
        operation_events.values())
    selected_after_overlap = sum(
        bool(row[
            "action_matches_after_selection"])
        for row in
        selected_instances)
    selected_before_overlap = sum(
        bool(row[
            "action_matches_before_selection"])
        for row in
        selected_instances)
    return {
        "action_overlap": {
            "selection_instances_with_exact_action_after_selection":
                selected_after_overlap,
            "selection_instances_with_exact_action_before_selection":
                selected_before_overlap,
            "warning":
                "An action before selection is diagnostic late overlap, not an operation commit.",
        },
        "by_operation_type": [
            {
                "count": count,
                "event_type":
                    event_type,
                "operation_type":
                    operation_type,
            }
            for (
                event_type,
                operation_type), count
            in sorted(
                by_type.items())
        ],
        "event_counts": {
            name: counts[name]
            for name in
            LIFECYCLE_TYPES
        },
        "funnel": {
            "commit_rate_per_unique_selection":
                _fraction(
                    committed_unique,
                    selected_unique),
            "completion_rate_per_commit":
                _fraction(
                    completed_unique,
                    committed_unique),
            "completion_rate_per_unique_selection":
                _fraction(
                    completed_unique,
                    selected_unique),
            "terminal_observation_rate_per_unique_selection":
                _fraction(
                    terminal_unique,
                    selected_unique),
        },
        "resolution_status_counts":
            dict(sorted(
                resolution_statuses
                .items())),
        "selected_instances":
            selected_instances,
        "terminal_reason_counts": [
            {
                "count": count,
                "event_type":
                    event_type,
                "reason_code":
                    reason_code,
            }
            for (
                event_type,
                reason_code), count
            in sorted(
                terminal_reasons.items())
        ],
        "unique_operation_counts": {
            name: unique[name]
            for name in
            LIFECYCLE_TYPES
        },
    }


def run(
        event_path, manifest_path):
    validation = validate_file(
        event_path)
    if not validation.valid:
        raise ValueError(
            "source event trace is invalid")
    with open(
            event_path,
            encoding="utf-8") as stream:
        events = [
            json.loads(line)
            for line in stream
            if line.strip()]
    with open(
            manifest_path,
            encoding="utf-8") as stream:
        manifest = json.load(
            stream)
    diagnostic = analyze(events)
    result = {
        "authority": {
            "claim_status":
                "engine-lifecycle-diagnostic-only",
            "policy_authority_eligible":
                False,
            "score_claim_eligible":
                False,
        },
        "configuration_hash":
            structural_hash({
                "impact_policy":
                    manifest.get(
                        "impact_policy"),
                "ruleset":
                    manifest.get(
                        "ruleset"),
                "turn_limit":
                    manifest.get(
                        "turn_limit"),
            }),
        "diagnostic":
            diagnostic,
        "engine": {
            "attempt_id":
                manifest.get(
                    "attempt_id"),
            "condition_id":
                manifest.get(
                    "condition_id"),
            "manifest_identity":
                manifest.get(
                    "manifest_identity"),
            "seed": manifest.get(
                "seed"),
            "turn_limit":
                manifest.get(
                    "turn_limit"),
        },
        "event_validation": {
            "error_count": len(
                validation.errors),
            "event_count":
                validation.event_count,
            "valid": validation.valid,
            "warning_count": len(
                validation.warnings),
        },
        "gates": {
            "at_least_one_committed_operation":
                diagnostic[
                    "unique_operation_counts"][
                        "operation_step_committed"]
                > 0,
            "at_least_one_completed_operation":
                diagnostic[
                    "unique_operation_counts"][
                        "operation_completed"]
                > 0,
            "positive_completion_delta_proven":
                False,
            "selected_operations_receive_terminal_observation":
                diagnostic["funnel"][
                    "terminal_observation_rate_per_unique_selection"]
                == 1.0,
        },
        "report_schema_version":
            "1.0",
        "source_event_trace_sha256":
            _sha256_file(
                event_path),
    }
    result["report_hash"] = (
        structural_hash(
            result))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--events", required=True)
    parser.add_argument(
        "--manifest", required=True)
    parser.add_argument(
        "--output", required=True)
    arguments = parser.parse_args()
    result = run(
        os.path.abspath(
            arguments.events),
        os.path.abspath(
            arguments.manifest))
    output = os.path.abspath(
        arguments.output)
    with open(
            output, "w",
            encoding="utf-8") as stream:
        json.dump(
            result, stream,
            sort_keys=True,
            indent=2)
        stream.write("\n")
    print(json.dumps({
        "output": output,
        "report_hash":
            result["report_hash"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
