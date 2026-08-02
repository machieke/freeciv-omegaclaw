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
            snapshots.append((relative, snapshot))
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
    for relative, snapshot in snapshots:
        runtime = build_runtime(
            declaration,
            ruleset_ir=ruleset_ir,
            operation_records_source=lambda: ())
        started = time.perf_counter()
        try:
            update = runtime.replace(snapshot)
            elapsed = (time.perf_counter() - started) * 1000.0
            sample = {
                "latency_ms": elapsed,
                "path": relative,
                "revision_id": update.revision_id,
                "snapshot_id": snapshot.snapshot_id,
                "source_seq": snapshot.identity.source_seq,
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
    for relative, snapshot in snapshots:
        started = time.perf_counter()
        try:
            update = runtime.replace(snapshot)
            elapsed = (time.perf_counter() - started) * 1000.0
            samples.append({
                "cold_verification": (
                    None if update.cold_verification is None
                    else update.cold_verification.to_dict()),
                "latency_ms": elapsed,
                "path": relative,
                "revision_id": update.revision_id,
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
                "maximum_atom_count": max(
                    (row["atom_count"] for row in cold_samples), default=0),
                "maximum_dependency_key_count": max(
                    (row["dependency_key_count"] for row in cold_samples),
                    default=0),
                "maximum_scope_count": max(
                    (row["scope_count"] for row in cold_samples), default=0),
                "maximum_support_count": max(
                    (row["support_count"] for row in cold_samples), default=0),
                "samples": cold_samples,
            },
            "incremental": {
                "cold_verification_count": len(verifications),
                "equivalent_count": sum(
                    bool(row["equivalent"]) for row in verifications),
                "latency": _summary(
                    row["latency_ms"] for row in incremental_samples),
                "samples": incremental_samples,
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
