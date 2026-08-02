#!/usr/bin/env python3
"""Replay frozen state events through the checked rich FDAS shadow runtime."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import glob
import json
import os
import statistics
import sys
import time


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.planning import ImpactCandidate  # noqa: E402
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.state import (  # noqa: E402
    SnapshotReplayError,
    snapshot_from_event,
)
from freeciv_agent.state.atomspace import (  # noqa: E402
    build_runtime,
    load_runtime_declaration,
)


DEFAULT_CAPTURE_GLOB = os.path.join(
    REPO, "benchmarks", "gdo", "captured_snapshots", "*_manifest.json")
DEFAULT_CONFIG = os.path.join(REPO, "profile", "dependent_atomspace_shadow.yaml")


def _legacy_candidates(captured):
    """Rebuild only the immutable comparison contract from frozen evidence."""
    result = []
    for row in captured.get("candidates", ()):
        if not isinstance(row, dict):
            raise ValueError("captured candidate must be an object")
        result.append(ImpactCandidate(
            dict(row["action"]), str(row["category"]),
            float(row["utility"]), str(row["rationale"]),
            None if row.get("projection") is None
            else dict(row["projection"])))
    return tuple(result)


def _percentile(values, fraction):
    values = sorted(float(value) for value in values)
    if not values:
        return None
    index = min(
        len(values) - 1,
        max(0, int(round((len(values) - 1) * fraction))))
    return values[index]


def _summary(values):
    values = tuple(float(value) for value in values)
    if not values:
        return {
            "count": 0,
            "maximum_ms": None,
            "mean_ms": None,
            "minimum_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
        }
    return {
        "count": len(values),
        "maximum_ms": max(values),
        "mean_ms": statistics.mean(values),
        "minimum_ms": min(values),
        "p50_ms": _percentile(values, 0.50),
        "p95_ms": _percentile(values, 0.95),
        "p99_ms": _percentile(values, 0.99),
    }


def _ratio_summary(values):
    values = tuple(float(value) for value in values)
    if not values:
        return {
            "count": 0, "maximum": None, "mean": None, "minimum": None,
            "p50": None, "p95": None, "p99": None,
        }
    return {
        "count": len(values),
        "maximum": max(values),
        "mean": statistics.mean(values),
        "minimum": min(values),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
    }


def _load_corpus(patterns):
    manifest_paths = sorted(set(
        path for pattern in patterns for path in glob.glob(pattern)))
    fixtures = {}
    manifest_rows = []
    failures = []
    for manifest_path in manifest_paths:
        with open(manifest_path, encoding="utf-8") as stream:
            manifest = json.load(stream)
        rows = tuple(manifest.get("fixtures", ()))
        manifest_rows.append({
            "fixture_count": len(rows),
            "manifest_hash": structural_hash(manifest),
            "path": os.path.relpath(manifest_path, REPO),
        })
        for row in rows:
            relative = str(row["path"])
            expected = str(row["fixture_sha256"])
            existing = fixtures.get(relative)
            if existing is not None and existing != expected:
                failures.append({
                    "diagnostic": "fixture hash differs across manifests",
                    "path": relative,
                })
            fixtures[relative] = expected

    snapshots = []
    gaps = []
    for relative, expected in sorted(fixtures.items()):
        path = relative if os.path.isabs(relative) else os.path.join(REPO, relative)
        try:
            with open(path, encoding="utf-8") as stream:
                captured = json.load(stream)
            observed = structural_hash(captured)
            if observed != expected:
                raise ValueError(
                    "fixture hash mismatch: expected {}, observed {}".format(
                        expected, observed))
            snapshot = snapshot_from_event(captured["snapshot_event"])
            snapshots.append((relative, snapshot, _legacy_candidates(captured)))
        except SnapshotReplayError as error:
            gaps.append({
                "diagnostic": str(error),
                "path": relative,
            })
        except (KeyError, OSError, TypeError, ValueError) as error:
            failures.append({
                "diagnostic": str(error),
                "path": relative,
            })
    snapshots.sort(key=lambda row: (
        row[1].turn, row[1].identity.source_seq, row[0]))
    return manifest_rows, fixtures, snapshots, gaps, failures


def _revision_counts(runtime, snapshot):
    revision = runtime.snapshot_store.current_dependent_revision(
        snapshot.identity.game_id, snapshot.player_id)
    predicates = Counter(
        record.key.predicate for record in revision.records)
    namespaces = Counter(
        record.key.namespace.value for record in revision.records)
    support_ids = set()
    dependency_keys = set()
    for record in revision.records:
        for support in record.supports:
            support_ids.add(support.support_id)
            dependency_keys.update(
                dependency.key for dependency in support.dependencies)
    return {
        "atom_count": len(revision.records),
        "dependency_key_count": len(dependency_keys),
        "namespace_counts": dict(sorted(namespaces.items())),
        "predicate_counts": dict(sorted(predicates.items())),
        "scope_count": len(revision.scopes),
        "support_count": len(support_ids),
    }


def _cold_replay(snapshots, declaration, ruleset_ir):
    samples = []
    failures = []
    for relative, snapshot, legacy_candidates in snapshots:
        runtime = build_runtime(
            declaration,
            ruleset_ir=ruleset_ir,
            operation_records_source=lambda: ())
        started = time.perf_counter()
        try:
            update = runtime.replace(snapshot)
            elapsed = (time.perf_counter() - started) * 1000.0
            evaluation = runtime.evaluate_shadow(snapshot, legacy_candidates)
            sample = {
                "fdas_total_latency_ms": elapsed + evaluation.latency_ms,
                "latency_ms": elapsed,
                "materialization_metrics": (
                    None if update.materialization_metrics is None
                    else update.materialization_metrics.to_dict()),
                "path": relative,
                "revision_id": update.revision_id,
                "snapshot_id": snapshot.snapshot_id,
                "source_seq": snapshot.identity.source_seq,
                "shadow_evaluation": {
                    "authority_eligible_count": sum(
                        candidate.authority_eligible
                        for candidate in evaluation.candidates),
                    "candidate_count": len(evaluation.candidates),
                    "candidate_instantiation": (
                        evaluation.candidate_instantiation.to_dict()),
                    "comparison": evaluation.comparison.to_dict(),
                    "evaluation_hash": evaluation.pressure.evaluation_hash,
                    "goal_count": len(evaluation.goals),
                    "latency_ms": evaluation.latency_ms,
                    "pressure_reason": evaluation.pressure.reason,
                    "pressure_status": evaluation.pressure.status,
                    "selected_operation_id": evaluation.pressure.schedule.get(
                        "selected_operation_id"),
                },
                "turn": snapshot.turn,
            }
            sample.update(_revision_counts(runtime, snapshot))
            samples.append(sample)
        except Exception as error:  # fail-closed evidence must retain all cases
            failures.append({
                "diagnostic": str(error),
                "error_type": type(error).__name__,
                "path": relative,
                "snapshot_id": snapshot.snapshot_id,
            })
    return samples, failures


def _incremental_replay(snapshots, declaration, ruleset_ir):
    samples = []
    failures = []
    runtime = build_runtime(
        declaration,
        ruleset_ir=ruleset_ir,
        operation_records_source=lambda: ())
    for relative, snapshot, legacy_candidates in snapshots:
        started = time.perf_counter()
        try:
            update = runtime.replace(snapshot)
            elapsed = (time.perf_counter() - started) * 1000.0
            evaluation = runtime.evaluate_shadow(snapshot, legacy_candidates)
            samples.append({
                "cold_verification": (
                    None if update.cold_verification is None
                    else update.cold_verification.to_dict()),
                "fdas_total_latency_ms": elapsed + evaluation.latency_ms,
                "latency_ms": elapsed,
                "materialization_metrics": (
                    None if update.materialization_metrics is None
                    else update.materialization_metrics.to_dict()),
                "path": relative,
                "revision_id": update.revision_id,
                "shadow_evaluation": {
                    "authority_eligible_count": sum(
                        candidate.authority_eligible
                        for candidate in evaluation.candidates),
                    "candidate_count": len(evaluation.candidates),
                    "candidate_instantiation": (
                        evaluation.candidate_instantiation.to_dict()),
                    "comparison": evaluation.comparison.to_dict(),
                    "evaluation_hash": evaluation.pressure.evaluation_hash,
                    "goal_count": len(evaluation.goals),
                    "latency_ms": evaluation.latency_ms,
                    "pressure_reason": evaluation.pressure.reason,
                    "pressure_status": evaluation.pressure.status,
                    "selected_operation_id": evaluation.pressure.schedule.get(
                        "selected_operation_id"),
                },
                "snapshot_id": snapshot.snapshot_id,
                "source_seq": snapshot.identity.source_seq,
                "turn": snapshot.turn,
            })
        except Exception as error:  # preserve the first transition failure
            failures.append({
                "diagnostic": str(error),
                "error_type": type(error).__name__,
                "path": relative,
                "snapshot_id": snapshot.snapshot_id,
            })
            break
    return samples, failures


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--capture-manifest", action="append", dest="capture_manifests",
        help="manifest path or glob; repeatable")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", default=None)
    parser.add_argument(
        "--mode", choices=("all", "cold", "incremental"), default="all")
    parser.add_argument("--output")
    parser.add_argument(
        "--require-complete-capture", action="store_true",
        help="treat intentionally reported old-capture gaps as failures")
    parser.add_argument(
        "--ruleset-root", default=os.environ.get("FREECIV_RULESET_ROOT"))
    parser.add_argument("--ruleset", default="civ2civ3")
    args = parser.parse_args(argv)
    if not args.ruleset_root:
        parser.error("--ruleset-root or FREECIV_RULESET_ROOT is required")

    patterns = args.capture_manifests or (DEFAULT_CAPTURE_GLOB,)
    manifests, fixtures, snapshots, gaps, corpus_failures = _load_corpus(
        patterns)
    declaration = load_runtime_declaration(args.config, args.manifest)
    ruleset_ir = compile_ruleset(args.ruleset_root, args.ruleset)
    cold_samples, cold_failures = ([], [])
    incremental_samples, incremental_failures = ([], [])
    if args.mode in ("all", "cold"):
        cold_samples, cold_failures = _cold_replay(
            snapshots, declaration, ruleset_ir)
    if args.mode in ("all", "incremental"):
        incremental_samples, incremental_failures = _incremental_replay(
            snapshots, declaration, ruleset_ir)

    verifications = tuple(
        row["cold_verification"] for row in incremental_samples
        if row["cold_verification"] is not None)
    failures = tuple(
        corpus_failures + cold_failures + incremental_failures)

    def shadow_summary(samples):
        comparisons = tuple(
            row["shadow_evaluation"]["comparison"] for row in samples)
        return {
            "authority_eligible_count": sum(
                row["shadow_evaluation"]["authority_eligible_count"]
                for row in samples),
            "authority_violation_count": sum(
                len(row["authority_violations"]) for row in comparisons),
            "candidate_count": sum(
                row["shadow_evaluation"]["candidate_count"]
                for row in samples),
            "extra_fdas_count": sum(
                len(row["extra_fdas"]) for row in comparisons),
            "goal_count": sum(
                row["shadow_evaluation"]["goal_count"]
                for row in samples),
            "latency": _summary(
                row["shadow_evaluation"]["latency_ms"]
                for row in samples),
            "legacy_candidate_count": sum(
                row["legacy_candidate_count"] for row in comparisons),
            "legal_binding_failure_count": sum(
                len(row["legal_binding_failures"])
                for row in comparisons),
            "missing_legacy_count": sum(
                len(row["missing_legacy"]) for row in comparisons),
            "omitted_unprotected_candidate_count": sum(
                row["shadow_evaluation"]["candidate_instantiation"][
                    "omitted_unprotected_count"]
                for row in samples),
            "overlap_count": sum(
                len(row["overlapping_action_keys"])
                for row in comparisons),
            "pressure_status_counts": dict(sorted(Counter(
                row["shadow_evaluation"]["pressure_status"]
                for row in samples).items())),
            "safety_downgrade_count": sum(
                len(row["safety_downgrades"]) for row in comparisons),
        }

    def materialization_summary(samples):
        values = tuple(
            row["materialization_metrics"] for row in samples
            if row.get("materialization_metrics") is not None)

        def shard_record_counts(field):
            counts = Counter()
            for row in values:
                counts.update(row.get(field, {}))
            return dict(sorted(counts.items()))

        return {
            "incremental_recomputation_ratio": _ratio_summary(
                row["incremental_recomputation_ratio"] for row in values),
            "recomputed_projector_counts": dict(sorted(Counter(
                projector_id for row in values
                for projector_id in row[
                    "recomputed_projector_ids"]).items())),
            "recomputed_shard_counts": dict(sorted(Counter(
                shard_id for row in values
                for shard_id in row.get(
                    "recomputed_shard_ids", ())).items())),
            "recomputed_shard_record_counts": shard_record_counts(
                "recomputed_shard_records"),
            "reused_projector_counts": dict(sorted(Counter(
                projector_id for row in values
                for projector_id in row["reused_projector_ids"]).items())),
            "reused_shard_counts": dict(sorted(Counter(
                shard_id for row in values
                for shard_id in row.get("reused_shard_ids", ())).items())),
            "reused_shard_record_counts": shard_record_counts(
                "reused_shard_records"),
            "rich_recomputed_record_count": sum(
                row["rich_recomputed_records"] for row in values),
            "rich_reused_record_count": sum(
                row["rich_reused_records"] for row in values),
            "sample_count": len(values),
        }
    report = {
        "claim_scope": "diagnostic-shadow-replay-only",
        "config": {
            "declaration_hash": declaration["declaration_hash"],
            "path": os.path.relpath(os.path.abspath(args.config), REPO),
        },
        "corpus": {
            "capture_completeness": (
                len(snapshots) / float(len(fixtures)) if fixtures else 0.0),
            "data_gaps": gaps,
            "manifests": manifests,
            "replayable_fixture_count": len(snapshots),
            "unique_fixture_count": len(fixtures),
        },
        "failures": list(failures),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "results": {
            "cold": {
                "latency": _summary(
                    row["latency_ms"] for row in cold_samples),
                "fdas_total_latency": _summary(
                    row["fdas_total_latency_ms"] for row in cold_samples),
                "maximum_atom_count": max(
                    (row["atom_count"] for row in cold_samples), default=0),
                "maximum_dependency_key_count": max(
                    (row["dependency_key_count"] for row in cold_samples),
                    default=0),
                "maximum_scope_count": max(
                    (row["scope_count"] for row in cold_samples), default=0),
                "maximum_support_count": max(
                    (row["support_count"] for row in cold_samples), default=0),
                "materialization": materialization_summary(cold_samples),
                "samples": cold_samples,
                "shadow_evaluation": shadow_summary(cold_samples),
            },
            "incremental": {
                "cold_verification_count": len(verifications),
                "equivalent_count": sum(
                    bool(row["equivalent"]) for row in verifications),
                "latency": _summary(
                    row["latency_ms"] for row in incremental_samples),
                "fdas_total_latency": _summary(
                    row["fdas_total_latency_ms"]
                    for row in incremental_samples),
                "materialization": materialization_summary(
                    incremental_samples),
                "samples": incremental_samples,
                "shadow_evaluation": shadow_summary(incremental_samples),
            },
        },
        "ruleset": args.ruleset,
        "schema_version": "1.0",
    }
    semantic = dict(report)
    semantic.pop("generated_at")
    report["report_hash"] = structural_hash(semantic)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w", encoding="utf-8") as stream:
            stream.write(rendered)
    print(rendered, end="")
    failed = bool(failures)
    if args.require_complete_capture and gaps:
        failed = True
    if any(not row["equivalent"] for row in verifications):
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
