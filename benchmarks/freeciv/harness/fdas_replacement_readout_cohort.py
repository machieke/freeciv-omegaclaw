"""Deterministic fresh-seed cohort audit for replacement candidate recall."""

import hashlib
import json
import math
import os

from freeciv_agent.events.schema import structural_hash

from .fdas_replacement_readout_live import (
    audit_fdas_replacement_readout_live,
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


def _wilson(successes, total, z=1.959963984540054):
    if total <= 0:
        return None, None
    proportion = float(successes) / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    spread = z * math.sqrt(
        proportion * (1.0 - proportion) / total
        + z * z / (4.0 * total * total)) / denominator
    return max(0.0, center - spread), min(1.0, center + spread)


def audit_fdas_replacement_readout_cohort(
        run_dir, expected_seeds, expected_source_commit=None, repo=None):
    """Require mechanics in all games and opportunity in two game clusters."""
    run_dir = os.path.abspath(run_dir)
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if not expected_seeds or len(expected_seeds) != len(set(expected_seeds)):
        raise ValueError("replacement cohort requires unique expected seeds")
    games_root = os.path.join(run_dir, "games", "main", "e_full_loop")
    rows = []
    for seed in expected_seeds:
        game_dir = os.path.join(games_root, "{}-00".format(seed))
        report = audit_fdas_replacement_readout_live(
            game_dir, repo=repo, require_grounded_pair=False)
        rows.append({
            "accepted": report["acceptance"]["accepted"],
            "game_dir": _logical(game_dir, repo),
            "grounded_pairs": report["summary"]["grounded_pairs"],
            "report_hash": report["structural_hash"],
            "seed": seed,
            "source_commit": report.get("source", {}).get("commit"),
        })
    opportunity = tuple(row for row in rows if row["grounded_pairs"] > 0)
    lower, upper = _wilson(len(opportunity), len(rows))
    run_summary_path = os.path.join(run_dir, "run-summary.json")
    with open(run_summary_path, encoding="utf-8") as stream:
        run_summary = json.load(stream)
    checks = {
        "all_expected_games_complete_without_infrastructure_failure": (
            run_summary.get("completed") == len(expected_seeds)
            and run_summary.get("jobs") == len(expected_seeds)
            and run_summary.get("infrastructure_failures") == 0
            and run_summary.get("resumed") == 0),
        "all_game_level_lifecycle_and_readout_audits_pass": all(
            row["accepted"] for row in rows),
        "all_sources_are_clean_and_commit_bound": all(
            row["source_commit"] is not None
            and (expected_source_commit is None
                 or row["source_commit"] == expected_source_commit)
            for row in rows),
        "grounded_recall_occurs_in_two_independent_games": (
            len(opportunity) >= 2),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "fresh-seed game-level coordinated-replacement recall rate and "
            "mechanical transfer only; no transition value, preference, "
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
            "game_count": len(rows),
            "grounded_pair_count": sum(
                row["grounded_pairs"] for row in rows),
            "opportunity_game_count": len(opportunity),
            "opportunity_game_rate": float(len(opportunity)) / len(rows),
            "opportunity_game_rate_wilson_95": {
                "lower": lower, "upper": upper},
            "opportunity_seeds": [row["seed"] for row in opportunity],
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
