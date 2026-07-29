"""Evidence-locked limited live activation and packet-safe rollback."""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash
from ..pressure.packets import PacketCost, PacketSchedule
from .impact import ImpactCandidate
from .impact_flow_adapter import ControlDecision


@dataclass(frozen=True)
class PairedCohortEvidence:
    cohort_id: str
    preregistered_primary_metric: str
    ruleset_digest: str
    opponent_profile: str
    horizon_turns: int
    controller_profile_hash: str
    treatment_seeds: tuple
    control_seeds: tuple
    tuning_protocol_hash: str
    engine_backed: bool
    fresh_confirmation: bool
    primary_effect: float
    confidence_interval: tuple
    primary_endpoint_met: bool
    controller_inclusive_compute: bool
    exact_replay_valid: bool
    schema_valid: bool
    unsupported_legality_violations: int
    safety_violations: int
    pilot_data_excluded: bool

    def __post_init__(self):
        for value, name in (
                (self.cohort_id, "cohort ID"),
                (self.preregistered_primary_metric,
                 "primary metric"),
                (self.ruleset_digest, "ruleset digest"),
                (self.opponent_profile, "opponent profile"),
                (self.controller_profile_hash,
                 "controller profile hash"),
                (self.tuning_protocol_hash,
                 "tuning protocol hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("{} is required".format(name))
        if (isinstance(self.horizon_turns, bool)
                or not isinstance(self.horizon_turns, int)
                or self.horizon_turns < 1):
            raise ValueError(
                "cohort horizon must be positive")
        if (not self.treatment_seeds
                or not self.control_seeds
                or set(self.treatment_seeds)
                & set(self.control_seeds)):
            raise ValueError(
                "treatment/control seeds must be nonempty and disjoint")
        if (len(self.confidence_interval) != 2
                or not all(math.isfinite(float(value))
                           for value
                           in self.confidence_interval)
                or self.confidence_interval[0]
                > self.confidence_interval[1]):
            raise ValueError(
                "cohort confidence interval is invalid")
        if not math.isfinite(float(self.primary_effect)):
            raise ValueError(
                "primary effect must be finite")
        for value, name in (
                (self.unsupported_legality_violations,
                 "legality violations"),
                (self.safety_violations,
                 "safety violations")):
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0):
                raise ValueError(
                    "{} must be non-negative".format(name))

    @property
    def eligible(self):
        return all((
            self.engine_backed,
            self.fresh_confirmation,
            self.primary_endpoint_met,
            self.controller_inclusive_compute,
            self.exact_replay_valid,
            self.schema_valid,
            self.unsupported_legality_violations == 0,
            self.safety_violations == 0,
            self.pilot_data_excluded,
        ))

    @property
    def evidence_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "cohort_id": self.cohort_id,
            "confidence_interval": [
                float(value)
                for value in self.confidence_interval],
            "control_seeds": list(
                self.control_seeds),
            "controller_inclusive_compute": (
                self.controller_inclusive_compute),
            "controller_profile_hash": (
                self.controller_profile_hash),
            "eligible": self.eligible,
            "engine_backed": self.engine_backed,
            "exact_replay_valid": (
                self.exact_replay_valid),
            "fresh_confirmation": (
                self.fresh_confirmation),
            "horizon_turns": self.horizon_turns,
            "opponent_profile": self.opponent_profile,
            "pilot_data_excluded": (
                self.pilot_data_excluded),
            "preregistered_primary_metric": (
                self.preregistered_primary_metric),
            "primary_effect": float(
                self.primary_effect),
            "primary_endpoint_met": (
                self.primary_endpoint_met),
            "ruleset_digest": self.ruleset_digest,
            "safety_violations": self.safety_violations,
            "schema_valid": self.schema_valid,
            "treatment_seeds": list(
                self.treatment_seeds),
            "tuning_protocol_hash": (
                self.tuning_protocol_hash),
            "unsupported_legality_violations": (
                self.unsupported_legality_violations),
        }


@dataclass(frozen=True)
class LiveScopePolicy:
    enabled_categories: tuple
    enabled_context_digests: tuple
    maximum_commit_rejection_rate: float = 0.05
    maximum_controller_latency_ms: float = 500.0
    allow_irreversible: bool = False

    def __post_init__(self):
        for values, name in (
                (self.enabled_categories, "live categories"),
                (self.enabled_context_digests, "live contexts")):
            if (len(set(values)) != len(values)
                    or any(not isinstance(value, str) or not value
                           for value in values)):
                raise ValueError(
                    "{} must be unique nonempty text".format(name))
        rejection = float(
            self.maximum_commit_rejection_rate)
        if not 0.0 <= rejection <= 1.0:
            raise ValueError(
                "commit rejection limit must be in [0, 1]")
        latency = float(
            self.maximum_controller_latency_ms)
        if not math.isfinite(latency) or latency <= 0.0:
            raise ValueError(
                "live latency limit must be positive")
        if not isinstance(self.allow_irreversible, bool):
            raise TypeError(
                "irreversible policy must be boolean")


@dataclass(frozen=True)
class LiveActivationResult:
    allowed: bool
    reason: str
    category: str
    context_digest: str
    evidence_hash: object
    rollback_mode: str
    activation_scope: str

    def to_dict(self):
        return {
            "activation_scope": self.activation_scope,
            "allowed": self.allowed,
            "category": self.category,
            "context_digest": self.context_digest,
            "evidence_hash": self.evidence_hash,
            "reason": self.reason,
            "rollback_mode": self.rollback_mode,
        }


class LimitedLiveActivationGate:
    """Permit only a predeclared, freshly confirmed engine-live subset."""

    GATE_IDENTITY = "limited-live-activation/1.0"

    def __init__(self, scope_policy):
        if not isinstance(scope_policy, LiveScopePolicy):
            raise TypeError(
                "live gate requires LiveScopePolicy")
        self.scope_policy = scope_policy

    def evaluate(
            self, candidate, context_digest,
            evidence, advisory_decision,
            commit_rejection_rate,
            controller_latency_ms,
            transition_calibrated):
        if not isinstance(candidate, ImpactCandidate):
            raise TypeError(
                "live activation requires ImpactCandidate")
        if not isinstance(
                advisory_decision, ControlDecision):
            raise TypeError(
                "live activation requires ControlDecision")
        if evidence is not None and not isinstance(
                evidence, PairedCohortEvidence):
            raise TypeError(
                "live evidence has wrong type")
        rejection = float(commit_rejection_rate)
        latency = float(controller_latency_ms)
        if (not 0.0 <= rejection <= 1.0
                or not math.isfinite(latency)
                or latency < 0.0):
            raise ValueError(
                "live health measurements are invalid")
        if not isinstance(transition_calibrated, bool):
            raise TypeError(
                "transition calibration status must be boolean")
        checks = (
            (
                candidate.category
                in self.scope_policy.enabled_categories,
                "category-not-enabled"),
            (
                context_digest
                in self.scope_policy.enabled_context_digests,
                "context-not-enabled"),
            (
                evidence is not None and evidence.eligible,
                "fresh-engine-paired-evidence-required"),
            (
                advisory_decision.health == "healthy"
                and advisory_decision.artifact.get(
                    "advisory_accepted") is True,
                "healthy-advisory-acceptance-required"),
            (
                advisory_decision.packet_schedule is not None
                and advisory_decision.packet_schedule.conserved,
                "conserved-packet-schedule-required"),
            (
                transition_calibrated,
                "transition-calibration-required"),
            (
                rejection <= self.scope_policy
                .maximum_commit_rejection_rate,
                "commit-rejection-rate-high"),
            (
                latency <= self.scope_policy
                .maximum_controller_latency_ms,
                "controller-latency-high"),
            (
                self.scope_policy.allow_irreversible
                or bool((candidate.projection or {}).get(
                    "reversible", True)),
                "irreversible-category-not-enabled"),
        )
        failed = next((
            reason for passed, reason in checks
            if not passed), None)
        return LiveActivationResult(
            allowed=failed is None,
            reason=(
                "live-scope-accepted"
                if failed is None else failed),
            category=candidate.category,
            context_digest=context_digest,
            evidence_hash=(
                evidence.evidence_hash
                if evidence is not None else None),
            rollback_mode="scalar_v2",
            activation_scope=(
                "predeclared-limited-category-context"))


@dataclass(frozen=True)
class RollbackResult:
    source_mode: str
    target_mode: str
    released_packets: tuple
    expired_operation_ids: tuple
    truth_mutations: int
    rollback_identity: str

    def __post_init__(self):
        if any(not isinstance(row, PacketCost)
               for row in self.released_packets):
            raise TypeError(
                "rollback packets have wrong type")
        if self.truth_mutations != 0:
            raise ValueError(
                "controller rollback cannot mutate truth")

    def to_dict(self):
        return {
            "expired_operation_ids": list(
                self.expired_operation_ids),
            "released_packets": [
                row.to_dict() for row in self.released_packets],
            "rollback_identity": self.rollback_identity,
            "source_mode": self.source_mode,
            "target_mode": self.target_mode,
            "truth_mutations": self.truth_mutations,
        }


class ControllerRollback:
    ROLLBACK_IDENTITY = "flow-controller-rollback/1.0"

    def rollback(
            self, decision, target_mode="scalar_v2"):
        if not isinstance(decision, ControlDecision):
            raise TypeError(
                "rollback requires ControlDecision")
        if target_mode not in (
                "scalar_v2", "legacy_scalar",
                "canonical"):
            raise ValueError(
                "rollback target is not safe")
        schedule = decision.packet_schedule
        if schedule is not None and not isinstance(
                schedule, PacketSchedule):
            raise TypeError(
                "rollback schedule has wrong type")
        released = []
        expired = []
        if schedule is not None:
            for reservation in schedule.reservations:
                released.extend(reservation.reserved)
                expired.append(
                    reservation.operation_id)
        return RollbackResult(
            source_mode=decision.controller_mode,
            target_mode=target_mode,
            released_packets=tuple(released),
            expired_operation_ids=tuple(expired),
            truth_mutations=0,
            rollback_identity=self.ROLLBACK_IDENTITY)
