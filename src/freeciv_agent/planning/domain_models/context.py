"""Authority, context, and validity envelopes for transition predictions."""

import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from ...pressure.transitions import ExpectedTransition


UNKNOWN_CONTEXT = "unknown"


def canonical_model_artifact(value):
    if not isinstance(value, dict):
        raise TypeError(
            "domain model artifact must be a dictionary")
    return json.dumps(
        value, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"))


class EstimateAuthority(str, Enum):
    EXACT_AUTHORITATIVE = "exact_authoritative"
    DETERMINISTIC_DERIVED = "deterministic_derived"
    CALIBRATED = "calibrated"
    HEURISTIC = "heuristic"
    LEGACY_PROXY = "legacy_proxy"
    ABSTAIN = "abstain"


LIVE_APPROVED_AUTHORITIES = frozenset((
    EstimateAuthority.EXACT_AUTHORITATIVE,
    EstimateAuthority.DETERMINISTIC_DERIVED,
    EstimateAuthority.CALIBRATED,
))


def canonical_context_token(value):
    """Return one stable, non-empty context token."""
    value = str(value if value is not None else UNKNOWN_CONTEXT).strip()
    if not value:
        return UNKNOWN_CONTEXT
    return value.lower().replace(" ", "_")


@dataclass(frozen=True)
class TransitionContextKey:
    schema_version: int
    action_category: str
    action_type: str
    goal_id: str
    lifecycle_state: str
    actor_class: Optional[str]
    target_class: Optional[str]
    threat_regime: Optional[str]
    terrain_bucket: Optional[str]
    horizon_bucket: str
    ruleset_digest: str

    def __post_init__(self):
        if (isinstance(self.schema_version, bool)
                or not isinstance(self.schema_version, int)
                or self.schema_version < 1):
            raise ValueError("transition context schema version must be positive")
        for value, name in (
                (self.action_category, "action category"),
                (self.action_type, "action type"),
                (self.goal_id, "goal ID"),
                (self.lifecycle_state, "lifecycle state"),
                (self.horizon_bucket, "horizon bucket"),
                (self.ruleset_digest, "ruleset digest")):
            if not isinstance(value, str) or not value:
                raise ValueError("{} must be a non-empty string".format(name))
        for value, name in (
                (self.actor_class, "actor class"),
                (self.target_class, "target class"),
                (self.threat_regime, "threat regime"),
                (self.terrain_bucket, "terrain bucket")):
            if value is not None and (
                    not isinstance(value, str) or not value):
                raise ValueError("{} must be a non-empty string or absent".format(
                    name))

    def to_dict(self):
        return {
            "action_category": self.action_category,
            "action_type": self.action_type,
            "actor_class": self.actor_class,
            "goal_id": self.goal_id,
            "horizon_bucket": self.horizon_bucket,
            "lifecycle_state": self.lifecycle_state,
            "ruleset_digest": self.ruleset_digest,
            "schema_version": int(self.schema_version),
            "target_class": self.target_class,
            "terrain_bucket": self.terrain_bucket,
            "threat_regime": self.threat_regime,
        }


@dataclass(frozen=True)
class EstimateValidity:
    snapshot_id: str
    legal_actions_digest: str
    ruleset_digest: str
    estimated_at_turn: int
    valid_through_turn: int

    def __post_init__(self):
        for value, name in (
                (self.snapshot_id, "snapshot ID"),
                (self.legal_actions_digest, "legal-actions digest"),
                (self.ruleset_digest, "ruleset digest")):
            if not isinstance(value, str) or not value:
                raise ValueError("{} must be a non-empty string".format(name))
        for value, name in (
                (self.estimated_at_turn, "estimate turn"),
                (self.valid_through_turn, "valid-through turn")):
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0):
                raise ValueError("{} must be a non-negative integer".format(name))
        if self.valid_through_turn < self.estimated_at_turn:
            raise ValueError("estimate validity cannot end before it begins")

    def matches(
            self, snapshot_id, legal_actions_digest,
            ruleset_digest, turn):
        return bool(
            self.snapshot_id == str(snapshot_id)
            and self.legal_actions_digest == str(legal_actions_digest)
            and self.ruleset_digest == str(ruleset_digest)
            and self.estimated_at_turn <= int(turn)
            <= self.valid_through_turn)

    def to_dict(self):
        return {
            "estimated_at_turn": int(self.estimated_at_turn),
            "legal_actions_digest": self.legal_actions_digest,
            "ruleset_digest": self.ruleset_digest,
            "snapshot_id": self.snapshot_id,
            "valid_through_turn": int(self.valid_through_turn),
        }


@dataclass(frozen=True)
class GroundedTransitionEstimate:
    transition: ExpectedTransition
    context_key: TransitionContextKey
    authority: EstimateAuthority
    confidence: float
    validity: EstimateValidity
    estimator_id: str
    estimator_version: str
    provenance: Tuple[str, ...]
    abstention_reason: Optional[str] = None
    model_artifact_json: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.transition, ExpectedTransition):
            raise TypeError("grounded estimate requires ExpectedTransition")
        if not isinstance(self.context_key, TransitionContextKey):
            raise TypeError("grounded estimate requires TransitionContextKey")
        if not isinstance(self.authority, EstimateAuthority):
            raise TypeError("grounded estimate authority has the wrong type")
        confidence = float(self.confidence)
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError("grounded estimate confidence must be in [0,1]")
        if not isinstance(self.validity, EstimateValidity):
            raise TypeError("grounded estimate requires EstimateValidity")
        for value, name in (
                (self.estimator_id, "estimator ID"),
                (self.estimator_version, "estimator version")):
            if not isinstance(value, str) or not value:
                raise ValueError("{} must be a non-empty string".format(name))
        if (not self.provenance
                or any(not isinstance(value, str) or not value
                       for value in self.provenance)):
            raise ValueError("grounded estimate requires provenance")
        if self.authority == EstimateAuthority.ABSTAIN:
            if (not isinstance(self.abstention_reason, str)
                    or not self.abstention_reason):
                raise ValueError("abstention requires a reason")
        elif self.abstention_reason is not None:
            raise ValueError("non-abstaining estimate cannot have an abstention reason")
        if (self.authority == EstimateAuthority.EXACT_AUTHORITATIVE
                and self.transition.residual_probability > 0.0):
            raise ValueError(
                "exact authoritative estimate cannot retain unknown mass")
        if self.context_key.ruleset_digest != self.validity.ruleset_digest:
            raise ValueError(
                "context and validity ruleset digests must agree")
        if self.model_artifact_json is not None:
            if (not isinstance(
                    self.model_artifact_json, str)
                    or not self.model_artifact_json):
                raise ValueError(
                    "model artifact JSON must be non-empty or absent")
            try:
                artifact = json.loads(
                    self.model_artifact_json)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "model artifact JSON is invalid") from error
            if not isinstance(artifact, dict):
                raise ValueError(
                    "model artifact JSON must encode an object")

    def live_eligible(
            self, snapshot_id, legal_actions_digest,
            ruleset_digest, turn):
        return bool(
            self.authority in LIVE_APPROVED_AUTHORITIES
            and self.validity.matches(
                snapshot_id, legal_actions_digest,
                ruleset_digest, turn))

    def to_dict(self):
        result = {
            "abstention_reason": self.abstention_reason,
            "authority": self.authority.value,
            "confidence": float(self.confidence),
            "context_key": self.context_key.to_dict(),
            "estimator_id": self.estimator_id,
            "estimator_version": self.estimator_version,
            "provenance": list(self.provenance),
            "transition": self.transition.to_dict(),
            "validity": self.validity.to_dict(),
        }
        if self.model_artifact_json is not None:
            result["model_artifact"] = json.loads(
                self.model_artifact_json)
        return result
