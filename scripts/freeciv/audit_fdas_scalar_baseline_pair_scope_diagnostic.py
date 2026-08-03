#!/usr/bin/env python3
"""Audit exact scalar-baseline pair-scope diagnostics without relaxing scope."""

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

from audit_fdas_safe_filtered_scalar_readout import (  # noqa: E402
    audit as audit_parent,
)
from audit_fdas_scalar_baseline_candidate_readout import (  # noqa: E402
    READOUT_COMPONENT_ID,
)
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)


AUDIT_IDENTITY = "fdas-scalar-baseline-pair-scope-diagnostic-audit/1.0"
EXACT_SCOPE_MARKER = ":pair-scope:"
GENERIC_SCOPE_REASON = ":pair-scope-mismatch"
KNOWN_EXACT_REASONS = frozenset({
    "duplicate-action",
    "identical-resource-set",
    "operation-type-mismatch",
    "target-ref-mismatch",
})
RESOURCE_OVERLAP_PREFIX = "resource-overlap:"


def _pair_scope_summary(run_root):
    exact = {}
    generic = 0
    malformed = 0
    affected_readouts = 0
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
                found = False
                for rejection in payload.get("details", {}).get(
                        "rejected", ()):
                    if not isinstance(rejection, str):
                        continue
                    if rejection.endswith(GENERIC_SCOPE_REASON):
                        generic += 1
                        found = True
                        continue
                    if EXACT_SCOPE_MARKER not in rejection:
                        continue
                    found = True
                    reason = rejection.split(EXACT_SCOPE_MARKER, 1)[1]
                    known = (reason in KNOWN_EXACT_REASONS
                             or (reason.startswith(RESOURCE_OVERLAP_PREFIX)
                                 and len(reason) > len(
                                     RESOURCE_OVERLAP_PREFIX)))
                    if not known:
                        malformed += 1
                    exact[reason] = exact.get(reason, 0) + 1
                affected_readouts += int(found)
    return {
        "affected_readouts": affected_readouts,
        "exact_reason_counts": dict(sorted(exact.items())),
        "exact_rejections": sum(exact.values()),
        "generic_rejections": generic,
        "malformed_exact_rejections": malformed,
        "resource_overlap_rejections": sum(
            count for reason, count in exact.items()
            if reason.startswith(RESOURCE_OVERLAP_PREFIX)),
    }


def audit(run_root, expected_seeds, expected_source_commit):
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if (len(expected_seeds) != 8
            or len(expected_seeds) != len(set(expected_seeds))):
        raise ValueError("pair-scope diagnostic requires exactly eight seeds")
    parent = audit_parent(
        run_root, expected_seeds, expected_source_commit)
    summary = _pair_scope_summary(run_root)
    gates = {
        "exact_pair_scope_failure_observed": (
            summary["exact_rejections"] > 0),
        "generic_pair_scope_reason_eliminated": (
            summary["generic_rejections"] == 0),
        "parent_safe_filter_audit_passed": parent["passed"],
        "pair_scope_reasons_are_well_formed": (
            summary["malformed_exact_rejections"] == 0),
        "resource_overlap_is_observed_exactly": (
            summary["resource_overlap_rejections"] > 0),
    }
    report = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "exact fail-closed scalar pair-scope diagnosis only; no scope "
            "relaxation, alternative grounding, ranking, counterfactual "
            "outcome, gameplay, score, or win-rate claim"),
        "expected_seeds": list(expected_seeds),
        "gates": gates,
        "pair_scope_summary": summary,
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
        "pair_scope_summary": report["pair_scope_summary"],
        "passed": report["passed"],
        "report_hash": report["report_hash"],
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
