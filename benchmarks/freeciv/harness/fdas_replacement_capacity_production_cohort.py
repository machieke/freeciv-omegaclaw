"""Fixed-seed audit for delayed replacement-capacity production mechanics."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash

from .fdas_replacement_capacity_production_live import (
    audit_fdas_replacement_capacity_production_live,
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


def audit_fdas_replacement_capacity_production_cohort(
        run_dir, expected_seeds, expected_source_commit=None, repo=None):
    """Aggregate all preregistered games without selecting on candidate yield."""
    run_dir = os.path.abspath(run_dir)
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if not expected_seeds or len(expected_seeds) != len(set(expected_seeds)):
        raise ValueError(
            "replacement capacity production cohort requires unique seeds")
    games_root = os.path.join(run_dir, "games", "main", "e_full_loop")
    rows = []
    for seed in expected_seeds:
        game_dir = os.path.join(games_root, "{}-00".format(seed))
        report = audit_fdas_replacement_capacity_production_live(
            game_dir, repo=repo)
        rows.append({
            "accepted": report["acceptance"]["accepted"],
            "capacity_production_candidates": report["summary"][
                "capacity_production_candidates"],
            "game_dir": _logical(game_dir, repo),
            "grounded_production_operations": report["summary"][
                "grounded_production_operations"],
            "production_model_abstentions": report["summary"][
                "production_model_abstentions"],
            "report_hash": report["structural_hash"],
            "seed": seed,
            "source_commit": report.get("source", {}).get("commit"),
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
        "all_game_level_production_operation_audits_pass": all(
            row["accepted"] for row in rows),
        "all_sources_are_clean_and_commit_bound": all(
            row["source_commit"] is not None
            and (expected_source_commit is None
                 or row["source_commit"] == expected_source_commit)
            for row in rows),
        "grounded_production_operations_recur_across_games": sum(
            row["grounded_production_operations"] > 0 for row in rows) >= 4,
        "grounded_production_operation_yield_is_nonzero": sum(
            row["grounded_production_operations"] for row in rows) > 0,
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "fixed fresh-game distribution of ruleset-grounded delayed "
            "replacement-defender production candidate mechanics only; no "
            "completion, goal-relief, action, score, or win-rate claim"),
        "evidence": {
            "run-summary.json": {
                "path": _logical(run_summary_path, repo),
                "sha256": _sha256(run_summary_path),
            },
        },
        "games": rows,
        "schema_version": "1.0",
        "summary": {
            "capacity_production_candidate_count": sum(
                row["capacity_production_candidates"] for row in rows),
            "game_count": len(rows),
            "games_with_grounded_production_operation": sum(
                row["grounded_production_operations"] > 0 for row in rows),
            "grounded_production_operation_count": sum(
                row["grounded_production_operations"] for row in rows),
            "production_model_abstention_count": sum(
                row["production_model_abstentions"] for row in rows),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
