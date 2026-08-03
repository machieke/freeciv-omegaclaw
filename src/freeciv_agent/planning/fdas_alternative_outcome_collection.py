"""Fail-closed shadow assignment for safe alternative-action outcomes.

This component does not execute its assignment.  It identifies narrow defence
decisions at which a later diagnostic may randomize between the current scalar
winner and one persistence-only alternative, records the exact policy
probability, and proves that both arms cross the same legal, resource, packet,
and commit-validation boundary.
"""

from dataclasses import dataclass, replace
import math

from ..events.schema import structural_hash
from ..pressure.fdas_adapter import DependentAtomPressureAdapter
from ..pressure.fdas_resources import DependentAtomSchedulingBridge
from ..pressure.packets import PacketBudget, ResourceKind
from ..pressure.scheduler import OperationScore
from .fdas import ShadowOperationCandidate
from .fdas_authority import (
    validate_bounded_defense_fortification_candidate,
    validate_bounded_defense_reinforcement_candidate,
)
from .fdas_commit import FDASCommitBinding, FDASCommitValidator
from .fdas_path_persistence_candidate_union import (
    FdasPathPersistenceCandidateUnion,
)
from .impact_types import ImpactCandidate


ALTERNATIVE_OUTCOME_COLLECTION_IDENTITY = (
    "fdas-safe-alternative-outcome-collection/1.3")
ALTERNATIVE_OUTCOME_POLICY_VERSION = (
    "fdas-defense-persistence-randomized-shadow/1.3")


def _finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("{} must be finite".format(name))
    return value


@dataclass(frozen=True)
class FdasAlternativeOutcomeCollectionConfig:
    experiment_id: str
    randomization_seed: int
    treatment_probability: float = 0.5
    maximum_priority_regret: float = 0.01
    maximum_risk_penalty_delta: float = 0.0
    mode: str = "shadow"
    allowed_action_type: str = "unit_fortify"
    claim_eligible: bool = False
    truth_mutated: bool = False
    source_sink_flow_enabled: bool = False
    outcome_update_scope: str = "control-model-only"
    require_same_target_ref: bool = True
    allowed_active_categories: tuple = (
        "city_defense", "city_garrison_move")

    def __post_init__(self):
        if not isinstance(self.experiment_id, str) or not self.experiment_id:
            raise ValueError("alternative collection experiment ID is required")
        if (isinstance(self.randomization_seed, bool)
                or not isinstance(self.randomization_seed, int)
                or self.randomization_seed < 0):
            raise ValueError("alternative collection seed is invalid")
        probability = _finite(
            self.treatment_probability, "treatment probability")
        if not 0.0 < probability < 1.0:
            raise ValueError("treatment probability must be in (0,1)")
        object.__setattr__(self, "treatment_probability", probability)
        for name in (
                "maximum_priority_regret",
                "maximum_risk_penalty_delta"):
            value = _finite(getattr(self, name), name.replace("_", " "))
            if value < 0.0:
                raise ValueError("{} cannot be negative".format(
                    name.replace("_", " ")))
            object.__setattr__(self, name, value)
        if self.mode != "shadow":
            raise ValueError(
                "alternative collection v1 supports shadow assignment only")
        if self.allowed_action_type not in ("unit_fortify", "unit_move"):
            raise ValueError(
                "alternative collection action slice is unsupported")
        for name in (
                "claim_eligible", "truth_mutated",
                "source_sink_flow_enabled"):
            if getattr(self, name) is not False:
                raise ValueError(
                    "alternative collection cannot enable {}".format(name))
        if self.outcome_update_scope != "control-model-only":
            raise ValueError(
                "alternative collection cannot update truth")
        if not isinstance(self.require_same_target_ref, bool):
            raise TypeError(
                "alternative collection target-match gate must be boolean")
        categories = tuple(sorted(set(self.allowed_active_categories)))
        if (not categories
                or set(categories) - {"city_defense", "city_garrison_move"}):
            raise ValueError(
                "alternative collection active categories are unsupported")
        object.__setattr__(self, "allowed_active_categories", categories)

    @classmethod
    def from_dict(cls, value):
        expected = {
            "allowed_action_type",
            "allowed_active_categories",
            "claim_eligible",
            "experiment_id",
            "maximum_priority_regret",
            "maximum_risk_penalty_delta",
            "mode",
            "outcome_update_scope",
            "randomization_seed",
            "require_same_target_ref",
            "source_sink_flow_enabled",
            "treatment_probability",
            "truth_mutated",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError(
                "alternative collection declaration is incomplete")
        return cls(**value)

    def to_dict(self):
        return {
            "allowed_active_categories": list(self.allowed_active_categories),
            "allowed_action_type": self.allowed_action_type,
            "claim_eligible": False,
            "experiment_id": self.experiment_id,
            "maximum_priority_regret": self.maximum_priority_regret,
            "maximum_risk_penalty_delta": (
                self.maximum_risk_penalty_delta),
            "mode": self.mode,
            "outcome_update_scope": self.outcome_update_scope,
            "randomization_seed": self.randomization_seed,
            "require_same_target_ref": self.require_same_target_ref,
            "source_sink_flow_enabled": False,
            "treatment_probability": self.treatment_probability,
            "truth_mutated": False,
        }


@dataclass(frozen=True)
class FdasAlternativeArmReadout:
    arm: str
    operation_id: str
    action_key: str
    actor_id: int
    target_ref: str
    resource_keys: tuple
    priority: float
    risk_penalty: float
    source_atom_id: str
    pressure_evaluation_hash: str
    resource_packet_artifact_hash: str
    commit_validation_hash: str

    def __post_init__(self):
        if self.arm not in ("control", "treatment"):
            raise ValueError("alternative arm is invalid")
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.action_key, "action key"),
                (self.target_ref, "target reference"),
                (self.source_atom_id, "source atom ID"),
                (self.pressure_evaluation_hash, "pressure evaluation hash"),
                (self.resource_packet_artifact_hash,
                 "resource/packet artifact hash"),
                (self.commit_validation_hash, "commit validation hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("alternative arm {} is required".format(name))
        if (isinstance(self.actor_id, bool)
                or not isinstance(self.actor_id, int)):
            raise ValueError("alternative arm actor ID is invalid")
        object.__setattr__(self, "resource_keys", tuple(self.resource_keys))
        object.__setattr__(self, "priority", _finite(
            self.priority, "alternative arm priority"))
        risk = _finite(self.risk_penalty, "alternative arm risk penalty")
        if risk < 0.0:
            raise ValueError("alternative arm risk penalty is negative")
        object.__setattr__(self, "risk_penalty", risk)

    def to_dict(self):
        return {
            "action_key": self.action_key,
            "actor_id": self.actor_id,
            "arm": self.arm,
            "commit_validation_hash": self.commit_validation_hash,
            "operation_id": self.operation_id,
            "source_atom_id": self.source_atom_id,
            "pressure_evaluation_hash": self.pressure_evaluation_hash,
            "priority": self.priority,
            "resource_keys": list(self.resource_keys),
            "resource_packet_artifact_hash": (
                self.resource_packet_artifact_hash),
            "risk_penalty": self.risk_penalty,
            "target_ref": self.target_ref,
        }


@dataclass(frozen=True)
class FdasAlternativeOutcomeCollectionReadout:
    status: str
    reason: object
    snapshot_id: str
    revision_id: str
    persistence_union_result_hash: str
    experiment_id: str
    policy_version: str
    config: dict
    checks: tuple
    arms: tuple
    assigned_arm: object
    assigned_operation_id: object
    assigned_action_key: object
    selection_policy_kind: object
    selection_propensity: object
    assignment_draw: object
    assignment_material_hash: object
    priority_regret: object
    risk_penalty_delta: object
    action_selection_changed: bool
    policy_authority: bool
    truth_mutated: bool
    claim_eligible: bool
    outcome_update_scope: str
    result_hash: str

    def __post_init__(self):
        if self.status not in ("disabled", "ineligible", "eligible-shadow"):
            raise ValueError("alternative collection status is invalid")
        for value, name in (
                (self.snapshot_id, "snapshot ID"),
                (self.revision_id, "revision ID"),
                (self.persistence_union_result_hash,
                 "persistence union result hash"),
                (self.experiment_id, "experiment ID"),
                (self.policy_version, "policy version"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("alternative collection {} is required".format(
                    name))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "arms", tuple(self.arms))
        if not isinstance(self.config, dict) or not self.config:
            raise TypeError("alternative collection config is invalid")
        canonical_config = (
            FdasAlternativeOutcomeCollectionConfig.from_dict(
                dict(self.config)).to_dict())
        if canonical_config != self.config:
            raise ValueError("alternative collection config is not canonical")
        object.__setattr__(self, "config", canonical_config)
        if any(not isinstance(value, FdasAlternativeArmReadout)
               for value in self.arms):
            raise TypeError("alternative collection arms are invalid")
        if any((
                self.action_selection_changed,
                self.policy_authority,
                self.truth_mutated,
                self.claim_eligible)):
            raise ValueError(
                "shadow alternative collection gained undeclared authority")
        if self.outcome_update_scope != "control-model-only":
            raise ValueError("alternative collection update scope differs")
        if self.status == "eligible-shadow":
            if (self.reason is not None
                    or tuple(value.arm for value in self.arms)
                    != ("control", "treatment")
                    or self.assigned_arm not in ("control", "treatment")
                    or self.selection_policy_kind != "stochastic"
                    or self.selection_propensity is None
                    or self.assignment_draw is None
                    or self.assignment_material_hash is None
                    or self.priority_regret is None
                    or self.risk_penalty_delta is None):
                raise ValueError(
                    "eligible alternative collection readout is incomplete")
            selected = dict((value.arm, value) for value in self.arms)[
                self.assigned_arm]
            if (self.assigned_operation_id != selected.operation_id
                    or self.assigned_action_key != selected.action_key):
                raise ValueError(
                    "alternative collection assignment binding differs")
            propensity = float(self.selection_propensity)
            draw = float(self.assignment_draw)
            if (not 0.0 < propensity < 1.0
                    or not 0.0 <= draw < 1.0):
                raise ValueError(
                    "alternative collection probability or draw is invalid")
        else:
            if not isinstance(self.reason, str) or not self.reason:
                raise ValueError(
                    "non-eligible alternative collection needs a reason")
            if any(value is not None for value in (
                    self.assigned_arm, self.assigned_operation_id,
                    self.assigned_action_key, self.selection_policy_kind,
                    self.selection_propensity, self.assignment_draw,
                    self.assignment_material_hash)):
                raise ValueError(
                    "ineligible alternative collection invented assignment")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("alternative collection result hash differs")

    def _semantic(self):
        return {
            "action_selection_changed": False,
            "arms": [value.to_dict() for value in self.arms],
            "assigned_action_key": self.assigned_action_key,
            "assigned_arm": self.assigned_arm,
            "assigned_operation_id": self.assigned_operation_id,
            "assignment_draw": self.assignment_draw,
            "assignment_executed": False,
            "assignment_material_hash": self.assignment_material_hash,
            "checks": list(self.checks),
            "claim_eligible": False,
            "config": dict(self.config),
            "experiment_id": self.experiment_id,
            "identity": ALTERNATIVE_OUTCOME_COLLECTION_IDENTITY,
            "outcome_update_scope": self.outcome_update_scope,
            "persistence_union_result_hash": (
                self.persistence_union_result_hash),
            "policy_authority": False,
            "policy_version": self.policy_version,
            "priority_regret": self.priority_regret,
            "reason": self.reason,
            "revision_id": self.revision_id,
            "risk_penalty_delta": self.risk_penalty_delta,
            "selection_policy_kind": self.selection_policy_kind,
            "selection_propensity": self.selection_propensity,
            "snapshot_id": self.snapshot_id,
            "source_sink_flow_enabled": False,
            "status": self.status,
            "truth_mutated": False,
        }

    def to_dict(self):
        value = self._semantic()
        value["result_hash"] = self.result_hash
        return value


class FdasAlternativeOutcomeCollectionEvaluator:
    """Find safe randomized-outcome opportunities without executing them."""

    def __init__(self, config, pressure_adapter=None, scheduling_bridge=None,
                 commit_validator=None):
        if not isinstance(config, FdasAlternativeOutcomeCollectionConfig):
            raise TypeError(
                "alternative collection evaluator requires typed config")
        self.config = config
        self.pressure_adapter = (
            pressure_adapter or DependentAtomPressureAdapter())
        self.scheduling_bridge = (
            scheduling_bridge or DependentAtomSchedulingBridge())
        self.commit_validator = commit_validator or FDASCommitValidator()

    def _readout(self, status, reason, snapshot, revision, persistence_union,
                 checks=(), arms=(), assigned_arm=None,
                 selection_propensity=None, assignment_draw=None,
                 assignment_material_hash=None, priority_regret=None,
                 risk_penalty_delta=None):
        arm_by_name = dict((value.arm, value) for value in arms)
        assigned = arm_by_name.get(assigned_arm)
        values = {
            "status": status,
            "reason": reason,
            "snapshot_id": snapshot.snapshot_id,
            "revision_id": revision.revision_id,
            "persistence_union_result_hash": persistence_union.result_hash,
            "experiment_id": self.config.experiment_id,
            "policy_version": ALTERNATIVE_OUTCOME_POLICY_VERSION,
            "config": self.config.to_dict(),
            "checks": tuple(checks),
            "arms": tuple(arms),
            "assigned_arm": assigned_arm,
            "assigned_operation_id": (
                None if assigned is None else assigned.operation_id),
            "assigned_action_key": (
                None if assigned is None else assigned.action_key),
            "selection_policy_kind": (
                "stochastic" if assigned is not None else None),
            "selection_propensity": selection_propensity,
            "assignment_draw": assignment_draw,
            "assignment_material_hash": assignment_material_hash,
            "priority_regret": priority_regret,
            "risk_penalty_delta": risk_penalty_delta,
            "action_selection_changed": False,
            "policy_authority": False,
            "truth_mutated": False,
            "claim_eligible": False,
            "outcome_update_scope": "control-model-only",
        }
        semantic = {
            "action_selection_changed": False,
            "arms": [value.to_dict() for value in values["arms"]],
            "assigned_action_key": values["assigned_action_key"],
            "assigned_arm": assigned_arm,
            "assigned_operation_id": values["assigned_operation_id"],
            "assignment_draw": assignment_draw,
            "assignment_executed": False,
            "assignment_material_hash": assignment_material_hash,
            "checks": list(values["checks"]),
            "claim_eligible": False,
            "config": self.config.to_dict(),
            "experiment_id": self.config.experiment_id,
            "identity": ALTERNATIVE_OUTCOME_COLLECTION_IDENTITY,
            "outcome_update_scope": "control-model-only",
            "persistence_union_result_hash": persistence_union.result_hash,
            "policy_authority": False,
            "policy_version": ALTERNATIVE_OUTCOME_POLICY_VERSION,
            "priority_regret": priority_regret,
            "reason": reason,
            "revision_id": revision.revision_id,
            "risk_penalty_delta": risk_penalty_delta,
            "selection_policy_kind": values["selection_policy_kind"],
            "selection_propensity": selection_propensity,
            "snapshot_id": snapshot.snapshot_id,
            "source_sink_flow_enabled": False,
            "status": status,
            "truth_mutated": False,
        }
        return FdasAlternativeOutcomeCollectionReadout(
            result_hash=structural_hash(semantic), **values)

    @staticmethod
    def _promote(candidate, source_record):
        contract = {
            "unit_fortify": "freeciv-unit-fortification-contract/1.0",
            "unit_move": "freeciv-unit-reinforcement-contract/1.0",
        }[candidate.action["action_type"]]
        operation = replace(
            candidate.operation,
            provenance=tuple(
                value for value in candidate.operation.provenance
                if value != "no-action-authority") + (
                    ALTERNATIVE_OUTCOME_COLLECTION_IDENTITY,
                    contract,
                    "claim-ineligible-stochastic-shadow-preflight",
                ))
        semantic = {
            "action_key": candidate.action_key,
            "authority_identity": ALTERNATIVE_OUTCOME_COLLECTION_IDENTITY,
            "goal_ids": list(operation.goal_ids),
            "operation_spec_digest": operation.spec_digest,
            "source_atom_id": source_record.atom_id,
            "resource_keys": list(candidate.resource_keys),
        }
        return replace(
            candidate,
            operation=operation,
            authority_eligible=True,
            blockers=(),
            provenance=tuple(candidate.provenance) + (
                ALTERNATIVE_OUTCOME_COLLECTION_IDENTITY,
                "atom:" + source_record.atom_id,
                contract,
                "claim-ineligible-stochastic-shadow-preflight",
            ),
            candidate_hash=structural_hash(semantic))

    def _preflight(self, arm, candidate, score, snapshot, revision, goals):
        validator = {
            "unit_fortify": validate_bounded_defense_fortification_candidate,
            "unit_move": validate_bounded_defense_reinforcement_candidate,
        }.get(candidate.action.get("action_type"))
        if validator is None:
            return None, "{}-unsupported-action-slice".format(arm)
        route, source_record, reason = validator(
            candidate, snapshot, revision, goals)
        if reason is not None:
            return None, "{}-{}".format(arm, reason)
        promoted = self._promote(candidate, source_record)
        evaluation = self.pressure_adapter.evaluate(
            revision, (route,), (promoted,))
        if (evaluation.status != "complete"
                or evaluation.schedule.get("selected_operation_id")
                != promoted.operation.operation_id):
            return None, "{}-pressure-preflight-rejected".format(arm)
        scheduling = self.scheduling_bridge.schedule(
            evaluation, (promoted,), snapshot,
            packet_budgets=(
                PacketBudget(ResourceKind.ACTION, 1),
                PacketBudget(ResourceKind.CPU, 1),
            ))
        if promoted.operation.operation_id not in (
                scheduling.joint_selected_operation_ids):
            return None, "{}-resource-packet-preflight-rejected".format(arm)
        binding = FDASCommitBinding.create(
            revision, snapshot, promoted, (route,))
        validation = self.commit_validator.validate(
            binding, revision, snapshot, promoted, authority_enabled=True)
        if not validation.plan_materialization_authorized:
            return None, "{}-commit-preflight-rejected:{}".format(
                arm, validation.reason)
        return FdasAlternativeArmReadout(
            arm,
            promoted.operation.operation_id,
            promoted.action_key,
            promoted.action["actor_id"],
            promoted.operation.target_ref,
            promoted.resource_keys,
            float(score.priority),
            float(score.risk_penalty),
            source_record.atom_id,
            evaluation.evaluation_hash,
            scheduling.artifact_hash,
            validation.result_hash,
        ), None

    def evaluate(self, snapshot, revision, shadow_evaluation,
                 legacy_candidate, candidates, scores, persistence_union):
        if not isinstance(persistence_union, FdasPathPersistenceCandidateUnion):
            raise TypeError(
                "alternative collection requires path-persistence union")
        checks = []
        if (persistence_union.snapshot_id != snapshot.snapshot_id
                or persistence_union.revision_id != revision.revision_id
                or shadow_evaluation.snapshot_id != snapshot.snapshot_id
                or shadow_evaluation.revision_id != revision.revision_id):
            return self._readout(
                "ineligible", "alternative-input-is-not-revision-current",
                snapshot, revision, persistence_union,
                checks=("revision-current-inputs",))
        checks.append("revision-current-inputs")
        if (not isinstance(legacy_candidate, ImpactCandidate)
                or legacy_candidate.category
                not in self.config.allowed_active_categories
                or legacy_candidate.action.get("action_type")
                != self.config.allowed_action_type):
            return self._readout(
                "ineligible", "active-winner-is-not-configured-defense-slice",
                snapshot, revision, persistence_union,
                checks=checks + ["active-fortification-slice"])
        checks.append("active-fortification-slice")
        additions = tuple(
            persistence_union.persistence_added_operation_ids)
        if len(additions) != 1:
            return self._readout(
                "ineligible", "requires-one-persistence-only-alternative",
                snapshot, revision, persistence_union,
                checks=checks + ["single-persistence-addition"])
        checks.append("single-persistence-addition")
        candidates = tuple(candidates)
        scores = tuple(scores)
        if (any(not isinstance(value, ShadowOperationCandidate)
                for value in candidates)
                or any(not isinstance(value, OperationScore)
                       for value in scores)):
            raise TypeError(
                "alternative collection requires typed candidates and scores")
        candidate_by_id = dict(
            (value.operation.operation_id, value) for value in candidates)
        score_by_id = dict((value.operation_id, value) for value in scores)
        baseline_matches = tuple(
            value for value in candidates
            if value.action_key == legacy_candidate.action_key)
        if len(baseline_matches) != 1:
            return self._readout(
                "ineligible", "active-winner-has-no-unique-fdas-route",
                snapshot, revision, persistence_union,
                checks=checks + ["active-winner-route-binding"])
        baseline = baseline_matches[0]
        treatment = candidate_by_id.get(additions[0])
        if (baseline.operation.operation_id
                != persistence_union.baseline_selected_operation_id):
            return self._readout(
                "ineligible", "active-winner-differs-from-fdas-scalar-winner",
                snapshot, revision, persistence_union,
                checks=checks + ["scalar-active-winner-equivalence"])
        checks.extend((
            "active-winner-route-binding",
            "scalar-active-winner-equivalence",
        ))
        if (treatment is None
                or treatment.operation.operation_id
                == baseline.operation.operation_id
                or treatment.action_key == baseline.action_key):
            return self._readout(
                "ineligible", "persistence-alternative-is-not-distinct-current-route",
                snapshot, revision, persistence_union,
                checks=checks + ["distinct-treatment-route"])
        checks.append("distinct-treatment-route")
        baseline_score = score_by_id.get(baseline.operation.operation_id)
        treatment_score = score_by_id.get(treatment.operation.operation_id)
        if (baseline_score is None or treatment_score is None
                or not baseline_score.admissible
                or not treatment_score.admissible):
            return self._readout(
                "ineligible", "alternative-score-is-unavailable-or-inadmissible",
                snapshot, revision, persistence_union,
                checks=checks + ["admissible-score-pair"])
        checks.append("admissible-score-pair")
        if (baseline.operation.operation_type
                != treatment.operation.operation_type
                or baseline.operation.target_ref is None
                or treatment.operation.target_ref is None
                or baseline.resource_keys == treatment.resource_keys
                or set(baseline.resource_keys).intersection(
                    treatment.resource_keys)):
            return self._readout(
                "ineligible", "alternative-pair-slice-or-resource-mismatch",
                snapshot, revision, persistence_union,
                checks=checks + ["same-slice-distinct-resource-pair"])
        checks.append("same-slice-distinct-resource-pair")
        if (self.config.require_same_target_ref
                and baseline.operation.target_ref
                != treatment.operation.target_ref):
            return self._readout(
                "ineligible", "alternative-target-reference-mismatch",
                snapshot, revision, persistence_union,
                checks=checks + ["configured-target-match-gate"])
        checks.append("configured-target-match-gate")
        if self.config.allowed_action_type == "unit_move":
            baseline_actor = snapshot.unit(baseline.action["actor_id"])
            treatment_actor = snapshot.unit(treatment.action["actor_id"])
            if (baseline_actor is None or treatment_actor is None
                    or baseline_actor.unit_type != treatment_actor.unit_type
                    or baseline.action.get("movement_cost")
                    != treatment.action.get("movement_cost")):
                return self._readout(
                    "ineligible",
                    "reinforcement-actor-or-step-cost-mismatch",
                    snapshot, revision, persistence_union,
                    checks=checks + ["matched-reinforcement-actor-class"])
            checks.append("matched-reinforcement-actor-class")
        priority_regret = (
            float(baseline_score.priority)
            - float(treatment_score.priority))
        if (priority_regret < -1e-12
                or priority_regret
                > self.config.maximum_priority_regret + 1e-12):
            return self._readout(
                "ineligible", "priority-regret-outside-safe-bound",
                snapshot, revision, persistence_union,
                checks=checks + ["bounded-priority-regret"],
                priority_regret=max(0.0, priority_regret))
        checks.append("bounded-priority-regret")
        risk_delta = abs(
            float(baseline_score.risk_penalty)
            - float(treatment_score.risk_penalty))
        if risk_delta > self.config.maximum_risk_penalty_delta + 1e-12:
            return self._readout(
                "ineligible", "risk-penalty-delta-outside-safe-bound",
                snapshot, revision, persistence_union,
                checks=checks + ["bounded-risk-delta"],
                priority_regret=priority_regret,
                risk_penalty_delta=risk_delta)
        checks.append("bounded-risk-delta")
        control_arm, reason = self._preflight(
            "control", baseline, baseline_score,
            snapshot, revision, shadow_evaluation.goals)
        if control_arm is None:
            return self._readout(
                "ineligible", reason, snapshot, revision, persistence_union,
                checks=checks + ["control-exact-preflight"],
                priority_regret=priority_regret,
                risk_penalty_delta=risk_delta)
        checks.append("control-exact-preflight")
        treatment_arm, reason = self._preflight(
            "treatment", treatment, treatment_score,
            snapshot, revision, shadow_evaluation.goals)
        if treatment_arm is None:
            return self._readout(
                "ineligible", reason, snapshot, revision, persistence_union,
                checks=checks + ["treatment-exact-preflight"],
                arms=(control_arm,), priority_regret=priority_regret,
                risk_penalty_delta=risk_delta)
        checks.append("treatment-exact-preflight")
        material = {
            "control_operation_id": control_arm.operation_id,
            "experiment_id": self.config.experiment_id,
            "game_id": snapshot.identity.game_id,
            "persistence_union_result_hash": persistence_union.result_hash,
            "policy_version": ALTERNATIVE_OUTCOME_POLICY_VERSION,
            "randomization_seed": self.config.randomization_seed,
            "revision_id": revision.revision_id,
            "snapshot_id": snapshot.snapshot_id,
            "treatment_operation_id": treatment_arm.operation_id,
        }
        assignment_hash = structural_hash(material)
        draw = int(assignment_hash[:16], 16) / float(2 ** 64)
        assigned_arm = (
            "treatment"
            if draw < self.config.treatment_probability else "control")
        propensity = (
            self.config.treatment_probability
            if assigned_arm == "treatment"
            else 1.0 - self.config.treatment_probability)
        checks.append("stable-propensity-recorded-assignment")
        return self._readout(
            "eligible-shadow", None, snapshot, revision, persistence_union,
            checks=checks,
            arms=(control_arm, treatment_arm),
            assigned_arm=assigned_arm,
            selection_propensity=propensity,
            assignment_draw=draw,
            assignment_material_hash=assignment_hash,
            priority_regret=priority_regret,
            risk_penalty_delta=risk_delta)
