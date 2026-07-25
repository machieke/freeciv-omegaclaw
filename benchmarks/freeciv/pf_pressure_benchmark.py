"""Deterministic PF-PLN focus benchmark with irrelevant alternative routes."""

from dataclasses import dataclass

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.pressure import (
    AtomState,
    GoalState,
    PressureConfig,
    PressureEngine,
    PressureGraph,
    PressureRule,
    Resolvability,
    TruthState,
)


@dataclass(frozen=True)
class PressureConcentrationResult:
    irrelevant_branches: int
    branch_depth: int
    exhaustive_expansions: int
    pressure_expansions: int
    instantiation_reduction_factor: float
    expansion_reduction: float
    relevant_pressure_mass: float
    irrelevant_pressure_mass: float
    pressure_concentration: float
    selected_root_routes: tuple
    relevant_route_selected: bool
    equal_decision_quality: bool
    truth_unchanged: bool
    graph_hash: str
    result_hash: str
    config: dict

    def to_dict(self):
        value = {
            "branch_depth": int(self.branch_depth),
            "config": dict(self.config),
            "exhaustive_expansions": int(self.exhaustive_expansions),
            "expansion_reduction": float(self.expansion_reduction),
            "equal_decision_quality": bool(self.equal_decision_quality),
            "graph_hash": self.graph_hash,
            "instantiation_reduction_factor": float(
                self.instantiation_reduction_factor),
            "irrelevant_branches": int(self.irrelevant_branches),
            "irrelevant_pressure_mass": float(
                self.irrelevant_pressure_mass),
            "pressure_concentration": float(self.pressure_concentration),
            "pressure_expansions": int(self.pressure_expansions),
            "relevant_pressure_mass": float(self.relevant_pressure_mass),
            "relevant_route_selected": bool(self.relevant_route_selected),
            "result_hash": self.result_hash,
            "selected_root_routes": list(self.selected_root_routes),
            "truth_unchanged": bool(self.truth_unchanged),
        }
        value["benchmark_hash"] = structural_hash(value)
        return value


def _atom(atom_id, actionable=False):
    return (
        AtomState(atom_id, TruthState(0.0, 1.0, crisp=True)),
        Resolvability(act=1.0) if actionable else Resolvability(infer=1.0),
    )


def _synthetic_graph(irrelevant_branches, branch_depth):
    graph = PressureGraph()
    root, root_resolvability = _atom("benchmark-goal")
    graph.add_atom(root, root_resolvability)
    relevant = []
    for depth in range(branch_depth):
        atom_id = "relevant-{}".format(depth)
        atom, resolvability = _atom(
            atom_id, actionable=depth == branch_depth - 1)
        graph.add_atom(atom, resolvability)
        relevant.append(atom_id)
    graph.add_rule(PressureRule(
        "route-relevant-root", (relevant[0],), "benchmark-goal",
        causal_kind="procedural", success_probability=1.0,
        conductance=1.0, route_cost=1.0))
    for depth in range(1, branch_depth):
        graph.add_rule(PressureRule(
            "route-relevant-{}".format(depth),
            (relevant[depth],), relevant[depth - 1],
            causal_kind="procedural"))

    irrelevant = []
    for branch in range(irrelevant_branches):
        branch_atoms = []
        for depth in range(branch_depth):
            atom_id = "irrelevant-{}-{}".format(branch, depth)
            atom, resolvability = _atom(
                atom_id, actionable=depth == branch_depth - 1)
            graph.add_atom(atom, resolvability)
            branch_atoms.append(atom_id)
            irrelevant.append(atom_id)
        graph.add_rule(PressureRule(
            "route-irrelevant-{}-root".format(branch),
            (branch_atoms[0],), "benchmark-goal",
            causal_kind="procedural", success_probability=0.01,
            conductance=0.05, route_cost=20.0))
        for depth in range(1, branch_depth):
            graph.add_rule(PressureRule(
                "route-irrelevant-{}-{}".format(branch, depth),
                (branch_atoms[depth],), branch_atoms[depth - 1],
                causal_kind="procedural"))
    return graph, tuple(relevant), tuple(irrelevant)


def _exhaustive_expansions(graph, target_atom_id, max_hops):
    frontier = (str(target_atom_id),)
    expansions = 0
    for _ in range(int(max_hops)):
        following = []
        for conclusion_id in frontier:
            for rule in graph.rules_for(conclusion_id):
                expansions += len(rule.premise_ids)
                following.extend(rule.premise_ids)
        frontier = tuple(following)
        if not frontier:
            break
    return expansions


def run_pressure_concentration_benchmark(
        irrelevant_branches=256, branch_depth=4, max_routes=32):
    if int(irrelevant_branches) < int(max_routes):
        raise ValueError(
            "irrelevant branches must be at least the pressure route beam")
    if int(branch_depth) < 2:
        raise ValueError("branch depth must be at least two")
    config = PressureConfig(
        max_hops=int(branch_depth),
        max_routes_per_conclusion=int(max_routes))
    graph, relevant, irrelevant = _synthetic_graph(
        int(irrelevant_branches), int(branch_depth))
    before = tuple(atom.to_dict() for atom in graph.atoms)
    goal = GoalState(
        "benchmark-focus", "benchmark-goal", 1.0,
        utility=1.0, urgency=1.0, commitment=1.0)
    result = PressureEngine(config).propagate(graph, (goal,))
    after = tuple(atom.to_dict() for atom in graph.atoms)
    dependencies = dict(dict(result.dependency_rows)["benchmark-focus"])
    relevant_mass = sum(dependencies.get(atom_id, 0.0)
                        for atom_id in relevant)
    irrelevant_mass = sum(dependencies.get(atom_id, 0.0)
                          for atom_id in irrelevant)
    total_mass = relevant_mass + irrelevant_mass
    concentration = relevant_mass / total_mass if total_mass else 0.0
    exhaustive = _exhaustive_expansions(
        graph, "benchmark-goal", branch_depth)
    pressure_expansions = len(result.traces)
    selected_root_routes = tuple(sorted(set(
        trace.rule_id for trace in result.traces
        if trace.conclusion_id == "benchmark-goal")))
    return PressureConcentrationResult(
        int(irrelevant_branches), int(branch_depth), exhaustive,
        pressure_expansions,
        float(exhaustive) / pressure_expansions,
        1.0 - float(pressure_expansions) / exhaustive,
        relevant_mass, irrelevant_mass, concentration,
        selected_root_routes,
        "route-relevant-root" in selected_root_routes,
        "route-relevant-root" in selected_root_routes,
        before == after, graph.artifact_hash, result.artifact_hash,
        config.to_dict())
