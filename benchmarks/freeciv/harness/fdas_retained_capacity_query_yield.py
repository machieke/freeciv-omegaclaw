"""Fresh fixed-cohort yield audit for retained-capacity query rows."""

import json
import os

from freeciv_agent.events.schema import structural_hash

from .fdas_retained_capacity_evidence_yield import (
    retained_capacity_evidence_yield_plan,
)
from .fdas_retained_capacity_query_episode_dataset import (
    export_fdas_retained_capacity_query_episode_dataset,
)
from .statistics import wilson


QUERY_YIELD_COHORT_IDENTITY = "fdas-retained-capacity-query-yield-cohort/1.0"
FROZEN_PILOT_GAMES = 64
_STATUSES = (
    "no-effect-observed", "effect-without-goal-relief",
    "goal-relief-observed",
)


def _load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def audit_fdas_retained_capacity_query_yield(
        run_dir, expected_seeds, expected_source_commit, repo=None,
        audit_workers=4):
    """Audit the exact PR97 game-level recurrence and prospective sizing."""
    seeds = tuple(int(value) for value in expected_seeds)
    if (len(seeds) != FROZEN_PILOT_GAMES
            or len(seeds) != len(set(seeds))):
        raise ValueError("retained capacity yield pilot requires 64 seeds")
    dataset = export_fdas_retained_capacity_query_episode_dataset(
        run_dir, seeds, expected_source_commit, repo=repo,
        audit_workers=audit_workers)
    run_summary = _load(os.path.join(os.path.abspath(run_dir),
                                     "run-summary.json"))
    rows_by_seed = dict((seed, []) for seed in seeds)
    for value in dataset["rows"]:
        rows_by_seed[value["seed"]].append(value["row"])

    games_with_queries = sum(bool(rows_by_seed[seed]) for seed in seeds)
    terminal_bearing_games = sum(any(
        row["observation_status"] == "terminal-observed"
        for row in rows_by_seed[seed]) for seed in seeds)
    censored_bearing_games = sum(any(
        row["observation_status"] == "right-censored"
        for row in rows_by_seed[seed]) for seed in seeds)
    status_bearing_games = dict((status, sum(any(
        row["outcome_status"] == status for row in rows_by_seed[seed])
        for seed in seeds)) for status in _STATUSES)
    rates = {
        "games_with_queries": wilson(games_with_queries, len(seeds)),
        "right_censored_query_bearing_games": wilson(
            censored_bearing_games, len(seeds)),
        "terminal_bearing_games": wilson(
            terminal_bearing_games, len(seeds)),
    }
    rates.update(dict((status + "_bearing_games", wilson(
        status_bearing_games[status], len(seeds))) for status in _STATUSES))
    updated_plan = retained_capacity_evidence_yield_plan(
        status_bearing_games=status_bearing_games,
        source_games=len(seeds))
    checks = {
        "all_query_episode_dataset_gates_pass": (
            dataset["acceptance"]["accepted"]),
        "all_truth_learning_readout_policy_authority_remains_disabled": all(
            dataset.get(name) is False for name in (
                "truth_mutated", "learning_authority",
                "policy_authority", "readout_authority")),
        "exact_fixed_games_are_retained_once": (
            tuple(value["seed"] for value in dataset["games"]) == seeds
            and len(dataset["games"]) == FROZEN_PILOT_GAMES),
        "run_completed_exactly_without_resume_or_infrastructure_failure": (
            run_summary.get("jobs") == FROZEN_PILOT_GAMES
            and run_summary.get("completed") == FROZEN_PILOT_GAMES
            and run_summary.get("resumed") == 0
            and run_summary.get("infrastructure_failures") == 0),
        "status_bearing_counts_are_game_scoped": all(
            status_bearing_games[status] == sum(any(
                row["outcome_status"] == status
                for row in rows_by_seed[seed]) for seed in seeds)
            for status in _STATUSES),
        "terminal_and_censored_game_counts_are_exact": (
            terminal_bearing_games == sum(
                value["terminal_rows"] > 0 for value in dataset["games"])
            and censored_bearing_games == sum(
                value["censored_rows"] > 0 for value in dataset["games"])),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "fresh fixed 64-game retained-capacity query, terminal, "
            "censoring, status, and feature recurrence plus prospective "
            "sample-size sensitivity; no model fitting, calibration, causal, "
            "policy, gameplay, score, or win-rate claim"),
        "dataset": dataset,
        "identity": QUERY_YIELD_COHORT_IDENTITY,
        "rates": rates,
        "run_summary": run_summary,
        "schema_version": "1.0",
        "source": {
            "expected_commit": expected_source_commit,
            "expected_seeds": list(seeds),
        },
        "summary": {
            **dataset["summary"],
            "right_censored_query_bearing_games": censored_bearing_games,
            "status_bearing_games": dict(sorted(status_bearing_games.items())),
            "terminal_bearing_games": terminal_bearing_games,
        },
        "updated_prospective_yield_plan": updated_plan,
        "truth_mutated": False,
        "learning_authority": False,
        "policy_authority": False,
        "readout_authority": False,
    }
    report["structural_hash"] = structural_hash(report)
    return report
