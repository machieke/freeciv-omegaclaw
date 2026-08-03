#!/usr/bin/env python3
"""Audit fresh safety-filtered grounded-alternative opportunity yield."""

import argparse
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

from audit_fdas_safe_filtered_scalar_readout import (  # noqa: E402
    audit as audit_parent,
)
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)


AUDIT_IDENTITY = "fdas-safe-filtered-scalar-readout-cohort-audit/1.0"


def _cohort_gates(parent):
    grounded_alternative_games = sum(
        value["measures"]["readout_grounded_alternatives"] > 0
        for value in parent["games"])
    grounded_control_games = sum(
        value["measures"]["grounded_controls"] > 0
        for value in parent["games"])
    return {
        "calibrated_addition_observed": (
            parent["totals"]["union_additions"] > 0),
        "grounded_alternative_compared": (
            parent["totals"]["readout_grounded_alternatives"] > 0),
        "grounded_alternative_game_observed": (
            grounded_alternative_games > 0),
        "grounded_safe_control_game_observed": grounded_control_games > 0,
        "parent_safe_filter_audit_passed": parent["passed"],
    }, grounded_alternative_games, grounded_control_games


def audit(run_root, expected_seeds, expected_source_commit):
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if len(expected_seeds) != 8 or len(expected_seeds) != len(
            set(expected_seeds)):
        raise ValueError("safe-filter cohort requires exactly eight seeds")
    parent = audit_parent(
        run_root, expected_seeds, expected_source_commit)
    gates, alternative_games, control_games = _cohort_gates(parent)
    report = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "fresh safety-filtered protected-alternative comparison yield "
            "only; no calibrated ranking, counterfactual outcome, gameplay, "
            "score, or win-rate claim"),
        "expected_seeds": list(expected_seeds),
        "gates": gates,
        "grounded_alternative_games": alternative_games,
        "grounded_safe_control_games": control_games,
        "parent_audit_hash": parent["report_hash"],
        "parent_totals": parent["totals"],
        "passed": all(gates.values()),
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
        "gates": report["gates"],
        "output": output,
        "passed": report["passed"],
        "report_hash": report["report_hash"],
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
