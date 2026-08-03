#!/usr/bin/env python3
"""Audit a fresh grounded-transition candidate readout engine smoke."""

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

from audit_fdas_decision_safe_candidate_readout import (  # noqa: E402
    _validate_readout,
)
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES,
    FdasCandidateChoiceSetStore,
)


AUDIT_IDENTITY = (
    "fdas-grounded-transition-candidate-readout-audit/1.0")
UNION_COMPONENT_ID = "fdas-grounded-transition-candidate-union"
READOUT_COMPONENT_ID = "fdas-decision-safe-candidate-readout"
CONFIG_SOURCE = (
    "profile/dependent_atomspace_defense_choice_surface_shadow.yaml")
MANIFEST_SOURCE = (
    "profile/fdas_manifest_defense_grounded_transition_readout_shadow.json")
MODEL_RESULT_HASH = (
    "edca977ffc87f9e731e00d5b5bacf3be03e1d5f28887e51e86966cb975ee3aa5")
CALIBRATION_ARTIFACT_HASH = (
    "b954be880a28cdd1cbc505b6d3c9a34d0151a424ef7330f31f3d5759f72c45d0")
CONFIRMATION_REPORT_HASH = (
    "eb15aabe1d2e11eac71f4aaf31939854798445a50fbc76c1e7df32c35326ae42")
MOVE_OPERATION_TYPE = "fdas-shadow:city-garrison-deficit:unit_move"
FORTIFY_OPERATION_TYPE = (
    "fdas-shadow:unit-fortification-opportunity:unit_fortify")
BROAD_BACKOFF_REASONS = frozenset({
    "action-estimate",
    "lifecycle-estimate",
})
CANDIDATE_SPECIFIC_REASONS = frozenset({
    "compact-estimate",
    "compact-lifecycle-estimate",
    "eta-estimate",
    "eta-lifecycle-estimate",
    "full-estimate",
    "full-lifecycle-estimate",
    "route-estimate",
    "route-lifecycle-estimate",
})
ABSTENTION_REASONS = frozenset({
    "insufficient-independent-transition-lineage-support",
    "missing-or-incomplete-transition-grounding",
    "outside-transition-move-domain",
})


def _read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _completed_endpoint(status):
    return bool(
        status.get("completed") is True
        and status.get("infrastructure_failure") is False
        and (status.get("horizon_reached") is True
             or status.get("terminal_game_over") is True
             or status.get("terminal_player_elimination") is True))


def _validate_union(details, payload):
    errors = []
    if not isinstance(details, dict):
        return ("details-not-object",), {}
    semantic = dict(details)
    artifact_hash = semantic.pop("calibration_artifact_hash", None)
    confirmation_hash = semantic.pop("confirmation_report_hash", None)
    model_kind = semantic.pop("calibration_model_kind", None)
    result_hash = semantic.pop("result_hash", None)
    if result_hash != structural_hash(semantic):
        errors.append("candidate-union-result-hash-differs")
    if artifact_hash != CALIBRATION_ARTIFACT_HASH:
        errors.append("calibration-artifact-hash-differs")
    if confirmation_hash != CONFIRMATION_REPORT_HASH:
        errors.append("confirmation-report-hash-differs")
    if model_kind != "grounded-transition":
        errors.append("calibration-model-kind-differs")
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
    if (details.get("identity") != "fdas-calibrated-candidate-union/1.0"
            or details.get("scalar_top_k") != 1
            or details.get("calibrated_per_action") != 1
            or details.get("maximum_interval_width") != 0.55):
        errors.append("frozen-union-configuration-differs")

    readouts = details.get("readouts")
    members = details.get("members")
    additions = details.get("calibrated_added_operation_ids")
    abstained = details.get("abstained_operation_ids")
    if (not isinstance(readouts, list) or not readouts
            or any(not isinstance(value, dict) for value in readouts)
            or not isinstance(members, list) or not members
            or any(not isinstance(value, dict) for value in members)
            or not isinstance(additions, list)
            or not isinstance(abstained, list)):
        return tuple(errors + ["candidate-union-collections-invalid"]), {}

    readout_ids = tuple(value.get("operation_id") for value in readouts)
    member_ids = tuple(value.get("operation_id") for value in members)
    if (None in readout_ids or None in member_ids
            or len(readout_ids) != len(set(readout_ids))
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
    candidate_specific = 0
    broad_backoff = 0
    estimated = 0
    for readout in readouts:
        status = readout.get("prediction_status")
        reason = readout.get("prediction_reason")
        eligible = readout.get("eligible_for_calibrated_recall") is True
        width = readout.get("interval_width")
        operation_type = readout.get("operation_type")
        if (operation_type not in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES
                or not isinstance(readout.get("prediction_result_hash"), str)
                or not readout.get("prediction_result_hash")):
            errors.append("transition-readout-identity-differs")
        if status == "estimated":
            estimated += 1
            if reason in BROAD_BACKOFF_REASONS:
                broad_backoff += 1
            elif reason in CANDIDATE_SPECIFIC_REASONS:
                candidate_specific += 1
            else:
                errors.append("transition-estimate-reason-differs")
            values = tuple(readout.get(name) for name in (
                "estimate", "interval_lower", "interval_upper"))
            if (any(isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or not 0.0 <= float(value) <= 1.0
                    for value in values)
                    or not values[1] <= values[0] <= values[2]
                    or width != values[2] - values[1]
                    or isinstance(readout.get("effective_lineages"), bool)
                    or not isinstance(readout.get("effective_lineages"), int)
                    or readout.get("effective_lineages") < 1):
                errors.append("transition-estimate-values-differ")
            expected_eligible = bool(
                not isinstance(width, bool)
                and isinstance(width, (int, float))
                and math.isfinite(float(width))
                and width <= 0.55)
            expected_eligibility_reason = (
                "supported-calibrated-transition" if expected_eligible
                else "prediction-interval-too-wide")
            if (eligible != expected_eligible
                    or readout.get("eligibility_reason")
                    != expected_eligibility_reason):
                errors.append("transition-estimate-eligibility-differs")
        elif status == "abstained":
            if (reason not in ABSTENTION_REASONS
                    or any(readout.get(name) is not None for name in (
                        "estimate", "interval_lower", "interval_upper",
                        "interval_width"))
                    or readout.get("effective_lineages") != 0
                    or eligible
                    or readout.get("eligibility_reason") != reason):
                errors.append("transition-abstention-differs")
        else:
            errors.append("transition-prediction-status-differs")
        if (operation_type == FORTIFY_OPERATION_TYPE
                and (status != "abstained"
                     or reason != "outside-transition-move-domain")):
            errors.append("fortify-transition-domain-differs")

    calibrated_members = tuple(
        value for value in members
        if "calibrated-transition-recall" in value.get("reasons", ()))
    expected_additions = tuple(
        value.get("operation_id") for value in calibrated_members
        if value.get("operation_id") in readout_by_id
        and isinstance(readout_by_id[value.get("operation_id")].get(
            "baseline_rank"), int)
        and readout_by_id[value.get("operation_id")]["baseline_rank"] > 1)
    if tuple(additions) != expected_additions:
        errors.append("calibrated-addition-set-differs")
    action_counts = {}
    for member in members:
        reasons = set(member.get("reasons", ()))
        if (not reasons or reasons - {
                "calibrated-transition-recall", "scalar-top-k",
                "scalar-winner"}):
            errors.append("candidate-union-member-reasons-differ")
        if "calibrated-transition-recall" not in reasons:
            continue
        readout = readout_by_id.get(member.get("operation_id"), {})
        if readout.get("eligible_for_calibrated_recall") is not True:
            errors.append("calibrated-member-is-not-eligible")
        operation_type = readout.get("operation_type")
        action_counts[operation_type] = action_counts.get(operation_type, 0) + 1
    if any(value > 1 for value in action_counts.values()):
        errors.append("calibrated-per-action-bound-exceeded")
    return tuple(sorted(set(errors))), {
        "abstentions": len(abstained),
        "additions": len(additions),
        "broad_backoff_predictions": broad_backoff,
        "candidate_specific_predictions": candidate_specific,
        "estimated_predictions": estimated,
        "members": len(members),
        "readouts": len(readouts),
        "union_events": 1,
    }


def audit(run_root, expected_seeds, expected_source_commit):
    run_root = os.path.abspath(run_root)
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if (not expected_seeds
            or len(expected_seeds) != len(set(expected_seeds))):
        raise ValueError("grounded-transition audit requires unique seeds")
    if (not isinstance(expected_source_commit, str)
            or len(expected_source_commit) != 40):
        raise ValueError("grounded-transition audit requires full commit")
    game_dirs = tuple(sorted(glob.glob(os.path.join(
        run_root, "games", "main", "e_full_loop", "*"))))
    games = []
    totals = {
        "abstentions": 0,
        "additions": 0,
        "broad_backoff_predictions": 0,
        "candidate_specific_predictions": 0,
        "decision_safe_abstentions": 0,
        "decision_safe_counterfactual_changes": 0,
        "decision_safe_eligible": 0,
        "decision_safe_evaluations": 0,
        "estimated_predictions": 0,
        "interval_overlap_abstentions": 0,
        "members": 0,
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
        game_totals = dict((name, 0) for name in totals)
        union_by_hash = {}
        errors = []
        readout_rows = []
        with open(event_path, encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                payload = event.get("payload", {})
                details = payload.get("details", {})
                component = payload.get("component_id")
                if (event.get("type") != "atomspace_shadow_decision"):
                    continue
                if component == UNION_COMPONENT_ID:
                    union_errors, measures = _validate_union(details, payload)
                    errors.extend(
                        "{}:{}".format(event.get("event_id"), value)
                        for value in union_errors)
                    for name, value in measures.items():
                        game_totals[name] += int(value)
                    if isinstance(details, dict):
                        union_by_hash[details.get("result_hash")] = details
                elif component == READOUT_COMPONENT_ID:
                    readout_rows.append(event)
        for event in readout_rows:
            payload = event.get("payload", {})
            details = payload.get("details", {})
            readout_errors, measures = _validate_readout(
                details, payload,
                union_by_hash.get(details.get("calibrated_union_result_hash")))
            errors.extend(
                "{}:{}".format(event.get("event_id"), value)
                for value in readout_errors)
            game_totals["decision_safe_abstentions"] += measures["abstained"]
            game_totals["decision_safe_counterfactual_changes"] += (
                measures["counterfactual_changes"])
            game_totals["decision_safe_eligible"] += measures["eligible"]
            game_totals["decision_safe_evaluations"] += measures["evaluations"]
            game_totals["interval_overlap_abstentions"] += sum(
                str(value).endswith(":calibrated-interval-overlap")
                for value in details.get("rejected", ()))
        for name, value in game_totals.items():
            totals[name] += value

        declaration = manifest.get("dependent_atomspace", {})
        source = manifest.get("source", {})
        game_gates = {
            "choice_and_readout_counts_match": (
                len(choice_store.choice_sets())
                == game_totals["union_events"]
                == game_totals["decision_safe_evaluations"]
                == status.get("fdas_candidate_choice_sets")),
            "completed_endpoint_without_infrastructure_failure": (
                _completed_endpoint(status)),
            "event_ledger_valid_without_warnings": (
                validation.valid and not validation.warnings),
            "exact_manifest_and_config": (
                declaration.get("config_source") == CONFIG_SOURCE
                and declaration.get("manifest_source") == MANIFEST_SOURCE),
            "grounded_transition_counters_match_status": all(
                status.get("fdas_grounded_transition_" + suffix)
                == game_totals[name]
                for suffix, name in (
                    ("candidate_union_abstentions", "abstentions"),
                    ("candidate_union_additions", "additions"),
                    ("broad_backoff_predictions", "broad_backoff_predictions"),
                    ("candidate_specific_predictions",
                     "candidate_specific_predictions"),
                    ("candidate_union_members", "members"),
                    ("candidate_union_readouts", "union_events"),
                    ("interval_overlap_abstentions",
                     "interval_overlap_abstentions"),
                )),
            "parent_calibrated_counters_match_status": all(
                status.get("fdas_calibrated_candidate_union_" + suffix)
                == game_totals[name]
                for suffix, name in (
                    ("abstentions", "abstentions"),
                    ("additions", "additions"),
                    ("members", "members"),
                    ("readouts", "union_events"),
                )) and status.get(
                    "fdas_calibrated_candidate_union_selection_changes") == 0,
            "decision_safe_counters_match_status": all(
                status.get("fdas_decision_safe_candidate_readout_" + suffix)
                == game_totals[name]
                for suffix, name in (
                    ("abstentions", "decision_safe_abstentions"),
                    ("counterfactual_changes",
                     "decision_safe_counterfactual_changes"),
                    ("eligible", "decision_safe_eligible"),
                    ("evaluations", "decision_safe_evaluations"),
                )),
            "events_are_semantically_valid": not errors,
            "source_is_clean_and_frozen": (
                source.get("dirty") is False
                and source.get("commit") == expected_source_commit),
            "zero_rejected_actions": status.get("rejected_actions") == 0,
        }
        games.append({
            "errors": errors,
            "event_errors": list(validation.errors),
            "event_warnings": list(validation.warnings),
            "game_gates": game_gates,
            "game_id": manifest.get("game_id"),
            "measures": game_totals,
            "runtime_ms": status.get("engine_backend_latency_ms"),
            "seed": manifest.get("seed"),
            "source": source,
        })

    mechanical_gates = {
        "all_game_gates_pass": (
            bool(games)
            and all(all(value["game_gates"].values()) for value in games)),
        "exact_expected_seeds_completed": (
            tuple(sorted(value["seed"] for value in games))
            == tuple(sorted(expected_seeds))),
        "source_identity_is_identical": bool(games) and len({
            structural_hash(value["source"]) for value in games}) == 1,
    }
    yield_gates = {
        "candidate_specific_prediction_observed": (
            totals["candidate_specific_predictions"] > 0),
        "estimated_prediction_observed": totals["estimated_predictions"] > 0,
        "grounded_transition_union_observed": totals["union_events"] > 0,
        "selection_remained_shadow_only": (
            totals["decision_safe_counterfactual_changes"]
            == totals["decision_safe_eligible"]),
    }
    report = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "default-off shadow mechanics and candidate-specific readout "
            "yield only; no counterfactual outcome, ranking quality, gameplay, "
            "score, or win-rate claim"),
        "expected_source_commit": expected_source_commit,
        "games": games,
        "mechanical_gates": mechanical_gates,
        "mechanically_accepted": all(mechanical_gates.values()),
        "passed": all(mechanical_gates.values()) and all(yield_gates.values()),
        "totals": totals,
        "yield_gates": yield_gates,
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
        "report_hash": report["report_hash"],
        "totals": report["totals"],
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
