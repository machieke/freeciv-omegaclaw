#!/usr/bin/env python3
"""Audit unseen-seed yield for ruleset-defensive scalar readout."""

import argparse
import glob
import json
import math
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_ruleset_defensive_scalar_readout import (  # noqa: E402
    MANIFEST_SOURCE,
    READOUT_COMPONENT_ID,
    REQUIRED_CAPABILITY_CHECKS,
)
from audit_fdas_safe_filtered_scalar_readout import (  # noqa: E402
    audit as audit_parent,
)
from audit_fdas_scalar_baseline_candidate_readout import (  # noqa: E402
    RULESET_DEFENSIVE_NONINFERIORITY_CHECKS,
)
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import (  # noqa: E402
    RULESET_DEFENSIVE_SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY,
)


AUDIT_IDENTITY = "fdas-ruleset-defensive-opportunity-cohort-audit/1.0"


def _wilson(successes, trials, z=1.959963984540054):
    if trials <= 0:
        return None
    successes = float(successes)
    trials = float(trials)
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    center = (proportion + z * z / (2.0 * trials)) / denominator
    radius = z * math.sqrt(
        proportion * (1.0 - proportion) / trials
        + z * z / (4.0 * trials * trials)) / denominator
    return {
        "confidence": 0.95,
        "lower": max(0.0, center - radius),
        "point": proportion,
        "upper": min(1.0, center + radius),
    }


def _yield_classification(measures):
    for name, label in (
            ("grounded_alternatives", "no-grounded-alternative-yield"),
            ("cross_type_comparisons", "no-cross-type-yield"),
            ("cross_type_defensive_comparable",
             "no-ruleset-defensive-equivalence-yield"),
            ("grounded_noninferior_alternatives",
             "no-grounded-noninferiority-yield"),
            ("interval_separated_alternatives",
             "no-interval-separation-yield"),
            ("shadow_preferences", "no-shadow-preference-yield")):
        if measures[name] <= 0:
            return label
    return "shadow-preference-observed"


def audit(run_root, expected_seeds, expected_source_commit):
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if (len(expected_seeds) != 16
            or len(expected_seeds) != len(set(expected_seeds))):
        raise ValueError("opportunity audit requires exactly 16 unique seeds")
    parent = audit_parent(
        run_root, expected_seeds, expected_source_commit,
        target_scoped=True,
        target_scoped_manifest_source=MANIFEST_SOURCE)
    measures = {
        "cross_type_comparisons": 0,
        "cross_type_defensive_comparable": 0,
        "grounded_alternatives": 0,
        "grounded_noninferior_alternatives": 0,
        "interval_separated_alternatives": 0,
        "readouts": 0,
        "shadow_preferences": 0,
    }
    identities = set()
    games = []
    for game_dir in sorted(glob.glob(os.path.join(
            os.path.abspath(run_root), "games", "main", "e_full_loop", "*"))):
        manifest_path = os.path.join(game_dir, "manifest.json")
        event_path = os.path.join(game_dir, "events.jsonl")
        with open(manifest_path, encoding="utf-8") as stream:
            seed = int(json.load(stream)["seed"])
        game = dict((name, 0) for name in measures)
        with open(event_path, encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                payload = event.get("payload", {})
                if (event.get("type") != "atomspace_shadow_decision"
                        or payload.get("component_id")
                        != READOUT_COMPONENT_ID):
                    continue
                details = payload.get("details", {})
                identities.add(details.get("identity"))
                game["readouts"] += 1
                game["shadow_preferences"] += int(
                    details.get("shadow_preference") is True)
                candidates = tuple(
                    value for value in details.get("candidates", ())
                    if isinstance(value, dict))
                control = next((
                    value for value in candidates
                    if value.get("operation_id")
                    == details.get("baseline_operation_id")), None)
                if control is None:
                    continue
                for candidate in candidates:
                    if candidate is control:
                        continue
                    game["grounded_alternatives"] += 1
                    checks = set(candidate.get(
                        "noninferiority_checks", ()))
                    if (candidate.get("eligibility_reason")
                            in ("grounded-noninferior", "eligible")
                            and RULESET_DEFENSIVE_NONINFERIORITY_CHECKS
                            <= checks):
                        game["grounded_noninferior_alternatives"] += 1
                    if (candidate.get("interval_lower", -1)
                            > control.get("interval_upper", float("inf"))):
                        game["interval_separated_alternatives"] += 1
                    if (candidate.get("unit_type")
                            == control.get("unit_type")):
                        continue
                    game["cross_type_comparisons"] += 1
                    if (REQUIRED_CAPABILITY_CHECKS <= checks
                            and "unit-type" not in checks):
                        game["cross_type_defensive_comparable"] += 1
        for name, value in game.items():
            measures[name] += value
        games.append({
            "measures": game,
            "seed": seed,
        })
    opportunity_games = sum(
        value["measures"]["grounded_alternatives"] > 0 for value in games)
    cross_type_games = sum(
        value["measures"]["cross_type_comparisons"] > 0 for value in games)
    separated_games = sum(
        value["measures"]["interval_separated_alternatives"] > 0
        for value in games)
    gates = {
        "all_readouts_use_ruleset_defensive_identity": (
            identities == {
                RULESET_DEFENSIVE_SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY}),
        "exact_sixteen_game_inventory": (
            tuple(sorted(value["seed"] for value in games))
            == tuple(sorted(expected_seeds))),
        "parent_safety_audit_passed": parent["passed"],
        "scalar_readout_observed": measures["readouts"] > 0,
    }
    report = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "unseen-seed ruleset-defensive comparable-candidate and interval "
            "yield only; no counterfactual outcome, gameplay, score, or "
            "win-rate claim"),
        "expected_seeds": list(expected_seeds),
        "game_level_rates": {
            "cross_type_comparison": _wilson(cross_type_games, len(games)),
            "grounded_alternative": _wilson(
                opportunity_games, len(games)),
            "interval_separation": _wilson(separated_games, len(games)),
        },
        "games": games,
        "gates": gates,
        "mechanically_accepted": all(gates.values()),
        "measures": measures,
        "parent_audit_hash": parent["report_hash"],
        "parent_totals": parent["totals"],
        "passed": all(gates.values()),
        "readout_identities": sorted(str(value) for value in identities),
        "yield_classification": _yield_classification(measures),
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
