"""Game-clustered discovery analysis for randomized FDAS candidate value."""

import math
import random

from freeciv_agent.events.schema import structural_hash


ANALYSIS_IDENTITY = "fdas-randomized-candidate-value-discovery/1.0"


def _percentile(values, probability):
    values = tuple(sorted(float(value) for value in values))
    if not values:
        raise ValueError("percentile requires values")
    position = (len(values) - 1) * float(probability)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _risk_difference(rows):
    arms = {}
    for arm in ("control", "treatment"):
        selected = tuple(value for value in rows
                         if value["assigned_arm"] == arm)
        if not selected:
            return None
        weighted_outcomes = sum(
            float(value["label_outcome"])
            / float(value["selection_propensity"])
            for value in selected)
        weights = sum(
            1.0 / float(value["selection_propensity"])
            for value in selected)
        arms[arm] = weighted_outcomes / weights
    return arms["treatment"] - arms["control"]


def analyze_randomized_candidate_value(
        audit_report, minimum_assignments_per_arm=44,
        minimum_game_clusters_per_arm=20, confidence=0.95,
        bootstrap_samples=10000, bootstrap_seed=8113):
    """Analyze one fixed discovery cohort with game-cluster resampling."""
    confidence = float(confidence)
    bootstrap_samples = int(bootstrap_samples)
    bootstrap_seed = int(bootstrap_seed)
    minimum_assignments_per_arm = int(minimum_assignments_per_arm)
    minimum_game_clusters_per_arm = int(minimum_game_clusters_per_arm)
    if (not 0.0 < confidence < 1.0 or bootstrap_samples < 100
            or bootstrap_seed < 0 or minimum_assignments_per_arm < 2
            or minimum_game_clusters_per_arm < 2):
        raise ValueError("candidate-value analysis configuration is invalid")
    if audit_report.get("passed") is not True:
        raise ValueError("candidate-value analysis requires passed audit")
    games = tuple(audit_report.get("games", ()))
    if not games:
        raise ValueError("candidate-value audit has no games")
    game_rows = {}
    for game in games:
        game_id = game.get("game_id")
        if not isinstance(game_id, str) or not game_id:
            raise ValueError("candidate-value game identity is absent")
        rows = tuple(
            value for value in game.get("assignments", ())
            if value.get("label_status") == "observed")
        for row in rows:
            if (row.get("game_id") != game_id
                    or row.get("assigned_arm") not in (
                        "control", "treatment")
                    or not isinstance(row.get("label_outcome"), bool)
                    or isinstance(row.get("selection_propensity"), bool)
                    or not isinstance(row.get("selection_propensity"),
                                      (int, float))
                    or not 0.0 < row["selection_propensity"] < 1.0):
                raise ValueError("candidate-value assignment is invalid")
        game_rows[game_id] = rows
    rows = tuple(value for game in game_rows.values() for value in game)
    assignments = {
        arm: sum(value["assigned_arm"] == arm for value in rows)
        for arm in ("control", "treatment")
    }
    clusters = {
        arm: sum(any(value["assigned_arm"] == arm for value in game)
                 for game in game_rows.values())
        for arm in ("control", "treatment")
    }
    estimate = _risk_difference(rows)
    rng = random.Random(bootstrap_seed)
    game_ids = tuple(sorted(game_rows))
    distribution = []
    for _ in range(bootstrap_samples):
        sampled = tuple(
            rng.choice(game_ids) for unused in game_ids)
        replicate_rows = tuple(
            value for game_id in sampled for value in game_rows[game_id])
        replicate = _risk_difference(replicate_rows)
        if replicate is not None:
            distribution.append(replicate)
    valid_fraction = len(distribution) / float(bootstrap_samples)
    if not distribution:
        interval = None
    else:
        tail = (1.0 - confidence) / 2.0
        interval = [
            _percentile(distribution, tail),
            _percentile(distribution, 1.0 - tail),
        ]
    mechanical_gates = {
        "arm_assignments_meet_power_plan": all(
            value >= minimum_assignments_per_arm
            for value in assignments.values()),
        "arm_game_clusters_meet_power_plan": all(
            value >= minimum_game_clusters_per_arm
            for value in clusters.values()),
        "bootstrap_valid_fraction_at_least_0_99": valid_fraction >= 0.99,
        "source_audit_passed": audit_report.get("passed") is True,
        "source_audit_terminal_aware": str(
            audit_report.get("audit_identity", "")).endswith("/1.5"),
    }
    positive_gate = bool(
        estimate is not None and interval is not None
        and interval[0] > 0.0)
    mechanically_valid = all(mechanical_gates.values())
    semantic = {
        "analysis_identity": ANALYSIS_IDENTITY,
        "assignments": assignments,
        "bootstrap": {
            "confidence": confidence,
            "interval": interval,
            "samples": bootstrap_samples,
            "seed": bootstrap_seed,
            "valid_fraction": valid_fraction,
        },
        "claim_scope": (
            "game-clustered randomized durable-defense candidate-value "
            "discovery; held-out confirmation required; no gameplay, score, "
            "or win-rate claim"),
        "discovery_positive_gate": positive_gate,
        "discovery_risk_difference": estimate,
        "disposition": (
            "advance-positive-confirmation"
            if mechanically_valid and positive_gate else
            "freeze-no-positive-value"
            if mechanically_valid else "mechanically-incomplete"),
        "game_clusters": clusters,
        "mechanical_gates": mechanical_gates,
        "mechanically_valid": mechanically_valid,
        "minimum_assignments_per_arm": minimum_assignments_per_arm,
        "minimum_game_clusters_per_arm": minimum_game_clusters_per_arm,
        "passed": mechanically_valid and positive_gate,
        "primary_estimand": (
            "inverse-propensity treatment-minus-control durable selected-"
            "actor city-defense probability"),
        "source_audit_report_hash": audit_report.get("report_hash"),
    }
    semantic["report_hash"] = structural_hash(semantic)
    return semantic
