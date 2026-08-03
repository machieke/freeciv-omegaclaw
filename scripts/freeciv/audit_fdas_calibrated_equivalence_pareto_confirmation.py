#!/usr/bin/env python3
"""Audit live calibrated-equivalence grounded-Pareto confirmation."""

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
    READOUT_COMPONENT_ID,
    audit as audit_parent,
)
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import (  # noqa: E402
    CALIBRATED_EQUIVALENCE_PARETO_CANDIDATE_READOUT_IDENTITY,
)


AUDIT_IDENTITY = "fdas-calibrated-equivalence-pareto-confirmation-audit/1.0"
MANIFEST_SOURCE = (
    "profile/fdas_manifest_defense_calibrated_equivalence_pareto_shadow.json")


def audit(run_root, expected_seed, expected_source_commit):
    expected_seed = int(expected_seed)
    parent = audit_parent(
        run_root, (expected_seed,), expected_source_commit,
        target_scoped=True,
        target_scoped_manifest_source=MANIFEST_SOURCE)
    measures = {
        "equivalence_pareto_preferences": 0,
        "grounded_alternatives": 0,
        "interval_separated_preferences": 0,
        "readouts": 0,
        "shadow_preferences": 0,
        "strict_improvements": 0,
    }
    identities = set()
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
                details = payload.get("details", {})
                measures["readouts"] += 1
                identities.add(details.get("identity"))
                candidates = tuple(
                    value for value in details.get("candidates", ())
                    if isinstance(value, dict))
                control = next((
                    value for value in candidates
                    if value.get("operation_id")
                    == details.get("baseline_operation_id")), None)
                measures["grounded_alternatives"] += max(
                    0, len(candidates) - int(control is not None))
                measures["strict_improvements"] += sum(bool(
                    value.get("strict_grounded_improvements"))
                    for value in candidates if value is not control)
                if details.get("status") != "eligible-shadow":
                    continue
                measures["shadow_preferences"] += 1
                reason = details.get("reason")
                if reason == (
                        "calibrated-equivalence-and-grounded-pareto-"
                        "dominance"):
                    measures["equivalence_pareto_preferences"] += 1
                elif reason == "calibrated-and-grounded-dominance":
                    measures["interval_separated_preferences"] += 1
    gates = {
        "equivalence_pareto_preference_observed": (
            measures["equivalence_pareto_preferences"] > 0),
        "exclusive_readout_v1_2_identity": (
            identities == {
                CALIBRATED_EQUIVALENCE_PARETO_CANDIDATE_READOUT_IDENTITY}),
        "grounded_alternative_observed": measures["grounded_alternatives"] > 0,
        "parent_safety_audit_passed": parent["passed"],
        "strict_grounded_improvement_observed": (
            measures["strict_improvements"] > 0),
    }
    report = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "known-opportunity live confirmation of exact calibrated "
            "equivalence plus grounded Pareto shadow readout only; no "
            "counterfactual outcome, gameplay, score, or win-rate claim"),
        "expected_seed": expected_seed,
        "gates": gates,
        "measures": measures,
        "parent_audit_hash": parent["report_hash"],
        "parent_totals": parent["totals"],
        "passed": all(gates.values()),
        "readout_identities": sorted(str(value) for value in identities),
    }
    report["report_hash"] = structural_hash(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("--expected-seed", type=int, required=True)
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
        "measures": report["measures"],
        "output": output,
        "passed": report["passed"],
        "report_hash": report["report_hash"],
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
