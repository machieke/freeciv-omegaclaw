#!/usr/bin/env python3
"""Audit a paired GDO-5 engine cohort at the operation-mechanism boundary."""

import argparse
from collections import Counter, defaultdict
import glob
import hashlib
import json
import math
import os
import sys


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
for path in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.config import load as load_harness_config  # noqa: E402
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.events.validator import validate_file  # noqa: E402


TERMINAL_TYPES = frozenset((
    "operation_completed",
    "operation_failed",
    "operation_abandoned",
    "operation_expired",
))
ADVERSE_TERMINAL_TYPES = frozenset((
    "operation_failed",
    "operation_abandoned",
    "operation_expired",
))
LIFECYCLE_TYPES = frozenset((
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
))


def _fraction(numerator, denominator):
    return (
        None
        if not denominator
        else float(numerator)
        / float(denominator))


def _mean(values):
    return (
        None
        if not values
        else sum(values) / float(len(values)))


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    rank = max(
        0,
        int(math.ceil(
            float(fraction)
            * len(ordered))) - 1)
    return ordered[rank]


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _operation_id(event):
    value = event.get(
        "payload", {}).get(
            "operation_id")
    return (
        value
        if isinstance(value, str)
        and value
        else None)


def _unit_id(value):
    if isinstance(value, int):
        return value
    if (
            isinstance(value, str)
            and value.startswith("unit:")
            and value[5:].isdigit()):
        return int(value[5:])
    return None


def _required_participants(payload):
    return frozenset(
        participant.get("actor_id")
        for participant in
        payload.get("participants", ())
        if (
            isinstance(participant, dict)
            and participant.get(
                "required") is True
            and isinstance(
                participant.get(
                    "actor_id"), str)))


def _claimed_current_actors(payload):
    result = set()
    for claim in payload.get(
            "claims", ()):
        if not isinstance(claim, dict):
            continue
        resource = claim.get(
            "resource", {})
        if (
                claim.get("hardness")
                == "hard_current"
                and claim.get(
                    "exclusive") is True
                and isinstance(
                    resource, dict)
                and resource.get(
                    "kind") == "actor"
                and isinstance(
                    resource.get(
                        "owner_id"), str)):
            result.add(
                resource["owner_id"])
    return frozenset(result)


def _exclusive_claim_keys(payload):
    result = set()
    for claim in payload.get(
            "claims", ()):
        if (
                not isinstance(claim, dict)
                or claim.get(
                    "hardness")
                != "hard_current"
                or claim.get(
                    "exclusive") is not True):
            continue
        result.add(
            canonical_json_bytes({
                "resource":
                    claim.get("resource"),
                "window":
                    claim.get("window"),
            }))
    return result


def _material_estimate(payload):
    value = payload.get(
        "material_estimate")
    return (
        value
        if isinstance(value, dict)
        else {})


def _resolve_pending_losses(
        event, pending, resolved):
    if event.get("type") != (
            "state_snapshot"):
        return
    turn = int(
        event.get("turn", 0))
    units = event.get(
        "payload", {}).get(
            "own_state", {}).get(
                "units")
    if not isinstance(units, list):
        return
    present = frozenset(
        unit.get("unit_id")
        for unit in units
        if isinstance(unit, dict))
    remaining = []
    for row in pending:
        if row["turn"] == turn:
            row = dict(row)
            row["observation_snapshot_id"] = (
                event.get(
                    "payload", {}).get(
                        "snapshot_id"))
            row["realized_friendly_terminal_loss"] = (
                0.0
                if row["actor_unit_id"]
                in present
                else row[
                    "attacker_remaining_value"])
            row["resolution"] = (
                "actor-survived-current-step"
                if row["actor_unit_id"]
                in present
                else "actor-destroyed-current-step")
            resolved.append(row)
        else:
            remaining.append(row)
    pending[:] = remaining


def analyze_trace(events):
    """Return exact, order-sensitive mechanism observations for one game."""
    counts = Counter()
    selected = set()
    activated = set()
    committed = set()
    terminal = {
        event_type: set()
        for event_type in
        TERMINAL_TYPES
    }
    selected_targets = defaultdict(
        lambda: defaultdict(set))
    reservations = defaultdict(list)
    partial_activations = []
    nonpositive_activations = []
    authority_rows = []
    scheduler_latency_ms = []
    pending_losses = []
    resolved_losses = []
    for event in events:
        _resolve_pending_losses(
            event,
            pending_losses,
            resolved_losses)
        event_type = str(
            event.get("type", ""))
        payload = event.get(
            "payload", {})
        if event_type == (
                "metric_sample"):
            if (
                    payload.get("name")
                    == "combat_operation_scheduler_latency_ms"
                    and isinstance(
                        payload.get("value"),
                        (int, float))
                    and not isinstance(
                        payload.get("value"),
                        bool)):
                scheduler_latency_ms.append(
                    float(
                        payload["value"]))
            continue
        if event_type not in (
                LIFECYCLE_TYPES):
            continue
        operation_id = (
            _operation_id(event))
        if operation_id is None:
            continue
        counts[event_type] += 1
        snapshot_id = payload.get(
            "snapshot_id")
        if event_type == (
                "operation_proposed"):
            if payload.get(
                    "selected") is True:
                target_id = payload.get(
                    "target_id")
                if (
                        isinstance(snapshot_id, str)
                        and isinstance(
                            target_id, str)):
                    selected_targets[
                        snapshot_id][
                            target_id].add(
                                operation_id)
        elif event_type == (
                "operation_reserved"):
            if isinstance(
                    snapshot_id, str):
                reservations[
                    snapshot_id].append((
                        operation_id,
                        _exclusive_claim_keys(
                            payload)))
        elif event_type == (
                "operation_step_selected"):
            selected.add(
                operation_id)
        elif event_type == (
                "operation_activated"):
            activated.add(
                operation_id)
            required = (
                _required_participants(
                    payload))
            claimed = (
                _claimed_current_actors(
                    payload))
            if (
                    not required
                    or not required
                    <= claimed):
                partial_activations.append({
                    "claimed_current_actors":
                        sorted(claimed),
                    "operation_id":
                        operation_id,
                    "required_participants":
                        sorted(required),
                    "snapshot_id":
                        snapshot_id,
                })
            material = (
                _material_estimate(
                    payload))
            advantage = material.get(
                "expected_terminal_material_advantage",
                {}).get("lower")
            if (
                    not isinstance(
                        advantage,
                        (int, float))
                    or isinstance(
                        advantage, bool)
                    or float(advantage)
                    <= 0.0):
                nonpositive_activations.append({
                    "advantage_lower":
                        advantage,
                    "operation_id":
                        operation_id,
                    "snapshot_id":
                        snapshot_id,
                })
            authority_rows.append({
                "action_type": (
                    payload.get(
                        "next_action", {})
                    .get("action_type")),
                "operation_id":
                    operation_id,
                "operation_type":
                    payload.get(
                        "operation_type"),
                "policy_authority":
                    payload.get(
                        "policy_authority"),
                "snapshot_id":
                    snapshot_id,
            })
        elif event_type == (
                "operation_step_committed"):
            committed.add(
                operation_id)
            material = (
                _material_estimate(
                    payload))
            friendly = material.get(
                "expected_friendly_terminal_loss",
                {})
            actor_unit_id = _unit_id(
                payload.get("actor_id"))
            remaining_value = material.get(
                "attacker_remaining_value")
            expected_lower = friendly.get(
                "lower")
            expected_upper = friendly.get(
                "upper")
            if all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    for value in (
                        actor_unit_id,
                        remaining_value,
                        expected_lower,
                        expected_upper)):
                pending_losses.append({
                    "action_id":
                        payload.get(
                            "action_id"),
                    "actor_unit_id":
                        actor_unit_id,
                    "attacker_remaining_value":
                        float(
                            remaining_value),
                    "expected_friendly_terminal_loss_lower":
                        float(
                            expected_lower),
                    "expected_friendly_terminal_loss_upper":
                        float(
                            expected_upper),
                    "operation_id":
                        operation_id,
                    "source_snapshot_id":
                        snapshot_id,
                    "turn": int(
                        event.get(
                            "turn", 0)),
                })
        elif event_type in (
                TERMINAL_TYPES):
            terminal[
                event_type].add(
                    operation_id)
    duplicate_targets = []
    for snapshot_id, targets in sorted(
            selected_targets.items()):
        for target_id, operations in sorted(
                targets.items()):
            if len(operations) > 1:
                duplicate_targets.append({
                    "operation_ids":
                        sorted(operations),
                    "snapshot_id":
                        snapshot_id,
                    "target_id":
                        target_id,
                })
    hard_conflicts = []
    for snapshot_id, rows in sorted(
            reservations.items()):
        for left_index, (
                left_id,
                left_claims) in enumerate(
                    rows):
            for (
                    right_id,
                    right_claims) in rows[
                        left_index + 1:]:
                overlap = (
                    left_claims
                    & right_claims)
                if overlap:
                    hard_conflicts.append({
                        "left_operation_id":
                            left_id,
                        "overlap_count":
                            len(overlap),
                        "right_operation_id":
                            right_id,
                        "snapshot_id":
                            snapshot_id,
                    })
    completed = terminal[
        "operation_completed"]
    adverse = set().union(*(
        terminal[event_type]
        for event_type in
        ADVERSE_TERMINAL_TYPES))
    selected_completed = (
        selected & completed)
    activated_completed = (
        activated & completed)
    selected_adverse = (
        selected & adverse)
    activated_adverse = (
        activated & adverse)
    return {
        "authority_rows":
            authority_rows,
        "duplicate_selected_targets":
            duplicate_targets,
        "event_counts": {
            name: counts[name]
            for name in sorted(
                LIFECYCLE_TYPES)
        },
        "hard_current_reservation_conflicts":
            hard_conflicts,
        "immediate_terminal_loss": {
            "censored_commits": len(
                pending_losses),
            "observations":
                resolved_losses,
        },
        "lifecycle": {
            "activated_adverse":
                len(activated_adverse),
            "activated_completed":
                len(activated_completed),
            "activated_unique":
                len(activated),
            "committed_unique":
                len(committed),
            "selected_adverse":
                len(selected_adverse),
            "selected_completed":
                len(selected_completed),
            "selected_unique":
                len(selected),
        },
        "nonpositive_activations":
            nonpositive_activations,
        "partial_activations":
            partial_activations,
        "scheduler_latency_ms":
            scheduler_latency_ms,
    }


def _combine_arm(rows):
    lifecycle = Counter()
    event_counts = Counter()
    losses = []
    authority_rows = []
    scheduler_latency = []
    result = {
        "duplicate_selected_targets": [],
        "hard_current_reservation_conflicts": [],
        "nonpositive_activations": [],
        "partial_activations": [],
    }
    censored = 0
    for row in rows:
        lifecycle.update(
            row["lifecycle"])
        event_counts.update(
            row["event_counts"])
        losses.extend(
            row["immediate_terminal_loss"][
                "observations"])
        censored += row[
            "immediate_terminal_loss"][
                "censored_commits"]
        authority_rows.extend(
            row["authority_rows"])
        scheduler_latency.extend(
            row[
                "scheduler_latency_ms"])
        for key in (
                "duplicate_selected_targets",
                "hard_current_reservation_conflicts",
                "nonpositive_activations",
                "partial_activations"):
            result[key].extend(
                row[key])
    expected_lower = [
        row[
            "expected_friendly_terminal_loss_lower"]
        for row in losses
    ]
    expected_upper = [
        row[
            "expected_friendly_terminal_loss_upper"]
        for row in losses
    ]
    realized = [
        row[
            "realized_friendly_terminal_loss"]
        for row in losses
    ]
    realized_mean = _mean(
        realized)
    expected_upper_mean = _mean(
        expected_upper)
    calibration_residual = (
        None
        if (
            realized_mean is None
            or expected_upper_mean is None)
        else realized_mean
        - expected_upper_mean)
    selected_unique = lifecycle[
        "selected_unique"]
    activated_unique = lifecycle[
        "activated_unique"]
    result.update({
        "authority": {
            "action_types":
                dict(sorted(Counter(
                    row["action_type"]
                    for row in
                    authority_rows).items())),
            "operation_types":
                dict(sorted(Counter(
                    row["operation_type"]
                    for row in
                    authority_rows).items())),
            "policy_authority_values":
                dict(sorted(Counter(
                    str(row[
                        "policy_authority"])
                    for row in
                    authority_rows).items())),
            "row_count": len(
                authority_rows),
        },
        "event_counts":
            dict(sorted(
                event_counts.items())),
        "immediate_terminal_loss": {
            "calibration_residual_vs_expected_upper":
                calibration_residual,
            "censored_commits":
                censored,
            "expected_mean": {
                "lower":
                    _mean(expected_lower),
                "upper":
                    expected_upper_mean,
            },
            "observation_count":
                len(losses),
            "realized_mean":
                realized_mean,
            "scope":
                "immediate-terminal-destruction-only",
        },
        "lifecycle": {
            **dict(lifecycle),
            "activation_rate_per_selection":
                _fraction(
                    activated_unique,
                    selected_unique),
            "adverse_terminal_rate_per_activation":
                _fraction(
                    lifecycle[
                        "activated_adverse"],
                    activated_unique),
            "adverse_terminal_rate_per_selection":
                _fraction(
                    lifecycle[
                        "selected_adverse"],
                    selected_unique),
            "completion_rate_per_activation":
                _fraction(
                    lifecycle[
                        "activated_completed"],
                    activated_unique),
            "completion_rate_per_selection":
                _fraction(
                    lifecycle[
                        "selected_completed"],
                    selected_unique),
        },
        "scheduler_latency_ms": {
            "maximum":
                max(
                    scheduler_latency,
                    default=None),
            "p50":
                _percentile(
                    scheduler_latency,
                    0.50),
            "p95":
                _percentile(
                    scheduler_latency,
                    0.95),
            "positive_p95":
                _percentile(
                    [
                        value
                        for value in
                        scheduler_latency
                        if value > 0.0
                    ],
                    0.95),
            "positive_sample_count":
                sum(
                    value > 0.0
                    for value in
                    scheduler_latency),
            "sample_count":
                len(scheduler_latency),
        },
    })
    return result


def _load_events(path):
    with open(
            path,
            encoding="utf-8") as stream:
        return [
            json.loads(line)
            for line in stream
            if line.strip()]


def _cohort_event_paths(root, cohort, arm):
    pattern = os.path.join(
        root,
        "games",
        "impact_pair",
        cohort,
        arm,
        "e_full_loop",
        "*",
        "events.jsonl")
    return sorted(
        glob.glob(pattern))


def _predeclared_design(profile, cohort):
    config = load_harness_config(
        profile)
    row = config[
        "paired_impact"][
            "cohorts"][cohort]
    design = row.get(
        "mechanism_design")
    return (
        design
        if isinstance(design, dict)
        else None)


def _delta(treatment, baseline):
    if (
            treatment is None
            or baseline is None):
        return None
    return float(treatment) - float(
        baseline)


def run(
        cohort_root,
        profile,
        captured_replay_path):
    aggregate_path = os.path.join(
        cohort_root,
        "impact-aggregate.json")
    with open(
            aggregate_path,
            encoding="utf-8") as stream:
        aggregate = json.load(
            stream)
    cohort = aggregate.get(
        "design", {}).get(
            "cohort")
    if not isinstance(
            cohort, str):
        raise ValueError(
            "impact aggregate has no cohort identity")
    design = _predeclared_design(
        profile,
        cohort)
    declared_types = (
        tuple(design.get(
            "declared_operation_types", ()))
        if design is not None
        else (
            "attack_then_conditional_attack",))
    loss_design = (
        design.get(
            "friendly_terminal_loss", {})
        if design is not None
        else {})
    tolerance = loss_design.get(
        "adverse_shift_tolerance")
    tolerance_predeclared = (
        isinstance(tolerance, (int, float))
        and not isinstance(tolerance, bool)
        and float(tolerance) >= 0.0)
    event_paths = {
        arm: _cohort_event_paths(
            cohort_root,
            cohort,
            arm)
        for arm in (
            "baseline",
            "treatment")
    }
    expected_games = int(
        aggregate.get(
            "complete_pairs", 0))
    for arm, paths in event_paths.items():
        if len(paths) != expected_games:
            raise ValueError(
                "{} has {} traces, expected {}"
                .format(
                    arm,
                    len(paths),
                    expected_games))
    arm_results = {}
    trace_sources = []
    validation = Counter()
    for arm in (
            "baseline",
            "treatment"):
        rows = []
        for path in event_paths[arm]:
            result = validate_file(
                path)
            validation[
                "event_count"] += (
                    result.event_count)
            validation[
                "error_count"] += len(
                    result.errors)
            validation[
                "warning_count"] += len(
                    result.warnings)
            rows.append(
                analyze_trace(
                    _load_events(
                        path)))
            trace_sources.append({
                "arm": arm,
                "path": os.path.relpath(
                    path,
                    cohort_root),
                "sha256":
                    _sha256_file(path),
            })
        arm_results[arm] = (
            _combine_arm(rows))
    with open(
            captured_replay_path,
            encoding="utf-8") as stream:
        captured = json.load(
            stream)
    baseline = arm_results[
        "baseline"]
    treatment = arm_results[
        "treatment"]
    completion_delta = _delta(
        treatment["lifecycle"][
            "completion_rate_per_selection"],
        baseline["lifecycle"][
            "completion_rate_per_selection"])
    adverse_terminal_delta = _delta(
        treatment["lifecycle"][
            "adverse_terminal_rate_per_selection"],
        baseline["lifecycle"][
            "adverse_terminal_rate_per_selection"])
    loss_shift = _delta(
        treatment[
            "immediate_terminal_loss"][
                "calibration_residual_vs_expected_upper"],
        baseline[
            "immediate_terminal_loss"][
                "calibration_residual_vs_expected_upper"])
    captured_gates = captured.get(
        "gates", {})
    partial_activation_zero = (
        not baseline[
            "partial_activations"]
        and not treatment[
            "partial_activations"])
    hard_conflicts_zero = (
        not baseline[
            "hard_current_reservation_conflicts"]
        and not treatment[
            "hard_current_reservation_conflicts"])
    no_adverse_loss_shift = (
        tolerance_predeclared
        and loss_shift is not None
        and loss_shift
        <= float(tolerance)
        and treatment[
            "immediate_terminal_loss"][
                "censored_commits"] == 0)
    policy_limited = (
        treatment["authority"][
            "row_count"] > 0
        and set(
            treatment["authority"][
                "operation_types"])
        <= set(declared_types)
        and set(
            treatment["authority"][
                "action_types"])
        <= {"unit_attack"}
        and not treatment[
            "nonpositive_activations"])
    directional_benefit = (
        completion_delta is not None
        and completion_delta > 0.0
        and adverse_terminal_delta
        is not None
        and adverse_terminal_delta < 0.0)
    gates = {
        "captured_atomic_lower_duplicate_targeting_than_b1":
            bool(captured_gates.get(
                "atomic_lower_duplicate_targeting_than_independent")),
        "fresh_directional_mechanism_benefit":
            directional_benefit,
        "hard_current_reservation_conflicts_zero":
            hard_conflicts_zero,
        "no_adverse_friendly_terminal_loss_shift_beyond_predeclared_tolerance":
            no_adverse_loss_shift,
        "nonpositive_material_activations_zero":
            not treatment[
                "nonpositive_activations"],
        "partial_current_activation_zero":
            partial_activation_zero,
        "policy_authority_limited_to_declared_operation_types":
            policy_limited,
        "scheduler_p95_below_50_ms":
            (
                treatment[
                    "scheduler_latency_ms"][
                        "positive_p95"] is not None
                and treatment[
                    "scheduler_latency_ms"][
                        "positive_p95"] <= 50.0),
        "selected_target_conflicts_zero":
            (
                not baseline[
                    "duplicate_selected_targets"]
                and not treatment[
                    "duplicate_selected_targets"]),
        "source_freeze_passed":
            bool(aggregate.get(
                "source_freeze", {}).get(
                    "passed")),
        "trace_validation_passed":
            validation[
                "error_count"] == 0,
    }
    purpose = aggregate.get(
        "design", {}).get(
            "cohort_purpose")
    pilot_gate_passed = (
        purpose == "pilot"
        and all(gates.values()))
    result = {
        "arms": arm_results,
        "authority": {
            "claim_status": (
                "bounded-mechanism-pilot"
                if purpose == "pilot"
                else "diagnostic-only"),
            "policy_authority_eligible":
                pilot_gate_passed,
            "score_claim_eligible":
                False,
        },
        "captured_replay": {
            "path": os.path.relpath(
                captured_replay_path,
                REPO),
            "report_hash":
                captured.get(
                    "report_hash"),
            "sha256":
                _sha256_file(
                    captured_replay_path),
        },
        "cohort": {
            "aggregate_path":
                os.path.relpath(
                    aggregate_path,
                    cohort_root),
            "aggregate_sha256":
                _sha256_file(
                    aggregate_path),
            "complete_pairs":
                aggregate.get(
                    "complete_pairs"),
            "configuration_hash":
                aggregate.get(
                    "configuration_hash"),
            "id": cohort,
            "primary_score_delta":
                aggregate.get(
                    "primary_outcome"),
            "purpose": purpose,
            "source_freeze":
                aggregate.get(
                    "source_freeze"),
        },
        "deltas": {
            "adverse_terminal_rate_per_selection":
                adverse_terminal_delta,
            "completion_rate_per_selection":
                completion_delta,
            "friendly_terminal_loss_calibration_residual":
                loss_shift,
        },
        "gates": gates,
        "pilot_gate_passed":
            pilot_gate_passed,
        "predeclared_mechanism_design": {
            "declared_operation_types":
                list(declared_types),
            "friendly_terminal_loss":
                loss_design,
            "present":
                design is not None,
            "tolerance_predeclared":
                tolerance_predeclared,
        },
        "report_schema_version": "1.0",
        "trace_sources": trace_sources,
        "trace_validation": {
            "error_count":
                validation[
                    "error_count"],
            "event_count":
                validation[
                    "event_count"],
            "valid":
                validation[
                    "error_count"] == 0,
            "warning_count":
                validation[
                    "warning_count"],
        },
    }
    result["report_hash"] = (
        structural_hash(result))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cohort-root",
        required=True)
    parser.add_argument(
        "--profile",
        default=os.path.join(
            REPO,
            "profile",
            "freeciv_harness.yaml"))
    parser.add_argument(
        "--captured-replay",
        default=os.path.join(
            REPO,
            "benchmarks",
            "gdo",
            "gdo5_combat_operation_captured_diagnostic.json"))
    parser.add_argument(
        "--output",
        required=True)
    arguments = parser.parse_args()
    result = run(
        os.path.abspath(
            arguments.cohort_root),
        os.path.abspath(
            arguments.profile),
        os.path.abspath(
            arguments.captured_replay))
    output = os.path.abspath(
        arguments.output)
    with open(
            output,
            "w",
            encoding="utf-8") as stream:
        json.dump(
            result,
            stream,
            sort_keys=True,
            indent=2)
        stream.write("\n")
    print(json.dumps({
        "output": output,
        "pilot_gate_passed":
            result[
                "pilot_gate_passed"],
        "report_hash":
            result[
                "report_hash"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
