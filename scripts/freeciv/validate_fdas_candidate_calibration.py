#!/usr/bin/env python3
"""Validate a frozen FDAS candidate calibration on disjoint engine games."""

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

from audit_fdas_candidate_choice_yield import audit as audit_yield  # noqa: E402
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import (  # noqa: E402
    DEFENSE_CANDIDATE_CHOICE_SURFACE,
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    FdasCandidateChoiceSetStore,
    evaluate_candidate_calibration,
    export_candidate_choice_calibration,
    load_candidate_calibration_model,
)


DEFAULT_YIELD_THRESHOLDS = {
    "actor_context_signatures": 8,
    "mixed_operation_type_choice_sets": 8,
    "multi_candidate_choice_sets": 10,
    "observed_each_outcome": 8,
    "observed_operation_type_lineages": 5,
    "observed_selected_outcomes": 40,
    "selected_each_operation_type": 5,
    "selected_operation_type_lineages": 5,
}


def _choice_paths(run_root):
    return tuple(sorted(glob.glob(os.path.join(
        os.path.abspath(run_root), "games", "main", "e_full_loop", "*",
        "fdas-candidate-choice-sets.json"))))


def _load_store(path):
    with open(path, encoding="utf-8") as stream:
        raw = json.load(stream)
    return FdasCandidateChoiceSetStore.load(
        path, raw["persistence_identity"])


def validation_report(
        run_root, model_path, confirmation_id, expected_seeds,
        expected_model_hash, yield_thresholds, validation_thresholds,
        bootstrap_samples=2000, bootstrap_seed=7751):
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if not expected_seeds or len(expected_seeds) != len(set(expected_seeds)):
        raise ValueError("confirmation requires unique expected seeds")
    model, artifact_hash = load_candidate_calibration_model(model_path)
    if model.result_hash != expected_model_hash:
        raise ValueError("confirmation model hash differs from frozen model")
    source_audit = audit_yield(
        run_root, expected_seeds=expected_seeds,
        pilot_id=confirmation_id, require_surface_strata=True,
        require_durable_lineages=True,
        progression_thresholds=yield_thresholds)
    if not source_audit["mechanically_accepted"]:
        raise ValueError("confirmation mechanical gate failed")
    if not source_audit["progression_gate_passed"]:
        raise ValueError("confirmation progression gate failed")
    paths = _choice_paths(run_root)
    if len(paths) != len(expected_seeds):
        raise ValueError("confirmation store count differs")
    stores = tuple(_load_store(path) for path in paths)
    exports = tuple(export_candidate_choice_calibration(
        store, DEFENSE_CANDIDATE_CHOICE_SURFACE,
        DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET) for store in stores)
    validation = evaluate_candidate_calibration(
        model, exports, confirmation_id, validation_thresholds,
        bootstrap_samples, bootstrap_seed)
    semantic = {
        "calibration_artifact_hash": artifact_hash,
        "claim_scope": validation["claim_scope"],
        "confirmation_id": confirmation_id,
        "model_result_hash": model.result_hash,
        "passed": validation["passed"],
        "policy_authority": False,
        "readout_authority": False,
        "schema_version": "fdas-candidate-calibration-confirmation/1.0",
        "source_store_paths": [
            os.path.relpath(path, REPO).replace(os.sep, "/")
            for path in paths],
        "truth_mutated": False,
        "validation": validation,
        "yield_report_hash": source_audit["report_hash"],
    }
    semantic["report_hash"] = structural_hash(semantic)
    return semantic, source_audit


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--yield-output", required=True)
    parser.add_argument("--confirmation-id", required=True)
    parser.add_argument("--expected-model-hash", required=True)
    parser.add_argument("--expected-seed", action="append", type=int,
                        required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=7751)
    parser.add_argument("--minimum-observed-selected-outcomes", type=int,
                        default=40)
    parser.add_argument("--minimum-observed-each-outcome", type=int,
                        default=8)
    parser.add_argument("--minimum-multi-candidate-sets", type=int,
                        default=10)
    parser.add_argument("--minimum-mixed-operation-type-sets", type=int,
                        default=8)
    parser.add_argument("--minimum-selected-each-operation-type", type=int,
                        default=5)
    parser.add_argument("--minimum-selected-operation-type-lineages", type=int,
                        default=5)
    parser.add_argument("--minimum-observed-operation-type-lineages", type=int,
                        default=5)
    parser.add_argument("--minimum-actor-context-signatures", type=int,
                        default=8)
    parser.add_argument("--minimum-prediction-coverage", type=float,
                        default=0.95)
    parser.add_argument("--maximum-brier-score", type=float, default=0.25)
    parser.add_argument("--maximum-log-loss", type=float, default=0.75)
    parser.add_argument("--maximum-calibration-error", type=float,
                        default=0.15)
    parser.add_argument("--maximum-action-calibration-error", type=float,
                        default=0.25)
    parser.add_argument(
        "--minimum-lifecycle-brier-improvement-ci-lower", type=float,
        default=-0.05)
    args = parser.parse_args(argv)
    yield_thresholds = {
        "actor_context_signatures": args.minimum_actor_context_signatures,
        "mixed_operation_type_choice_sets": (
            args.minimum_mixed_operation_type_sets),
        "multi_candidate_choice_sets": args.minimum_multi_candidate_sets,
        "observed_each_outcome": args.minimum_observed_each_outcome,
        "observed_operation_type_lineages": (
            args.minimum_observed_operation_type_lineages),
        "observed_selected_outcomes": (
            args.minimum_observed_selected_outcomes),
        "selected_each_operation_type": (
            args.minimum_selected_each_operation_type),
        "selected_operation_type_lineages": (
            args.minimum_selected_operation_type_lineages),
    }
    validation_thresholds = {
        "maximum_action_calibration_error": (
            args.maximum_action_calibration_error),
        "maximum_brier_score": args.maximum_brier_score,
        "maximum_calibration_error": args.maximum_calibration_error,
        "maximum_log_loss": args.maximum_log_loss,
        "minimum_lifecycle_brier_improvement_ci_lower": (
            args.minimum_lifecycle_brier_improvement_ci_lower),
        "minimum_prediction_coverage": args.minimum_prediction_coverage,
    }
    report, source_audit = validation_report(
        args.run_root, args.model, args.confirmation_id,
        tuple(args.expected_seed), args.expected_model_hash,
        yield_thresholds, validation_thresholds,
        args.bootstrap_samples, args.bootstrap_seed)
    for path, value in (
            (args.output, report), (args.yield_output, source_audit)):
        output = os.path.abspath(path)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "wb") as stream:
            stream.write(canonical_json_bytes(value) + b"\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
