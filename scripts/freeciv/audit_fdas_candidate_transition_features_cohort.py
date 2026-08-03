#!/usr/bin/env python3
"""Audit transition feature invariants per game and opportunity at cohort scope."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SRC = os.path.join(REPO, "src")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
for path in (SRC, SCRIPT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_candidate_transition_features import (  # noqa: E402
    AUDIT_IDENTITY as LEGACY_AUDIT_IDENTITY,
    audit as audit_legacy,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402


AUDIT_IDENTITY = "fdas-candidate-transition-feature-cohort-audit/2.0"


def reinterpret_feature_audit(legacy):
    """Separate row invariants from chance opportunity presence."""
    if not isinstance(legacy, dict):
        raise TypeError("cohort feature audit requires legacy report")
    report_hash = legacy.get("report_hash")
    semantic = dict(legacy)
    semantic.pop("report_hash", None)
    if (legacy.get("audit_identity") != LEGACY_AUDIT_IDENTITY
            or not isinstance(report_hash, str)
            or report_hash != structural_hash(semantic)):
        raise ValueError("legacy transition feature audit is invalid")
    required = {
        "calibration_artifact_hash", "decision_safe_parent_audit_hash",
        "games", "gates", "model_result_hash", "totals",
    }
    if not required.issubset(legacy):
        raise ValueError("legacy transition feature audit is incomplete")
    games = []
    for source in legacy["games"]:
        measures = dict(source.get("measures", {}))
        prior = dict(source.get("gates", {}))
        errors = tuple(sorted(set(str(value)
                                  for value in source.get("errors", ()))))
        move_choices = measures.get("move_choices")
        if (isinstance(move_choices, bool)
                or not isinstance(move_choices, int)
                or move_choices < 0):
            raise ValueError("transition feature move count is invalid")
        gates = {
            "candidate_choice_store_is_valid": prior.get(
                "candidate_choice_store_is_valid") is True,
            "errors_absent": not errors,
            "fortify_queries_remain_frozen": prior.get(
                "fortify_queries_remain_frozen") is True,
            "frozen_predictions_are_byte_identical": prior.get(
                "frozen_predictions_are_byte_identical") is True,
            "move_queries_are_enriched_when_present": (
                move_choices == 0
                or prior.get("every_move_query_is_enriched") is True),
            "zero_incomplete_move_groundings": prior.get(
                "zero_incomplete_move_groundings") is True,
        }
        games.append({
            "errors": list(errors),
            "game_id": source.get("game_id"),
            "gates": gates,
            "incomplete_grounding_reasons": dict(
                source.get("incomplete_grounding_reasons", {})),
            "measures": measures,
            "passed": all(gates.values()),
            "seed": source.get("seed"),
            "store_digest": source.get("store_digest"),
        })
    totals = dict(legacy["totals"])
    gates = {
        "all_game_feature_invariants_pass": all(
            value["passed"] for value in games),
        "decision_safe_parent_audit_passes": legacy["gates"].get(
            "decision_safe_parent_audit_passes") is True,
        "diverse_multi_move_choice_sets_are_observed": totals.get(
            "diverse_multi_move_choice_sets", 0) >= 1,
        "exact_expected_seeds_completed": legacy["gates"].get(
            "exact_expected_seeds_completed") is True,
        "move_choices_are_observed": totals.get("move_choices", 0) >= 1,
        "multi_move_choice_sets_are_observed": totals.get(
            "multi_move_choice_sets", 0) >= 1,
        "transition_signatures_are_diverse": totals.get(
            "unique_transition_signatures", 0) >= 2,
    }
    result = {
        "audit_identity": AUDIT_IDENTITY,
        "calibration_artifact_hash": legacy["calibration_artifact_hash"],
        "claim_scope": (
            "outcome-free grounded candidate-transition row invariants and "
            "cohort opportunity mechanics; no calibration, counterfactual, "
            "ranking, gameplay, score, or win-rate claim"),
        "decision_safe_parent_audit_hash": (
            legacy["decision_safe_parent_audit_hash"]),
        "games": games,
        "gates": gates,
        "legacy_audit_hash": report_hash,
        "model_result_hash": legacy["model_result_hash"],
        "passed": all(gates.values()),
        "policy_authority": False,
        "readout_authority": False,
        "totals": totals,
        "truth_mutated": False,
    }
    result["report_hash"] = structural_hash(result)
    return result


def audit(run_dir, model_path, expected_seeds, expected_source_commit=None):
    return reinterpret_feature_audit(audit_legacy(
        run_dir, model_path, expected_seeds,
        expected_source_commit=expected_source_commit))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--model", required=True)
    parser.add_argument("--expected-seed", action="append", type=int,
                        required=True)
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = audit(
        args.run_dir, args.model, args.expected_seed,
        expected_source_commit=args.expected_source_commit)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    temporary = output + ".tmp.{}".format(os.getpid())
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
    os.replace(temporary, output)
    print(json.dumps({
        "output": output,
        "passed": report["passed"],
        "report_hash": report["report_hash"],
        "totals": report["totals"],
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
