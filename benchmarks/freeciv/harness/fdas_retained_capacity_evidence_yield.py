"""Frozen evidence-yield plan for retained-capacity terminal statuses."""

from freeciv_agent.events.schema import structural_hash

from .statistics import binomial_minimum_trials, wilson


EVIDENCE_YIELD_PLAN_IDENTITY = "fdas-retained-capacity-evidence-yield-plan/1.0"
FROZEN_STATUS_BEARING_GAMES = {
    "effect-without-goal-relief": 1,
    "goal-relief-observed": 2,
    "no-effect-observed": 3,
}
FROZEN_SOURCE_GAMES = 16
FROZEN_REQUIRED_STATUS_GAMES = 10
FROZEN_TARGET_YIELD_PROBABILITY = 0.9
FROZEN_QUERY_ENABLED_PILOT_GAMES = 64


def retained_capacity_evidence_yield_plan(
        status_bearing_games=None, source_games=FROZEN_SOURCE_GAMES,
        required_status_games=FROZEN_REQUIRED_STATUS_GAMES,
        target_probability=FROZEN_TARGET_YIELD_PROBABILITY,
        query_enabled_pilot_games=FROZEN_QUERY_ENABLED_PILOT_GAMES):
    """Plan fixed cohorts from per-game status recurrence without fitting."""
    counts = dict(
        FROZEN_STATUS_BEARING_GAMES
        if status_bearing_games is None else status_bearing_games)
    source_games = int(source_games)
    required_status_games = int(required_status_games)
    query_enabled_pilot_games = int(query_enabled_pilot_games)
    if (set(counts) != set(FROZEN_STATUS_BEARING_GAMES)
            or source_games < 1 or required_status_games < 1
            or query_enabled_pilot_games < 1
            or any(isinstance(value, bool) or not isinstance(value, int)
                   or value < 1 or value > source_games
                   for value in counts.values())):
        raise ValueError("retained capacity evidence-yield inputs differ")

    statuses = []
    for status in sorted(counts):
        observed = counts[status]
        plug_in_rate = observed / float(source_games)
        interval = wilson(observed, source_games)
        plug_in = binomial_minimum_trials(
            plug_in_rate, required_status_games, target_probability)
        lower_bound = binomial_minimum_trials(
            interval["lower"], required_status_games, target_probability)
        statuses.append({
            "observed_status_bearing_games": observed,
            "plug_in_design": plug_in,
            "plug_in_rate": plug_in_rate,
            "status": status,
            "wilson_95_interval": interval,
            "wilson_lower_sensitivity_design": lower_bound,
        })
    provisional = max(
        value["plug_in_design"]["samples"] for value in statuses)
    conservative = max(
        value["wilson_lower_sensitivity_design"]["samples"]
        for value in statuses)
    report = {
        "claim_scope": (
            "exact fixed-cohort evidence-yield planning from reused PR94 "
            "per-game status recurrence; no population-rate, model, "
            "calibration, learning, causal, score, or win-rate claim"),
        "confirmation": {
            "disjoint_fixed_seeds_required": True,
            "provisional_games": provisional,
        },
        "discovery": {
            "fixed_seeds_required": True,
            "provisional_games": provisional,
        },
        "identity": EVIDENCE_YIELD_PLAN_IDENTITY,
        "planning": {
            "conservative_wilson_lower_sensitivity_games": conservative,
            "provisional_games_per_discovery_or_confirmation_cohort": (
                provisional),
            "query_enabled_yield_pilot_games": query_enabled_pilot_games,
            "required_status_bearing_games": required_status_games,
            "target_probability": float(target_probability),
        },
        "schema_version": "1.0",
        "source": {
            "cohort": "reused-published-PR94",
            "independence_unit": "game-status-occurrence",
            "source_games": source_games,
            "status_bearing_games": dict(sorted(counts.items())),
        },
        "statuses": statuses,
        "truth_mutated": False,
        "learning_authority": False,
        "policy_authority": False,
        "readout_authority": False,
    }
    report["plan_hash"] = structural_hash(report)
    return report
