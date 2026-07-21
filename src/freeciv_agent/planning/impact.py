"""Grounded strategic action planning over the exact server legal-action set.

This module deliberately performs no inference.  It turns already-authoritative
state and server-advertised actions into short, auditable plans which still pass
through :class:`ExecutionGate` immediately before transport.
"""

import json
import math
from dataclasses import dataclass

from ..events.schema import canonical_json_bytes, structural_hash
from .model import BranchScore, Plan, PlanStep, ResourceLedger


LEGACY_FOUNDER_TYPES = frozenset(("settlers", "migrants", "engineers"))
RULESET_FOUNDER_FLAG = "cities"
RULESET_WORKER_FLAG = "settlers"
RULESET_ADD_TO_CITY_FLAG = "addtocity"
EXPLORER_TYPES = frozenset(("explorer", "diplomat", "spy", "caravan"))
DEFENDER_PRIORITY = (
    "Mech. Inf.", "Alpine Troops", "Riflemen", "Musketeers", "Pikemen",
    "Phalanx", "Legion", "Warriors",
)
IMPROVEMENT_PRIORITY = (
    "Granary", "Library", "Marketplace", "City Walls", "Barracks II",
    "Barracks I", "Temple", "Courthouse", "Aqueduct, River",
)
OFFENSIVE_ACTIONS = frozenset((
    "unit_attack", "unit_suicide_attack", "unit_bombard", "unit_capture",
    "unit_conquer_city", "unit_wipe",
))


@dataclass(frozen=True)
class ImpactCandidate:
    action: dict
    category: str
    utility: float
    rationale: str
    projection: dict = None

    @property
    def action_key(self):
        return canonical_json_bytes(self.action).decode("utf-8")

    @property
    def scope(self):
        action_type = str(self.action.get("action_type", ""))
        if action_type == "city_production":
            return ("production", self.action.get("city_id"))
        if action_type.startswith("unit_"):
            return ("unit", self.action.get("actor_id"))
        return (action_type, None)

    @property
    def terminal_on_accept(self):
        """Whether transport acceptance can consume the actor before state catches up."""
        return self.action.get("action_type") in (
            "unit_build_city", "unit_join_city", "unit_suicide_attack")

    @property
    def unit_scope_consumed_on_accept(self):
        """Whether acceptance can spend an actor resource hidden by a stale snapshot."""
        return str(self.action.get("action_type", "")).startswith("unit_")

    def to_dict(self):
        result = {
            "action": dict(self.action), "category": self.category,
            "rationale": self.rationale, "utility": self.utility,
        }
        if self.projection is not None:
            result["projection"] = dict(self.projection)
        return result


@dataclass(frozen=True)
class ImpactDecision:
    candidate: ImpactCandidate
    plan: Plan


@dataclass(frozen=True)
class DeferredImpactResolution:
    """One accepted action resolved by a later authoritative snapshot."""

    candidate: ImpactCandidate
    before_snapshot: object
    after_snapshot: object
    effect_observed: bool


class DeferredImpactOutcomeLedger(object):
    """Reconcile accepted actions whose effects outlive the bounded wait.

    Freeciv may execute an accepted order later in the same turn or while the
    turn is closing.  A timeout is therefore not proof of no effect.  Entries
    remain pending while only same-turn snapshots disagree, resolve as soon as
    the candidate-specific effect is visible, and expire as a grounded
    no-effect outcome on the first later-turn snapshot.
    """

    def __init__(self):
        self._pending = []

    def __len__(self):
        return len(self._pending)

    def defer(self, candidate, before_snapshot):
        self._pending.append((candidate, before_snapshot))

    def resolve(self, planner, after_snapshot):
        resolved = []
        pending = []
        for candidate, before_snapshot in self._pending:
            effect_observed = planner.candidate_effect_observed(
                candidate, before_snapshot, after_snapshot)
            if (effect_observed
                    or int(after_snapshot.turn) > int(before_snapshot.turn)):
                resolved.append(DeferredImpactResolution(
                    candidate, before_snapshot, after_snapshot,
                    bool(effect_observed)))
            else:
                pending.append((candidate, before_snapshot))
        self._pending = pending
        return tuple(resolved)


class ImpactTurnBudget(object):
    """Bound no-effect failover without consuming a successful action scope."""

    def __init__(self, max_no_effect_failovers):
        self.max_no_effect_failovers = int(max_no_effect_failovers)
        if not 0 <= self.max_no_effect_failovers <= 8:
            raise ValueError("max_no_effect_failovers must be in 0..8")
        self.used_scopes = set()
        self.failed_attempts = {}
        self.failover_attempts = 0
        self.recoveries = 0

    @property
    def excluded_scopes(self):
        return frozenset(self.used_scopes)

    def record(self, candidate, effect_observed, authoritative_refresh=True):
        scope = candidate.scope
        is_failover = self.failed_attempts.get(scope, 0) > 0
        if is_failover:
            self.failover_attempts += 1
        if (not authoritative_refresh or effect_observed or candidate.terminal_on_accept
                or candidate.unit_scope_consumed_on_accept):
            self.used_scopes.add(scope)
            self.recoveries += int(is_failover and effect_observed)
        else:
            failures = self.failed_attempts.get(scope, 0) + 1
            self.failed_attempts[scope] = failures
            if failures > self.max_no_effect_failovers:
                self.used_scopes.add(scope)
        return is_failover


def _normalized_type(value):
    return str(value or "").strip().lower().replace("_", " ")


def _distance(x, y, tx, ty, width, height):
    if None in (x, y, tx, ty) or width <= 0 or height <= 0:
        return 0
    dx = min((int(x) - int(tx)) % width, (int(tx) - int(x)) % width)
    dy = min((int(y) - int(ty)) % height, (int(ty) - int(y)) % height)
    return max(dx, dy)


def _target_name(action):
    target = action.get("target")
    if isinstance(target, dict):
        return str(target.get("production_type", target.get("value", "")))
    return str(target or "")


class GroundedImpactPlanner(object):
    """Select high-impact legal actions without weakening the execution gate."""

    SOLVER_IDENTITY = "grounded-impact-planner/1.2"

    # Routing evidence is deliberately a tie-breaker within the strategic
    # expansion policy.  It must never manufacture legality or bypass the
    # execution gate's one-unit-action safety boundary.
    FOUNDER_CITY_SEPARATION_WEIGHT = 24.0
    FOUNDER_CARDINAL_CORRIDOR_BONUS = 18.0
    FOUNDER_TRAVERSABLE_EDGE_BONUS = 36.0
    FOUNDER_FAILED_EDGE_PENALTY = 30.0

    def __init__(self, config=None, ruleset_ir=None):
        values = dict(config or {})
        self.max_actions_per_turn = int(values.get("max_actions_per_turn", 8))
        self.expansion_city_target = int(values.get("expansion_city_target", 3))
        self.settle_min_distance = int(values.get("settle_min_distance", 3))
        self.horizon_turn = int(values.get("horizon_turn", 30))
        self.production_minimum_remaining_turns = int(
            values.get("production_minimum_remaining_turns", 8))
        self.expansion_minimum_remaining_turns = int(
            values.get("expansion_minimum_remaining_turns", 12))
        self.foodbox_percent = int(values.get("foodbox_percent", 100))
        self.unit_build_score_divisor = int(values.get(
            "unit_build_score_divisor", 10))
        self.refresh_timeout_seconds = float(
            values.get("refresh_timeout_seconds", 2.0))
        self.no_effect_retry_limit = int(values.get("no_effect_retry_limit", 1))
        self.max_no_effect_failovers_per_scope = int(
            values.get("max_no_effect_failovers_per_scope", 4))
        self.preserve_city_defenders = bool(values.get("preserve_city_defenders", True))
        self.production_strategy = str(values.get(
            "production_strategy", "horizon_score"))
        if not 1 <= self.max_actions_per_turn <= 32:
            raise ValueError("max_actions_per_turn must be in 1..32")
        if not 1 <= self.expansion_city_target <= 20:
            raise ValueError("expansion_city_target must be in 1..20")
        if not 1 <= self.settle_min_distance <= 12:
            raise ValueError("settle_min_distance must be in 1..12")
        if not 1 <= self.horizon_turn <= 500:
            raise ValueError("horizon_turn must be in 1..500")
        if not 1 <= self.production_minimum_remaining_turns <= 100:
            raise ValueError("production_minimum_remaining_turns must be in 1..100")
        if not 1 <= self.expansion_minimum_remaining_turns <= 100:
            raise ValueError("expansion_minimum_remaining_turns must be in 1..100")
        if self.expansion_minimum_remaining_turns < self.production_minimum_remaining_turns:
            raise ValueError(
                "expansion_minimum_remaining_turns cannot be shorter than production")
        if not 1 <= self.foodbox_percent <= 1000:
            raise ValueError("foodbox_percent must be in 1..1000")
        if not 1 <= self.unit_build_score_divisor <= 100:
            raise ValueError("unit_build_score_divisor must be in 1..100")
        if not 0.25 <= self.refresh_timeout_seconds <= 10.0:
            raise ValueError("refresh_timeout_seconds must be in [0.25,10]")
        if not 1 <= self.no_effect_retry_limit <= 8:
            raise ValueError("no_effect_retry_limit must be in 1..8")
        if not 0 <= self.max_no_effect_failovers_per_scope <= 8:
            raise ValueError("max_no_effect_failovers_per_scope must be in 0..8")
        if self.production_strategy not in ("static_priority", "horizon_score"):
            raise ValueError(
                "production_strategy must be 'static_priority' or 'horizon_score'")
        self.visited_positions = set()
        self._fortified_units = set()
        self._no_effect_attempts = {}
        self._reported_suppressions = set()
        self.no_effect_retries_blocked = 0
        self._build_costs = {}
        self._production_specs = {}
        self._ruleset_founder_types = set()
        self._ruleset_worker_types = set()
        self._ruleset_add_to_city_types = set()
        self._server_founder_types = set()
        self._founder_cardinal_intents = {}
        self._founder_traversable_edges = set()
        self._founder_failed_edges = {}
        self._founder_actor_failed_edges = set()
        self._failed_exploration_target_sources = {}
        self._failed_exploration_prunes = set()
        self._unit_score_batch_intent = None
        self._unit_score_batch_cache_key = None
        self._unit_score_batch_cache = {}
        self.founder_route_successes = 0
        self.founder_route_failures = 0
        self.founder_cardinal_corridor_attempts = 0
        self.founder_cardinal_corridor_successes = 0
        self.population_recovery_attempts = 0
        self.population_recovery_completions = 0
        self.population_recovered = 0
        self.population_recovery_route_attempts = 0
        self.population_recovery_route_successes = 0
        parameters = getattr(ruleset_ir, "parameters", {})
        initial_food = parameters.get("granary_food_ini", {})
        incremental_food = parameters.get("granary_food_inc", {})
        initial_values = (initial_food.get("value")
                          if isinstance(initial_food, dict) else None)
        if not isinstance(initial_values, list):
            initial_values = ([initial_values]
                              if isinstance(initial_values, (int, float)) else [20])
        self._granary_food_ini = tuple(max(1, int(value)) for value in initial_values)
        incremental_value = (incremental_food.get("value")
                             if isinstance(incremental_food, dict) else None)
        self._granary_food_inc = (max(0, int(incremental_value))
                                  if isinstance(incremental_value, (int, float)) else 10)
        self._growth_cost_source = (
            "ruleset_ir" if isinstance(initial_food, dict)
            and isinstance(incremental_food, dict) else "bounded_fallback")
        for rule in getattr(ruleset_ir, "rules", ()):
            quantitative = getattr(rule, "quantitative", {})
            cost = quantitative.get("build_cost")
            if isinstance(cost, dict):
                cost = cost.get("value")
            pop_cost = quantitative.get("pop_cost", 0)
            if isinstance(pop_cost, dict):
                pop_cost = pop_cost.get("value", 0)
            if (getattr(rule, "target_kind", None) not in (
                    "unit", "building", "improvement")
                    or isinstance(cost, bool) or not isinstance(cost, (int, float))
                    or cost <= 0):
                continue
            for label in (getattr(rule, "display_name", None),
                          getattr(rule, "rule_name", None)):
                if label:
                    key = _normalized_type(label)
                    self._build_costs[key] = int(cost)
                    self._production_specs[key] = {
                        "build_cost": int(cost),
                        "pop_cost": (0 if isinstance(pop_cost, bool)
                                     or not isinstance(pop_cost, (int, float))
                                     else max(0, int(pop_cost))),
                        "target_kind": getattr(rule, "target_kind", None),
                    }
                    flags = self._trait_values(rule, "flags")
                    if RULESET_FOUNDER_FLAG in flags:
                        self._ruleset_founder_types.add(key)
                    if RULESET_WORKER_FLAG in flags:
                        self._ruleset_worker_types.add(key)
                    if RULESET_ADD_TO_CITY_FLAG in flags:
                        self._ruleset_add_to_city_types.add(key)

    @staticmethod
    def _trait_values(rule, name):
        trait = getattr(rule, "traits", {}).get(name, {})
        values = trait.get("values", ()) if isinstance(trait, dict) else ()
        return frozenset(_normalized_type(value) for value in values)

    @staticmethod
    def _actions(snapshot):
        return tuple(json.loads(value) for value in snapshot.legal_action_json)

    def _legal_unit_types(self, snapshot, action_type, actions=None):
        result = set()
        for action in self._actions(snapshot) if actions is None else actions:
            if action.get("action_type") != action_type:
                continue
            unit = snapshot.unit(action.get("actor_id"))
            if unit is not None:
                result.add(_normalized_type(unit.unit_type))
        return frozenset(result)

    def _founder_types(self, snapshot, actions=None):
        return frozenset(
            self._ruleset_founder_types | self._server_founder_types
            | set(self._legal_unit_types(snapshot, "unit_build_city", actions)))

    @property
    def founder_capable_types(self):
        """Normalized types backed by ruleset flags or observed legal actions."""
        return tuple(sorted(self._ruleset_founder_types | self._server_founder_types))

    def _founder_capability_source(self, normalized):
        if normalized in self._ruleset_founder_types:
            return "ruleset_flag:Cities"
        if normalized in self._server_founder_types:
            return "server_legal_action:unit_build_city"
        return None

    def observe(self, snapshot):
        actions = self._actions(snapshot)
        self._server_founder_types.update(self._legal_unit_types(
            snapshot, "unit_build_city", actions))
        for unit in snapshot.units:
            if unit.x is not None and unit.y is not None:
                self.visited_positions.add((unit.x, unit.y))

    def capability_pruned_worker_move_keys(self, snapshot):
        """Return legal worker moves rejected because the actor cannot found cities.

        This helper and candidate enumeration are deliberately read-only. The live
        harness owns aggregation so inspecting a snapshot cannot alter a decision.
        """
        actions = self._actions(snapshot)
        founder_types = self._founder_types(snapshot, actions)
        result = []
        for action in actions:
            if action.get("action_type") != "unit_move":
                continue
            unit = snapshot.unit(action.get("actor_id"))
            normalized = _normalized_type(unit.unit_type) if unit is not None else ""
            if normalized in self._ruleset_worker_types - founder_types:
                result.append(canonical_json_bytes(action).decode("utf-8"))
        return tuple(sorted(result))

    def nonprogress_move_keys(self, snapshot):
        """Return legal moves rejected for lacking observable strategic progress."""
        actions = self._actions(snapshot)
        founder_types = self._founder_types(snapshot, actions)
        return tuple(sorted(
            canonical_json_bytes(action).decode("utf-8")
            for action in actions
            if action.get("action_type") == "unit_move"
            and self._move_candidate(snapshot, action, founder_types) is None
            and self._move_is_nonprogress(snapshot, action, founder_types)))

    def founder_unreachable_move_keys(self, snapshot):
        """Return founder moves pruned by actor-local reachability evidence.

        Like candidate enumeration, this inspection is read-only.  The live
        harness aggregates the returned canonical keys without allowing
        telemetry collection to alter routing state.
        """
        actions = self._actions(snapshot)
        founder_types = self._founder_types(snapshot, actions)
        return tuple(sorted(
            canonical_json_bytes(action).decode("utf-8")
            for action in actions
            if action.get("action_type") == "unit_move"
            and self._founder_move_evidence(
                snapshot, action, founder_types).get("actor_failed")))

    def commit(self, candidate):
        """Record a successfully transported persistent policy decision."""
        if candidate.category == "city_defense":
            self._fortified_units.add(candidate.action.get("actor_id"))

    @staticmethod
    def _unit_grounding(unit):
        if unit is None:
            return None
        # Moves refresh at every turn and are therefore deliberately omitted.
        # A retry becomes eligible only when the actor's material local state
        # changes, rather than merely because another turn started.
        return {
            "activity": unit.activity, "hp": unit.hp, "type": unit.unit_type,
            "unit_id": unit.unit_id, "x": unit.x, "y": unit.y,
        }

    @staticmethod
    def _unit_effect_grounding(unit):
        """Actor facts that prove an accepted unit action consumed resources."""
        if unit is None:
            return None
        return {
            "activity": unit.activity, "hp": unit.hp,
            "moves_left": unit.moves_left, "type": unit.unit_type,
            "unit_id": unit.unit_id, "x": unit.x, "y": unit.y,
        }

    @staticmethod
    def _combat_target_grounding(snapshot, action):
        """Packet-visible target facts that can prove an offensive effect."""
        target = action.get("target")
        if not isinstance(target, dict):
            return ()
        target_unit_id = target.get("target_unit_id")
        if target_unit_id is not None:
            rows = (snapshot.visible_enemy_unit(target_unit_id),)
        else:
            x, y = target.get("x"), target.get("y")
            if x is None or y is None:
                return ()
            rows = tuple(row for row in snapshot.visible_enemy_units
                         if (row.x, row.y) == (x, y))
        return tuple(sorted(
            (row.unit_id, row.owner, row.unit_type, row.hp, row.x, row.y)
            for row in rows if row is not None))

    def local_actor_effect_observed(self, candidate, before, after):
        """Detect actor-local effects omitted by the proxy's general state hash.

        In particular, FreeCiv can publish a movement-point update without
        changing the proxy state hash.  Treating that accepted action as a
        no-effect failure would permit a stale same-turn failover and can send a
        second order after the unit has exhausted its moves.
        """
        actor_id = candidate.action.get("actor_id")
        if actor_id is None:
            return False
        return self._unit_effect_grounding(before.unit(actor_id)) != (
            self._unit_effect_grounding(after.unit(actor_id)))

    def candidate_effect_observed(self, candidate, before, after):
        """Require an authoritative effect attributable to the submitted action.

        A source-sequence or general state-hash change can be caused by economy,
        research, or opponent packets.  In particular it does not prove that a
        requested production target was installed.  Production therefore uses
        an exact city-target predicate. Offensive actions additionally compare
        their packet-visible target stack so a destroyed defender counts even
        when the attacker remains fortified with unchanged hit points. Other
        unit actions use actor-local resource changes; only action kinds without
        a local grounding use the general state hash as a final fallback.
        """
        action = candidate.action
        if action.get("action_type") == "city_production":
            city = after.city(action.get("city_id"))
            kind = action.get("production_kind")
            value = action.get("production_value")
            return bool(city is not None and kind is not None and value is not None
                        and city.production_kind == int(kind)
                        and city.production_value == int(value))
        if action.get("action_type") == "unit_build_city":
            actor_id = action.get("actor_id")
            return bool(actor_id is not None and before.unit(actor_id) is not None
                        and after.unit(actor_id) is None
                        and len(after.cities) > len(before.cities))
        if action.get("action_type") == "unit_join_city":
            actor_id = action.get("actor_id")
            target = action.get("target")
            city_id = target.get("city_id") if isinstance(target, dict) else None
            recovered = int((candidate.projection or {}).get(
                "recovered_population", 0))
            before_city = before.city(city_id) if city_id is not None else None
            after_city = after.city(city_id) if city_id is not None else None
            return bool(actor_id is not None and recovered > 0
                        and before.unit(actor_id) is not None
                        and after.unit(actor_id) is None
                        and before_city is not None and after_city is not None
                        and after_city.size == before_city.size + recovered)
        if action.get("action_type") in OFFENSIVE_ACTIONS:
            return (self.local_actor_effect_observed(candidate, before, after)
                    or self._combat_target_grounding(before, action)
                    != self._combat_target_grounding(after, action))
        if action.get("actor_id") is not None:
            return self.local_actor_effect_observed(candidate, before, after)
        return before.identity.state_hash != after.identity.state_hash

    def _grounding_signature(self, snapshot, candidate):
        """Hash only the local authoritative facts that can change an outcome."""
        action = candidate.action
        actor_id = action.get("actor_id")
        city_id = action.get("city_id")
        target = action.get("target")
        if city_id is None and isinstance(target, dict):
            city_id = target.get("city_id")
        actor = snapshot.unit(actor_id) if actor_id is not None else None
        city = snapshot.city(city_id) if city_id is not None else None
        target_unit = None
        if isinstance(target, dict):
            target_unit_id = target.get("target_unit_id")
            if target_unit_id is not None:
                target_unit = snapshot.visible_enemy_unit(target_unit_id)
            elif target.get("x") is not None and target.get("y") is not None:
                target_unit = next((row for row in snapshot.visible_enemy_units
                                    if (row.x, row.y) == (target["x"], target["y"])), None)
        city_grounding = None if city is None else {
            "city_id": city.city_id, "production_kind": city.production_kind,
            "production_value": city.production_value, "shield_stock": city.shield_stock,
            "size": city.size, "x": city.x, "y": city.y,
        }
        city_layout = (
            sorted((row.city_id, row.x, row.y) for row in snapshot.cities)
            if candidate.category in ("city_founding", "expansion_move") else [])
        return structural_hash({
            "action": action,
            "actor": self._unit_grounding(actor),
            "cities": city_layout,
            "city": city_grounding,
            "target_unit": self._unit_grounding(target_unit),
        })

    def record_outcome(
            self, candidate, snapshot, effect_observed, after_snapshot=None):
        """Learn from an accepted action without treating acceptance as effect.

        Exact no-effect actions are suppressed while their local authoritative
        grounding is unchanged.  Movement refreshes and unrelated economic state
        cannot make an unreachable order eligible again; actor, city, or visible
        target changes can.
        """
        self.commit(candidate)
        if candidate.category == "production_military_score":
            intent = self._unit_score_batch_intent
            if (not isinstance(intent, dict)
                    or intent.get("awaiting") != candidate.action_key
                    or not effect_observed
                    or (after_snapshot is not None
                        and int(after_snapshot.turn) != int(intent["turn"]))):
                self._unit_score_batch_intent = None
            else:
                intent["remaining"].discard(candidate.action_key)
                intent["awaiting"] = None
                if not intent["remaining"]:
                    self._unit_score_batch_intent = None
        if candidate.category == "population_recovery":
            self.population_recovery_attempts += 1
            if effect_observed:
                self.population_recovery_completions += 1
                self.population_recovered += int((candidate.projection or {}).get(
                    "recovered_population", 0))
        if candidate.category == "population_recovery_move":
            self.population_recovery_route_attempts += 1
            target = candidate.action.get("target", {})
            actor_id = candidate.action.get("actor_id")
            after_unit = (after_snapshot.unit(actor_id)
                          if after_snapshot is not None else None)
            if (after_unit is not None and isinstance(target, dict)
                    and (after_unit.x, after_unit.y)
                    == (target.get("x"), target.get("y"))):
                self.population_recovery_route_successes += 1
        if candidate.category == "city_founding":
            # A settlement attempt ends the current movement corridor whether
            # the site succeeds or the unit must search from the same tile.
            self._founder_cardinal_intents.pop(
                candidate.action.get("actor_id"), None)
        self._record_founder_route_outcome(
            candidate, snapshot, after_snapshot)
        self._record_exploration_destination_outcome(
            candidate, snapshot, after_snapshot)
        key = (candidate.action_key, self._grounding_signature(snapshot, candidate))
        if effect_observed:
            self._no_effect_attempts.pop(key, None)
        else:
            self._no_effect_attempts[key] = self._no_effect_attempts.get(key, 0) + 1

    def _no_effect_suppressed(self, snapshot, candidate):
        key = (candidate.action_key, self._grounding_signature(snapshot, candidate))
        if self._no_effect_attempts.get(key, 0) < self.no_effect_retry_limit:
            return False
        reported = (snapshot.snapshot_id, key)
        if reported not in self._reported_suppressions:
            self._reported_suppressions.add(reported)
            self.no_effect_retries_blocked += 1
        return True

    def _exploration_destination_key(self, snapshot, action):
        unit = snapshot.unit(action.get("actor_id"))
        target = action.get("target")
        if unit is None or not isinstance(target, dict):
            return None
        x, y = target.get("x"), target.get("y")
        if x is None or y is None:
            return None
        return (_normalized_type(unit.unit_type), snapshot.map_width,
                snapshot.map_height, int(x), int(y))

    def _record_exploration_destination_outcome(self, candidate, before, after):
        """Learn only repeated source-independent exploration obstructions."""
        if candidate.category != "exploration_move" or after is None:
            return
        action = candidate.action
        key = self._exploration_destination_key(before, action)
        before_unit = before.unit(action.get("actor_id"))
        after_unit = after.unit(action.get("actor_id"))
        target = action.get("target")
        if (key is None or before_unit is None or after_unit is None
                or not isinstance(target, dict)):
            return
        target_position = (int(target["x"]), int(target["y"]))
        if (after_unit.x, after_unit.y) == target_position:
            self._failed_exploration_target_sources.pop(key, None)
            return
        if (after_unit.x, after_unit.y) != (before_unit.x, before_unit.y):
            return
        # A packet-visible opponent is a transient tactical obstruction, not
        # evidence that the destination itself is untraversable.
        if any((row.x, row.y) == target_position
               for row in before.visible_enemy_units):
            return
        self._failed_exploration_target_sources.setdefault(key, set()).add(
            (before_unit.x, before_unit.y))

    def _exploration_destination_reliably_failed(self, snapshot, action):
        key = self._exploration_destination_key(snapshot, action)
        return bool(key is not None and len(
            self._failed_exploration_target_sources.get(key, ())) >= 2)

    @property
    def repeated_failed_destination_moves_pruned(self):
        return len(self._failed_exploration_prunes)

    def _founders(self, snapshot, founder_types=None):
        founder_types = (self._founder_types(snapshot)
                         if founder_types is None else founder_types)
        return tuple(unit for unit in snapshot.units
                     if _normalized_type(unit.unit_type) in founder_types)

    def _combat_units(self, snapshot, founder_types=None):
        founder_types = (self._founder_types(snapshot)
                         if founder_types is None else founder_types)
        excluded = self._ruleset_worker_types | set(founder_types) | EXPLORER_TYPES
        return tuple(unit for unit in snapshot.units
                     if _normalized_type(unit.unit_type) not in excluded)

    @staticmethod
    def _legacy_combat_units(snapshot):
        return tuple(unit for unit in snapshot.units
                     if _normalized_type(unit.unit_type)
                     not in LEGACY_FOUNDER_TYPES | EXPLORER_TYPES)

    def _distance_from_cities(self, snapshot, x, y):
        rows = [_distance(x, y, city.x, city.y, snapshot.map_width, snapshot.map_height)
                for city in snapshot.cities]
        return min(rows) if rows else self.settle_min_distance

    @staticmethod
    def _city_layout(snapshot):
        return tuple(sorted(
            (city.city_id, city.x, city.y) for city in snapshot.cities))

    @staticmethod
    def _axis_heading(source, target, size):
        if source is None or target is None or source == target:
            return 0
        if size <= 0:
            return 1 if int(target) > int(source) else -1
        forward = (int(target) - int(source)) % int(size)
        backward = (int(source) - int(target)) % int(size)
        if forward == backward:
            return 1 if int(target) > int(source) else -1
        return 1 if forward < backward else -1

    def _move_heading(self, snapshot, source, target):
        return (
            self._axis_heading(source[0], target[0], snapshot.map_width),
            self._axis_heading(source[1], target[1], snapshot.map_height),
        )

    def _founder_edge(self, snapshot, action, founder_types):
        unit = snapshot.unit(action.get("actor_id"))
        target = action.get("target", {})
        if unit is None or not isinstance(target, dict):
            return None
        unit_type = _normalized_type(unit.unit_type)
        x, y = target.get("x"), target.get("y")
        if (unit_type not in founder_types or None in (unit.x, unit.y, x, y)
                or (unit.x, unit.y) == (x, y)):
            return None
        return (unit_type, int(unit.x), int(unit.y), int(x), int(y))

    def _founder_actor_edge(self, snapshot, unit, edge):
        return (
            int(unit.unit_id), edge, self._city_layout(snapshot),
        )

    def _founder_cardinal_intent(self, snapshot, unit):
        intent = self._founder_cardinal_intents.get(unit.unit_id)
        if (intent is None
                or intent["unit_type"] != _normalized_type(unit.unit_type)
                or intent["city_layout"] != self._city_layout(snapshot)
                or intent["position"] != (unit.x, unit.y)
                or self._distance_from_cities(snapshot, unit.x, unit.y)
                >= self.settle_min_distance):
            return None
        return intent

    def _founder_move_evidence(self, snapshot, action, founder_types):
        """Read grounded routing evidence for one advertised founder move."""
        edge = self._founder_edge(snapshot, action, founder_types)
        if edge is None:
            return {}
        unit = snapshot.unit(action.get("actor_id"))
        heading = self._move_heading(
            snapshot, (edge[1], edge[2]), (edge[3], edge[4]))
        intent = self._founder_cardinal_intent(snapshot, unit)
        return {
            "actor_failed": (
                self._founder_actor_edge(snapshot, unit, edge)
                in self._founder_actor_failed_edges),
            "edge": edge,
            "failed_attempts": self._founder_failed_edges.get(edge, 0),
            "cardinal_corridor_match": bool(
                intent is not None and intent["heading"] == heading),
            "traversable_edge": edge in self._founder_traversable_edges,
        }

    def _record_founder_route_outcome(self, candidate, before, after):
        """Record only an exact post-action position as traversability proof."""
        if candidate.category != "expansion_move":
            return
        corridor_attempt = bool(
            (candidate.projection or {}).get("cardinal_corridor_match", False))
        self.founder_cardinal_corridor_attempts += int(corridor_attempt)
        if after is None:
            return
        founder_types = self._founder_types(before)
        edge = self._founder_edge(before, candidate.action, founder_types)
        unit = before.unit(candidate.action.get("actor_id"))
        if edge is None or unit is None:
            return
        actor_edge = self._founder_actor_edge(before, unit, edge)
        target = (edge[3], edge[4])
        after_unit = after.unit(unit.unit_id)
        traversed = bool(
            after_unit is not None
            and (after_unit.x, after_unit.y) == target
            and (unit.x, unit.y) != target)
        if traversed:
            self.founder_route_successes += 1
            self.founder_cardinal_corridor_successes += int(corridor_attempt)
            self._founder_traversable_edges.add(edge)
            self._founder_actor_failed_edges.discard(actor_edge)
            heading = self._move_heading(
                before, (unit.x, unit.y), target)
            if (heading[0] == 0) != (heading[1] == 0):
                self._founder_cardinal_intents[unit.unit_id] = {
                    "city_layout": self._city_layout(before),
                    "heading": heading,
                    "position": target,
                    "unit_type": _normalized_type(unit.unit_type),
                }
            else:
                # A diagonal step proves only that exact edge. Carrying its
                # vector forward previously overshot productive city sites.
                self._founder_cardinal_intents.pop(unit.unit_id, None)
            return

        self.founder_route_failures += 1
        self._founder_failed_edges[edge] = (
            self._founder_failed_edges.get(edge, 0) + 1)
        self._founder_actor_failed_edges.add(actor_edge)
        intent = self._founder_cardinal_intents.get(unit.unit_id)
        if (intent is not None and intent["position"] == (unit.x, unit.y)
                and intent["heading"] == self._move_heading(
                    before, (unit.x, unit.y), target)):
            self._founder_cardinal_intents.pop(unit.unit_id, None)

    def _founder_city_separation_gain(self, snapshot, unit, x, y):
        """Measure outward progress across all established cities.

        Minimum city distance remains the settlement constraint.  This aggregate
        delta resolves the otherwise arbitrary first step from a city tile by
        favoring the side of the city network with more expansion room.
        """
        current = sum(_distance(
            unit.x, unit.y, city.x, city.y,
            snapshot.map_width, snapshot.map_height) for city in snapshot.cities)
        target = sum(_distance(
            x, y, city.x, city.y,
            snapshot.map_width, snapshot.map_height) for city in snapshot.cities)
        return ((target - current) / float(len(snapshot.cities))
                if snapshot.cities else 0.0)

    def _founder_route_eta(self):
        """Estimate movement turns from observed successful/failed route orders."""
        attempts = self.founder_route_successes + self.founder_route_failures
        if attempts <= 0:
            return self.settle_min_distance, "minimum_distance"
        if self.founder_route_successes <= 0:
            return (self.settle_min_distance
                    + min(self.settle_min_distance, self.founder_route_failures),
                    "observed_route_effects")
        eta = int(math.ceil(
            self.settle_min_distance * attempts
            / float(self.founder_route_successes)))
        return max(self.settle_min_distance, eta), "observed_route_effects"

    def _city_defender_is_required(self, snapshot, unit, founder_types=None):
        if not self.preserve_city_defenders:
            return False
        founder_types = (self._founder_types(snapshot)
                         if founder_types is None else founder_types)
        if (_normalized_type(unit.unit_type) in self._ruleset_worker_types
                | set(founder_types) | EXPLORER_TYPES):
            return False
        city = next((row for row in snapshot.cities
                     if (row.x, row.y) == (unit.x, unit.y)), None)
        if city is None:
            return False
        defenders = [row for row in self._combat_units(snapshot, founder_types)
                     if (row.x, row.y) == (city.x, city.y)]
        return len(defenders) <= 1

    @staticmethod
    def _known_hut_positions(snapshot):
        if snapshot.map_width <= 0:
            return ()
        return tuple((tile % snapshot.map_width, tile // snapshot.map_width)
                     for tile in snapshot.known_hut_tile_ids)

    def _hut_route_distances(self, snapshot, unit, x, y):
        huts = self._known_hut_positions(snapshot)
        if not huts:
            return None
        current = min(_distance(
            unit.x, unit.y, hx, hy, snapshot.map_width, snapshot.map_height)
                      for hx, hy in huts)
        target = min(_distance(
            x, y, hx, hy, snapshot.map_width, snapshot.map_height)
                     for hx, hy in huts)
        return current, target

    @staticmethod
    def _current_production_matches(city, action):
        kind = action.get("production_kind")
        value = action.get("production_value")
        return (kind is not None and value is not None
                and int(kind) == city.production_kind and int(value) == city.production_value)

    @staticmethod
    def _current_production_name(city):
        expected_kind = {"unit": 6, "improvement": 3}
        for kind, item_id, name in city.buildable:
            if (expected_kind.get(str(kind).lower()) == city.production_kind
                    and int(item_id) == city.production_value):
                return str(name)
        return None

    @staticmethod
    def _city_output(city, index):
        if len(city.surplus) <= index:
            return 0
        return max(0, int(city.surplus[index]))

    def _growth_food_cost(self, city_size):
        """Return the active ruleset's food box for one city-size transition."""
        size = max(1, int(city_size or 1))
        if size <= len(self._granary_food_ini):
            base = self._granary_food_ini[size - 1]
        else:
            base = (self._granary_food_ini[-1]
                    + self._granary_food_inc * (size - len(self._granary_food_ini)))
        return max(1, int(math.ceil(base * self.foodbox_percent / 100.0)))

    def _population_ready_eta(self, city, required_size):
        """Conservatively project turns until a population-costing build can finish.

        Food surplus is held at its current authoritative value and food retained
        by unknown city improvements is not assumed. This may reject a marginal
        build, but it cannot invent population that the city has not grown yet.
        """
        size = max(1, int(city.size or 1))
        target = max(1, int(required_size))
        if size >= target:
            return 0
        food = self._city_output(city, 0)
        if food <= 0:
            return None
        stock = max(0, int(city.food_stock or 0))
        turns = 0
        while size < target:
            cost = self._growth_food_cost(size)
            turns += int(math.ceil(max(0, cost - stock) / float(food)))
            size += 1
            stock = 0
        return turns

    def _production_projection(
            self, city, name, remaining_turns, snapshot=None, founder_types=(),
            shield_stock_override=None):
        """Estimate whether production can affect the declared score horizon.

        This is deliberately a small, auditable projection rather than a game
        simulator.  Ruleset build cost and authoritative city surplus establish
        completion time.  The value terms mirror score-bearing mechanisms:
        population growth, technology throughput, expansion, and unit output.
        """
        normalized = _normalized_type(name)
        cost = self._build_costs.get(normalized)
        spec = self._production_specs.get(normalized, {})
        shields = self._city_output(city, 1)
        stock = max(0, int(
            city.shield_stock or 0) if shield_stock_override is None
            else int(shield_stock_override))
        if cost is None and normalized:
            # Unit tests and lightweight consumers may construct the planner
            # without a compiled IR. Preserve a conservative bounded fallback;
            # release evaluation always injects the active ruleset IR.
            shield_eta = self.production_minimum_remaining_turns
        else:
            shield_eta = (
                0 if stock >= cost else
                None if shields <= 0 else
                int(math.ceil((cost - stock) / float(shields))))
        eta = shield_eta
        population_eta = 0
        if normalized in founder_types and int(spec.get("pop_cost", 0)) > 0:
            population_eta = self._population_ready_eta(
                city, int(spec.get("pop_cost", 0)) + 1)
            eta = (None if shield_eta is None or population_eta is None
                   else max(shield_eta, population_eta))
        active_turns = (None if eta is None else max(0, int(remaining_turns) - eta))
        projection = {
            "active_turns": active_turns, "build_cost": cost,
            "cost_source": "ruleset_ir" if cost is not None else "bounded_fallback",
            "completion_eta_turns": eta, "remaining_turns": int(remaining_turns),
            "pop_cost": int(spec.get("pop_cost", 0)),
            "projected_shield_stock": stock,
            "shield_completion_eta_turns": shield_eta,
            "shield_surplus": shields, "score_value": 0.0,
        }
        if normalized in founder_types:
            projection["founder_capable"] = True
            projection["founder_capability_source"] = (
                self._founder_capability_source(normalized)
                or "current_server_legal_action:unit_build_city")
            projection["growth_cost_source"] = self._growth_cost_source
            projection["population_ready_eta_turns"] = population_eta
        if eta is None:
            return projection

        if (spec.get("target_kind") == "unit"
                and normalized not in founder_types
                and int(spec.get("pop_cost", 0)) == 0):
            repeat_eta = (None if cost is None or shields <= 0 else
                          max(1, int(math.ceil(cost / float(shields)))))
            projected_completions = (
                0 if repeat_eta is None or active_turns < 0 else
                1 + active_turns // repeat_eta)
            unit_score_progress = (
                projected_completions / float(self.unit_build_score_divisor))
            projection.update({
                "projected_unit_completions": projected_completions,
                "repeat_completion_eta_turns": repeat_eta,
                "projected_unit_score_progress": unit_score_progress,
                "guaranteed_unit_score_points": (
                    projected_completions // self.unit_build_score_divisor),
                "unit_build_score_divisor": self.unit_build_score_divisor,
                "score_value": unit_score_progress,
            })

        food = self._city_output(city, 0)
        science = self._city_output(city, 5)
        growth_cost = self._growth_food_cost(city.size)
        growth_eta = self._population_ready_eta(city, int(city.size or 1) + 1)
        if normalized in founder_types:
            # A completed founder needs time to move and establish a score-bearing
            # city. Charge its exact ruleset population cost rather than assuming
            # that every terrain worker is able to establish a city.
            route_eta, route_eta_source = self._founder_route_eta()
            settlement_runway = max(0, active_turns - route_eta)
            projection["score_value"] = max(
                0.0, 1.0 - projection["pop_cost"]
                + settlement_runway * 0.15)
            projection["founder_route_eta_turns"] = route_eta
            projection["founder_route_eta_source"] = route_eta_source
            projection["settlement_eta_turns"] = eta + route_eta
            projection["settlement_runway_turns"] = settlement_runway
        elif normalized == "granary":
            useful_growths = (0 if not food or active_turns <= 0 else
                              max(0, 1 + (active_turns - max(1, growth_eta))
                                  // max(1, growth_cost // max(1, food))))
            projection["growth_eta_turns"] = growth_eta
            projection["projected_growth_opportunities"] = useful_growths
            projection["score_value"] = float(useful_growths)
            if cost is None and active_turns > 0:
                projection["score_value"] = active_turns / 100.0
        elif normalized == "library":
            research = getattr(snapshot, "research", None)
            research_cost = int(getattr(research, "cost", 0) or 0)
            research_progress = int(getattr(research, "progress", 0) or 0)
            beakers_per_turn = int(getattr(research, "beakers_per_turn", 0) or 0)
            library_bonus = int(math.ceil(science * 0.5))
            natural_bulbs = research_progress + beakers_per_turn * remaining_turns
            projected_bulbs = natural_bulbs + library_bonus * active_turns
            natural_techs = natural_bulbs // research_cost if research_cost else 0
            projected_techs = projected_bulbs // research_cost if research_cost else 0
            score_techs = max(0, projected_techs - natural_techs)
            projection["projected_science_bonus"] = library_bonus * active_turns
            projection["projected_additional_technologies"] = score_techs
            projection["research_cost"] = research_cost
            projection["score_value"] = float(score_techs * 2)
        elif normalized == "marketplace":
            trade = self._city_output(city, 2)
            projection["projected_trade"] = trade * active_turns
            # Gold and trade are not direct FreeCiv score components. Keep the
            # telemetry, but do not claim a fixed-horizon score gain.
            projection["score_value"] = 0.0
        elif name in DEFENDER_PRIORITY:
            # The pinned server scores cumulative units built in groups. The
            # repeated-production projection above records both fractional
            # progress and whole guaranteed score points.
            pass
        elif name in IMPROVEMENT_PRIORITY:
            projection["score_value"] = 0.0
        else:
            # Unknown current targets still receive a completion value. This
            # prevents destructive churn away from a ruleset-valid near-finished
            # build while permitting a switch away from one that cannot finish.
            projection["score_value"] = 0.5 if active_turns > 0 else 0.0
        return projection

    def _static_production_candidate(
            self, snapshot, action, city, name, normalized, current_name,
            current_normalized, founders, city_count, needs_founder,
            remaining_turns):
        """Frozen pre-hardening production policy for paired baselines."""
        if needs_founder and current_normalized in LEGACY_FOUNDER_TYPES:
            return None
        if (needs_founder and normalized in LEGACY_FOUNDER_TYPES
                and remaining_turns >= self.expansion_minimum_remaining_turns):
            return ImpactCandidate(
                action, "production_expansion", 920.0 + remaining_turns,
                "static baseline: produce one founder with fixed runway")
        if remaining_turns < self.production_minimum_remaining_turns:
            return None
        defenders = self._legacy_combat_units(snapshot)
        defense_deficit = len(defenders) < max(1, city_count)
        if defense_deficit and current_name in DEFENDER_PRIORITY:
            return None
        if defense_deficit:
            for index, target in enumerate(DEFENDER_PRIORITY):
                if name.lower() == target.lower():
                    return ImpactCandidate(
                        action, "production_defense",
                        850.0 - index + remaining_turns,
                        "static baseline: cover the city-defense deficit")
        if current_name in IMPROVEMENT_PRIORITY:
            return None
        for index, target in enumerate(IMPROVEMENT_PRIORITY):
            if name.lower() == target.lower():
                return ImpactCandidate(
                    action, "production_economy",
                    740.0 - index + remaining_turns,
                    "static baseline: select priority-ordered economy production")
        for index, target in enumerate(DEFENDER_PRIORITY):
            if name.lower() == target.lower():
                return ImpactCandidate(
                    action, "production_military",
                    520.0 - index + remaining_turns,
                    "static baseline: select priority-ordered military production")
        return None

    @staticmethod
    def _projection_can_affect_horizon(projection, minimum_active_turns=1):
        eta = projection.get("completion_eta_turns")
        active = projection.get("active_turns")
        return bool(eta is not None and active is not None
                    and active >= int(minimum_active_turns))

    def _queued_founder_count(self, snapshot, founder_types, remaining_turns):
        """Count only founder builds projected to settle by the horizon."""
        count = 0
        for queued_city in snapshot.cities:
            queued_name = self._current_production_name(queued_city)
            if _normalized_type(queued_name) not in founder_types:
                continue
            projection = self._production_projection(
                queued_city, queued_name, remaining_turns, snapshot=snapshot,
                founder_types=founder_types)
            if (projection.get("settlement_eta_turns") is not None
                    and projection["settlement_eta_turns"] <= remaining_turns):
                count += 1
        return count

    def _unit_score_batch_members(self, snapshot, actions, founder_types):
        """Select a lossless city batch that guarantees incremental unit score.

        Freeciv's units-built counter is civilization-wide. A city-local threshold
        misses batches where several productive cities jointly add ten builds. The
        batch compares optimized future completions with the exact current production
        trajectory and commits its members one confirmed production change at a time.
        """
        intent = self._unit_score_batch_intent
        legal_keys = frozenset(
            canonical_json_bytes(action).decode("utf-8") for action in actions)
        if isinstance(intent, dict):
            if int(intent.get("turn", -1)) != int(snapshot.turn):
                self._unit_score_batch_intent = None
            elif intent.get("awaiting") is not None:
                return {}
            else:
                intent["remaining"].intersection_update(legal_keys)
                if not intent["remaining"]:
                    self._unit_score_batch_intent = None
                else:
                    return {
                        key: dict(intent["projection"])
                        for key in intent["remaining"]}

        cache_key = (
            snapshot.snapshot_id, tuple(sorted(legal_keys)),
            tuple(sorted(founder_types)))
        if cache_key == self._unit_score_batch_cache_key:
            return {key: dict(value)
                    for key, value in self._unit_score_batch_cache.items()}

        remaining_turns = self.horizon_turn - snapshot.turn
        current_by_city = {}
        current_score_bearing_nonunit = set()
        best_by_city = {}
        best_action_by_city = {}
        for city in snapshot.cities:
            current_name = self._current_production_name(city)
            current_projection = self._production_projection(
                city, current_name, remaining_turns, snapshot=snapshot,
                founder_types=founder_types) if current_name else {}
            completions = int(current_projection.get(
                "projected_unit_completions", 0))
            if ("projected_unit_completions" not in current_projection
                    and float(current_projection.get("score_value", 0.0)) > 0):
                current_score_bearing_nonunit.add(city.city_id)
            current_by_city[city.city_id] = completions
            best_by_city[city.city_id] = completions

        for action in actions:
            if action.get("action_type") != "city_production":
                continue
            city = snapshot.city(action.get("city_id"))
            if (city is None or not city.buildability_available
                    or city.shield_stock != 0
                    or city.city_id in current_score_bearing_nonunit
                    or self._current_production_matches(city, action)):
                continue
            name = _target_name(action)
            if not any(name.lower() == target.lower()
                       for target in DEFENDER_PRIORITY):
                continue
            projection = self._production_projection(
                city, name, remaining_turns, snapshot=snapshot,
                founder_types=founder_types)
            if not self._projection_can_affect_horizon(projection):
                continue
            completions = int(projection.get("projected_unit_completions", 0))
            action_key = canonical_json_bytes(action).decode("utf-8")
            previous = best_action_by_city.get(city.city_id)
            if (completions > best_by_city[city.city_id]
                    or (completions == best_by_city[city.city_id]
                        and completions > current_by_city[city.city_id]
                        and (previous is None or action_key < previous[0]))):
                best_by_city[city.city_id] = completions
                best_action_by_city[city.city_id] = (action_key, projection)

        current_total = sum(current_by_city.values())
        optimized_total = sum(best_by_city.values())
        incremental = optimized_total - current_total
        guaranteed = incremental // self.unit_build_score_divisor
        if guaranteed <= 0:
            self._unit_score_batch_cache_key = cache_key
            self._unit_score_batch_cache = {}
            return {}
        action_keys = tuple(sorted(
            row[0] for row in best_action_by_city.values()))
        batch_projection = {
            "batch_action_keys": list(action_keys),
            "batch_current_projected_unit_completions": current_total,
            "batch_optimized_projected_unit_completions": optimized_total,
            "batch_incremental_unit_completions": incremental,
            "batch_guaranteed_unit_score_points": guaranteed,
            "batch_selected_city_count": len(action_keys),
        }
        result = {key: dict(batch_projection) for key in action_keys}
        self._unit_score_batch_cache_key = cache_key
        self._unit_score_batch_cache = result
        return {key: dict(value) for key, value in result.items()}

    def _preexpansion_growth_candidate(
            self, snapshot, action, actions, city, projection, founder_types,
            founder_deficit, current_normalized, remaining_turns):
        """Sequence a Granary before the last founder only with full runway.

        Population-costing founders can erase capital growth when they are queued
        long before their settlement is needed. The sequence is deliberately
        conservative: it assumes zero shields carry from the Granary, grants no
        Granary food-retention benefit to the founder ETA, and requires the new
        city to retain the normal minimum active runway after settlement.
        """
        if (founder_deficit != 1 or current_normalized in founder_types
                or _normalized_type(_target_name(action)) != "granary"
                or projection.get("score_value", 0.0) <= 0
                or not self._projection_can_affect_horizon(projection)):
            return None
        granary_eta = int(projection["completion_eta_turns"])
        founder_remaining = int(remaining_turns) - granary_eta
        if founder_remaining < self.expansion_minimum_remaining_turns:
            return None
        best = None
        for founder_action in actions:
            if (founder_action.get("action_type") != "city_production"
                    or founder_action.get("city_id") != city.city_id):
                continue
            founder_name = _target_name(founder_action)
            if _normalized_type(founder_name) not in founder_types:
                continue
            founder_projection = self._production_projection(
                city, founder_name, founder_remaining, snapshot=snapshot,
                founder_types=founder_types, shield_stock_override=0)
            if int(founder_projection.get("pop_cost", 0)) <= 0:
                continue
            settlement_eta = founder_projection.get("settlement_eta_turns")
            if settlement_eta is None:
                continue
            combined_eta = granary_eta + int(settlement_eta)
            settlement_runway = int(remaining_turns) - combined_eta
            if (combined_eta > remaining_turns
                    or settlement_runway < self.production_minimum_remaining_turns
                    or founder_projection.get("score_value", 0.0) <= 0):
                continue
            action_key = canonical_json_bytes(founder_action).decode("utf-8")
            rank = (combined_eta, action_key)
            if best is None or rank < best[0]:
                best = (rank, founder_name, founder_projection,
                        combined_eta, settlement_runway)
        if best is None:
            return None
        _, founder_name, founder_projection, combined_eta, settlement_runway = best
        projection.update({
            "founder_deficit_before": founder_deficit,
            "preexpansion_founder": founder_name,
            "preexpansion_founder_completion_eta_turns": (
                founder_projection.get("completion_eta_turns")),
            "preexpansion_founder_population_ready_eta_turns": (
                founder_projection.get("population_ready_eta_turns")),
            "preexpansion_founder_score_value": founder_projection["score_value"],
            "preexpansion_sequence_settlement_eta_turns": combined_eta,
            "preexpansion_sequence_settlement_runway_turns": settlement_runway,
            "preexpansion_shield_stock_assumption": 0,
        })
        return ImpactCandidate(
            action, "production_preexpansion_growth",
            950.0 + projection["score_value"] * 10.0 - granary_eta,
            "complete score-bearing growth infrastructure before the final "
            "population-costing founder while preserving conservative settlement "
            "and active-city runway",
            projection)

    def _production_candidate(self, snapshot, action, founder_types, actions):
        city = snapshot.city(action.get("city_id"))
        if city is None or not city.buildability_available:
            return None
        if self._current_production_matches(city, action):
            return None
        name = _target_name(action)
        normalized = _normalized_type(name)
        city_count = len(snapshot.cities)
        current_name = self._current_production_name(city)
        current_normalized = _normalized_type(current_name)
        remaining_turns = self.horizon_turn - snapshot.turn
        if self.production_strategy == "static_priority":
            # The paired baseline retains its original lossless-boundary rule.
            if city.shield_stock not in (None, 0):
                return None
            legacy_founders = tuple(
                unit for unit in snapshot.units
                if _normalized_type(unit.unit_type) in LEGACY_FOUNDER_TYPES)
            legacy_needs_founder = (
                city_count < self.expansion_city_target and not legacy_founders)
            return self._static_production_candidate(
                snapshot, action, city, name, normalized, current_name,
                current_normalized, legacy_founders, city_count,
                legacy_needs_founder,
                remaining_turns)
        founders = self._founders(snapshot, founder_types)
        queued_founders = self._queued_founder_count(
            snapshot, founder_types, remaining_turns)
        expansion_capacity = city_count + len(founders) + queued_founders
        founder_deficit = max(0, self.expansion_city_target - expansion_capacity)
        needs_founder = founder_deficit > 0
        current_projection = (self._production_projection(
            city, current_name, remaining_turns, snapshot=snapshot,
            founder_types=founder_types)
                              if current_name else None)
        current_queue_counted = int(
            current_normalized in founder_types
            and current_projection is not None
            and current_projection.get("settlement_eta_turns") is not None
            and current_projection["settlement_eta_turns"] <= remaining_turns)
        expansion_capacity_without_current = (
            expansion_capacity - current_queue_counted)
        current_is_redundant_founder = (
            current_normalized in founder_types
            and expansion_capacity_without_current >= self.expansion_city_target)
        current_pop_cost = int(self._production_specs.get(
            current_normalized, {}).get("pop_cost", 0))
        current_completes_by_horizon = bool(
            current_projection is not None
            and current_projection.get("completion_eta_turns") is not None
            and current_projection["completion_eta_turns"] <= remaining_turns)
        urgent_founder_repurpose = bool(
            current_is_redundant_founder and current_pop_cost > 0
            and current_completes_by_horizon)

        # Normal changes remain lossless at an empty stock boundary. A redundant
        # positive-population founder is the sole exception: completing it and
        # automatically repeating it costs citizens. Project the replacement as
        # if every accumulated shield were discarded, so the exception cannot
        # invent carry-over value.
        if city.shield_stock not in (None, 0) and not urgent_founder_repurpose:
            return None
        projection = self._production_projection(
            city, name, remaining_turns, snapshot=snapshot,
            founder_types=founder_types,
            shield_stock_override=(0 if urgent_founder_repurpose else None))
        if normalized in founder_types:
            projection.update({
                "existing_founders": len(founders),
                "expansion_capacity_before": expansion_capacity,
                "founder_deficit_before": founder_deficit,
                "queued_founders": queued_founders,
            })

        if urgent_founder_repurpose:
            target_pop_cost = int(self._production_specs.get(
                normalized, {}).get("pop_cost", 0))
            priorities = IMPROVEMENT_PRIORITY + DEFENDER_PRIORITY
            target_index = next((
                index for index, target in enumerate(priorities)
                if name.lower() == target.lower()), None)
            if (target_index is None or normalized in founder_types
                    or target_pop_cost > 0):
                return None
            completion_eta = projection.get("completion_eta_turns")
            projection.update({
                "avoided_population_cost": current_pop_cost,
                "expansion_capacity_without_current": (
                    expansion_capacity_without_current),
                "repurpose_discarded_shield_stock": max(
                    0, int(city.shield_stock or 0)),
                "repurpose_shield_stock_assumption": 0,
                "repurpose_target_completes_by_horizon": bool(
                    completion_eta is not None
                    and completion_eta <= remaining_turns),
            })
            eta_penalty = (remaining_turns + 1 if completion_eta is None
                           else completion_eta)
            return ImpactCandidate(
                action, "production_repurpose",
                900.0 + current_pop_cost * 20.0
                + projection["score_value"] * 10.0
                - eta_penalty - target_index * 0.01,
                "retire population-costing founder production while expansion "
                "capacity remains at target without its current queue",
                projection)

        unit_score_batch = self._unit_score_batch_members(
            snapshot, actions, founder_types).get(
                canonical_json_bytes(action).decode("utf-8"))
        if needs_founder and current_normalized in founder_types:
            return None
        preexpansion_growth = self._preexpansion_growth_candidate(
            snapshot, action, actions, city, projection, founder_types,
            founder_deficit, current_normalized, remaining_turns)
        if preexpansion_growth is not None:
            return preexpansion_growth
        if (needs_founder and normalized in founder_types
                and remaining_turns >= self.expansion_minimum_remaining_turns
                and projection.get("settlement_eta_turns") is not None
                and projection["settlement_eta_turns"] <= remaining_turns
                and projection["score_value"] > 0):
            return ImpactCandidate(
                action, "production_expansion",
                920.0 + projection["score_value"] * 10.0
                - projection["completion_eta_turns"],
                "fill the grounded city-plus-founder capacity deficit when the "
                "configured start runway and exact ruleset build, population, and "
                "route ETA project positive score value by the horizon",
                projection)

        # Protect expansion capacity: when the target has not been met and no
        # founder exists, economy or military production must not displace the
        # legal founder opportunity.
        if needs_founder:
            return None

        # A late accepted switch can register as transport activity while being
        # unable to finish before fixed-horizon scoring.  Do not spend policy
        # budget or trigger a treatment failover on such non-evaluable changes.
        if remaining_turns < self.production_minimum_remaining_turns:
            return None

        if not self._projection_can_affect_horizon(projection):
            return None

        defenders = self._combat_units(snapshot, founder_types)
        defense_deficit = len(defenders) < max(1, city_count)
        if defense_deficit and current_name in DEFENDER_PRIORITY:
            return None
        if defense_deficit:
            for index, target in enumerate(DEFENDER_PRIORITY):
                if name.lower() == target.lower():
                    return ImpactCandidate(
                        action, "production_defense",
                        850.0 + projection["score_value"] * 10.0
                        - projection["completion_eta_turns"] - index * 0.01,
                        "cover the city-defense deficit with a horizon-completing unit",
                        projection)

        for index, target in enumerate(IMPROVEMENT_PRIORITY):
            if name.lower() == target.lower():
                # Keep a current valid target when it completes in time and is
                # projected at least as valuable. Switching at zero shields is
                # lossless mechanically, but can still destroy a good trajectory.
                if (current_projection is not None
                        and self._projection_can_affect_horizon(current_projection)
                        and not current_is_redundant_founder
                        and current_projection["score_value"] >= projection["score_value"]):
                    return None
                if projection["score_value"] <= 0:
                    return None
                return ImpactCandidate(
                    action, "production_economy",
                    740.0 + projection["score_value"] * 10.0
                    - projection["completion_eta_turns"] - index * 0.01,
                    "select score-bearing economy production using build ETA and city output",
                    projection)

        for index, target in enumerate(DEFENDER_PRIORITY):
            if name.lower() != target.lower():
                continue
            if not current_is_redundant_founder and unit_score_batch is None:
                continue
            if (not current_is_redundant_founder
                    and unit_score_batch is None
                    and current_projection is not None
                    and self._projection_can_affect_horizon(current_projection)
                    and current_projection["score_value"] >= projection["score_value"]):
                continue
            category = ("production_repurpose" if current_is_redundant_founder
                        else "production_military_score")
            if unit_score_batch is not None:
                projection.update(unit_score_batch)
            base_utility = 700.0 if current_is_redundant_founder else 740.0
            reason = (
                "retire redundant founder production into a horizon-completing "
                "defender without further population cost"
                if current_is_redundant_founder else
                "select a confirmed city batch whose incremental repeated unit "
                "production guarantees fixed-horizon units-built score")
            return ImpactCandidate(
                action, category,
                base_utility + projection["score_value"] * 10.0
                - projection["completion_eta_turns"] - index * 0.01,
                reason, projection)

        # Sub-threshold non-deficit unit churn remains excluded unless it
        # retires a now-redundant founder build.
        return None

    def _move_is_nonprogress(self, snapshot, action, founder_types):
        """Distinguish targetless/revisiting moves from safety exclusions."""
        unit = snapshot.unit(action.get("actor_id"))
        target = action.get("target", {})
        if unit is None or not isinstance(target, dict):
            return False
        x, y = target.get("x"), target.get("y")
        if x is None or y is None or (unit.x, unit.y) == (x, y):
            return False
        unit_type = _normalized_type(unit.unit_type)
        if unit_type in founder_types or unit_type in self._ruleset_worker_types:
            return False
        if self._city_defender_is_required(snapshot, unit, founder_types):
            return False
        if unit_type in EXPLORER_TYPES:
            hut_distances = self._hut_route_distances(snapshot, unit, x, y)
            if hut_distances is not None and hut_distances[1] < hut_distances[0]:
                return False
        enemies = [row for row in snapshot.visible_enemy_units
                   if row.x is not None and row.y is not None]
        if enemies:
            current_distance = min(_distance(
                unit.x, unit.y, row.x, row.y,
                snapshot.map_width, snapshot.map_height) for row in enemies)
            target_distance = min(_distance(
                x, y, row.x, row.y, snapshot.map_width, snapshot.map_height)
                                  for row in enemies)
            if target_distance < current_distance:
                return False
        return not (unit_type in EXPLORER_TYPES
                    and (x, y) not in self.visited_positions)

    def _move_candidate(self, snapshot, action, founder_types):
        unit = snapshot.unit(action.get("actor_id"))
        target = action.get("target", {})
        if unit is None or not isinstance(target, dict):
            return None
        x, y = target.get("x"), target.get("y")
        if x is None or y is None or (unit.x, unit.y) == (x, y):
            return None
        # A plain move cannot enter a packet-visible non-owned stack. The
        # server must advertise an explicit attack, conquest, or diplomatic
        # action for that target instead.
        if any((row.x, row.y) == (x, y)
               for row in snapshot.visible_enemy_units):
            return None
        unit_type = _normalized_type(unit.unit_type)
        novelty = 1.0 if (x, y) not in self.visited_positions else 0.0
        city_distance = self._distance_from_cities(snapshot, x, y)
        if unit_type in founder_types:
            if len(snapshot.cities) >= self.expansion_city_target:
                if (self.production_strategy != "horizon_score"
                        or unit_type not in self._ruleset_add_to_city_types):
                    return None
                spec = self._production_specs.get(unit_type, {})
                population = int(spec.get("pop_cost", 0))
                if population <= 0 or not snapshot.cities:
                    return None
                current_distance = min(_distance(
                    unit.x, unit.y, city.x, city.y,
                    snapshot.map_width, snapshot.map_height)
                                       for city in snapshot.cities)
                target_distance = min(_distance(
                    x, y, city.x, city.y,
                    snapshot.map_width, snapshot.map_height)
                                      for city in snapshot.cities)
                if target_distance >= current_distance:
                    return None
                nearest_city_ids = sorted(
                    city.city_id for city in snapshot.cities
                    if _distance(x, y, city.x, city.y,
                                 snapshot.map_width, snapshot.map_height)
                    == target_distance)
                return ImpactCandidate(
                    action, "population_recovery_move",
                    970.0 + population * 5.0 - target_distance,
                    "strictly reduce a surplus founder's distance to an owned "
                    "city for exact ruleset population recovery",
                    {"current_city_distance": current_distance,
                     "recovered_population": population,
                     "target_city_distance": target_distance,
                     "target_city_ids": nearest_city_ids})
            projection = None
            route_utility = 0.0
            utility = 800.0 + city_distance * 20.0 + novelty * 15.0
            if self.production_strategy == "horizon_score":
                evidence = self._founder_move_evidence(
                    snapshot, action, founder_types)
                # Direct actor-local evidence is strong enough to prune this
                # unchanged edge. Cross-actor evidence is only a preference:
                # transient occupancy must not make a legal corridor disappear.
                if evidence.get("actor_failed"):
                    return None
                separation_gain = self._founder_city_separation_gain(
                    snapshot, unit, x, y)
                current_city_distance = self._distance_from_cities(
                    snapshot, unit.x, unit.y)
                route_progress = city_distance >= current_city_distance
                route_utility = (
                    separation_gain * int(current_city_distance == 0)
                    * self.FOUNDER_CITY_SEPARATION_WEIGHT
                    + int(evidence.get("cardinal_corridor_match", False))
                    * self.FOUNDER_CARDINAL_CORRIDOR_BONUS
                    + int(route_progress and evidence.get("traversable_edge", False))
                    * self.FOUNDER_TRAVERSABLE_EDGE_BONUS
                    - min(2, int(evidence.get("failed_attempts", 0)))
                    * self.FOUNDER_FAILED_EDGE_PENALTY)
                projection = {
                    "city_separation_gain": separation_gain,
                    "city_separation_tiebreak_active": (
                        current_city_distance == 0),
                    "cardinal_corridor_match": bool(
                        evidence.get("cardinal_corridor_match", False)),
                    "failed_edge_attempts": int(
                        evidence.get("failed_attempts", 0)),
                    "founder_route_eta_turns": self._founder_route_eta()[0],
                    "traversable_edge": bool(
                        route_progress and evidence.get("traversable_edge", False)),
                }
                utility += route_utility
            return ImpactCandidate(
                action, "expansion_move", utility,
                "move a founder toward settlement using grounded route evidence",
                projection)

        # The ruleset's worker flag is broader than city-founding capability.
        # Sending non-founder workers toward the frontier consumed movement and
        # action budget without creating any score-bearing settlement path.
        if unit_type in self._ruleset_worker_types:
            return None

        if self._city_defender_is_required(snapshot, unit, founder_types):
            return None
        if unit_type in EXPLORER_TYPES:
            hut_distances = self._hut_route_distances(snapshot, unit, x, y)
            if hut_distances is not None and hut_distances[1] < hut_distances[0]:
                current_hut_distance, target_hut_distance = hut_distances
                return ImpactCandidate(
                    action, "hut_exploration",
                    940.0 - target_hut_distance * 8.0 + novelty * 5.0,
                    "strictly reduce distance to an exact packet-known hut",
                    {"current_hut_distance": current_hut_distance,
                     "target_hut_distance": target_hut_distance,
                     "target_is_known_hut": target_hut_distance == 0})
        enemies = [row for row in snapshot.visible_enemy_units
                   if row.x is not None and row.y is not None]
        if enemies:
            current_enemy_distance = min(_distance(
                unit.x, unit.y, row.x, row.y,
                snapshot.map_width, snapshot.map_height) for row in enemies)
            target_enemy_distance = min(_distance(
                x, y, row.x, row.y, snapshot.map_width, snapshot.map_height)
                                        for row in enemies)
            if target_enemy_distance < current_enemy_distance:
                return ImpactCandidate(
                    action, "tactical_move",
                    700.0 - target_enemy_distance * 12.0 + novelty * 5.0,
                    "strictly reduce distance to a packet-visible opponent")
        if unit_type in EXPLORER_TYPES and novelty:
            if self._exploration_destination_reliably_failed(snapshot, action):
                self._failed_exploration_prunes.add(
                    canonical_json_bytes(action).decode("utf-8"))
                return None
            return ImpactCandidate(
                action, "exploration_move",
                610.0 + city_distance * 5.0 + novelty * 25.0,
                "reveal a new position with an exploration-capable unit")
        return None

    def _population_recovery_candidate(self, snapshot, action, founder_types):
        """Recover ruleset-declared founder population after expansion is complete."""
        if (self.production_strategy != "horizon_score"
                or len(snapshot.cities) < self.expansion_city_target):
            return None
        unit = snapshot.unit(action.get("actor_id"))
        target = action.get("target")
        city_id = target.get("city_id") if isinstance(target, dict) else None
        city = snapshot.city(city_id) if city_id is not None else None
        if unit is None or city is None or unit.tile is None or city.tile is None:
            return None
        normalized = _normalized_type(unit.unit_type)
        # Exact Cities and AddToCity capabilities together prove that this is
        # a founder the server may consume for the advertised recovery action.
        if (normalized not in self._ruleset_founder_types
                or normalized not in self._ruleset_add_to_city_types):
            return None
        spec = self._production_specs.get(normalized, {})
        population = int(spec.get("pop_cost", 0))
        if population <= 0 or unit.tile != city.tile:
            return None
        return ImpactCandidate(
            action, "population_recovery", 990.0 + population,
            "restore a surplus founder's exact ruleset population cost after "
            "the expansion target is complete",
            {"recovered_population": population,
             "population_value_source": "ruleset_ir",
             "target_city_id": city.city_id})

    @staticmethod
    def _offensive_target_is_visible(snapshot, action):
        """Require packet-visible opposition before issuing an attack order.

        FreeCiv can accept an attack order toward an empty/unknown adjacent tile.
        Treating transport acceptance as tactical impact caused the planner to
        spend its whole action budget on harmless orders.  Visibility is the
        grounded effect precondition; the execution gate remains the final
        legality precondition.
        """
        target = action.get("target")
        if not isinstance(target, dict):
            return False
        target_unit = target.get("target_unit_id")
        if target_unit is not None:
            return snapshot.visible_enemy_unit(target_unit) is not None
        x, y = target.get("x"), target.get("y")
        if x is None or y is None:
            return False
        return any((row.x, row.y) == (x, y) for row in snapshot.visible_enemy_units)

    def candidates(self, snapshot, excluded=(), excluded_scopes=()):
        excluded = set(excluded)
        excluded_scopes = set(excluded_scopes)
        result = []
        actions = self._actions(snapshot)
        available_actions = tuple(
            action for action in actions
            if canonical_json_bytes(action).decode("utf-8") not in excluded)
        founder_types = self._founder_types(snapshot, actions)
        for action in actions:
            key = canonical_json_bytes(action).decode("utf-8")
            if key in excluded:
                continue
            action_type = str(action.get("action_type", ""))
            candidate = None
            if (action_type in OFFENSIVE_ACTIONS
                    and self._offensive_target_is_visible(snapshot, action)):
                candidate = ImpactCandidate(
                    action, "tactical_attack", 980.0,
                    "execute an exact server-advertised offensive action")
            elif action_type == "unit_build_city":
                unit = snapshot.unit(action.get("actor_id"))
                if (unit is not None and len(snapshot.cities) < self.expansion_city_target
                        and self._distance_from_cities(snapshot, unit.x, unit.y)
                        >= self.settle_min_distance):
                    candidate = ImpactCandidate(
                        action, "city_founding", 1000.0,
                        "found a city at or beyond the configured spacing")
            elif action_type == "unit_join_city":
                candidate = self._population_recovery_candidate(
                    snapshot, action, founder_types)
            elif action_type == "city_production":
                candidate = self._production_candidate(
                    snapshot, action, founder_types, available_actions)
            elif action_type == "unit_move":
                candidate = self._move_candidate(snapshot, action, founder_types)
            elif action_type == "unit_fortify":
                unit = snapshot.unit(action.get("actor_id"))
                if (unit is not None and unit.unit_id not in self._fortified_units
                        and self._city_defender_is_required(
                            snapshot, unit, founder_types)):
                    candidate = ImpactCandidate(
                        action, "city_defense", 680.0,
                        "fortify the sole grounded city defender")
            if candidate is not None and candidate.scope not in excluded_scopes:
                if not self._no_effect_suppressed(snapshot, candidate):
                    result.append(candidate)
        return tuple(sorted(result, key=lambda row: (
            -row.utility, row.category, row.action_key)))

    def plan(self, snapshot, excluded=(), excluded_scopes=()):
        rows = self.candidates(
            snapshot, excluded=excluded, excluded_scopes=excluded_scopes)
        if not rows:
            return None
        candidate = rows[0]
        if (candidate.category == "production_military_score"
                and self._unit_score_batch_intent is None):
            projection = candidate.projection or {}
            action_keys = projection.get("batch_action_keys", ())
            if action_keys:
                self._unit_score_batch_intent = {
                    "awaiting": candidate.action_key,
                    "projection": {
                        key: value for key, value in projection.items()
                        if key.startswith("batch_")},
                    "remaining": set(action_keys),
                    "turn": int(snapshot.turn),
                }
        elif (candidate.category == "production_military_score"
              and isinstance(self._unit_score_batch_intent, dict)):
            self._unit_score_batch_intent["awaiting"] = candidate.action_key
        proof_hash = structural_hash({
            "action": candidate.action, "category": candidate.category,
            "projection": candidate.projection,
            "snapshot_id": snapshot.snapshot_id,
        })
        step_id = "impact-step-" + proof_hash[:16]
        step = PlanStep(
            step_id, "engine-action", candidate.action, snapshot.turn, 0, 0.0,
            status="ACTIVE", snapshot_id=snapshot.snapshot_id,
            legal_actions_digest=snapshot.legal_actions_digest)
        scheduler_cost = max(0.0, 1000.0 - candidate.utility)
        branch = BranchScore(
            "impact-" + candidate.category, 1.0, scheduler_cost, 0, True)
        plan_id = "impact-plan-" + structural_hash([
            proof_hash, step.to_dict(), branch.to_dict()])[:20]
        plan = Plan(
            plan_id, "grounded-impact:{}".format(candidate.category), proof_hash,
            snapshot.snapshot_id, (step,), ResourceLedger(), (branch,),
            branch.branch_id, "grounded-impact-utility", scheduler_cost, 1.0, 0,
            self.SOLVER_IDENTITY)
        return ImpactDecision(candidate, plan)
