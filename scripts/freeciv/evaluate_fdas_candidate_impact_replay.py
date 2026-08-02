#!/usr/bin/env python3
"""Evaluate approved FDAS rule decision impact on frozen snapshots."""

import argparse
from collections import Counter
import hashlib
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
for location in (
        os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks"),
        SCRIPT_DIR):
    if location not in sys.path:
        sys.path.insert(0, location)

import run_fdas_captured_replay as captured_replay  # noqa: E402
from freeciv.harness.runner import _source_identity  # noqa: E402
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    CAUSAL_INDUCTION_FEATURE_SCHEMA,
    DURABLE_ACTOR_CITY_DEFENSE_TARGET,
    DecisionEpisodeStore,
    FdasDefenseEpisodeRecorder,
    FdasPromotedRuleCandidateImpactShadow,
)
from freeciv_agent.pressure import (  # noqa: E402
    PromotedRuleCandidateImpactAnalyzer,
    load_promoted_rule_shadow_artifacts,
)
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    build_runtime,
    load_runtime_declaration,
)


DEFAULT_CONFIG = os.path.join(
    REPO, "profile",
    "dependent_atomspace_defense_actor_persistence_causal_induction_shadow.yaml")
DEFAULT_MANIFEST = os.path.join(
    REPO, "profile",
    "fdas_manifest_defense_actor_persistence_candidate_impact_shadow.json")
DEFAULT_APPROVED = os.path.join(
    REPO, "docs", "freeciv", "evidence",
    "fdas-pr29-causal-induction-holdout-engine.json")
DEFAULT_CONSOLIDATION = os.path.join(
    REPO, "docs", "freeciv", "evidence",
    "fdas-pr30-promoted-rule-consolidation.json")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _logical(path):
    absolute = os.path.abspath(path)
    relative = os.path.relpath(absolute, REPO)
    if relative != os.pardir and not relative.startswith(os.pardir + os.sep):
        return relative.replace(os.sep, "/")
    return absolute


def _write(path, value):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    temporary = os.path.abspath(path) + ".tmp.{}".format(os.getpid())
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, os.path.abspath(path))


def _run_once(snapshots, declaration, ruleset_ir, bundle):
    episode_store = DecisionEpisodeStore("fdas-candidate-impact-replay")
    runtime = build_runtime(
        declaration,
        ruleset_ir=ruleset_ir,
        operation_records_source=lambda: (),
        episode_source=episode_store)
    evaluator = FdasPromotedRuleCandidateImpactShadow(
        FdasDefenseEpisodeRecorder(
            episode_store,
            induction_feature_schema=CAUSAL_INDUCTION_FEATURE_SCHEMA),
        PromotedRuleCandidateImpactAnalyzer(
            bundle.readout, runtime.shadow_pressure_config),
        DURABLE_ACTOR_CITY_DEFENSE_TARGET)
    rows = []
    failures = []
    for path, snapshot, legacy_candidates in snapshots:
        try:
            runtime.replace(snapshot)
            shadow = runtime.evaluate_shadow(snapshot, legacy_candidates)
            evaluation = evaluator.evaluate(
                snapshot,
                shadow.candidates,
                runtime.shadow_operation_scores(shadow),
                shadow.pressure.schedule.get("selected_operation_id"))
            rows.append({
                "evaluation": evaluation.to_dict(),
                "path": path,
                "revision_id": shadow.revision_id,
                "snapshot_id": snapshot.snapshot_id,
                "turn": snapshot.turn,
            })
        except Exception as error:
            failures.append({
                "diagnostic": str(error),
                "error_type": type(error).__name__,
                "path": path,
                "snapshot_id": snapshot.snapshot_id,
            })
    return tuple(rows), tuple(failures)


def run(arguments):
    patterns = arguments.capture_manifests or (
        captured_replay.DEFAULT_CAPTURE_GLOB,)
    manifests, fixtures, snapshots, gaps, corpus_failures = (
        captured_replay._load_corpus(patterns))
    declaration = load_runtime_declaration(
        arguments.config, arguments.manifest)
    diagnostic = declaration["manifest"].get(
        "induced_rule_candidate_impact_diagnostic", {})
    bundle = load_promoted_rule_shadow_artifacts(
        arguments.approved_report, arguments.consolidation_report)
    bundle_value = bundle.to_dict()
    ruleset_ir = compile_ruleset(arguments.ruleset_root, arguments.ruleset)
    first, first_failures = _run_once(
        snapshots, declaration, ruleset_ir, bundle)
    second, second_failures = _run_once(
        snapshots, declaration, ruleset_ir, bundle)
    failures = tuple(corpus_failures) + first_failures + second_failures
    evaluations = tuple(row["evaluation"] for row in first)
    impacts = tuple(
        value["impact"] for value in evaluations
        if value["impact"] is not None)
    candidate_rows = tuple(
        row for impact in impacts for row in impact["rows"])
    reasons = Counter(value["reason"] for value in evaluations)
    readout_reasons = Counter(
        row["prediction"]["reason"]
        for row in candidate_rows if row["prediction"] is not None)
    source = dict(
        _source_identity(),
        runner_path=_logical(__file__),
        runner_sha256=_sha256(__file__))
    artifact_binding = all(
        diagnostic.get(name) == bundle_value[name]
        for name in (
            "approved_report_sha256",
            "approved_report_structural_hash",
            "consolidation_report_sha256",
            "consolidation_report_structural_hash"))
    checks = {
        "accepted_artifacts_match_manifest": artifact_binding,
        "candidate_impact_is_shadow_live": (
            declaration["manifest"]["capabilities"].get(
                "induced_rule_candidate_impact_shadow") == "shadow-live"),
        "candidate_population_is_nonempty": bool(candidate_rows),
        "deterministic_repeated_readout": first == second,
        "execution_source_requirement_met": (
            not arguments.require_clean_source
            or source.get("dirty") is False),
        "multiple_candidate_contexts_are_observed": any(
            value["scoped_candidate_count"] > 1 for value in evaluations),
        "no_replay_failures": not failures,
        "no_truth_readout_policy_or_action_authority": all(
            value["truth_mutated"] is False
            and value["policy_authority"] is False
            and value["readout_authority"] is False
            and value["action_selection_changed"] is False
            and (value["impact"] is None
                 or value["impact"]["truth_mutated"] is False
                 and value["impact"]["policy_authority"] is False
                 and value["impact"]["readout_authority"] is False
                 and value["impact"]["action_selection_changed"] is False)
            for value in evaluations),
        "positive_complete_prediction_coverage": any(
            value["complete_prediction_coverage"] for value in impacts),
        "replay_population_is_nonempty": bool(first),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "artifacts": bundle_value,
        "claim_scope": (
            "frozen-snapshot, category-scoped, non-authorizing candidate "
            "impact replay of held-out-approved promoted rules; reports "
            "counterfactual priority and rank diagnostics only, with no "
            "truth, readout, policy, action, gameplay, score, or win-rate "
            "claim"),
        "config": {
            "declaration_hash": declaration["declaration_hash"],
            "manifest_path": _logical(arguments.manifest),
            "profile_path": _logical(arguments.config),
        },
        "corpus": {
            "data_gaps": list(gaps),
            "manifests": manifests,
            "replayable_fixture_count": len(snapshots),
            "unique_fixture_count": len(fixtures),
        },
        "failures": list(failures),
        "readouts": list(first),
        "ruleset": arguments.ruleset,
        "schema_version": "1.0",
        "source": source,
        "summary": {
            "candidate_rows": len(candidate_rows),
            "complete_prediction_coverage_count": sum(
                value["complete_prediction_coverage"] for value in impacts),
            "contextual_priority_delta_count": sum(
                abs(float(row["priority_delta"])) > 1e-12
                for row in candidate_rows),
            "counterfactual_winner_change_count": sum(
                value["counterfactual_winner_changed"] is True
                for value in impacts),
            "evaluated_count": sum(
                value["status"] == "evaluated" for value in evaluations),
            "evaluation_reason_counts": dict(sorted(reasons.items())),
            "multi_candidate_evaluation_count": sum(
                value["scoped_candidate_count"] > 1
                for value in evaluations),
            "readout_reason_counts": dict(sorted(readout_reasons.items())),
            "replay_count": len(first),
        },
    }
    report["structural_hash"] = structural_hash(report)
    if arguments.output:
        _write(arguments.output, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--approved-report", default=DEFAULT_APPROVED)
    parser.add_argument(
        "--consolidation-report", default=DEFAULT_CONSOLIDATION)
    parser.add_argument(
        "--capture-manifest", action="append", dest="capture_manifests")
    parser.add_argument("--ruleset-root", default=os.environ.get(
        "FREECIV_RULESET_ROOT"))
    parser.add_argument("--ruleset", default="civ2civ3")
    parser.add_argument("--output")
    parser.add_argument("--require-clean-source", action="store_true")
    args = parser.parse_args(argv)
    if not args.ruleset_root:
        parser.error("--ruleset-root or FREECIV_RULESET_ROOT is required")
    report = run(args)
    print(json.dumps({
        "accepted": report["acceptance"]["accepted"],
        "counterfactual_winner_change_count": report["summary"][
            "counterfactual_winner_change_count"],
        "replay_count": report["summary"]["replay_count"],
        "structural_hash": report["structural_hash"],
    }, sort_keys=True))
    return 0 if report["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
