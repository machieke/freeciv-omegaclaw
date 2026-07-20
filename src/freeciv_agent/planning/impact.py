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
            "unit_build_city", "unit_suicide_attack")

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

    SOLVER_IDENTITY = "grounded-impact-planner/1.0"

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
        self._server_founder_types = set()
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
        an exact city-target predicate; unit actions use actor-local resource
        changes; only action kinds without a local grounding use the general
        state hash as a final fallback.
        """
        action = candidate.action
        if action.get("action_type") == "city_production":
            city = after.city(action.get("city_id"))
            kind = action.get("production_kind")
            value = action.get("production_value")
            return bool(city is not None and kind is not None and value is not None
                        and city.production_kind == int(kind)
                        and city.production_value == int(value))
        if action.get("actor_id") is not None:
            return self.local_actor_effect_observed(candidate, before, after)
        return before.identity.state_hash != after.identity.state_hash

    def _grounding_signature(self, snapshot, candidate):
        """Hash only the local authoritative facts that can change an outcome."""
        action = candidate.action
        actor_id = action.get("actor_id")
        city_id = action.get("city_id")
        actor = snapshot.unit(actor_id) if actor_id is not None else None
        city = snapshot.city(city_id) if city_id is not None else None
        target = action.get("target")
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

    def record_outcome(self, candidate, snapshot, effect_observed):
        """Learn from an accepted action without treating acceptance as effect.

        Exact no-effect actions are suppressed while their local authoritative
        grounding is unchanged.  Movement refreshes and unrelated economic state
        cannot make an unreachable order eligible again; actor, city, or visible
        target changes can.
        """
        self.commit(candidate)
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

    def _production_projection(
            self, city, name, remaining_turns, snapshot=None, founder_types=()):
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
        stock = max(0, int(city.shield_stock or 0))
        if cost is None and normalized:
            # Unit tests and lightweight consumers may construct the planner
            # without a compiled IR. Preserve a conservative bounded fallback;
            # release evaluation always injects the active ruleset IR.
            eta = self.production_minimum_remaining_turns
        else:
            eta = (None if cost is None else int(math.ceil(
                max(0, cost - stock) / float(max(1, shields)))))
        active_turns = (None if eta is None else max(0, int(remaining_turns) - eta))
        projection = {
            "active_turns": active_turns, "build_cost": cost,
            "cost_source": "ruleset_ir" if cost is not None else "bounded_fallback",
            "completion_eta_turns": eta, "remaining_turns": int(remaining_turns),
            "pop_cost": int(spec.get("pop_cost", 0)),
            "shield_surplus": shields, "score_value": 0.0,
        }
        if normalized in founder_types:
            projection["founder_capable"] = True
            projection["founder_capability_source"] = (
                self._founder_capability_source(normalized)
                or "current_server_legal_action:unit_build_city")
        if eta is None:
            return projection

        food = self._city_output(city, 0)
        science = self._city_output(city, 5)
        growth_cost = 20 + max(1, int(city.size or 1)) * 10
        growth_eta = int(math.ceil(max(
            0, growth_cost - max(0, int(city.food_stock or 0)))
            / float(max(1, food)))) if food else None
        if normalized in founder_types:
            # A completed founder needs time to move and establish a score-bearing
            # city. Charge its exact ruleset population cost rather than assuming
            # that every terrain worker is able to establish a city.
            projection["score_value"] = max(
                0.0, 1.0 - projection["pop_cost"] * 2.0
                + (active_turns - 3) * 0.15)
            projection["settlement_runway_turns"] = max(0, active_turns - 3)
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
            projection["score_value"] = 0.1 + active_turns / 1000.0
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

    def _production_candidate(self, snapshot, action, founder_types):
        city = snapshot.city(action.get("city_id"))
        if city is None or not city.buildability_available:
            return None
        # Mid-build switching loses shields in FreeCiv.  Only select a new item
        # at an empty stock boundary, even though the proxy advertises all choices.
        if city.shield_stock not in (None, 0) or self._current_production_matches(city, action):
            return None
        name = _target_name(action)
        normalized = _normalized_type(name)
        city_count = len(snapshot.cities)
        current_name = self._current_production_name(city)
        current_normalized = _normalized_type(current_name)
        remaining_turns = self.horizon_turn - snapshot.turn
        if self.production_strategy == "static_priority":
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
        needs_founder = city_count < self.expansion_city_target and not founders
        projection = self._production_projection(
            city, name, remaining_turns, snapshot=snapshot,
            founder_types=founder_types)
        current_projection = (self._production_projection(
            city, current_name, remaining_turns, snapshot=snapshot,
            founder_types=founder_types)
                              if current_name else None)
        if needs_founder and current_normalized in founder_types:
            return None
        if (needs_founder and normalized in founder_types
                and remaining_turns >= self.expansion_minimum_remaining_turns
                and self._projection_can_affect_horizon(projection, 4)):
            if (projection["pop_cost"] > 0
                    and remaining_turns < self.expansion_minimum_remaining_turns * 2):
                return None
            return ImpactCandidate(
                action, "production_expansion",
                920.0 + projection["score_value"] * 10.0
                - projection["completion_eta_turns"],
                "produce one founder only when build ETA leaves settlement runway",
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

        # A single non-deficit unit contributes only one tenth of the unit score
        # category and may not change the integer total at all. Preserve the
        # current build instead of churning to a cheaper military target.
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
        unit_type = _normalized_type(unit.unit_type)
        novelty = 1.0 if (x, y) not in self.visited_positions else 0.0
        city_distance = self._distance_from_cities(snapshot, x, y)
        if unit_type in founder_types:
            if len(snapshot.cities) >= self.expansion_city_target:
                return None
            return ImpactCandidate(
                action, "expansion_move",
                800.0 + city_distance * 20.0 + novelty * 15.0,
                "move a founder away from existing cities toward a legal settlement tile")

        # The ruleset's worker flag is broader than city-founding capability.
        # Sending non-founder workers toward the frontier consumed movement and
        # action budget without creating any score-bearing settlement path.
        if unit_type in self._ruleset_worker_types:
            return None

        if self._city_defender_is_required(snapshot, unit, founder_types):
            return None
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
            return ImpactCandidate(
                action, "exploration_move",
                610.0 + city_distance * 5.0 + novelty * 25.0,
                "reveal a new position with an exploration-capable unit")
        return None

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
            elif action_type == "city_production":
                candidate = self._production_candidate(
                    snapshot, action, founder_types)
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
