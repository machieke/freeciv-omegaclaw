#!/usr/bin/env python3
"""Fit non-authorizing grounded move-transition calibration."""

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
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import (  # noqa: E402
    CANDIDATE_TRANSITION_FEATURE_SCHEMA,
    CANDIDATE_TRANSITION_OPERATION_TYPE,
    DEFENSE_CANDIDATE_CHOICE_SURFACE,
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    FdasCandidateChoiceSetStore,
    export_candidate_choice_calibration,
    fit_candidate_transition_calibration,
)


DEFAULT_DISCOVERY_THRESHOLDS = {
    "diverse_multi_move_choice_sets": 12,
    "games_with_observed_move": 6,
    "negative_move_outcomes": 8,
    "observed_move_lineages": 8,
    "observed_move_outcomes": 12,
    "positive_move_outcomes": 3,
    "selected_transition_signatures": 6,
}
FEATURE_PREFIX = "candidate-transition:"


def _choice_paths(run_root):
    return tuple(sorted(glob.glob(os.path.join(
        os.path.abspath(run_root), "games", "main", "e_full_loop", "*-*",
        "fdas-candidate-choice-sets.json"))))


def _load_store(path):
    with open(path, encoding="utf-8") as stream:
        raw = json.load(stream)
    return FdasCandidateChoiceSetStore.load(
        path, raw["persistence_identity"])


def _single_prefixed(values, prefix, name):
    matches = tuple(
        value[len(prefix):] for value in values if value.startswith(prefix))
    if len(matches) != 1 or not matches[0]:
        raise ValueError("transition discovery requires exact {}".format(name))
    return matches[0]


def _discovery_yield(exports, feature_report, thresholds):
    rows = []
    for export in exports:
        for episode in export.examples:
            context = dict(episode.context)
            if context.get("operation_type") != (
                    CANDIDATE_TRANSITION_OPERATION_TYPE):
                continue
            if context.get("candidate_transition_feature_schema") != (
                    CANDIDATE_TRANSITION_FEATURE_SCHEMA):
                raise ValueError("transition discovery feature schema differs")
            transition = tuple(sorted(
                value for value in episode.features
                if value.startswith(FEATURE_PREFIX)))
            if not transition or (
                    FEATURE_PREFIX + "transition_grounding_status=complete"
                    not in transition):
                raise ValueError("transition discovery grounding is incomplete")
            rows.append({
                "game_id": _single_prefixed(
                    episode.provenance_ids, "game-id:", "game identity"),
                "lineage_id": _single_prefixed(
                    episode.provenance_ids, "candidate-lineage:",
                    "candidate lineage"),
                "outcome": bool(episode.outcome),
                "signature": transition,
            })
    measures = {
        "diverse_multi_move_choice_sets": feature_report["totals"][
            "diverse_multi_move_choice_sets"],
        "games_with_observed_move": len({value["game_id"] for value in rows}),
        "negative_move_outcomes": sum(not value["outcome"] for value in rows),
        "observed_move_lineages": len({value["lineage_id"] for value in rows}),
        "observed_move_outcomes": len(rows),
        "positive_move_outcomes": sum(value["outcome"] for value in rows),
        "selected_transition_signatures": len({
            value["signature"] for value in rows}),
    }
    gates = {
        name + "_sufficient": measures[name] >= thresholds[name]
        for name in sorted(thresholds)}
    return {
        "gates": gates,
        "measures": measures,
        "passed": all(gates.values()),
        "thresholds": thresholds,
    }


def fit_report(run_root, discovery_id, model_id, expected_seeds,
               expected_source_commit, model_prior_strength=4.0,
               discovery_thresholds=None):
    seeds = tuple(int(value) for value in expected_seeds)
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("transition discovery requires unique seeds")
    thresholds = dict(
        DEFAULT_DISCOVERY_THRESHOLDS
        if discovery_thresholds is None else discovery_thresholds)
    if set(thresholds) != set(DEFAULT_DISCOVERY_THRESHOLDS):
        raise ValueError("transition discovery thresholds are incomplete")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1
           for value in thresholds.values()):
        raise ValueError("transition discovery thresholds must be positive")
    feature_report = audit_features(
        run_root,
        os.path.join(
            REPO, "docs", "freeciv", "evidence",
            "fdas-pr40-candidate-calibration-discovery.json"),
        seeds, expected_source_commit=expected_source_commit)
    if not feature_report["passed"]:
        raise ValueError("transition discovery feature audit failed")
    paths = _choice_paths(run_root)
    if len(paths) != len(seeds):
        raise ValueError("transition discovery store count differs")
    stores = tuple(_load_store(path) for path in paths)
    if any(value.quarantined for value in stores):
        raise ValueError("transition discovery store is quarantined")
    exports = tuple(export_candidate_choice_calibration(
        store, DEFENSE_CANDIDATE_CHOICE_SURFACE,
        DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET) for store in stores)
    yield_report = _discovery_yield(exports, feature_report, thresholds)
    if not yield_report["passed"]:
        raise ValueError("transition discovery progression gate failed")
    model = fit_candidate_transition_calibration(
        exports, model_id, prior_strength=model_prior_strength)
    semantic = {
        "calibration_model": model.to_dict(),
        "claim_scope": (
            "in-sample selected-only hierarchical move-transition "
            "calibration; no censored counterfactual, ranking, policy, "
            "readout, gameplay, score, or win-rate claim"),
        "discovery_id": discovery_id,
        "feature_audit_hash": feature_report["report_hash"],
        "policy_authority": False,
        "readout_authority": False,
        "schema_version": "fdas-candidate-transition-calibration-fit/1.0",
        "source_store_paths": [
            os.path.relpath(path, REPO).replace(os.sep, "/")
            for path in paths],
        "truth_mutated": False,
        "yield": yield_report,
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
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--model-prior-strength", type=float, default=4.0)
    for name, value in sorted(DEFAULT_DISCOVERY_THRESHOLDS.items()):
        parser.add_argument(
            "--minimum-" + name.replace("_", "-"),
            dest=name, type=int, default=value)
    args = parser.parse_args(argv)
    thresholds = {
        name: getattr(args, name) for name in DEFAULT_DISCOVERY_THRESHOLDS}
    report = fit_report(
        args.run_root, args.discovery_id, args.model_id,
        tuple(args.expected_seed), args.expected_source_commit,
        model_prior_strength=args.model_prior_strength,
        discovery_thresholds=thresholds)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "wb") as stream:
        stream.write(canonical_json_bytes(report) + b"\n")
    print(json.dumps({
        "model_result_hash": report["calibration_model"]["result_hash"],
        "output": output,
        "report_hash": report["report_hash"],
        "yield": report["yield"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
