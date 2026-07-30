#!/usr/bin/env python3
"""Evaluate the conditional GDO-9 bridge/flow re-entry gates."""

import argparse
import hashlib
import json
import os
import re
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


INPUTS = {
    "contextual_calibration":
        "benchmarks/gdo/"
        "gdo8_contextual_calibration_diagnostic.json",
    "engine_lifecycle":
        "benchmarks/gdo/"
        "gdo4_operation_lifecycle_160_diagnostic.json",
    "resource_scheduler":
        "benchmarks/gdo/"
        "gdo3_resource_shadow_diagnostic.json",
    "synthetic_combat_lifecycle":
        "benchmarks/gdo/"
        "gdo5_combat_operation_lifecycle_diagnostic.json",
    "protected_bridge":
        "docs/freeciv/evidence/"
        "pf-protected-bridge-readout-diagnostic-v1.json",
    "flow_synthetic":
        "docs/freeciv/evidence/"
        "pf-unified-g4-flow-sandbox.json",
    "flow_engine_confirmation":
        "docs/freeciv/evidence/"
        "pf-unified-flow-advisory-confirmatory-v1.md",
}


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(
                lambda: stream.read(
                    1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _historical_confirmation(path):
    with open(path, encoding="utf-8") as stream:
        text = stream.read()
    patterns = {
        "full_loop_latency_delta_ms":
            r"Full turn loop \| [^|]+ \| [^|]+ \| \+([0-9.]+) ms",
        "impact_planning_latency_delta_ms":
            r"Impact planning \| [^|]+ \| [^|]+ \| \+([0-9.]+) ms",
        "score_delta":
            r"Treatment-minus-baseline player score was `\+([0-9.]+)`",
        "score_interval_lower":
            r"interval `\[\-([0-9.]+), \+([0-9.]+)\]`",
    }
    score = re.search(
        patterns["score_delta"], text)
    interval = re.search(
        patterns["score_interval_lower"],
        text)
    impact = re.search(
        patterns[
            "impact_planning_latency_delta_ms"],
        text)
    loop = re.search(
        patterns[
            "full_loop_latency_delta_ms"],
        text)
    if not all((
            score, interval,
            impact, loop)):
        raise ValueError(
            "historical confirmation format changed")
    return {
        "full_loop_latency_delta_ms":
            float(loop.group(1)),
        "impact_planning_latency_delta_ms":
            float(impact.group(1)),
        "primary_endpoint_met": False,
        "score_delta": float(
            score.group(1)),
        "score_interval": [
            -float(interval.group(1)),
            float(interval.group(2)),
        ],
    }


def run():
    absolute = {
        name: os.path.join(REPO, path)
        for name, path in INPUTS.items()}
    contextual = _json(
        absolute[
            "contextual_calibration"])
    lifecycle = _json(
        absolute["engine_lifecycle"])
    resource = _json(
        absolute["resource_scheduler"])
    combat_lifecycle = _json(
        absolute[
            "synthetic_combat_lifecycle"])
    protected = _json(
        absolute["protected_bridge"])
    flow_synthetic = _json(
        absolute["flow_synthetic"])
    confirmation = (
        _historical_confirmation(
            absolute[
                "flow_engine_confirmation"]))

    conditions = {
        "1_candidate_invariant_calibrated_target_slice": {
            "passed": bool(
                contextual.get(
                    "scope", {}).get(
                        "engine_backed")
                and contextual.get(
                    "scope", {}).get(
                        "live_authority_eligible")),
            "reason": (
                "contextual v2 passes a synthetic mechanism gate but has "
                "no disjoint engine-backed support/holdout bundle"),
        },
        "2_zero_hard_identity_overallocation": {
            "passed": bool(
                resource.get(
                    "gates", {}).get(
                        "hard_capacity_violations_absent")
                and not resource.get(
                    "hard_capacity_violations")),
            "reason": (
                "captured shadow scheduling reports zero hard-capacity "
                "violations"),
        },
        "3_stable_operation_completion_failure_semantics": {
            "passed": bool(
                lifecycle.get(
                    "gates", {}).get(
                        "at_least_one_committed_operation")
                and lifecycle.get(
                    "gates", {}).get(
                        "at_least_one_completed_operation")
                and combat_lifecycle.get(
                    "passed") is True),
            "reason": (
                "synthetic lifecycle semantics pass, but retained engine "
                "replay has no committed or completed operation"),
        },
        "4_bounded_exact_scheduler_is_comparison_baseline": {
            "passed": bool(
                resource.get(
                    "gates", {}).get(
                        "exact_schedule_status")
                and resource.get(
                    "gates", {}).get(
                        "semantic_schedule_deterministic")),
            "reason": (
                "bounded exact identity scheduler is implemented and "
                "deterministic in the captured comparison"),
        },
        "5_residual_route_allocation_error_identified": {
            "passed": False,
            "reason": (
                "no replay residual has been isolated after contextual "
                "calibration and B4 exact operation scheduling"),
        },
        "6_residual_not_semantic_stale_or_unsupported": {
            "passed": False,
            "reason": (
                "the prior engine failure was semantic terminal-action "
                "exclusion, while current contextual engine support is absent"),
        },
        "7_incremental_value_exceeds_controller_cost": {
            "passed": bool(
                confirmation[
                    "primary_endpoint_met"]
                and confirmation[
                    "score_interval"][0] > 0.0
                and confirmation[
                    "full_loop_latency_delta_ms"] <= 0.0),
            "reason": (
                "historical engine confirmation found no score benefit "
                "and added 291.57 ms per full turn"),
        },
    }
    entry_approved = all(
        row["passed"]
        for row in conditions.values())
    bridge_claim = {
        "eligible_against_b4": False,
        "historical_added_memberships":
            protected.get(
                "mechanism", {}).get(
                    "bridge_added_memberships"),
        "historical_candidate_recall_mechanism":
            protected.get(
                "result", {}).get(
                    "candidate_recall_mechanism"),
        "reason": (
            "historical recall was measured before the grounded B4 "
            "baseline and cannot take credit for new domain candidates"),
    }
    flow_claim = {
        "eligible_against_b4": False,
        "historical_synthetic_valid":
            flow_synthetic.get(
                "valid") is True,
        "historical_engine_confirmation":
            confirmation,
        "reason": (
            "synthetic allocation effects did not transfer to confirmed "
            "FreeCiv score value and were not compared with grounded B4"),
    }
    report = {
        "baseline_ladder": {
            "B0": "implemented-frozen-canonical-impact",
            "B1": "implemented-frozen-scalar-v2-plus-v1-packets",
            "B2": "implemented-shadow-grounded-estimates-plus-v1-scheduler",
            "B3": "implemented-shadow-grounded-identity-greedy",
            "B4": "implemented-shadow-grounded-bounded-exact-scheduler",
            "B5": "historical-shadow-bridge-not-revalidated-against-B4",
            "B6": "historical-shadow-flow-not-revalidated-against-B4",
        },
        "bridge_claim": bridge_claim,
        "conditions": conditions,
        "decision": {
            "bridge_reentry_allowed":
                entry_approved,
            "flow_reentry_allowed":
                entry_approved
                and bridge_claim[
                    "eligible_against_b4"],
            "live_authority_allowed":
                False,
            "next_required_evidence": (
                "disjoint engine-backed contextual training/holdout, "
                "stable engine operation completions, then a B4 replay "
                "residual attributable only to route allocation"),
            "result": (
                "entry-approved"
                if entry_approved
                else "entry-gate-closed"),
        },
        "entry_approved": entry_approved,
        "flow_claim": flow_claim,
        "inputs": {
            name: {
                "path": INPUTS[name],
                "sha256": _sha256(path),
            }
            for name, path in
            sorted(absolute.items())
        },
        "schema_version": "1.0",
    }
    report["report_hash"] = (
        structural_hash(report))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=os.path.join(
            REPO, "benchmarks", "gdo",
            "gdo9_bridge_flow_entry_audit.json"))
    arguments = parser.parse_args()
    report = run()
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
        "conditions": report["conditions"],
        "decision": report["decision"],
        "entry_approved":
            report["entry_approved"],
        "output": os.path.relpath(
            output, REPO),
        "report_hash":
            report["report_hash"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
