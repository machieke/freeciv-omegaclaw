"""Fixed-cohort audit for retained-capacity transition discovery data."""

import json
import os

from freeciv_agent.events.schema import structural_hash

from .fdas_retained_capacity_query_episode_dataset import (
    export_fdas_retained_capacity_query_episode_dataset,
)
from .statistics import wilson


TRANSITION_DISCOVERY_COHORT_IDENTITY = (
    "fdas-retained-capacity-transition-discovery-cohort/1.0")
FROZEN_DISCOVERY_GAMES = 301
FROZEN_ADEQUACY_THRESHOLDS = {
    "effect-without-goal-relief_episodes": 10,
    "effect-without-goal-relief_games": 10,
    "goal-relief-observed_episodes": 10,
    "goal-relief-observed_games": 10,
    "no-effect-observed_episodes": 10,
    "no-effect-observed_games": 10,
    "terminal_bearing_games": 20,
    "terminal_rows": 30,
}
_STATUSES = (
    "no-effect-observed", "effect-without-goal-relief",
    "goal-relief-observed",
)


def _load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def retained_capacity_transition_discovery_adequacy(dataset):
    """Evaluate only the frozen PR98 diversity gates for an exported dataset."""
    rows_by_seed = dict((value["seed"], []) for value in dataset["games"])
    for value in dataset["rows"]:
        rows_by_seed[value["seed"]].append(value["row"])
    status_episodes = dict((status, sum(
        value["row"]["outcome_status"] == status
        for value in dataset["rows"])) for status in _STATUSES)
    status_games = dict((status, sum(any(
        row["outcome_status"] == status for row in rows_by_seed[seed])
        for seed in rows_by_seed)) for status in _STATUSES)
    terminal_bearing_games = sum(any(
        row["observation_status"] == "terminal-observed"
        for row in rows_by_seed[seed]) for seed in rows_by_seed)
    measures = {
        "terminal_bearing_games": terminal_bearing_games,
        "terminal_rows": dataset["summary"]["terminal_rows"],
    }
    for status in _STATUSES:
        measures[status + "_episodes"] = status_episodes[status]
        measures[status + "_games"] = status_games[status]
    checks = dict((name + "_minimum_met",
                   measures[name] >= FROZEN_ADEQUACY_THRESHOLDS[name])
                  for name in sorted(FROZEN_ADEQUACY_THRESHOLDS))
    return {
        "checks": checks,
        "decision": (
            "eligible-for-preregistered-transition-model-fitting"
            if all(checks.values()) else "insufficient-evidence"),
        "measures": measures,
        "thresholds": dict(FROZEN_ADEQUACY_THRESHOLDS),
    }


def audit_fdas_retained_capacity_transition_discovery(
        run_dir, expected_seeds, expected_source_commit, repo=None,
        audit_workers=4):
    """Audit the exact PR98 discovery cohort without fitting a model."""
    seeds = tuple(int(value) for value in expected_seeds)
    if (len(seeds) != FROZEN_DISCOVERY_GAMES
            or len(seeds) != len(set(seeds))):
        raise ValueError(
            "retained capacity transition discovery requires 301 unique seeds")
    dataset = export_fdas_retained_capacity_query_episode_dataset(
        run_dir, seeds, expected_source_commit, repo=repo,
        audit_workers=audit_workers)
    run_summary = _load(os.path.join(os.path.abspath(run_dir),
                                     "run-summary.json"))
    adequacy = retained_capacity_transition_discovery_adequacy(dataset)
    rows_by_seed = dict((seed, []) for seed in seeds)
    for value in dataset["rows"]:
        rows_by_seed[value["seed"]].append(value["row"])
    terminal_bearing_games = adequacy["measures"]["terminal_bearing_games"]
    censored_bearing_games = sum(any(
        row["observation_status"] == "right-censored"
        for row in rows_by_seed[seed]) for seed in seeds)
    status_bearing_games = dict((status, adequacy["measures"][
        status + "_games"]) for status in _STATUSES)
    rates = {
        "games_with_queries": wilson(
            dataset["summary"]["games_with_queries"], len(seeds)),
        "right_censored_query_bearing_games": wilson(
            censored_bearing_games, len(seeds)),
        "terminal_bearing_games": wilson(
            terminal_bearing_games, len(seeds)),
    }
    rates.update(dict((status + "_bearing_games", wilson(
        status_bearing_games[status], len(seeds))) for status in _STATUSES))
    mechanics_checks = {
        "all_query_episode_dataset_gates_pass": (
            dataset["acceptance"]["accepted"]),
        "all_truth_learning_readout_policy_authority_remains_disabled": all(
            dataset.get(name) is False for name in (
                "truth_mutated", "learning_authority",
                "policy_authority", "readout_authority")),
        "exact_fixed_games_are_retained_once": (
            tuple(value["seed"] for value in dataset["games"]) == seeds
            and len(dataset["games"]) == FROZEN_DISCOVERY_GAMES),
        "run_completed_exactly_without_resume_or_infrastructure_failure": (
            run_summary.get("jobs") == FROZEN_DISCOVERY_GAMES
            and run_summary.get("completed") == FROZEN_DISCOVERY_GAMES
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
    mechanics_accepted = all(mechanics_checks.values())
    report = {
        "acceptance": {
            "accepted": mechanics_accepted,
            "checks": mechanics_checks,
        },
        "adequacy": adequacy,
        "claim_scope": (
            "fixed 301-game retained-capacity transition discovery data "
            "mechanics and preregistered diversity adequacy only; no fitted "
            "model, calibration, causal, readout, policy, gameplay, score, "
            "or win-rate claim"),
        "dataset": dataset,
        "discovery_ready": (
            mechanics_accepted
            and adequacy["decision"]
            == "eligible-for-preregistered-transition-model-fitting"),
        "identity": TRANSITION_DISCOVERY_COHORT_IDENTITY,
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
        "truth_mutated": False,
        "learning_authority": False,
        "policy_authority": False,
        "readout_authority": False,
    }
    report["structural_hash"] = structural_hash(report)
    return report
