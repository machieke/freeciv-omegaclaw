"""Deterministic executable-semantics benchmark for PF-PLN Phase 0."""

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


def _atom(atom_id, strength, confidence, resolvability):
    return (
        AtomState(
            atom_id,
            TruthState(strength, confidence, crisp=True),
        ),
        resolvability,
    )


def _capital_graph():
    graph = PressureGraph()
    rows = (
        _atom(
            "survives", 0.42, 0.65,
            Resolvability(infer=0.5, retain=0.5)),
        _atom(
            "no-attack", 0.25, 0.8,
            Resolvability(observe=0.8, act=0.2)),
        _atom(
            "defense", 0.25, 0.9,
            Resolvability(infer=0.3, act=0.8)),
        _atom(
            "treasury", 0.70, 0.70,
            Resolvability(observe=1.0, infer=0.2)),
        _atom(
            "archer-available", 0.95, 0.90,
            Resolvability(observe=0.1, infer=0.2)),
        _atom(
            "buy-archer", 0.0, 1.0,
            Resolvability(act=1.0)),
    )
    for atom, resolvability in rows:
        graph.add_atom(atom, resolvability)
    graph.add_rule(PressureRule(
        "survival-routes",
        ("defense", "no-attack"),
        "survives",
        kind="or",
        causal_kind="procedural",
        premise_weights=(0.69, 0.31),
    ))
    graph.add_rule(PressureRule(
        "buy-route",
        ("treasury", "archer-available", "buy-archer"),
        "defense",
        kind="and",
        causal_kind="procedural",
    ))
    return graph


def run_semantics_benchmark():
    """Execute the worked capital-defense graph through scheduling."""
    graph = _capital_graph()
    truth_before = tuple(atom.to_dict() for atom in graph.atoms)
    goal = GoalState(
        "defend-capital", "survives", 0.90, utility=100.0)
    engine = PressureEngine()
    first = engine.propagate(graph, (goal,))
    second = engine.propagate(graph, (goal,))
    operations = (
        Operation(
            "observe-treasury",
            "treasury",
            "observe",
            CostVector(compute=0.25),
            causal_kind="diagnostic",
        ),
        Operation(
            "buy-archer",
            "buy-archer",
            "act",
            CostVector(resource=1.0),
            causal_kind="procedural",
        ),
        Operation(
            "observe-archer-availability",
            "archer-available",
            "observe",
            CostVector(compute=0.25),
            causal_kind="diagnostic",
        ),
    )
    scheduler = PressureScheduler()
    schedule = scheduler.decision_artifact(operations, first)
    repeat_schedule = scheduler.decision_artifact(operations, second)
    truth_after = tuple(atom.to_dict() for atom in graph.atoms)

    report = {
        "acceptance": {
            "capital_defense_executes_end_to_end": (
                schedule["selected_operation_id"] is not None),
            "pressure_reproducible": (
                first.artifact_hash == second.artifact_hash),
            "schedule_reproducible": schedule == repeat_schedule,
            "truth_firewall_preserved": truth_before == truth_after,
            "typed_pressure_reaches_action_and_observation": (
                first.pressure(
                    "defend-capital", "buy-archer").act > 0
                and first.pressure(
                    "defend-capital", "treasury").observe > 0),
        },
        "benchmark": "pf-pln-phase-0-executable-semantics",
        "capital_defense": {
            "buy_archer_action_pressure": first.pressure(
                "defend-capital", "buy-archer").act,
            "defense_dependency": first.dependency(
                "defend-capital", "defense"),
            "goal_dependency": first.dependency(
                "defend-capital", "survives"),
            "no_attack_dependency": first.dependency(
                "defend-capital", "no-attack"),
            "pressure_hash": first.artifact_hash,
            "selected_operation_id": schedule["selected_operation_id"],
            "treasury_observation_pressure": first.pressure(
                "defend-capital", "treasury").observe,
        },
        "configuration": {
            "graph_hash": graph.artifact_hash,
            "operations": [
                {
                    "atom_id": operation.atom_id,
                    "cost": operation.cost.to_dict(),
                    "mode": operation.mode,
                    "operation_id": operation.operation_id,
                }
                for operation in operations
            ],
        },
        "schema_version": "1.0",
    }
    report["artifact_hash"] = structural_hash(report)
    return report
