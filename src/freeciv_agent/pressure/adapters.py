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
        "population_recovery": "score",
        "population_recovery_move": "score",
        "production_defense": "survival",
        "tactical_attack": "survival",
        "tactical_move": "survival",
    }

    def __init__(self, config=None, conductance_state=None):
        self.config = config or PressureConfig()
        self.engine = PressureEngine(self.config)
        self.scheduler = PressureScheduler(self.config)
        self.conductance_state = conductance_state

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

    @staticmethod
    def _direct_completion_source(category, rows):
        """Identify a currently grounded, candidate-scoped goal completion.

        Category conductance is deliberately reusable across instrumental
        routes, but a failure at one exact settlement site or hut approach is
        not evidence against a newly legal direct completion at another
        grounding. The Impact planner separately suppresses unchanged failed
        actions and settlement sites before candidates reach this adapter.
        """
        if category == "city_founding" and any(
                candidate.action.get("action_type") == "unit_build_city"
                for candidate, _ in rows):
            return "authoritative:new-legal-settlement-site"
        if category == "hut_exploration" and any(
                bool((candidate.projection or {}).get(
                    "target_is_known_hut"))
                for candidate, _ in rows):
            return "authoritative:move-enters-packet-known-hut"
        return None

    @staticmethod
    def _wrapped_distance(left, right, width, height):
        if any(getattr(row, key, None) is None
               for row in (left, right) for key in ("x", "y")):
            return None
        dx = abs(int(left.x) - int(right.x))
        dy = abs(int(left.y) - int(right.y))
        if int(width or 0) > 0:
            dx %= int(width)
            dx = min(dx, int(width) - dx)
        if int(height or 0) > 0:
            dy %= int(height)
            dy = min(dy, int(height) - dy)
        return max(dx, dy)

    @classmethod
    def _relevant_visible_threats(cls, snapshot, radius):
        """Return only opponents grounded near an owned survival anchor."""
        enemies = tuple(
            getattr(snapshot, "visible_enemy_units", ()) or ())
        cities = tuple(getattr(snapshot, "cities", ()) or ())
        anchors = cities or tuple(getattr(snapshot, "units", ()) or ())
        if not enemies or not anchors:
            return ()
        width = getattr(snapshot, "map_width", 0)
        height = getattr(snapshot, "map_height", 0)
        relevant = []
        for enemy in enemies:
            distances = tuple(
                cls._wrapped_distance(enemy, anchor, width, height)
                for anchor in anchors)
            # Missing coordinates fail safe. Engine snapshots normally carry
            # them, while retaining this behavior protects partial consumers.
            if any(value is None for value in distances):
                relevant.append(enemy)
            elif min(distances) <= int(radius):
                relevant.append(enemy)
        return tuple(relevant)

    @classmethod
    def _grounded_goal_specs(
            cls, snapshot, candidates, expansion_city_target,
            survival_threat_radius):
        """Derive live goal truth from authoritative state and legal candidates.

        Candidate presence is admissible grounding here because candidates are
        created only from the current server-advertised legal-action set.  It
        does not establish that an action will succeed; it establishes that the
        corresponding unresolved deficit is currently actionable.
        """
        categories = set(str(candidate.category) for candidate in candidates)
        current_cities = len(getattr(snapshot, "cities", ()) or ())
        expansion_truth = min(
            1.0, float(current_cities) / max(
                1, int(expansion_city_target)))
        relevant_threats = cls._relevant_visible_threats(
            snapshot, survival_threat_radius)
        # A production_defense candidate is generated only when the
        # authoritative unit/city counts show missing defense coverage.
        # city_defense is different: it is a legal fortification opportunity
        # for a combat unit already occupying its city.  Treating that
        # opportunity as a deficit manufactures survival pressure and lets
        # routine fortification preempt score-bearing work in a safe state.
        defense_deficit = "production_defense" in categories
        survival_truth = (
            0.0 if relevant_threats or defense_deficit else 1.0)
        exploration_actionable = any(
            cls.goal_for_category(category) == "exploration"
            for category in categories)
        score_actionable = any(
            cls.goal_for_category(category) == "score"
            for category in categories)
        return {
            "survival": (
                survival_truth, 1.50, True,
                ("authoritative:grounded-production-defense-deficit"
                 if defense_deficit else
                 "authoritative:visible-enemy-within-city-threat-radius:{}".format(
                     int(survival_threat_radius))
                 if relevant_threats else
                 "authoritative:no-proximate-visible-threat-or-defense-deficit")),
            "expansion": (
                expansion_truth, 1.25, False,
                "authoritative:city-count-over-target"),
            "score": (
                0.0 if score_actionable else 1.0, 1.00, False,
                ("authoritative:grounded-score-action"
                 if score_actionable
                 else "authoritative:no-grounded-score-action")),
            "exploration": (
                0.0 if exploration_actionable else 1.0, 0.35, False,
                ("authoritative:grounded-exploration-action"
                 if exploration_actionable
                 else "authoritative:no-grounded-exploration-action")),
        }

    def rank(
            self, snapshot, candidates, expansion_city_target, horizon_turn,
            survival_threat_radius=3, _goal_specs_override=None):
        candidates = tuple(candidates)
        if not candidates:
            return (), None
        if (isinstance(survival_threat_radius, bool)
                or not 1 <= int(survival_threat_radius) <= 12):
            raise ValueError("survival threat radius must be in 1..12")
        graph = PressureGraph()
        goal_specs = (
            self._grounded_goal_specs(
                snapshot, candidates, expansion_city_target,
                survival_threat_radius)
            if _goal_specs_override is None
            else dict(_goal_specs_override))
        goals = []
        grouped = dict((key, {}) for key in goal_specs)
        candidate_by_operation = {}
        operation_by_candidate = {}
        operation_atom_by_candidate = {}
        # Operation IDs are utility ordered so operations sharing one category
        # pressure atom still select the best grounded action deterministically.
        # The caller normally supplies this order already, but the adapter must
        # not make correctness depend on caller enumeration.
        candidate_order = dict(
            (id(candidate), index)
            for index, candidate in enumerate(sorted(
                candidates, key=lambda row: (
                    -float(row.utility), str(row.category), row.action_key))))
        conductance_snapshot = (
            self.conductance_state.decision_snapshot()
            if self.conductance_state is not None else None)
        for name, (strength, utility, safety, grounding) in sorted(
                goal_specs.items()):
            atom_id = "pf-impact-goal:{}".format(name)
            graph.add_atom(
                AtomState(atom_id, TruthState(strength, 1.0, crisp=True),
                          expression={
                              "goal": name,
                              "grounding": grounding,
                              "strength": strength,
                          }),
                Resolvability(retain=0.1))
            urgency = (
                1.0 + 1.0 / max(
                    1, int(horizon_turn) - int(getattr(snapshot, "turn", 0)))
                if name == "score" else 1.0)
            goals.append(GoalState(
                "pf-impact:{}".format(name), atom_id, 1.0, utility,
                urgency, safety=safety, context=(grounding,)))
        for index, candidate in enumerate(candidates):
            goal_name = self.goal_for_category(candidate.category)
            atom_id = "pf-impact-candidate:{}".format(structural_hash({
                "action": candidate.action, "category": candidate.category,
            })[:20])
            graph.add_atom(
                AtomState(atom_id, TruthState(0.0, 1.0, crisp=True),
                          expression=candidate.to_dict()),
                Resolvability(act=1.0))
            grouped[goal_name].setdefault(
                str(candidate.category), []).append((candidate, atom_id))
        category_maximum_utility = dict(
            (category, max(
                max(0.0, float(candidate.utility))
                for candidate, _ in rows))
            for categories in grouped.values()
            for category, rows in categories.items())
        goal_maximum_utility = dict(
            (goal_name, max(
                (category_maximum_utility[category]
                 for category in categories),
                default=0.0))
            for goal_name, categories in grouped.items())
        decision_conductance = {}
        # Safety is lexicographic only when an authoritative survival deficit
        # is active and the current legal set contains a grounded survival
        # operation. Otherwise rejecting all non-safety work would leave no
        # actionable route for the cycle.
        safety_actionable = bool(grouped["survival"])
        safety_active = (
            float(goal_specs["survival"][0]) < 1.0 and safety_actionable)
        opportunity_ceiling = (
            goal_maximum_utility["survival"] if safety_active else
            max(goal_maximum_utility.values(), default=0.0))
        for goal_name in sorted(grouped):
            goal_utility_ceiling = max(
                goal_maximum_utility[goal_name], 1e-12)
            for category in sorted(grouped[goal_name]):
                rows = grouped[goal_name][category]
                category_utility = category_maximum_utility[category]
                category_atom_id = "pf-impact-category:{}".format(
                    structural_hash([goal_name, category])[:20])
                graph.add_atom(AtomState(
                    category_atom_id, TruthState(0.0, 1.0, crisp=True),
                    expression={"category": category, "goal": goal_name}),
                    # A category is actionable when at least one of its member
                    # operations is grounded in the legal-action set.
                    Resolvability(act=1.0))
                learned_conductance = (
                    self.conductance_state.value(category)
                    if self.conductance_state is not None else 1.0)
                direct_completion_source = self._direct_completion_source(
                    category, rows)
                # Contextual optimism must not override the planner's own
                # grounded preference for a more valuable operation serving
                # the same goal (for example, moving to a demonstrably better
                # settlement site). It only prevents stale cross-context
                # conductance from demoting the goal's current best action.
                if (direct_completion_source is not None
                        and category_utility
                        < goal_maximum_utility[goal_name]):
                    direct_completion_source = None
                optimistic_conductance = (
                    self.conductance_state.initial_conductance
                    if self.conductance_state is not None else 1.0)
                conductance = (
                    max(learned_conductance, optimistic_conductance)
                    if direct_completion_source is not None
                    else learned_conductance)
                decision_conductance[category] = {
                    "direct_completion_source": direct_completion_source,
                    "effective_conductance": float(conductance),
                    "learned_conductance": float(learned_conductance),
                    "optimistic_floor_applied": bool(
                        direct_completion_source is not None
                        and conductance > learned_conductance),
                }
                graph.add_rule(PressureRule(
                    "pf-impact-category-route:{}".format(category),
                    (category_atom_id,),
                    "pf-impact-goal:{}".format(goal_name),
                    causal_kind="procedural", conductance=conductance,
                    success_probability=(
                        category_utility / goal_utility_ceiling),
                    source={
                        "adapter": "grounded-impact-planner",
                        "category": category,
                        "conductance_state_hash": (
                            conductance_snapshot.get("state_hash")
                            if conductance_snapshot is not None else None),
                        "direct_completion_source": direct_completion_source,
                        "effective_conductance": float(conductance),
                        "grounded_category_utility": category_utility,
                        "grounded_goal_utility_ceiling": goal_utility_ceiling,
                        "learned_conductance": float(learned_conductance),
                    }))
                graph.add_rule(PressureRule(
                    "pf-impact-candidate-route:{}".format(category),
                    tuple(atom_id for _, atom_id in rows),
                    category_atom_id,
                    kind="or", causal_kind="procedural",
                    premise_weights=tuple(
                        max(0.0, float(candidate.utility))
                        for candidate, _ in rows),
                    source={
                        "adapter": "grounded-impact-planner",
                        "category": category,
                    }))
                for candidate, atom_id in rows:
                    operation_id = "pf-impact-op:{:08d}:{}".format(
                        candidate_order[id(candidate)],
                        structural_hash(candidate.action)[:20])
                    candidate_by_operation[operation_id] = candidate
                    operation_by_candidate[id(candidate)] = operation_id
                    # Candidate atoms retain the complete OR-route provenance,
                    # but cross-goal operation scoring happens at category
                    # level. Otherwise adding equivalent legal alternatives
                    # divides the category's pressure and can change the
                    # winning goal without changing state or best action.
                    operation_atom_by_candidate[id(candidate)] = category_atom_id
        result = self.engine.propagate(graph, tuple(goals))
        operations = []
        for operation_id, candidate in sorted(candidate_by_operation.items()):
            goal_name = self.goal_for_category(candidate.category)
            # The Impact planner's utility is a grounded cross-category action
            # value. Its loss relative to the best currently actionable goal
            # is therefore an opportunity cost, not another truth or pressure
            # input. All operations for one goal share the cost so category
            # cardinality and within-goal conductance learning remain intact.
            opportunity_cost = max(
                0.0,
                opportunity_ceiling - goal_maximum_utility[goal_name])
            operations.append(Operation(
                operation_id, operation_atom_by_candidate[id(candidate)],
                "act", CostVector(
                    compute=1.0, opportunity=opportunity_cost),
                causal_kind="procedural",
                safety_compatible=(
                    not safety_active or goal_name == "survival"),
                payload=candidate.to_dict()))
        scores = self.scheduler.score_all(operations, result)
        rank = dict((row.operation_id, index) for index, row in enumerate(scores)
                    if row.admissible)
        ordered = tuple(sorted(candidates, key=lambda candidate: (
            rank.get(operation_by_candidate[id(candidate)], len(rank)),
            -candidate.utility, candidate.category, candidate.action_key)))
        if conductance_snapshot is not None:
            # The persisted state hash continues to identify only learned
            # feedback. This decision-scoped projection records when a new
            # direct grounding used its optimistic prior instead.
            conductance_snapshot["decision_routes"] = dict(
                (category, decision_conductance[category])
                for category in sorted(decision_conductance))
        artifact = {
            "conductance_state": (
                conductance_snapshot),
            "pressure": result.to_dict(),
            "schedule": self.scheduler.decision_artifact(operations, result),
        }
        return ordered, artifact

    def record_category_outcome(
            self, category, effect_observed, feedback_id,
            realized_relief=None, relief_source=None,
            caused_by_feedback_id=None):
        if self.conductance_state is None:
            return None
        if realized_relief is None:
            return self.conductance_state.feedback(
                category, effect_observed, feedback_id)
        return self.conductance_state.feedback(
            category, effect_observed, feedback_id,
            realized_relief=realized_relief,
            relief_source=relief_source,
            caused_by_feedback_id=caused_by_feedback_id)

    def record_outcome(
            self, candidate, effect_observed, feedback_id,
            realized_relief=None, relief_source=None):
        return self.record_category_outcome(
            candidate.category, effect_observed, feedback_id,
            realized_relief, relief_source)
