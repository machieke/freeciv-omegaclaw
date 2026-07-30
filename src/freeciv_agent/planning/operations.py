"""Versioned, identity-bearing operation contracts.

An operation is durable coordination intent.  It is deliberately separate
from candidate utility, pressure, and the current legal action: those values
may change while the participant/goal/target identity remains stable.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from ..events.schema import structural_hash


OPERATION_SCHEMA_VERSION = 1


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


def _text_tuple(values, name, allow_empty=False):
    values = tuple(values)
    if not allow_empty and not values:
        raise ValueError("{} cannot be empty".format(name))
    if any(
            not isinstance(value, str)
            or not value
            for value in values):
        raise ValueError(
            "{} values must be non-empty strings".format(name))
    if len(set(values)) != len(values):
        raise ValueError(
            "{} values must be unique".format(name))
    return values


class OperationState(str, Enum):
    PROPOSED = "proposed"
    RESERVABLE = "reservable"
    RESERVED = "reserved"
    ACTIVE = "active"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"
    EXPIRED = "expired"


TERMINAL_OPERATION_STATES = frozenset((
    OperationState.COMPLETED,
    OperationState.FAILED,
    OperationState.ABANDONED,
    OperationState.EXPIRED,
))


_ALLOWED_TRANSITIONS = {
    OperationState.PROPOSED: frozenset((
        OperationState.RESERVABLE,
        OperationState.BLOCKED,
        OperationState.FAILED,
        OperationState.ABANDONED,
        OperationState.EXPIRED,
    )),
    OperationState.RESERVABLE: frozenset((
        OperationState.RESERVED,
        OperationState.BLOCKED,
        OperationState.FAILED,
        OperationState.ABANDONED,
        OperationState.EXPIRED,
    )),
    OperationState.RESERVED: frozenset((
        OperationState.ACTIVE,
        OperationState.BLOCKED,
        OperationState.FAILED,
        OperationState.ABANDONED,
        OperationState.EXPIRED,
    )),
    OperationState.ACTIVE: frozenset((
        OperationState.BLOCKED,
        OperationState.SUSPENDED,
        OperationState.COMPLETED,
        OperationState.FAILED,
        OperationState.ABANDONED,
        OperationState.EXPIRED,
    )),
    OperationState.BLOCKED: frozenset((
        OperationState.RESERVABLE,
        OperationState.ACTIVE,
        OperationState.SUSPENDED,
        OperationState.FAILED,
        OperationState.ABANDONED,
        OperationState.EXPIRED,
    )),
    OperationState.SUSPENDED: frozenset((
        OperationState.RESERVABLE,
        OperationState.ACTIVE,
        OperationState.BLOCKED,
        OperationState.FAILED,
        OperationState.ABANDONED,
        OperationState.EXPIRED,
    )),
}


def operation_transition_allowed(current, target):
    current = OperationState(current)
    target = OperationState(target)
    return target in _ALLOWED_TRANSITIONS.get(
        current, ())


def operation_id_from_components(
        operation_type, goal_ids,
        participants, target_ref,
        ruleset_digest, creation_epoch):
    """Return stable identity without incorporating a volatile score."""
    material = {
        "creation_epoch": int(
            creation_epoch),
        "goal_ids": sorted(
            _text_tuple(
                goal_ids, "goal ids")),
        "operation_type":
            _required_text(
                operation_type,
                "operation type"),
        "participants": sorted(
            (
                {
                    "actor_id":
                        _required_text(
                            participant.actor_id,
                            "participant actor id"),
                    "role":
                        _required_text(
                            participant.role,
                            "participant role"),
                }
                for participant in
                tuple(participants)
            ),
            key=lambda row: (
                row["role"],
                row["actor_id"])),
        "ruleset_digest":
            _required_text(
                ruleset_digest,
                "ruleset digest"),
        "target_ref": target_ref,
    }
    if (target_ref is not None
            and (not isinstance(
                target_ref, str)
                 or not target_ref)):
        raise ValueError(
            "target ref must be null or a non-empty string")
    return "operation-" + structural_hash(
        material)[:32]


@dataclass(frozen=True)
class OperationParticipant:
    role: str
    actor_id: str
    actor_class: str
    required: bool

    def __post_init__(self):
        _required_text(
            self.role, "participant role")
        _required_text(
            self.actor_id,
            "participant actor id")
        _required_text(
            self.actor_class,
            "participant actor class")
        if not isinstance(
                self.required, bool):
            raise TypeError(
                "participant required must be boolean")

    def to_dict(self):
        return {
            "actor_class":
                self.actor_class,
            "actor_id": self.actor_id,
            "required": self.required,
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, value):
        return cls(
            role=value["role"],
            actor_id=value["actor_id"],
            actor_class=value[
                "actor_class"],
            required=value["required"])


@dataclass(frozen=True)
class OperationStep:
    step_id: str
    action_type: str
    actor_role: str
    target_ref: Optional[str]
    requirement_set_id: str
    completion_predicate_id: str
    maximum_attempts: int

    def __post_init__(self):
        for value, name in (
                (self.step_id,
                 "step id"),
                (self.action_type,
                 "step action type"),
                (self.actor_role,
                 "step actor role"),
                (self.requirement_set_id,
                 "step requirement set id"),
                (self.completion_predicate_id,
                 "completion predicate id")):
            _required_text(value, name)
        if (self.target_ref is not None
                and (
                    not isinstance(
                        self.target_ref,
                        str)
                    or not self
                    .target_ref)):
            raise ValueError(
                "step target ref must be null or a non-empty string")
        if (isinstance(
                self.maximum_attempts,
                bool)
                or not isinstance(
                    self.maximum_attempts,
                    int)
                or self.maximum_attempts
                < 1):
            raise ValueError(
                "step maximum attempts must be positive")

    def to_dict(self):
        return {
            "action_type":
                self.action_type,
            "actor_role":
                self.actor_role,
            "completion_predicate_id":
                self.completion_predicate_id,
            "maximum_attempts":
                self.maximum_attempts,
            "requirement_set_id":
                self.requirement_set_id,
            "step_id": self.step_id,
            "target_ref":
                self.target_ref,
        }

    @classmethod
    def from_dict(cls, value):
        return cls(
            step_id=value["step_id"],
            action_type=value[
                "action_type"],
            actor_role=value[
                "actor_role"],
            target_ref=value.get(
                "target_ref"),
            requirement_set_id=value[
                "requirement_set_id"],
            completion_predicate_id=value[
                "completion_predicate_id"],
            maximum_attempts=value[
                "maximum_attempts"])


@dataclass(frozen=True)
class OperationSpec:
    schema_version: int
    operation_id: str
    operation_type: str
    goal_ids: Tuple[str, ...]
    participants: Tuple[OperationParticipant, ...]
    target_ref: Optional[str]
    steps: Tuple[OperationStep, ...]
    created_turn: int
    expiry_turn: int
    replacement_margin: float
    provenance: Tuple[str, ...]
    ruleset_digest: str

    def __post_init__(self):
        if self.schema_version != (
                OPERATION_SCHEMA_VERSION):
            raise ValueError(
                "unsupported operation schema version")
        _required_text(
            self.operation_id,
            "operation id")
        _required_text(
            self.operation_type,
            "operation type")
        _required_text(
            self.ruleset_digest,
            "ruleset digest")
        object.__setattr__(
            self, "goal_ids",
            _text_tuple(
                self.goal_ids,
                "goal ids"))
        object.__setattr__(
            self, "participants",
            tuple(self.participants))
        object.__setattr__(
            self, "steps",
            tuple(self.steps))
        object.__setattr__(
            self, "provenance",
            _text_tuple(
                self.provenance,
                "operation provenance"))
        if any(
                not isinstance(
                    row,
                    OperationParticipant)
                for row in
                self.participants):
            raise TypeError(
                "participants must be OperationParticipant values")
        if any(
                not isinstance(
                    row,
                    OperationStep)
                for row in self.steps):
            raise TypeError(
                "steps must be OperationStep values")
        if not self.steps:
            raise ValueError(
                "operation must have at least one step")
        participant_roles = {
            row.role
            for row in
            self.participants}
        if any(
                step.actor_role
                not in participant_roles
                for step in
                self.steps):
            raise ValueError(
                "every operation step must reference a participant role")
        if len({
                row.step_id
                for row in
                self.steps}) != len(
                    self.steps):
            raise ValueError(
                "operation step ids must be unique")
        if (self.target_ref is not None
                and (
                    not isinstance(
                        self.target_ref,
                        str)
                    or not self
                    .target_ref)):
            raise ValueError(
                "target ref must be null or a non-empty string")
        for value, name in (
                (self.created_turn,
                 "created turn"),
                (self.expiry_turn,
                 "expiry turn")):
            if (isinstance(value, bool)
                    or not isinstance(
                        value, int)
                    or value < 0):
                raise ValueError(
                    "{} must be non-negative".format(name))
        if self.expiry_turn < (
                self.created_turn):
            raise ValueError(
                "expiry turn cannot precede creation")
        if (isinstance(
                self.replacement_margin,
                bool)
                or not isinstance(
                    self.replacement_margin,
                    (int, float))
                or self.replacement_margin
                < 0.0):
            raise ValueError(
                "replacement margin must be non-negative")

    @property
    def spec_digest(self):
        return structural_hash(
            self.to_dict(
                include_digest=False))

    def to_dict(
            self, include_digest=True):
        payload = {
            "created_turn":
                self.created_turn,
            "expiry_turn":
                self.expiry_turn,
            "goal_ids": list(
                self.goal_ids),
            "operation_id":
                self.operation_id,
            "operation_type":
                self.operation_type,
            "participants": [
                row.to_dict()
                for row in
                self.participants],
            "provenance": list(
                self.provenance),
            "replacement_margin":
                float(
                    self.replacement_margin),
            "ruleset_digest":
                self.ruleset_digest,
            "schema_version":
                self.schema_version,
            "steps": [
                row.to_dict()
                for row in self.steps],
            "target_ref":
                self.target_ref,
        }
        if include_digest:
            payload["spec_digest"] = (
                self.spec_digest)
        return payload

    @classmethod
    def from_dict(cls, value):
        spec = cls(
            schema_version=value[
                "schema_version"],
            operation_id=value[
                "operation_id"],
            operation_type=value[
                "operation_type"],
            goal_ids=tuple(
                value["goal_ids"]),
            participants=tuple(
                OperationParticipant
                .from_dict(row)
                for row in
                value[
                    "participants"]),
            target_ref=value.get(
                "target_ref"),
            steps=tuple(
                OperationStep
                .from_dict(row)
                for row in
                value["steps"]),
            created_turn=value[
                "created_turn"],
            expiry_turn=value[
                "expiry_turn"],
            replacement_margin=value[
                "replacement_margin"],
            provenance=tuple(
                value["provenance"]),
            ruleset_digest=value[
                "ruleset_digest"])
        digest = value.get(
            "spec_digest")
        if (digest is not None
                and digest
                != spec.spec_digest):
            raise ValueError(
                "operation spec digest mismatch")
        return spec


@dataclass
class OperationProgress:
    operation_id: str
    state: OperationState
    current_step_index: int
    attempt_count: int
    blocked_reason: Optional[str]
    last_snapshot_id: str
    last_updated_turn: int
    terminal_reason: Optional[str] = None

    def __post_init__(self):
        _required_text(
            self.operation_id,
            "operation progress id")
        self.state = OperationState(
            self.state)
        for value, name in (
                (self.current_step_index,
                 "current step index"),
                (self.attempt_count,
                 "attempt count"),
                (self.last_updated_turn,
                 "last updated turn")):
            if (isinstance(value, bool)
                    or not isinstance(
                        value, int)
                    or value < 0):
                raise ValueError(
                    "{} must be non-negative".format(name))
        _required_text(
            self.last_snapshot_id,
            "last snapshot id")
        for value, name in (
                (self.blocked_reason,
                 "blocked reason"),
                (self.terminal_reason,
                 "terminal reason")):
            if (value is not None
                    and (
                        not isinstance(
                            value, str)
                        or not value)):
                raise ValueError(
                    "{} must be null or non-empty".format(name))
        if (self.state
                == OperationState.BLOCKED
                and self.blocked_reason
                is None):
            raise ValueError(
                "blocked operation requires a reason")
        if (self.state
                in TERMINAL_OPERATION_STATES
                and self.terminal_reason
                is None):
            raise ValueError(
                "terminal operation requires a reason")

    def to_dict(self):
        return {
            "attempt_count":
                self.attempt_count,
            "blocked_reason":
                self.blocked_reason,
            "current_step_index":
                self.current_step_index,
            "last_snapshot_id":
                self.last_snapshot_id,
            "last_updated_turn":
                self.last_updated_turn,
            "operation_id":
                self.operation_id,
            "state": self.state.value,
            "terminal_reason":
                self.terminal_reason,
        }

    @classmethod
    def from_dict(cls, value):
        return cls(
            operation_id=value[
                "operation_id"],
            state=OperationState(
                value["state"]),
            current_step_index=value[
                "current_step_index"],
            attempt_count=value[
                "attempt_count"],
            blocked_reason=value.get(
                "blocked_reason"),
            last_snapshot_id=value[
                "last_snapshot_id"],
            last_updated_turn=value[
                "last_updated_turn"],
            terminal_reason=value.get(
                "terminal_reason"))
