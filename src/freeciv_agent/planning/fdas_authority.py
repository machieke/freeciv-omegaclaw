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
