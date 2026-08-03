#!/usr/bin/env python3
"""Audit exact scalar-baseline grounding reasons without a yield claim."""

import argparse
import glob
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_scalar_baseline_candidate_readout import (  # noqa: E402
    READOUT_COMPONENT_ID,
    audit as audit_parent,
)
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)


AUDIT_IDENTITY = "fdas-scalar-baseline-grounding-diagnostic-audit/1.0"
GENERIC_REASON = "control-grounded-transition-input-unavailable"
EXACT_CONTROL_PREFIXES = (
    "control-actor-fields-unavailable:",
    "control-actor-state-unavailable",
    "control-bounded-validator-",
    "control-deficit-support-record-unavailable",
    "control-native-route-",
    "control-target-city-state-unavailable",
)


def _reason_summary(run_root):
    counts = {}
    for event_path in sorted(glob.glob(os.path.join(
            os.path.abspath(run_root), "games", "main", "e_full_loop", "*",
            "events.jsonl"))):
        with open(event_path, encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                payload = event.get("payload", {})
                if (event.get("type") != "atomspace_shadow_decision"
                        or payload.get("component_id")
                        != READOUT_COMPONENT_ID):
                    continue
                reason = payload.get("details", {}).get("reason")
                if isinstance(reason, str) and reason:
                    counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def audit(run_root, expected_seeds, expected_source_commit):
    parent = audit_parent(
        run_root, expected_seeds, expected_source_commit)
    reasons = _reason_summary(run_root)
    generic = reasons.get(GENERIC_REASON, 0)
    exact = sum(
        count for reason, count in reasons.items()
        if reason.startswith(EXACT_CONTROL_PREFIXES))
    grounded_controls = sum(
        count for reason, count in reasons.items()
        if reason in (
            "calibrated-and-grounded-dominance",
            "no-protected-alternative",
            "no-separated-grounded-noninferior-alternative"))
    gates = {
        "candidate_specific_prediction_observed": (
            parent["totals"]["union_candidate_specific_predictions"] > 0),
        "exact_grounding_failure_observed": exact > 0,
        "generic_grounding_reason_eliminated": generic == 0,
        "parent_mechanics_are_accepted": parent["mechanically_accepted"],
    }
    report = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "exact fail-closed scalar-control grounding diagnosis only; no "
            "candidate opportunity, preference, ranking, gameplay, score, or "
            "win-rate claim"),
        "exact_control_grounding_failures": exact,
        "gates": gates,
        "generic_control_grounding_failures": generic,
        "grounded_control_readouts": grounded_controls,
        "parent_audit_hash": parent["report_hash"],
        "parent_mechanically_accepted": parent["mechanically_accepted"],
        "passed": all(gates.values()),
        "reason_counts": reasons,
    }
    report["report_hash"] = structural_hash(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("--expected-seed", action="append", type=int,
                        required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = audit(
        args.run_root, args.expected_seed, args.expected_source_commit)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "wb") as stream:
        stream.write(canonical_json_bytes(report) + b"\n")
    print(json.dumps({
        "output": output,
        "passed": report["passed"],
        "reason_counts": report["reason_counts"],
        "report_hash": report["report_hash"],
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
