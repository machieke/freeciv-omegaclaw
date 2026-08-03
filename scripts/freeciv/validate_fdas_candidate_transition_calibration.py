#!/usr/bin/env python3
"""Validate grounded move-transition calibration on disjoint games."""

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

from audit_fdas_candidate_transition_features import (  # noqa: E402
    audit as audit_features,
)
from fit_fdas_candidate_transition_calibration import (  # noqa: E402
    DEFAULT_DISCOVERY_THRESHOLDS,
    _discovery_yield,
)
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import (  # noqa: E402
    DEFAULT_TRANSITION_VALIDATION_THRESHOLDS,
    DEFENSE_CANDIDATE_CHOICE_SURFACE,
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    FdasCandidateChoiceSetStore,
    evaluate_candidate_transition_calibration,
    export_candidate_choice_calibration,
    load_candidate_transition_calibration_model,
)


def _choice_paths(run_root):
    return tuple(sorted(glob.glob(os.path.join(
        os.path.abspath(run_root), "games", "main", "e_full_loop", "*-*",
        "fdas-candidate-choice-sets.json"))))


def _load_store(path):
    with open(path, encoding="utf-8") as stream:
        raw = json.load(stream)
    return FdasCandidateChoiceSetStore.load(
        path, raw["persistence_identity"])


def confirmation_report(
        run_root, model_path, confirmation_id, expected_seeds,
        expected_source_commit, yield_thresholds=None,
        validation_thresholds=None, bootstrap_samples=2000,
        bootstrap_seed=16061, feature_auditor=None,
        report_schema_version=(
            "fdas-candidate-transition-calibration-confirmation/1.0")):
    seeds = tuple(int(value) for value in expected_seeds)
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("transition confirmation requires unique seeds")
    if feature_auditor is None:
        feature_auditor = audit_features
    if not callable(feature_auditor):
        raise TypeError("transition confirmation feature auditor is invalid")
    if not isinstance(report_schema_version, str) or not report_schema_version:
        raise ValueError("transition confirmation report schema is required")
    feature_report = feature_auditor(
        run_root,
        os.path.join(
            REPO, "docs", "freeciv", "evidence",
            "fdas-pr40-candidate-calibration-discovery.json"),
        seeds, expected_source_commit=expected_source_commit)
    paths = _choice_paths(run_root)
    if len(paths) != len(seeds):
        raise ValueError("transition confirmation store count differs")
    stores = tuple(_load_store(path) for path in paths)
    if any(value.quarantined for value in stores):
        raise ValueError("transition confirmation store is quarantined")
    exports = tuple(export_candidate_choice_calibration(
        store, DEFENSE_CANDIDATE_CHOICE_SURFACE,
        DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET) for store in stores)
    yield_thresholds = dict(
        DEFAULT_DISCOVERY_THRESHOLDS
        if yield_thresholds is None else yield_thresholds)
    yield_report = _discovery_yield(
        exports, feature_report, yield_thresholds)
    model, calibration_artifact_hash = (
        load_candidate_transition_calibration_model(model_path))
    validation = evaluate_candidate_transition_calibration(
        model, exports, confirmation_id,
        thresholds=validation_thresholds,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed)
    passed = bool(
        feature_report["passed"]
        and yield_report["passed"]
        and validation["passed"])
    semantic = {
        "calibration_artifact_hash": calibration_artifact_hash,
        "claim_scope": validation["claim_scope"],
        "confirmation_id": confirmation_id,
        "feature_audit_hash": feature_report["report_hash"],
        "model_result_hash": model.result_hash,
        "passed": passed,
        "policy_authority": False,
        "readout_authority": False,
        "schema_version": report_schema_version,
        "source_store_paths": [
            os.path.relpath(path, REPO).replace(os.sep, "/")
            for path in paths],
        "truth_mutated": False,
        "validation": validation,
        "yield": yield_report,
    }
    semantic["report_hash"] = structural_hash(semantic)
    return semantic


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--confirmation-id", required=True)
    parser.add_argument("--expected-seed", action="append", type=int,
                        required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=16061)
    for name, value in sorted(DEFAULT_DISCOVERY_THRESHOLDS.items()):
        parser.add_argument(
            "--minimum-yield-" + name.replace("_", "-"),
            dest="yield_" + name, type=int, default=value)
    for name, value in sorted(
            DEFAULT_TRANSITION_VALIDATION_THRESHOLDS.items()):
        prefix = "--" + name.replace("_", "-")
        value_type = int if name in (
            "minimum_distinct_prediction_values",
            "minimum_heldout_lineages") else float
        parser.add_argument(prefix, dest=name, type=value_type, default=value)
    args = parser.parse_args(argv)
    yield_thresholds = {
        name: getattr(args, "yield_" + name)
        for name in DEFAULT_DISCOVERY_THRESHOLDS}
    validation_thresholds = {
        name: getattr(args, name)
        for name in DEFAULT_TRANSITION_VALIDATION_THRESHOLDS}
    report = confirmation_report(
        args.run_root, args.model, args.confirmation_id,
        tuple(args.expected_seed), args.expected_source_commit,
        yield_thresholds=yield_thresholds,
        validation_thresholds=validation_thresholds,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "wb") as stream:
        stream.write(canonical_json_bytes(report) + b"\n")
    print(json.dumps({
        "output": output,
        "passed": report["passed"],
        "report_hash": report["report_hash"],
        "validation": report["validation"],
        "yield": report["yield"],
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
