#!/usr/bin/env python3
"""Run the GDO-1 paired shadow replay and latency diagnostic."""

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
from freeciv_agent.pressure import ImpactPressureRankerV2  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


DEFAULT_FIXTURE = os.path.join(
    REPO, "benchmarks", "freeciv", "samples",
    "real_state_turn1.json")
DEFAULT_OUTPUT = os.path.join(
    REPO, "benchmarks", "gdo",
    "gdo1_shadow_diagnostic.local.json")


def _percentile(rows, fraction):
    ordered = sorted(float(value) for value in rows)
    if not ordered:
        raise ValueError("percentile requires observations")
    index = int(float(fraction) * (len(ordered) - 1))
    return ordered[index]


def _summary(rows):
    return {
        "maximum_ms": max(rows),
        "mean_ms": statistics.mean(rows),
        "p50_ms": statistics.median(rows),
        "p95_ms": _percentile(rows, 0.95),
        "p99_ms": _percentile(rows, 0.99),
        "sample_count": len(rows),
    }


def _load_fixture(path):
    with open(path, encoding="utf-8") as stream:
        payload = json.load(stream)
    snapshot = ProxyStateDTO.parse(
        "gdo1-shadow-replay", 1,
        payload).to_snapshot()
    candidates = GroundedImpactPlanner({
        "pressure_enabled": False,
    }).candidates(snapshot)
    return payload, snapshot, candidates


def _domain_readout(artifact):
    authority_counts = {}
    estimator_counts = {}
    abstention_counts = {}
    parity_counts = {}
    for row in artifact.get(
            "estimates", ()):
        estimate = row["estimate"]
        authority = estimate[
            "authority"]
        estimator = "{}/{}".format(
            estimate["estimator_id"],
            estimate[
                "estimator_version"])
        authority_counts[authority] = (
            authority_counts.get(
                authority, 0) + 1)
        estimator_counts[estimator] = (
            estimator_counts.get(
                estimator, 0) + 1)
        reason = estimate.get(
            "abstention_reason")
        if reason:
            abstention_counts[reason] = (
                abstention_counts.get(
                    reason, 0) + 1)
        artifact_value = estimate.get(
            "model_artifact")
        if isinstance(
                artifact_value, dict):
            parity = artifact_value.get(
                "parity_status")
            if parity:
                parity_counts[parity] = (
                    parity_counts.get(
                        parity, 0) + 1)
    return {
        "abstention_reason_counts":
            dict(sorted(
                abstention_counts.items())),
        "authority_counts":
            dict(sorted(
                authority_counts.items())),
        "estimator_counts":
            dict(sorted(
                estimator_counts.items())),
        "parity_status_counts":
            dict(sorted(
                parity_counts.items())),
    }


def _replay_snapshot(snapshot, sample_index):
    identity = replace(
        snapshot.identity,
        source_seq=int(sample_index),
        state_hash=structural_hash({
            "base_state_hash":
                snapshot.identity.state_hash,
            "gdo_replay_sample":
                int(sample_index),
        }))
    return replace(
        snapshot, identity=identity)


def run(fixture_path, iterations, warmup):
    payload, snapshot, candidates = _load_fixture(
        fixture_path)
    ruleset_digest = structural_hash({
        "fixture": os.path.relpath(
            fixture_path, REPO),
        "ruleset_ready": snapshot.ruleset_ready,
        "schema": "gdo-fixture-ruleset/1.0",
    })
    baseline = ImpactPressureRankerV2()
    shadow = ImpactPressureRankerV2(
        domain_estimates_enabled=True,
        ruleset_digest=ruleset_digest)
    baseline_ms = []
    shadow_dispatch_ms = []
    shadow_full_loop_ms = []
    worker_ms = []
    queue_delay_ms = []
    worker_end_to_end_ms = []
    order_equal = True
    action_trace_equal = True
    schedule_equal = True
    coverage = []
    completions = []
    last_snapshot = None
    last_completion = None
    determinism_shadow = None
    try:
        for index in range(int(warmup)):
            warm_snapshot = _replay_snapshot(
                snapshot, 100000 + index)
            arguments = (
                warm_snapshot, candidates, 5,
                int(warm_snapshot.turn) + 200)
            baseline.rank(*arguments)
            _, artifact = shadow.rank(
                *arguments)
            shadow.wait_for_domain_estimates(
                artifact["domain_estimates"][
                    "dispatch_batch_id"],
                timeout=5.0)

        # Every measured iteration uses a distinct snapshot identity.  The
        # shadow path must therefore dispatch and complete fresh work rather
        # than receiving a warmed same-snapshot cache hit.
        for index in range(int(iterations)):
            sample_snapshot = _replay_snapshot(
                snapshot, 200000 + index)
            last_snapshot = sample_snapshot
            arguments = (
                sample_snapshot, candidates, 5,
                int(sample_snapshot.turn) + 200)
            rankers = (
                (("baseline", baseline), ("shadow", shadow))
                if index % 2 == 0 else
                (("shadow", shadow), ("baseline", baseline)))
            decisions = {}
            for name, ranker in rankers:
                # Worker allocations from one arm must not make the paired
                # comparator pay that arm's deferred cyclic-GC bill.  Run the
                # same untimed stabilization before both measurements; worker
                # compute and full-loop wall time remain reported separately.
                gc.collect()
                started = time.perf_counter()
                decisions[name] = ranker.rank(
                    *arguments)
                decision_elapsed = (
                    time.perf_counter()
                    - started) * 1000.0
                if name == "baseline":
                    baseline_ms.append(
                        decision_elapsed)
                    continue
                shadow_dispatch_ms.append(
                    decision_elapsed)
                domain = decisions[name][1][
                    "domain_estimates"]
                completion = (
                    shadow.wait_for_domain_estimates(
                        domain["dispatch_batch_id"],
                        timeout=5.0))
                shadow_full_loop_ms.append(
                    (
                        time.perf_counter()
                        - started) * 1000.0)
                completions.append(completion)
                last_completion = completion
                worker_ms.append(
                    completion[
                        "worker_latency_ms"])
                queue_delay_ms.append(
                    completion[
                        "queue_delay_ms"])
                worker_end_to_end_ms.append(
                    completion[
                        "end_to_end_latency_ms"])
                coverage.append(
                    float(
                        completion[
                            "estimate_count"])
                    / float(max(
                        1, len(candidates))))
            baseline_order, baseline_artifact = (
                decisions["baseline"])
            shadow_order, shadow_artifact = (
                decisions["shadow"])
            order_equal = bool(
                order_equal
                and baseline_order == shadow_order)
            action_trace_equal = bool(
                action_trace_equal
                and canonical_json_bytes([
                    row.action for row
                    in baseline_order])
                == canonical_json_bytes([
                    row.action for row
                    in shadow_order]))
            schedule_equal = bool(
                schedule_equal
                and baseline_artifact["schedule"]
                == shadow_artifact["schedule"])

        # Recompute the final batch through an independent registry/executor;
        # this checks semantic determinism rather than cache stability.
        determinism_shadow = ImpactPressureRankerV2(
            domain_estimates_enabled=True,
            ruleset_digest=ruleset_digest)
        _, repeat_artifact = determinism_shadow.rank(
            last_snapshot, candidates, 5,
            int(last_snapshot.turn) + 200)
        repeated_completion = (
            determinism_shadow
            .wait_for_domain_estimates(
                repeat_artifact[
                    "domain_estimates"][
                        "dispatch_batch_id"],
                timeout=5.0))
        semantic_determinism = bool(
            last_completion["artifact_hash"]
            == repeated_completion[
                "artifact_hash"])
        shadow_statistics = (
            shadow.domain_estimate_statistics())
    finally:
        shadow.close_domain_estimates()
        if determinism_shadow is not None:
            determinism_shadow.close_domain_estimates()

    baseline_summary = _summary(baseline_ms)
    shadow_summary = _summary(
        shadow_dispatch_ms)
    shadow_full_loop_summary = _summary(
        shadow_full_loop_ms)
    overhead = (
        shadow_summary["p95_ms"]
        / baseline_summary["p95_ms"] - 1.0)
    full_loop_overhead = (
        shadow_full_loop_summary["p95_ms"]
        / baseline_summary["p95_ms"] - 1.0)
    all_completed = all(
        row is not None
        and row.get("status") == "completed"
        for row in completions)
    result = {
        "baseline": baseline_summary,
        "candidate_count": len(candidates),
        "claim_status": "diagnostic-only",
        "coverage": {
            "mean_fraction": statistics.mean(coverage),
            "minimum_fraction": min(coverage),
            "required_fraction": 0.95,
        },
        "fixture": {
            "path": os.path.relpath(
                fixture_path, REPO),
            "payload_hash": structural_hash(payload),
            "snapshot_id": snapshot.snapshot_id,
        },
        "domain_readout":
            _domain_readout(
                last_completion),
        "gates": {
            "action_trace_byte_identical":
                action_trace_equal,
            "candidate_coverage": min(coverage) >= 0.95,
            "fresh_batches_completed":
                all_completed,
            "live_order_identical": order_equal,
            "p95_overhead_within_5_percent":
                overhead <= 0.05,
            "queue_capacity_not_exceeded":
                shadow_statistics[
                    "capacity_rejection_count"] == 0,
            "schedule_identical": schedule_equal,
            "semantic_estimates_deterministic":
                semantic_determinism,
            "worker_failures_absent":
                shadow_statistics[
                    "failed_batch_count"] == 0,
        },
        "iterations": int(iterations),
        "measurement_protocol": {
            "fresh_snapshot_per_pair": True,
            "paired_gc_stabilization": True,
            "worker_cost_reported_separately": True,
        },
        "full_loop_p95_overhead_fraction":
            full_loop_overhead,
        "p95_overhead_fraction": overhead,
        "policy_authority": False,
        "schema_version": "1.2",
        "shadow": shadow_summary,
        "shadow_full_loop": (
            shadow_full_loop_summary),
        "shadow_worker": {
            "compute": _summary(worker_ms),
            "end_to_end": _summary(
                worker_end_to_end_ms),
            "executor": shadow_statistics,
            "queue_delay": _summary(
                queue_delay_ms),
        },
        "warmup_iterations": int(warmup),
    }
    result["passed"] = all(
        result["gates"].values())
    result["report_hash"] = structural_hash(
        result)
    return result


def main():
    parser = argparse.ArgumentParser(
        description=__doc__)
    parser.add_argument(
        "--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--iterations", type=int, default=100)
    parser.add_argument(
        "--warmup", type=int, default=10)
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    if arguments.iterations < 10:
        parser.error("iterations must be at least 10")
    if arguments.warmup < 0:
        parser.error("warmup must be non-negative")
    result = run(
        os.path.abspath(arguments.fixture),
        arguments.iterations,
        arguments.warmup)
    output = os.path.abspath(arguments.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as stream:
        json.dump(
            result, stream, indent=2,
            sort_keys=True)
        stream.write("\n")
    print(json.dumps({
        "output": output,
        "passed": result["passed"],
        "report_hash": result["report_hash"],
    }, sort_keys=True))
    # A diagnostic gate failure is data, not a script crash.
    return 0


if __name__ == "__main__":
    sys.exit(main())
