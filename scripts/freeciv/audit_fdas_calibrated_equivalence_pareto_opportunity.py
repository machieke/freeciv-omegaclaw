#!/usr/bin/env python3
"""Audit unseen-seed yield for calibrated-equivalence Pareto readout."""

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

from audit_fdas_calibrated_equivalence_pareto_confirmation import (  # noqa: E402
    MANIFEST_SOURCE,
    READOUT_COMPONENT_ID,
)
from audit_fdas_ruleset_defensive_opportunity_cohort import (  # noqa: E402
    _wilson,
)
from audit_fdas_safe_filtered_scalar_readout import (  # noqa: E402
    audit as audit_parent,
)
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import (  # noqa: E402
    CALIBRATED_EQUIVALENCE_PARETO_CANDIDATE_READOUT_IDENTITY,
)


AUDIT_IDENTITY = "fdas-calibrated-equivalence-pareto-opportunity-audit/1.0"


def _yield_classification(measures):
    if measures["grounded_alternatives"] <= 0:
        return "no-grounded-alternative-yield"
    if measures["strict_improvement_alternatives"] <= 0:
        return "no-strict-grounded-improvement-yield"
    if measures["equivalence_pareto_preferences"] <= 0:
        return "no-equivalence-pareto-preference-yield"
    return "equivalence-pareto-preference-observed"


def audit(run_root, expected_seeds, expected_source_commit):
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if (len(expected_seeds) != 16
            or len(expected_seeds) != len(set(expected_seeds))):
        raise ValueError(
            "equivalence Pareto opportunity audit requires 16 unique seeds")
    parent = audit_parent(
        run_root, expected_seeds, expected_source_commit,
        target_scoped=True,
        target_scoped_manifest_source=MANIFEST_SOURCE)
    totals = {
        "equivalence_pareto_preferences": 0,
        "grounded_alternatives": 0,
        "interval_separated_preferences": 0,
        "readouts": 0,
        "shadow_preferences": 0,
        "strict_improvement_alternatives": 0,
    }
    identities = set()
    games = []
    for game_dir in sorted(glob.glob(os.path.join(
            os.path.abspath(run_root), "games", "main", "e_full_loop", "*"))):
        with open(os.path.join(game_dir, "manifest.json"),
                  encoding="utf-8") as stream:
            seed = int(json.load(stream)["seed"])
        measures = dict((name, 0) for name in totals)
        with open(os.path.join(game_dir, "events.jsonl"),
                  encoding="utf-8") as stream:
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
                alternatives = tuple(
                    value for value in candidates if value is not control)
                measures["grounded_alternatives"] += len(alternatives)
                measures["strict_improvement_alternatives"] += sum(bool(
                    value.get("strict_grounded_improvements"))
                    for value in alternatives)
                if details.get("status") != "eligible-shadow":
                    continue
                measures["shadow_preferences"] += 1
                if details.get("reason") == (
                        "calibrated-equivalence-and-grounded-pareto-"
                        "dominance"):
                    measures["equivalence_pareto_preferences"] += 1
                elif details.get("reason") == (
                        "calibrated-and-grounded-dominance"):
                    measures["interval_separated_preferences"] += 1
        for name, value in measures.items():
            totals[name] += value
        games.append({"measures": measures, "seed": seed})
    game_count = len(games)
    opportunity_games = sum(
        value["measures"]["grounded_alternatives"] > 0 for value in games)
    strict_games = sum(
        value["measures"]["strict_improvement_alternatives"] > 0
        for value in games)
    preference_games = sum(
        value["measures"]["equivalence_pareto_preferences"] > 0
        for value in games)
    gates = {
        "exact_sixteen_game_inventory": (
            tuple(sorted(value["seed"] for value in games))
            == tuple(sorted(expected_seeds))),
        "exclusive_readout_v1_2_identity": (
            identities == {
                CALIBRATED_EQUIVALENCE_PARETO_CANDIDATE_READOUT_IDENTITY}),
        "parent_safety_audit_passed": parent["passed"],
        "scalar_readout_observed": totals["readouts"] > 0,
    }
    report = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "unseen-seed calibrated-equivalence grounded-Pareto preference "
            "yield only; no counterfactual outcome, gameplay, score, or "
            "win-rate claim"),
        "expected_seeds": list(expected_seeds),
        "game_level_rates": {
            "equivalence_pareto_preference": _wilson(
                preference_games, game_count),
            "grounded_alternative": _wilson(
                opportunity_games, game_count),
            "strict_grounded_improvement": _wilson(
                strict_games, game_count),
        },
        "games": games,
        "gates": gates,
        "mechanically_accepted": all(gates.values()),
        "measures": totals,
        "parent_audit_hash": parent["report_hash"],
        "parent_totals": parent["totals"],
        "passed": all(gates.values()),
        "readout_identities": sorted(str(value) for value in identities),
        "yield_classification": _yield_classification(totals),
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
        "measures": report["measures"],
        "output": output,
        "passed": report["passed"],
        "report_hash": report["report_hash"],
        "yield_classification": report["yield_classification"],
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
