#!/usr/bin/env python3
"""Run the paired GDO-3 identity-resource shadow diagnostic."""

import argparse
import gc
import json
import os
import statistics
import sys
import time
from dataclasses import replace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks"),
        REPO):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import GroundedImpactPlanner  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


DEFAULT_FIXTURE = os.path.join(
    REPO, "benchmarks", "freeciv", "samples",
    "real_state_turn1.json")
DEFAULT_OUTPUT = os.path.join(
    REPO, "benchmarks", "gdo",
    "gdo3_resource_shadow_diagnostic.local.json")


def _percentile(rows, fraction):
    ordered = sorted(float(value) for value in rows)
    if not ordered:
        raise ValueError(
            "percentile requires observations")
    return ordered[
        int(float(fraction) * (
            len(ordered) - 1))]


def _summary(rows):
    return {
        "maximum_ms": max(rows),
        "mean_ms": statistics.mean(rows),
        "p50_ms": statistics.median(rows),
        "p95_ms": _percentile(
            rows, 0.95),
        "p99_ms": _percentile(
            rows, 0.99),
        "sample_count": len(rows),
    }


def _planner(resource_shadow):
    return GroundedImpactPlanner({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_resource_scheduler_enabled":
            bool(resource_shadow),
    })


def _load_fixture(path):
    with open(path, encoding="utf-8") as stream:
        payload = json.load(stream)
    snapshot = ProxyStateDTO.parse(
        "gdo3-resource-replay", 1,
        payload).to_snapshot()
    return payload, snapshot


def _replay_snapshot(snapshot, sample_index):
    identity = replace(
        snapshot.identity,
        source_seq=int(sample_index),
        state_hash=structural_hash({
            "base_state_hash":
                snapshot.identity.state_hash,
            "gdo3_replay_sample":
                int(sample_index),
        }))
    return replace(
        snapshot, identity=identity)


def _resource_pending(planner):
    return planner.last_control_decision.artifact[
        "ranker_artifact"][
            "identity_resource_schedule"]


def _resource_ranker(planner):
    return planner._pressure_ranker_v2


def _resource_identity(resource):
    return (
        resource["kind"],
        resource["scope"],
        resource["owner_id"],
        resource.get("subresource"),
    )


def _selected_hard_capacity_violations(artifact):
    schedule = artifact["exact"]
    selected = frozenset(
        schedule[
            "selected_operation_ids"])
    claims = {}
    for request in schedule["requests"]:
        if request[
                "operation_id"] not in selected:
            continue
        for claim in request["claims"]:
            if claim["hardness"] != (
                    "hard_current"):
                continue
            claims.setdefault(
                _resource_identity(
                    claim["resource"]),
                []).append(claim)
    capacities = {}
    for capacity in schedule[
            "capacities"]:
        capacities.setdefault(
            _resource_identity(
                capacity["resource"]),
            []).append(capacity)
    violations = []
    for resource, rows in sorted(
            claims.items()):
        capacity_rows = capacities.get(
            resource, ())
        points = sorted(set(
            value
            for row in (
                tuple(rows)
                + tuple(capacity_rows))
            for value in (
                row["window"][
                    "start_turn"],
                row["window"][
                    "end_turn_exclusive"])))
        for left, right in zip(
                points, points[1:]):
            active = [
                row for row in rows
                if (row["window"][
                        "start_turn"]
                    <= left
                    < row["window"][
                        "end_turn_exclusive"])]
            if not active:
                continue
            available = sum(
                row["quantity"]
                for row in capacity_rows
                if (row["window"][
                        "start_turn"]
                    <= left
                    and row["window"][
                        "end_turn_exclusive"]
                    >= right))
            allocated = sum(
                row["quantity"]
                for row in active)
            exclusive_conflict = (
                len(active) > 1
                and any(
                    row["exclusive"]
                    for row in active))
            if (available <= 0
                    or allocated > available
                    or exclusive_conflict):
                violations.append({
                    "allocated":
                        allocated,
                    "available":
                        available,
                    "end_turn_exclusive":
                        right,
                    "exclusive_conflict":
                        exclusive_conflict,
                    "resource":
                        list(resource),
                    "start_turn": left,
                })
    return violations


def _rejections_attributable(artifact):
    for row in artifact["exact"][
            "entries"]:
        if row["selected"]:
            if row["reason"] is not None:
                return False
            continue
        if not row["reason"]:
            return False
        if row["reason"] in (
                "missing-authoritative-capacity",
                "exclusive-resource-conflict",
                "resource-capacity-exceeded"
                ) and not row[
                    "conflict_resource_ids"]:
            return False
    return True


def _run_shadow(
        planner, snapshot):
    started = time.perf_counter()
    decision = planner.plan(snapshot)
    dispatch_ms = (
        time.perf_counter()
        - started) * 1000.0
    if decision is None:
        raise RuntimeError(
            "resource diagnostic fixture produced no decision")
    pending = _resource_pending(
        planner)
    planner.dispatch_resource_schedules()
    completed = (
        _resource_ranker(planner)
        .wait_for_resource_schedule(
            pending[
                "dispatch_batch_id"],
            timeout=5.0))
    if completed is None:
        raise RuntimeError(
            "resource shadow batch disappeared")
    full_loop_ms = (
        time.perf_counter()
        - started) * 1000.0
    return (
        decision, dispatch_ms,
        full_loop_ms, completed)


def run(fixture_path, iterations, warmup):
    payload, snapshot = _load_fixture(
        fixture_path)
    baseline = _planner(False)
    shadow = _planner(True)
    baseline_ms = []
    shadow_dispatch_ms = []
    shadow_full_loop_ms = []
    worker_ms = []
    order_equal = True
    action_equal = True
    scalar_schedule_equal = True
    packet_selection_equal = True
    exact_status = True
    hard_capacity_violations = []
    attributable_rejections = True
    completions = []
    last_snapshot = None
    last_completed = None
    repeat = None
    try:
        for index in range(int(warmup)):
            warm_snapshot = _replay_snapshot(
                snapshot,
                100000 + index)
            baseline.plan(
                warm_snapshot)
            _run_shadow(
                shadow, warm_snapshot)

        for index in range(int(iterations)):
            sample = _replay_snapshot(
                snapshot,
                200000 + index)
            last_snapshot = sample
            arms = (
                ("baseline", "shadow")
                if index % 2 == 0
                else ("shadow", "baseline"))
            decisions = {}
            for name in arms:
                gc.collect()
                if name == "baseline":
                    started = time.perf_counter()
                    decisions[name] = (
                        baseline.plan(sample))
                    baseline_ms.append(
                        (
                            time.perf_counter()
                            - started) * 1000.0)
                else:
                    (
                        decisions[name],
                        dispatch_ms,
                        full_loop_ms,
                        completed,
                    ) = _run_shadow(
                        shadow, sample)
                    shadow_dispatch_ms.append(
                        dispatch_ms)
                    shadow_full_loop_ms.append(
                        full_loop_ms)
                    worker_ms.append(
                        completed[
                            "worker_latency_ms"])
                    completions.append(
                        completed)
                    last_completed = completed
                    packet_selection_equal = bool(
                        packet_selection_equal
                        and completed[
                            "packet_exact_selection_equal"])
                    exact_status = bool(
                        exact_status
                        and completed["exact"][
                            "status"] == "exact")
                    attributable_rejections = bool(
                        attributable_rejections
                        and _rejections_attributable(
                            completed))
                    hard_capacity_violations.extend(
                        _selected_hard_capacity_violations(
                            completed))
            baseline_decision = decisions[
                "baseline"]
            shadow_decision = decisions[
                "shadow"]
            if (baseline_decision is None
                    or shadow_decision is None):
                raise RuntimeError(
                    "paired replay produced no decision")
            action_equal = bool(
                action_equal
                and canonical_json_bytes(
                    baseline_decision
                    .candidate.action)
                == canonical_json_bytes(
                    shadow_decision
                    .candidate.action))
            baseline_control = (
                baseline
                .last_control_decision)
            shadow_control = (
                shadow
                .last_control_decision)
            order_equal = bool(
                order_equal
                and baseline_control
                .ordered_candidate_keys
                == shadow_control
                .ordered_candidate_keys)
            scalar_schedule_equal = bool(
                scalar_schedule_equal
                and baseline_control.artifact[
                    "ranker_artifact"][
                        "schedule"]
                == shadow_control.artifact[
                    "ranker_artifact"][
                        "schedule"])

        repeat = _planner(True)
        _, _, _, repeated = _run_shadow(
            repeat, last_snapshot)
        semantic_determinism = bool(
            last_completed[
                "artifact_hash"]
            == repeated[
                "artifact_hash"])
        executor = (
            _resource_ranker(shadow)
            .resource_schedule_statistics())
    finally:
        baseline.close_domain_estimates()
        shadow.close_domain_estimates()
        if repeat is not None:
            repeat.close_domain_estimates()

    baseline_summary = _summary(
        baseline_ms)
    dispatch_summary = _summary(
        shadow_dispatch_ms)
    full_loop_summary = _summary(
        shadow_full_loop_ms)
    worker_summary = _summary(
        worker_ms)
    overhead_fraction = (
        dispatch_summary["p95_ms"]
        / baseline_summary["p95_ms"]
        - 1.0)
    overhead_ms = (
        dispatch_summary["p95_ms"]
        - baseline_summary["p95_ms"])
    result = {
        "baseline": baseline_summary,
        "claim_status":
            "diagnostic-only",
        "fixture": {
            "path": os.path.relpath(
                fixture_path, REPO),
            "payload_hash":
                structural_hash(
                    payload),
            "snapshot_id":
                snapshot.snapshot_id,
        },
        "gates": {
            "all_batches_completed":
                all(
                    row.get("status")
                    == "completed"
                    for row in completions),
            "all_rejections_attributable":
                attributable_rejections,
            "exact_schedule_status":
                exact_status,
            "hard_capacity_violations_absent":
                not hard_capacity_violations,
            "live_action_byte_identical":
                action_equal,
            "live_order_identical":
                order_equal,
            "no_live_authority":
                all(
                    row.get(
                        "shadow_only")
                    and not row.get(
                        "policy_authority")
                    for row in completions),
            "p95_absolute_overhead_within_50_ms":
                overhead_ms <= 50.0,
            "p95_relative_overhead_within_15_percent":
                overhead_fraction <= 0.15,
            "packet_exact_selection_equal":
                packet_selection_equal,
            "queue_capacity_not_exceeded":
                executor[
                    "capacity_rejection_count"] == 0,
            "scalar_schedule_identical":
                scalar_schedule_equal,
            "semantic_schedule_deterministic":
                semantic_determinism,
        },
        "hard_capacity_violations":
            hard_capacity_violations,
        "iterations": int(
            iterations),
        "measurement_protocol": {
            "alternating_arm_order": True,
            "fresh_snapshot_per_pair": True,
            "paired_gc_stabilization": True,
            "worker_completed_before_next_arm": True,
            "worker_cost_reported_separately": True,
        },
        "p95_absolute_overhead_ms":
            overhead_ms,
        "p95_overhead_fraction":
            overhead_fraction,
        "policy_authority": False,
        "resource_executor": executor,
        "schema_version": "1.0",
        "shadow_dispatch": dispatch_summary,
        "shadow_full_loop":
            full_loop_summary,
        "shadow_worker":
            worker_summary,
        "warmup_iterations": int(
            warmup),
    }
    result["passed"] = all(
        result["gates"].values())
    result["report_hash"] = (
        structural_hash(
            result))
    return result


def main():
    parser = argparse.ArgumentParser(
        description=__doc__)
    parser.add_argument(
        "--fixture",
        default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--iterations",
        type=int, default=100)
    parser.add_argument(
        "--warmup",
        type=int, default=10)
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    if arguments.iterations < 10:
        parser.error(
            "iterations must be at least 10")
    if arguments.warmup < 0:
        parser.error(
            "warmup must be non-negative")
    result = run(
        os.path.abspath(
            arguments.fixture),
        arguments.iterations,
        arguments.warmup)
    output = os.path.abspath(
        arguments.output)
    os.makedirs(
        os.path.dirname(output),
        exist_ok=True)
    with open(
            output, "w",
            encoding="utf-8") as stream:
        json.dump(
            result, stream,
            indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({
        "output": output,
        "passed": result["passed"],
        "report_hash":
            result["report_hash"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
