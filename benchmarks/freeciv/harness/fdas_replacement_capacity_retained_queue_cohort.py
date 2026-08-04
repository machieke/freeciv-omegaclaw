"""Aggregate fixed fresh retained replacement-capacity queue evidence."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash

from .fdas_replacement_capacity_retained_queue_live import (
    audit_fdas_replacement_capacity_retained_queue_live,
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


def audit_fdas_replacement_capacity_retained_queue_cohort(
        run_dir, expected_seeds, expected_source_commit=None, repo=None,
        minimum_games_with_selected_match=2,
        minimum_games_with_product_observation=1):
    """Retain every fixed game, including zero-match and zero-product games."""
    run_dir = os.path.abspath(run_dir)
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if not expected_seeds or len(expected_seeds) != len(set(expected_seeds)):
        raise ValueError("retained queue cohort seeds must be unique")
    for value, name in (
            (minimum_games_with_selected_match, "selected-match"),
            (minimum_games_with_product_observation, "product-observation")):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("minimum {} games is invalid".format(name))
    games_root = os.path.join(run_dir, "games", "main", "e_full_loop")
    rows = []
    for seed in expected_seeds:
        game_dir = os.path.join(games_root, "{}-00".format(seed))
        report = audit_fdas_replacement_capacity_retained_queue_live(
            game_dir, repo=repo)
        rows.append({
            "accepted": report["acceptance"]["accepted"],
            "game_dir": _logical(game_dir, repo),
            "report_hash": report["structural_hash"],
            "seed": seed,
            "source_commit": report.get("source", {}).get("commit"),
            "source_dirty": report.get("source", {}).get("dirty"),
            **report["summary"],
        })
    run_summary_path = os.path.join(run_dir, "run-summary.json")
    with open(run_summary_path, encoding="utf-8") as stream:
        run_summary = json.load(stream)
    games_with_matches = sum(row["selected_matches"] > 0 for row in rows)
    games_with_products = sum(row["product_observations"] > 0 for row in rows)
    checks = {
        "all_expected_games_complete_without_infrastructure_failure": (
            run_summary.get("completed") == len(expected_seeds)
            and run_summary.get("jobs") == len(expected_seeds)
            and run_summary.get("infrastructure_failures") == 0
            and run_summary.get("resumed") == 0),
        "all_game_level_retained_queue_audits_pass": all(
            row["accepted"] for row in rows),
        "all_sources_are_clean_and_commit_bound": all(
            row["source_commit"] is not None
            and row["source_dirty"] is False
            and (expected_source_commit is None
                 or row["source_commit"] == expected_source_commit)
            for row in rows),
        "selected_retained_queue_recurrence_meets_frozen_minimum": (
            games_with_matches >= minimum_games_with_selected_match),
        "authoritative_product_recurrence_meets_frozen_minimum": (
            games_with_products >= minimum_games_with_product_observation),
    }
    names = (
        "ambiguous_matches", "evaluations", "no_matches",
        "operations_registered", "product_observations",
        "queue_observations", "selected_matches", "terminal_failures")
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "fixed fresh-game recurrence of PF-selected already-authoritative "
            "replacement-capacity queues and later observed terminal outcome; "
            "no action, causal value, score, or win-rate claim"),
        "design": {
            "minimum_games_with_product_observation":
                minimum_games_with_product_observation,
            "minimum_games_with_selected_match":
                minimum_games_with_selected_match,
            "zero_match_and_zero_product_games_retained": True,
        },
        "evidence": {"run-summary.json": {
            "path": _logical(run_summary_path, repo),
            "sha256": _sha256(run_summary_path),
        }},
        "games": rows,
        "schema_version": "1.0",
        "summary": {
            "game_count": len(rows),
            "games_with_product_observation": games_with_products,
            "games_with_selected_match": games_with_matches,
            **dict((name, sum(row[name] for row in rows)) for name in names),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
