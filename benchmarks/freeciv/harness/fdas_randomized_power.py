"""Outcome-blind power planning for randomized FDAS candidate value."""

import math
from statistics import NormalDist

from freeciv_agent.events.schema import structural_hash


POWER_PLAN_IDENTITY = "fdas-randomized-candidate-value-power-plan/1.0"


def _probability(value, name):
    value = float(value)
    if not math.isfinite(value) or not 0.0 < value < 1.0:
        raise ValueError("{} must be in (0,1)".format(name))
    return value


def _round_up(value, multiple):
    multiple = int(multiple)
    if multiple < 1:
        raise ValueError("rounding multiple must be positive")
    return int(math.ceil(float(value) / multiple) * multiple)


def _yield_material(report):
    """Extract only frozen yield fields; never inspect outcome direction."""
    games = tuple(report.get("games", ()))
    if not games or report.get("passed") is not True:
        raise ValueError("power planning requires a passed yield audit")
    status_rows = tuple(value.get("status_counts", {}) for value in games)
    game_count = len(games)
    assignment_count = sum(int(value.get("assignments", 0))
                           for value in status_rows)
    opportunity_games = sum(
        int(value.get("assignments", 0)) > 0 for value in status_rows)
    arm_assignments = {
        arm: sum(int(value.get(arm, 0)) for value in status_rows)
        for arm in ("control", "treatment")
    }
    arm_game_clusters = {
        arm: sum(int(value.get(arm, 0)) > 0 for value in status_rows)
        for arm in ("control", "treatment")
    }
    if (assignment_count < 1 or opportunity_games < 1
            or min(arm_assignments.values()) < 1
            or min(arm_game_clusters.values()) < 1):
        raise ValueError("yield audit lacks both randomized arms")
    source_engine_ms = tuple(
        float(value.get("source_engine_backend_latency_ms", 0.0))
        for value in games)
    return {
        "arm_assignments": arm_assignments,
        "arm_game_clusters": arm_game_clusters,
        "assignment_count": assignment_count,
        "game_count": game_count,
        "opportunity_games": opportunity_games,
        "source_engine_backend_latency_ms": list(source_engine_ms),
    }


def plan_randomized_candidate_value(
        yield_report, minimum_detectable_risk_difference=0.35,
        alpha=0.05, target_power=0.80, planning_icc=0.25,
        yield_safety_multiplier=1.25, minimum_game_clusters_per_arm=20,
        workers=4, mean_engine_seconds_per_game=None):
    """Return a conservative outcome-blind clustered discovery design."""
    material = _yield_material(yield_report)
    delta = _probability(
        minimum_detectable_risk_difference,
        "minimum detectable risk difference")
    alpha = _probability(alpha, "alpha")
    target_power = _probability(target_power, "target power")
    planning_icc = float(planning_icc)
    if not math.isfinite(planning_icc) or not 0.0 <= planning_icc < 1.0:
        raise ValueError("planning ICC must be in [0,1)")
    yield_safety_multiplier = float(yield_safety_multiplier)
    if (not math.isfinite(yield_safety_multiplier)
            or yield_safety_multiplier < 1.0):
        raise ValueError("yield safety multiplier cannot be below one")
    minimum_game_clusters_per_arm = int(minimum_game_clusters_per_arm)
    workers = int(workers)
    if minimum_game_clusters_per_arm < 2 or workers < 1:
        raise ValueError("cluster and worker counts are invalid")

    # Symmetric worst-case rates around 0.5 avoid using observed outcome
    # direction or magnitude. This is the conventional normal approximation
    # for an independently randomized two-proportion contrast.
    control_rate = 0.5 - delta / 2.0
    treatment_rate = 0.5 + delta / 2.0
    pooled_rate = 0.5
    normal = NormalDist()
    z_alpha = normal.inv_cdf(1.0 - alpha / 2.0)
    z_power = normal.inv_cdf(target_power)
    independent_per_arm = (
        (z_alpha * math.sqrt(2.0 * pooled_rate * (1.0 - pooled_rate))
         + z_power * math.sqrt(
             control_rate * (1.0 - control_rate)
             + treatment_rate * (1.0 - treatment_rate))) ** 2
        / (delta ** 2))

    mean_cluster_size = (
        material["assignment_count"] / float(material["opportunity_games"]))
    design_effect = 1.0 + max(0.0, mean_cluster_size - 1.0) * planning_icc
    assignments_per_arm = int(math.ceil(
        independent_per_arm * design_effect))
    total_assignments = 2 * assignments_per_arm
    assignment_yield_per_game = (
        material["assignment_count"] / float(material["game_count"]))
    games_for_assignments = int(math.ceil(
        total_assignments / assignment_yield_per_game))

    arm_cluster_yield = min(
        material["arm_game_clusters"].values()) / float(
            material["game_count"])
    games_for_clusters = int(math.ceil(
        minimum_game_clusters_per_arm / arm_cluster_yield))
    point_games = max(games_for_assignments, games_for_clusters)
    planned_games = _round_up(
        math.ceil(point_games * yield_safety_multiplier), workers)

    if mean_engine_seconds_per_game is None:
        observed = tuple(
            value / 1000.0
            for value in material["source_engine_backend_latency_ms"]
            if value > 0.0)
        mean_engine_seconds_per_game = (
            None if not observed else sum(observed) / len(observed))
    if mean_engine_seconds_per_game is not None:
        mean_engine_seconds_per_game = float(mean_engine_seconds_per_game)
        if (not math.isfinite(mean_engine_seconds_per_game)
                or mean_engine_seconds_per_game <= 0.0):
            raise ValueError("mean engine runtime must be positive")
        engine_hours = (
            planned_games * mean_engine_seconds_per_game / 3600.0)
        estimated_wall_hours = engine_hours / workers
    else:
        engine_hours = None
        estimated_wall_hours = None

    yield_material = {
        key: value for key, value in material.items()
        if key != "source_engine_backend_latency_ms"
    }
    semantic = {
        "alpha": alpha,
        "analysis_unit": "assignment-with-game-clustered-inference",
        "assignments_per_arm": assignments_per_arm,
        "claim_scope": (
            "powered randomized candidate-value discovery design; separate "
            "held-out confirmation required; no gameplay, score, or win-rate "
            "claim"),
        "design_effect": design_effect,
        "estimated_engine_hours": engine_hours,
        "estimated_wall_hours": estimated_wall_hours,
        "games_for_assignment_yield": games_for_assignments,
        "games_for_cluster_yield": games_for_clusters,
        "independent_assignments_per_arm": independent_per_arm,
        "mean_assignments_per_opportunity_game": mean_cluster_size,
        "mean_engine_seconds_per_game": mean_engine_seconds_per_game,
        "minimum_detectable_risk_difference": delta,
        "minimum_game_clusters_per_arm": minimum_game_clusters_per_arm,
        "outcome_direction_used": False,
        "planned_games": planned_games,
        "planning_icc": planning_icc,
        "power_plan_identity": POWER_PLAN_IDENTITY,
        "primary_estimand": (
            "treatment-minus-control durable selected-actor city-defense "
            "probability"),
        "target_power": target_power,
        "total_assignments": total_assignments,
        "workers": workers,
        "yield_material": yield_material,
        "yield_material_hash": structural_hash(yield_material),
        "yield_safety_multiplier": yield_safety_multiplier,
    }
    semantic["plan_hash"] = structural_hash(semantic)
    return semantic
