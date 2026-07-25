"""Deterministic conflicting-goal scheduler ablation for PF-PLN Phase 9."""

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.pressure import (
    AtomState,
    CostVector,
    GoalState,
    Operation,
    PressureEngine,
    PressureGraph,
    PressureRule,
    PressureScheduler,
    Resolvability,
    TruthState,
)


def _pressure_result():
    graph = PressureGraph()
    graph.add_atom(
        AtomState("goal:left", TruthState(0.0, 1.0, crisp=True)),
        Resolvability(infer=1.0))
    graph.add_atom(
        AtomState("goal:right", TruthState(0.0, 1.0, crisp=True)),
        Resolvability(infer=1.0))
    graph.add_atom(
        AtomState("shared:operation", TruthState(0.0, 1.0, crisp=True)),
        Resolvability(act=1.0))
    graph.add_rule(PressureRule(
        "route:left", ("shared:operation",), "goal:left",
        causal_kind="procedural"))
    graph.add_rule(PressureRule(
        "route:right", ("shared:operation",), "goal:right",
        causal_kind="procedural"))
    goals = (
        GoalState("left", "goal:left", utility=1.0),
        GoalState("right", "goal:right", utility=1.0),
    )
    return graph, goals, PressureEngine().propagate(graph, goals)


def _operations(harm, balanced_relief):
    cost = CostVector(compute=1.0)
    return (
        Operation(
            "balanced", "shared:operation", "act", cost,
            causal_kind="procedural",
            goal_effects=(
                ("left", balanced_relief),
                ("right", balanced_relief))),
        Operation(
            "specialist-left", "shared:operation", "act", cost,
            causal_kind="procedural",
            goal_effects=(("left", 1.0), ("right", -harm))),
        Operation(
            "specialist-right", "shared:operation", "act", cost,
            causal_kind="procedural",
            goal_effects=(("left", -harm), ("right", 1.0))),
    )


def _single_goal(graph, goal):
    return PressureEngine().propagate(graph, (goal,))


def _joint_relief(score):
    return sum(row.weighted_effect for row in score.goal_effects)


def run_multi_goal_benchmark(scenarios=64):
    scenarios = int(scenarios)
    if scenarios < 8:
        raise ValueError("multi-goal benchmark needs at least eight scenarios")
    graph, goals, joint_pressure = _pressure_result()
    scheduler = PressureScheduler()
    rows = []
    complete_explanations = True
    multi_wins = 0
    total_gain = 0.0
    for index in range(scenarios):
        harm = 0.20 + 0.70 * (index % 8) / 7.0
        balanced_relief = 0.55 + 0.15 * ((index // 8) % 8) / 7.0
        operations = _operations(harm, balanced_relief)
        independent = []
        for goal in goals:
            selected = scheduler.select(
                operations, _single_goal(graph, goal))
            independent.append(selected)
        recommendations = tuple(
            row.operation_id for row in independent)
        # Independent goals disagree under one shared one-operation budget.
        # The baseline coordinator deterministically takes the highest isolated
        # priority and then operation ID; it has no cross-goal effect model.
        baseline_id = sorted(
            independent, key=lambda row: (
                -row.priority, row.operation_id))[0].operation_id
        baseline_score = scheduler.score(
            next(row for row in operations
                 if row.operation_id == baseline_id),
            joint_pressure)
        multi_score = scheduler.select(operations, joint_pressure)
        baseline_relief = _joint_relief(baseline_score)
        multi_relief = _joint_relief(multi_score)
        gain = multi_relief - baseline_relief
        multi_wins += int(gain > 0)
        total_gain += gain
        explanations = tuple(
            row.to_dict() for row in multi_score.goal_effects)
        complete_explanations = (
            complete_explanations
            and set(row["goal_id"] for row in explanations)
            == {"left", "right"})
        rows.append({
            "balanced_relief": balanced_relief,
            "baseline_joint_relief": baseline_relief,
            "baseline_selected": baseline_id,
            "goal_explanations": list(explanations),
            "harm": harm,
            "independent_recommendations": list(recommendations),
            "joint_relief_gain": gain,
            "multi_goal_joint_relief": multi_relief,
            "multi_goal_selected": multi_score.operation_id,
            "scenario": index,
        })
    report = {
        "acceptance": {
            "explanations_preserved_per_goal": complete_explanations,
            "independent_goals_conflict": all(
                len(set(row["independent_recommendations"])) == 2
                for row in rows),
            "multi_goal_beats_independent": multi_wins == scenarios,
            "multi_goal_selects_joint_route": all(
                row["multi_goal_selected"] == "balanced" for row in rows),
        },
        "benchmark": "pf-pln-phase-9-conflicting-goals",
        "configuration": {
            "random_seed": None,
            "scenarios": scenarios,
            "shared_operation_budget": 1,
        },
        "graph_hash": graph.artifact_hash,
        "mean_joint_relief_gain": total_gain / scenarios,
        "multi_goal_wins": multi_wins,
        "scenario_rows": rows,
        "schema_version": "1.0",
    }
    report["artifact_hash"] = structural_hash(report)
    return report
