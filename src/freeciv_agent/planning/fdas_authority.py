"""Fail-closed bounded authority over an exact legacy city action.

The first FDAS authority slice is deliberately a pass-through boundary.  It
may validate and select a city-governor action only when the legacy planner
already selected the byte-identical action.  This exercises the complete
FDAS pressure/resource/packet/commit chain without introducing an
uncalibrated policy divergence.
"""

from dataclasses import dataclass, replace

from ..events.schema import structural_hash
from ..pressure.fdas_adapter import DependentAtomPressureAdapter
from ..pressure.fdas_resources import DependentAtomSchedulingBridge
from ..pressure.packets import PacketBudget, ResourceKind
from .fdas import ShadowOperationCandidate
from .fdas_commit import FDASCommitBinding, FDASCommitValidator
from .impact_types import ImpactCandidate


_AUTHORITY_IDENTITY = "fdas-bounded-city-stability/1.0"
_DEFENSE_AUTHORITY_IDENTITY = (
    "fdas-bounded-defense-fortification/1.0")


def _defense_target_city(goal):
    values = tuple(
        value.entity_id for value in goal.target_key.arguments
        if (getattr(value, "kind", None) == "city"
            and getattr(value, "entity_id", None) is not None))
    return values[0] if len(values) == 1 else None


def _defense_opportunity_record(revision, actor_id, city_id):
    matches = tuple(
        record for record in revision.records
        if (record.key.predicate == "unit-fortification-opportunity"
            and len(record.key.arguments) == 2
            and getattr(record.key.arguments[0], "entity_id", None)
            == str(actor_id)
            and getattr(record.key.arguments[1], "entity_id", None)
            == str(city_id)))
    return matches[0] if len(matches) == 1 else None


def validate_bounded_defense_fortification_candidate(
        candidate, snapshot, revision, goals):
    """Validate the shared exact fortification safety contract.

    The function grants no authority and changes no candidate.  Keeping this
    check separate lets diagnostic alternative-selection policies prove that
    both arms satisfy the same bounded contract without pretending that the
    alternative was the legacy-selected pass-through.
    """
    if not isinstance(candidate, ShadowOperationCandidate):
        return None, None, "selected-operation-candidate-unavailable"
    if (not candidate.legal_bound
            or candidate.action_key not in snapshot.legal_action_json):
        return None, None, "selected-action-not-currently-legal"
    action = candidate.action
    if (
            action.get("action_type") != "unit_fortify"
            or set(action) != {"action_type", "actor_id"}
            or isinstance(action.get("actor_id"), bool)
            or not isinstance(action.get("actor_id"), int)):
        return (
            None, None,
            "outside-bounded-defense-fortification-action-shape")
    goal_by_id = dict((value.goal.goal_id, value) for value in goals)
    routes = tuple(
        goal_by_id.get(goal_id)
        for goal_id in candidate.operation.goal_ids)
    if (len(routes) != 1
            or routes[0] is None
            or routes[0].deficit_predicate
            != "unit-fortification-opportunity"):
        return None, None, "outside-bounded-unit-fortification-route"
    city_id = _defense_target_city(routes[0])
    city = snapshot.city(city_id)
    actor_id = action["actor_id"]
    actor = snapshot.unit(actor_id)
    if (city is None or city.tile is None or actor is None
            or actor.tile != city.tile):
        return (
            None, None,
            "current-defense-actor-or-city-state-unavailable")
    if str(actor.activity or "").lower() in (
            "fortify", "fortified", "fortifying"):
        return None, None, "current-unit-is-already-fortifying"
    opportunity = _defense_opportunity_record(
        revision, actor_id, city_id)
    if opportunity is None or not opportunity.supports:
        return (
            None, None,
            "fdas-fortification-opportunity-support-unavailable")
    if candidate.resource_keys != (
            "unit-action:{}".format(actor_id),):
        return None, None, "bounded-defense-resource-identity-mismatch"
    permitted_blockers = frozenset((
        "legacy-shadow-control-route-uncompiled",
        "uncompiled-action-effect",
    ))
    unexpected_blockers = tuple(
        value for value in candidate.blockers
        if value not in permitted_blockers)
    if unexpected_blockers:
        return None, None, "candidate-has-noncontractual-blockers"
    return routes[0], opportunity, None


def validate_bounded_defense_reinforcement_candidate(
        candidate, snapshot, revision, goals):
    """Validate one exact, source-safe, non-transport reinforcement step."""
    if not isinstance(candidate, ShadowOperationCandidate):
        return None, None, "selected-operation-candidate-unavailable"
    if (not candidate.legal_bound
            or candidate.action_key not in snapshot.legal_action_json):
        return None, None, "selected-action-not-currently-legal"
    action = candidate.action
    allowed_keys = {
        "action_type", "actor_id", "movement_cost", "target",
        "transport_required",
    }
    target = action.get("target")
    if (action.get("action_type") != "unit_move"
            or not {"action_type", "actor_id", "target"} <= set(action)
            or set(action) - allowed_keys
            or isinstance(action.get("actor_id"), bool)
            or not isinstance(action.get("actor_id"), int)
            or not isinstance(target, dict)
            or set(target) != {"x", "y"}
            or any(isinstance(target.get(name), bool)
                   or not isinstance(target.get(name), int)
                   for name in ("x", "y"))
            or action.get("transport_required") is True):
        return (
            None, None,
            "outside-bounded-defense-reinforcement-action-shape")
    goal_by_id = dict((value.goal.goal_id, value) for value in goals)
    routes = tuple(
        goal_by_id.get(goal_id)
        for goal_id in candidate.operation.goal_ids)
    if (len(routes) != 1
            or routes[0] is None
            or routes[0].deficit_predicate != "city-garrison-deficit"):
        return None, None, "outside-bounded-city-garrison-route"
    city_id = _defense_target_city(routes[0])
    city = snapshot.city(city_id)
    actor_id = action["actor_id"]
    actor = snapshot.unit(actor_id)
    if (city is None or city.tile is None or actor is None
            or actor.tile is None or actor.tile == city.tile):
        return (
            None, None,
            "current-reinforcement-actor-or-city-state-unavailable")
    if (candidate.operation.operation_type
            != "fdas-shadow:city-garrison-deficit:unit_move"
            or candidate.operation.target_ref
            != "city:{}".format(city_id)):
        return None, None, "reinforcement-operation-target-mismatch"
    native_route = snapshot.movement_route(actor_id, city.tile)
    if not bool(
            native_route is not None
            and native_route.authority == "freeciv-server-pathfinder"
            and native_route.schema_version == "1.0"
            and native_route.reachable
            and native_route.origin_tile == actor.tile
            and native_route.turn == snapshot.turn
            and native_route.source_seq <= snapshot.identity.source_seq
            and snapshot.map_width > 0):
        return None, None, "current-native-reinforcement-route-unavailable"
    first_x = native_route.first_step_tile % snapshot.map_width
    first_y = native_route.first_step_tile // snapshot.map_width
    if target != {"x": first_x, "y": first_y}:
        return None, None, "reinforcement-first-step-route-mismatch"
    movement_cost = action.get("movement_cost")
    if (movement_cost is not None
            and (isinstance(movement_cost, bool)
                 or not isinstance(movement_cost, int)
                 or movement_cost <= 0
                 or (actor.moves_left is not None
                     and movement_cost > actor.moves_left))):
        return None, None, "reinforcement-movement-budget-mismatch"
    if candidate.resource_keys != (
            "unit-action:{}".format(actor_id),):
        return None, None, "bounded-defense-resource-identity-mismatch"
    permitted_blockers = frozenset((
        "legacy-shadow-control-route-uncompiled",
        "uncompiled-action-effect",
    ))
    unexpected_blockers = tuple(
        value for value in candidate.blockers
        if value not in permitted_blockers)
    if unexpected_blockers:
        return None, None, "candidate-has-noncontractual-blockers"
    deficit = revision.record(routes[0].deficit_atom_id)
    if deficit is None or not deficit.supports:
        return None, None, "fdas-city-garrison-support-unavailable"
    return routes[0], deficit, None


@dataclass(frozen=True)
class FdasAuthorityReadout:
    status: str
    reason: object
    snapshot_id: str
    revision_id: str
    operation_id: object
    action_key: object
    authority_slice: str
    checks: tuple
    authority_pressure: object
    scheduling: object
    commit_validation: object
    readout_hash: str

    def __post_init__(self):
        if self.status not in ("authorized", "fallback", "disabled"):
            raise ValueError("invalid FDAS authority readout status")
        object.__setattr__(self, "checks", tuple(self.checks))
        if self.status == "authorized":
            if self.reason is not None or not self.action_key:
                raise ValueError("authorized FDAS readout is inconsistent")
        elif not isinstance(self.reason, str) or not self.reason:
            raise ValueError("non-authorized FDAS readout needs a reason")

    @property
    def authorized(self):
        return self.status == "authorized"

    @property
    def policy_authority(self):
        return self.authorized

    def to_dict(self):
        return {
            "action_key": self.action_key,
            "authority_slice": self.authority_slice,
            "authority_pressure": self.authority_pressure,
            "checks": list(self.checks),
            "commit_validation": self.commit_validation,
            "operation_id": self.operation_id,
            "policy_authority": self.policy_authority,
            "readout_hash": self.readout_hash,
            "reason": self.reason,
            "revision_id": self.revision_id,
            "scheduling": self.scheduling,
            "snapshot_id": self.snapshot_id,
            "status": self.status,
        }


class FdasBoundedCityAuthority(object):
    """Authorize one exact, already-selected food-governor action or fallback."""

    AUTHORITY_IDENTITY = _AUTHORITY_IDENTITY

    def __init__(self, pressure_adapter=None, scheduling_bridge=None,
                 commit_validator=None):
        self.pressure_adapter = (
            pressure_adapter or DependentAtomPressureAdapter())
        self.scheduling_bridge = (
            scheduling_bridge or DependentAtomSchedulingBridge())
        self.commit_validator = commit_validator or FDASCommitValidator()

    @staticmethod
    def relevant(legacy_candidate):
        """Return whether this bounded slice can affect the legacy winner."""
        if not isinstance(legacy_candidate, ImpactCandidate):
            return False
        action = legacy_candidate.action
        return bool(
            action.get("action_type") == "city_governor"
            and action.get("target") == {"food_surplus_reserve": 1})

    @staticmethod
    def _readout(status, reason, snapshot, revision, operation_id=None,
                 action_key=None, checks=(), scheduling=None,
                 validation=None, authority_pressure=None):
        scheduling_value = (
            None if scheduling is None
            else scheduling.to_dict(include_latency=False))
        validation_value = (
            None if validation is None else validation.to_dict())
        semantic = {
            "action_key": action_key,
            "authority_slice": _AUTHORITY_IDENTITY,
            "authority_pressure": authority_pressure,
            "checks": list(checks),
            "commit_validation": validation_value,
            "operation_id": operation_id,
            "reason": reason,
            "revision_id": revision.revision_id,
            "scheduling": scheduling_value,
            "snapshot_id": snapshot.snapshot_id,
            "status": status,
        }
        return FdasAuthorityReadout(
            status, reason, snapshot.snapshot_id, revision.revision_id,
            operation_id, action_key, _AUTHORITY_IDENTITY, tuple(checks),
            authority_pressure, scheduling_value, validation_value,
            structural_hash(semantic))

    @staticmethod
    def _promote(candidate, snapshot, goals):
        if not isinstance(candidate, ShadowOperationCandidate):
            return None, "selected-operation-candidate-unavailable"
        if not candidate.legal_bound \
                or candidate.action_key not in snapshot.legal_action_json:
            return None, "selected-action-not-currently-legal"
        action = candidate.action
        target = action.get("target")
        reserve = (
            target.get("food_surplus_reserve")
            if isinstance(target, dict) else None)
        if (
                action.get("action_type") != "city_governor"
                or set(target or {}) != {"food_surplus_reserve"}
                or isinstance(reserve, bool)
                or not isinstance(reserve, int)
                or not 1 <= reserve <= 10):
            return None, "outside-bounded-city-stability-action-shape"
        goal_by_id = dict((value.goal.goal_id, value) for value in goals)
        routes = tuple(
            goal_by_id.get(goal_id)
            for goal_id in candidate.operation.goal_ids)
        if (
                not routes
                or any(value is None for value in routes)
                or any(value.deficit_predicate != "city-food-deficit"
                       for value in routes)):
            return None, "outside-bounded-city-food-deficit-route"
        city_id = str(action.get("city_id"))
        city = snapshot.city(city_id)
        if city is None or not city.governor_available:
            return None, "current-city-governor-state-unavailable"
        food_surplus = (
            city.surplus[0] if tuple(city.surplus or ()) else None)
        if food_surplus is None or int(food_surplus) >= reserve:
            return None, "current-city-food-deficit-not-confirmed"
        unexpected_blockers = tuple(
            value for value in candidate.blockers
            if value != "uncompiled-action-effect")
        if unexpected_blockers:
            return None, "candidate-has-noncontractual-blockers"
        operation = replace(
            candidate.operation,
            provenance=tuple(
                value for value in candidate.operation.provenance
                if value != "no-action-authority") + (
                    _AUTHORITY_IDENTITY,
                    "freeciv-proxy-city-governor-contract/v10",
                    "legacy-selected-byte-identical-pass-through",
                ))
        semantic = {
            "action_key": candidate.action_key,
            "authority_identity": _AUTHORITY_IDENTITY,
            "goal_ids": list(operation.goal_ids),
            "operation_spec_digest": operation.spec_digest,
            "resource_keys": list(candidate.resource_keys),
            "snapshot_id": snapshot.snapshot_id,
        }
        promoted = replace(
            candidate,
            operation=operation,
            authority_eligible=True,
            blockers=(),
            provenance=tuple(candidate.provenance) + (
                _AUTHORITY_IDENTITY,
                "freeciv-proxy-city-governor-contract/v10",
                "legacy-selected-byte-identical-pass-through",
            ),
            candidate_hash=structural_hash(semantic),
        )
        return promoted, None

    def evaluate(self, snapshot, revision, shadow_evaluation,
                 legacy_candidate, authority_enabled=False,
                 city_stability_enabled=False):
        checks = []
        if not authority_enabled or not city_stability_enabled:
            return self._readout(
                "disabled", "fdas-city-stability-authority-disabled",
                snapshot, revision, checks=("domain-authority-gate",))
        checks.append("domain-authority-gate")
        if not isinstance(legacy_candidate, ImpactCandidate):
            return self._readout(
                "fallback", "legacy-selected-candidate-unavailable",
                snapshot, revision, checks=checks)
        if (
                shadow_evaluation.snapshot_id != snapshot.snapshot_id
                or shadow_evaluation.revision_id != revision.revision_id):
            return self._readout(
                "fallback", "fdas-evaluation-not-current",
                snapshot, revision, checks=checks + [
                    "revision-current-evaluation"])
        checks.append("revision-current-evaluation")
        food_goal_ids = frozenset(
            value.goal.goal_id for value in shadow_evaluation.goals
            if value.deficit_predicate == "city-food-deficit")
        candidates = tuple(
            value for value in shadow_evaluation.candidates
            if (value.action_key == legacy_candidate.action_key
                and value.operation.goal_ids
                and set(value.operation.goal_ids) <= food_goal_ids))
        if len(candidates) != 1:
            return self._readout(
                "fallback", "legacy-winner-has-no-unique-fdas-food-route",
                snapshot, revision, action_key=legacy_candidate.action_key,
                checks=checks + ["legacy-winner-fdas-route-binding"])
        source = candidates[0]
        selected_id = source.operation.operation_id
        checks.append("legacy-winner-fdas-route-binding")
        candidate, reason = self._promote(
            source, snapshot, shadow_evaluation.goals)
        if candidate is None:
            return self._readout(
                "fallback", reason, snapshot, revision,
                operation_id=selected_id, action_key=source.action_key,
                checks=checks + ["bounded-city-stability-contract"])
        checks.append("bounded-city-stability-contract")
        goal_ids = frozenset(candidate.operation.goal_ids)
        route_goals = tuple(
            value for value in shadow_evaluation.goals
            if value.goal.goal_id in goal_ids)
        authority_pressure = self.pressure_adapter.evaluate(
            revision, route_goals, (candidate,))
        authority_pressure_value = {
            "evaluation_hash": authority_pressure.evaluation_hash,
            "schedule_hash": authority_pressure.schedule.get(
                "structural_hash"),
            "selected_operation_id": authority_pressure.schedule.get(
                "selected_operation_id"),
            "status": authority_pressure.status,
        }
        if authority_pressure.schedule.get("selected_operation_id") != \
                candidate.operation.operation_id:
            return self._readout(
                "fallback", "fdas-authority-route-not-selected",
                snapshot, revision, operation_id=selected_id,
                action_key=candidate.action_key,
                checks=checks + ["authority-pressure-readout"],
                authority_pressure=authority_pressure_value)
        checks.append("authority-pressure-readout")
        scheduling = self.scheduling_bridge.schedule(
            authority_pressure, (candidate,), snapshot,
            packet_budgets=(
                PacketBudget(ResourceKind.ACTION, 1),
                PacketBudget(ResourceKind.CPU, 1),
            ))
        if candidate.operation.operation_id not in \
                scheduling.joint_selected_operation_ids:
            return self._readout(
                "fallback", "fdas-resource-or-packet-schedule-rejected",
                snapshot, revision, operation_id=selected_id,
                action_key=candidate.action_key,
                checks=checks + ["resource-and-packet-schedule"],
                scheduling=scheduling,
                authority_pressure=authority_pressure_value)
        checks.append("resource-and-packet-schedule")
        binding = FDASCommitBinding.create(
            revision, snapshot, candidate, route_goals)
        validation = self.commit_validator.validate(
            binding, revision, snapshot, candidate,
            authority_enabled=True)
        if not validation.plan_materialization_authorized:
            return self._readout(
                "fallback", validation.reason, snapshot, revision,
                operation_id=selected_id, action_key=candidate.action_key,
                checks=checks + ["exact-fdas-commit-validation"],
                scheduling=scheduling, validation=validation,
                authority_pressure=authority_pressure_value)
        checks.append("exact-fdas-commit-validation")
        return self._readout(
            "authorized", None, snapshot, revision,
            operation_id=selected_id, action_key=candidate.action_key,
            checks=checks, scheduling=scheduling, validation=validation,
            authority_pressure=authority_pressure_value)


class FdasBoundedDefenseAuthority(object):
    """Authorize one exact legacy-selected fortification or fallback."""

    AUTHORITY_IDENTITY = _DEFENSE_AUTHORITY_IDENTITY

    def __init__(self, pressure_adapter=None, scheduling_bridge=None,
                 commit_validator=None):
        self.pressure_adapter = (
            pressure_adapter or DependentAtomPressureAdapter())
        self.scheduling_bridge = (
            scheduling_bridge or DependentAtomSchedulingBridge())
        self.commit_validator = commit_validator or FDASCommitValidator()

    @staticmethod
    def relevant(legacy_candidate):
        """Return whether the winner belongs to the defense authority domain."""
        return bool(
            isinstance(legacy_candidate, ImpactCandidate)
            and legacy_candidate.category == "city_defense")

    @staticmethod
    def _readout(status, reason, snapshot, revision, operation_id=None,
                 action_key=None, checks=(), scheduling=None,
                 validation=None, authority_pressure=None):
        scheduling_value = (
            None if scheduling is None
            else scheduling.to_dict(include_latency=False))
        validation_value = (
            None if validation is None else validation.to_dict())
        semantic = {
            "action_key": action_key,
            "authority_slice": _DEFENSE_AUTHORITY_IDENTITY,
            "authority_pressure": authority_pressure,
            "checks": list(checks),
            "commit_validation": validation_value,
            "operation_id": operation_id,
            "reason": reason,
            "revision_id": revision.revision_id,
            "scheduling": scheduling_value,
            "snapshot_id": snapshot.snapshot_id,
            "status": status,
        }
        return FdasAuthorityReadout(
            status, reason, snapshot.snapshot_id, revision.revision_id,
            operation_id, action_key, _DEFENSE_AUTHORITY_IDENTITY,
            tuple(checks), authority_pressure, scheduling_value,
            validation_value, structural_hash(semantic))

    @staticmethod
    def _target_city(goal):
        return _defense_target_city(goal)

    @staticmethod
    def _opportunity_record(revision, actor_id, city_id):
        return _defense_opportunity_record(revision, actor_id, city_id)

    def _promote(self, candidate, snapshot, revision, goals):
        _route, opportunity, reason = (
            validate_bounded_defense_fortification_candidate(
                candidate, snapshot, revision, goals))
        if reason is not None:
            return None, reason
        action = candidate.action
        actor_id = action["actor_id"]
        operation = replace(
            candidate.operation,
            provenance=tuple(
                value for value in candidate.operation.provenance
                if value != "no-action-authority") + (
                    _DEFENSE_AUTHORITY_IDENTITY,
                    "freeciv-unit-fortification-contract/1.0",
                    "legacy-selected-byte-identical-pass-through",
                ))
        semantic = {
            "action_key": candidate.action_key,
            "authority_identity": _DEFENSE_AUTHORITY_IDENTITY,
            "goal_ids": list(operation.goal_ids),
            "operation_spec_digest": operation.spec_digest,
            "resource_keys": list(candidate.resource_keys),
            "opportunity_atom_id": opportunity.atom_id,
            "snapshot_id": snapshot.snapshot_id,
        }
        promoted = replace(
            candidate,
            operation=operation,
            authority_eligible=True,
            blockers=(),
            provenance=tuple(candidate.provenance) + (
                _DEFENSE_AUTHORITY_IDENTITY,
                "atom:{}".format(opportunity.atom_id),
                "freeciv-unit-fortification-contract/1.0",
                "legacy-selected-byte-identical-pass-through",
            ),
            candidate_hash=structural_hash(semantic),
        )
        return promoted, None

    def evaluate(self, snapshot, revision, shadow_evaluation,
                 legacy_candidate, authority_enabled=False,
                 city_defense_enabled=False):
        checks = []
        if not authority_enabled or not city_defense_enabled:
            return self._readout(
                "disabled", "fdas-city-defense-authority-disabled",
                snapshot, revision, checks=("domain-authority-gate",))
        checks.append("domain-authority-gate")
        if not isinstance(legacy_candidate, ImpactCandidate):
            return self._readout(
                "fallback", "legacy-selected-candidate-unavailable",
                snapshot, revision, checks=checks)
        if legacy_candidate.category != "city_defense":
            return self._readout(
                "fallback", "legacy-winner-is-not-city-defense",
                snapshot, revision, action_key=legacy_candidate.action_key,
                checks=checks + ["legacy-defense-category-gate"])
        checks.append("legacy-defense-category-gate")
        if (
                shadow_evaluation.snapshot_id != snapshot.snapshot_id
                or shadow_evaluation.revision_id != revision.revision_id):
            return self._readout(
                "fallback", "fdas-evaluation-not-current",
                snapshot, revision, checks=checks + [
                    "revision-current-evaluation"])
        checks.append("revision-current-evaluation")
        fortification_goal_ids = frozenset(
            value.goal.goal_id for value in shadow_evaluation.goals
            if value.deficit_predicate
            == "unit-fortification-opportunity")
        candidates = tuple(
            value for value in shadow_evaluation.candidates
            if (value.action_key == legacy_candidate.action_key
                and value.operation.goal_ids
                and set(value.operation.goal_ids)
                <= fortification_goal_ids))
        if len(candidates) != 1:
            return self._readout(
                "fallback",
                "legacy-winner-has-no-unique-fdas-fortification-route",
                snapshot, revision, action_key=legacy_candidate.action_key,
                checks=checks + [
                    "legacy-winner-fdas-fortification-route-binding"])
        source = candidates[0]
        selected_id = source.operation.operation_id
        checks.append("legacy-winner-fdas-fortification-route-binding")
        candidate, reason = self._promote(
            source, snapshot, revision, shadow_evaluation.goals)
        if candidate is None:
            return self._readout(
                "fallback", reason, snapshot, revision,
                operation_id=selected_id, action_key=source.action_key,
                checks=checks + [
                    "bounded-defense-fortification-contract"])
        checks.append("bounded-defense-fortification-contract")
        goal_ids = frozenset(candidate.operation.goal_ids)
        route_goals = tuple(
            value for value in shadow_evaluation.goals
            if value.goal.goal_id in goal_ids)
        authority_pressure = self.pressure_adapter.evaluate(
            revision, route_goals, (candidate,))
        authority_pressure_value = {
            "evaluation_hash": authority_pressure.evaluation_hash,
            "schedule_hash": authority_pressure.schedule.get(
                "structural_hash"),
            "selected_operation_id": authority_pressure.schedule.get(
                "selected_operation_id"),
            "status": authority_pressure.status,
        }
        if authority_pressure.schedule.get("selected_operation_id") != \
                candidate.operation.operation_id:
            return self._readout(
                "fallback", "fdas-authority-route-not-selected",
                snapshot, revision, operation_id=selected_id,
                action_key=candidate.action_key,
                checks=checks + ["authority-pressure-readout"],
                authority_pressure=authority_pressure_value)
        checks.append("authority-pressure-readout")
        scheduling = self.scheduling_bridge.schedule(
            authority_pressure, (candidate,), snapshot,
            packet_budgets=(
                PacketBudget(ResourceKind.ACTION, 1),
                PacketBudget(ResourceKind.CPU, 1),
            ))
        if candidate.operation.operation_id not in \
                scheduling.joint_selected_operation_ids:
            return self._readout(
                "fallback", "fdas-resource-or-packet-schedule-rejected",
                snapshot, revision, operation_id=selected_id,
                action_key=candidate.action_key,
                checks=checks + ["resource-and-packet-schedule"],
                scheduling=scheduling,
                authority_pressure=authority_pressure_value)
        checks.append("resource-and-packet-schedule")
        binding = FDASCommitBinding.create(
            revision, snapshot, candidate, route_goals)
        validation = self.commit_validator.validate(
            binding, revision, snapshot, candidate,
            authority_enabled=True)
        if not validation.plan_materialization_authorized:
            return self._readout(
                "fallback", validation.reason, snapshot, revision,
                operation_id=selected_id, action_key=candidate.action_key,
                checks=checks + ["exact-fdas-commit-validation"],
                scheduling=scheduling, validation=validation,
                authority_pressure=authority_pressure_value)
        checks.append("exact-fdas-commit-validation")
        return self._readout(
            "authorized", None, snapshot, revision,
            operation_id=selected_id, action_key=candidate.action_key,
            checks=checks, scheduling=scheduling, validation=validation,
            authority_pressure=authority_pressure_value)

    def candidate_from_readout(
            self, snapshot, revision, shadow_evaluation, readout):
        """Recover the exact promoted candidate behind an authorized readout.

        This is deliberately stricter than a lookup by action key.  Episode
        attribution may bind only to the same snapshot, revision, operation,
        action, and fresh commit result that crossed the authority boundary.
        """
        if not isinstance(readout, FdasAuthorityReadout):
            raise TypeError("defense authority readout has the wrong type")
        if (not readout.authorized
                or readout.authority_slice != self.AUTHORITY_IDENTITY):
            raise ValueError("defense episode requires authorized readout")
        if (readout.snapshot_id != snapshot.snapshot_id
                or readout.revision_id != revision.revision_id
                or shadow_evaluation.snapshot_id != snapshot.snapshot_id
                or shadow_evaluation.revision_id != revision.revision_id):
            raise ValueError("defense authority evidence is not current")
        sources = tuple(
            value for value in shadow_evaluation.candidates
            if (value.operation.operation_id == readout.operation_id
                and value.action_key == readout.action_key))
        if len(sources) != 1:
            raise ValueError("authorized defense route is not unique")
        candidate, reason = self._promote(
            sources[0], snapshot, revision, shadow_evaluation.goals)
        if candidate is None:
            raise ValueError(
                "authorized defense route no longer satisfies contract: {}"
                .format(reason))
        goal_ids = frozenset(candidate.operation.goal_ids)
        route_goals = tuple(
            value for value in shadow_evaluation.goals
            if value.goal.goal_id in goal_ids)
        binding = FDASCommitBinding.create(
            revision, snapshot, candidate, route_goals)
        validation = self.commit_validator.validate(
            binding, revision, snapshot, candidate,
            authority_enabled=True)
        expected_hash = (readout.commit_validation or {}).get("result_hash")
        if (not validation.plan_materialization_authorized
                or validation.result_hash != expected_hash):
            raise ValueError("authorized defense commit evidence changed")
        return candidate
