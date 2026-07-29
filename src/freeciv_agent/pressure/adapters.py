"""Adapters from existing FreeCiv proof and impact artifacts into PF-PLN."""

import time
from dataclasses import dataclass, replace
from types import SimpleNamespace

from ..events.schema import structural_hash
from .engine import (
    PressureEngine,
    PressureEngineV2,
    PressureGraph,
    PressureV2Policy,
)
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
from .time import DeadlineState, evaluate_deadline


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


class ProofPressureAdapterV2(ProofPressureAdapter):
    """Opt-in proof adapter for achievement/uncertainty split semantics."""

    def __init__(self, config=None, policy=None):
        super().__init__(config=config)
        self.policy = policy or PressureV2Policy()
        self.engine = PressureEngineV2(
            self.config, policy=self.policy)


class ImpactPressureRanker(object):
    """Goal-indexed pressure ranking for grounded legal ImpactCandidate values."""

    CATEGORY_GOALS = {
        "city_defense": "survival",
        "city_food_governor": "food_sustainability",
        "city_happiness_governor": "survival",
        "city_founding": "expansion",
        "city_garrison_move": "survival",
        "disorder_luxury_restore": "score",
        "disorder_luxury_shift": "survival",
        "disorder_luxury_unwind": "survival",
        "expansion_move": "expansion",
        "food_support_disband": "food_sustainability",
        "food_support_rehome": "food_sustainability",
        "government_recovery": "governance",
        "government_transition": "governance",
        "hut_exploration": "exploration",
        "population_recovery": "score",
        "population_recovery_move": "score",
        "production_defense": "survival",
        "production_coastal_defense": "survival",
        "production_fleet_readiness": "score",
        "production_founder_attrition_recovery": "survival",
        "production_food_stabilization": "food_sustainability",
        "production_happiness_recovery": "survival",
        "production_industrialization": "score",
        "production_land_capability": "survival",
        "production_modernization": "score",
        "production_threat_modernization": "survival",
        "production_naval_response": "survival",
        "production_research_infrastructure": "research_sustainability",
        "production_continuity": "production_continuity",
        "production_commerce_infrastructure": "treasury_sustainability",
        "production_treasury_stabilization": "treasury_sustainability",
        "tactical_attack": "survival",
        "tactical_move": "survival",
        "treasury_support_disband": "treasury_sustainability",
        "treasury_tax_restore": "score",
        "treasury_tax_shift": "treasury_sustainability",
    }

    def __init__(
            self, config=None, conductance_state=None, score_alignment=False,
            exploration_information_enabled=True,
            score_alignment_utility_tolerance=0.0):
        self.config = config or PressureConfig()
        self.engine = PressureEngine(self.config)
        self.scheduler = PressureScheduler(self.config)
        self.conductance_state = conductance_state
        if not isinstance(score_alignment, bool):
            raise TypeError("score alignment must be boolean")
        if not isinstance(exploration_information_enabled, bool):
            raise TypeError("exploration information setting must be boolean")
        if (isinstance(score_alignment_utility_tolerance, bool)
                or not isinstance(
                    score_alignment_utility_tolerance, (int, float))
                or not 0.0 <= float(
                    score_alignment_utility_tolerance) <= 0.25):
            raise ValueError(
                "score alignment utility tolerance must be in 0..0.25")
        self.score_alignment = score_alignment
        self.exploration_information_enabled = (
            exploration_information_enabled)
        self.score_alignment_utility_tolerance = float(
            score_alignment_utility_tolerance)

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
    def _safety_candidate_relevant(
            cls, snapshot, candidate, relevant_threats, defense_deficit,
            survival_threat_radius):
        """Bind safety compatibility to the threat that activated safety."""
        category = str(candidate.category)
        if category in (
                "production_defense", "production_land_capability",
                "city_garrison_move"):
            return bool(defense_deficit)
        if category in (
                "production_naval_response", "production_coastal_defense"):
            # These candidates exist only while the planner's bounded,
            # packet-visible naval-threat memory is active.
            return True
        if category == "production_happiness_recovery":
            # This candidate exists only while an authoritative disordered
            # city has a packet-buildable local happiness exit and the bounded
            # national luxury bridge is active.
            return True
        if category == "disorder_luxury_unwind":
            # Returning an active or expired emergency bridge to ordinary
            # rates is part of completing that bounded survival lifecycle.
            return True
        if category == "production_threat_modernization":
            projection = candidate.projection or {}
            return bool(
                relevant_threats
                and float(projection.get(
                    "visible_enemy_domain_power", 0.0))
                > float(projection.get("current_domain_power", 0.0)))
        if category == "city_defense" and defense_deficit:
            return True
        if category not in (
                "city_defense", "tactical_attack", "tactical_move"):
            return False
        if not relevant_threats:
            return False
        action = candidate.action
        target = action.get("target")
        target = target if isinstance(target, dict) else {}
        actor_id = action.get("actor_id")
        actor = (
            snapshot.unit(actor_id)
            if actor_id is not None and hasattr(snapshot, "unit")
            else next((
                unit for unit in tuple(
                    getattr(snapshot, "units", ()) or ())
                if getattr(unit, "unit_id", None) == actor_id), None))
        if category == "city_defense":
            if actor is None:
                return False
            width = getattr(snapshot, "map_width", 0)
            height = getattr(snapshot, "map_height", 0)
            distances = tuple(
                cls._wrapped_distance(actor, enemy, width, height)
                for enemy in relevant_threats)
            return (
                bool(distances)
                and not any(value is None for value in distances)
                and min(distances) <= int(survival_threat_radius))
        if category == "tactical_attack":
            target_unit_id = target.get("target_unit_id")
            if target_unit_id is not None:
                return any(
                    getattr(enemy, "unit_id", None) == target_unit_id
                    for enemy in relevant_threats)
            target_xy = (target.get("x"), target.get("y"))
            return target_xy != (None, None) and any(
                (getattr(enemy, "x", None), getattr(enemy, "y", None))
                == target_xy for enemy in relevant_threats)

        destination = (target.get("x"), target.get("y"))
        if (actor is None or destination == (None, None)
                or getattr(actor, "x", None) is None
                or getattr(actor, "y", None) is None):
            return False
        width = getattr(snapshot, "map_width", 0)
        height = getattr(snapshot, "map_height", 0)
        current_distances = tuple(
            cls._wrapped_distance(actor, enemy, width, height)
            for enemy in relevant_threats)
        projected = SimpleNamespace(x=destination[0], y=destination[1])
        projected_distances = tuple(
            cls._wrapped_distance(projected, enemy, width, height)
            for enemy in relevant_threats)
        if (any(value is None for value in current_distances)
                or any(value is None for value in projected_distances)):
            return False
        return min(projected_distances) < min(current_distances)

    @classmethod
    def _grounded_goal_specs(
            cls, snapshot, candidates, expansion_city_target,
            survival_threat_radius, score_alignment=False,
            exploration_information_enabled=True, goal_facts=None):
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
        goal_facts = dict(goal_facts or {})
        defense_city_ids = tuple(
            goal_facts.get("defense_deficit_city_ids", ()))
        defense_deficit = bool(
            defense_city_ids
            if "defense_deficit_city_ids" in goal_facts
            else "production_defense" in categories)
        disorder_city_ids = tuple(
            goal_facts.get("disorder_city_ids", ()))
        recent_naval_threat = bool(
            goal_facts.get("recent_naval_threat", False))
        survival_truth = (
            0.0 if relevant_threats or defense_deficit
            or disorder_city_ids or recent_naval_threat else 1.0)
        food_city_ids = tuple(goal_facts.get("food_deficit_city_ids", ()))
        food_truth = float(goal_facts.get(
            "food_safe_fraction", 1.0 if not food_city_ids else 0.0))
        food_truth = min(1.0, max(0.0, food_truth))
        treasury_deficit = bool(goal_facts.get("treasury_deficit", False))
        treasury_structural_deficit = bool(
            goal_facts.get("treasury_structural_deficit", False))
        research_deficit = bool(goal_facts.get("research_deficit", False))
        research_stalled_turns = int(
            goal_facts.get("research_stalled_turns", 0) or 0)
        production_continuity_city_ids = tuple(
            goal_facts.get("production_continuity_city_ids", ()))
        production_continuity_releasable_city_ids = tuple(
            goal_facts.get(
                "production_continuity_releasable_city_ids", ()))
        production_continuity_blocked_city_ids = tuple(
            goal_facts.get(
                "production_continuity_blocked_city_ids", ()))
        production_continuity_deficit = bool(
            goal_facts.get(
                "production_continuity_deficit",
                production_continuity_city_ids))
        city_loss_recovery = bool(
            goal_facts.get("city_loss_recovery", False))
        if current_cities < int(expansion_city_target):
            expansion_grounding = (
                "authoritative:owned-city-loss-recovery:{}-of-{}".format(
                    current_cities,
                    int(goal_facts.get(
                        "city_loss_recovery_target",
                        expansion_city_target)))
                if city_loss_recovery else
                "authoritative:city-count-below-target:{}-of-{}".format(
                    current_cities, int(expansion_city_target)))
        else:
            expansion_grounding = (
                "authoritative:city-count-at-or-above-target")
        government_recovery = next((
            candidate for candidate in candidates
            if candidate.category == "government_recovery"), None)
        government_transition = next((
            candidate for candidate in candidates
            if candidate.category == "government_transition"), None)
        governance_candidate = (
            government_recovery or government_transition)
        governance_target = (
            (governance_candidate.projection or {}).get("target_government")
            if governance_candidate is not None else None)
        exploration_categories = tuple(
            candidate for candidate in candidates
            if cls.goal_for_category(candidate.category) == "exploration")
        exploration_actionable = bool(exploration_categories)
        known_hut_actionable = any(
            candidate.category == "hut_exploration"
            for candidate in exploration_categories)
        if (score_alignment and exploration_actionable
                and not exploration_information_enabled
                and not known_hut_actionable):
            exploration_truth = 1.0
            exploration_grounding = (
                "authoritative:no-information-gain-and-no-known-hut")
        else:
            exploration_truth = 0.0 if exploration_actionable else 1.0
            exploration_grounding = (
                "authoritative:grounded-known-hut-action"
                if known_hut_actionable else
                "authoritative:grounded-exploration-action"
                if exploration_actionable else
                "authoritative:no-grounded-exploration-action")
        score_actionable = any(
            (cls._guaranteed_horizon_score(candidate) > 0.0
             if score_alignment else
             cls.goal_for_category(candidate.category) == "score")
            for candidate in candidates)
        score_gap = goal_facts.get("score_gap_to_leader")
        score_deficit = bool(
            score_gap is not None and float(score_gap) < 0.0)
        return {
            "survival": (
                survival_truth, 1.50, True,
                ("authoritative:city-disorder-deficit:{}".format(
                    ",".join(str(value) for value in disorder_city_ids))
                 if disorder_city_ids else
                 "authoritative:grounded-production-defense-deficit"
                 if defense_deficit else
                 "authoritative:bounded-packet-visible-naval-threat-memory"
                 if recent_naval_threat else
                 "authoritative:visible-enemy-within-city-threat-radius:{}".format(
                     int(survival_threat_radius))
                 if relevant_threats else
                 "authoritative:no-proximate-visible-threat-or-defense-deficit")),
            "food_sustainability": (
                food_truth, 1.75, True,
                ("authoritative:city-food-surplus-reserve-deficit:{}".format(
                    ",".join(str(value) for value in food_city_ids))
                 if food_city_ids else
                 "authoritative:all-city-food-reserves-safe")),
            "treasury_sustainability": (
                0.0 if treasury_deficit else 1.0, 1.65, True,
                ("authoritative:expired-coinage-masks-negative-operating-gold"
                 ":operating={}:effective={}".format(
                     goal_facts.get("treasury_operating_gold_per_turn"),
                     goal_facts.get("treasury_net_gold_per_turn"))
                 if treasury_structural_deficit else
                 "authoritative:net-gold-or-turn-start-upkeep-reserve-deficit"
                 if treasury_deficit else
                 "authoritative:net-gold-and-turn-start-upkeep-reserve-safe")),
            "research_sustainability": (
                0.0 if research_deficit else 1.0, 1.55, False,
                ("authoritative:material-research-throughput-deficit"
                 ":gross={}:upkeep={}:net={}:stalled={}".format(
                     goal_facts.get("research_gross_beakers_per_turn"),
                     goal_facts.get("research_tech_upkeep"),
                     goal_facts.get("research_net_beakers_per_turn"),
                     research_stalled_turns)
                 if research_deficit else
                 "authoritative:positive-net-research")),
            "production_continuity": (
                0.0 if production_continuity_deficit else 1.0,
                1.25, False,
                ("authoritative:expired-coinage-bridge-cities:{}"
                 ":releasable={}:treasury-blocked={}".format(
                     ",".join(str(value)
                              for value in production_continuity_city_ids),
                     ",".join(str(value) for value
                              in production_continuity_releasable_city_ids),
                     ",".join(str(value) for value
                              in production_continuity_blocked_city_ids))
                 if production_continuity_deficit else
                 "authoritative:no-expired-coinage-bridge")),
            "governance": (
                0.0 if governance_candidate is not None else 1.0,
                2.00 if government_recovery is not None else 1.35,
                government_recovery is not None,
                ("authoritative:post-revolution-government-selection-required"
                 if government_recovery is not None else
                 "authoritative:packet-legal-preferred-government:{}".format(
                     governance_target)
                 if government_transition is not None else
                 "authoritative:no-grounded-government-action")),
            "expansion": (
                expansion_truth,
                1.60 if city_loss_recovery else 1.25,
                False, expansion_grounding),
            "score": (
                0.0 if score_actionable or score_deficit else 1.0,
                min(1.75, 1.00 + abs(float(score_gap or 0)) / 100.0),
                False,
                ("authoritative:score-gap-to-leader:{}".format(score_gap)
                 if score_deficit else
                 "authoritative:grounded-guaranteed-horizon-score-action"
                 if score_alignment and score_actionable
                 else "authoritative:grounded-score-action"
                 if score_actionable
                 else "authoritative:no-grounded-score-action")),
            "exploration": (
                exploration_truth, 0.35, False, exploration_grounding),
        }

    @staticmethod
    def _guaranteed_horizon_score(candidate):
        """Return only score progress grounded to complete by the horizon.

        Projected growth, science, or settlement value remains useful to the
        canonical Impact utility, but it is not strong enough to authorize PF
        to override that utility.  The pressure guard accepts only an immediate
        score-bearing completion or a ruleset-grounded guaranteed unit score.
        """
        projection = candidate.projection or {}
        if candidate.category == "city_founding":
            return 1.0
        if candidate.category == "population_recovery":
            return max(
                0.0, float(projection.get("recovered_population", 0.0)))
        guaranteed = max(
            0.0,
            float(projection.get(
                "guaranteed_unit_score_points", 0.0)),
            float(projection.get(
                "batch_guaranteed_unit_score_points", 0.0)))
        if not guaranteed:
            return 0.0
        remaining = projection.get("remaining_turns")
        eta = projection.get(
            "repeat_completion_eta_turns",
            projection.get("completion_eta_turns"))
        if (remaining is not None and eta is not None
                and float(eta) > float(remaining)):
            return 0.0
        if projection.get("repurpose_target_completes_by_horizon") is False:
            return 0.0
        return guaranteed

    @staticmethod
    def _deadline_fit(candidate):
        """Reject only projections explicitly completing after the horizon."""
        projection = candidate.projection or {}
        remaining = projection.get("remaining_turns")
        eta = projection.get(
            "settlement_eta_turns",
            projection.get(
                "preexpansion_sequence_settlement_eta_turns",
                projection.get(
                    "repeat_completion_eta_turns",
                    projection.get("completion_eta_turns"))))
        if projection.get("repurpose_target_completes_by_horizon") is False:
            return 0.0
        if (remaining is not None and eta is not None
                and float(eta) > float(remaining)):
            return 0.0
        return 1.0

    @staticmethod
    def _deadline_estimate(candidate):
        """Return a structured v2 estimate without changing v1 ranking."""
        projection = candidate.projection or {}
        remaining = projection.get("remaining_turns")
        eta = projection.get(
            "settlement_eta_turns",
            projection.get(
                "preexpansion_sequence_settlement_eta_turns",
                projection.get(
                    "repeat_completion_eta_turns",
                    projection.get("completion_eta_turns"))))
        completes = projection.get(
            "repurpose_target_completes_by_horizon")
        expected = None if eta is None else float(eta)
        deadline = None if remaining is None else int(remaining)
        if completes is False and deadline is not None:
            expected = max(
                float(deadline) + 1.0,
                expected if expected is not None else 0.0)
        state = DeadlineState(
            current_turn=0,
            deadline_turn=deadline,
            expected_completion_turn=expected,
            completion_variance=float(
                projection.get("completion_variance", 0.0) or 0.0))
        return evaluate_deadline(
            state, hard_horizon_turn=deadline)

    def _goal_risk_profile(self, name, safety):
        """Compatibility hook; scalar-v1 has no distributional profile."""
        return None

    def _operation_semantics(self, candidate, goal_id):
        """Compatibility hook for v2 risk, deadline, and packet metadata."""
        return {}

    def _teleological_operations(
            self, snapshot, operations, candidate_by_operation,
            pressure_result, horizon_turn):
        """Compatibility hook; scalar-v1 remains byte-exact."""
        del (
            snapshot, candidate_by_operation,
            pressure_result, horizon_turn)
        return tuple(operations), None

    @classmethod
    def _score_aligned_scores(
            cls, scores, candidate_by_operation, safety_active,
            utility_tolerance=0.0):
        """Bound utility regret while respecting heuristic uncertainty."""
        scores = tuple(scores)
        eligible_operations = frozenset(
            row.operation_id for row in scores if row.admissible)
        if not eligible_operations:
            return scores
        deadline_candidates = tuple(
            row for row in candidate_by_operation.items()
            if (row[0] in eligible_operations
                and cls._deadline_fit(row[1]) > 0.0))
        if not deadline_candidates:
            return scores
        canonical = min(
            deadline_candidates,
            key=lambda row: (
                -float(row[1].utility), str(row[1].category),
                row[1].action_key, row[0]))
        canonical_candidate = canonical[1]
        canonical_score = cls._guaranteed_horizon_score(
            canonical_candidate)
        utility_floor = (
            float(canonical_candidate.utility)
            - abs(float(canonical_candidate.utility))
            * float(utility_tolerance))
        guarded = []
        for row in scores:
            candidate = candidate_by_operation[row.operation_id]
            score_gain = (
                not safety_active
                and cls._guaranteed_horizon_score(candidate)
                > canonical_score)
            utility_preserved = (
                float(candidate.utility)
                >= utility_floor)
            deadline_fit = cls._deadline_fit(candidate) > 0.0
            if (row.admissible and deadline_fit
                    and not utility_preserved and not score_gain):
                guarded.append(replace(
                    row, admissible=False,
                    reason="score_alignment_guard", priority=0.0))
            elif row.admissible and not deadline_fit:
                guarded.append(replace(
                    row, admissible=False,
                    reason="score_alignment_deadline", priority=0.0))
            else:
                guarded.append(row)
        return tuple(sorted(guarded, key=lambda row: (
            not row.admissible, -row.priority, row.operation_id)))

    def rank(
            self, snapshot, candidates, expansion_city_target, horizon_turn,
            survival_threat_radius=3, _goal_specs_override=None,
            diagnostics=None, _conservative_safety_replay=False,
            _goal_facts=None):
        candidates = tuple(candidates)
        if (isinstance(survival_threat_radius, bool)
                or not 1 <= int(survival_threat_radius) <= 12):
            raise ValueError("survival threat radius must be in 1..12")
        graph_started = time.perf_counter()
        graph = PressureGraph()
        goal_specs = (
            self._grounded_goal_specs(
                snapshot, candidates, expansion_city_target,
                survival_threat_radius,
                score_alignment=self.score_alignment,
                exploration_information_enabled=(
                    self.exploration_information_enabled),
                goal_facts=_goal_facts)
            if _goal_specs_override is None
            else dict(_goal_specs_override))
        relevant_threats = self._relevant_visible_threats(
            snapshot, survival_threat_radius)
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
                urgency, safety=safety, context=(grounding,),
                risk_profile=self._goal_risk_profile(name, safety)))
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
        category_guaranteed_score = dict(
            (category, max(
                self._guaranteed_horizon_score(candidate)
                for candidate, _ in rows))
            for categories in grouped.values()
            for category, rows in categories.items())
        category_deadline_fit = dict(
            (category, max(
                self._deadline_fit(candidate)
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
        defense_deficit = bool(
            tuple((_goal_facts or {}).get(
                "defense_deficit_city_ids", ()))
            if _goal_facts is not None else any(
                candidate.category == "production_defense"
                for candidate in candidates))
        active_safety_goals = frozenset(
            name for name, (strength, _, safety, _) in goal_specs.items()
            if safety and float(strength) < 1.0)

        def safety_candidate_relevant(candidate):
            goal_name = self.goal_for_category(candidate.category)
            if goal_name not in active_safety_goals:
                return False
            if goal_name != "survival":
                return True
            return bool(
                _conservative_safety_replay
                or self._safety_candidate_relevant(
                    snapshot, candidate, relevant_threats,
                    defense_deficit, survival_threat_radius))

        aligned_safety_candidates = tuple(
            candidate for candidate in candidates
            if safety_candidate_relevant(candidate))
        safety_actionable = bool(
            aligned_safety_candidates
            if self.score_alignment else tuple(
                candidate for candidate in candidates
                if self.goal_for_category(candidate.category)
                in active_safety_goals))
        safety_active = bool(active_safety_goals and safety_actionable)
        opportunity_ceiling = (
            max((
                goal_maximum_utility[name]
                for name in active_safety_goals), default=0.0)
            if safety_active else
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
        if diagnostics is not None:
            diagnostics["pressure_graph_latency_ms"] = (
                diagnostics.get("pressure_graph_latency_ms", 0.0)
                + (time.perf_counter() - graph_started) * 1000.0)
        propagation_started = time.perf_counter()
        result = self.engine.propagate(graph, tuple(goals))
        if diagnostics is not None:
            diagnostics["pressure_propagation_latency_ms"] = (
                diagnostics.get("pressure_propagation_latency_ms", 0.0)
                + (time.perf_counter() - propagation_started) * 1000.0)
        operation_started = time.perf_counter()
        operations = []
        for operation_id, candidate in sorted(candidate_by_operation.items()):
            goal_name = self.goal_for_category(candidate.category)
            # The Impact planner's utility is a grounded cross-category action
            # value. Its loss relative to the best currently actionable goal
            # is therefore an opportunity cost, not another truth or pressure
            # input. Legacy semantics share the cost across one goal. The
            # score-aligned policy uses the best value in each category, which
            # preserves category cardinality invariance while preventing a
            # weak same-goal category from borrowing a stronger one's value.
            # No opportunity cost is asserted inside the declared uncertainty
            # band because those heuristic utilities are operationally tied.
            opportunity_cost = max(
                0.0,
                (
                    opportunity_ceiling
                    - abs(opportunity_ceiling)
                    * self.score_alignment_utility_tolerance
                    - category_maximum_utility[candidate.category])
                if self.score_alignment else
                opportunity_ceiling - goal_maximum_utility[goal_name])
            operations.append(Operation(
                operation_id, operation_atom_by_candidate[id(candidate)],
                "act", CostVector(
                    compute=1.0, opportunity=opportunity_cost),
                causal_kind="procedural",
                deadline_fit=(
                    category_deadline_fit[candidate.category]
                    if self.score_alignment else 1.0),
                future_option_value=(
                    category_guaranteed_score[candidate.category]
                    if self.score_alignment else 0.0),
                safety_compatible=(
                    not safety_active or (
                        goal_name in active_safety_goals
                        and (not self.score_alignment
                             or safety_candidate_relevant(candidate)))),
                payload=candidate.to_dict(),
                **self._operation_semantics(
                    candidate, "pf-impact:{}".format(goal_name))))
        if diagnostics is not None:
            diagnostics["pressure_operation_latency_ms"] = (
                diagnostics.get("pressure_operation_latency_ms", 0.0)
                + (time.perf_counter() - operation_started) * 1000.0)
        operations, teleological_artifact = (
            self._teleological_operations(
                snapshot, tuple(operations),
                candidate_by_operation, result, horizon_turn))
        operations = list(operations)
        schedule_started = time.perf_counter()
        scores = self.scheduler.score_all(operations, result)
        if self.score_alignment:
            scores = self._score_aligned_scores(
                scores, candidate_by_operation, safety_active,
                self.score_alignment_utility_tolerance)
            if diagnostics is not None:
                diagnostics["pressure_score_alignment_guard_rejections"] = (
                    diagnostics.get(
                        "pressure_score_alignment_guard_rejections", 0)
                    + sum(
                        row.reason == "score_alignment_guard"
                        for row in scores))
                diagnostics["pressure_score_alignment_deadline_rejections"] = (
                    diagnostics.get(
                        "pressure_score_alignment_deadline_rejections", 0)
                    + sum(
                        row.reason == "score_alignment_deadline"
                        for row in scores))
        rank = dict((row.operation_id, index) for index, row in enumerate(scores)
                    if row.admissible)
        ordered = tuple(sorted(candidates, key=lambda candidate: (
            rank.get(operation_by_candidate[id(candidate)], len(rank)),
            -candidate.utility, candidate.category, candidate.action_key)))
        if diagnostics is not None:
            diagnostics["pressure_schedule_latency_ms"] = (
                diagnostics.get("pressure_schedule_latency_ms", 0.0)
                + (time.perf_counter() - schedule_started) * 1000.0)
        artifact_started = time.perf_counter()
        if conductance_snapshot is not None:
            # The persisted state hash continues to identify only learned
            # feedback. This decision-scoped projection records when a new
            # direct grounding used its optimistic prior instead.
            conductance_snapshot["decision_routes"] = dict(
                (category, decision_conductance[category])
                for category in sorted(decision_conductance))
        pressure_artifact = result.to_dict()
        artifact = {
            "conductance_state": (
                conductance_snapshot),
            "pressure": pressure_artifact,
            "schedule": self.scheduler.decision_artifact(
                operations, result, scores=scores,
                pressure_artifact=pressure_artifact),
        }
        if teleological_artifact is not None:
            artifact["teleology"] = teleological_artifact
        if diagnostics is not None:
            diagnostics["pressure_artifact_latency_ms"] = (
                diagnostics.get("pressure_artifact_latency_ms", 0.0)
                + (time.perf_counter() - artifact_started) * 1000.0)
        return ordered, artifact

    def record_category_outcome(
            self, category, effect_observed, feedback_id,
            realized_relief=None, relief_source=None,
            caused_by_feedback_id=None, diagnostics=None):
        if self.conductance_state is None:
            return None
        if realized_relief is None:
            return self.conductance_state.feedback(
                category, effect_observed, feedback_id,
                diagnostics=diagnostics)
        return self.conductance_state.feedback(
            category, effect_observed, feedback_id,
            realized_relief=realized_relief,
            relief_source=relief_source,
            caused_by_feedback_id=caused_by_feedback_id,
            diagnostics=diagnostics)

    def record_outcome(
            self, candidate, effect_observed, feedback_id,
            realized_relief=None, relief_source=None, diagnostics=None):
        return self.record_category_outcome(
            candidate.category, effect_observed, feedback_id,
            realized_relief, relief_source, diagnostics=diagnostics)


class ImpactPressureRankerV2(ImpactPressureRanker):
    """Opt-in Impact adapter using scalar-v2 pressure semantics."""

    def __init__(
            self, config=None, conductance_state=None,
            score_alignment=False,
            exploration_information_enabled=True,
            score_alignment_utility_tolerance=0.0,
            policy=None, teleological_enabled=False):
        super().__init__(
            config=config,
            conductance_state=conductance_state,
            score_alignment=score_alignment,
            exploration_information_enabled=(
                exploration_information_enabled),
            score_alignment_utility_tolerance=(
                score_alignment_utility_tolerance))
        self.v2_policy = policy or PressureV2Policy()
        if not isinstance(teleological_enabled, bool):
            raise TypeError(
                "teleological_enabled must be boolean")
        self.teleological_enabled = teleological_enabled
        self.engine = PressureEngineV2(
            self.config, policy=self.v2_policy)

    @staticmethod
    def _expected_state_cost(transition, goal_id):
        fallback = transition.residual_loss_for(goal_id)
        return (
            sum(
                float(outcome.probability) * (
                    float(outcome.cost_to_go_for(goal_id))
                    if outcome.cost_to_go_for(goal_id) is not None
                    else fallback)
                for outcome in transition.outcomes)
            + float(transition.residual_probability) * fallback)

    def _teleological_operations(
            self, snapshot, operations, candidate_by_operation,
            pressure_result, horizon_turn):
        if not self.teleological_enabled:
            return tuple(operations), None
        from .teleology import (
            CostToGoEstimate,
            GoalLoss,
            LeverageEstimate,
            TypedAdvantage,
        )
        from .transitions import (
            ProjectionTransitionModel,
            TransitionModelRegistry,
        )
        goal_losses = {}
        for goal in pressure_result.goals:
            demand = pressure_result.demand(goal.goal_id)
            goal_losses[goal.goal_id] = GoalLoss(
                goal.goal_id,
                demand.achievement,
                demand.epistemic,
                demand.deadline,
                demand.safety,
                demand.total)
        registries = {}
        decorated = []
        estimates = []
        current_turn = float(getattr(snapshot, "turn", 0))
        for operation in operations:
            candidate = candidate_by_operation[
                operation.operation_id]
            goal_id = "pf-impact:{}".format(
                self.goal_for_category(candidate.category))
            current_loss = goal_losses[goal_id].total
            vector = pressure_result.pressure(
                goal_id, operation.atom_id)
            grounded_relief = min(
                current_loss,
                abs(float(vector.net(operation.mode)))
                * float(operation.success_probability)
                * float(operation.relief_scale))
            next_cost = max(
                0.0, current_loss - grounded_relief)
            payload = dict(operation.payload or {})
            projection = dict(payload.get("projection", {}))
            projection["next_goal_cost_to_go"] = {
                goal_id: next_cost}
            projection.setdefault(
                "provenance", (
                    "scalar-v2-grounded-category-effect",
                    "existing-impact-candidate-projection",
                ))
            payload["projection"] = projection
            modeled_operation = replace(
                operation, payload=payload)
            registry = registries.get(candidate.category)
            if registry is None:
                registry = TransitionModelRegistry()
                registry.register(
                    candidate.category,
                    ProjectionTransitionModel(
                        "grounded-impact-one-step:{}/1.0".format(
                            candidate.category),
                        "impact:{}:horizon-{}".format(
                            candidate.category,
                            max(
                                0,
                                int(horizon_turn)
                                - int(current_turn))),
                        fallback_loss=max(
                            current_loss, 1e-12)))
                registries[candidate.category] = registry
            transition = registry.predict(
                snapshot, modeled_operation)
            expected_state_cost = self._expected_state_cost(
                transition, goal_id)
            expected_relief = max(
                0.0, current_loss - expected_state_cost)
            state_cost_rows = tuple(
                (
                    outcome.probability,
                    outcome.cost_to_go_for(goal_id)
                    if outcome.cost_to_go_for(goal_id) is not None
                    else transition.residual_loss_for(goal_id),
                )
                for outcome in transition.outcomes)
            state_cost_values = tuple(
                float(value) for _, value in state_cost_rows) + (
                (transition.residual_loss_for(goal_id),)
                if transition.residual_probability > 0.0 else ())
            expected_total_cost = transition.expected_cost_to_go(
                goal_id)
            lower = min(
                state_cost_values or (expected_total_cost,))
            upper = max(
                max(
                    state_cost_values
                    or (expected_total_cost,)),
                expected_total_cost)
            cost_to_go = CostToGoEstimate(
                goal_id=goal_id,
                expected_loss=expected_total_cost,
                lower_bound=min(lower, expected_total_cost),
                upper_bound=upper,
                horizon=max(
                    0, int(horizon_turn) - int(current_turn)),
                estimator_id=transition.model_id,
                feature_digest=structural_hash(
                    transition.to_dict()),
                calibrated=False)
            variance = sum(
                float(probability)
                * (float(value) - expected_state_cost) ** 2
                for probability, value in state_cost_rows)
            if transition.residual_probability > 0.0:
                variance += (
                    float(transition.residual_probability)
                    * (
                        transition.residual_loss_for(goal_id)
                        - expected_state_cost) ** 2)
            resource_use = {}
            for outcome in transition.outcomes:
                for resource, delta in outcome.resource_delta:
                    if delta < 0.0:
                        resource_use[resource] = (
                            resource_use.get(resource, 0.0)
                            + float(outcome.probability)
                            * abs(float(delta)))
            completion_turns = tuple(
                float(outcome.completion_turn)
                for outcome in transition.outcomes
                if outcome.completion_turn is not None)
            advantage = TypedAdvantage(
                goal_id=goal_id,
                target_id=operation.atom_id,
                mode=operation.mode,
                expected_relief=expected_relief,
                relief_variance=variance,
                information_gain=operation.information_gain,
                option_value=operation.future_option_value,
                predicted_latency=(
                    max(0.0, min(completion_turns) - current_turn)
                    if completion_turns else 0.0),
                predicted_resource_use=tuple(
                    sorted(resource_use.items())),
                estimator_id=transition.model_id)
            leverage = LeverageEstimate(
                goal_id, operation.atom_id,
                expected_relief,
                "counterfactual",
                transition.modeled_probability,
                (
                    "one-step-grounded-impact-projection",
                    "risk-penalty-applied-separately-once",
                ))
            decorated.append(replace(
                operation, typed_advantages=(advantage,)))
            estimates.append({
                "advantage": advantage.to_dict(),
                "category": candidate.category,
                "cost_to_go": cost_to_go.to_dict(),
                "current_goal_loss": float(current_loss),
                "goal_id": goal_id,
                "leverage": leverage.to_dict(),
                "operation_id": operation.operation_id,
                "transition": transition.to_dict(),
            })
        artifact = {
            "enabled": True,
            "estimator_hierarchy": (
                "exact-terminal",
                "grounded-impact-one-step",
                "bounded-dynamic-programming",
                "calibrated-heuristic",
                "immediate-loss-fallback"),
            "goal_losses": [
                goal_losses[key].to_dict()
                for key in sorted(goal_losses)],
            "horizon_turn": int(horizon_turn),
            "operation_estimates": sorted(
                estimates,
                key=lambda row: row["operation_id"]),
            "risk_accounting": (
                "transition state relief plus scheduler risk penalty; "
                "risk is not included in TypedAdvantage"),
            "schema_version": "1.0",
        }
        artifact["artifact_hash"] = structural_hash(artifact)
        return tuple(decorated), artifact

    def _goal_risk_profile(self, name, safety):
        from .risk import RiskProfile
        return RiskProfile(
            aversion=(1.0 if safety else 0.15),
            max_tail_loss=(1.0 if safety else None),
            hard_gate=bool(safety))

    def _operation_semantics(self, candidate, goal_id):
        from .packets import PacketCost, ResourceKind
        from .risk import estimate_uncertain_loss
        projection = candidate.projection or {}
        declared = projection.get("risk_estimate")
        estimates = ()
        if isinstance(declared, dict):
            provenance = tuple(declared.get("provenance", ()))
            if not provenance:
                raise ValueError(
                    "v2 candidate risk estimate requires provenance")
            estimate = estimate_uncertain_loss(
                expected_loss=declared.get("expected_loss", 0.0),
                outcome_variance=declared.get("variance", 0.0),
                confidence=declared.get("confidence", 0.0),
                tail_alpha=declared.get("tail_alpha", 0.10),
                provenance=provenance)
            estimates = ((goal_id, estimate),)
        reversible = bool(projection.get("reversible", True))
        return {
            "deadline_estimate": self._deadline_estimate(candidate),
            "externally_consequential": True,
            "packet_costs": (
                PacketCost(ResourceKind.ACTION, 1),
                PacketCost(ResourceKind.CPU, 1)),
            "reversible": reversible,
            "risk_estimates": estimates,
        }
