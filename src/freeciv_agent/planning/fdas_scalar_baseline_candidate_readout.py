"""Decision-safe shadow preference against protected scalar FDAS top-1."""

from dataclasses import dataclass

from ..events.schema import structural_hash
from .fdas_calibrated_candidate_union import FdasCalibratedCandidateUnion
from .fdas_decision_safe_candidate_readout import (
    FdasDecisionSafeCandidateReadoutConfig,
    FdasDecisionSafeCandidateReadoutEvaluator,
    FdasGroundedCandidateValue,
)
from .fdas_defensive_capability import FdasDefensiveCapabilityResolver


SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY = (
    "fdas-scalar-baseline-candidate-readout/1.0")
RULESET_DEFENSIVE_SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY = (
    "fdas-scalar-baseline-candidate-readout/1.1")
CALIBRATED_EQUIVALENCE_PARETO_CANDIDATE_READOUT_IDENTITY = (
    "fdas-scalar-baseline-candidate-readout/1.2")
SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITIES = frozenset((
    SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY,
    RULESET_DEFENSIVE_SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY,
    CALIBRATED_EQUIVALENCE_PARETO_CANDIDATE_READOUT_IDENTITY,
))
SCALAR_BASELINE_CONTROL_SEMANTICS = "protected-fdas-scalar-top-1"


@dataclass(frozen=True)
class FdasScalarBaselineCandidateReadout:
    status: str
    reason: str
    snapshot_id: str
    revision_id: str
    protected_union_result_hash: str
    control_semantics: str
    config: dict
    baseline_operation_id: object
    proposed_operation_id: object
    shadow_preference: bool
    candidates: tuple
    rejected: tuple
    result_hash: str
    identity: str = SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY

    def __post_init__(self):
        if self.status not in ("eligible-shadow", "abstained"):
            raise ValueError("scalar-baseline readout status is invalid")
        for value, name in (
                (self.reason, "reason"),
                (self.snapshot_id, "snapshot ID"),
                (self.revision_id, "revision ID"),
                (self.protected_union_result_hash, "protected union hash"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "scalar-baseline readout {} is required".format(name))
        if self.control_semantics != SCALAR_BASELINE_CONTROL_SEMANTICS:
            raise ValueError("scalar-baseline control semantics differ")
        if self.identity not in SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITIES:
            raise ValueError("scalar-baseline readout identity differs")
        canonical = FdasDecisionSafeCandidateReadoutConfig.from_dict(
            dict(self.config)).to_dict()
        if canonical != self.config:
            raise ValueError("scalar-baseline config is not canonical")
        object.__setattr__(self, "config", canonical)
        candidates = tuple(self.candidates)
        rejected = tuple(sorted(set(str(value) for value in self.rejected)))
        if any(not isinstance(value, FdasGroundedCandidateValue)
               for value in candidates):
            raise TypeError("scalar-baseline readout candidates are untyped")
        if any(not value for value in rejected):
            raise ValueError("scalar-baseline rejection is invalid")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "rejected", rejected)
        eligible = self.status == "eligible-shadow"
        if (eligible != self.shadow_preference
                or eligible != (self.proposed_operation_id is not None)
                or (eligible and self.baseline_operation_id is None)
                or (eligible and self.proposed_operation_id
                    == self.baseline_operation_id)):
            raise ValueError("scalar-baseline preference semantics differ")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("scalar-baseline result hash differs")

    def _semantic(self):
        return {
            "action_selection_changed": False,
            "baseline_operation_id": self.baseline_operation_id,
            "candidates": [value.to_dict() for value in self.candidates],
            "config": dict(self.config),
            "control_semantics": self.control_semantics,
            "identity": self.identity,
            "policy_authority": False,
            "proposed_operation_id": self.proposed_operation_id,
            "protected_union_result_hash": self.protected_union_result_hash,
            "readout_authority": False,
            "reason": self.reason,
            "rejected": list(self.rejected),
            "revision_id": self.revision_id,
            "shadow_preference": self.shadow_preference,
            "snapshot_id": self.snapshot_id,
            "status": self.status,
            "truth_mutated": False,
        }

    def to_dict(self):
        value = self._semantic()
        value["result_hash"] = self.result_hash
        return value


class FdasScalarBaselineCandidateReadoutEvaluator(
        FdasDecisionSafeCandidateReadoutEvaluator):
    """Compare protected candidates only with their scalar top-1 control."""

    def __init__(self, config=None, ruleset_ir=None,
                 calibrated_equivalence_pareto=False):
        if not isinstance(calibrated_equivalence_pareto, bool):
            raise TypeError(
                "calibrated equivalence Pareto flag must be boolean")
        if calibrated_equivalence_pareto and ruleset_ir is None:
            raise ValueError(
                "calibrated equivalence Pareto requires ruleset grounding")
        resolver = (
            None if ruleset_ir is None
            else FdasDefensiveCapabilityResolver(ruleset_ir))
        super().__init__(config, resolver)
        self.calibrated_equivalence_pareto = calibrated_equivalence_pareto
        self.record_calibration_comparison = calibrated_equivalence_pareto
        self.readout_identity = (
            SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY
            if resolver is None else
            CALIBRATED_EQUIVALENCE_PARETO_CANDIDATE_READOUT_IDENTITY
            if calibrated_equivalence_pareto else
            RULESET_DEFENSIVE_SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY)

    @staticmethod
    def _calibrated_equivalent(control, alternative):
        return all(getattr(control, name) == getattr(alternative, name)
                   for name in (
                       "effective_lineages",
                       "estimate",
                       "interval_lower",
                       "interval_upper",
                       "prediction_reason",
                   ))

    @staticmethod
    def _pair_scope_rejections(candidate, baseline_candidate):
        """Return exact fail-closed scope predicates without changing scope."""
        reasons = []
        if candidate.action_key == baseline_candidate.action_key:
            reasons.append("duplicate-action")
        if (candidate.operation.operation_type
                != baseline_candidate.operation.operation_type):
            reasons.append("operation-type-mismatch")
        if (candidate.operation.target_ref
                != baseline_candidate.operation.target_ref):
            reasons.append("target-ref-mismatch")
        if candidate.resource_keys == baseline_candidate.resource_keys:
            reasons.append("identical-resource-set")
        overlap = tuple(sorted(set(candidate.resource_keys).intersection(
            baseline_candidate.resource_keys)))
        reasons.extend(
            "resource-overlap:" + str(value) for value in overlap)
        return tuple(reasons)

    def _ground(self, candidate, prediction, snapshot, revision, goals,
                *, eligibility_reason, checks=()):
        return self._ground_exact(
            candidate, prediction, snapshot, revision, goals,
            eligibility_reason=eligibility_reason, checks=checks)

    def _readout(self, status, reason, snapshot, revision, protected_union,
                 baseline_operation_id=None, proposed_operation_id=None,
                 candidates=(), rejected=()):
        semantic = {
            "action_selection_changed": False,
            "baseline_operation_id": baseline_operation_id,
            "candidates": [value.to_dict() for value in candidates],
            "config": self.config.to_dict(),
            "control_semantics": SCALAR_BASELINE_CONTROL_SEMANTICS,
            "identity": self.readout_identity,
            "policy_authority": False,
            "proposed_operation_id": proposed_operation_id,
            "protected_union_result_hash": protected_union.result_hash,
            "readout_authority": False,
            "reason": reason,
            "rejected": sorted(set(str(value) for value in rejected)),
            "revision_id": revision.revision_id,
            "shadow_preference": status == "eligible-shadow",
            "snapshot_id": snapshot.snapshot_id,
            "status": status,
            "truth_mutated": False,
        }
        return FdasScalarBaselineCandidateReadout(
            status, reason, snapshot.snapshot_id, revision.revision_id,
            protected_union.result_hash, SCALAR_BASELINE_CONTROL_SEMANTICS,
            self.config.to_dict(), baseline_operation_id,
            proposed_operation_id, status == "eligible-shadow",
            tuple(candidates), tuple(semantic["rejected"]),
            structural_hash(semantic), self.readout_identity)

    def evaluate(self, snapshot, revision, shadow_evaluation,
                 candidates, protected_union):
        if not isinstance(protected_union, FdasCalibratedCandidateUnion):
            raise TypeError(
                "scalar-baseline readout requires calibrated candidate union")
        if (protected_union.snapshot_id != snapshot.snapshot_id
                or protected_union.revision_id != revision.revision_id
                or shadow_evaluation.snapshot_id != snapshot.snapshot_id
                or shadow_evaluation.revision_id != revision.revision_id):
            return self._readout(
                "abstained", "input-is-not-revision-current",
                snapshot, revision, protected_union)
        candidates = tuple(candidates)
        candidate_by_id = {
            value.operation.operation_id: value for value in candidates}
        predictions = {
            value.operation_id: value for value in protected_union.readouts}
        if (len(candidate_by_id) != len(candidates)
                or set(predictions) != set(candidate_by_id)):
            return self._readout(
                "abstained", "candidate-surface-is-incomplete",
                snapshot, revision, protected_union)
        baseline_id = protected_union.baseline_selected_operation_id
        baseline_candidate = candidate_by_id.get(baseline_id)
        baseline_prediction = predictions.get(baseline_id)
        if (baseline_candidate is None or baseline_prediction is None
                or baseline_prediction.baseline_rank != 1):
            return self._readout(
                "abstained", "scalar-baseline-is-not-reconstructable",
                snapshot, revision, protected_union)
        if (baseline_candidate.action.get("action_type")
                != self.config.allowed_action_type):
            return self._readout(
                "abstained", "scalar-baseline-is-not-reinforcement-move",
                snapshot, revision, protected_union,
                baseline_operation_id=baseline_id)
        control, reason = self._ground(
            baseline_candidate, baseline_prediction,
            snapshot, revision, shadow_evaluation.goals,
            eligibility_reason="protected-scalar-control")
        if control is None:
            return self._readout(
                "abstained", "control-{}".format(reason),
                snapshot, revision, protected_union,
                baseline_operation_id=baseline_id)

        grounded = [control]
        rejected = []
        eligible = []
        protected_ids = tuple(protected_union.operation_ids)
        for operation_id in protected_ids:
            if operation_id == baseline_id:
                continue
            candidate = candidate_by_id.get(operation_id)
            if candidate is None:
                rejected.append(operation_id + ":candidate-is-missing")
                continue
            scope_rejections = self._pair_scope_rejections(
                candidate, baseline_candidate)
            if self.config.require_same_target_ref is not True:
                raise AssertionError(
                    "scalar-baseline readout lost same-target protection")
            if scope_rejections:
                rejected.extend(
                    operation_id + ":pair-scope:" + value
                    for value in scope_rejections)
                continue
            alternative, reason = self._ground(
                candidate, predictions.get(operation_id),
                snapshot, revision, shadow_evaluation.goals,
                eligibility_reason="protected-candidate")
            if alternative is None:
                rejected.append(operation_id + ":" + reason)
                continue
            noninferior, passed, failed = self._noninferiority(
                control, alternative)
            strict_improvements = (
                self._strict_grounded_improvements(control, alternative)
                if self.calibrated_equivalence_pareto else ())
            calibrated_equivalent = bool(
                self.calibrated_equivalence_pareto
                and self._calibrated_equivalent(
                    baseline_prediction, predictions.get(operation_id)))
            equivalence_pareto = bool(
                self.calibrated_equivalence_pareto
                and noninferior
                and calibrated_equivalent
                and strict_improvements)
            alternative = FdasGroundedCandidateValue(**{
                **alternative.__dict__,
                "eligibility_reason": (
                    "grounded-noninferior"
                    if noninferior else "grounded-noninferiority-failed"),
                "noninferiority_checks": passed,
                "strict_grounded_improvements": strict_improvements,
            })
            separated = (
                alternative.interval_lower
                >= control.interval_upper
                + self.config.minimum_interval_separation
                and alternative.interval_lower > control.interval_upper)
            if not separated and not equivalence_pareto:
                grounded.append(alternative)
                rejected.append(
                    operation_id + ":calibrated-interval-overlap")
                if not noninferior:
                    rejected.append(
                        operation_id + ":grounded-noninferiority-failed:"
                        + ",".join(failed))
                continue
            alternative = FdasGroundedCandidateValue(**{
                **alternative.__dict__,
                "eligibility_reason": (
                    ("eligible-interval-separated"
                     if self.calibrated_equivalence_pareto and separated else
                     "eligible-calibrated-equivalence-pareto"
                     if equivalence_pareto else
                     "eligible") if noninferior
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
            reason = (
                "no-protected-alternative"
                if len(protected_ids) == 1
                else "no-separated-grounded-noninferior-alternative")
            return self._readout(
                "abstained", reason, snapshot, revision, protected_union,
                baseline_operation_id=baseline_id,
                candidates=tuple(grounded), rejected=tuple(rejected))
        selected = sorted(
            eligible,
            key=lambda value: (
                (0 if value.eligibility_reason
                 in ("eligible", "eligible-interval-separated") else 1),
                -value.interval_lower,
                -value.estimate,
                value.estimated_turns,
                value.total_movement_cost,
                -value.hp,
                -value.veteran,
                value.operation_id))[0]
        return self._readout(
            "eligible-shadow",
            ("calibrated-equivalence-and-grounded-pareto-dominance"
             if selected.eligibility_reason
             == "eligible-calibrated-equivalence-pareto" else
             "calibrated-and-grounded-dominance"),
            snapshot, revision, protected_union,
            baseline_operation_id=baseline_id,
            proposed_operation_id=selected.operation_id,
            candidates=tuple(grounded), rejected=tuple(rejected))
