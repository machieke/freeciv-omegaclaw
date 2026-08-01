"""Stable Impact planning contracts, explicit policies, and pure helpers."""

from dataclasses import dataclass

from ..events.schema import canonical_json_bytes
from .model import Plan


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
HAPPINESS_IMPROVEMENT_PRIORITY = (
    "Temple", "Cathedral", "Amphitheater",
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
        """Whether acceptance can consume an actor before state catches up."""
        return self.action.get("action_type") in (
            "government_change", "unit_build_city", "unit_disband",
            "unit_join_city", "unit_suicide_attack")

    @property
    def unit_scope_consumed_on_accept(self):
        """Whether acceptance can spend an actor hidden by a stale snapshot."""
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
    operation_authority: object = None


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
    """Reconcile accepted actions whose effects outlive the bounded wait."""

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
        if (not authoritative_refresh or effect_observed
                or candidate.terminal_on_accept
                or candidate.unit_scope_consumed_on_accept):
            self.used_scopes.add(scope)
            self.recoveries += int(is_failover and effect_observed)
        else:
            failures = self.failed_attempts.get(scope, 0) + 1
            self.failed_attempts[scope] = failures
            if failures > self.max_no_effect_failovers:
                self.used_scopes.add(scope)
        return is_failover


def normalized_type(value):
    return str(value or "").strip().lower().replace("_", " ")


PLANNED_PRODUCTION_TYPES = frozenset(
    normalized_type(name)
    for name in (
        IMPROVEMENT_PRIORITY + HAPPINESS_IMPROVEMENT_PRIORITY
        + DEFENDER_PRIORITY))
NORMALIZED_DEFENDER_TYPES = frozenset(
    normalized_type(name) for name in DEFENDER_PRIORITY)
NORMALIZED_FOOD_OUTPUT_TYPES = frozenset(
    normalized_type(name) for name in FOOD_OUTPUT_PRIORITY)
NORMALIZED_TREASURY_STABILIZATION_TYPES = frozenset(
    normalized_type(name) for name in TREASURY_STABILIZATION_PRIORITY)
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
NORMALIZED_COMMERCE_IMPROVEMENT_TYPES = frozenset(
    normalized_type(name) for name in COMMERCE_IMPROVEMENT_PRIORITY)
NAVAL_IMPROVEMENT_PRIORITY = (
    "Port Facility", "Coastal Defense", "SAM Battery", "SDI Defense",
)
NORMALIZED_HAPPINESS_IMPROVEMENT_TYPES = frozenset(
    normalized_type(name) for name in HAPPINESS_IMPROVEMENT_PRIORITY)


def wrapped_distance(x, y, tx, ty, width, height):
    if None in (x, y, tx, ty) or width <= 0 or height <= 0:
        return 0
    dx = min((int(x) - int(tx)) % width, (int(tx) - int(x)) % width)
    dy = min((int(y) - int(ty)) % height, (int(ty) - int(y)) % height)
    return max(dx, dy)


def target_name(action):
    target = action.get("target")
    if isinstance(target, dict):
        return str(target.get("production_type", target.get("value", "")))
    return str(target or "")


def spatial_target(action):
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
