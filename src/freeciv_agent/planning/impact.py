"""Grounded strategic action planning over the exact server legal-action set.

This module deliberately performs no inference.  It turns already-authoritative
state and server-advertised actions into short, auditable plans which still pass
through :class:`ExecutionGate` immediately before transport.
"""

import json
import math
import time
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
    "Granary", "Harbor", "Supermarket", "Library", "Marketplace",
    "City Walls", "Barracks II", "Barracks I", "Temple", "Courthouse",
    "Aqueduct, River", "Coinage",
)
FOOD_OUTPUT_PRIORITY = ("Harbor", "Supermarket")
FOOD_STABILIZATION_PRIORITY = (
    FOOD_OUTPUT_PRIORITY + (
        "Granary", "Aqueduct, River", "Marketplace", "Library", "City Walls",
        "Barracks II", "Barracks I", "Temple", "Courthouse", "Coinage",
    )
)
TREASURY_STABILIZATION_PRIORITY = (
    "Coinage", "Marketplace", "Courthouse", "Library", "Granary",
    "City Walls", "Barracks II", "Barracks I", "Temple", "Aqueduct, River",
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
        if action_type == "city_governor":
            return ("governor", self.action.get("city_id"))
        if action_type.startswith("unit_"):
            return ("unit", self.action.get("actor_id"))
        return (action_type, None)

    @property
    def terminal_on_accept(self):
        """Whether transport acceptance can consume the actor before state catches up."""
        return self.action.get("action_type") in (
            "unit_build_city", "unit_disband", "unit_join_city",
            "unit_suicide_attack")

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
    pressure_artifact: object = None


@dataclass(frozen=True)
class DeferredImpactResolution:
    """One accepted action resolved by a later authoritative snapshot."""

    candidate: ImpactCandidate
    before_snapshot: object
    after_snapshot: object
    effect_observed: bool
    feedback_id: object = None


@dataclass(frozen=True)
class GroundedGoalRelief:
    """Candidate-relative goal progress measured from authoritative snapshots."""

    goal: str
    realized_relief: float
    source: str

    def to_dict(self):
        return {
            "goal": self.goal,
            "realized_relief": float(self.realized_relief),
            "source": self.source,
        }


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

    def defer(self, candidate, before_snapshot, feedback_id=None):
        self._pending.append((candidate, before_snapshot, feedback_id))

    def resolve(self, planner, after_snapshot):
        resolved = []
        pending = []
        for candidate, before_snapshot, feedback_id in self._pending:
            effect_observed = planner.candidate_effect_observed(
                candidate, before_snapshot, after_snapshot)
            if (effect_observed
                    or int(after_snapshot.turn) > int(before_snapshot.turn)):
                resolved.append(DeferredImpactResolution(
                    candidate, before_snapshot, after_snapshot,
                    bool(effect_observed), feedback_id))
            else:
                pending.append((candidate, before_snapshot, feedback_id))
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


PLANNED_PRODUCTION_TYPES = frozenset(
    _normalized_type(name)
    for name in IMPROVEMENT_PRIORITY + DEFENDER_PRIORITY)
NORMALIZED_DEFENDER_TYPES = frozenset(
    _normalized_type(name) for name in DEFENDER_PRIORITY)
NORMALIZED_FOOD_OUTPUT_TYPES = frozenset(
    _normalized_type(name) for name in FOOD_OUTPUT_PRIORITY)
NORMALIZED_TREASURY_STABILIZATION_TYPES = frozenset(
    _normalized_type(name) for name in TREASURY_STABILIZATION_PRIORITY)
INDUSTRIAL_IMPROVEMENT_PRIORITY = (
    "Manufacturing Plant", "Factory", "Offshore Platform", "Power Plant",
    "Hydro Plant", "Solar Plant",
)
RESEARCH_IMPROVEMENT_PRIORITY = (
    "Research Lab", "University", "Library",
)
COMMERCE_IMPROVEMENT_PRIORITY = (
    "Stock Exchange", "Bank", "Marketplace", "Courthouse",
)
NAVAL_IMPROVEMENT_PRIORITY = (
    "Port Facility", "Coastal Defense", "SAM Battery", "SDI Defense",
)


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


def _spatial_target(action):
    target = action.get("target")
    candidates = [target] if isinstance(target, dict) else []
    candidates.append(action)
    for candidate in candidates:
        x = candidate.get("x", candidate.get("dest_x"))
        y = candidate.get("y", candidate.get("dest_y"))
        if (isinstance(x, int) and not isinstance(x, bool)
                and isinstance(y, int) and not isinstance(y, bool)):
            return {"x": x, "y": y}
    return None


class GroundedImpactPlanner(object):
    """Select high-impact legal actions without weakening the execution gate."""

    SOLVER_IDENTITY = "grounded-impact-planner/1.27"

    # Routing evidence is deliberately a tie-breaker within the strategic
    # expansion policy.  It must never manufacture legality or bypass the
    # execution gate's one-unit-action safety boundary.
    FOUNDER_CITY_SEPARATION_WEIGHT = 24.0
    FOUNDER_CARDINAL_CORRIDOR_BONUS = 18.0
    FOUNDER_TRAVERSABLE_EDGE_BONUS = 36.0
    FOUNDER_FAILED_EDGE_PENALTY = 30.0
    FOUNDER_SETTLEMENT_SITE_UTILITY = 990.0
    FOUNDER_SETTLEMENT_ALTERNATIVE_UTILITY_CEILING = 980.0

    def __init__(self, config=None, ruleset_ir=None, pressure_state_path=None,
                 pressure_state_identity=None):
        values = dict(config or {})
        pressure_enabled = values.get("pressure_enabled", False)
        if not isinstance(pressure_enabled, bool):
            raise ValueError("pressure_enabled must be boolean")
        self.pressure_enabled = pressure_enabled
        pressure_learning_enabled = values.get(
            "pressure_learning_enabled", False)
        if not isinstance(pressure_learning_enabled, bool):
            raise ValueError("pressure_learning_enabled must be boolean")
        if pressure_learning_enabled and not pressure_enabled:
            raise ValueError("pressure learning requires pressure_enabled")
        self.pressure_learning_enabled = pressure_learning_enabled
        pressure_score_alignment_enabled = values.get(
            "pressure_score_alignment_enabled", False)
        if not isinstance(pressure_score_alignment_enabled, bool):
            raise ValueError(
                "pressure_score_alignment_enabled must be boolean")
        self.pressure_score_alignment_enabled = (
            pressure_score_alignment_enabled)
        pressure_exploration_information_enabled = values.get(
            "pressure_exploration_information_enabled", True)
        if not isinstance(pressure_exploration_information_enabled, bool):
            raise ValueError(
                "pressure_exploration_information_enabled must be boolean")
        self.pressure_exploration_information_enabled = (
            pressure_exploration_information_enabled)
        pressure_score_alignment_utility_tolerance = values.get(
            "pressure_score_alignment_utility_tolerance", 0.0)
        if (isinstance(pressure_score_alignment_utility_tolerance, bool)
                or not isinstance(
                    pressure_score_alignment_utility_tolerance, (int, float))
                or not 0.0 <= float(
                    pressure_score_alignment_utility_tolerance) <= 0.25):
            raise ValueError(
                "pressure_score_alignment_utility_tolerance must be in "
                "0..0.25")
        self.pressure_score_alignment_utility_tolerance = float(
            pressure_score_alignment_utility_tolerance)
        pressure_max_routes = values.get(
            "pressure_max_routes_per_conclusion", 32)
        if (isinstance(pressure_max_routes, bool)
                or not 1 <= int(pressure_max_routes) <= 10000):
            raise ValueError(
                "pressure_max_routes_per_conclusion must be in 1..10000")
        pressure_survival_threat_radius = values.get(
            "pressure_survival_threat_radius", 3)
        if (isinstance(pressure_survival_threat_radius, bool)
                or not 1 <= int(pressure_survival_threat_radius) <= 12):
            raise ValueError(
                "pressure_survival_threat_radius must be in 1..12")
        self.pressure_survival_threat_radius = int(
            pressure_survival_threat_radius)
        for name, lower, upper, upper_inclusive in (
                ("pressure_damping", 0.0, 1.0, False),
                ("pressure_exploration_floor", 0.0, 1.0, True),
                ("pressure_temperature", 0.0, float("inf"), False)):
            setting = float(values.get(name, {
                "pressure_damping": 0.85,
                "pressure_exploration_floor": 0.05,
                "pressure_temperature": 0.15,
            }[name]))
            valid_upper = setting <= upper if upper_inclusive else setting < upper
            if (setting < lower or not valid_upper
                    or (name == "pressure_temperature" and setting == 0)):
                raise ValueError("{} is outside its valid range".format(name))
        for name, lower, upper, lower_inclusive in (
                ("pressure_learning_rate", 0.0, 1.0, False),
                ("pressure_no_progress_rate", 0.0, 1.0, True),
                ("pressure_initial_conductance", 0.0, 1.0, True)):
            setting = float(values.get(name, {
                "pressure_learning_rate": 0.10,
                "pressure_no_progress_rate": 0.10,
                "pressure_initial_conductance": 1.00,
            }[name]))
            valid_lower = setting >= lower if lower_inclusive else setting > lower
            if not valid_lower or setting > upper:
                raise ValueError("{} is outside its valid range".format(name))
        self.max_actions_per_turn = int(values.get("max_actions_per_turn", 8))
        self.expansion_city_target = int(values.get("expansion_city_target", 3))
        self.settle_min_distance = int(values.get("settle_min_distance", 3))
        self.horizon_turn = int(values.get("horizon_turn", 30))
        preferred_government = values.get("preferred_government", "")
        if not isinstance(preferred_government, str):
            raise ValueError("preferred_government must be a string")
        self.preferred_government = preferred_government.strip()
        if len(self.preferred_government) > 64:
            raise ValueError(
                "preferred_government must be at most 64 characters")
        government_runway = values.get(
            "government_minimum_remaining_turns", 12)
        if (isinstance(government_runway, bool)
                or not isinstance(government_runway, (int, float))
                or int(government_runway) != government_runway):
            raise ValueError(
                "government_minimum_remaining_turns must be an integer")
        self.government_minimum_remaining_turns = int(government_runway)
        government_minimum_city_count = values.get(
            "government_minimum_city_count", 0)
        if (isinstance(government_minimum_city_count, bool)
                or not isinstance(government_minimum_city_count, (int, float))
                or int(government_minimum_city_count)
                != government_minimum_city_count):
            raise ValueError(
                "government_minimum_city_count must be an integer")
        self.government_minimum_city_count = int(
            government_minimum_city_count)
        founder_attrition_rebuild_limit = values.get(
            "founder_attrition_rebuild_limit", 0)
        if (isinstance(founder_attrition_rebuild_limit, bool)
                or not isinstance(
                    founder_attrition_rebuild_limit, (int, float))
                or int(founder_attrition_rebuild_limit)
                != founder_attrition_rebuild_limit):
            raise ValueError(
                "founder_attrition_rebuild_limit must be an integer")
        self.founder_attrition_rebuild_limit = int(
            founder_attrition_rebuild_limit)
        self.production_minimum_remaining_turns = int(
            values.get("production_minimum_remaining_turns", 8))
        self.expansion_minimum_remaining_turns = int(
            values.get("expansion_minimum_remaining_turns", 12))
        settlement_runway = values.get(
            "expansion_minimum_settlement_runway_turns", 0)
        if (isinstance(settlement_runway, bool)
                or not isinstance(settlement_runway, (int, float))
                or int(settlement_runway) != settlement_runway):
            raise ValueError(
                "expansion_minimum_settlement_runway_turns must be an integer")
        self.expansion_minimum_settlement_runway_turns = int(
            settlement_runway)
        settlement_deadline_recovery = values.get(
            "expansion_settlement_deadline_recovery_enabled", True)
        if not isinstance(settlement_deadline_recovery, bool):
            raise ValueError(
                "expansion_settlement_deadline_recovery_enabled must be boolean")
        self.expansion_settlement_deadline_recovery_enabled = (
            settlement_deadline_recovery)
        settlement_site_preference = values.get(
            "expansion_packet_site_preference_enabled", True)
        if not isinstance(settlement_site_preference, bool):
            raise ValueError(
                "expansion_packet_site_preference_enabled must be boolean")
        self.expansion_packet_site_preference_enabled = (
            settlement_site_preference)
        escort_retention = values.get(
            "expansion_escort_retention_enabled", False)
        if not isinstance(escort_retention, bool):
            raise ValueError(
                "expansion_escort_retention_enabled must be boolean")
        self.expansion_escort_retention_enabled = escort_retention
        escort_threat_gating = values.get(
            "expansion_escort_threat_gating_enabled", False)
        if not isinstance(escort_threat_gating, bool):
            raise ValueError(
                "expansion_escort_threat_gating_enabled must be boolean")
        self.expansion_escort_threat_gating_enabled = escort_threat_gating
        escort_route_threat_memory = values.get(
            "expansion_escort_route_threat_memory_enabled", False)
        if not isinstance(escort_route_threat_memory, bool):
            raise ValueError(
                "expansion_escort_route_threat_memory_enabled must be boolean")
        self.expansion_escort_route_threat_memory_enabled = (
            escort_route_threat_memory)
        final_settlement_escort = values.get(
            "expansion_final_settlement_escort_enabled", False)
        if not isinstance(final_settlement_escort, bool):
            raise ValueError(
                "expansion_final_settlement_escort_enabled must be boolean")
        self.expansion_final_settlement_escort_enabled = (
            final_settlement_escort)
        for setting in (
                "ruleset_driven_production_enabled",
                "naval_response_enabled",
                "modernization_enabled",
                "industrialization_enabled"):
            value = values.get(setting, False)
            if not isinstance(value, bool):
                raise ValueError("{} must be boolean".format(setting))
            setattr(self, setting, value)
        threat_memory_turns = values.get("strategic_threat_memory_turns", 60)
        if (isinstance(threat_memory_turns, bool)
                or not isinstance(threat_memory_turns, (int, float))
                or int(threat_memory_turns) != threat_memory_turns
                or not 0 <= int(threat_memory_turns) <= 200):
            raise ValueError(
                "strategic_threat_memory_turns must be in 0..200")
        self.strategic_threat_memory_turns = int(threat_memory_turns)
        self.foodbox_percent = int(values.get("foodbox_percent", 100))
        self.unit_build_score_divisor = int(values.get(
            "unit_build_score_divisor", 10))
        self.military_units_per_city_limit = int(values.get(
            "military_units_per_city_limit", 3))
        self.food_surplus_reserve = int(values.get(
            "food_surplus_reserve", 1))
        disorder_luxury_recovery_enabled = values.get(
            "disorder_luxury_recovery_enabled", False)
        if not isinstance(disorder_luxury_recovery_enabled, bool):
            raise ValueError(
                "disorder_luxury_recovery_enabled must be boolean")
        self.disorder_luxury_recovery_enabled = (
            disorder_luxury_recovery_enabled)
        city_happiness_governor_enabled = values.get(
            "city_happiness_governor_enabled", False)
        if not isinstance(city_happiness_governor_enabled, bool):
            raise ValueError(
                "city_happiness_governor_enabled must be boolean")
        self.city_happiness_governor_enabled = (
            city_happiness_governor_enabled)
        self.treasury_reserve_turns = int(values.get(
            "treasury_reserve_turns", 2))
        self.treasury_minimum_gold = int(values.get(
            "treasury_minimum_gold", 5))
        self.normal_tax_rate = int(values.get("normal_tax_rate", 40))
        self.normal_science_rate = int(values.get(
            "normal_science_rate", 60))
        self.refresh_timeout_seconds = float(
            values.get("refresh_timeout_seconds", 2.0))
        self.terminal_refresh_timeout_seconds = float(
            values.get(
                "terminal_refresh_timeout_seconds",
                max(1.0, self.refresh_timeout_seconds)))
        self.refresh_stability_interval_seconds = float(
            values.get("refresh_stability_interval_seconds", 0.2))
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
        if not 1 <= self.horizon_turn <= 1000:
            raise ValueError("horizon_turn must be in 1..1000")
        if not 0 <= self.government_minimum_remaining_turns <= 100:
            raise ValueError(
                "government_minimum_remaining_turns must be in 0..100")
        if not 0 <= self.government_minimum_city_count <= 20:
            raise ValueError(
                "government_minimum_city_count must be in 0..20")
        if not 0 <= self.founder_attrition_rebuild_limit <= 20:
            raise ValueError(
                "founder_attrition_rebuild_limit must be in 0..20")
        if not 1 <= self.production_minimum_remaining_turns <= 100:
            raise ValueError("production_minimum_remaining_turns must be in 1..100")
        if not 1 <= self.expansion_minimum_remaining_turns <= 100:
            raise ValueError("expansion_minimum_remaining_turns must be in 1..100")
        if not 0 <= self.expansion_minimum_settlement_runway_turns <= 100:
            raise ValueError(
                "expansion_minimum_settlement_runway_turns must be in 0..100")
        if self.expansion_minimum_remaining_turns < self.production_minimum_remaining_turns:
            raise ValueError(
                "expansion_minimum_remaining_turns cannot be shorter than production")
        if not 1 <= self.foodbox_percent <= 1000:
            raise ValueError("foodbox_percent must be in 1..1000")
        if not 1 <= self.unit_build_score_divisor <= 100:
            raise ValueError("unit_build_score_divisor must be in 1..100")
        if not 1 <= self.military_units_per_city_limit <= 12:
            raise ValueError(
                "military_units_per_city_limit must be in 1..12")
        if not 0 <= self.food_surplus_reserve <= 10:
            raise ValueError("food_surplus_reserve must be in 0..10")
        if not 1 <= self.treasury_reserve_turns <= 20:
            raise ValueError("treasury_reserve_turns must be in 1..20")
        if not 0 <= self.treasury_minimum_gold <= 1000:
            raise ValueError("treasury_minimum_gold must be in 0..1000")
        if (not 0 <= self.normal_tax_rate <= 100
                or not 0 <= self.normal_science_rate <= 100
                or self.normal_tax_rate + self.normal_science_rate > 100):
            raise ValueError(
                "normal tax/science rates must be in 0..100 and sum to <=100")
        if not 0.25 <= self.refresh_timeout_seconds <= 10.0:
            raise ValueError("refresh_timeout_seconds must be in [0.25,10]")
        if not 0.25 <= self.terminal_refresh_timeout_seconds <= 10.0:
            raise ValueError(
                "terminal_refresh_timeout_seconds must be in [0.25,10]")
        if self.terminal_refresh_timeout_seconds < self.refresh_timeout_seconds:
            raise ValueError(
                "terminal_refresh_timeout_seconds cannot be shorter than "
                "refresh_timeout_seconds")
        if not 0.05 <= self.refresh_stability_interval_seconds <= 0.5:
            raise ValueError(
                "refresh_stability_interval_seconds must be in [0.05,0.5]")
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
        self._enemy_domain_last_seen = {}
        self._ruleset_founder_types = set()
        self._ruleset_worker_types = set()
        self._ruleset_add_to_city_types = set()
        self._server_founder_types = set()
        self._founder_cardinal_intents = {}
        self._founder_route_positions = {}
        self._founder_traversable_edges = set()
        self._founder_failed_edges = {}
        self._founder_actor_failed_edges = set()
        self._observed_founders = {}
        self._founder_attrition_positions = {}
        self._luxury_safety_signature = None
        self._minimum_safe_luxury_rate = max(
            0, 100 - self.normal_tax_rate - self.normal_science_rate)
        self._failed_settlement_sites = set()
        self._failed_settlement_site_prunes = set()
        self._founder_escort_deferral_snapshots = set()
        self._founder_escort_threat_deferral_snapshots = set()
        self._founder_escort_persisted_threat_deferral_snapshots = set()
        self._founder_final_escort_deferral_snapshots = set()
        self._founder_final_escort_rendezvous_hold_snapshots = set()
        self._founder_final_escort_rendezvous_no_progress_snapshots = set()
        self._founder_final_escort_unprepared_route_bypass_snapshots = set()
        self._founder_final_escort_unthreatened_route_bypass_snapshots = set()
        self._founder_route_threat_observations = set()
        self._founder_route_threats = {}
        self._failed_exploration_target_sources = {}
        self._failed_exploration_prunes = set()
        self._preexpansion_sequences = {}
        self._unit_score_batch_intent = None
        self._unit_score_batch_cache_key = None
        self._unit_score_batch_cache = {}
        self._action_cache_snapshot = None
        self._action_cache = ()
        # At most one successful-but-not-yet-relieving route is retained per
        # category and goal. A later authoritative goal change may credit that
        # bounded procedural trace once; repeated moves cannot multiply credit.
        self._pending_goal_routes = {}
        self._queued_conductance_updates = []
        self._pressure_ranker = None
        if self.pressure_enabled:
            from ..pressure import (
                ConductanceState, ImpactPressureRanker, PressureConfig)
            conductance_state = None
            if self.pressure_learning_enabled:
                conductance_state = ConductanceState(
                    pressure_state_path,
                    identity=(pressure_state_identity
                              or "grounded-impact-planner"),
                    learning_rate=float(values.get(
                        "pressure_learning_rate", 0.10)),
                    no_progress_rate=float(values.get(
                        "pressure_no_progress_rate", 0.10)),
                    initial_conductance=float(values.get(
                        "pressure_initial_conductance", 1.00)))
            self._pressure_ranker = ImpactPressureRanker(PressureConfig(
                damping=float(values.get("pressure_damping", 0.85)),
                exploration_floor=float(values.get(
                    "pressure_exploration_floor", 0.05)),
                softmax_temperature=float(values.get(
                    "pressure_temperature", 0.15)),
                max_routes_per_conclusion=int(values.get(
                    "pressure_max_routes_per_conclusion", 32))),
                conductance_state=conductance_state,
                score_alignment=self.pressure_score_alignment_enabled,
                exploration_information_enabled=(
                    self.pressure_exploration_information_enabled),
                score_alignment_utility_tolerance=(
                    self.pressure_score_alignment_utility_tolerance))
        self.founder_route_successes = 0
        self.founder_route_failures = 0
        self.founder_cardinal_corridor_attempts = 0
        self.founder_cardinal_corridor_successes = 0
        self.founder_settlement_site_preference_attempts = 0
        self.founder_settlement_site_preference_successes = 0
        self.founder_escort_move_attempts = 0
        self.founder_escort_move_successes = 0
        self.founder_threat_avoidance_move_attempts = 0
        self.founder_threat_avoidance_move_successes = 0
        self.founder_escort_defense_production_attempts = 0
        self.founder_escort_defense_production_successes = 0
        self.founder_final_escort_preparation_production_attempts = 0
        self.founder_final_escort_preparation_production_successes = 0
        self.founder_final_escort_move_attempts = 0
        self.founder_final_escort_move_successes = 0
        self.founder_final_escorted_settlement_attempts = 0
        self.founder_final_escorted_settlement_completions = 0
        self.founder_escorted_settlement_attempts = 0
        self.founder_escorted_settlement_completions = 0
        self.founder_unescorted_safe_settlement_attempts = 0
        self.founder_unescorted_safe_settlement_completions = 0
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
            upkeep = {}
            for field_name in ("uk_food", "uk_shield", "uk_gold", "happy_cost"):
                value = quantitative.get(field_name, 0)
                if isinstance(value, dict):
                    value = value.get("value", 0)
                upkeep[field_name] = (
                    0 if isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    else max(0, int(value)))
            capabilities = {}
            for field_name in (
                    "attack", "defense", "hitpoints", "firepower",
                    "move_rate", "transport_cap", "fuel"):
                value = quantitative.get(field_name, 0)
                if isinstance(value, dict):
                    value = value.get("value", 0)
                capabilities[field_name] = (
                    0 if isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    else max(0, int(value)))
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
                        "unit_class": next(iter(
                            self._trait_values(rule, "class")), ""),
                        "flags": tuple(sorted(
                            self._trait_values(rule, "flags"))),
                        "roles": tuple(sorted(
                            self._trait_values(rule, "roles"))),
                        "cargo": tuple(sorted(
                            self._trait_values(rule, "cargo"))),
                        "targets": tuple(sorted(
                            self._trait_values(rule, "targets"))),
                        **capabilities,
                        **upkeep,
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

    def _actions(self, snapshot):
        """Decode one immutable snapshot's canonical actions at most once.

        Observation, pruning telemetry, and planning inspect the same snapshot
        consecutively. The parsed dictionaries remain planner-private and no
        policy path mutates them, so retaining the one-snapshot decode preserves
        the exact canonical strings while avoiding repeated JSON work.
        """
        if self._action_cache_snapshot is not snapshot:
            self._action_cache_snapshot = snapshot
            self._action_cache = tuple(
                json.loads(value) for value in snapshot.legal_action_json)
        return self._action_cache

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
        for enemy in snapshot.visible_enemy_units:
            domain = self._unit_domain(_normalized_type(enemy.unit_type))
            self._enemy_domain_last_seen[domain] = int(snapshot.turn)
        self._enemy_domain_last_seen = {
            domain: turn
            for domain, turn in self._enemy_domain_last_seen.items()
            if int(snapshot.turn) - int(turn) <= self.strategic_threat_memory_turns
        }
        self._server_founder_types.update(self._legal_unit_types(
            snapshot, "unit_build_city", actions))
        founder_types = self._founder_types(snapshot, actions)
        combat_units = self._combat_units(snapshot, founder_types)
        luxury_signature = tuple(
            (int(city.city_id), int(city.size or 0), sum(
                (unit.x, unit.y) == (city.x, city.y)
                for unit in combat_units))
            for city in sorted(snapshot.cities, key=lambda row: row.city_id))
        normal_luxury = max(
            0, 100 - self.normal_tax_rate - self.normal_science_rate)
        if luxury_signature != self._luxury_safety_signature:
            # A city, population, or grounded-garrison change can alter the
            # luxury threshold. Permit a new bounded downward probe.
            self._luxury_safety_signature = luxury_signature
            self._minimum_safe_luxury_rate = normal_luxury
        luxury_rate = snapshot.economy.luxury_rate
        if (self.disorder_luxury_recovery_enabled
                and luxury_rate is not None
                and any(city.disorder is True for city in snapshot.cities)):
            # The current rate is authoritatively insufficient for this exact
            # city/garrison signature. Remember the next ten-point boundary so
            # restoration cannot oscillate below it after disorder clears.
            self._minimum_safe_luxury_rate = max(
                self._minimum_safe_luxury_rate,
                min(60, int(luxury_rate) + 10))
        current_founders = {
            int(unit.unit_id): {
                "city_layout": self._city_layout(snapshot),
                "map_height": int(snapshot.map_height),
                "map_width": int(snapshot.map_width),
                "position": (int(unit.x), int(unit.y)),
                "unit_type": _normalized_type(unit.unit_type),
            }
            for unit in snapshot.units
            if (_normalized_type(unit.unit_type) in founder_types
                and None not in (unit.x, unit.y))
        }
        current_layout = self._city_layout(snapshot)
        current_city_positions = {
            (city.x, city.y) for city in snapshot.cities
            if None not in (city.x, city.y)}
        for actor_id, previous in self._observed_founders.items():
            if actor_id in current_founders:
                continue
            # A founder that becomes a city is success, not attrition. Likewise,
            # population recovery is allowed only after the expansion target and
            # must not poison an otherwise safe city tile.
            if (len(previous["city_layout"]) >= self.expansion_city_target
                    or len(current_layout) > len(previous["city_layout"])
                    or previous["position"] in current_city_positions):
                continue
            key = (
                previous["unit_type"], previous["map_width"],
                previous["map_height"], previous["position"][0],
                previous["position"][1],
            )
            self._founder_attrition_positions[key] = (
                self._founder_attrition_positions.get(key, 0) + 1)
        self._observed_founders = current_founders
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

    def founder_cycle_move_keys(self, snapshot):
        """Return recent founder revisits suppressed by a fresh alternative.

        A revisit remains eligible at a real dead end. When a fresh grounded
        move exists, however, the recently traversed route must not dominate it
        and recreate a bounded multi-tile loop.
        """
        actions = self._actions(snapshot)
        founder_types = self._founder_types(snapshot, actions)
        return tuple(sorted(
            canonical_json_bytes(action).decode("utf-8")
            for action in actions
            if action.get("action_type") == "unit_move"
            and self._founder_cycle_has_alternative(
                snapshot, action, founder_types, actions)))

    def founder_attrition_move_keys(self, snapshot):
        """Return founder moves diverted from an observed attrition tile.

        The disappearance is learned only across authoritative observations and
        the move is suppressed only while another server-advertised route exists.
        This keeps a transient loss from manufacturing an impassable dead end.
        """
        actions = self._actions(snapshot)
        founder_types = self._founder_types(snapshot, actions)
        return tuple(sorted(
            canonical_json_bytes(action).decode("utf-8")
            for action in actions
            if action.get("action_type") == "unit_move"
            and self._founder_attrition_has_alternative(
                snapshot, action, founder_types, actions)))

    def pruning_move_keys(self, snapshot):
        """Return all read-only move-pruning observations in one catalog pass.

        The individual helpers remain the public behavioral oracle.  The live
        harness uses this equivalent batch form so it decodes founder capability
        once, traverses the legal-action catalog once, and reuses the canonical
        action key already carried by the authoritative snapshot.
        """
        actions = self._actions(snapshot)
        founder_types = self._founder_types(snapshot, actions)
        result = {
            "capability_pruned_worker_moves": [],
            "nonprogress_moves": [],
            "unreachable_founder_moves": [],
            "founder_cycle_moves": [],
            "founder_attrition_moves": [],
        }
        nonfounder_worker_types = self._ruleset_worker_types - founder_types
        founder_rows = []
        for action, action_key in zip(actions, snapshot.legal_action_json):
            if action.get("action_type") != "unit_move":
                continue
            unit = snapshot.unit(action.get("actor_id"))
            normalized = _normalized_type(unit.unit_type) if unit is not None else ""
            if normalized in nonfounder_worker_types:
                result["capability_pruned_worker_moves"].append(action_key)
            if normalized in founder_types:
                evidence = self._founder_move_evidence(
                    snapshot, action, founder_types)
                founder_rows.append((
                    action, action_key, evidence,
                    self._founder_attrition_count(
                        snapshot, action, founder_types)))
                if evidence.get("actor_failed"):
                    result["unreachable_founder_moves"].append(action_key)
                continue
            # Founders and ruleset workers can never satisfy non-progress by
            # definition. Avoid running the complete candidate planner for
            # those actors merely to rediscover that exclusion.
            if (normalized not in self._ruleset_worker_types
                    and self._move_candidate(
                        snapshot, action, founder_types) is None
                    and self._move_is_nonprogress(
                        snapshot, action, founder_types)):
                result["nonprogress_moves"].append(action_key)

        if len(snapshot.cities) < self.expansion_city_target:
            for action, action_key, evidence, attrition_count in founder_rows:
                actor_id = action.get("actor_id")
                alternatives = (
                    (other_evidence, other_attrition_count)
                    for other_action, other_key, other_evidence,
                    other_attrition_count in founder_rows
                    if (other_action.get("actor_id") == actor_id
                        and other_key != action_key))
                alternatives = tuple(alternatives)
                if (evidence.get("recent_revisit")
                        and any(other_evidence
                                and not other_evidence.get("actor_failed")
                                and not other_evidence.get("recent_revisit")
                                for other_evidence, _ in alternatives)):
                    result["founder_cycle_moves"].append(action_key)
                if (attrition_count > 0
                        and any(other_evidence
                                and not other_evidence.get("actor_failed")
                                and other_attrition_count <= 0
                                for other_evidence, other_attrition_count
                                in alternatives)):
                    result["founder_attrition_moves"].append(action_key)
        return {
            name: tuple(sorted(action_keys))
            for name, action_keys in result.items()
        }

    def failed_settlement_site_action_keys(self, snapshot):
        """Return advertised founding actions suppressed by exact site evidence."""
        return tuple(sorted(
            canonical_json_bytes(action).decode("utf-8")
            for action in self._actions(snapshot)
            if (action.get("action_type") == "unit_build_city"
                and self._settlement_site_key(snapshot, action)
                in self._failed_settlement_sites)))

    @property
    def failed_settlement_sites_pruned(self):
        return len(self._failed_settlement_site_prunes)

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
            "activity": unit.activity, "homecity": unit.homecity,
            "hp": unit.hp, "type": unit.unit_type,
            "unit_id": unit.unit_id, "x": unit.x, "y": unit.y,
        }

    @staticmethod
    def _unit_effect_grounding(unit):
        """Actor facts that prove an accepted unit action consumed resources."""
        if unit is None:
            return None
        return {
            "activity": unit.activity, "homecity": unit.homecity, "hp": unit.hp,
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
        if action.get("action_type") == "city_governor":
            city = after.city(action.get("city_id"))
            target = action.get("target")
            reserve = (
                target.get("food_surplus_reserve")
                if isinstance(target, dict) else None)
            require_happy = (
                target.get("require_happy", False)
                if isinstance(target, dict) else False)
            return bool(
                city is not None and reserve is not None
                and self._city_food_governor_matches(
                    city, int(reserve), require_happy=require_happy))
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
        if action.get("action_type") == "government_change":
            target = action.get("target")
            government_id = (
                target.get("government_id")
                if isinstance(target, dict) else None)
            return bool(
                government_id is not None
                and (
                    after.government.current_id == int(government_id)
                    or after.government.target_id == int(government_id))
                and (
                    before.government.selection_required
                    != after.government.selection_required
                    or before.government.target_id
                    != after.government.target_id
                    or before.government.current_id
                    != after.government.current_id))
        if action.get("action_type") in OFFENSIVE_ACTIONS:
            return (self.local_actor_effect_observed(candidate, before, after)
                    or self._combat_target_grounding(before, action)
                    != self._combat_target_grounding(after, action))
        if action.get("actor_id") is not None:
            return self.local_actor_effect_observed(candidate, before, after)
        return before.identity.state_hash != after.identity.state_hash

    @staticmethod
    def _fortified_activity(value):
        return "fort" in str(value or "").strip().lower()

    def candidate_goal_relief(
            self, candidate, before, after, effect_observed):
        """Measure candidate-relative progress without revising engine truth.

        Only packet-grounded state changes which are specific to the selected
        goal are eligible.  Merely changing an actor's position, movement
        points, or a city's production target is not goal relief.
        """
        if self._pressure_ranker is None:
            raise RuntimeError("goal relief requires pressure ranking")
        goal = self._pressure_ranker.goal_for_category(candidate.category)
        if not effect_observed:
            return GroundedGoalRelief(
                goal, 0.0, "authoritative:candidate-specific-no-effect")

        if goal == "expansion":
            target = max(1, self.expansion_city_target)
            before_strength = min(1.0, float(len(before.cities)) / target)
            after_strength = min(1.0, float(len(after.cities)) / target)
            relief = max(0.0, after_strength - before_strength)
            if relief > 0.0:
                return GroundedGoalRelief(
                    goal, min(1.0, relief),
                    "authoritative:owned-city-count-progress")

        if (goal == "score"
                and candidate.category == "population_recovery"):
            target = candidate.action.get("target")
            city_id = target.get("city_id") if isinstance(target, dict) else None
            before_city = before.city(city_id) if city_id is not None else None
            after_city = after.city(city_id) if city_id is not None else None
            expected = int((candidate.projection or {}).get(
                "recovered_population", 0))
            recovered = (
                int(after_city.size) - int(before_city.size)
                if before_city is not None and after_city is not None else 0)
            if expected > 0 and recovered > 0:
                return GroundedGoalRelief(
                    goal, min(1.0, float(recovered) / expected),
                    "authoritative:owned-city-population-recovery")

        if goal == "food_sustainability":
            before_gap = sum(max(
                0, self.food_surplus_reserve
                - self._raw_city_surplus(city, 0))
                for city in before.cities)
            after_gap = sum(max(
                0, self.food_surplus_reserve
                - self._raw_city_surplus(city, 0))
                for city in after.cities)
            if after_gap < before_gap:
                return GroundedGoalRelief(
                    goal, min(
                        1.0, float(before_gap - after_gap)
                        / max(1, before_gap)),
                    "authoritative:city-food-reserve-gap-reduction")

        if goal == "treasury_sustainability":
            before_net = self._net_gold_per_turn(before)
            after_net = self._net_gold_per_turn(after)
            before_reserve_gap = max(
                0, self._treasury_reserve_required(before)
                - int(before.economy.gold or 0))
            after_reserve_gap = max(
                0, self._treasury_reserve_required(after)
                - int(after.economy.gold or 0))
            net_gain = max(0, after_net - before_net)
            reserve_gain = max(0, before_reserve_gap - after_reserve_gap)
            if net_gain or reserve_gain:
                return GroundedGoalRelief(
                    goal, min(
                        1.0,
                        float(net_gain + reserve_gain)
                        / max(1, abs(before_net) + before_reserve_gap)),
                    "authoritative:net-gold-or-upkeep-reserve-gap-reduction")

        if goal == "survival":
            if candidate.category in (
                    "city_happiness_governor", "disorder_luxury_shift"):
                before_disorder = sum(
                    city.disorder is True for city in before.cities)
                after_disorder = sum(
                    city.disorder is True for city in after.cities)
                if after_disorder < before_disorder:
                    return GroundedGoalRelief(
                        goal, min(
                            1.0,
                            float(before_disorder - after_disorder)
                            / max(1, before_disorder)),
                        "authoritative:city-disorder-count-reduction")
            if candidate.category == "tactical_attack":
                before_targets = self._combat_target_grounding(
                    before, candidate.action)
                after_targets = dict(
                    (row[0], row) for row in self._combat_target_grounding(
                        after, candidate.action))
                before_hp = sum(max(0, int(row[3] or 0))
                                for row in before_targets)
                after_hp = sum(max(
                    0, int(after_targets.get(row[0], (None,) * 4)[3] or 0))
                               for row in before_targets)
                if before_hp > after_hp:
                    return GroundedGoalRelief(
                        goal, min(
                            1.0, float(before_hp - after_hp) / before_hp),
                        "authoritative:visible-target-hitpoint-reduction")
            if candidate.category == "city_defense":
                actor_id = candidate.action.get("actor_id")
                before_unit = (
                    before.unit(actor_id) if actor_id is not None else None)
                after_unit = (
                    after.unit(actor_id) if actor_id is not None else None)
                if (before_unit is not None and after_unit is not None
                        and not self._fortified_activity(before_unit.activity)
                        and self._fortified_activity(after_unit.activity)):
                    return GroundedGoalRelief(
                        goal, 1.0,
                        "authoritative:city-defender-fortified")
            if candidate.category == "city_garrison_move":
                before_deficits = len(self._local_garrison_deficits(before))
                after_deficits = len(self._local_garrison_deficits(after))
                if after_deficits < before_deficits:
                    return GroundedGoalRelief(
                        goal, min(
                            1.0,
                            float(before_deficits - after_deficits)
                            / max(1, before_deficits)),
                        "authoritative:city-local-garrison-deficit-reduction")

        if goal == "exploration":
            before_visible = set(before.visible_tile_ids)
            after_visible = set(after.visible_tile_ids)
            newly_visible = len(after_visible - before_visible)
            map_area = max(
                1, int(after.map_width or 0) * int(after.map_height or 0))
            visibility_relief = min(
                1.0, float(newly_visible) / map_area)
            before_huts = set(before.known_hut_tile_ids)
            after_huts = set(after.known_hut_tile_ids)
            resolved_huts = len(before_huts - after_huts)
            hut_relief = min(
                1.0, float(resolved_huts) / max(1, len(before_huts)))
            relief = max(visibility_relief, hut_relief)
            if relief > 0.0:
                return GroundedGoalRelief(
                    goal, relief,
                    ("authoritative:known-hut-resolution"
                     if hut_relief >= visibility_relief
                     else "authoritative:new-visible-map-area"))

        return GroundedGoalRelief(
            goal, 0.0,
            "authoritative:no-measurable-{}-goal-progress".format(goal))

    def drain_conductance_updates(self):
        """Return downstream updates once in deterministic causal order."""
        rows = tuple(self._queued_conductance_updates)
        self._queued_conductance_updates = []
        return rows

    def _record_downstream_goal_relief(
            self, candidate, feedback_id, observation):
        """Credit one pending category route per newly relieved goal."""
        pending = self._pending_goal_routes.pop(observation.goal, {})
        for category in sorted(pending):
            # One goal-progress event updates a category route at most once.
            # The direct category is already credited by the current feedback.
            if category == candidate.category:
                continue
            trace = pending[category]
            downstream_feedback_id = (
                "pressure-downstream-" + structural_hash([
                    observation.goal, category, trace["feedback_id"],
                    feedback_id, observation.realized_relief,
                ])[:24])
            update = self._pressure_ranker.record_category_outcome(
                category, True, downstream_feedback_id,
                observation.realized_relief,
                "authoritative:downstream-{}-goal-trace".format(
                    observation.goal),
                caused_by_feedback_id=feedback_id)
            if update is not None:
                self._queued_conductance_updates.append(update)

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
            "production_value": city.production_value,
            # Accumulating shields cannot make an infeasible citizen-manager
            # floor feasible. Excluding that counter prevents one rejected CMA
            # request per turn while still retrying after a target completion,
            # population/output change, or authoritative governor transition.
            **({} if candidate.category in (
                "city_food_governor", "city_happiness_governor") else {
                "shield_stock": city.shield_stock,
            }),
            "size": city.size, "surplus": city.surplus,
            "disorder": city.disorder,
            "had_famine": city.had_famine,
            "governor_available": city.governor_available,
            "governor_enabled": city.governor_enabled,
            "governor_minimal_surplus": city.governor_minimal_surplus,
            "governor_require_happy": city.governor_require_happy,
            "governor_factor": city.governor_factor,
            "x": city.x, "y": city.y,
        }
        city_layout = (
            sorted((row.city_id, row.x, row.y) for row in snapshot.cities)
            if candidate.category in (
                "city_founding", "expansion_move",
                "founder_threat_avoidance_move") else [])
        return structural_hash({
            "action": action,
            "actor": self._unit_grounding(actor),
            "cities": city_layout,
            "city": city_grounding,
            "target_unit": self._unit_grounding(target_unit),
        })

    def record_outcome(
            self, candidate, snapshot, effect_observed, after_snapshot=None,
            feedback_id=None, diagnostics=None):
        """Learn from an accepted action without treating acceptance as effect.

        Exact no-effect actions are suppressed while their local authoritative
        grounding is unchanged.  Movement refreshes and unrelated economic state
        cannot make an unreachable order eligible again; actor, city, or visible
        target changes can.
        """
        bookkeeping_started = time.perf_counter()
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
                self._founder_route_threats.pop(
                    candidate.action.get("actor_id"), None)
        if (candidate.category == "production_preexpansion_growth"
                and effect_observed):
            projection = candidate.projection or {}
            city_id = candidate.action.get("city_id")
            founder_kind = projection.get("preexpansion_founder_kind")
            founder_value = projection.get("preexpansion_founder_value")
            if None not in (city_id, founder_kind, founder_value):
                self._preexpansion_sequences[int(city_id)] = {
                    "founder_kind": int(founder_kind),
                    "founder_name": projection.get("preexpansion_founder"),
                    "founder_value": int(founder_value),
                    "granary_kind": candidate.action.get("production_kind"),
                    "granary_value": candidate.action.get("production_value"),
                    "selected_turn": int(snapshot.turn),
                }
        if (candidate.category == "production_preexpansion_founder"
                and effect_observed):
            self._preexpansion_sequences.pop(
                candidate.action.get("city_id"), None)
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
        if candidate.category == "founder_escort_move":
            self.founder_escort_move_attempts += 1
            target = candidate.action.get("target", {})
            actor_id = candidate.action.get("actor_id")
            after_unit = (after_snapshot.unit(actor_id)
                          if after_snapshot is not None else None)
            if (after_unit is not None and isinstance(target, dict)
                    and (after_unit.x, after_unit.y)
                    == (target.get("x"), target.get("y"))):
                self.founder_escort_move_successes += 1
                if (candidate.projection or {}).get(
                        "settlement_final_escort_preparation") is True:
                    self.founder_final_escort_move_successes += 1
            if (candidate.projection or {}).get(
                    "settlement_final_escort_preparation") is True:
                self.founder_final_escort_move_attempts += 1
        if candidate.category == "founder_threat_avoidance_move":
            self.founder_threat_avoidance_move_attempts += 1
            target = candidate.action.get("target", {})
            actor_id = candidate.action.get("actor_id")
            after_unit = (after_snapshot.unit(actor_id)
                          if after_snapshot is not None else None)
            if (after_unit is not None and isinstance(target, dict)
                    and (after_unit.x, after_unit.y)
                    == (target.get("x"), target.get("y"))):
                self.founder_threat_avoidance_move_successes += 1
        if (candidate.category == "production_defense"
                and (candidate.projection or {}).get(
                    "settlement_escort_defense") is True):
            self.founder_escort_defense_production_attempts += 1
            self.founder_escort_defense_production_successes += int(
                bool(effect_observed))
            if (candidate.projection or {}).get(
                    "settlement_final_escort_preparation") is True:
                self.founder_final_escort_preparation_production_attempts += 1
                self.founder_final_escort_preparation_production_successes += int(
                    bool(effect_observed))
        if candidate.category == "city_founding":
            if (candidate.projection or {}).get(
                    "settlement_escort_present") is True:
                self.founder_escorted_settlement_attempts += 1
                self.founder_escorted_settlement_completions += int(
                    bool(effect_observed))
                if (candidate.projection or {}).get(
                        "settlement_final_escort") is True:
                    self.founder_final_escorted_settlement_attempts += 1
                    self.founder_final_escorted_settlement_completions += int(
                        bool(effect_observed))
            if (candidate.projection or {}).get(
                    "settlement_escort_safe_bypass") is True:
                self.founder_unescorted_safe_settlement_attempts += 1
                self.founder_unescorted_safe_settlement_completions += int(
                    bool(effect_observed))
            if effect_observed:
                self._founder_route_threats.pop(
                    candidate.action.get("actor_id"), None)
            # A settlement attempt ends the current movement corridor whether
            # the site succeeds or the unit must search from the same tile.
            self._founder_cardinal_intents.pop(
                candidate.action.get("actor_id"), None)
            self._founder_route_positions.pop(
                candidate.action.get("actor_id"), None)
            site_key = self._settlement_site_key(snapshot, candidate.action)
            if site_key is not None and not effect_observed:
                self._failed_settlement_sites.add(site_key)
        self._record_founder_route_outcome(
            candidate, snapshot, after_snapshot)
        self._record_exploration_destination_outcome(
            candidate, snapshot, after_snapshot)
        if diagnostics is not None:
            diagnostics["bookkeeping_latency_ms"] = (
                diagnostics.get("bookkeeping_latency_ms", 0.0)
                + (time.perf_counter() - bookkeeping_started) * 1000.0)
        grounding_started = time.perf_counter()
        key = (candidate.action_key, self._grounding_signature(snapshot, candidate))
        if effect_observed:
            self._no_effect_attempts.pop(key, None)
        else:
            self._no_effect_attempts[key] = self._no_effect_attempts.get(key, 0) + 1
        if diagnostics is not None:
            diagnostics["grounding_latency_ms"] = (
                diagnostics.get("grounding_latency_ms", 0.0)
                + (time.perf_counter() - grounding_started) * 1000.0)
        if self._pressure_ranker is None:
            return None
        feedback_started = time.perf_counter()
        feedback_id = feedback_id or "pressure-feedback-" + structural_hash([
            candidate.category, candidate.action,
            getattr(snapshot, "snapshot_id", None),
            getattr(after_snapshot, "snapshot_id", None),
            bool(effect_observed),
            self._no_effect_attempts.get(key, 0),
        ])[:24]
        if diagnostics is not None:
            diagnostics["feedback_latency_ms"] = (
                diagnostics.get("feedback_latency_ms", 0.0)
                + (time.perf_counter() - feedback_started) * 1000.0)
        relief_started = time.perf_counter()
        relief = self.candidate_goal_relief(
            candidate, snapshot, after_snapshot or snapshot, effect_observed)
        if diagnostics is not None:
            diagnostics["goal_relief_latency_ms"] = (
                diagnostics.get("goal_relief_latency_ms", 0.0)
                + (time.perf_counter() - relief_started) * 1000.0)
        conductance_started = time.perf_counter()
        update = self._pressure_ranker.record_outcome(
            candidate, effect_observed, feedback_id,
            relief.realized_relief, relief.source,
            diagnostics=diagnostics)
        if diagnostics is not None:
            diagnostics["conductance_latency_ms"] = (
                diagnostics.get("conductance_latency_ms", 0.0)
                + (time.perf_counter() - conductance_started) * 1000.0)
        downstream_started = time.perf_counter()
        if effect_observed and relief.realized_relief > 0.0:
            self._record_downstream_goal_relief(
                candidate, feedback_id, relief)
        elif effect_observed:
            self._pending_goal_routes.setdefault(
                relief.goal, {})[candidate.category] = {
                    "feedback_id": feedback_id,
                    "snapshot_id": getattr(snapshot, "snapshot_id", None),
                    "turn": int(getattr(snapshot, "turn", 0)),
                }
        if diagnostics is not None:
            diagnostics["downstream_latency_ms"] = (
                diagnostics.get("downstream_latency_ms", 0.0)
                + (time.perf_counter() - downstream_started) * 1000.0)
            diagnostics["calls"] = diagnostics.get("calls", 0) + 1
        return update

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

    def _settlement_site_key(self, snapshot, action):
        unit = snapshot.unit(action.get("actor_id"))
        if unit is None or None in (unit.x, unit.y):
            return None
        return (
            _normalized_type(unit.unit_type), int(snapshot.map_width),
            int(snapshot.map_height), int(unit.x), int(unit.y),
            self._city_layout(snapshot),
        )

    def _founder_traversable_edge(self, snapshot, edge):
        """Scope route-preference evidence to its strategic city geometry."""
        return (edge, self._city_layout(snapshot))

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
        history = self._founder_route_positions.get(unit.unit_id, ())
        immediate_backtrack = bool(
            len(history) >= 2
            and history[-1] == (unit.x, unit.y)
            and history[-2] == (edge[3], edge[4]))
        revisit_indices = (
            tuple(index for index, position in enumerate(history[:-1])
                  if position == (edge[3], edge[4]))
            if history and history[-1] == (unit.x, unit.y) else ())
        recent_revisit = bool(revisit_indices)
        route_cycle_length = (
            len(history) - revisit_indices[-1]
            if revisit_indices else 0)
        return {
            "actor_failed": (
                self._founder_actor_edge(snapshot, unit, edge)
                in self._founder_actor_failed_edges),
            "edge": edge,
            "failed_attempts": self._founder_failed_edges.get(edge, 0),
            "cardinal_corridor_match": bool(
                intent is not None and intent["heading"] == heading),
            "immediate_backtrack": immediate_backtrack,
            "recent_revisit": recent_revisit,
            "route_cycle_length": route_cycle_length,
            "traversable_edge": (
                self._founder_traversable_edge(snapshot, edge)
                in self._founder_traversable_edges),
        }

    def _founder_cycle_has_alternative(
            self, snapshot, action, founder_types, actions=None,
            evidence=None):
        """Suppress a recent revisit only when a fresh grounded move exists."""
        if len(snapshot.cities) >= self.expansion_city_target:
            return False
        if evidence is None:
            evidence = self._founder_move_evidence(
                snapshot, action, founder_types)
        if not evidence.get("recent_revisit"):
            return False
        actor_id = action.get("actor_id")
        action_key = canonical_json_bytes(action).decode("utf-8")
        for alternative in self._actions(snapshot) if actions is None else actions:
            if (alternative.get("action_type") != "unit_move"
                    or alternative.get("actor_id") != actor_id
                    or canonical_json_bytes(alternative).decode("utf-8") == action_key):
                continue
            other_evidence = self._founder_move_evidence(
                snapshot, alternative, founder_types)
            if (other_evidence
                    and not other_evidence.get("actor_failed")
                    and not other_evidence.get("recent_revisit")):
                return True
        return False

    def _founder_attrition_count(self, snapshot, action, founder_types):
        edge = self._founder_edge(snapshot, action, founder_types)
        if edge is None:
            return 0
        key = (edge[0], int(snapshot.map_width), int(snapshot.map_height),
               edge[3], edge[4])
        return int(self._founder_attrition_positions.get(key, 0))

    def _founder_attrition_total(self, snapshot, founder_types):
        """Count observed founder disappearances on this exact map."""
        return sum(
            int(count)
            for key, count in self._founder_attrition_positions.items()
            if (key[0] in founder_types
                and key[1] == int(snapshot.map_width)
                and key[2] == int(snapshot.map_height)))

    def _founder_attrition_has_alternative(
            self, snapshot, action, founder_types, actions=None):
        """Avoid a grounded loss site only when a legal fresh route remains."""
        if (len(snapshot.cities) >= self.expansion_city_target
                or self._founder_attrition_count(
                    snapshot, action, founder_types) <= 0):
            return False
        actor_id = action.get("actor_id")
        action_key = canonical_json_bytes(action).decode("utf-8")
        for alternative in self._actions(snapshot) if actions is None else actions:
            if (alternative.get("action_type") != "unit_move"
                    or alternative.get("actor_id") != actor_id
                    or canonical_json_bytes(alternative).decode(
                        "utf-8") == action_key):
                continue
            evidence = self._founder_move_evidence(
                snapshot, alternative, founder_types)
            if (evidence
                    and not evidence.get("actor_failed")
                    and self._founder_attrition_count(
                        snapshot, alternative, founder_types) <= 0):
                return True
        return False

    def _record_founder_route_outcome(self, candidate, before, after):
        """Record only an exact post-action position as traversability proof."""
        if candidate.category != "expansion_move":
            return
        corridor_attempt = bool(
            (candidate.projection or {}).get("cardinal_corridor_match", False))
        site_preference_attempt = bool(
            (candidate.projection or {}).get(
                "settlement_site_preference_active", False))
        self.founder_cardinal_corridor_attempts += int(corridor_attempt)
        self.founder_settlement_site_preference_attempts += int(
            site_preference_attempt)
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
            self.founder_settlement_site_preference_successes += int(
                site_preference_attempt)
            self._founder_traversable_edges.add(
                self._founder_traversable_edge(before, edge))
            self._founder_actor_failed_edges.discard(actor_edge)
            source = (unit.x, unit.y)
            history = list(self._founder_route_positions.get(
                unit.unit_id, ()))
            if not history or history[-1] != source:
                history = [source]
            history.append(target)
            self._founder_route_positions[unit.unit_id] = tuple(history[-4:])
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

    def _founder_site_escorts(self, snapshot, founder, founder_types):
        """Return packet-grounded combat units occupying a founder's site."""
        if founder is None or founder.x is None or founder.y is None:
            return ()
        return tuple(sorted(
            (unit for unit in self._combat_units(snapshot, founder_types)
             if (unit.x, unit.y) == (founder.x, founder.y)),
            key=lambda unit: unit.unit_id))

    def _directly_foundable_founders(
            self, snapshot, actions, founder_types, unescorted_only=False):
        """Resolve current Found City actors from the authoritative catalog."""
        actor_ids = {
            action.get("actor_id") for action in (actions or ())
            if action.get("action_type") == "unit_build_city"
            and action.get("actor_id") is not None
        }
        founders = tuple(sorted(
            (unit for unit in snapshot.units
             if unit.unit_id in actor_ids
             and unit.x is not None and unit.y is not None
             and _normalized_type(unit.unit_type) in founder_types),
            key=lambda unit: unit.unit_id))
        if not unescorted_only:
            return founders
        return tuple(
            unit for unit in founders
            if not self._founder_site_escorts(
                snapshot, unit, founder_types))

    def _founder_visible_threats(self, snapshot, founder):
        """Return exact packet-visible opponents proximate to one founder."""
        if founder is None or founder.x is None or founder.y is None:
            return ()
        return tuple(sorted(
            (unit for unit in snapshot.visible_enemy_units
             if unit.x is not None and unit.y is not None
             and _distance(
                 founder.x, founder.y, unit.x, unit.y,
                 snapshot.map_width, snapshot.map_height)
             <= self.pressure_survival_threat_radius),
            key=lambda unit: unit.unit_id))

    def _observe_founder_route_threats(self, snapshot, founder_types):
        """Retain exact local contestation for the observed founder lifetime."""
        founders = self._founders(snapshot, founder_types)
        active_ids = {founder.unit_id for founder in founders}
        for founder_id in tuple(self._founder_route_threats):
            if founder_id not in active_ids:
                self._founder_route_threats.pop(founder_id, None)
        for founder in founders:
            threats = self._founder_visible_threats(snapshot, founder)
            if not threats:
                continue
            row = self._founder_route_threats.setdefault(
                founder.unit_id, {
                    "enemy_positions": {},
                    "enemy_unit_ids": set(),
                    "first_observed_turn": int(snapshot.turn),
                    "last_observed_turn": int(snapshot.turn),
                })
            row["enemy_unit_ids"].update(
                threat.unit_id for threat in threats)
            row["enemy_positions"].update({
                threat.unit_id: (int(threat.x), int(threat.y))
                for threat in threats
            })
            row["last_observed_turn"] = int(snapshot.turn)
            self._founder_route_threat_observations.update(
                (snapshot.snapshot_id, founder.unit_id, threat.unit_id)
                for threat in threats)

    def _founder_route_threat(self, snapshot, founder):
        if (founder is None
                or founder.x is None or founder.y is None
                or not self.expansion_escort_route_threat_memory_enabled):
            return None
        row = self._founder_route_threats.get(founder.unit_id)
        if row is None or not any(
                _distance(
                    founder.x, founder.y, x, y,
                    snapshot.map_width, snapshot.map_height)
                <= self.pressure_survival_threat_radius
                for x, y in row["enemy_positions"].values()):
            return None
        return row

    def _founder_threat_avoidance_candidate(
            self, snapshot, action, founder):
        """Move away from exact remembered threat geometry when escort stalls."""
        route_threat = self._founder_route_threat(snapshot, founder)
        target = action.get("target", {})
        if route_threat is None or not isinstance(target, dict):
            return None
        x, y = target.get("x"), target.get("y")
        if x is None or y is None:
            return None
        positions = tuple(route_threat["enemy_positions"].values())
        current_distance = min(
            _distance(
                founder.x, founder.y, tx, ty,
                snapshot.map_width, snapshot.map_height)
            for tx, ty in positions)
        target_distance = min(
            _distance(
                x, y, tx, ty,
                snapshot.map_width, snapshot.map_height)
            for tx, ty in positions)
        if target_distance <= current_distance:
            return None
        return ImpactCandidate(
            action, "founder_threat_avoidance_move",
            960.0 + target_distance,
            "strictly increase a contested founder's distance from exact "
            "remembered opponent geometry while no escort is available",
            {
                "current_route_threat_distance": current_distance,
                "route_threat_first_turn": route_threat[
                    "first_observed_turn"],
                "route_threat_last_turn": route_threat[
                    "last_observed_turn"],
                "route_threat_unit_ids": tuple(sorted(
                    route_threat["enemy_unit_ids"])),
                "target_route_threat_distance": target_distance,
            })

    def _final_escort_threat_active(self, snapshot, founder):
        """Require exact threat evidence before final-route coordination."""
        return bool(
            not self.expansion_escort_threat_gating_enabled
            or self._founder_visible_threats(snapshot, founder)
            or self._founder_route_threat(snapshot, founder))

    def _founder_escort_required(self, snapshot, founder):
        if not self.expansion_escort_retention_enabled:
            return False
        return bool(
            self._final_settlement_escort_active(snapshot, founder)
            or
            not self.expansion_escort_threat_gating_enabled
            or self._founder_visible_threats(snapshot, founder)
            or self._founder_route_threat(snapshot, founder))

    def _final_settlement_escort_active(self, snapshot, founder):
        """Require co-location only for the city that completes the target."""
        return bool(
            self.expansion_final_settlement_escort_enabled
            and self.expansion_escort_retention_enabled
            and self.founder_final_escort_preparation_production_successes > 0
            and self.expansion_city_target > 0
            and len(snapshot.cities) == self.expansion_city_target - 1
            and self._final_escort_threat_active(snapshot, founder))

    def _final_escort_preparation_founders(
            self, snapshot, founder_types):
        """Identify the active founder assigned to the final expansion slot.

        Founders are created monotonically in the engine. When every remaining
        city slot already has an active founder, the newest founder owns the
        final slot. Preparing only that actor avoids restoring unconditional
        escort waiting for earlier safe settlements.
        """
        if (not self.expansion_final_settlement_escort_enabled
                or not self.expansion_escort_retention_enabled):
            return ()
        remaining_slots = self.expansion_city_target - len(snapshot.cities)
        founders = tuple(sorted(
            self._founders(snapshot, founder_types),
            key=lambda unit: unit.unit_id))
        if remaining_slots <= 0 or len(founders) < remaining_slots:
            return ()
        return founders[-1:]

    def _prepared_final_escort_route_founders(
            self, snapshot, founder_types):
        """Return prepared final founders only with exact threat evidence."""
        founders = self._final_escort_preparation_founders(
            snapshot, founder_types)
        if not founders:
            return ()
        if (self
                .founder_final_escort_preparation_production_successes <= 0):
            self._founder_final_escort_unprepared_route_bypass_snapshots.update(
                (snapshot.snapshot_id, founder.unit_id)
                for founder in founders)
            return ()
        threatened = tuple(
            founder for founder in founders
            if self._final_escort_threat_active(snapshot, founder))
        threatened_ids = {founder.unit_id for founder in threatened}
        self._founder_final_escort_unthreatened_route_bypass_snapshots.update(
            (snapshot.snapshot_id, founder.unit_id)
            for founder in founders
            if founder.unit_id not in threatened_ids)
        return threatened

    def _escort_required_founders(
            self, snapshot, actions, founder_types):
        return tuple(
            founder for founder in self._directly_foundable_founders(
                snapshot, actions, founder_types, unescorted_only=True)
            if self._founder_escort_required(snapshot, founder))

    def _escort_target_founders(
            self, snapshot, actions, founder_types):
        """Return exact current founders that a spare escort may approach."""
        rows = {
            founder.unit_id: founder
            for founder in self._escort_required_founders(
                snapshot, actions, founder_types)}
        for founder in self._prepared_final_escort_route_founders(
                snapshot, founder_types):
            if not self._founder_site_escorts(
                    snapshot, founder, founder_types):
                rows[founder.unit_id] = founder
        return tuple(rows[key] for key in sorted(rows))

    def _record_founder_escort_deferral(self, snapshot, founder):
        key = (snapshot.snapshot_id, founder.unit_id)
        self._founder_escort_deferral_snapshots.add(key)
        if self._final_settlement_escort_active(snapshot, founder):
            self._founder_final_escort_deferral_snapshots.add(key)
        current_threats = self._founder_visible_threats(snapshot, founder)
        route_threat = self._founder_route_threat(snapshot, founder)
        if (self.expansion_escort_threat_gating_enabled
                and (current_threats or route_threat)):
            self._founder_escort_threat_deferral_snapshots.add(key)
            if not current_threats and route_threat:
                self._founder_escort_persisted_threat_deferral_snapshots.add(
                    key)

    @property
    def founder_escort_deferral_snapshots(self):
        return len(self._founder_escort_deferral_snapshots)

    @property
    def founder_escort_threat_deferral_snapshots(self):
        return len(self._founder_escort_threat_deferral_snapshots)

    @property
    def founder_escort_persisted_threat_deferral_snapshots(self):
        return len(
            self._founder_escort_persisted_threat_deferral_snapshots)

    @property
    def founder_route_threat_observations(self):
        return len(self._founder_route_threat_observations)

    @property
    def founder_final_escort_deferral_snapshots(self):
        return len(self._founder_final_escort_deferral_snapshots)

    @property
    def founder_final_escort_rendezvous_hold_snapshots(self):
        return len(self._founder_final_escort_rendezvous_hold_snapshots)

    @property
    def founder_final_escort_rendezvous_no_progress_snapshots(self):
        return len(
            self._founder_final_escort_rendezvous_no_progress_snapshots)

    @property
    def founder_final_escort_unprepared_route_bypass_snapshots(self):
        return len(
            self._founder_final_escort_unprepared_route_bypass_snapshots)

    @property
    def founder_final_escort_unthreatened_route_bypass_snapshots(self):
        return len(
            self._founder_final_escort_unthreatened_route_bypass_snapshots)

    def _final_founder_waits_for_rendezvous(
            self, snapshot, founder, founder_types, actions=None):
        """Hold the assigned final founder while a spare combat unit closes.

        Founder and escort usually have the same movement rate. Allowing both
        to move independently preserves their separation forever, so the
        assigned founder yields one action until first co-location. Recovery
        and remembered-threat avoidance are evaluated before this hold.
        """
        if not any(
                candidate.unit_id == founder.unit_id
                for candidate in self._prepared_final_escort_route_founders(
                    snapshot, founder_types)):
            return False
        if self._founder_site_escorts(snapshot, founder, founder_types):
            return False
        if actions is None:
            return False
        spare_combat = tuple(
            unit for unit in self._combat_units(snapshot, founder_types)
            if unit.x is not None
            and unit.y is not None
            and not self._city_defender_is_required(
                snapshot, unit, founder_types))
        if not spare_combat:
            return False
        spare_by_id = {unit.unit_id: unit for unit in spare_combat}
        progress_available = False
        for action in actions:
            if action.get("action_type") != "unit_move":
                continue
            escort = spare_by_id.get(action.get("actor_id"))
            target = action.get("target")
            if escort is None or not isinstance(target, dict):
                continue
            x, y = target.get("x"), target.get("y")
            if x is None or y is None:
                continue
            if any(
                    (enemy.x, enemy.y) == (x, y)
                    for enemy in snapshot.visible_enemy_units):
                continue
            current_distance = _distance(
                escort.x, escort.y, founder.x, founder.y,
                snapshot.map_width, snapshot.map_height)
            target_distance = _distance(
                x, y, founder.x, founder.y,
                snapshot.map_width, snapshot.map_height)
            if target_distance < current_distance:
                progress_available = True
                break
        if not progress_available:
            self._founder_final_escort_rendezvous_no_progress_snapshots.add(
                (snapshot.snapshot_id, founder.unit_id))
            return False
        self._founder_final_escort_rendezvous_hold_snapshots.add(
            (snapshot.snapshot_id, founder.unit_id))
        return True

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
        return len(defenders) <= self._required_garrison_count(city)

    @staticmethod
    def _city_mood_margin(city):
        values = (
            city.feeling_happy, city.feeling_unhappy, city.feeling_angry)
        if not all(row for row in values):
            return None
        return (
            int(city.feeling_happy[-1])
            - int(city.feeling_unhappy[-1])
            - 2 * int(city.feeling_angry[-1]))

    def _required_garrison_count(self, city):
        """Keep packet-observed martial-law coverage near disorder."""
        margin = self._city_mood_margin(city)
        if city.disorder is True or (margin is not None and margin <= 1):
            return min(
                self.military_units_per_city_limit,
                max(1, int(city.size or 1)))
        return 1

    def _military_capacity(self, snapshot):
        return max(
            1, len(snapshot.cities) * self.military_units_per_city_limit)

    @staticmethod
    def _unit_upkeep(unit, index):
        upkeep = tuple(getattr(unit, "upkeep", ()) or ())
        return int(upkeep[index]) if len(upkeep) > index else 0

    @staticmethod
    def _raw_city_surplus(city, index):
        surplus = tuple(getattr(city, "surplus", ()) or ())
        return int(surplus[index]) if len(surplus) > index else 0

    def _unit_gold_upkeep(self, snapshot):
        observed = sum(
            self._unit_upkeep(unit, 3) for unit in snapshot.units)
        declared = getattr(snapshot.economy, "unit_gold_upkeep", None)
        return observed if declared is None else max(observed, int(declared))

    def _city_gold_surplus_per_turn(self, snapshot):
        declared = getattr(
            snapshot.economy, "city_gold_surplus_per_turn", None)
        if declared is not None:
            return int(declared)
        return sum(
            self._raw_city_surplus(city, 3) for city in snapshot.cities)

    def _net_gold_per_turn(self, snapshot):
        """Return ruleset-aware income after packet-observed upkeep.

        V7 projections carry the exact engine-style result. Older captures in
        this repository are civ2civ3/Mixed, where city surplus already includes
        building upkeep but nation-paid unit upkeep must still be subtracted.
        """
        economy = snapshot.economy
        if (economy.gold_per_turn is not None
                and economy.gold_upkeep_style is not None):
            return int(economy.gold_per_turn)
        if economy.gold_upkeep_style == "City":
            return self._city_gold_surplus_per_turn(snapshot)
        return (
            self._city_gold_surplus_per_turn(snapshot)
            - self._unit_gold_upkeep(snapshot))

    def _treasury_reserve_required(self, snapshot, additional_upkeep=0):
        upkeep = self._unit_gold_upkeep(snapshot) + max(
            0, int(additional_upkeep))
        declared = getattr(snapshot.economy, "gold_upkeep_reserve", None)
        immediate = max(upkeep, int(declared or 0))
        return max(
            self.treasury_minimum_gold,
            immediate * self.treasury_reserve_turns)

    def _treasury_deficit(self, snapshot, additional_upkeep=0):
        economy = snapshot.economy
        if not economy.available or economy.gold is None:
            return False
        additional = max(0, int(additional_upkeep))
        reserve = self._treasury_reserve_required(snapshot, additional)
        gold = int(economy.gold)
        net = self._net_gold_per_turn(snapshot) - additional
        # A negative per-turn balance is not itself an emergency. A large,
        # packet-observed treasury can safely fund it for the configured runway.
        # Route production or tax only when the reserve is already breached or
        # the same bounded runway would consume it.
        return bool(
            gold < reserve
            or (net < 0
                and gold + net * self.treasury_reserve_turns < reserve))

    def _current_coinage_contribution(
            self, snapshot, city, current_normalized=None):
        """Return packet-grounded cash that vanishes with a Coinage switch."""
        if city is None:
            return 0
        normalized = (
            _normalized_type(self._current_production_name(city))
            if current_normalized is None else current_normalized)
        capitalization = getattr(
            snapshot.economy, "capitalization_gold_per_turn", None)
        if normalized != "coinage" or capitalization is None:
            return 0
        # V9 exposes the nation total. The current city's nonnegative shield
        # surplus is its bounded contribution to that total; taking the minimum
        # remains conservative when another ruleset applies a conversion bonus.
        return min(
            max(0, int(capitalization)),
            self._city_output(city, 1))

    def _treasury_recovery_can_release(
            self, snapshot, city=None, current_normalized=None):
        """Require one extra funded turn before leaving a cash stabilizer.

        The ordinary deficit threshold answers whether the current snapshot can
        fund the configured runway.  Releasing Coinage exactly at that boundary
        can consume the margin on the next turn and produce an endless
        Coinage/unit oscillation.  One additional observed turn of runway is a
        bounded hysteresis band; it neither changes the emergency threshold nor
        assumes future income.
        """
        economy = snapshot.economy
        if not economy.available or economy.gold is None:
            return False
        reserve = self._treasury_reserve_required(snapshot)
        net = self._net_gold_per_turn(snapshot)
        if net is None:
            return False
        net -= self._current_coinage_contribution(
            snapshot, city, current_normalized)
        return (
            int(economy.gold)
            + min(0, int(net)) * (self.treasury_reserve_turns + 1)
            >= reserve)

    def _food_deficit_city_ids(self, snapshot):
        return tuple(sorted(
            city.city_id for city in snapshot.cities
            if (self._raw_city_surplus(city, 0) < self.food_surplus_reserve
                or city.had_famine is True)))

    @staticmethod
    def _city_food_governor_matches(
            city, reserve, require_happy=False):
        return bool(
            city.governor_available
            and city.governor_enabled is True
            and tuple(city.governor_minimal_surplus)
            == (int(reserve), 0, 0, 0, 0, 0)
            and city.governor_require_happy is bool(require_happy)
            and city.governor_allow_disorder is False
            and city.governor_max_growth is False
            and city.governor_allow_specialists is True
            and tuple(city.governor_factor) == (6, 2, 2, 1, 1, 2)
            and city.governor_happy_factor == 0)

    def _city_food_governor_candidate(self, snapshot, action):
        city = snapshot.city(action.get("city_id"))
        target = action.get("target")
        reserve = (
            target.get("food_surplus_reserve")
            if isinstance(target, dict) else None)
        require_happy = (
            target.get("require_happy", False)
            if isinstance(target, dict) else False)
        if not isinstance(require_happy, bool):
            return None
        if require_happy:
            if not self.city_happiness_governor_enabled:
                return None
            if (city is None or not city.governor_available
                    or reserve != 0 or city.disorder is not True
                    or self._city_food_governor_matches(
                        city, reserve, require_happy=True)):
                return None
            return ImpactCandidate(
                action, "city_happiness_governor", 2400.0,
                "activate the server-side citizen manager for this disordered "
                "city without suppressing national science or tax rates",
                {
                    "city_id": city.city_id,
                    "disorder_before": True,
                    "governor_enabled_before": city.governor_enabled,
                    "require_happy": True,
                    "server_capability": "PACKET_WEB_CMA_SET",
                })
        if (city is None or not city.governor_available
                or reserve != self.food_surplus_reserve
                or self._city_food_governor_matches(city, reserve)):
            return None
        food_surplus = self._raw_city_surplus(city, 0)
        if food_surplus >= reserve and city.had_famine is not True:
            return None
        return ImpactCandidate(
            action, "city_food_governor",
            2100.0 + max(0, reserve - food_surplus) * 25.0,
            "activate the server-side citizen manager with the configured "
            "food-surplus floor before another famine cycle",
            {
                "city_id": city.city_id,
                "food_surplus_before": food_surplus,
                "food_surplus_reserve": reserve,
                "governor_enabled_before": city.governor_enabled,
                "had_famine": city.had_famine,
                "server_capability": "PACKET_WEB_CMA_SET",
            })

    def _local_garrison_deficits(self, snapshot, founder_types=None):
        founder_types = (self._founder_types(snapshot)
                         if founder_types is None else founder_types)
        combat_units = self._combat_units(snapshot, founder_types)
        deficits = []
        for city in snapshot.cities:
            current = sum(
                (unit.x, unit.y) == (city.x, city.y)
                for unit in combat_units)
            required = self._required_garrison_count(city)
            if current < required:
                deficits.append({
                    "city_id": city.city_id,
                    "current": current,
                    "required": required,
                    "x": city.x,
                    "y": city.y,
                })
        return tuple(deficits)

    def _sustainability_facts(self, snapshot, founder_types=None):
        food_deficits = self._food_deficit_city_ids(snapshot)
        defense_deficits = self._local_garrison_deficits(
            snapshot, founder_types)
        disorder_city_ids = tuple(sorted(
            city.city_id for city in snapshot.cities
            if city.disorder is True))
        facts = {
            "defense_deficit_city_ids": tuple(
                row["city_id"] for row in defense_deficits),
            "disorder_city_ids": disorder_city_ids,
            "food_deficit_city_ids": food_deficits,
            "food_safe_fraction": (
                1.0 if not snapshot.cities else
                float(len(snapshot.cities) - len(food_deficits))
                / len(snapshot.cities)),
            "treasury_deficit": self._treasury_deficit(snapshot),
            "treasury_net_gold_per_turn": self._net_gold_per_turn(snapshot),
            "treasury_reserve_required": (
                self._treasury_reserve_required(snapshot)),
        }
        score_gap = self._score_gap(snapshot)
        if score_gap is not None:
            facts["score_gap_to_leader"] = score_gap
        if self._recent_domain_threat(snapshot, "sea"):
            facts["recent_naval_threat"] = True
        return facts

    def _production_upkeep_safe(
            self, snapshot, city, normalized, food_surplus_floor=None):
        spec = self._production_specs.get(normalized, {})
        if spec.get("target_kind") != "unit":
            return True
        food_surplus_floor = (
            self.food_surplus_reserve
            if food_surplus_floor is None else int(food_surplus_floor))
        food_upkeep = int(spec.get("uk_food", 0))
        if (food_upkeep > 0
                and self._raw_city_surplus(city, 0) - food_upkeep
                < food_surplus_floor):
            return False
        gold_upkeep = int(spec.get("uk_gold", 0))
        if (gold_upkeep > 0
                and (not snapshot.economy.available
                     or self._treasury_deficit(snapshot, gold_upkeep))):
            return False
        return True

    def _production_requires_support(self, normalized):
        spec = self._production_specs.get(normalized, {})
        return any(
            int(spec.get(field_name, 0)) > 0
            for field_name in ("uk_food", "uk_shield", "uk_gold"))

    def _unit_domain(self, normalized):
        unit_class = _normalized_type(
            self._production_specs.get(normalized, {}).get("unit_class"))
        if "missile" in unit_class:
            return "missile"
        if any(value in unit_class for value in ("sea", "ocean", "trireme")):
            return "sea"
        if "air" in unit_class or "heli" in unit_class:
            return "air"
        return "land"

    def _unit_power(self, normalized):
        spec = self._production_specs.get(normalized, {})
        if spec.get("target_kind") != "unit":
            return 0.0
        attack = float(spec.get("attack", 0))
        defense = float(spec.get("defense", 0))
        hitpoints = max(1.0, float(spec.get("hitpoints", 10)))
        firepower = max(1.0, float(spec.get("firepower", 1)))
        mobility = float(spec.get("move_rate", 0)) / 3.0
        transport = float(spec.get("transport_cap", 0))
        # Preserve offensive reach and staying power. Transport capacity is a
        # useful secondary capability, but a ferry must not outrank a combat
        # vessel while answering an observed naval threat.
        return (
            (attack * 1.15 + defense) * hitpoints * firepower / 10.0
            + mobility * 0.5 + transport * 0.25)

    def _recent_domain_threat(self, snapshot, domain):
        turn = self._enemy_domain_last_seen.get(domain)
        return (
            turn is not None
            and int(snapshot.turn) - int(turn)
            <= self.strategic_threat_memory_turns)

    def _naval_response_delivery_pending(self, snapshot, normalized):
        """Retain one selected sea capability until an owned instance exists."""
        return bool(
            self._production_specs.get(
                normalized, {}).get("target_kind") == "unit"
            and self._unit_domain(normalized) == "sea"
            and self._recent_domain_threat(snapshot, "sea")
            and not any(
                _normalized_type(unit.unit_type) == normalized
                for unit in snapshot.units))

    @staticmethod
    def _score_gap(snapshot):
        opponent_scores = [
            row.score for row in getattr(snapshot, "opponent_scores", ())
            if row.score is not None and row.score >= 0
            and row.is_alive is not False]
        if (snapshot.own_score is None or snapshot.own_score < 0
                or not opponent_scores):
            return None
        return int(snapshot.own_score) - max(int(value) for value in opponent_scores)

    def _strategic_production_candidate(
            self, snapshot, action, city, name, normalized, projection,
            current_projection, defenders):
        """Rank ruleset-derived capabilities once survival/expansion are safe."""
        if not self.ruleset_driven_production_enabled:
            return None
        spec = self._production_specs.get(normalized, {})
        kind = spec.get("target_kind")
        eta = projection.get("completion_eta_turns")
        if eta is None:
            return None
        score_gap = self._score_gap(snapshot)
        if kind == "unit":
            if not self._production_upkeep_safe(snapshot, city, normalized):
                return None
            if (self._production_requires_support(normalized)
                    and len(defenders) >= self._military_capacity(snapshot)):
                return None
            domain = self._unit_domain(normalized)
            power = self._unit_power(normalized)
            own_domain_units = [
                unit for unit in snapshot.units
                if self._unit_domain(_normalized_type(unit.unit_type)) == domain]
            own_best = max((
                self._unit_power(_normalized_type(unit.unit_type))
                for unit in own_domain_units), default=0.0)
            visible_enemy_power = max((
                self._unit_power(_normalized_type(unit.unit_type))
                for unit in snapshot.visible_enemy_units
                if self._unit_domain(
                    _normalized_type(unit.unit_type)) == domain),
                default=0.0)
            projection.update({
                "capability_domain": domain,
                "capability_power": round(power, 3),
                "current_domain_power": round(own_best, 3),
                "visible_enemy_domain_power": round(
                    visible_enemy_power, 3),
                "score_gap_to_leader": score_gap,
                "ruleset_driven": True,
            })
            # One-shot missile payloads are tactical consumables, not a
            # persistent domain-capability ceiling. They require a separate
            # target and launch policy and must not displace conventional
            # modernization merely because their attack scalar is extreme.
            if domain == "missile":
                return None
            if (domain == "sea" and self.naval_response_enabled
                    and self._recent_domain_threat(snapshot, "sea")):
                return ImpactCandidate(
                    action, "production_naval_response",
                    1120.0 + power * 2.0 - eta,
                    "answer the remembered packet-visible naval threat with "
                    "the strongest sustainable ruleset-buildable sea capability",
                    projection)
            if (domain == "sea" and self.naval_response_enabled
                    and not own_domain_units and score_gap is not None
                    and score_gap < 0):
                return ImpactCandidate(
                    action, "production_fleet_readiness",
                    835.0 + power * 2.0 - eta,
                    "establish a first packet-legal fleet capability while "
                    "trailing the authoritative score leader",
                    projection)
            if (self.modernization_enabled and power > 0
                    and power >= max(own_best + 1.0, own_best * 1.10)):
                threat_deficit = visible_enemy_power > own_best
                defense_deficit = (
                    domain == "land"
                    and float(spec.get("defense", 0)) > 0
                    and len(defenders) < sum(
                        self._required_garrison_count(row)
                        for row in snapshot.cities))
                category = (
                    "production_threat_modernization"
                    if threat_deficit else
                    "production_defense"
                    if defense_deficit else
                    "production_modernization")
                projection["defensive_modernization"] = defense_deficit
                return ImpactCandidate(
                    action, category,
                    (900.0 if defense_deficit else 820.0)
                    + power * 2.0 - eta,
                    ("answer a packet-visible same-domain capability deficit "
                     "with a materially stronger ruleset-derived unit"
                     if threat_deficit else
                     "fill a grounded garrison deficit with a materially "
                     "stronger ruleset-derived defensive unit"
                     if defense_deficit else
                     "replace the current domain capability ceiling with a "
                     "materially stronger ruleset-derived unit"),
                    projection)
            return None

        if kind not in ("building", "improvement"):
            return None
        normalized_priorities = {
            "production_industrialization": tuple(
                map(_normalized_type, INDUSTRIAL_IMPROVEMENT_PRIORITY)),
            "production_research_infrastructure": tuple(
                map(_normalized_type, RESEARCH_IMPROVEMENT_PRIORITY)),
            "production_commerce_infrastructure": tuple(
                map(_normalized_type, COMMERCE_IMPROVEMENT_PRIORITY)),
            "production_coastal_defense": tuple(
                map(_normalized_type, NAVAL_IMPROVEMENT_PRIORITY)),
        }
        category = next((
            candidate_category
            for candidate_category, names in normalized_priorities.items()
            if normalized in names), None)
        if category is None:
            return None
        operating = snapshot.economy.operating_gold_per_turn
        if operating is not None and operating < 0:
            runway_turns = int(eta) + self.treasury_reserve_turns
            if (snapshot.economy.gold is None
                    or int(snapshot.economy.gold)
                    + int(operating) * runway_turns
                    < self._treasury_reserve_required(snapshot)):
                return None
            projection.update({
                "operating_gold_per_turn": int(operating),
                "treasury_construction_runway_turns": runway_turns,
            })
        if category == "production_industrialization":
            if not self.industrialization_enabled:
                return None
            utility = 805.0
            rationale = (
                "expand the city's ruleset-buildable industrial base before "
                "another long fixed-horizon production cycle")
        elif category == "production_research_infrastructure":
            gross = snapshot.research.gross_beakers_per_turn
            upkeep = snapshot.research.tech_upkeep
            research_pressure = bool(
                upkeep is not None and gross is not None
                and (gross <= 0 or upkeep * 4 >= gross))
            if not (research_pressure or score_gap is not None and score_gap < 0):
                return None
            utility = 815.0
            rationale = (
                "increase research infrastructure while technology upkeep "
                "materially consumes gross science or score trails")
        elif category == "production_commerce_infrastructure":
            if operating is None or operating >= 0:
                return None
            utility = 825.0
            rationale = (
                "repair negative operating cash flow only when the observed "
                "treasury can fund construction without treating Coinage "
                "capitalization as structural income")
        else:
            if not (self.naval_response_enabled
                    and self._recent_domain_threat(snapshot, "sea")):
                return None
            utility = 850.0
            rationale = (
                "add packet-legal coastal infrastructure while the remembered "
                "naval threat remains active")
        index = normalized_priorities[category].index(normalized)
        projection.update({
            "score_gap_to_leader": score_gap,
            "ruleset_driven": True,
            "strategic_improvement_rank": index,
        })
        return ImpactCandidate(
            action, category,
            utility + projection["score_value"] * 10.0 - eta - index * 0.01,
            rationale, projection)

    def _move_creates_vulnerable_stack(
            self, snapshot, unit, x, y, founder_types):
        """Avoid non-city stacks which the killstack rule can erase at once."""
        if any((city.x, city.y) == (x, y) for city in snapshot.cities):
            return False
        occupants = [
            row for row in snapshot.units
            if row.unit_id != unit.unit_id and (row.x, row.y) == (x, y)]
        if not occupants:
            return False
        unit_type = _normalized_type(unit.unit_type)
        # Settlement routing is already governed by exact foundability,
        # attrition, threat, and escort checks.  Applying this generic combat
        # killstack heuristic to founders changed packet-confirmed routes and
        # could move the final city into a materially less defensible site.
        if unit_type in founder_types:
            return False
        # Preserve the explicitly configured one-founder/one-escort rendezvous;
        # no other non-city concentration is required by this planner.
        occupant_types = {
            _normalized_type(row.unit_type) for row in occupants}
        founder_escort = bool(
            self.expansion_escort_retention_enabled
            and len(occupants) == 1
            and (
                unit_type in founder_types
                and not occupant_types.intersection(founder_types)
                or unit_type not in founder_types
                and occupant_types.intersection(founder_types)))
        return not founder_escort

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

    def _unit_score_batch_members(
            self, snapshot, actions, founder_types, action_keys=None,
            combat_unit_count=None):
        """Select a lossless city batch that guarantees incremental unit score.

        Freeciv's units-built counter is civilization-wide. A city-local threshold
        misses batches where several productive cities jointly add ten builds. The
        batch compares optimized future completions with the exact current production
        trajectory and commits its members one confirmed production change at a time.
        """
        intent = self._unit_score_batch_intent
        legal_keys = (
            frozenset(action_keys) if action_keys is not None else
            frozenset(
                canonical_json_bytes(action).decode("utf-8")
                for action in actions))
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
            snapshot.snapshot_id, legal_keys,
            tuple(sorted(founder_types)))
        if cache_key == self._unit_score_batch_cache_key:
            return {key: dict(value)
                    for key, value in self._unit_score_batch_cache.items()}

        remaining_turns = self.horizon_turn - snapshot.turn
        current_by_city = {}
        current_score_bearing_nonunit = set()
        best_by_city = {}
        best_action_by_city = {}
        best_requires_support_by_city = {}
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
                best_requires_support_by_city[city.city_id] = (
                    self._production_requires_support(
                        _normalized_type(name)))

        current_total = sum(current_by_city.values())
        optimized_total = sum(best_by_city.values())
        incremental = optimized_total - current_total
        if any(best_requires_support_by_city.values()):
            if combat_unit_count is None:
                combat_unit_count = len(
                    self._combat_units(snapshot, founder_types))
            safe_capacity = max(
                0, self._military_capacity(snapshot) - combat_unit_count)
            incremental = min(incremental, safe_capacity)
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
            direct_founder_projection = self._production_projection(
                city, founder_name, remaining_turns, snapshot=snapshot,
                founder_types=founder_types)
            direct_population_eta = direct_founder_projection.get(
                "population_ready_eta_turns")
            direct_shield_eta = direct_founder_projection.get(
                "shield_completion_eta_turns")
            # Granary-first is a population-timing optimization, not a generic
            # infrastructure preference. If the direct founder is already
            # shield-bound, sequencing can only delay settlement and expose the
            # founder/new city to additional horizon risk.
            if (direct_population_eta is None or direct_shield_eta is None
                    or int(direct_population_eta) <= int(direct_shield_eta)):
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
                    or settlement_runway < max(
                        self.production_minimum_remaining_turns,
                        self.expansion_minimum_settlement_runway_turns)
                    or founder_projection.get("score_value", 0.0) <= 0):
                continue
            action_key = canonical_json_bytes(founder_action).decode("utf-8")
            rank = (combined_eta, action_key)
            if best is None or rank < best[0]:
                best = (rank, founder_action, founder_name,
                        direct_founder_projection, founder_projection,
                        combined_eta, settlement_runway)
        if best is None:
            return None
        (_, founder_action, founder_name, direct_founder_projection,
         founder_projection,
         combined_eta, settlement_runway) = best
        projection.update({
            "founder_deficit_before": founder_deficit,
            "preexpansion_founder": founder_name,
            "preexpansion_founder_kind": founder_action.get("production_kind"),
            "preexpansion_founder_value": founder_action.get("production_value"),
            "preexpansion_founder_completion_eta_turns": (
                founder_projection.get("completion_eta_turns")),
            "preexpansion_founder_population_ready_eta_turns": (
                founder_projection.get("population_ready_eta_turns")),
            "preexpansion_direct_founder_population_ready_eta_turns": (
                direct_founder_projection.get("population_ready_eta_turns")),
            "preexpansion_direct_founder_shield_completion_eta_turns": (
                direct_founder_projection.get("shield_completion_eta_turns")),
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

    def _preexpansion_founder_followup_candidate(
            self, snapshot, action, city, founder_types, current_normalized,
            needs_founder, remaining_turns):
        """Complete a confirmed Granary-first sequence at its first boundary."""
        intent = self._preexpansion_sequences.get(city.city_id)
        if not isinstance(intent, dict) or not needs_founder:
            return None
        if (_normalized_type(_target_name(action)) not in founder_types
                or action.get("production_kind") != intent.get("founder_kind")
                or action.get("production_value") != intent.get("founder_value")):
            return None
        if (city.production_kind == intent.get("granary_kind")
                and city.production_value == intent.get("granary_value")):
            return None
        # Only the automatic target's first shield tick or completion overflow
        # may be discarded. Missing that boundary does not authorize destroying
        # a later, materially accumulated production trajectory.
        discarded_stock = max(0, int(city.shield_stock or 0))
        if discarded_stock > self._city_output(city, 1):
            return None
        projection = self._production_projection(
            city, _target_name(action), remaining_turns, snapshot=snapshot,
            founder_types=founder_types, shield_stock_override=0)
        settlement_eta = projection.get("settlement_eta_turns")
        if (remaining_turns < self.expansion_minimum_remaining_turns
                or settlement_eta is None
                or settlement_eta > remaining_turns
                or projection.get("score_value", 0.0) <= 0):
            return None
        projection.update({
            "preexpansion_followup": True,
            "preexpansion_followup_selected_turn": intent.get("selected_turn"),
            "preexpansion_followup_discarded_shield_stock": discarded_stock,
            "preexpansion_followup_discard_limit": self._city_output(city, 1),
            "preexpansion_followup_shield_stock_assumption": 0,
            "preexpansion_followup_previous_target": current_normalized,
        })
        return ImpactCandidate(
            action, "production_preexpansion_founder",
            960.0 + projection["score_value"] * 10.0
            - projection["completion_eta_turns"],
            "complete the confirmed Granary-first sequence at the bounded "
            "automatic-production boundary",
            projection)

    def _production_sustainability_route(
            self, snapshot, city, current_normalized, proposed_normalized,
            founder_types, current_is_required_founder=False):
        """Return an emergency queue route before another upkeep unit completes."""
        current_spec = self._production_specs.get(current_normalized, {})
        current_is_unit = current_spec.get("target_kind") == "unit"
        current_food_upkeep = int(current_spec.get("uk_food", 0))
        current_gold_upkeep = int(current_spec.get("uk_gold", 0))
        current_is_required_defender = bool(
            current_normalized in NORMALIZED_DEFENDER_TYPES
            and len(tuple(
                unit for unit in self._combat_units(snapshot, founder_types)
                if (unit.x, unit.y) == (city.x, city.y)))
            < self._required_garrison_count(city))
        current_is_funded_naval_response = bool(
            self._naval_response_delivery_pending(
                snapshot, current_normalized))
        food_floor = (
            0 if current_is_required_defender
            else self.food_surplus_reserve)
        protected_first_completion = bool(
            current_is_required_defender
            or current_is_required_founder
            or current_is_funded_naval_response)
        food_risk = bool(
            not protected_first_completion
            and current_is_unit and current_food_upkeep > 0
            and self._raw_city_surplus(city, 0) - current_food_upkeep
            < food_floor)
        treasury_risk = bool(
            self._treasury_deficit(snapshot)
            or (not protected_first_completion
                and current_is_unit and current_gold_upkeep > 0
                and self._treasury_deficit(
                    snapshot, current_gold_upkeep)))
        current_food_stabilizer = any(
            _normalized_type(name) == current_normalized
            for name in FOOD_STABILIZATION_PRIORITY)
        current_treasury_stabilizer = any(
            _normalized_type(name) == current_normalized
            for name in TREASURY_STABILIZATION_PRIORITY)
        proposed_name = next((
            name for name in set(
                FOOD_STABILIZATION_PRIORITY + TREASURY_STABILIZATION_PRIORITY)
            if _normalized_type(name) == proposed_normalized), None)
        if proposed_name is None:
            return None
        if (food_risk and not current_food_stabilizer
                and proposed_name in FOOD_STABILIZATION_PRIORITY):
            return (
                "production_food_stabilization",
                FOOD_STABILIZATION_PRIORITY.index(proposed_name),
                current_food_upkeep,
                "interrupt an automatic support-unit repeat before its next "
                "completion breaches the city food-surplus reserve")
        if (treasury_risk and not current_treasury_stabilizer
                and proposed_name in TREASURY_STABILIZATION_PRIORITY):
            # A treasury switch was observed discarding every newly selected
            # combat-vessel queue after two or three shields, then reopening
            # the same naval choice as soon as Coinage briefly relieved cash.
            # In a multi-city empire, retain the funded response and require a
            # different city to supply recovery. A one-city empire may still
            # use immediate Coinage, but not a long treasury building, as its
            # last safety escape hatch.
            if (current_is_funded_naval_response
                    and (len(snapshot.cities) > 1
                         or proposed_name != "Coinage")):
                return None
            return (
                "production_treasury_stabilization",
                TREASURY_STABILIZATION_PRIORITY.index(proposed_name),
                current_gold_upkeep,
                "redirect production toward treasury recovery before another "
                "turn-start gold-upkeep shortfall")
        return None

    def _production_candidate(
            self, snapshot, action, founder_types, actions,
            action_key=None, action_keys=None, shared_context=None):
        def shared(key, factory):
            if shared_context is None:
                return factory()
            if key not in shared_context:
                shared_context[key] = factory()
            return shared_context[key]

        city = snapshot.city(action.get("city_id"))
        if city is None or not city.buildability_available:
            return None
        if self._current_production_matches(city, action):
            return None
        name = _target_name(action)
        normalized = _normalized_type(name)
        # The policy can only select a ruleset-backed founder or one of its
        # declared economy/defense targets. Reject every other legal build
        # alternative before constructing current and proposed horizon
        # projections.
        if (normalized not in founder_types
                and normalized not in LEGACY_FOUNDER_TYPES
                and normalized not in PLANNED_PRODUCTION_TYPES
                and not (
                    self.ruleset_driven_production_enabled
                    and normalized in self._production_specs)):
            return None
        city_count = len(snapshot.cities)
        current_name = shared(
            ("current_production_name", city.city_id),
            lambda: self._current_production_name(city))
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
        founders = shared(
            "founders",
            lambda: self._founders(snapshot, founder_types))
        queued_founders = shared(
            "queued_founders",
            lambda: self._queued_founder_count(
                snapshot, founder_types, remaining_turns))
        expansion_capacity = city_count + len(founders) + queued_founders
        founder_deficit = max(0, self.expansion_city_target - expansion_capacity)
        needs_founder = founder_deficit > 0
        current_projection = shared(
            ("current_projection", city.city_id),
            lambda: (self._production_projection(
                city, current_name, remaining_turns, snapshot=snapshot,
                founder_types=founder_types)
                     if current_name else None))
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
        preexpansion_followup = self._preexpansion_founder_followup_candidate(
            snapshot, action, city, founder_types, current_normalized,
            needs_founder, remaining_turns)
        if preexpansion_followup is not None:
            return preexpansion_followup
        combat_units = shared(
            "combat_units",
            lambda: self._combat_units(snapshot, founder_types))
        local_defender_count = sum(
            (unit.x, unit.y) == (city.x, city.y)
            for unit in combat_units)
        required_garrison = self._required_garrison_count(city)
        current_food_output_recovery = bool(
            current_normalized in NORMALIZED_FOOD_OUTPUT_TYPES
            and int(city.shield_stock or 0) > 0)
        current_funded_treasury_recovery = bool(
            current_normalized in NORMALIZED_TREASURY_STABILIZATION_TYPES
            and current_normalized != "coinage"
            and int(city.shield_stock or 0) > 0)
        current_treasury_recovery = bool(
            current_normalized in NORMALIZED_TREASURY_STABILIZATION_TYPES
            and (self._treasury_deficit(snapshot)
                 or current_funded_treasury_recovery))
        current_naval_response_in_progress = bool(
            self._naval_response_delivery_pending(
                snapshot, current_normalized))
        if current_food_output_recovery:
            # The server applies the building effect only on completion. Do not
            # destroy accumulated recovery shields because food briefly touches
            # the reserve before the structural building is complete. The
            # authoritative completion removes the queue and releases this hold.
            return None
        mandatory_local_defense = bool(
            local_defender_count < required_garrison
            and current_normalized not in NORMALIZED_DEFENDER_TYPES
            and normalized in NORMALIZED_DEFENDER_TYPES
            and not current_naval_response_in_progress
            and not current_treasury_recovery
            and self._raw_city_surplus(city, 0) >= 0)
        direct_food_output_recovery = bool(
            self._raw_city_surplus(city, 0) < self.food_surplus_reserve
            and normalized in NORMALIZED_FOOD_OUTPUT_TYPES
            and current_normalized not in NORMALIZED_FOOD_OUTPUT_TYPES)
        treasury_recovery_hold = bool(
            current_normalized in NORMALIZED_TREASURY_STABILIZATION_TYPES
            and normalized not in NORMALIZED_TREASURY_STABILIZATION_TYPES
            and (current_funded_treasury_recovery
                 or not self._treasury_recovery_can_release(
                     snapshot, city, current_normalized)))
        if (treasury_recovery_hold
                and not mandatory_local_defense
                and not direct_food_output_recovery):
            return None
        if self.expansion_escort_retention_enabled:
            unescorted_founders = shared(
                "escort_required_founders",
                lambda: self._escort_required_founders(
                    snapshot, actions, founder_types))
            spare_combat_units = tuple(
                unit for unit in combat_units
                if not self._city_defender_is_required(
                    snapshot, unit, founder_types))
            site_escort_defense_needed = bool(
                unescorted_founders and not spare_combat_units)
        else:
            unescorted_founders = ()
            spare_combat_units = ()
            site_escort_defense_needed = False
        remaining_city_slots = max(
            0, self.expansion_city_target - city_count)
        escort_route_eta = self._founder_route_eta()[0]
        final_escort_queue_ready = bool(
            self.expansion_final_settlement_escort_enabled
            and shared(
                "final_escort_queue_ready",
                lambda: any(
                    _normalized_type(self._current_production_name(row))
                    in NORMALIZED_DEFENDER_TYPES
                    and any(
                        (unit.x, unit.y) == (row.x, row.y)
                        for unit in combat_units)
                    and (lambda queued_projection:
                         queued_projection.get("completion_eta_turns") is not None
                         and queued_projection["completion_eta_turns"]
                         <= escort_route_eta)(
                             self._production_projection(
                                 row, self._current_production_name(row),
                                 remaining_turns, snapshot=snapshot,
                                 founder_types=founder_types))
                    for row in snapshot.cities)))
        final_escort_preparation_needed = bool(
            self.expansion_final_settlement_escort_enabled
            and self.expansion_escort_retention_enabled
            and self.founder_final_escort_preparation_production_successes == 0
            and remaining_city_slots > 0
            and len(founders) + queued_founders >= remaining_city_slots
            and not spare_combat_units
            and not final_escort_queue_ready)
        # A desired final escort is not itself a production-defense deficit.
        # Only the narrow immediate, same-kind conversion below may materialize
        # that preparation. If the current city/action cannot satisfy it, keep
        # ordinary production ranking behaviorally identical to the disabled
        # policy instead of suppressing otherwise valid defense/economy work.
        escort_defense_needed = bool(site_escort_defense_needed)
        urgent_founder_repurpose = bool(
            current_is_redundant_founder and current_pop_cost > 0
            and current_completes_by_horizon)
        urgent_site_escort_repurpose = bool(
            site_escort_defense_needed
            and current_normalized in founder_types
            and current_pop_cost > 0
            and current_completes_by_horizon)
        urgent_repurpose = bool(
            urgent_founder_repurpose or urgent_site_escort_repurpose)
        sustainability_route = self._production_sustainability_route(
            snapshot, city, current_normalized, normalized, founder_types,
            current_is_required_founder=bool(
                current_normalized in founder_types
                and expansion_capacity_without_current
                < self.expansion_city_target))

        # Normal changes remain lossless at an empty stock boundary. A redundant
        # positive-population founder is the sole general exception: completing
        # it and automatically repeating it costs citizens. Final-escort
        # preparation has a narrower ruleset-grounded exception when the server
        # advertises another unit target with the same production kind. That
        # exact kind boundary retains carried shields; a cross-kind switch keeps
        # the conservative zero-stock projection.
        if (city.shield_stock not in (None, 0)
                and not urgent_repurpose
                and not mandatory_local_defense
                and not direct_food_output_recovery
                and sustainability_route is None):
            return None
        city_has_grounded_defender = any(
            (unit.x, unit.y) == (city.x, city.y)
            for unit in combat_units)
        final_escort_same_kind_switch = bool(
            final_escort_preparation_needed
            and current_is_redundant_founder
            and city_has_grounded_defender
            and action.get("production_kind") is not None
            and city.production_kind is not None
            and int(action["production_kind"]) == int(city.production_kind))
        repurpose_shield_stock_assumption = (
            max(0, int(city.shield_stock or 0))
            if final_escort_same_kind_switch else 0)
        projection = self._production_projection(
            city, name, remaining_turns, snapshot=snapshot,
            founder_types=founder_types,
            shield_stock_override=(
                repurpose_shield_stock_assumption
                if urgent_repurpose else
                0 if (mandatory_local_defense
                      or direct_food_output_recovery) else None))
        if sustainability_route is not None:
            category, target_index, avoided_upkeep, rationale = (
                sustainability_route)
            projection.update({
                "avoided_next_completion_upkeep": avoided_upkeep,
                "food_surplus_reserve": self.food_surplus_reserve,
                "net_gold_per_turn": self._net_gold_per_turn(snapshot),
                "sustainability_override": True,
                "treasury_reserve_required": (
                    self._treasury_reserve_required(snapshot)),
                "discarded_shield_stock": max(
                    0, int(city.shield_stock or 0)),
            })
            return ImpactCandidate(
                action, category,
                1900.0 - target_index * 10.0
                - min(100.0, float(city.shield_stock or 0)),
                rationale, projection)
        if direct_food_output_recovery:
            target_index = next(
                index for index, target in enumerate(FOOD_OUTPUT_PRIORITY)
                if normalized == _normalized_type(target))
            completion_eta = projection.get("completion_eta_turns")
            if completion_eta is None or completion_eta > remaining_turns:
                return None
            projection.update({
                "authoritative_food_surplus_before": (
                    self._raw_city_surplus(city, 0)),
                "food_output_recovery": True,
                "food_surplus_reserve": self.food_surplus_reserve,
                "discarded_shield_stock": max(
                    0, int(city.shield_stock or 0)),
            })
            return ImpactCandidate(
                action, "production_food_stabilization",
                2200.0
                + max(
                    0, self.food_surplus_reserve
                    - self._raw_city_surplus(city, 0)) * 25.0
                - completion_eta - target_index * 0.01,
                "complete a packet-legal food-output building before further "
                "famine or garrison work",
                projection)
        if normalized in NORMALIZED_DEFENDER_TYPES:
            defender_food_floor = (
                0 if local_defender_count < required_garrison
                else self.food_surplus_reserve)
            # The first replacement garrison is bounded by the local deficit.
            # Existing authoritative support/upkeep observations cannot expose
            # future government free-support slots, so do not let nominal unit
            # upkeep permanently block an otherwise undefended city. The
            # sustainability controllers observe the completed unit's actual
            # upkeep and react before any additional military production.
            if (not mandatory_local_defense
                    and not self._production_upkeep_safe(
                    snapshot, city, normalized,
                    food_surplus_floor=defender_food_floor)):
                return None
        if mandatory_local_defense:
            completion_eta = projection.get("completion_eta_turns")
            target_index = next((
                index for index, target in enumerate(DEFENDER_PRIORITY)
                if name.lower() == target.lower()), None)
            if (target_index is None or completion_eta is None
                    or completion_eta > remaining_turns):
                return None
            # Switching this city away from Coinage removes its shield-to-gold
            # contribution immediately. Project the replacement against that
            # post-switch flow instead of spending income the action destroys.
            net_gold = (
                self._net_gold_per_turn(snapshot)
                - self._current_coinage_contribution(
                    snapshot, city, current_normalized))
            treasury_reserve = self._treasury_reserve_required(snapshot)
            gold = int(snapshot.economy.gold or 0)
            if (net_gold is None
                    or (net_gold < 0
                        and gold + net_gold * max(1, completion_eta)
                        < treasury_reserve)):
                return None
            projection.update({
                "mandatory_local_garrison": True,
                "required_garrison": required_garrison,
                "current_garrison": local_defender_count,
                "discarded_shield_stock": max(
                    0, int(city.shield_stock or 0)),
                "treasury_at_completion": (
                    gold + net_gold * max(1, completion_eta)),
                "treasury_reserve_required": treasury_reserve,
                "upkeep_validation": (
                    "authoritative-post-completion-sustainability-control"),
            })
            return ImpactCandidate(
                action, "production_defense",
                2050.0 + projection["score_value"] * 10.0
                - completion_eta - target_index * 0.01,
                ("restore the missing martial-law garrison immediately; "
                 "validate its realized support cost through authoritative "
                 "food and treasury controls"
                 if city.disorder is True else
                 "replace a missing city-local garrison immediately; validate "
                 "its realized support cost through authoritative food and "
                 "treasury controls"),
                projection)
        if (final_escort_same_kind_switch
                and projection.get("completion_eta_turns") != 0):
            final_escort_same_kind_switch = False
            repurpose_shield_stock_assumption = 0
            projection = self._production_projection(
                city, name, remaining_turns, snapshot=snapshot,
                founder_types=founder_types, shield_stock_override=0)
        urgent_escort_repurpose = bool(
            urgent_site_escort_repurpose or final_escort_same_kind_switch)
        if normalized in founder_types:
            projection.update({
                "existing_founders": len(founders),
                "expansion_capacity_before": expansion_capacity,
                "founder_deficit_before": founder_deficit,
                "queued_founders": queued_founders,
            })

        if urgent_repurpose:
            target_pop_cost = int(self._production_specs.get(
                normalized, {}).get("pop_cost", 0))
            priorities = (
                DEFENDER_PRIORITY if urgent_escort_repurpose
                else IMPROVEMENT_PRIORITY + DEFENDER_PRIORITY)
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
                    0, int(city.shield_stock or 0)
                    - repurpose_shield_stock_assumption),
                "repurpose_shield_stock_assumption": (
                    repurpose_shield_stock_assumption),
                "repurpose_same_production_kind": (
                    final_escort_same_kind_switch),
                "repurpose_target_completes_by_horizon": bool(
                    completion_eta is not None
                    and completion_eta <= remaining_turns),
            })
            if urgent_escort_repurpose:
                projection.update({
                    "settlement_escort_defense": True,
                    "unescorted_founder_ids": tuple(
                        unit.unit_id for unit in unescorted_founders),
                    "settlement_final_escort_preparation": (
                        final_escort_preparation_needed),
                })
            eta_penalty = (remaining_turns + 1 if completion_eta is None
                           else completion_eta)
            return ImpactCandidate(
                action, ("production_defense" if urgent_escort_repurpose
                         else "production_repurpose"),
                (980.0 if urgent_escort_repurpose else 900.0)
                + current_pop_cost * 20.0
                + projection["score_value"] * 10.0
                - eta_penalty - target_index * 0.01,
                ("retain same-kind founder shield carry-over to prepare the "
                 "final target settlement's grounded escort before route wait"
                 if (urgent_escort_repurpose
                     and final_escort_same_kind_switch) else
                 "retire population-costing founder production into a grounded "
                 "escort while a packet-legal settlement is unguarded"
                 if urgent_escort_repurpose else
                 "retire population-costing founder production while expansion "
                 "capacity remains at target without its current queue"),
                projection)

        if escort_defense_needed:
            if (final_escort_preparation_needed
                    and not site_escort_defense_needed):
                return None
            target_index = next((
                index for index, target in enumerate(DEFENDER_PRIORITY)
                if name.lower() == target.lower()), None)
            completion_eta = projection.get("completion_eta_turns")
            if (target_index is not None
                    and normalized not in founder_types
                    and int(self._production_specs.get(
                        normalized, {}).get("pop_cost", 0)) <= 0
                    and completion_eta is not None
                    and completion_eta <= remaining_turns):
                projection.update({
                    "settlement_escort_defense": True,
                    "unescorted_founder_ids": tuple(
                        unit.unit_id for unit in unescorted_founders),
                    "settlement_final_escort_preparation": (
                        final_escort_preparation_needed),
                })
                return ImpactCandidate(
                    action, "production_defense",
                    980.0 + projection["score_value"] * 10.0
                    - completion_eta - target_index * 0.01,
                    ("prepare a grounded escort before the final target "
                     "settlement reaches its legal site"
                     if final_escort_preparation_needed else
                     "fill a grounded contested-settlement escort deficit "
                    "from an empty production stock"),
                    projection)

        local_defenders = tuple(
            unit for unit in combat_units
            if (unit.x, unit.y) == (city.x, city.y))
        required_garrison = self._required_garrison_count(city)
        target_index = next((
            index for index, target in enumerate(DEFENDER_PRIORITY)
            if name.lower() == target.lower()), None)
        completion_eta = projection.get("completion_eta_turns")
        mood_margin = self._city_mood_margin(city)
        city_at_disorder_risk = bool(
            city.disorder is True
            or (mood_margin is not None and mood_margin <= 1))
        if (city_at_disorder_risk
                and len(local_defenders) < required_garrison
                and target_index is not None
                and completion_eta is not None
                and completion_eta <= remaining_turns):
            return ImpactCandidate(
                action, "production_defense",
                (995.0 if city.disorder is True else 850.0)
                + projection["score_value"] * 10.0
                - completion_eta - target_index * 0.01,
                ("restore an at-risk martial-law garrison before further "
                 "expansion"
                 if city_at_disorder_risk
                 else
                 "cover the city-local defense deficit before further "
                 "expansion"),
                dict(
                    projection,
                    required_garrison=required_garrison,
                    current_garrison=len(local_defenders)))

        if needs_founder and current_normalized in founder_types:
            return None
        preexpansion_growth = self._preexpansion_growth_candidate(
            snapshot, action, actions, city, projection, founder_types,
            founder_deficit, current_normalized, remaining_turns)
        if preexpansion_growth is not None:
            return preexpansion_growth
        if (needs_founder and normalized in founder_types
                and not (
                    self.founder_attrition_rebuild_limit > 0
                    and self._founder_attrition_total(
                        snapshot, founder_types)
                    >= self.founder_attrition_rebuild_limit
                    and snapshot.visible_enemy_units)
                and remaining_turns >= self.expansion_minimum_remaining_turns
                and projection.get("settlement_eta_turns") is not None
                and projection["settlement_eta_turns"] <= remaining_turns
                and projection.get("settlement_runway_turns", -1)
                >= self.expansion_minimum_settlement_runway_turns
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

        defenders = combat_units
        strategic_candidate = self._strategic_production_candidate(
            snapshot, action, city, name, normalized, projection,
            current_projection, defenders)
        if strategic_candidate is not None:
            return strategic_candidate
        local_defenders = tuple(
            unit for unit in defenders
            if (unit.x, unit.y) == (city.x, city.y))
        required_garrison = self._required_garrison_count(city)
        total_required_garrisons = sum(
            self._required_garrison_count(row) for row in snapshot.cities)
        defense_deficit = len(defenders) < total_required_garrisons
        if defense_deficit and current_name in DEFENDER_PRIORITY:
            return None
        if defense_deficit:
            for index, target in enumerate(DEFENDER_PRIORITY):
                if name.lower() == target.lower():
                    return ImpactCandidate(
                        action, "production_defense",
                        (995.0 if city.disorder is True else 850.0)
                        + projection["score_value"] * 10.0
                        - projection["completion_eta_turns"] - index * 0.01,
                        ("restore an at-risk martial-law garrison with a "
                         "horizon-completing defender"
                         if city.disorder is True
                         or self._city_mood_margin(city) in (0, 1)
                         else
                         "cover the city-defense deficit with a "
                         "horizon-completing unit"),
                        dict(projection, required_garrison=required_garrison,
                             current_garrison=len(local_defenders),
                             total_required_garrisons=(
                                 total_required_garrisons)))

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
            if (self._production_requires_support(normalized)
                    and len(defenders) >= self._military_capacity(snapshot)):
                continue
            # Batch projection is relevant only to a score-bearing military
            # target. Deferring it until this branch avoids scanning every
            # city/action trajectory when expansion, timing, or target kind
            # has already made the current alternative ineligible.
            unit_score_batch = shared(
                "unit_score_batch",
                lambda: self._unit_score_batch_members(
                    snapshot, actions, founder_types,
                    action_keys=action_keys,
                    combat_unit_count=len(defenders))).get(
                    action_key if action_key is not None else
                    canonical_json_bytes(action).decode("utf-8"))
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
        if self._garrison_move_candidate(
                snapshot, action, unit, founder_types) is not None:
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

    def _move_candidate(
            self, snapshot, action, founder_types, actions=None):
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
        if self._move_creates_vulnerable_stack(
                snapshot, unit, x, y, founder_types):
            return None
        novelty = 1.0 if (x, y) not in self.visited_positions else 0.0
        city_distance = self._distance_from_cities(snapshot, x, y)
        if unit_type in founder_types:
            recovery_reason = self._founder_population_recovery_reason(
                snapshot, unit_type)
            if recovery_reason is not None:
                population = int(self._production_specs.get(
                    unit_type, {}).get("pop_cost", 0))
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
                projection = {
                    "current_city_distance": current_distance,
                    "recovered_population": population,
                    "target_city_distance": target_distance,
                    "target_city_ids": nearest_city_ids,
                }
                if recovery_reason != "expansion_target_complete":
                    projection.update(self._settlement_deadline_projection(
                        snapshot, recovery_reason))
                return ImpactCandidate(
                    action, "population_recovery_move",
                    970.0 + population * 5.0 - target_distance,
                    ("strictly reduce a non-score-bearing founder's distance "
                     "to an owned city for exact ruleset population recovery"
                     if recovery_reason != "expansion_target_complete" else
                    "strictly reduce a surplus founder's distance to an owned "
                     "city for exact ruleset population recovery"),
                    projection)
            if self.expansion_escort_retention_enabled and any(
                    founder.unit_id == unit.unit_id
                    for founder in self._escort_required_founders(
                        snapshot, actions, founder_types)):
                avoidance = self._founder_threat_avoidance_candidate(
                    snapshot, action, unit)
                if avoidance is not None:
                    return avoidance
                # When no exact remembered-threat escape exists, preserve the
                # legal site while a spare grounded combat unit approaches.
                self._record_founder_escort_deferral(snapshot, unit)
                return None
            if self._final_founder_waits_for_rendezvous(
                    snapshot, unit, founder_types, actions):
                return None
            if (len(snapshot.cities) >= self.expansion_city_target
                    or self._founder_settlement_deadline_exhausted(snapshot)):
                return None
            evidence = self._founder_move_evidence(
                snapshot, action, founder_types)
            if self._founder_cycle_has_alternative(
                    snapshot, action, founder_types, actions=actions,
                    evidence=evidence):
                return None
            if self._founder_attrition_has_alternative(
                    snapshot, action, founder_types, actions=actions):
                return None
            projection = None
            route_utility = 0.0
            utility = 800.0 + city_distance * 20.0 + novelty * 15.0
            if self.production_strategy == "horizon_score":
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
                    "founder_attrition_position_failures": (
                        self._founder_attrition_count(
                            snapshot, action, founder_types)),
                    "founder_route_eta_turns": self._founder_route_eta()[0],
                    "immediate_backtrack": bool(
                        evidence.get("immediate_backtrack", False)),
                    "recent_route_revisit": bool(
                        evidence.get("recent_revisit", False)),
                    "route_cycle_length": int(
                        evidence.get("route_cycle_length", 0)),
                    "traversable_edge": bool(
                        route_progress and evidence.get("traversable_edge", False)),
                }
                utility += route_utility
                site_eligible = action.get("settlement_site_eligible")
                confirmed_site_available = bool(
                    self.expansion_packet_site_preference_enabled
                    and actions is not None
                    and any(
                        alternative.get("action_type") == "unit_move"
                        and alternative.get("actor_id") == unit.unit_id
                        and alternative.get("settlement_site_eligible") is True
                        for alternative in actions))
                site_preference_active = bool(
                    confirmed_site_available and site_eligible is True)
                if confirmed_site_available:
                    # Preserve city founding itself at utility 1000 while
                    # deterministically preferring a one-move, packet-confirmed
                    # site over additional frontier wandering. Alternatives
                    # remain candidates so a learned failed edge cannot create
                    # an artificial dead end.
                    utility = (
                        self.FOUNDER_SETTLEMENT_SITE_UTILITY
                        if site_preference_active else
                        min(
                            utility,
                            self.FOUNDER_SETTLEMENT_ALTERNATIVE_UTILITY_CEILING))
                projection.update({
                    "settlement_site_eligible": site_eligible,
                    "settlement_site_preference_active": site_preference_active,
                    "settlement_site_preference_available": (
                        confirmed_site_available),
                    "settlement_site_preference_source": (
                        "packet-ruleset-found-city-preconditions"
                        if site_eligible is not None else None),
                })
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
        if (self.expansion_escort_retention_enabled
                and unit.x is not None and unit.y is not None
                and any(
                    combat.unit_id == unit.unit_id
                    for combat in self._combat_units(
                        snapshot, founder_types))):
            foundable = self._escort_target_founders(
                snapshot, actions, founder_types)
            if foundable:
                current_distance = min(
                    _distance(
                        unit.x, unit.y, founder.x, founder.y,
                        snapshot.map_width, snapshot.map_height)
                    for founder in foundable)
                target_distance = min(
                    _distance(
                        x, y, founder.x, founder.y,
                        snapshot.map_width, snapshot.map_height)
                    for founder in foundable)
                if target_distance < current_distance:
                    target_founder_ids = tuple(
                        founder.unit_id for founder in foundable
                        if _distance(
                            x, y, founder.x, founder.y,
                            snapshot.map_width, snapshot.map_height)
                        == target_distance)
                    return ImpactCandidate(
                        action, "founder_escort_move",
                        975.0 - target_distance,
                        ("strictly reduce a spare combat unit's distance to the "
                         "founder assigned to the final expansion slot"
                         if any(
                             founder.unit_id in target_founder_ids
                             for founder in self._prepared_final_escort_route_founders(
                                 snapshot, founder_types))
                         else
                         "strictly reduce a spare combat unit's distance to an "
                         "unescorted packet-legal settlement site"),
                        {
                            "current_founder_distance": current_distance,
                            "settlement_escort_active": True,
                            "settlement_final_escort_preparation": any(
                                founder.unit_id in target_founder_ids
                                for founder in (
                                    self._prepared_final_escort_route_founders(
                                        snapshot, founder_types))),
                            "target_founder_distance": target_distance,
                            "target_founder_ids": target_founder_ids,
                        })
        garrison_move = self._garrison_move_candidate(
            snapshot, action, unit, founder_types)
        if garrison_move is not None:
            return garrison_move
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

    def _settlement_runway_remaining(self, snapshot):
        return max(0, int(self.horizon_turn) - int(snapshot.turn))

    def _founder_settlement_deadline_exhausted(self, snapshot):
        required = self.expansion_minimum_settlement_runway_turns
        return bool(
            self.expansion_settlement_deadline_recovery_enabled
            and self.production_strategy == "horizon_score"
            and len(snapshot.cities) < self.expansion_city_target
            and required > 0
            and self._settlement_runway_remaining(snapshot) <= required)

    def _founder_population_recovery_reason(
            self, snapshot, normalized_founder_type):
        """Return why an exact founder may be recovered instead of expanded.

        Production already rejects founders that cannot preserve the declared
        post-settlement runway. Apply the same fixed-horizon contract to
        existing founders: once even immediate settlement is at its deadline,
        another movement action cannot create a runway-compliant city.
        """
        if (self.production_strategy != "horizon_score"
                or normalized_founder_type not in self._ruleset_founder_types
                or normalized_founder_type not in self._ruleset_add_to_city_types
                or int(self._production_specs.get(
                    normalized_founder_type, {}).get("pop_cost", 0)) <= 0
                or not snapshot.cities):
            return None
        if len(snapshot.cities) >= self.expansion_city_target:
            return "expansion_target_complete"
        if self._founder_settlement_deadline_exhausted(snapshot):
            return "settlement_runway_exhausted"
        return None

    def _settlement_deadline_projection(self, snapshot, reason):
        return {
            "expansion_city_target": self.expansion_city_target,
            "population_recovery_reason": reason,
            "settlement_runway_remaining_turns": (
                self._settlement_runway_remaining(snapshot)),
            "settlement_runway_required_turns": (
                self.expansion_minimum_settlement_runway_turns),
        }

    def _population_recovery_candidate(self, snapshot, action, founder_types):
        """Recover a ruleset founder after target or settlement deadline."""
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
        recovery_reason = self._founder_population_recovery_reason(
            snapshot, normalized)
        if recovery_reason is None:
            return None
        spec = self._production_specs.get(normalized, {})
        population = int(spec.get("pop_cost", 0))
        if population <= 0 or unit.tile != city.tile:
            return None
        projection = {
            "recovered_population": population,
            "population_value_source": "ruleset_ir",
            "target_city_id": city.city_id,
        }
        if recovery_reason != "expansion_target_complete":
            projection.update(self._settlement_deadline_projection(
                snapshot, recovery_reason))
        return ImpactCandidate(
            action, "population_recovery", 990.0 + population,
            ("restore a founder's exact ruleset population cost after its "
             "declared score-bearing settlement runway is exhausted"
             if recovery_reason != "expansion_target_complete" else
             "restore a surplus founder's exact ruleset population cost after "
             "the expansion target is complete"),
            projection)

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

    def _support_recovery_candidate(
            self, snapshot, action, founder_types):
        action_type = action.get("action_type")
        unit = snapshot.unit(action.get("actor_id"))
        if unit is None:
            return None
        food_upkeep = self._unit_upkeep(unit, 0)
        gold_upkeep = self._unit_upkeep(unit, 3)
        home = (
            snapshot.city(unit.homecity)
            if unit.homecity is not None and unit.homecity > 0 else None)
        if action_type == "unit_home_city":
            target = action.get("target")
            target_city_id = (
                target.get("city_id")
                if isinstance(target, dict) else None)
            target_city = (
                snapshot.city(target_city_id)
                if target_city_id is not None else next((
                    city for city in snapshot.cities
                    if (city.x, city.y) == (unit.x, unit.y)), None))
            if (food_upkeep <= 0 or home is None or target_city is None
                    or target_city.city_id == home.city_id
                    or self._raw_city_surplus(home, 0)
                    >= self.food_surplus_reserve
                    or self._raw_city_surplus(target_city, 0) - food_upkeep
                    < self.food_surplus_reserve):
                return None
            return ImpactCandidate(
                action, "food_support_rehome", 1980.0 + food_upkeep * 10.0,
                "move exact food support from a deficit home city to the "
                "packet-legal city currently hosting the unit",
                {
                    "food_surplus_reserve": self.food_surplus_reserve,
                    "from_city_id": home.city_id,
                    "from_food_surplus": self._raw_city_surplus(home, 0),
                    "target_city_id": target_city.city_id,
                    "target_food_surplus_after": (
                        self._raw_city_surplus(target_city, 0) - food_upkeep),
                    "transferred_food_upkeep": food_upkeep,
                })
        if action_type != "unit_disband":
            return None
        if self._city_defender_is_required(snapshot, unit, founder_types):
            return None
        if (food_upkeep > 0 and home is not None
                and self._raw_city_surplus(home, 0)
                < self.food_surplus_reserve):
            return ImpactCandidate(
                action, "food_support_disband", 1960.0 + food_upkeep * 10.0,
                "retire a non-required support unit before an exact food "
                "upkeep loss is forced by the server",
                {
                    "city_id": home.city_id,
                    "food_surplus_before": self._raw_city_surplus(home, 0),
                    "food_surplus_after": (
                        self._raw_city_surplus(home, 0) + food_upkeep),
                    "food_surplus_reserve": self.food_surplus_reserve,
                    "removed_food_upkeep": food_upkeep,
                })
        if gold_upkeep > 0 and self._treasury_deficit(snapshot):
            return ImpactCandidate(
                action, "treasury_support_disband",
                1760.0 + gold_upkeep * 10.0,
                "retire a non-required gold-supported unit before the "
                "turn-start treasury reserve is exhausted",
                {
                    "gold_before": snapshot.economy.gold,
                    "net_gold_per_turn_before": (
                        self._net_gold_per_turn(snapshot)),
                    "net_gold_per_turn_after": (
                        self._net_gold_per_turn(snapshot) + gold_upkeep),
                    "removed_gold_upkeep": gold_upkeep,
                    "treasury_reserve_required": (
                        self._treasury_reserve_required(snapshot)),
                })
        return None

    def _rate_recovery_candidate(self, snapshot, action):
        if action.get("action_type") != "player_rates":
            return None
        target = action.get("target")
        if not isinstance(target, dict):
            return None
        economy = snapshot.economy
        target_tax = target.get("tax_rate")
        target_science = target.get("science_rate")
        target_luxury = target.get("luxury_rate")
        if any(value is None for value in (
                economy.tax_rate, economy.science_rate, economy.luxury_rate,
                target_tax, target_science, target_luxury)):
            return None
        if sum(int(target[key]) for key in (
                "tax_rate", "science_rate", "luxury_rate")) != 100:
            return None
        disorder_city_ids = tuple(sorted(
            city.city_id for city in snapshot.cities
            if city.disorder is True))
        if (self.disorder_luxury_recovery_enabled
                and disorder_city_ids
                and int(target_luxury) == int(economy.luxury_rate) + 10
                and int(target_luxury) <= 60
                and int(target_tax) <= int(economy.tax_rate)
                and int(target_science) <= int(economy.science_rate)
                and not (
                    self._treasury_deficit(snapshot)
                    and int(target_tax) < int(economy.tax_rate))):
            return ImpactCandidate(
                action, "disorder_luxury_shift",
                2300.0 + len(disorder_city_ids) * 25.0
                + int(target_science) * 0.01,
                "shift one packet-valid rate increment to luxury until "
                "authoritative city disorder clears and shield production "
                "can resume",
                {
                    "disorder_city_ids": disorder_city_ids,
                    "luxury_rate_before": int(economy.luxury_rate),
                    "luxury_rate_after": int(target_luxury),
                    "minimum_safe_luxury_rate": (
                        self._minimum_safe_luxury_rate),
                    "science_rate_before": int(economy.science_rate),
                    "science_rate_after": int(target_science),
                    "tax_rate_before": int(economy.tax_rate),
                    "tax_rate_after": int(target_tax),
                })
        if (self._treasury_deficit(snapshot)
                and int(target_tax) > int(economy.tax_rate)
                and int(target_luxury) == int(economy.luxury_rate)):
            return ImpactCandidate(
                action, "treasury_tax_shift",
                2050.0 + int(target_tax) - int(economy.tax_rate),
                "shift one packet-valid rate increment from science to tax "
                "while the exact treasury reserve is unsafe",
                {
                    "gold": economy.gold,
                    "net_gold_per_turn": self._net_gold_per_turn(snapshot),
                    "tax_rate_before": economy.tax_rate,
                    "tax_rate_after": int(target_tax),
                    "treasury_reserve_required": (
                        self._treasury_reserve_required(snapshot)),
                })
        reserve = self._treasury_reserve_required(snapshot)
        if (not self._treasury_deficit(snapshot)
                and int(economy.gold or 0) >= reserve * 2
                and int(economy.tax_rate) > self.normal_tax_rate
                and int(target_tax) < int(economy.tax_rate)
                and int(target_science) > int(economy.science_rate)
                and int(target_tax) >= self.normal_tax_rate
                and int(target_science) <= self.normal_science_rate):
            return ImpactCandidate(
                action, "treasury_tax_restore", 760.0,
                "restore the configured science allocation after the treasury "
                "has retained twice its exact upkeep reserve",
                {
                    "gold": economy.gold,
                    "science_rate_before": economy.science_rate,
                    "science_rate_after": int(target_science),
                    "treasury_reserve_required": reserve,
                })
        normal_luxury = max(
            0, 100 - self.normal_tax_rate - self.normal_science_rate)
        if (self.disorder_luxury_recovery_enabled
                and not disorder_city_ids
                and not self._local_garrison_deficits(snapshot)
                and int(economy.luxury_rate) > normal_luxury
                and int(target_luxury) == int(economy.luxury_rate) - 10
                and int(target_luxury) >= max(
                    normal_luxury, self._minimum_safe_luxury_rate)
                and int(target_tax) >= int(economy.tax_rate)
                and int(target_science) >= int(economy.science_rate)):
            return ImpactCandidate(
                action, "disorder_luxury_restore",
                755.0
                + max(
                    0, int(target_science) - int(economy.science_rate))
                + (5.0 if self._treasury_deficit(snapshot)
                   and int(target_tax) > int(economy.tax_rate) else 0.0),
                "restore one packet-valid luxury increment only after all "
                "cities are orderly and have a grounded local garrison",
                {
                    "luxury_rate_before": int(economy.luxury_rate),
                    "luxury_rate_after": int(target_luxury),
                    "minimum_safe_luxury_rate": (
                        self._minimum_safe_luxury_rate),
                    "science_rate_before": int(economy.science_rate),
                    "science_rate_after": int(target_science),
                    "tax_rate_before": int(economy.tax_rate),
                    "tax_rate_after": int(target_tax),
                })
        return None

    def _government_candidate(self, snapshot, action):
        """Select an exact transition target or finish an active revolution."""
        if action.get("action_type") != "government_change":
            return None
        target = action.get("target")
        if not isinstance(target, dict):
            return None
        government_id = target.get("government_id")
        name = str(target.get("government_name", "")).strip()
        if government_id is None or not name:
            return None
        government = snapshot.government
        normalized_name = name.casefold()
        preferred = self.preferred_government.casefold()

        if government.selection_required:
            intended = str(government.target_name or "").strip().casefold()
            priority = {
                "despotism": 50.0, "monarchy": 40.0,
                "communism": 30.0, "republic": 20.0,
                "democracy": 10.0,
            }.get(normalized_name, 0.0)
            if preferred and normalized_name == preferred:
                priority += 75.0
            if intended and intended != "anarchy" and normalized_name == intended:
                priority += 150.0
            return ImpactCandidate(
                action, "government_recovery", 2000.0 + priority,
                "select the packet-legal intended government to end "
                "research-blocking Anarchy",
                {
                    "current_government": government.current_name,
                    "intended_government": government.target_name,
                    "revolution_finishes": government.revolution_finishes,
                    "target_government": name,
                    "target_government_id": int(government_id),
                })

        if (
            not self.preferred_government
            or not government.available
            or government.in_revolution
            or len(snapshot.cities) < self.government_minimum_city_count
            or str(government.current_name or "").strip().casefold()
                == preferred
            or normalized_name != preferred
        ):
            return None
        remaining_turns = self._settlement_runway_remaining(snapshot)
        if remaining_turns < self.government_minimum_remaining_turns:
            return None
        return ImpactCandidate(
            action, "government_transition", 1500.0,
            "start an exact packet-legal transition to the configured "
            "government while the declared horizon retains recovery runway",
            {
                "current_government": government.current_name,
                "government_minimum_remaining_turns": (
                    self.government_minimum_remaining_turns),
                "government_minimum_city_count": (
                    self.government_minimum_city_count),
                "observed_city_count": len(snapshot.cities),
                "remaining_turns": remaining_turns,
                "target_government": name,
                "target_government_id": int(government_id),
            })

    def _garrison_move_candidate(
            self, snapshot, action, unit, founder_types):
        combat_units = self._combat_units(snapshot, founder_types)
        if not any(row.unit_id == unit.unit_id for row in combat_units):
            return None
        deficits = self._local_garrison_deficits(snapshot, founder_types)
        if not deficits:
            return None
        target = action.get("target")
        if not isinstance(target, dict):
            return None
        x, y = target.get("x"), target.get("y")
        if x is None or y is None:
            return None
        current_distance = min(_distance(
            unit.x, unit.y, row["x"], row["y"],
            snapshot.map_width, snapshot.map_height) for row in deficits)
        target_distance = min(_distance(
            x, y, row["x"], row["y"],
            snapshot.map_width, snapshot.map_height) for row in deficits)
        if target_distance >= current_distance:
            return None
        target_city_ids = tuple(sorted(
            row["city_id"] for row in deficits
            if _distance(
                x, y, row["x"], row["y"],
                snapshot.map_width, snapshot.map_height) == target_distance))
        return ImpactCandidate(
            action, "city_garrison_move",
            965.0 - target_distance,
            "strictly reduce a spare combat unit's distance to an exact "
            "city-local garrison deficit",
            {
                "current_garrison_distance": current_distance,
                "target_city_ids": target_city_ids,
                "target_garrison_distance": target_distance,
            })

    def candidates(
            self, snapshot, excluded=(), excluded_scopes=(),
            diagnostics=None):
        excluded = set(excluded)
        excluded_scopes = set(excluded_scopes)
        result = []
        catalog_started = time.perf_counter()
        actions = self._actions(snapshot)
        if diagnostics is not None:
            diagnostics["catalog_latency_ms"] = (
                diagnostics.get("catalog_latency_ms", 0.0)
                + (time.perf_counter() - catalog_started) * 1000.0)
            diagnostics["legal_action_count"] = (
                diagnostics.get("legal_action_count", 0) + len(actions))
        setup_started = time.perf_counter()
        action_rows = tuple(zip(actions, snapshot.legal_action_json))
        available_action_rows = tuple(
            (action, action_key) for action, action_key in action_rows
            if action_key not in excluded)
        available_actions = tuple(
            action for action, _ in available_action_rows)
        available_action_keys = frozenset(
            action_key for _, action_key in available_action_rows)
        founder_types = self._founder_types(snapshot, actions)
        if (self.expansion_escort_retention_enabled
                and self.expansion_escort_threat_gating_enabled
                and self.expansion_escort_route_threat_memory_enabled):
            self._observe_founder_route_threats(
                snapshot, founder_types)
        production_context = {}
        if diagnostics is not None:
            diagnostics["candidate_setup_latency_ms"] = (
                diagnostics.get("candidate_setup_latency_ms", 0.0)
                + (time.perf_counter() - setup_started) * 1000.0)
        for action, key in action_rows:
            action_started = (
                time.perf_counter() if diagnostics is not None else None)
            if key in excluded:
                continue
            action_type = str(action.get("action_type", ""))
            candidate = None
            if action_type == "player_rates":
                candidate = self._rate_recovery_candidate(snapshot, action)
            elif action_type == "city_governor":
                candidate = self._city_food_governor_candidate(
                    snapshot, action)
            elif action_type in ("unit_disband", "unit_home_city"):
                candidate = self._support_recovery_candidate(
                    snapshot, action, founder_types)
            elif action_type == "government_change":
                candidate = self._government_candidate(snapshot, action)
            elif (action_type in OFFENSIVE_ACTIONS
                    and self._offensive_target_is_visible(snapshot, action)):
                unit = snapshot.unit(action.get("actor_id"))
                if (unit is not None
                        and not self._city_defender_is_required(
                            snapshot, unit, founder_types)):
                    candidate = ImpactCandidate(
                        action, "tactical_attack", 900.0,
                        "execute an exact server-advertised offensive action "
                        "with a non-required combat unit")
            elif action_type == "unit_build_city":
                unit = snapshot.unit(action.get("actor_id"))
                site_key = self._settlement_site_key(snapshot, action)
                settlement_runway = self._settlement_runway_remaining(snapshot)
                settlement_runway_required = (
                    self.expansion_minimum_settlement_runway_turns
                    if self.expansion_settlement_deadline_recovery_enabled
                    else 0)
                escorts = self._founder_site_escorts(
                    snapshot, unit, founder_types)
                escort_required = self._founder_escort_required(
                    snapshot, unit)
                visible_threats = (
                    self._founder_visible_threats(snapshot, unit)
                    if (self.expansion_escort_retention_enabled
                        and self.expansion_escort_threat_gating_enabled)
                    else ())
                route_threat = self._founder_route_threat(snapshot, unit)
                if (unit is not None and len(snapshot.cities) < self.expansion_city_target
                        and self._distance_from_cities(snapshot, unit.x, unit.y)
                        >= self.settle_min_distance
                        and settlement_runway
                        >= settlement_runway_required):
                    if (self.expansion_escort_retention_enabled
                            and escort_required and not escorts):
                        self._record_founder_escort_deferral(snapshot, unit)
                    elif site_key in self._failed_settlement_sites:
                        self._failed_settlement_site_prunes.add(key)
                    else:
                        projection = None
                        if settlement_runway_required > 0:
                            projection = {
                                "settlement_runway_remaining_turns": (
                                    settlement_runway),
                                "settlement_runway_required_turns": (
                                    settlement_runway_required),
                            }
                        if self.expansion_escort_retention_enabled:
                            projection = dict(projection or {})
                            projection.update({
                                "settlement_escort_present": bool(escorts),
                                "settlement_escort_required": bool(
                                    escort_required),
                                "settlement_final_escort": (
                                    self._final_settlement_escort_active(
                                        snapshot, unit)),
                                "settlement_escort_safe_bypass": bool(
                                    self.expansion_escort_threat_gating_enabled
                                    and not escort_required and not escorts),
                                "settlement_escort_threat_gating_enabled": (
                                    self.expansion_escort_threat_gating_enabled),
                                "settlement_escort_unit_ids": tuple(
                                    escort.unit_id for escort in escorts),
                                "settlement_visible_threat_unit_ids": tuple(
                                    threat.unit_id
                                    for threat in visible_threats),
                                "settlement_route_threat_first_turn": (
                                    route_threat.get("first_observed_turn")
                                    if route_threat else None),
                                "settlement_route_threat_last_turn": (
                                    route_threat.get("last_observed_turn")
                                    if route_threat else None),
                                "settlement_route_threat_unit_ids": tuple(
                                    sorted(route_threat["enemy_unit_ids"]))
                                if route_threat else (),
                            })
                        candidate = ImpactCandidate(
                            action, "city_founding", 1000.0,
                            ("found an unthreatened city immediately because no "
                             "packet-visible opponent is within the founder "
                             "threat radius and the declared score-bearing "
                             "runway remains"
                             if (self.expansion_escort_retention_enabled
                                 and self.expansion_escort_threat_gating_enabled
                                 and not escort_required and not escorts
                                 and settlement_runway_required > 0)
                             else "found an unthreatened city immediately "
                             "because no packet-visible opponent is within the "
                             "founder threat radius"
                             if (self.expansion_escort_retention_enabled
                                 and self.expansion_escort_threat_gating_enabled
                                 and not escort_required and not escorts)
                             else "found a city at or beyond the configured spacing "
                             "with a grounded co-located escort and the "
                             "declared score-bearing runway"
                             if (self.expansion_escort_retention_enabled
                                 and settlement_runway_required > 0)
                             else "found a city at or beyond the configured "
                             "spacing with a grounded co-located escort"
                             if self.expansion_escort_retention_enabled
                             else "found a city at or beyond the configured "
                             "spacing with the declared score-bearing runway"
                             if settlement_runway_required > 0
                             else "found a city at or beyond the configured spacing"),
                            projection)
            elif action_type == "unit_join_city":
                candidate = self._population_recovery_candidate(
                    snapshot, action, founder_types)
            elif action_type == "city_production":
                candidate = self._production_candidate(
                    snapshot, action, founder_types, available_actions,
                    action_key=key, action_keys=available_action_keys,
                    shared_context=production_context)
            elif action_type == "unit_move":
                candidate = self._move_candidate(
                    snapshot, action, founder_types, actions=actions)
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
            if diagnostics is not None:
                latency_ms = (
                    time.perf_counter() - action_started) * 1000.0
                if action_type == "city_production":
                    name = "candidate_production_latency_ms"
                elif action_type == "unit_move":
                    name = "candidate_movement_latency_ms"
                else:
                    name = "candidate_other_latency_ms"
                diagnostics[name] = diagnostics.get(name, 0.0) + latency_ms
        finalize_started = time.perf_counter()
        ordered = tuple(sorted(result, key=lambda row: (
            -row.utility, row.category, row.action_key)))
        if diagnostics is not None:
            diagnostics["candidate_finalize_latency_ms"] = (
                diagnostics.get("candidate_finalize_latency_ms", 0.0)
                + (time.perf_counter() - finalize_started) * 1000.0)
        return ordered

    def plan(self, snapshot, excluded=(), excluded_scopes=(),
             diagnostics=None):
        candidate_started = time.perf_counter()
        rows = self.candidates(
            snapshot, excluded=excluded, excluded_scopes=excluded_scopes,
            diagnostics=diagnostics)
        candidate_latency_ms = (
            time.perf_counter() - candidate_started) * 1000.0
        if diagnostics is not None:
            diagnostics["calls"] = diagnostics.get("calls", 0) + 1
            diagnostics["candidate_count"] = (
                diagnostics.get("candidate_count", 0) + len(rows))
            diagnostics["candidate_latency_ms"] = (
                diagnostics.get("candidate_latency_ms", 0.0)
                + candidate_latency_ms)
        if not rows:
            return None
        pressure_artifact = None
        if self._pressure_ranker is not None:
            pressure_started = time.perf_counter()
            rows, pressure_artifact = self._pressure_ranker.rank(
                snapshot, rows, self.expansion_city_target, self.horizon_turn,
                self.pressure_survival_threat_radius,
                diagnostics=diagnostics,
                _goal_facts=self._sustainability_facts(snapshot))
            if diagnostics is not None:
                diagnostics["pressure_latency_ms"] = (
                    diagnostics.get("pressure_latency_ms", 0.0)
                    + (time.perf_counter() - pressure_started) * 1000.0)
                diagnostics["pressure_calls"] = (
                    diagnostics.get("pressure_calls", 0) + 1)
        materialization_started = time.perf_counter()
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
            legal_actions_digest=snapshot.legal_actions_digest,
            spatial=_spatial_target(candidate.action))
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
        if diagnostics is not None:
            diagnostics["materialization_latency_ms"] = (
                diagnostics.get("materialization_latency_ms", 0.0)
                + (time.perf_counter() - materialization_started) * 1000.0)
        return ImpactDecision(candidate, plan, pressure_artifact)
