#!/usr/bin/env python3
"""Audit a fresh protected FDAS calibrated candidate-union cohort."""

import argparse
import glob
import json
import math
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES,
    FdasCandidateChoiceSetStore,
)


AUDIT_IDENTITY = "fdas-calibrated-candidate-union-audit/1.0"
COMPONENT_ID = "fdas-calibrated-candidate-union"
CONFIG_SOURCE = (
    "profile/dependent_atomspace_defense_choice_surface_shadow.yaml")
MANIFEST_SOURCE = (
    "profile/fdas_manifest_defense_calibrated_union_shadow.json")
MODEL_RESULT_HASH = (
    "9d2af28d765e75cfe3a0aade43be9d5f0a251904f605dd79394db93363a2562a")
CALIBRATION_ARTIFACT_HASH = (
    "b990cb2ce5dd973c4ded876b114986f3f54d52a358ed57d4f8e1078958d787d9")
CONFIRMATION_REPORT_HASH = (
    "f1bd991a6d78a2554d1ed73f4e67c56c87f1b299c4e4f71db9ef26cc73ec9cc8")
DEFAULT_THRESHOLDS = {
    "calibrated_additions": 8,
    "eligible_readouts": 50,
    "game_addition_rate_wilson_lower": 0.10,
    "games_with_additions": 4,
    "mixed_action_unions": 8,
    "union_readouts": 300,
}


def _read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _wilson(successes, samples, z=1.959963984540054):
    if samples < 1:
        return 0.0, 1.0
    n = float(samples)
    p = float(successes) / n
    denominator = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denominator
    radius = z * math.sqrt(
        p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def _validate_union(details, payload):
    errors = []
    if not isinstance(details, dict):
        return ("details-not-object",), {}
    semantic = dict(details)
    calibration_hash = semantic.pop("calibration_artifact_hash", None)
    confirmation_hash = semantic.pop("confirmation_report_hash", None)
    result_hash = semantic.pop("result_hash", None)
    if result_hash != structural_hash(semantic):
        errors.append("candidate-union-result-hash-differs")
    if calibration_hash != CALIBRATION_ARTIFACT_HASH:
        errors.append("calibration-artifact-hash-differs")
    if confirmation_hash != CONFIRMATION_REPORT_HASH:
        errors.append("confirmation-report-hash-differs")
    if details.get("model_result_hash") != MODEL_RESULT_HASH:
        errors.append("model-result-hash-differs")
    if (details.get("snapshot_id") != payload.get("snapshot_id")
            or details.get("revision_id") != payload.get("revision_id")):
        errors.append("revision-binding-differs")
    if any(details.get(name) is not False for name in (
            "action_selection_changed", "capacity_solver_enabled",
            "flow_advection_enabled", "policy_authority",
            "readout_authority", "truth_mutated")):
        errors.append("shadow-authority-differs")
    if details.get("scalar_final_score_authority") is not True:
        errors.append("scalar-authority-differs")
    if (details.get("scalar_top_k") != 1
            or details.get("calibrated_per_action") != 1
            or details.get("maximum_interval_width") != 0.55):
        errors.append("frozen-union-configuration-differs")
    readouts = details.get("readouts")
    members = details.get("members")
    additions = details.get("calibrated_added_operation_ids")
    abstained = details.get("abstained_operation_ids")
    if (not isinstance(readouts, list) or not readouts
            or not isinstance(members, list) or not members
            or not isinstance(additions, list)
            or not isinstance(abstained, list)):
        return tuple(errors + ["candidate-union-collections-invalid"]), {}
    readout_ids = tuple(value.get("operation_id") for value in readouts)
    member_ids = tuple(value.get("operation_id") for value in members)
    if (len(readout_ids) != len(set(readout_ids))
            or len(member_ids) != len(set(member_ids))
            or set(member_ids) - set(readout_ids)
            or len(members) > 3):
        errors.append("candidate-union-membership-bound-differs")
    ranks = tuple(value.get("baseline_rank") for value in readouts)
    if ranks != tuple(range(1, len(readouts) + 1)):
        errors.append("scalar-ranking-differs")
    readout_by_id = dict(zip(readout_ids, readouts))
    member_by_id = dict(zip(member_ids, members))
    baseline_id = details.get("baseline_selected_operation_id")
    if (baseline_id != readout_ids[0]
            or baseline_id not in member_by_id
            or set(member_by_id[baseline_id].get("reasons", ()))
            < {"scalar-top-k", "scalar-winner"}):
        errors.append("scalar-winner-protection-differs")
    expected_abstained = tuple(
        value["operation_id"] for value in readouts
        if value.get("eligible_for_calibrated_recall") is not True)
    if tuple(abstained) != expected_abstained:
        errors.append("uncertainty-abstention-differs")
    for readout in readouts:
        eligible = readout.get("eligible_for_calibrated_recall") is True
        width = readout.get("interval_width")
        if eligible and (
                readout.get("prediction_status") != "estimated"
                or isinstance(width, bool)
                or not isinstance(width, (int, float))
                or width > 0.55):
            errors.append("eligible-readout-exceeds-confidence-bound")
    calibrated_members = tuple(
        value for value in members
        if "calibrated-transition-recall" in value.get("reasons", ()))
    expected_additions = tuple(
        value["operation_id"] for value in calibrated_members
        if readout_by_id[value["operation_id"]]["baseline_rank"] > 1)
    if tuple(additions) != expected_additions:
        errors.append("calibrated-addition-set-differs")
    action_counts = {}
    for member in calibrated_members:
        readout = readout_by_id.get(member["operation_id"], {})
        if readout.get("eligible_for_calibrated_recall") is not True:
            errors.append("calibrated-member-is-not-eligible")
        operation_type = readout.get("operation_type")
        if operation_type not in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES:
            errors.append("calibrated-member-action-differs")
        action_counts[operation_type] = action_counts.get(operation_type, 0) + 1
    if any(value > 1 for value in action_counts.values()):
        errors.append("calibrated-per-action-bound-exceeded")
    return tuple(errors), {
        "abstentions": len(abstained),
        "additions": len(additions),
        "eligible_readouts": sum(
            value.get("eligible_for_calibrated_recall") is True
            for value in readouts),
        "members": len(members),
        "mixed_action": len(set(
            value.get("operation_type") for value in readouts)) > 1,
        "readouts": len(readouts),
    }


def audit(run_root, expected_seeds, expected_source_commit, thresholds=None,
          cohort_id="fdas_calibrated_candidate_union_confirmation_v1"):
    run_root = os.path.abspath(run_root)
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if (not expected_seeds
            or len(expected_seeds) != len(set(expected_seeds))):
        raise ValueError("candidate-union audit requires unique seeds")
    if not isinstance(expected_source_commit, str) or len(
            expected_source_commit) != 40:
        raise ValueError("candidate-union audit requires full source commit")
    if not isinstance(cohort_id, str) or not cohort_id:
        raise ValueError("candidate-union audit requires cohort identity")
    thresholds = dict(DEFAULT_THRESHOLDS if thresholds is None else thresholds)
    if set(thresholds) != set(DEFAULT_THRESHOLDS):
        raise ValueError("candidate-union audit thresholds differ")
    for name, value in thresholds.items():
        if name == "game_addition_rate_wilson_lower":
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not 0.0 <= float(value) <= 1.0):
                raise ValueError("candidate-union rate threshold is invalid")
        elif (isinstance(value, bool) or not isinstance(value, int)
                or value < 1):
            raise ValueError("candidate-union count threshold is invalid")
    game_dirs = tuple(sorted(glob.glob(os.path.join(
        run_root, "games", "main", "e_full_loop", "*"))))
    games = []
    all_errors = []
    totals = {
        "abstentions": 0,
        "additions": 0,
        "eligible_readouts": 0,
        "members": 0,
        "mixed_action": 0,
        "readouts": 0,
        "union_events": 0,
    }
    for game_dir in game_dirs:
        manifest = _read_json(os.path.join(game_dir, "manifest.json"))
        status = _read_json(os.path.join(game_dir, "status.json"))
        event_path = os.path.join(game_dir, "events.jsonl")
        choice_path = os.path.join(game_dir, "fdas-candidate-choice-sets.json")
        choice_raw = _read_json(choice_path)
        choice_store = FdasCandidateChoiceSetStore.load(
            choice_path, choice_raw["persistence_identity"])
        validation = validate_file(event_path)
        game_totals = dict((key, 0) for key in totals)
        union_errors = []
        with open(event_path, encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                payload = event.get("payload", {})
                if (event.get("type") != "atomspace_shadow_decision"
                        or payload.get("component_id") != COMPONENT_ID):
                    continue
                game_totals["union_events"] += 1
                errors, measures = _validate_union(
                    payload.get("details"), payload)
                union_errors.extend(
                    "{}:{}".format(event.get("event_id"), value)
                    for value in errors)
                for key, value in measures.items():
                    game_totals[key] += int(value)
        for key, value in game_totals.items():
            totals[key] += value
        declaration = manifest.get("dependent_atomspace", {})
        source = manifest.get("source", {})
        game_gates = {
            "candidate_choice_count_matches_union_events": (
                len(choice_store.choice_sets())
                == game_totals["union_events"]
                == status.get("fdas_candidate_choice_sets")),
            "completed_horizon_without_infrastructure_failure": (
                status.get("completed") is True
                and status.get("horizon_reached") is True
                and status.get("infrastructure_failure") is False),
            "event_ledger_valid_without_warnings": (
                validation.valid and not validation.warnings),
            "manifest_profile_is_frozen": (
                declaration.get("config_source") == CONFIG_SOURCE
                and declaration.get("manifest_source") == MANIFEST_SOURCE),
            "source_is_clean_and_frozen": (
                source.get("dirty") is False
                and source.get("commit") == expected_source_commit),
            "union_counters_match_status": all(
                status.get("fdas_calibrated_candidate_union_" + name)
                == game_totals[key]
                for name, key in (
                    ("abstentions", "abstentions"),
                    ("additions", "additions"),
                    ("members", "members"),
                    ("readouts", "union_events"),
                )) and status.get(
                    "fdas_calibrated_candidate_union_selection_changes") == 0,
            "union_events_are_semantically_valid": not union_errors,
            "zero_rejected_actions": status.get("rejected_actions") == 0,
        }
        if not all(game_gates.values()):
            all_errors.extend(
                "seed-{}:{}".format(manifest.get("seed"), name)
                for name, passed in game_gates.items() if not passed)
        all_errors.extend(union_errors)
        games.append({
            "attempt_id": manifest.get("attempt_id"),
            "game_gates": game_gates,
            "game_id": manifest.get("game_id"),
            "measures": game_totals,
            "runtime_ms": status.get("engine_backend_latency_ms"),
            "seed": manifest.get("seed"),
            "source": source,
            "union_errors": union_errors,
        })
    games_with_additions = sum(
        value["measures"]["additions"] > 0 for value in games)
    rate_lower, rate_upper = _wilson(games_with_additions, len(games))
    mechanical_gates = {
        "all_game_gates_pass": bool(games) and not all_errors,
        "exact_preregistered_seeds_completed": (
            tuple(sorted(value["seed"] for value in games))
            == tuple(sorted(expected_seeds))),
        "source_identity_is_identical": bool(games) and len({
            structural_hash(value["source"]) for value in games}) == 1,
    }
    progression_gates = {
        "calibrated_addition_yield": (
            totals["additions"] >= thresholds["calibrated_additions"]),
        "eligible_readout_yield": (
            totals["eligible_readouts"] >= thresholds["eligible_readouts"]),
        "game_level_recurrence": (
            games_with_additions >= thresholds["games_with_additions"]),
        "game_level_recurrence_interval": (
            rate_lower >= thresholds[
                "game_addition_rate_wilson_lower"]),
        "mixed_action_opportunity_yield": (
            totals["mixed_action"] >= thresholds["mixed_action_unions"]),
        "union_readout_yield": (
            totals["union_events"] >= thresholds["union_readouts"]),
    }
    semantic = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "protected candidate recall beyond frozen scalar top-1 on "
            "fresh engine games; no action-selection, counterfactual-outcome, "
            "gameplay, score, or win-rate claim"),
        "cohort_id": cohort_id,
        "expected_source_commit": expected_source_commit,
        "games": games,
        "games_with_additions": games_with_additions,
        "mechanical_gates": mechanical_gates,
        "mechanically_accepted": all(mechanical_gates.values()),
        "progression_gate_passed": all(progression_gates.values()),
        "progression_gates": progression_gates,
        "thresholds": thresholds,
        "totals": totals,
        "wilson_game_addition_rate": {
            "interval_lower": rate_lower,
            "interval_upper": rate_upper,
            "observed_rate": (
                games_with_additions / float(len(games)) if games else 0.0),
        },
    }
    semantic["passed"] = (
        semantic["mechanically_accepted"]
        and semantic["progression_gate_passed"])
    semantic["report_hash"] = structural_hash(semantic)
    return semantic


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("--output")
    parser.add_argument("--expected-seed", action="append", type=int,
                        required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument(
        "--cohort-id",
        default="fdas_calibrated_candidate_union_confirmation_v1")
    parser.add_argument("--minimum-calibrated-additions", type=int, default=8)
    parser.add_argument("--minimum-eligible-readouts", type=int, default=50)
    parser.add_argument(
        "--minimum-game-addition-rate-wilson-lower", type=float,
        default=0.10)
    parser.add_argument("--minimum-games-with-additions", type=int, default=4)
    parser.add_argument("--minimum-mixed-action-unions", type=int, default=8)
    parser.add_argument("--minimum-union-readouts", type=int, default=300)
    args = parser.parse_args(argv)
    thresholds = {
        "calibrated_additions": args.minimum_calibrated_additions,
        "eligible_readouts": args.minimum_eligible_readouts,
        "game_addition_rate_wilson_lower": (
            args.minimum_game_addition_rate_wilson_lower),
        "games_with_additions": args.minimum_games_with_additions,
        "mixed_action_unions": args.minimum_mixed_action_unions,
        "union_readouts": args.minimum_union_readouts,
    }
    report = audit(
        args.run_root, tuple(args.expected_seed),
        args.expected_source_commit, thresholds, args.cohort_id)
    payload = canonical_json_bytes(report) + b"\n"
    if args.output:
        output = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "wb") as stream:
            stream.write(payload)
    else:
        sys.stdout.buffer.write(payload)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
