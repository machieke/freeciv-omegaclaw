#!/usr/bin/env python3
"""Audit fresh engine-backed FDAS decision-safe readout evidence."""

import argparse
import glob
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    DECISION_SAFE_CANDIDATE_READOUT_IDENTITY,
    FdasDecisionSafeCandidateReadoutConfig,
)


AUDIT_IDENTITY = "fdas-decision-safe-candidate-readout-audit/1.0"
COMPONENT_ID = "fdas-decision-safe-candidate-readout"
CALIBRATED_COMPONENT_ID = "fdas-calibrated-candidate-union"
CONFIG_SOURCE = (
    "profile/dependent_atomspace_defense_choice_surface_shadow.yaml")
MANIFEST_SOURCE = (
    "profile/fdas_manifest_defense_decision_safe_readout_shadow.json")
REQUIRED_NONINFERIORITY_CHECKS = frozenset({
    "estimated-turns",
    "first-step-movement-cost",
    "homecity-relation",
    "hit-points",
    "moves-left",
    "total-movement-cost",
    "unit-type",
    "veteran-level",
})


def _read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _events(path):
    with open(path, encoding="utf-8") as stream:
        return tuple(json.loads(line) for line in stream if line.strip())


def _completed_endpoint(status):
    return bool(
        status.get("completed") is True
        and status.get("infrastructure_failure") is False
        and (status.get("horizon_reached") is True
             or status.get("terminal_game_over") is True
             or status.get("terminal_player_elimination") is True))


def _validate_readout(details, payload, calibrated_parent):
    errors = []
    semantic = dict(details)
    result_hash = semantic.pop("result_hash", None)
    if result_hash != structural_hash(semantic):
        errors.append("decision-safe-result-hash-differs")
    if details.get("identity") != DECISION_SAFE_CANDIDATE_READOUT_IDENTITY:
        errors.append("decision-safe-identity-differs")
    if any(details.get(name) is not False for name in (
            "action_selection_changed", "policy_authority",
            "readout_authority", "truth_mutated")):
        errors.append("decision-safe-shadow-authority-differs")
    if (details.get("snapshot_id") != payload.get("snapshot_id")
            or details.get("revision_id") != payload.get("revision_id")):
        errors.append("decision-safe-event-binding-differs")
    if (not isinstance(calibrated_parent, dict)
            or details.get("calibrated_union_result_hash")
            != calibrated_parent.get("result_hash")
            or details.get("snapshot_id")
            != calibrated_parent.get("snapshot_id")
            or details.get("revision_id")
            != calibrated_parent.get("revision_id")):
        errors.append("decision-safe-calibrated-parent-binding-differs")
    try:
        config = FdasDecisionSafeCandidateReadoutConfig.from_dict(
            details.get("config"))
        if config.to_dict() != details.get("config"):
            errors.append("decision-safe-config-is-not-canonical")
    except (TypeError, ValueError):
        config = None
        errors.append("decision-safe-config-is-invalid")
    candidates = details.get("candidates")
    if not isinstance(candidates, list):
        candidates = []
        errors.append("decision-safe-candidates-are-invalid")
    by_id = dict(
        (value.get("operation_id"), value)
        for value in candidates if isinstance(value, dict))
    if (len(by_id) != len(candidates)
            or None in by_id):
        errors.append("decision-safe-candidate-identities-differ")
    status = details.get("status")
    proposed_id = details.get("proposed_operation_id")
    baseline_id = details.get("baseline_operation_id")
    if status == "eligible-shadow":
        control = by_id.get(baseline_id)
        proposed = by_id.get(proposed_id)
        if (details.get("counterfactual_change") is not True
                or control is None or proposed is None
                or proposed_id == baseline_id
                or details.get("reason")
                != "calibrated-and-grounded-dominance"):
            errors.append("decision-safe-eligible-binding-differs")
        if control is not None and proposed is not None:
            separation = (
                0.0 if config is None
                else config.minimum_interval_separation)
            if not (
                    proposed.get("interval_lower")
                    > control.get("interval_upper")
                    and proposed.get("interval_lower")
                    >= control.get("interval_upper") + separation):
                errors.append("decision-safe-intervals-are-not-separated")
            homecity_rank = {"none": 0, "other": 1, "target": 2}
            noninferior = (
                proposed.get("unit_type") == control.get("unit_type")
                and proposed.get("estimated_turns")
                <= control.get("estimated_turns")
                and proposed.get("total_movement_cost")
                <= control.get("total_movement_cost")
                and proposed.get("first_step_movement_cost")
                <= control.get("first_step_movement_cost")
                and proposed.get("hp") >= control.get("hp")
                and proposed.get("moves_left") >= control.get("moves_left")
                and proposed.get("veteran") >= control.get("veteran")
                and homecity_rank.get(proposed.get("homecity_relation"), -1)
                >= homecity_rank.get(control.get("homecity_relation"), 99))
            if not noninferior:
                errors.append("decision-safe-grounded-noninferiority-differs")
            if (set(proposed.get("noninferiority_checks", ()))
                    != REQUIRED_NONINFERIORITY_CHECKS
                    or proposed.get("eligibility_reason") != "eligible"):
                errors.append("decision-safe-grounded-checks-differ")
    elif status == "abstained":
        if (details.get("counterfactual_change") is not False
                or proposed_id is not None):
            errors.append("decision-safe-abstention-gained-preference")
    else:
        errors.append("decision-safe-status-is-invalid")
    measures = {
        "abstained": int(status == "abstained"),
        "candidates": len(candidates),
        "counterfactual_changes": int(
            details.get("counterfactual_change") is True),
        "eligible": int(status == "eligible-shadow"),
        "evaluations": 1,
    }
    return tuple(sorted(set(errors))), measures


def _audit_game(game_dir, expected_source_commit=None):
    events_path = os.path.join(game_dir, "events.jsonl")
    status = _read_json(os.path.join(game_dir, "status.json"))
    manifest = _read_json(os.path.join(game_dir, "manifest.json"))
    events = _events(events_path)
    validation = validate_file(events_path)
    calibrated = {}
    for event in events:
        payload = event.get("payload", {})
        details = payload.get("details", {})
        if (event.get("type") == "atomspace_shadow_decision"
                and payload.get("component_id") == CALIBRATED_COMPONENT_ID):
            calibrated[details.get("result_hash")] = details
    readout_events = tuple(
        event for event in events
        if (event.get("type") == "atomspace_shadow_decision"
            and event.get("payload", {}).get("component_id") == COMPONENT_ID))
    errors = []
    totals = {
        "abstained": 0, "candidates": 0,
        "counterfactual_changes": 0, "eligible": 0, "evaluations": 0,
    }
    for event in readout_events:
        payload = event.get("payload", {})
        details = payload.get("details", {})
        readout_errors, measures = _validate_readout(
            details, payload,
            calibrated.get(details.get("calibrated_union_result_hash")))
        errors.extend(
            "{}:{}".format(event.get("event_id"), value)
            for value in readout_errors)
        for name, value in measures.items():
            totals[name] += value
    source = manifest.get("source", {})
    declared = manifest.get("dependent_atomspace", {})
    gates = {
        "completed_endpoint_without_infrastructure_failure": (
            _completed_endpoint(status)),
        "event_ledger_valid_without_warnings": (
            not validation.errors and not validation.warnings),
        "exact_manifest_and_config": (
            declared.get("config_source") == CONFIG_SOURCE
            and declared.get("manifest_source") == MANIFEST_SOURCE),
        "one_or_more_readout_evaluations": totals["evaluations"] > 0,
        "readout_counters_match_status": all(
            status.get("fdas_decision_safe_candidate_readout_" + name)
            == totals[source_name]
            for name, source_name in (
                ("evaluations", "evaluations"),
                ("eligible", "eligible"),
                ("abstentions", "abstained"),
                ("counterfactual_changes", "counterfactual_changes"),
            )),
        "readouts_are_semantically_valid": not errors,
        "source_is_clean_and_expected": (
            source.get("dirty") is False
            and (expected_source_commit is None
                 or source.get("commit") == expected_source_commit)),
        "zero_rejected_actions": status.get("rejected_actions") == 0,
    }
    return {
        "errors": errors,
        "event_errors": list(validation.errors),
        "event_warnings": list(validation.warnings),
        "game_id": manifest.get("game_id"),
        "gates": gates,
        "measures": totals,
        "passed": all(gates.values()),
        "seed": manifest.get("seed"),
        "source": source,
    }


def audit(run_dir, expected_seeds, expected_source_commit=None):
    seeds = tuple(int(value) for value in expected_seeds)
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("decision-safe audit requires unique expected seeds")
    game_dirs = tuple(sorted(glob.glob(os.path.join(
        os.path.abspath(run_dir), "games", "*", "*", "*-*"))))
    games = tuple(_audit_game(
        game_dir, expected_source_commit=expected_source_commit)
        for game_dir in game_dirs)
    gates = {
        "all_game_gates_pass": all(value["passed"] for value in games),
        "exact_expected_seeds_completed": (
            tuple(sorted(value["seed"] for value in games))
            == tuple(sorted(seeds))),
        "source_identity_is_identical": len({
            json.dumps(value["source"], sort_keys=True)
            for value in games}) == 1,
    }
    report = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "shadow-only calibrated and grounded preference mechanics; no "
            "counterfactual outcome, gameplay, score, or win-rate claim"),
        "games": list(games),
        "gates": gates,
        "passed": all(gates.values()),
        "totals": {
            name: sum(value["measures"][name] for value in games)
            for name in (
                "abstained", "candidates", "counterfactual_changes",
                "eligible", "evaluations")
        },
    }
    report["report_hash"] = structural_hash(report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--expected-seed", action="append", type=int,
                        required=True)
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = audit(
        args.run_dir, args.expected_seed,
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
