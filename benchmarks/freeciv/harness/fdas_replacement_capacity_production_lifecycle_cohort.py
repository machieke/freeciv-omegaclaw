"""Fixed-seed aggregate for exact replacement-production lifecycles."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash

from .fdas_replacement_capacity_production_lifecycle_live import (
    audit_fdas_replacement_capacity_production_lifecycle_live,
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


def audit_fdas_replacement_capacity_production_lifecycle_cohort(
        run_dir, expected_seeds, expected_source_commit=None, repo=None,
        minimum_games_with_product_observation=1):
    """Aggregate fixed games without dropping zero-match or zero-yield games."""
    run_dir = os.path.abspath(run_dir)
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if not expected_seeds or len(expected_seeds) != len(set(expected_seeds)):
        raise ValueError("replacement production lifecycle seeds must be unique")
    if minimum_games_with_product_observation < 0:
        raise ValueError("minimum product-observation games cannot be negative")
    games_root = os.path.join(run_dir, "games", "main", "e_full_loop")
    rows = []
    for seed in expected_seeds:
        game_dir = os.path.join(games_root, "{}-00".format(seed))
        report = audit_fdas_replacement_capacity_production_lifecycle_live(
            game_dir, repo=repo)
        rows.append({
            "accepted": report["acceptance"]["accepted"],
            "game_dir": _logical(game_dir, repo),
            "report_hash": report["structural_hash"],
            "seed": seed,
            "source_commit": report.get("source", {}).get("commit"),
            **report["summary"],
        })
    run_summary_path = os.path.join(run_dir, "run-summary.json")
    with open(run_summary_path, encoding="utf-8") as stream:
        run_summary = json.load(stream)
    games_with_products = sum(row["product_observations"] > 0 for row in rows)
    checks = {
        "all_expected_games_complete_without_infrastructure_failure": (
            run_summary.get("completed") == len(expected_seeds)
            and run_summary.get("jobs") == len(expected_seeds)
            and run_summary.get("infrastructure_failures") == 0
            and run_summary.get("resumed") == 0),
        "all_game_level_lifecycle_audits_pass": all(
            row["accepted"] for row in rows),
        "all_sources_are_clean_and_commit_bound": all(
            row["source_commit"] is not None
            and (expected_source_commit is None
                 or row["source_commit"] == expected_source_commit)
            for row in rows),
        "exact_selected_action_matches_are_observed": sum(
            row["exact_matches"] for row in rows) > 0,
        "grounded_lifecycle_operations_are_registered": sum(
            row["operations_registered"] for row in rows) > 0,
        "later_authoritative_product_observation_recurs_as_frozen": (
            games_with_products >= minimum_games_with_product_observation),
    }
    totals = {
        name: sum(row[name] for row in rows)
        for name in (
            "ambiguous_matches", "exact_matches", "match_evaluations",
            "no_matches", "operations_registered", "product_observations",
            "queue_acceptances", "queue_observations", "terminal_failures")
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "fixed fresh-game recurrence of exact existing-policy production "
            "matches and later authoritative replacement-defender product "
            "observation only; no policy, causal value, score, or win-rate "
            "claim"),
        "design": {
            "minimum_games_with_product_observation":
                minimum_games_with_product_observation,
            "zero_match_games_retained": True,
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
            **totals,
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
