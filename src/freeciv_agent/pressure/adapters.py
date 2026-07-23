"""Adapters from existing FreeCiv proof and impact artifacts into PF-PLN."""

from dataclasses import dataclass

from ..events.schema import structural_hash
from .engine import PressureEngine, PressureGraph
from .model import (
    AtomState,
    CostVector,
    GoalState,
    Operation,
    PressureConfig,
    PressureRule,
    Resolvability,
    TruthState,
)
from .scheduler import PressureScheduler


PROCEDURAL_PREDICATES = frozenset((
    "buildable", "has-building", "has-tech", "researchable",
    "usable-action",
))


def _node_atom_id(node_id):
    return "pf-proof-node:{}".format(node_id)


def _truth(node):
    value = node.get("tv") or node.get("atom", {}).get("tv") or {}
    provenance = node.get("atom", {}).get("provenance_ids", ())
    return TruthState(
        float(value.get("strength", 0.0)),
        float(value.get("confidence", 0.0)),
        tuple(sorted(set(provenance))),
        bool(node.get("crisp", node.get("atom", {}).get("crisp", False))))


def _resolvability(node):
    if node.get("satisfied"):
        return Resolvability(retain=0.5)
    kind = node.get("kind")
    predicate = str(node.get("atom", {}).get("predicate", ""))
    if kind in ("cycle", "unreachable"):
        return Resolvability(expand=1.0, infer=0.1)
    if kind == "grounded":
        return Resolvability(observe=1.0, infer=0.2)
    if not node.get("crisp", True):
        return Resolvability(infer=0.4, observe=1.0, retain=0.2)
    if predicate in PROCEDURAL_PREDICATES:
        return Resolvability(infer=0.2, act=1.0, retain=0.1)
    return Resolvability(infer=0.8, expand=0.2, retain=0.1)


@dataclass(frozen=True)
class ProofPressureContext:
    graph: PressureGraph
    goal: GoalState
    node_atom_ids: tuple


def proof_pressure_context(query_result, utility=1.0, urgency=1.0,
                           commitment=1.0, target_strength=1.0, safety=False):
    """Convert a lossless proof DAG without changing its epistemic content."""
    proof = query_result.proof
    nodes = dict((node["node_id"], node) for node in proof["nodes"])
    graph = PressureGraph()
    mapping = []
    for node_id in sorted(nodes):
        node = nodes[node_id]
        atom_id = _node_atom_id(node_id)
        mapping.append((node_id, atom_id))
        graph.add_atom(AtomState(
            atom_id, _truth(node), expression=node.get("atom"),
            context=tuple(sorted((node.get("scope") or {}).items())),
            lifecycle=("achieved" if node.get("satisfied") else "blocked")),
            _resolvability(node))
    for node_id in sorted(nodes):
        node = nodes[node_id]
        children = tuple(node.get("premise_node_refs", ()))
        if not children:
            continue
        predicate = str(node.get("atom", {}).get("predicate", ""))
        kind = node.get("kind") if node.get("kind") in ("and", "or") else "dependency"
        graph.add_rule(PressureRule(
            "pf-proof-rule:{}".format(node_id),
            tuple(_node_atom_id(child) for child in children),
            _node_atom_id(node_id),
            kind=kind,
            causal_kind=("procedural" if predicate in PROCEDURAL_PREDICATES
                         else "definitional"),
            conductance=float(_truth(node).confidence),
            residual=(0.0 if node.get("satisfied") else 1.0),
            source={
                "proof_hash": proof["structural_hash"],
                "rule_applied": node.get("rule_applied"),
                "subtree_hash": node.get("subtree_hash"),
            }))
    root_atom_id = _node_atom_id(proof["root_node_id"])
    goal = GoalState(
        "pf-goal:{}".format(getattr(query_result.goal, "goal_id", root_atom_id)),
        root_atom_id, target_strength, utility, urgency, commitment,
        safety=safety)
    return ProofPressureContext(graph, goal, tuple(mapping))


class ProofPressureAdapter(object):
    """Produces an inspectable pressure frontier from an existing oracle result."""

    def __init__(self, config=None):
        self.config = config or PressureConfig()
        self.engine = PressureEngine(self.config)
        self.scheduler = PressureScheduler(self.config)

    def evaluate(self, query_result, utility=1.0, urgency=1.0,
                 commitment=1.0, safety=False):
        context = proof_pressure_context(
            query_result, utility, urgency, commitment, safety=safety)
        return context, self.engine.propagate(context.graph, (context.goal,))

    def frontier_operations(self, context, pressure_result):
        operations = []
        for node_id, atom_id in context.node_atom_ids:
            atom = context.graph.atom(atom_id)
            resolvability = context.graph.resolvability(atom_id)
            if atom.lifecycle == "achieved":
                continue
            candidates = [
                (channel, resolvability.value(channel))
                for channel in ("act", "observe", "infer", "expand")
                if resolvability.value(channel) > 0
            ]
            if not candidates:
                continue
            mode = max(candidates, key=lambda row: (
                pressure_result.pressure(
                    context.goal.goal_id, atom_id).value(row[0]),
                row[1], row[0]))[0]
            causal_kind = "procedural" if mode == "act" else "diagnostic"
            operations.append(Operation(
                "pf-proof-op:{}".format(node_id), atom_id, mode,
                CostVector(compute=1.0), causal_kind=causal_kind,
                payload={"proof_node_id": node_id}))
        return tuple(operations)

    def decision_artifact(self, query_result, utility=1.0, urgency=1.0,
                          commitment=1.0, safety=False):
        context, result = self.evaluate(
            query_result, utility, urgency, commitment, safety)
        operations = self.frontier_operations(context, result)
        return {
            "graph_hash": context.graph.artifact_hash,
            "pressure": result.to_dict(),
            "schedule": self.scheduler.decision_artifact(
                operations, result) if operations else None,
        }


class ImpactPressureRanker(object):
    """Goal-indexed pressure ranking for grounded legal ImpactCandidate values."""

    CATEGORY_GOALS = {
        "city_defense": "survival",
        "city_founding": "expansion",
        "expansion_move": "expansion",
        "hut_exploration": "exploration",
        "population_recovery": "expansion",
        "population_recovery_move": "expansion",
        "tactical_attack": "survival",
        "tactical_move": "survival",
    }

    def __init__(self, config=None):
        self.config = config or PressureConfig()
        self.engine = PressureEngine(self.config)
        self.scheduler = PressureScheduler(self.config)

    @classmethod
    def goal_for_category(cls, category):
        category = str(category)
        if category in cls.CATEGORY_GOALS:
            return cls.CATEGORY_GOALS[category]
        if "expansion" in category or "founder" in category:
            return "expansion"
        if "explor" in category:
            return "exploration"
        if "production" in category or "economy" in category:
            return "score"
        return "score"

    def rank(self, snapshot, candidates, expansion_city_target, horizon_turn):
        candidates = tuple(candidates)
        if not candidates:
            return (), None
        graph = PressureGraph()
        current_cities = len(getattr(snapshot, "cities", ()))
        expansion_truth = min(
            1.0, float(current_cities) / max(1, int(expansion_city_target)))
        goal_specs = {
            "survival": (0.0, 1.50, True),
            "expansion": (expansion_truth, 1.25, False),
            "score": (0.0, 1.00, False),
            "exploration": (0.0, 0.35, False),
        }
        goals = []
        grouped = dict((key, []) for key in goal_specs)
        candidate_by_operation = {}
        for name, (strength, utility, safety) in sorted(goal_specs.items()):
            atom_id = "pf-impact-goal:{}".format(name)
            graph.add_atom(
                AtomState(atom_id, TruthState(strength, 1.0, crisp=True),
                          expression={"goal": name}),
                Resolvability(retain=0.1))
            urgency = (
                1.0 + 1.0 / max(
                    1, int(horizon_turn) - int(getattr(snapshot, "turn", 0)))
                if name == "score" else 1.0)
            goals.append(GoalState(
                "pf-impact:{}".format(name), atom_id, 1.0, utility,
                urgency, safety=safety))
        for index, candidate in enumerate(candidates):
            goal_name = self.goal_for_category(candidate.category)
            atom_id = "pf-impact-candidate:{}".format(structural_hash({
                "action": candidate.action, "category": candidate.category,
            })[:20])
            graph.add_atom(
                AtomState(atom_id, TruthState(0.0, 1.0, crisp=True),
                          expression=candidate.to_dict()),
                Resolvability(act=1.0))
            grouped[goal_name].append((candidate, atom_id))
        for goal_name in sorted(grouped):
            rows = grouped[goal_name]
            if not rows:
                continue
            graph.add_rule(PressureRule(
                "pf-impact-route:{}".format(goal_name),
                tuple(atom_id for _, atom_id in rows),
                "pf-impact-goal:{}".format(goal_name),
                kind="or", causal_kind="procedural",
                premise_weights=tuple(
                    max(0.0, float(candidate.utility)) for candidate, _ in rows),
                source={"adapter": "grounded-impact-planner"}))
            for candidate, atom_id in rows:
                operation_id = "pf-impact-op:{}".format(
                    structural_hash(candidate.action)[:20])
                candidate_by_operation[operation_id] = candidate
        result = self.engine.propagate(graph, tuple(goals))
        operations = []
        for operation_id, candidate in sorted(candidate_by_operation.items()):
            atom_id = next(
                atom.atom_id for atom in graph.atoms
                if atom.expression == candidate.to_dict())
            operations.append(Operation(
                operation_id, atom_id, "act", CostVector(compute=1.0),
                causal_kind="procedural", payload=candidate.to_dict()))
        scores = self.scheduler.score_all(operations, result)
        rank = dict((row.operation_id, index) for index, row in enumerate(scores)
                    if row.admissible)
        ordered = tuple(sorted(candidates, key=lambda candidate: (
            rank.get(
                "pf-impact-op:{}".format(
                    structural_hash(candidate.action)[:20]), len(rank)),
            -candidate.utility, candidate.category, candidate.action_key)))
        artifact = {
            "pressure": result.to_dict(),
            "schedule": self.scheduler.decision_artifact(operations, result),
        }
        return ordered, artifact
