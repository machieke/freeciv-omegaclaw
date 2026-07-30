#!/usr/bin/env python3
"""Run the GDO-1 paired shadow replay and latency diagnostic."""

import argparse
import json
import os
import statistics
import sys
import time


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
    arguments = (
        snapshot, candidates, 5,
        int(snapshot.turn) + 200)
    for _ in range(int(warmup)):
        baseline.rank(*arguments)
        shadow.rank(*arguments)

    baseline_ms = []
    shadow_ms = []
    order_equal = True
    action_trace_equal = True
    schedule_equal = True
    semantic_estimates = []
    coverage = []
    # Alternate execution order to reduce systematic cache/thermal bias.
    for index in range(int(iterations)):
        rankers = (
            (("baseline", baseline), ("shadow", shadow))
            if index % 2 == 0 else
            (("shadow", shadow), ("baseline", baseline)))
        decisions = {}
        for name, ranker in rankers:
            started = time.perf_counter()
            decisions[name] = ranker.rank(
                *arguments)
            elapsed = (
                time.perf_counter() - started) * 1000.0
            (baseline_ms if name == "baseline"
             else shadow_ms).append(elapsed)
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
        domain = shadow_artifact[
            "domain_estimates"]
        coverage.append(
            float(domain["estimate_count"])
            / float(max(1, len(candidates))))
        semantic_estimates.append(
            domain["artifact_hash"])

    baseline_summary = _summary(baseline_ms)
    shadow_summary = _summary(shadow_ms)
    overhead = (
        shadow_summary["p95_ms"]
        / baseline_summary["p95_ms"] - 1.0)
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
        "gates": {
            "action_trace_byte_identical":
                action_trace_equal,
            "candidate_coverage": min(coverage) >= 0.95,
            "live_order_identical": order_equal,
            "p95_overhead_within_5_percent":
                overhead <= 0.05,
            "schedule_identical": schedule_equal,
            "semantic_estimates_deterministic":
                len(set(semantic_estimates)) == 1,
        },
        "iterations": int(iterations),
        "p95_overhead_fraction": overhead,
        "policy_authority": False,
        "schema_version": "1.0",
        "shadow": shadow_summary,
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
