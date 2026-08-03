#!/usr/bin/env python3
"""Audit a preregistered multi-game FDAS candidate-choice yield pilot."""

import argparse
import glob
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

from audit_fdas_candidate_choices import audit as audit_choices  # noqa: E402
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES,
    DEFENSE_CANDIDATE_CHOICE_SURFACE,
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    FdasCandidateChoiceSetStore,
    combine_candidate_choice_stores,
)


PILOT_ID = "fdas_candidate_choice_yield_pilot_v1"
EXPECTED_SEEDS = (104743, 104759, 104761)


def _load_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _load_choice_store(path):
    raw = _load_json(path)
    return FdasCandidateChoiceSetStore.load(
        path, raw["persistence_identity"])


def _choice_component_authority_safe(path):
    count = 0
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            event = json.loads(line)
            payload = event.get("payload", {})
            if payload.get("component_id") != (
                    "fdas-induced-rule-candidate-choice-set"):
                continue
            count += 1
            details = payload.get("details", {})
            if (details.get("truth_mutated") is not False
                    or details.get("readout_authority") is not False
                    or details.get("policy_authority") is not False
                    or details.get("action_selection_changed") is not False):
                return count, False
    return count, count > 0


def _choice_operation_type(choice):
    context = dict(choice.feature_query.context)
    value = context.get("operation_type")
    if not isinstance(value, str) or not value:
        raise ValueError("candidate choice lacks exact operation type")
    return value


def _choice_actor_id(choice):
    action = json.loads(choice.action_key)
    actor_id = action.get("actor_id")
    if (isinstance(actor_id, bool) or not isinstance(actor_id, int)
            or actor_id < 0):
        raise ValueError("candidate choice lacks exact unit actor")
    return actor_id


def audit(run_root, expected_seeds=EXPECTED_SEEDS, pilot_id=PILOT_ID,
          require_surface_strata=False):
    run_root = os.path.abspath(run_root)
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if (not expected_seeds
            or len(expected_seeds) != len(set(expected_seeds))):
        raise ValueError("yield audit requires unique expected seeds")
    if not isinstance(pilot_id, str) or not pilot_id:
        raise ValueError("yield audit requires pilot identity")
    game_dirs = tuple(sorted(glob.glob(os.path.join(
        run_root, "games", "main", "e_full_loop", "*"))))
    rows = []
    choice_paths = []
    validation_reports = []
    component_event_count = 0
    component_authority_safe = True
    for game_dir in game_dirs:
        manifest = _load_json(os.path.join(game_dir, "manifest.json"))
        status = _load_json(os.path.join(game_dir, "status.json"))
        choice_path = os.path.join(
            game_dir, "fdas-candidate-choice-sets.json")
        event_path = os.path.join(game_dir, "events.jsonl")
        validation = validate_file(event_path)
        component_count, authority_safe = (
            _choice_component_authority_safe(event_path))
        validation_reports.append(validation)
        component_event_count += component_count
        component_authority_safe = (
            component_authority_safe and authority_safe)
        choice_paths.append(choice_path)
        rows.append({
            "attempt_id": manifest["attempt_id"],
            "choice_store_path": os.path.relpath(
                choice_path, REPO).replace(os.sep, "/"),
            "completed": status.get("completed") is True,
            "event_count": validation.event_count,
            "event_errors": len(validation.errors),
            "event_warnings": len(validation.warnings),
            "game_id": manifest["game_id"],
            "horizon_reached": status.get("horizon_reached") is True,
            "infrastructure_failure": status.get(
                "infrastructure_failure") is True,
            "rejected_actions": status.get("rejected_actions"),
            "runtime_ms": status.get("engine_backend_latency_ms"),
            "seed": manifest["seed"],
            "source": manifest.get("source"),
        })
    choice_audit = audit_choices(tuple(choice_paths))
    stores = tuple(_load_choice_store(path) for path in choice_paths)
    cohort_store = (
        stores[0] if len(stores) == 1 else
        combine_candidate_choice_stores(
            stores,
            choice_audit["artifact"]["cohort_persistence_identity"]))
    choice_sets = cohort_store.choice_sets()
    selected_rows = tuple(
        row for value in choice_sets for row in value.choices
        if row.selection_role == "selected")
    observed_sets = tuple(
        value for value in choice_sets
        if value.outcome_status == "observed")
    feature_signatures = set(structural_hash({
        "context": list(row.feature_query.context),
        "features": list(row.feature_query.features),
    }) for row in selected_rows)
    actor_context_signatures = set(structural_hash({
        "action_key": row.action_key,
        "actor_features": [
            value for value in row.feature_query.features
            if value.startswith((
                "context:actor_", "context:other_fortified_units_",
                "context:other_own_units_", "context:own_units_"))],
    }) for row in selected_rows)
    engine_hours = sum(
        float(row["runtime_ms"] or 0.0) for row in rows) / 3600000.0
    source_identities = tuple(
        structural_hash(row["source"]) for row in rows)
    mechanical_gates = {
        "all_candidate_choice_audit_gates_pass": choice_audit["passed"],
        "all_event_ledgers_valid_without_warnings": all(
            value.valid and not value.warnings
            for value in validation_reports),
        "all_games_completed_horizon": all(
            value["completed"] and value["horizon_reached"]
            for value in rows),
        "all_games_have_zero_rejected_actions": all(
            value["rejected_actions"] == 0 for value in rows),
        "candidate_choice_component_is_non_authorizing": (
            component_authority_safe),
        "exact_preregistered_seeds_completed": (
            tuple(sorted(value["seed"] for value in rows))
            == tuple(sorted(expected_seeds))),
        "no_infrastructure_failures": not any(
            value["infrastructure_failure"] for value in rows),
        "source_is_clean_and_identical": bool(rows) and (
            len(set(source_identities)) == 1
            and all(value["source"].get("dirty") is False
                    for value in rows)),
    }
    if require_surface_strata:
        mechanical_gates["exact_defense_choice_surface_scope"] = bool(
            choice_audit["operation_type"]
            == DEFENSE_CANDIDATE_CHOICE_SURFACE
            and choice_audit["outcome_target"]
            == DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET)
    selected_operation_type_counts = dict(
        (operation_type, sum(
            _choice_operation_type(row) == operation_type
            for row in selected_rows))
        for operation_type in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES)
    choice_operation_type_counts = dict(
        (operation_type, sum(
            _choice_operation_type(row) == operation_type
            for value in choice_sets for row in value.choices))
        for operation_type in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES)
    selected_operation_type_lineages = dict(
        (operation_type, set(
            (value.game_id, _choice_actor_id(row), operation_type)
            for value in choice_sets for row in value.choices
            if (row.selection_role == "selected"
                and _choice_operation_type(row) == operation_type)))
        for operation_type in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES)
    observed_operation_type_lineages = dict(
        (operation_type, set(
            (value.game_id, _choice_actor_id(row), operation_type)
            for value in observed_sets for row in value.choices
            if (row.selection_role == "selected"
                and _choice_operation_type(row) == operation_type)))
        for operation_type in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES)
    yield_measures = {
        "actor_context_signatures": len(actor_context_signatures),
        "choice_sets": len(choice_sets),
        "choices": sum(len(value.choices) for value in choice_sets),
        "distinct_selected_feature_signatures": len(feature_signatures),
        "engine_hours": engine_hours,
        "multi_candidate_choice_sets": sum(
            len(value.choices) > 1 for value in choice_sets),
        "mixed_operation_type_choice_sets": sum(
            len(set(_choice_operation_type(row) for row in value.choices))
            > 1 for value in choice_sets),
        "no_in_scope_selection_sets": sum(
            value.selected_operation_id is None for value in choice_sets),
        "nonselected_censored_choices": sum(
            row.selection_role == "nonselected-censored"
            for value in choice_sets for row in value.choices),
        "observed_negative_selected_outcomes": sum(
            value.observed_outcome is False for value in observed_sets),
        "observed_positive_selected_outcomes": sum(
            value.observed_outcome is True for value in observed_sets),
        "observed_selected_outcomes": len(observed_sets),
        "observed_selected_outcomes_per_engine_hour": (
            len(observed_sets) / engine_hours if engine_hours > 0.0 else 0.0),
        "selected_pending_or_censored": sum(
            value.selected_operation_id is not None
            and value.outcome_status != "observed"
            for value in choice_sets),
        "selected_operation_type_counts": (
            selected_operation_type_counts),
        "selected_operation_type_lineage_counts": dict(
            (key, len(value)) for key, value in
            selected_operation_type_lineages.items()),
        "observed_operation_type_lineage_counts": dict(
            (key, len(value)) for key, value in
            observed_operation_type_lineages.items()),
        "choice_operation_type_counts": choice_operation_type_counts,
    }
    progression_gates = {
        "actor_context_signature_yield": (
            yield_measures["actor_context_signatures"] >= 3),
        "multi_candidate_yield": (
            yield_measures["multi_candidate_choice_sets"] >= 3),
        "observed_selected_outcome_yield": (
            yield_measures["observed_selected_outcomes"] >= 12),
        "outcome_contrast_yield": (
            yield_measures["observed_positive_selected_outcomes"] >= 2
            and yield_measures["observed_negative_selected_outcomes"] >= 2),
    }
    if require_surface_strata:
        progression_gates.update({
            "mixed_action_strata_yield": (
                yield_measures["mixed_operation_type_choice_sets"] >= 3),
            "selected_action_strata_yield": all(
                selected_operation_type_counts.get(value, 0) >= 2
                for value in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES),
            "selected_action_strata_lineage_yield": all(
                len(selected_operation_type_lineages.get(value, ())) >= 2
                for value in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES),
            "observed_action_strata_lineage_yield": all(
                len(observed_operation_type_lineages.get(value, ())) >= 2
                for value in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES),
        })
    semantic = {
        "candidate_choice_audit": choice_audit,
        "claim_scope": (
            "claim-ineligible candidate-choice mechanism/yield pilot; no "
            "model fit, calibration, ranking, gameplay, score, or win-rate "
            "claim"),
        "component_event_count": component_event_count,
        "games": rows,
        "mechanical_gates": mechanical_gates,
        "mechanically_accepted": all(mechanical_gates.values()),
        "pilot_id": pilot_id,
        "progression_gate_passed": all(progression_gates.values()),
        "progression_gates": progression_gates,
        "schema_version": "fdas-candidate-choice-yield-audit/1.0",
        "yield_measures": yield_measures,
    }
    semantic["report_hash"] = structural_hash(semantic)
    return semantic


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("--output")
    parser.add_argument(
        "--expected-seed", action="append", type=int,
        help="repeat for each preregistered seed; defaults to PR34")
    parser.add_argument("--pilot-id", default=PILOT_ID)
    parser.add_argument("--require-surface-strata", action="store_true")
    args = parser.parse_args(argv)
    report = audit(
        args.run_root,
        expected_seeds=(
            tuple(args.expected_seed)
            if args.expected_seed else EXPECTED_SEEDS),
        pilot_id=args.pilot_id,
        require_surface_strata=args.require_surface_strata)
    payload = canonical_json_bytes(report) + b"\n"
    if args.output:
        output = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "wb") as stream:
            stream.write(payload)
    else:
        sys.stdout.buffer.write(payload)
    return 0 if report["mechanically_accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
