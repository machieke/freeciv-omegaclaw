#!/usr/bin/env python3
"""Audit the live ruleset-defensive scalar readout confirmation."""

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
from audit_fdas_target_scoped_scalar_readout import (  # noqa: E402
    _target_gates,
)
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import (  # noqa: E402
    RULESET_DEFENSIVE_SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY,
)


AUDIT_IDENTITY = "fdas-ruleset-defensive-scalar-readout-audit/1.0"
MANIFEST_SOURCE = (
    "profile/fdas_manifest_defense_ruleset_defensive_scalar_readout_shadow.json")
REQUIRED_CAPABILITY_CHECKS = frozenset((
    "defensive-effect-signature",
    "ruleset-defense",
    "ruleset-firepower",
    "ruleset-maximum-hitpoints",
    "unit-class",
))


def audit(run_root, expected_seed, expected_source_commit):
    expected_seed = int(expected_seed)
    parent = audit_parent(
        run_root, (expected_seed,), expected_source_commit,
        target_scoped=True,
        target_scoped_manifest_source=MANIFEST_SOURCE)
    target_gates, _alternative_games, _multi_surfaces = _target_gates(parent)
    readouts = 0
    grounded_candidates = 0
    cross_type_comparisons = 0
    cross_type_capability_noninferior = 0
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
                readouts += 1
                identities.add(details.get("identity"))
                candidates = tuple(
                    value for value in details.get("candidates", ())
                    if isinstance(value, dict))
                grounded_candidates += len(candidates)
                control = next((
                    value for value in candidates
                    if value.get("operation_id")
                    == details.get("baseline_operation_id")), None)
                if control is None:
                    continue
                for candidate in candidates:
                    if (candidate is control
                            or candidate.get("unit_type")
                            == control.get("unit_type")):
                        continue
                    cross_type_comparisons += 1
                    checks = set(candidate.get(
                        "noninferiority_checks", ()))
                    if (REQUIRED_CAPABILITY_CHECKS <= checks
                            and "unit-type" not in checks
                            and isinstance(
                                control.get("defensive_capability"), dict)
                            and isinstance(
                                candidate.get("defensive_capability"), dict)):
                        cross_type_capability_noninferior += 1
    gates = {
        "additions_only_recall_observed": target_gates[
            "additions_only_recall_observed"],
        "cross_type_capability_noninferiority_observed": (
            cross_type_capability_noninferior > 0),
        "cross_type_grounded_comparison_observed": cross_type_comparisons > 0,
        "grounded_same_target_alternative_observed": target_gates[
            "grounded_same_target_alternative_observed"],
        "parent_target_scoped_safety_audit_passed": parent["passed"],
        "ruleset_defensive_identity_is_exclusive": (
            identities == {
                RULESET_DEFENSIVE_SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY}),
        "ruleset_grounded_candidates_observed": grounded_candidates > 0,
        "scalar_readout_observed": readouts > 0,
    }
    report = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "known-opportunity live confirmation of ruleset-grounded defensive "
            "comparison only; reused seed is not independent evidence and "
            "establishes no ranking, outcome, gameplay, score, or win-rate "
            "claim"),
        "cross_type_capability_noninferior": (
            cross_type_capability_noninferior),
        "cross_type_comparisons": cross_type_comparisons,
        "expected_seed": expected_seed,
        "gates": gates,
        "grounded_candidates": grounded_candidates,
        "parent_audit_hash": parent["report_hash"],
        "parent_totals": parent["totals"],
        "passed": all(gates.values()),
        "readouts": readouts,
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
        "output": output,
        "passed": report["passed"],
        "report_hash": report["report_hash"],
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
