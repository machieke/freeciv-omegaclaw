"""Immutable request contracts for Freeciv domain transition models."""

from dataclasses import dataclass
from typing import Optional, Protocol, Tuple

from .context import EstimateValidity


@dataclass(frozen=True)
class CandidateDomainFeatures:
    """Small typed hints that cannot otherwise be recovered from a snapshot."""

    schema_version: int
    actor_id: Optional[str]
    target_id: Optional[str]
    advertised_action_id: Optional[str]
    intent_tags: Tuple[str, ...]

    def __post_init__(self):
        if (isinstance(self.schema_version, bool)
                or not isinstance(self.schema_version, int)
                or self.schema_version < 1):
            raise ValueError("candidate feature schema version must be positive")
        for value, name in (
                (self.actor_id, "actor ID"),
                (self.target_id, "target ID"),
                (self.advertised_action_id, "advertised action ID")):
            if value is not None and (
                    not isinstance(value, str) or not value):
                raise ValueError("{} must be a non-empty string or absent".format(
                    name))
        if any(not isinstance(value, str) or not value
               for value in self.intent_tags):
            raise ValueError("candidate intent tags must be non-empty strings")
        if tuple(sorted(set(self.intent_tags))) != self.intent_tags:
            raise ValueError(
                "candidate intent tags must be unique and canonically sorted")

    def to_dict(self):
        return {
            "actor_id": self.actor_id,
            "advertised_action_id": self.advertised_action_id,
            "intent_tags": list(self.intent_tags),
            "schema_version": int(self.schema_version),
            "target_id": self.target_id,
        }


@dataclass(frozen=True)
class DomainEstimateRequest:
    """One isolated request for an intrinsic action transition estimate."""

    request_id: str
    snapshot: object
    ruleset_ir: object
    legal_action: object
    candidate: object
    goal_losses: tuple
    operation_context: object
    validity: EstimateValidity
    horizon_turn: int
    features: Optional[CandidateDomainFeatures] = None

    def __post_init__(self):
        if not isinstance(self.request_id, str) or not self.request_id:
            raise ValueError("domain estimate request requires a request ID")
        if not isinstance(self.validity, EstimateValidity):
            raise TypeError("domain estimate request requires EstimateValidity")
        if (isinstance(self.horizon_turn, bool)
                or not isinstance(self.horizon_turn, int)
                or self.horizon_turn < self.validity.estimated_at_turn):
            raise ValueError(
                "domain estimate horizon cannot precede the estimate turn")
        rows = tuple(self.goal_losses)
        if any(not isinstance(row, tuple) or len(row) != 2
               or not isinstance(row[0], str) or not row[0]
               or isinstance(row[1], bool)
               or not isinstance(row[1], (int, float))
               or float(row[1]) < 0.0
               for row in rows):
            raise ValueError(
                "goal losses must be (non-empty goal ID, non-negative loss)")
        keys = [row[0] for row in rows]
        if len(keys) != len(set(keys)) or tuple(sorted(rows)) != rows:
            raise ValueError(
                "goal losses must be unique and canonically sorted")
        if self.features is not None and not isinstance(
                self.features, CandidateDomainFeatures):
            raise TypeError("request features have the wrong type")

    @property
    def action_category(self):
        return str(getattr(self.candidate, "category", "unknown") or "unknown")

    @property
    def action_type(self):
        action = self.legal_action
        if not isinstance(action, dict):
            action = getattr(self.candidate, "action", {})
        return str(
            action.get("action_type", action.get("type", "unknown"))
            if isinstance(action, dict) else "unknown")

    @property
    def stable_operation_id(self):
        return "gdo-operation:{}".format(self.request_id)


class DomainTransitionModel(Protocol):
    """Interface implemented by grounded and explicitly legacy estimators."""

    model_id: str
    model_version: str
    immutable_request_safe: bool

    def supports(self, request: DomainEstimateRequest) -> bool:
        ...

    def estimate(
            self, request: DomainEstimateRequest
    ) -> "GroundedTransitionEstimate":
        ...
