"""Uncertainty- and grounding-safe FDAS candidate preference diagnostics.

This component deliberately stops before action authority.  It asks whether a
calibrated alternative is separated from the active control candidate and is
no worse on exact route and unit facts that matter to reinforcement.  Missing
or overlapping evidence produces an explicit abstention.
"""

from dataclasses import dataclass
import math

from ..events.schema import structural_hash
from .fdas import ShadowOperationCandidate
from .fdas_authority import (
    validate_bounded_defense_reinforcement_candidate,
)
from .fdas_calibrated_candidate_union import (
    FdasCalibratedCandidateUnion,
)
from .impact_types import ImpactCandidate


DECISION_SAFE_CANDIDATE_READOUT_IDENTITY = (
    "fdas-decision-safe-candidate-readout/1.0")


def _finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("{} must be finite".format(name))
    return value


@dataclass(frozen=True)
class FdasDecisionSafeCandidateReadoutConfig:
    minimum_interval_separation: float = 0.0
    require_grounded_noninferiority: bool = True
    require_same_target_ref: bool = True
    allowed_action_type: str = "unit_move"

    def __post_init__(self):
        separation = _finite(
            self.minimum_interval_separation,
            "minimum interval separation")
        if separation < 0.0 or separation > 1.0:
            raise ValueError(
                "minimum interval separation must be in [0,1]")
        object.__setattr__(self, "minimum_interval_separation", separation)
        if self.require_grounded_noninferiority is not True:
            raise ValueError(
                "decision-safe readout requires grounded noninferiority")
        if self.require_same_target_ref is not True:
            raise ValueError(
                "decision-safe readout requires the same target")
        if self.allowed_action_type != "unit_move":
            raise ValueError(
                "decision-safe readout supports only reinforcement moves")

    @classmethod
    def from_dict(cls, value):
        expected = {
            "allowed_action_type",
            "minimum_interval_separation",
            "require_grounded_noninferiority",
            "require_same_target_ref",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError(
                "decision-safe candidate readout config is incomplete")
        return cls(**value)

    def to_dict(self):
        return {
            "allowed_action_type": self.allowed_action_type,
            "minimum_interval_separation": (
                self.minimum_interval_separation),
            "require_grounded_noninferiority": True,
            "require_same_target_ref": True,
        }


@dataclass(frozen=True)
class FdasGroundedCandidateValue:
    operation_id: str
    action_key: str
    actor_id: int
    target_city_id: int
    unit_type: str
    estimated_turns: int
    total_movement_cost: int
    first_step_movement_cost: int
    hp: int
    moves_left: int
    veteran: int
    homecity_relation: str
    estimate: float
    interval_lower: float
    interval_upper: float
    effective_lineages: int
    source_atom_id: str
    eligibility_reason: str
    noninferiority_checks: tuple

    def __post_init__(self):
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.action_key, "action key"),
                (self.unit_type, "unit type"),
                (self.source_atom_id, "source atom ID"),
                (self.eligibility_reason, "eligibility reason")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "grounded candidate {} is required".format(name))
        for value, name, minimum in (
                (self.actor_id, "actor ID", 0),
                (self.target_city_id, "target city ID", 0),
                (self.estimated_turns, "estimated turns", 1),
                (self.total_movement_cost, "total movement cost", 0),
                (self.first_step_movement_cost,
                 "first-step movement cost", 0),
                (self.hp, "hit points", 0),
                (self.moves_left, "moves left", 0),
                (self.veteran, "veteran level", 0),
                (self.effective_lineages, "effective lineages", 1)):
            if (isinstance(value, bool) or not isinstance(value, int)
                    or value < minimum):
                raise ValueError(
                    "grounded candidate {} is invalid".format(name))
        if self.homecity_relation not in ("none", "other", "target"):
            raise ValueError(
                "grounded candidate homecity relation is invalid")
        estimate, lower, upper = tuple(_finite(value, name) for value, name in (
            (self.estimate, "estimate"),
            (self.interval_lower, "interval lower"),
            (self.interval_upper, "interval upper"),
        ))
        if (any(not 0.0 <= value <= 1.0
                for value in (estimate, lower, upper))
                or not lower <= estimate <= upper):
            raise ValueError(
                "grounded candidate calibrated interval is invalid")
        object.__setattr__(self, "estimate", estimate)
        object.__setattr__(self, "interval_lower", lower)
        object.__setattr__(self, "interval_upper", upper)
        checks = tuple(sorted(set(str(value)
                                  for value in self.noninferiority_checks)))
        if any(not value for value in checks):
            raise ValueError(
                "grounded candidate noninferiority check is invalid")
        object.__setattr__(self, "noninferiority_checks", checks)

    def to_dict(self):
        return {
            "action_key": self.action_key,
            "actor_id": self.actor_id,
            "effective_lineages": self.effective_lineages,
            "eligibility_reason": self.eligibility_reason,
            "estimate": self.estimate,
            "estimated_turns": self.estimated_turns,
            "first_step_movement_cost": self.first_step_movement_cost,
            "homecity_relation": self.homecity_relation,
            "hp": self.hp,
            "interval_lower": self.interval_lower,
            "interval_upper": self.interval_upper,
            "moves_left": self.moves_left,
            "noninferiority_checks": list(self.noninferiority_checks),
            "operation_id": self.operation_id,
            "source_atom_id": self.source_atom_id,
            "target_city_id": self.target_city_id,
            "total_movement_cost": self.total_movement_cost,
            "unit_type": self.unit_type,
            "veteran": self.veteran,
        }


@dataclass(frozen=True)
class FdasDecisionSafeCandidateReadout:
    status: str
    reason: str
    snapshot_id: str
    revision_id: str
    calibrated_union_result_hash: str
    config: dict
    baseline_operation_id: object
    proposed_operation_id: object
    counterfactual_change: bool
    candidates: tuple
    rejected: tuple
    result_hash: str

    def __post_init__(self):
        if self.status not in ("eligible-shadow", "abstained"):
            raise ValueError(
                "decision-safe candidate readout status is invalid")
        for value, name in (
                (self.reason, "reason"),
                (self.snapshot_id, "snapshot ID"),
                (self.revision_id, "revision ID"),
                (self.calibrated_union_result_hash,
                 "calibrated union result hash"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "decision-safe candidate {} is required".format(name))
        canonical = FdasDecisionSafeCandidateReadoutConfig.from_dict(
            dict(self.config)).to_dict()
        if canonical != self.config:
            raise ValueError(
                "decision-safe candidate config is not canonical")
        object.__setattr__(self, "config", canonical)
        candidates = tuple(self.candidates)
        rejected = tuple(sorted(set(str(value) for value in self.rejected)))
        if any(not isinstance(value, FdasGroundedCandidateValue)
               for value in candidates):
            raise TypeError(
                "decision-safe candidate readout requires typed candidates")
        if any(not value for value in rejected):
            raise ValueError(
                "decision-safe candidate rejection is invalid")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "rejected", rejected)
        eligible = self.status == "eligible-shadow"
        if (eligible != self.counterfactual_change
                or eligible != (self.proposed_operation_id is not None)
                or (eligible and self.baseline_operation_id is None)
                or (eligible and self.proposed_operation_id
                    == self.baseline_operation_id)):
            raise ValueError(
                "decision-safe candidate counterfactual semantics differ")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError(
                "decision-safe candidate result hash differs")

    def _semantic(self):
        return {
            "action_selection_changed": False,
            "baseline_operation_id": self.baseline_operation_id,
            "calibrated_union_result_hash": (
                self.calibrated_union_result_hash),
            "candidates": [value.to_dict() for value in self.candidates],
            "config": dict(self.config),
            "counterfactual_change": self.counterfactual_change,
            "identity": DECISION_SAFE_CANDIDATE_READOUT_IDENTITY,
            "policy_authority": False,
            "proposed_operation_id": self.proposed_operation_id,
            "readout_authority": False,
            "reason": self.reason,
            "rejected": list(self.rejected),
            "revision_id": self.revision_id,
            "snapshot_id": self.snapshot_id,
            "status": self.status,
            "truth_mutated": False,
        }

    def to_dict(self):
        value = self._semantic()
        value["result_hash"] = self.result_hash
        return value


class FdasDecisionSafeCandidateReadoutEvaluator:
    """Prefer only calibrated and mechanically non-inferior alternatives."""

    _HOMECITY_RANK = {"none": 0, "other": 1, "target": 2}

    def __init__(self, config=None):
        self.config = config or FdasDecisionSafeCandidateReadoutConfig()
        if not isinstance(
                self.config, FdasDecisionSafeCandidateReadoutConfig):
            raise TypeError(
                "decision-safe evaluator requires typed config")

    def _readout(self, status, reason, snapshot, revision, calibrated_union,
                 baseline_operation_id=None, proposed_operation_id=None,
                 candidates=(), rejected=()):
        semantic = {
            "action_selection_changed": False,
            "baseline_operation_id": baseline_operation_id,
            "calibrated_union_result_hash": calibrated_union.result_hash,
            "candidates": [value.to_dict() for value in candidates],
            "config": self.config.to_dict(),
            "counterfactual_change": status == "eligible-shadow",
            "identity": DECISION_SAFE_CANDIDATE_READOUT_IDENTITY,
            "policy_authority": False,
            "proposed_operation_id": proposed_operation_id,
            "readout_authority": False,
            "reason": reason,
            "rejected": sorted(set(str(value) for value in rejected)),
            "revision_id": revision.revision_id,
            "snapshot_id": snapshot.snapshot_id,
            "status": status,
            "truth_mutated": False,
        }
        return FdasDecisionSafeCandidateReadout(
            status, reason, snapshot.snapshot_id, revision.revision_id,
            calibrated_union.result_hash, self.config.to_dict(),
            baseline_operation_id, proposed_operation_id,
            status == "eligible-shadow", tuple(candidates),
            tuple(semantic["rejected"]), structural_hash(semantic))

    @staticmethod
    def _target_city_id(candidate):
        target = candidate.operation.target_ref
        if not isinstance(target, str) or not target.startswith("city:"):
            return None
        try:
            return int(target.split(":", 1)[1])
        except ValueError:
            return None

    def _ground_exact(self, candidate, prediction, snapshot, revision, goals,
                      *, eligibility_reason, checks=()):
        if (not isinstance(candidate, ShadowOperationCandidate)
                or candidate.action.get("action_type")
                != self.config.allowed_action_type
                or prediction is None
                or not prediction.eligible_for_calibrated_recall):
            return None, "unestimated-or-out-of-slice"
        actor_id = candidate.action.get("actor_id")
        target_city_id = self._target_city_id(candidate)
        actor = snapshot.unit(actor_id) if isinstance(actor_id, int) else None
        city = (snapshot.city(target_city_id)
                if target_city_id is not None else None)
        route = (snapshot.movement_route(actor_id, city.tile)
                 if actor is not None and city is not None
                 and city.tile is not None else None)
        pressure_route, source_record, reason = (
            validate_bounded_defense_reinforcement_candidate(
                candidate, snapshot, revision, goals))
        del pressure_route
        if reason is not None:
            return None, "bounded-validator-" + reason
        if source_record is None:
            return None, "deficit-support-record-unavailable"
        if actor is None:
            return None, "actor-state-unavailable"
        if city is None:
            return None, "target-city-state-unavailable"
        if route is None:
            return None, "native-route-unavailable"
        if not route.reachable:
            return None, "native-route-unreachable"
        if route.turn != snapshot.turn:
            return None, "native-route-turn-mismatch"
        if route.source_seq > snapshot.identity.source_seq:
            return None, "native-route-is-future"
        if route.estimated_turns < 1:
            return None, "native-route-eta-invalid"
        missing_fields = tuple(
            name for name, value in (
                ("homecity", actor.homecity),
                ("hp", actor.hp),
                ("moves-left", actor.moves_left),
                ("veteran", actor.veteran),
            ) if value is None)
        if missing_fields:
            return None, "actor-fields-unavailable:" + ",".join(
                missing_fields)
        homecity_relation = (
            "target" if actor.homecity == target_city_id else
            "none" if actor.homecity == 0 else "other")
        return FdasGroundedCandidateValue(
            candidate.operation.operation_id,
            candidate.action_key,
            actor.unit_id,
            target_city_id,
            actor.unit_type,
            route.estimated_turns,
            route.total_movement_cost,
            route.first_step_movement_cost,
            actor.hp,
            actor.moves_left,
            actor.veteran,
            homecity_relation,
            prediction.estimate,
            prediction.interval_lower,
            prediction.interval_upper,
            prediction.effective_lineages,
            source_record.atom_id,
            eligibility_reason,
            tuple(checks),
        ), None

    def _ground(self, candidate, prediction, snapshot, revision, goals,
                *, eligibility_reason, checks=()):
        value, reason = self._ground_exact(
            candidate, prediction, snapshot, revision, goals,
            eligibility_reason=eligibility_reason, checks=checks)
        if value is not None or reason == "unestimated-or-out-of-slice":
            return value, reason
        # Preserve PR58's frozen legacy-control reason surface. The separate
        # scalar-baseline evaluator overrides this wrapper for exact RCA.
        return None, "grounded-transition-input-unavailable"

    def _noninferiority(self, control, alternative):
        checks = {
            "estimated-turns": (
                alternative.estimated_turns <= control.estimated_turns),
            "first-step-movement-cost": (
                alternative.first_step_movement_cost
                <= control.first_step_movement_cost),
            "homecity-relation": (
                self._HOMECITY_RANK[alternative.homecity_relation]
                >= self._HOMECITY_RANK[control.homecity_relation]),
            "hit-points": alternative.hp >= control.hp,
            "moves-left": alternative.moves_left >= control.moves_left,
            "total-movement-cost": (
                alternative.total_movement_cost
                <= control.total_movement_cost),
            "unit-type": alternative.unit_type == control.unit_type,
            "veteran-level": alternative.veteran >= control.veteran,
        }
        failed = tuple(sorted(name for name, passed in checks.items()
                              if not passed))
        passed = tuple(sorted(name for name, value in checks.items()
                              if value))
        return not failed, passed, failed

    def evaluate(self, snapshot, revision, shadow_evaluation,
                 legacy_candidate, candidates, calibrated_union):
        if not isinstance(calibrated_union, FdasCalibratedCandidateUnion):
            raise TypeError(
                "decision-safe readout requires calibrated candidate union")
        if (calibrated_union.snapshot_id != snapshot.snapshot_id
                or calibrated_union.revision_id != revision.revision_id
                or shadow_evaluation.snapshot_id != snapshot.snapshot_id
                or shadow_evaluation.revision_id != revision.revision_id):
            return self._readout(
                "abstained", "input-is-not-revision-current",
                snapshot, revision, calibrated_union)
        if (not isinstance(legacy_candidate, ImpactCandidate)
                or legacy_candidate.action.get("action_type")
                != self.config.allowed_action_type):
            return self._readout(
                "abstained", "active-winner-is-not-reinforcement-move",
                snapshot, revision, calibrated_union)
        candidates = tuple(candidates)
        candidate_by_id = {
            value.operation.operation_id: value for value in candidates}
        predictions = {
            value.operation_id: value for value in calibrated_union.readouts}
        baseline_matches = tuple(
            value for value in candidates
            if value.action_key == legacy_candidate.action_key)
        if len(baseline_matches) != 1:
            return self._readout(
                "abstained", "active-winner-has-no-unique-fdas-route",
                snapshot, revision, calibrated_union)
        baseline_candidate = baseline_matches[0]
        baseline_id = baseline_candidate.operation.operation_id
        control, reason = self._ground(
            baseline_candidate, predictions.get(baseline_id),
            snapshot, revision, shadow_evaluation.goals,
            eligibility_reason="active-control")
        if control is None:
            return self._readout(
                "abstained", "control-{}".format(reason),
                snapshot, revision, calibrated_union,
                baseline_operation_id=baseline_id)
        grounded = [control]
        rejected = []
        eligible = []
        for operation_id, candidate in sorted(candidate_by_id.items()):
            if operation_id == baseline_id:
                continue
            if (candidate.action_key == baseline_candidate.action_key
                    or candidate.operation.operation_type
                    != baseline_candidate.operation.operation_type
                    or (self.config.require_same_target_ref
                        and candidate.operation.target_ref
                        != baseline_candidate.operation.target_ref)
                    or candidate.resource_keys == baseline_candidate.resource_keys
                    or set(candidate.resource_keys).intersection(
                        baseline_candidate.resource_keys)):
                rejected.append(operation_id + ":pair-scope-mismatch")
                continue
            alternative, reason = self._ground(
                candidate, predictions.get(operation_id),
                snapshot, revision, shadow_evaluation.goals,
                eligibility_reason="candidate")
            if alternative is None:
                rejected.append(operation_id + ":" + reason)
                continue
            separated = (
                alternative.interval_lower
                >= control.interval_upper
                + self.config.minimum_interval_separation
                and alternative.interval_lower > control.interval_upper)
            if not separated:
                grounded.append(alternative)
                rejected.append(operation_id + ":calibrated-interval-overlap")
                continue
            noninferior, passed, failed = self._noninferiority(
                control, alternative)
            alternative = FdasGroundedCandidateValue(
                **{
                    **alternative.__dict__,
                    "eligibility_reason": (
                        "eligible" if noninferior
                        else "grounded-noninferiority-failed"),
                    "noninferiority_checks": passed,
                })
            grounded.append(alternative)
            if not noninferior:
                rejected.append(
                    operation_id + ":grounded-noninferiority-failed:"
                    + ",".join(failed))
                continue
            eligible.append(alternative)
        if not eligible:
            return self._readout(
                "abstained", "no-separated-grounded-noninferior-alternative",
                snapshot, revision, calibrated_union,
                baseline_operation_id=baseline_id,
                candidates=tuple(grounded), rejected=tuple(rejected))
        selected = sorted(
            eligible,
            key=lambda value: (
                -value.interval_lower,
                -value.estimate,
                value.estimated_turns,
                value.total_movement_cost,
                -value.hp,
                -value.veteran,
                value.operation_id))[0]
        return self._readout(
            "eligible-shadow", "calibrated-and-grounded-dominance",
            snapshot, revision, calibrated_union,
            baseline_operation_id=baseline_id,
            proposed_operation_id=selected.operation_id,
            candidates=tuple(grounded), rejected=tuple(rejected))
