"""Grounded strategic action planning over the exact server legal-action set.

This module deliberately performs no inference.  It turns already-authoritative
state and server-advertised actions into short, auditable plans which still pass
through :class:`ExecutionGate` immediately before transport.
"""

import json
from dataclasses import dataclass

from ..events.schema import canonical_json_bytes, structural_hash
from .model import BranchScore, Plan, PlanStep, ResourceLedger


FOUNDER_TYPES = frozenset(("settlers", "migrants", "engineers"))
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

    @property
    def action_key(self):
        return canonical_json_bytes(self.action).decode("utf-8")

    @property
    def scope(self):
        action_type = str(self.action.get("action_type", ""))
        if action_type == "city_production":
            return ("production", self.action.get("city_id"))
        if action_type == "unit_build_city":
            return ("found-city", self.action.get("actor_id"))
        if action_type.startswith("unit_"):
            return ("unit", self.action.get("actor_id"))
        return (action_type, None)

    def to_dict(self):
        return {
            "action": dict(self.action), "category": self.category,
            "rationale": self.rationale, "utility": self.utility,
        }


@dataclass(frozen=True)
class ImpactDecision:
    candidate: ImpactCandidate
    plan: Plan


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

    def __init__(self, config=None):
        values = dict(config or {})
        self.max_actions_per_turn = int(values.get("max_actions_per_turn", 8))
        self.expansion_city_target = int(values.get("expansion_city_target", 3))
        self.settle_min_distance = int(values.get("settle_min_distance", 3))
        self.no_effect_retry_limit = int(values.get("no_effect_retry_limit", 1))
        self.preserve_city_defenders = bool(values.get("preserve_city_defenders", True))
        if not 1 <= self.max_actions_per_turn <= 32:
            raise ValueError("max_actions_per_turn must be in 1..32")
        if not 1 <= self.expansion_city_target <= 20:
            raise ValueError("expansion_city_target must be in 1..20")
        if not 1 <= self.settle_min_distance <= 12:
            raise ValueError("settle_min_distance must be in 1..12")
        if not 1 <= self.no_effect_retry_limit <= 8:
            raise ValueError("no_effect_retry_limit must be in 1..8")
        self.visited_positions = set()
        self._fortified_units = set()
        self._no_effect_attempts = {}
        self._reported_suppressions = set()
        self.no_effect_retries_blocked = 0

    @staticmethod
    def _actions(snapshot):
        return tuple(json.loads(value) for value in snapshot.legal_action_json)

    def observe(self, snapshot):
        for unit in snapshot.units:
            if unit.x is not None and unit.y is not None:
                self.visited_positions.add((unit.x, unit.y))

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

    @staticmethod
    def _founders(snapshot):
        return tuple(unit for unit in snapshot.units
                     if _normalized_type(unit.unit_type) in FOUNDER_TYPES)

    @staticmethod
    def _combat_units(snapshot):
        return tuple(unit for unit in snapshot.units
                     if _normalized_type(unit.unit_type) not in FOUNDER_TYPES | EXPLORER_TYPES)

    def _distance_from_cities(self, snapshot, x, y):
        rows = [_distance(x, y, city.x, city.y, snapshot.map_width, snapshot.map_height)
                for city in snapshot.cities]
        return min(rows) if rows else self.settle_min_distance

    def _city_defender_is_required(self, snapshot, unit):
        if not self.preserve_city_defenders:
            return False
        if _normalized_type(unit.unit_type) in FOUNDER_TYPES | EXPLORER_TYPES:
            return False
        city = next((row for row in snapshot.cities
                     if (row.x, row.y) == (unit.x, unit.y)), None)
        if city is None:
            return False
        defenders = [row for row in self._combat_units(snapshot)
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

    def _production_candidate(self, snapshot, action):
        city = snapshot.city(action.get("city_id"))
        if city is None or not city.buildability_available:
            return None
        # Mid-build switching loses shields in FreeCiv.  Only select a new item
        # at an empty stock boundary, even though the proxy advertises all choices.
        if city.shield_stock not in (None, 0) or self._current_production_matches(city, action):
            return None
        name = _target_name(action)
        normalized = _normalized_type(name)
        founders = self._founders(snapshot)
        city_count = len(snapshot.cities)
        current_name = self._current_production_name(city)
        current_normalized = _normalized_type(current_name)
        needs_founder = city_count < self.expansion_city_target and not founders
        if needs_founder and current_normalized in FOUNDER_TYPES:
            return None
        if needs_founder and normalized in FOUNDER_TYPES:
            return ImpactCandidate(
                action, "production_expansion", 920.0,
                "produce one founder while below the configured city target")

        defenders = self._combat_units(snapshot)
        defense_deficit = len(defenders) < max(1, city_count)
        if defense_deficit and current_name in DEFENDER_PRIORITY:
            return None
        if defense_deficit:
            for index, target in enumerate(DEFENDER_PRIORITY):
                if name.lower() == target.lower():
                    return ImpactCandidate(
                        action, "production_defense", 850.0 - index,
                        "cover the current city-defense deficit")

        if current_name in IMPROVEMENT_PRIORITY:
            return None

        for index, target in enumerate(IMPROVEMENT_PRIORITY):
            if name.lower() == target.lower():
                return ImpactCandidate(
                    action, "production_economy", 740.0 - index,
                    "select the highest-priority available growth/economy improvement")

        for index, target in enumerate(DEFENDER_PRIORITY):
            if name.lower() == target.lower():
                return ImpactCandidate(
                    action, "production_military", 520.0 - index,
                    "add a useful military unit after expansion and infrastructure")
        return None

    def _move_candidate(self, snapshot, action):
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
        if unit_type in FOUNDER_TYPES:
            if len(snapshot.cities) >= self.expansion_city_target:
                return None
            return ImpactCandidate(
                action, "expansion_move",
                800.0 + city_distance * 20.0 + novelty * 15.0,
                "move a founder away from existing cities toward a legal settlement tile")

        if self._city_defender_is_required(snapshot, unit):
            return None
        enemies = [row for row in snapshot.visible_enemy_units
                   if row.x is not None and row.y is not None]
        if enemies:
            enemy_distance = min(_distance(
                x, y, row.x, row.y, snapshot.map_width, snapshot.map_height)
                                 for row in enemies)
            return ImpactCandidate(
                action, "tactical_move",
                700.0 - enemy_distance * 12.0 + novelty * 5.0,
                "move a non-essential unit toward a packet-visible opponent")
        if unit_type in EXPLORER_TYPES:
            return ImpactCandidate(
                action, "exploration_move",
                610.0 + city_distance * 5.0 + novelty * 25.0,
                "reveal a new position with an exploration-capable unit")
        return ImpactCandidate(
            action, "frontier_move",
            360.0 + city_distance * 4.0 + novelty * 20.0,
            "advance a non-garrison unit toward the visible frontier")

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
        self.observe(snapshot)
        excluded = set(excluded)
        excluded_scopes = set(excluded_scopes)
        result = []
        for action in self._actions(snapshot):
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
                candidate = self._production_candidate(snapshot, action)
            elif action_type == "unit_move":
                candidate = self._move_candidate(snapshot, action)
            elif action_type == "unit_fortify":
                unit = snapshot.unit(action.get("actor_id"))
                if (unit is not None and unit.unit_id not in self._fortified_units
                        and self._city_defender_is_required(snapshot, unit)):
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
