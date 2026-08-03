#!/usr/bin/env python3
"""Audit clean engine-backed FDAS candidate-transition feature yield."""

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

from audit_fdas_decision_safe_candidate_readout import (  # noqa: E402
    audit as audit_decision_safe,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    CANDIDATE_TRANSITION_FEATURE_KEYS,
    CANDIDATE_TRANSITION_FEATURE_SCHEMA,
    FdasCandidateChoiceSetStore,
    load_candidate_calibration_model,
)
from freeciv_agent.pressure import InductionFeatureQuery  # noqa: E402


AUDIT_IDENTITY = "fdas-candidate-transition-feature-audit/1.0"
SCHEMA_CONTEXT_KEY = "candidate_transition_feature_schema"
FEATURE_PREFIX = "candidate-transition:"
SCHEMA_PROVENANCE = (
    "candidate-transition-feature-schema:"
    + CANDIDATE_TRANSITION_FEATURE_SCHEMA)
GROUNDING_PROVENANCE_PREFIX = "candidate-transition-grounding:"


def _read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _transition_features(query):
    rows = tuple(
        value[len(FEATURE_PREFIX):].split("=", 1)
        for value in query.features if value.startswith(FEATURE_PREFIX))
    if (any(len(value) != 2 or not value[0] or not value[1]
            for value in rows)
            or len({value[0] for value in rows}) != len(rows)):
        raise ValueError("candidate transition features are malformed")
    return dict(rows)


def _stripped_query(query):
    return InductionFeatureQuery(
        query.query_id,
        tuple(
            value for value in query.context
            if value[0] != SCHEMA_CONTEXT_KEY),
        tuple(
            value for value in query.features
            if not value.startswith(FEATURE_PREFIX)),
        tuple(
            value for value in query.provenance_ids
            if value != SCHEMA_PROVENANCE
            and not value.startswith(GROUNDING_PROVENANCE_PREFIX)),
    )


def _audit_game(game_dir, model):
    path = os.path.join(game_dir, "fdas-candidate-choice-sets.json")
    raw = _read_json(path)
    store = FdasCandidateChoiceSetStore.load(
        path, raw.get("persistence_identity"))
    errors = []
    measures = {
        "choice_sets": 0,
        "complete_move_choices": 0,
        "diverse_multi_move_choice_sets": 0,
        "fortify_choices": 0,
        "frozen_prediction_compatibility_checks": 0,
        "incomplete_move_choices": 0,
        "move_choice_sets": 0,
        "move_choices": 0,
        "multi_move_choice_sets": 0,
        "unique_transition_signatures": 0,
    }
    incomplete_reasons = {}
    all_signatures = set()
    if store.quarantined:
        errors.append("candidate-choice-store-is-quarantined")
        rows = ()
    else:
        rows = store.choice_sets()
    measures["choice_sets"] = len(rows)
    for choice_set in rows:
        move_rows = []
        for choice in choice_set.choices:
            try:
                action = json.loads(choice.action_key)
            except (TypeError, ValueError):
                errors.append(
                    choice_set.choice_set_id + ":action-key-is-invalid")
                continue
            query = choice.feature_query
            context = dict(query.context)
            transition_values = tuple(
                value for value in query.provenance_ids
                if value.startswith(GROUNDING_PROVENANCE_PREFIX))
            if action.get("action_type") != "unit_move":
                measures["fortify_choices"] += 1
                if (SCHEMA_CONTEXT_KEY in context
                        or any(value.startswith(FEATURE_PREFIX)
                               for value in query.features)
                        or SCHEMA_PROVENANCE in query.provenance_ids
                        or transition_values):
                    errors.append(
                        choice_set.choice_set_id + ":fortify-query-was-enriched")
                continue
            measures["move_choices"] += 1
            move_rows.append(choice)
            prefix = choice_set.choice_set_id + ":" + choice.operation_id
            try:
                features = _transition_features(query)
            except ValueError:
                features = {}
                errors.append(prefix + ":transition-features-are-invalid")
            if (context.get(SCHEMA_CONTEXT_KEY)
                    != CANDIDATE_TRANSITION_FEATURE_SCHEMA
                    or set(features) != set(
                        CANDIDATE_TRANSITION_FEATURE_KEYS)
                    or query.provenance_ids.count(SCHEMA_PROVENANCE) != 1
                    or len(transition_values) != 1):
                errors.append(prefix + ":transition-schema-is-incomplete")
            status = features.get("transition_grounding_status")
            if (len(transition_values) == 1
                    and transition_values[0][len(
                        GROUNDING_PROVENANCE_PREFIX):] != status):
                errors.append(prefix + ":grounding-provenance-differs")
            if status == "complete":
                measures["complete_move_choices"] += 1
                if any(value == "unknown" for value in features.values()):
                    errors.append(prefix + ":complete-grounding-is-unknown")
                signature = tuple(sorted(features.items()))
                all_signatures.add(signature)
            else:
                measures["incomplete_move_choices"] += 1
                incomplete_reasons[status or "missing"] = (
                    incomplete_reasons.get(status or "missing", 0) + 1)
                if any(
                        value != "unknown"
                        for key, value in features.items()
                        if key != "transition_grounding_status"):
                    errors.append(prefix + ":incomplete-grounding-was-imputed")
            try:
                before = model.predict(_stripped_query(query)).to_dict()
                after = model.predict(query).to_dict()
                measures[
                    "frozen_prediction_compatibility_checks"] += 1
                if before != after:
                    errors.append(prefix + ":frozen-prediction-changed")
            except (KeyError, TypeError, ValueError) as error:
                errors.append(prefix + ":prediction-check-failed:" + str(error))
        if move_rows:
            measures["move_choice_sets"] += 1
        if len(move_rows) >= 2:
            measures["multi_move_choice_sets"] += 1
            signatures = set()
            for choice in move_rows:
                try:
                    features = _transition_features(choice.feature_query)
                except ValueError:
                    continue
                if features.get("transition_grounding_status") == "complete":
                    signatures.add(tuple(sorted(features.items())))
            if len(signatures) >= 2:
                measures["diverse_multi_move_choice_sets"] += 1
    measures["unique_transition_signatures"] = len(all_signatures)
    gates = {
        "candidate_choice_store_is_valid": not store.quarantined,
        "every_move_query_is_enriched": (
            measures["move_choices"] > 0
            and not any("transition-schema-is-incomplete" in value
                        for value in errors)),
        "fortify_queries_remain_frozen": not any(
            "fortify-query-was-enriched" in value for value in errors),
        "frozen_predictions_are_byte_identical": (
            measures["frozen_prediction_compatibility_checks"]
            == measures["move_choices"]
            and not any("prediction" in value for value in errors)),
        "grounded_transition_signatures_are_diverse": (
            measures["unique_transition_signatures"] >= 2
            and measures["diverse_multi_move_choice_sets"] >= 1),
        "multi_move_choice_sets_are_observed": (
            measures["multi_move_choice_sets"] >= 1),
        "zero_incomplete_move_groundings": (
            measures["incomplete_move_choices"] == 0),
    }
    return {
        "errors": sorted(set(errors)),
        "game_id": next((value.game_id for value in rows), None),
        "gates": gates,
        "incomplete_grounding_reasons": incomplete_reasons,
        "measures": measures,
        "passed": all(gates.values()) and not errors,
        "seed": int(os.path.basename(game_dir).split("-", 1)[0]),
        "store_digest": None if store.quarantined else store.store_digest,
    }


def audit(run_dir, model_path, expected_seeds, expected_source_commit=None):
    seeds = tuple(int(value) for value in expected_seeds)
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("feature audit requires unique expected seeds")
    model, calibration_artifact_hash = load_candidate_calibration_model(
        model_path)
    readout = audit_decision_safe(
        run_dir, seeds, expected_source_commit=expected_source_commit)
    game_dirs = tuple(sorted(glob.glob(os.path.join(
        os.path.abspath(run_dir), "games", "*", "*", "*-*"))))
    games = tuple(_audit_game(value, model) for value in game_dirs)
    gates = {
        "all_feature_game_gates_pass": all(
            value["passed"] for value in games),
        "decision_safe_parent_audit_passes": readout["passed"] is True,
        "exact_expected_seeds_completed": (
            tuple(sorted(value["seed"] for value in games))
            == tuple(sorted(seeds))),
    }
    measure_names = tuple(sorted(next(iter(games))["measures"])) if games else ()
    report = {
        "audit_identity": AUDIT_IDENTITY,
        "calibration_artifact_hash": calibration_artifact_hash,
        "claim_scope": (
            "outcome-free grounded candidate-transition feature mechanics; "
            "no calibration, counterfactual, ranking, gameplay, score, or "
            "win-rate claim"),
        "decision_safe_parent_audit_hash": readout["report_hash"],
        "games": list(games),
        "gates": gates,
        "model_result_hash": model.result_hash,
        "passed": all(gates.values()),
        "policy_authority": False,
        "readout_authority": False,
        "totals": {
            name: sum(value["measures"][name] for value in games)
            for name in measure_names},
        "truth_mutated": False,
    }
    report["report_hash"] = structural_hash(report)
    return report


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
