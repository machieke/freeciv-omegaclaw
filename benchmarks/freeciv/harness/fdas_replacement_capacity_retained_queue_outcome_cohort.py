"""Aggregate fixed fresh retained-capacity delayed-outcome evidence."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash

from .fdas_replacement_capacity_retained_queue_outcome_live import (
    audit_fdas_replacement_capacity_retained_queue_outcome_live,
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


def audit_fdas_replacement_capacity_retained_queue_outcome_cohort(
        run_dir, expected_seeds, expected_source_commit=None, repo=None,
        minimum_games_with_label=2, minimum_games_with_product=1,
        minimum_games_with_relief=1, minimum_positive_relief=1):
    """Retain every fixed game, including all censored zero-yield games."""
    run_dir = os.path.abspath(run_dir)
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if not expected_seeds or len(expected_seeds) != len(set(expected_seeds)):
        raise ValueError("retained capacity outcome cohort seeds must be unique")
    thresholds = {
        "label": minimum_games_with_label,
        "product": minimum_games_with_product,
        "relief": minimum_games_with_relief,
        "positive relief": minimum_positive_relief,
    }
    for name, value in thresholds.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("minimum {} is invalid".format(name))
    games_root = os.path.join(run_dir, "games", "main", "e_full_loop")
    rows = []
    for seed in expected_seeds:
        game_dir = os.path.join(games_root, "{}-00".format(seed))
        report = audit_fdas_replacement_capacity_retained_queue_outcome_live(
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
    games_with_labels = sum(row["labels_opened"] > 0 for row in rows)
    games_with_products = sum(row["products_observed"] > 0 for row in rows)
    games_with_relief = sum(row["relief_observed"] > 0 for row in rows)
    names = (
        "labels_opened", "pending_product", "products_observed",
        "pending_relief", "terminal_no_progress", "relief_observed",
        "relief_positive", "relief_negative")
    totals = dict((name, sum(row[name] for row in rows)) for name in names)
    checks = {
        "all_expected_games_complete_without_infrastructure_failure": (
            run_summary.get("completed") == len(expected_seeds)
            and run_summary.get("jobs") == len(expected_seeds)
            and run_summary.get("infrastructure_failures") == 0
            and run_summary.get("resumed") == 0),
        "all_game_level_delayed_outcome_audits_pass": all(
            row["accepted"] for row in rows),
        "all_sources_are_clean_and_commit_bound": all(
            row["source_commit"] is not None
            and row["source_dirty"] is False
            and (expected_source_commit is None
                 or row["source_commit"] == expected_source_commit)
            for row in rows),
        "retained_queue_label_recurrence_meets_frozen_minimum": (
            games_with_labels >= minimum_games_with_label),
        "exact_product_recurrence_meets_frozen_minimum": (
            games_with_products >= minimum_games_with_product),
        "delayed_relief_recurrence_meets_frozen_minimum": (
            games_with_relief >= minimum_games_with_relief),
        "durable_positive_relief_meets_frozen_minimum": (
            totals["relief_positive"] >= minimum_positive_relief),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "fixed fresh-game recurrence of exact retained replacement-"
            "capacity queue, product, and delayed durable-relief attribution; "
            "zero-yield and right-censored games are retained; no causal "
            "policy, transition-value, score, or win-rate claim"),
        "design": {
            "minimum_games_with_label": minimum_games_with_label,
            "minimum_games_with_product": minimum_games_with_product,
            "minimum_games_with_relief": minimum_games_with_relief,
            "minimum_positive_relief": minimum_positive_relief,
            "zero_yield_and_right_censored_games_retained": True,
        },
        "evidence": {"run-summary.json": {
            "path": _logical(run_summary_path, repo),
            "sha256": _sha256(run_summary_path),
        }},
        "games": rows,
        "schema_version": "1.0",
        "summary": {
            "game_count": len(rows),
            "games_with_label": games_with_labels,
            "games_with_product": games_with_products,
            "games_with_relief": games_with_relief,
            **totals,
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
