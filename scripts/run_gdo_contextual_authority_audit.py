#!/usr/bin/env python3
"""Summarize the fresh GDO-8 contextual-authority engine diagnostic."""

import argparse
import hashlib
import itertools
import json
import os
import sys


REPO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)


COHORT = (
    "contextual_transition_authority_diagnostic_v1")


def _json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(
                lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _event_paths(root, arm):
    directory = os.path.join(
        root, "games", "impact_pair",
        COHORT, arm, "e_full_loop")
    return tuple(sorted(
        os.path.join(directory, seed, "events.jsonl")
        for seed in os.listdir(directory)
        if os.path.isfile(os.path.join(
            directory, seed, "events.jsonl"))))


def _read_events(path):
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def _action_sequence(path):
    rows = []
    for event in _read_events(path):
        if event.get("type") != "action_sent":
            continue
        payload = event.get("payload", {})
        summary = payload.get(
            "summary", payload)
        rows.append((
            int(event["turn"]),
            summary.get("action")))
    return tuple(rows)


def _calibration_counts(path):
    result = {
        "all_candidate_support": 0,
        "authority_active": 0,
        "authority_requested": 0,
        "decision_count": 0,
        "fallbacks": 0,
    }
    for event in _read_events(path):
        if event.get(
                "type") != "teleology_estimated":
            continue
        calibration = (
            event.get("payload", {})
            .get("summary", {})
            .get("calibration", {}))
        result["decision_count"] += 1
        result["all_candidate_support"] += int(
            calibration.get(
                "all_candidate_support")
            is True)
        result["authority_active"] += int(
            calibration.get(
                "authority_active")
            is True)
        result["authority_requested"] += int(
            calibration.get(
                "authority_requested")
            is True)
        result["fallbacks"] += int(
            calibration.get(
                "gate_reason")
            is not None
            and calibration.get(
                "gate_reason")
            != "authority-disabled")
    return result


def _metric(aggregate, name):
    row = aggregate[
        "paired_deltas"][name]
    return {
        "estimate": row["estimate"],
        "interval": [
            row["lower"], row["upper"]],
        "method": row["method"],
        "pairs": row["n"],
    }


def run(artifact_root):
    root = os.path.abspath(
        artifact_root)
    aggregate_path = os.path.join(
        root, "impact-aggregate.json")
    aggregate = _json(aggregate_path)
    baseline_paths = _event_paths(
        root, "baseline")
    treatment_paths = _event_paths(
        root, "treatment")
    if (
            len(baseline_paths) != 10
            or len(treatment_paths) != 10
    ):
        raise ValueError(
            "authority diagnostic requires ten complete pairs")
    by_arm = {
        "baseline": dict(
            (os.path.basename(
                os.path.dirname(path)), path)
            for path in baseline_paths),
        "treatment": dict(
            (os.path.basename(
                os.path.dirname(path)), path)
            for path in treatment_paths),
    }
    if set(by_arm["baseline"]) != set(
            by_arm["treatment"]):
        raise ValueError(
            "paired authority seeds differ")
    divergence = []
    event_files = []
    calibration = {}
    for arm, paths in (
            ("baseline", baseline_paths),
            ("treatment", treatment_paths)):
        totals = {
            "all_candidate_support": 0,
            "authority_active": 0,
            "authority_requested": 0,
            "decision_count": 0,
            "fallbacks": 0,
        }
        for path in paths:
            counts = _calibration_counts(
                path)
            for key in totals:
                totals[key] += counts[key]
            event_files.append({
                "arm": arm,
                "events_sha256":
                    _sha256(path),
                "path": os.path.relpath(
                    path, root),
                "seed": int(
                    os.path.basename(
                        os.path.dirname(path))
                    .split("-", 1)[0]),
            })
        calibration[arm] = totals
    for seed in sorted(
            by_arm["baseline"]):
        baseline = _action_sequence(
            by_arm["baseline"][seed])
        treatment = _action_sequence(
            by_arm["treatment"][seed])
        mismatches = tuple(
            index
            for index, pair in enumerate(
                itertools.zip_longest(
                    baseline, treatment))
            if pair[0] != pair[1])
        if mismatches:
            first = mismatches[0]
            divergence.append({
                "baseline_action_count":
                    len(baseline),
                "first_baseline":
                    baseline[first]
                    if first < len(
                        baseline) else None,
                "first_difference_index":
                    first,
                "first_treatment":
                    treatment[first]
                    if first < len(
                        treatment) else None,
                "mismatched_positions":
                    len(mismatches),
                "seed": int(
                    seed.split("-", 1)[0]),
                "treatment_action_count":
                    len(treatment),
            })
    gates = {
        "all_treatment_decisions_supported": (
            calibration[
                "treatment"][
                    "all_candidate_support"]
            == calibration[
                "treatment"][
                    "decision_count"]),
        "authority_active_when_requested": (
            calibration[
                "treatment"][
                    "authority_active"]
            == calibration[
                "treatment"][
                    "authority_requested"]
            == calibration[
                "treatment"][
                    "decision_count"]),
        "clean_source_stable":
            aggregate[
                "source_freeze"][
                    "passed"] is True,
        "no_authority_fallbacks":
            calibration[
                "treatment"][
                    "fallbacks"] == 0,
        "safety_gates_passed":
            aggregate[
                "safety_gates"][
                    "overall_passed"] is True,
        "ten_complete_pairs": (
            aggregate[
                "complete_pairs"] == 10
            and not aggregate[
                "failures"]),
    }
    score_delta = _metric(
        aggregate, "score_turn_n")
    runtime_passed = all(
        gates.values())
    policy_benefit = (
        score_delta["interval"][0] > 0.0)
    report = {
        "calibration": calibration,
        "claim_boundary": {
            "claim_eligible_cohort": False,
            "gameplay_score_claim": False,
            "prediction_authority_runtime_claim":
                runtime_passed,
        },
        "cohort": {
            "claim_eligible": False,
            "complete_pairs":
                aggregate[
                    "complete_pairs"],
            "id": COHORT,
            "purpose": "diagnostic",
            "source_commits":
                aggregate[
                    "source_freeze"][
                        "commits"],
        },
        "event_files": sorted(
            event_files,
            key=lambda row: (
                row["seed"], row["arm"])),
        "gates": gates,
        "policy_effect": {
            "action_divergence_pairs":
                len(divergence),
            "action_divergences":
                divergence,
            "full_loop_latency_delta_ms":
                _metric(
                    aggregate,
                    "turn_full_loop_latency_ms"),
            "impact_planning_latency_delta_ms":
                _metric(
                    aggregate,
                    "turn_impact_planning_latency_ms"),
            "score_delta": score_delta,
            "score_margin_delta":
                _metric(
                    aggregate,
                    "score_margin_turn_n"),
            "win_rate_delta":
                _metric(
                    aggregate,
                    "game_win"),
        },
        "result": {
            "live_authority_recommended":
                False,
            "policy_benefit_gate_passed":
                policy_benefit,
            "runtime_authority_gate_passed":
                runtime_passed,
            "summary": (
                "approved model exercised safely with complete support; "
                "no paired player-score or win-rate improvement"),
        },
        "schema_version": "1.0",
        "source": {
            "aggregate_sha256":
                _sha256(aggregate_path),
            "artifact_root":
                os.path.basename(root),
        },
    }
    report["report_hash"] = structural_hash(
        report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifacts",
        default=os.path.join(
            REPO, "artifacts", "freeciv",
            "gdo8-contextual-authority-v1"))
    parser.add_argument(
        "--output",
        default=os.path.join(
            REPO, "benchmarks", "gdo",
            "gdo8_contextual_authority_diagnostic.json"))
    arguments = parser.parse_args()
    report = run(arguments.artifacts)
    output = os.path.abspath(
        arguments.output)
    os.makedirs(
        os.path.dirname(output),
        exist_ok=True)
    with open(output, "wb") as stream:
        stream.write(
            canonical_json_bytes(report))
        stream.write(b"\n")
    print(json.dumps({
        "gates": report["gates"],
        "output": os.path.relpath(
            output, REPO),
        "report_hash":
            report["report_hash"],
        "result": report["result"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
