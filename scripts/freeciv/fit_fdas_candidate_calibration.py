#!/usr/bin/env python3
"""Fit a non-authorizing FDAS action/lifecycle calibration artifact."""

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
    export_candidate_choice_calibration,
    fit_candidate_calibration,
)


DEFAULT_THRESHOLDS = {
    "actor_context_signatures": 10,
    "mixed_operation_type_choice_sets": 10,
    "multi_candidate_choice_sets": 12,
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


def fit_report(run_root, discovery_id, model_id, expected_seeds,
               thresholds=None, minimum_action_lineages=5,
               minimum_lifecycle_lineages=3):
    """Validate a frozen discovery cohort and fit its selected-only model."""
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if not expected_seeds or len(expected_seeds) != len(set(expected_seeds)):
        raise ValueError("calibration fit requires unique expected seeds")
    thresholds = dict(DEFAULT_THRESHOLDS if thresholds is None else thresholds)
    yield_report = audit_yield(
        run_root, expected_seeds=expected_seeds, pilot_id=discovery_id,
        require_surface_strata=True, progression_thresholds=thresholds)
    if not yield_report["mechanically_accepted"]:
        raise ValueError("calibration discovery mechanical gate failed")
    if not yield_report["progression_gate_passed"]:
        raise ValueError("calibration discovery progression gate failed")
    paths = _choice_paths(run_root)
    if len(paths) != len(expected_seeds):
        raise ValueError("calibration discovery store count differs")
    stores = tuple(_load_store(path) for path in paths)
    if any(value.quarantined for value in stores):
        raise ValueError("calibration discovery store is quarantined")
    exports = tuple(export_candidate_choice_calibration(
        store, DEFENSE_CANDIDATE_CHOICE_SURFACE,
        DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET) for store in stores)
    model = fit_candidate_calibration(
        exports, model_id,
        minimum_action_lineages=minimum_action_lineages,
        minimum_lifecycle_lineages=minimum_lifecycle_lineages)
    semantic = {
        "calibration_model": model.to_dict(),
        "claim_scope": (
            "in-sample selected-only descriptive calibration artifact; "
            "no counterfactual, ranking, policy, readout, gameplay, score, "
            "or win-rate claim"),
        "discovery_id": discovery_id,
        "policy_authority": False,
        "readout_authority": False,
        "schema_version": "fdas-candidate-calibration-fit/1.0",
        "source_store_paths": [
            os.path.relpath(path, REPO).replace(os.sep, "/")
            for path in paths],
        "truth_mutated": False,
        "yield_report_hash": yield_report["report_hash"],
    }
    semantic["report_hash"] = structural_hash(semantic)
    return semantic


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("--output", required=True)
    parser.add_argument("--discovery-id", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--expected-seed", action="append", type=int,
                        required=True)
    parser.add_argument("--minimum-action-lineages", type=int, default=5)
    parser.add_argument("--minimum-lifecycle-lineages", type=int, default=3)
    parser.add_argument("--minimum-actor-context-signatures", type=int,
                        default=DEFAULT_THRESHOLDS[
                            "actor_context_signatures"])
    parser.add_argument("--minimum-mixed-operation-type-sets", type=int,
                        default=DEFAULT_THRESHOLDS[
                            "mixed_operation_type_choice_sets"])
    parser.add_argument("--minimum-multi-candidate-sets", type=int,
                        default=DEFAULT_THRESHOLDS[
                            "multi_candidate_choice_sets"])
    parser.add_argument("--minimum-observed-each-outcome", type=int,
                        default=DEFAULT_THRESHOLDS[
                            "observed_each_outcome"])
    parser.add_argument("--minimum-observed-operation-type-lineages", type=int,
                        default=DEFAULT_THRESHOLDS[
                            "observed_operation_type_lineages"])
    parser.add_argument("--minimum-observed-selected-outcomes", type=int,
                        default=DEFAULT_THRESHOLDS[
                            "observed_selected_outcomes"])
    parser.add_argument("--minimum-selected-each-operation-type", type=int,
                        default=DEFAULT_THRESHOLDS[
                            "selected_each_operation_type"])
    parser.add_argument("--minimum-selected-operation-type-lineages", type=int,
                        default=DEFAULT_THRESHOLDS[
                            "selected_operation_type_lineages"])
    args = parser.parse_args(argv)
    thresholds = {
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
    report = fit_report(
        args.run_root, args.discovery_id, args.model_id,
        tuple(args.expected_seed), thresholds,
        args.minimum_action_lineages, args.minimum_lifecycle_lineages)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "wb") as stream:
        stream.write(canonical_json_bytes(report) + b"\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
