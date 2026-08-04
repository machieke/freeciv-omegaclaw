"""Deterministic fixed-seed audit for replacement opportunity staging."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash

from .fdas_replacement_opportunity_live import (
    audit_fdas_replacement_opportunity_live,
)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _logical(path, repo=None):
    absolute = os.path.abspath(path)
    if repo is not None:
        relative = os.path.relpath(absolute, os.path.abspath(repo))
        if relative != os.pardir and not relative.startswith(os.pardir + os.sep):
            return relative.replace(os.sep, "/")
    return absolute


def audit_fdas_replacement_opportunity_cohort(
        run_dir, expected_seeds, expected_source_commit=None, repo=None):
    """Aggregate fixed independent games without selecting on opportunity."""
    run_dir = os.path.abspath(run_dir)
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if not expected_seeds or len(expected_seeds) != len(set(expected_seeds)):
        raise ValueError("replacement opportunity cohort requires unique seeds")
    games_root = os.path.join(run_dir, "games", "main", "e_full_loop")
    rows = []
    stage_counts = {}
    for seed in expected_seeds:
        game_dir = os.path.join(games_root, "{}-00".format(seed))
        report = audit_fdas_replacement_opportunity_live(game_dir, repo=repo)
        for stage, count in report["summary"]["stage_counts"].items():
            stage_counts[stage] = stage_counts.get(stage, 0) + count
        rows.append({
            "accepted": report["acceptance"]["accepted"],
            "evaluations": report["summary"]["evaluations"],
            "game_dir": _logical(game_dir, repo),
            "report_hash": report["structural_hash"],
            "seed": seed,
            "source_commit": report.get("source", {}).get("commit"),
            "stage_counts": report["summary"]["stage_counts"],
        })
    run_summary_path = os.path.join(run_dir, "run-summary.json")
    with open(run_summary_path, encoding="utf-8") as stream:
        run_summary = json.load(stream)
    checks = {
        "all_expected_games_complete_without_infrastructure_failure": (
            run_summary.get("completed") == len(expected_seeds)
            and run_summary.get("jobs") == len(expected_seeds)
            and run_summary.get("infrastructure_failures") == 0
            and run_summary.get("resumed") == 0),
        "all_game_level_opportunity_funnel_audits_pass": all(
            row["accepted"] for row in rows),
        "all_sources_are_clean_and_commit_bound": all(
            row["source_commit"] is not None
            and (expected_source_commit is None
                 or row["source_commit"] == expected_source_commit)
            for row in rows),
        "every_game_contributes_revision_level_diagnostics": all(
            row["evaluations"] > 0 for row in rows),
        "stage_partition_covers_every_evaluation": (
            sum(stage_counts.values())
            == sum(row["evaluations"] for row in rows)),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "fixed fresh-game distribution of revision-level replacement "
            "opportunity blockers only; no transition value, preference, "
            "action, outcome, score, or win-rate improvement claim"),
        "evidence": {
            "run-summary.json": {
                "path": _logical(run_summary_path, repo),
                "sha256": _sha256(run_summary_path),
            },
        },
        "games": rows,
        "schema_version": "1.0",
        "summary": {
            "evaluation_count": sum(row["evaluations"] for row in rows),
            "game_count": len(rows),
            "games_with_grounded_pair": sum(
                row["stage_counts"].get("grounded-pair-available", 0) > 0
                for row in rows),
            "games_with_no_safe_replacement": sum(
                row["stage_counts"].get(
                    "no-safe-replacement-relation", 0) > 0
                for row in rows),
            "stage_counts": dict(sorted(stage_counts.items())),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
