#!/usr/bin/env python3
"""Audit exact safety filtering before grounded-transition candidate recall."""

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

from audit_fdas_grounded_transition_candidate_readout import (  # noqa: E402
    UNION_COMPONENT_ID,
    _completed_endpoint,
    _validate_union,
)
from audit_fdas_scalar_baseline_candidate_readout import (  # noqa: E402
    READOUT_COMPONENT_ID,
    _validate_readout,
)
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    DECISION_SAFE_CANDIDATE_FILTER_IDENTITY,
    TARGET_SCOPED_CANDIDATE_FILTER_IDENTITY,
    FdasCandidateChoiceSetStore,
)


AUDIT_IDENTITY = "fdas-safe-filtered-scalar-readout-audit/1.0"
FILTER_COMPONENT_ID = "fdas-decision-safe-candidate-filter"
CONFIG_SOURCE = (
    "profile/dependent_atomspace_defense_choice_surface_shadow.yaml")
MANIFEST_SOURCE = (
    "profile/fdas_manifest_defense_safe_filtered_scalar_readout_shadow.json")
TARGET_SCOPED_MANIFEST_SOURCE = (
    "profile/fdas_manifest_defense_target_scoped_scalar_readout_shadow.json")
TARGET_FILTER_COMPONENT_ID = "fdas-target-scoped-candidate-filter"


def _read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _validate_filter(details, payload):
    errors = []
    if not isinstance(details, dict):
        return ("details-not-object",), {}
    semantic = dict(details)
    result_hash = semantic.pop("result_hash", None)
    if result_hash != structural_hash(semantic):
        errors.append("candidate-filter-result-hash-differs")
    if details.get("identity") != DECISION_SAFE_CANDIDATE_FILTER_IDENTITY:
        errors.append("candidate-filter-identity-differs")
    if any(details.get(name) is not False for name in (
            "action_selection_changed", "policy_authority",
            "readout_authority", "truth_mutated")):
        errors.append("candidate-filter-shadow-authority-differs")
    if (details.get("candidate_surface_preserved") is not True
            or details.get("calibrated_union_input_filtered") is not True):
        errors.append("candidate-filter-boundary-differs")
    if (details.get("snapshot_id") != payload.get("snapshot_id")
            or details.get("revision_id") != payload.get("revision_id")):
        errors.append("candidate-filter-revision-binding-differs")
    readouts = details.get("readouts")
    eligible = details.get("eligible_operation_ids")
    excluded = details.get("excluded_operation_ids")
    if (not isinstance(readouts, list) or not readouts
            or any(not isinstance(value, dict) for value in readouts)
            or not isinstance(eligible, list)
            or not isinstance(excluded, list)
            or details.get("input_candidate_count") != len(readouts)):
        return tuple(errors + ["candidate-filter-collections-differ"]), {}
    operation_ids = tuple(value.get("operation_id") for value in readouts)
    if None in operation_ids or len(operation_ids) != len(set(operation_ids)):
        errors.append("candidate-filter-operation-identities-differ")
    expected_eligible = tuple(
        value.get("operation_id") for value in readouts
        if value.get("status") == "eligible")
    expected_excluded = tuple(
        value.get("operation_id") for value in readouts
        if value.get("status") == "excluded")
    if (tuple(eligible) != expected_eligible
            or tuple(excluded) != expected_excluded
            or set(eligible).intersection(excluded)
            or set(eligible).union(excluded) != set(operation_ids)):
        errors.append("candidate-filter-partition-differs")
    source_garrison_exclusions = 0
    for readout in readouts:
        row_semantic = dict(readout)
        row_hash = row_semantic.pop("result_hash", None)
        if row_hash != structural_hash(row_semantic):
            errors.append("candidate-filter-row-hash-differs")
        blockers = readout.get("blockers")
        if (not isinstance(blockers, list)
                or blockers != sorted(set(blockers))
                or any(not isinstance(value, str) or not value
                       for value in blockers)):
            errors.append("candidate-filter-blockers-differ")
            blockers = []
        if readout.get("status") == "eligible":
            if (readout.get("reason") is not None
                    or not isinstance(readout.get("source_atom_id"), str)
                    or not readout.get("source_atom_id")):
                errors.append("eligible-candidate-filter-row-differs")
            if "protected-source-garrison" in blockers:
                errors.append("protected-source-garrison-became-eligible")
        elif readout.get("status") == "excluded":
            if (not isinstance(readout.get("reason"), str)
                    or not readout.get("reason")
                    or readout.get("source_atom_id") is not None):
                errors.append("excluded-candidate-filter-row-differs")
            if "protected-source-garrison" in blockers:
                source_garrison_exclusions += 1
        else:
            errors.append("candidate-filter-row-status-differs")
    return tuple(sorted(set(errors))), {
        "eligible": len(eligible),
        "empty_surfaces": int(not eligible),
        "evaluations": 1,
        "excluded": len(excluded),
        "inputs": len(readouts),
        "source_garrison_exclusions": source_garrison_exclusions,
    }


def _validate_target_filter(details, payload):
    errors = []
    if not isinstance(details, dict):
        return ("details-not-object",), {}
    semantic = dict(details)
    result_hash = semantic.pop("result_hash", None)
    if result_hash != structural_hash(semantic):
        errors.append("target-filter-result-hash-differs")
    if details.get("identity") != TARGET_SCOPED_CANDIDATE_FILTER_IDENTITY:
        errors.append("target-filter-identity-differs")
    if any(details.get(name) is not False for name in (
            "action_selection_changed", "policy_authority",
            "readout_authority", "truth_mutated")):
        errors.append("target-filter-shadow-authority-differs")
    if (details.get("candidate_surface_preserved") is not True
            or details.get("calibrated_union_input_filtered") is not True
            or details.get("snapshot_id") != payload.get("snapshot_id")
            or details.get("revision_id") != payload.get("revision_id")):
        errors.append("target-filter-boundary-differs")
    rows = details.get("readouts")
    in_scope = details.get("in_scope_operation_ids")
    out_scope = details.get("out_of_scope_operation_ids")
    if (not isinstance(rows, list) or not rows
            or any(not isinstance(value, dict) for value in rows)
            or not isinstance(in_scope, list)
            or not isinstance(out_scope, list)
            or details.get("input_candidate_count") != len(rows)):
        return tuple(errors + ["target-filter-collections-differ"]), {}
    operation_ids = tuple(value.get("operation_id") for value in rows)
    expected_in = tuple(value.get("operation_id") for value in rows
                        if value.get("status") == "in-scope")
    expected_out = tuple(value.get("operation_id") for value in rows
                         if value.get("status") == "out-of-scope")
    if (None in operation_ids or len(operation_ids) != len(set(operation_ids))
            or tuple(in_scope) != expected_in
            or tuple(out_scope) != expected_out
            or set(in_scope).intersection(out_scope)
            or set(in_scope).union(out_scope) != set(operation_ids)
            or details.get("baseline_operation_id") not in in_scope):
        errors.append("target-filter-partition-differs")
    baseline_type = details.get("baseline_operation_type")
    baseline_target = details.get("baseline_target_ref")
    for row in rows:
        row_semantic = dict(row)
        row_hash = row_semantic.pop("result_hash", None)
        if row_hash != structural_hash(row_semantic):
            errors.append("target-filter-row-hash-differs")
        failures = row.get("scope_failures")
        if (not isinstance(failures, list)
                or failures != sorted(set(failures))
                or set(failures) - {
                    "operation-type-mismatch", "target-ref-mismatch"}):
            errors.append("target-filter-row-failures-differ")
            continue
        expected = []
        if row.get("operation_type") != baseline_type:
            expected.append("operation-type-mismatch")
        if row.get("target_ref") != baseline_target:
            expected.append("target-ref-mismatch")
        if (failures != sorted(expected)
                or (row.get("status") == "in-scope") != (not expected)):
            errors.append("target-filter-row-scope-differs")
    return tuple(sorted(set(errors))), {
        "evaluations": 1,
        "in_scope": len(in_scope),
        "inputs": len(rows),
        "out_of_scope": len(out_scope),
        "singleton_surfaces": int(len(in_scope) == 1),
    }


def audit(run_root, expected_seeds, expected_source_commit,
          *, target_scoped=False, target_scoped_manifest_source=None):
    run_root = os.path.abspath(run_root)
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if (not expected_seeds
            or len(expected_seeds) != len(set(expected_seeds))):
        raise ValueError("safe-filter audit requires unique seeds")
    if (not isinstance(expected_source_commit, str)
            or len(expected_source_commit) != 40):
        raise ValueError("safe-filter audit requires full commit")
    game_dirs = tuple(sorted(glob.glob(os.path.join(
        run_root, "games", "main", "e_full_loop", "*"))))
    totals = {
        "filter_eligible": 0,
        "filter_empty_surfaces": 0,
        "filter_evaluations": 0,
        "filter_excluded": 0,
        "filter_inputs": 0,
        "filter_source_garrison_exclusions": 0,
        "grounded_controls": 0,
        "readout_abstentions": 0,
        "readout_eligible": 0,
        "readout_evaluations": 0,
        "readout_grounded_alternatives": 0,
        "readout_interval_overlaps": 0,
        "readout_shadow_preferences": 0,
        "union_abstentions": 0,
        "union_additions": 0,
        "union_broad_backoff_predictions": 0,
        "union_candidate_specific_predictions": 0,
        "union_estimated_predictions": 0,
        "union_events": 0,
        "union_members": 0,
        "union_readouts": 0,
    }
    if target_scoped:
        totals.update({
            "target_filter_evaluations": 0,
            "target_filter_in_scope": 0,
            "target_filter_inputs": 0,
            "target_filter_out_of_scope": 0,
            "target_filter_singleton_surfaces": 0,
        })
    games = []
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
        filters_by_event = {}
        target_filters_by_event = {}
        unions_by_hash = {}
        readout_events = []
        errors = []
        with open(event_path, encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                payload = event.get("payload", {})
                details = payload.get("details", {})
                component = payload.get("component_id")
                if event.get("type") != "atomspace_shadow_decision":
                    continue
                if component == FILTER_COMPONENT_ID:
                    filter_errors, measures = _validate_filter(details, payload)
                    errors.extend(
                        "{}:{}".format(event.get("event_id"), value)
                        for value in filter_errors)
                    for name, value in measures.items():
                        game_totals["filter_" + name] += int(value)
                    filters_by_event[event.get("event_id")] = details
                elif component == TARGET_FILTER_COMPONENT_ID:
                    target_errors, measures = _validate_target_filter(
                        details, payload)
                    errors.extend(
                        "{}:{}".format(event.get("event_id"), value)
                        for value in target_errors)
                    for name, value in measures.items():
                        game_totals["target_filter_" + name] += int(value)
                    parent_ids = tuple(event.get("caused_by", ()))
                    safety_parent = (
                        filters_by_event.get(parent_ids[0])
                        if len(parent_ids) == 1 else None)
                    target_partition = set(details.get(
                        "in_scope_operation_ids", ())).union(
                            details.get("out_of_scope_operation_ids", ()))
                    if (safety_parent is None
                            or target_partition != set(safety_parent.get(
                                "eligible_operation_ids", ()))
                            or details.get("snapshot_id")
                            != safety_parent.get("snapshot_id")
                            or details.get("revision_id")
                            != safety_parent.get("revision_id")):
                        errors.append(
                            "{}:target-filter-safety-parent-differs".format(
                                event.get("event_id")))
                    target_filters_by_event[event.get("event_id")] = details
                elif component == UNION_COMPONENT_ID:
                    union_errors, measures = _validate_union(
                        details, payload,
                        calibrated_additions_only=target_scoped)
                    errors.extend(
                        "{}:{}".format(event.get("event_id"), value)
                        for value in union_errors)
                    mapping = {
                        "abstentions": "union_abstentions",
                        "additions": "union_additions",
                        "broad_backoff_predictions": (
                            "union_broad_backoff_predictions"),
                        "candidate_specific_predictions": (
                            "union_candidate_specific_predictions"),
                        "estimated_predictions": "union_estimated_predictions",
                        "members": "union_members",
                        "readouts": "union_readouts",
                        "union_events": "union_events",
                    }
                    for name, value in measures.items():
                        game_totals[mapping[name]] += int(value)
                    parent_ids = tuple(event.get("caused_by", ()))
                    filter_parent = ((
                        target_filters_by_event.get(parent_ids[0])
                        if target_scoped else
                        filters_by_event.get(parent_ids[0]))
                        if len(parent_ids) == 1 else None)
                    union_ids = set(
                        value.get("operation_id")
                        for value in details.get("readouts", ())
                        if isinstance(value, dict))
                    eligible_ids = set(
                        filter_parent.get(
                            "in_scope_operation_ids" if target_scoped
                            else "eligible_operation_ids", ()))
                    if (filter_parent is None
                            or details.get("snapshot_id")
                            != filter_parent.get("snapshot_id")
                            or details.get("revision_id")
                            != filter_parent.get("revision_id")
                            or union_ids - eligible_ids):
                        errors.append(
                            "{}:candidate-union-filter-parent-differs".format(
                                event.get("event_id")))
                    unions_by_hash[details.get("result_hash")] = details
                elif component == READOUT_COMPONENT_ID:
                    readout_events.append(event)
        for event in readout_events:
            payload = event.get("payload", {})
            details = payload.get("details", {})
            readout_errors, measures = _validate_readout(
                details, payload,
                unions_by_hash.get(details.get("protected_union_result_hash")))
            errors.extend(
                "{}:{}".format(event.get("event_id"), value)
                for value in readout_errors)
            for name, value in measures.items():
                game_totals["readout_" + name] += int(value)
            candidates = details.get("candidates", ())
            if (isinstance(candidates, list)
                    and any(isinstance(value, dict)
                            and value.get("operation_id")
                            == details.get("baseline_operation_id")
                            for value in candidates)):
                game_totals["grounded_controls"] += 1
        for name, value in game_totals.items():
            totals[name] += value

        declaration = manifest.get("dependent_atomspace", {})
        source = manifest.get("source", {})
        game_gates = {
            "choice_count_matches_filter_events": (
                len(choice_store.choice_sets())
                == game_totals["filter_evaluations"]
                == status.get("fdas_candidate_choice_sets")),
            "completed_endpoint_without_infrastructure_failure": (
                _completed_endpoint(status)),
            "event_ledger_valid_without_warnings": (
                validation.valid and not validation.warnings),
            "exact_manifest_and_config": (
                declaration.get("config_source") == CONFIG_SOURCE
                and declaration.get("manifest_source") == (
                    (target_scoped_manifest_source
                     or TARGET_SCOPED_MANIFEST_SOURCE)
                    if target_scoped else MANIFEST_SOURCE)),
            "filter_counters_match_status": all(
                status.get("fdas_decision_safe_candidate_filter_" + suffix)
                == game_totals["filter_" + name]
                for suffix, name in (
                    ("eligible", "eligible"),
                    ("empty_surfaces", "empty_surfaces"),
                    ("evaluations", "evaluations"),
                    ("excluded", "excluded"),
                    ("inputs", "inputs"),
                    ("source_garrison_exclusions",
                     "source_garrison_exclusions"),
                )),
            "readout_and_union_counts_match": (
                game_totals["readout_evaluations"]
                == game_totals["union_events"]
                <= game_totals["filter_evaluations"]),
            "readout_counters_match_status": all(
                status.get("fdas_scalar_baseline_candidate_readout_" + suffix)
                == game_totals["readout_" + name]
                for suffix, name in (
                    ("abstentions", "abstentions"),
                    ("eligible", "eligible"),
                    ("evaluations", "evaluations"),
                    ("grounded_alternatives", "grounded_alternatives"),
                    ("interval_overlaps", "interval_overlaps"),
                    ("shadow_preferences", "shadow_preferences"),
                )),
            "union_counters_match_status": all(
                status.get("fdas_grounded_transition_" + suffix)
                == game_totals[name]
                for suffix, name in (
                    ("candidate_union_abstentions", "union_abstentions"),
                    ("candidate_union_additions", "union_additions"),
                    ("broad_backoff_predictions",
                     "union_broad_backoff_predictions"),
                    ("candidate_specific_predictions",
                     "union_candidate_specific_predictions"),
                    ("candidate_union_members", "union_members"),
                    ("candidate_union_readouts", "union_events"),
                )),
            "events_are_semantically_valid": not errors,
            "source_is_clean_and_frozen": (
                source.get("dirty") is False
                and source.get("commit") == expected_source_commit),
            "zero_rejected_actions": status.get("rejected_actions") == 0,
        }
        if target_scoped:
            game_gates["target_filter_counters_match_status"] = all(
                status.get("fdas_target_scoped_candidate_filter_" + suffix)
                == game_totals["target_filter_" + name]
                for suffix, name in (
                    ("evaluations", "evaluations"),
                    ("inputs", "inputs"),
                    ("in_scope", "in_scope"),
                    ("out_of_scope", "out_of_scope"),
                    ("singleton_surfaces", "singleton_surfaces"),
                ))
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
            totals["union_candidate_specific_predictions"] > 0),
        "grounded_safe_control_observed": totals["grounded_controls"] > 0,
        "protected_source_garrison_excluded": (
            totals["filter_source_garrison_exclusions"] > 0),
        "safe_candidate_reached_union": totals["union_events"] > 0,
    }
    report = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "exact pre-union candidate safety filtering and scalar-control "
            "mechanics only; no preference, ranking, counterfactual outcome, "
            "gameplay, score, or win-rate claim"),
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
