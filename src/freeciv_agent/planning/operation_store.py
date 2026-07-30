"""Deterministic, versioned progress storage for explicit operations."""

from dataclasses import dataclass
import json
import os
import tempfile

from ..events.schema import (
    canonical_json_bytes,
    structural_hash,
)
from .operations import (
    OperationProgress,
    OperationSpec,
    OperationState,
    TERMINAL_OPERATION_STATES,
    operation_transition_allowed,
)


OPERATION_STORE_SCHEMA_VERSION = 1


class OperationStoreError(RuntimeError):
    pass


class OperationTransitionError(
        OperationStoreError):
    pass


@dataclass(frozen=True)
class OperationRecord:
    spec: OperationSpec
    progress: OperationProgress

    def __post_init__(self):
        if (self.spec.operation_id
                != self.progress
                .operation_id):
            raise ValueError(
                "operation spec/progress identity mismatch")
        if (self.progress
                .current_step_index
                >= len(self.spec.steps)
                and self.progress.state
                not in
                TERMINAL_OPERATION_STATES):
            raise ValueError(
                "non-terminal progress points beyond operation steps")

    def to_dict(self):
        return {
            "progress":
                self.progress.to_dict(),
            "spec": self.spec.to_dict(),
        }

    @classmethod
    def from_dict(cls, value):
        return cls(
            spec=OperationSpec.from_dict(
                value["spec"]),
            progress=OperationProgress
            .from_dict(
                value["progress"]))


class OperationStore:
    """Mutable progress over immutable operation specifications.

    A failed restart load never guesses at partially valid content.  The
    original file is left untouched and the returned store is quarantined
    until an operator explicitly replaces or repairs it.
    """

    STORE_IDENTITY = (
        "freeciv-operation-store/1.0")

    def __init__(
            self, persistence_identity,
            records=(),
            quarantine_reason=None):
        if (not isinstance(
                persistence_identity,
                str)
                or not persistence_identity):
            raise ValueError(
                "operation store persistence identity is required")
        if (quarantine_reason is not None
                and (
                    not isinstance(
                        quarantine_reason,
                        str)
                    or not quarantine_reason)):
            raise ValueError(
                "quarantine reason must be null or non-empty")
        self.persistence_identity = (
            persistence_identity)
        self.quarantine_reason = (
            quarantine_reason)
        self._records = {}
        for record in tuple(records):
            if not isinstance(
                    record,
                    OperationRecord):
                raise TypeError(
                    "operation records must be OperationRecord values")
            operation_id = (
                record.spec.operation_id)
            if operation_id in (
                    self._records):
                raise ValueError(
                    "duplicate operation record")
            self._records[
                operation_id] = record

    @property
    def quarantined(self):
        return self.quarantine_reason is not None

    @property
    def store_digest(self):
        return structural_hash(
            self.to_dict(
                include_digest=False))

    def _writable(self):
        if self.quarantined:
            raise OperationStoreError(
                "operation store is quarantined: {}".format(
                    self.quarantine_reason))

    def records(self):
        return tuple(
            self._records[key]
            for key in sorted(
                self._records))

    def get(self, operation_id):
        return self._records.get(
            operation_id)

    def nonterminal_records(self):
        return tuple(
            record
            for record in self.records()
            if record.progress.state
            not in
            TERMINAL_OPERATION_STATES)

    def propose(
            self, spec, snapshot_id,
            turn):
        self._writable()
        if not isinstance(
                spec, OperationSpec):
            raise TypeError(
                "spec must be an OperationSpec")
        existing = self._records.get(
            spec.operation_id)
        if existing is not None:
            if (existing.spec.spec_digest
                    != spec.spec_digest):
                raise OperationStoreError(
                    "operation identity collision")
            return existing
        progress = OperationProgress(
            operation_id=(
                spec.operation_id),
            state=OperationState.PROPOSED,
            current_step_index=0,
            attempt_count=0,
            blocked_reason=None,
            last_snapshot_id=(
                snapshot_id),
            last_updated_turn=int(
                turn))
        record = OperationRecord(
            spec, progress)
        self._records[
            spec.operation_id] = record
        return record

    def transition(
            self, operation_id,
            target_state, snapshot_id,
            turn, reason=None,
            expected_snapshot_id=None):
        self._writable()
        record = self._records.get(
            operation_id)
        if record is None:
            raise OperationStoreError(
                "unknown operation")
        progress = record.progress
        target_state = OperationState(
            target_state)
        if (expected_snapshot_id
                is not None
                and progress
                .last_snapshot_id
                != expected_snapshot_id):
            raise OperationTransitionError(
                "stale operation progress")
        if target_state == (
                progress.state):
            if (progress.last_snapshot_id
                    == snapshot_id
                    and progress
                    .last_updated_turn
                    == int(turn)):
                return record
            raise OperationTransitionError(
                "same-state transition requires an identical observation")
        if not operation_transition_allowed(
                progress.state,
                target_state):
            raise OperationTransitionError(
                "invalid operation transition {} -> {}".format(
                    progress.state.value,
                    target_state.value))
        if (target_state
                in (
                    OperationState.BLOCKED,)
                and (
                    not isinstance(
                        reason, str)
                    or not reason)):
            raise OperationTransitionError(
                "blocked transition requires a reason")
        if (target_state
                in TERMINAL_OPERATION_STATES
                and (
                    not isinstance(
                        reason, str)
                    or not reason)):
            raise OperationTransitionError(
                "terminal transition requires a reason")
        updated = OperationProgress(
            operation_id=operation_id,
            state=target_state,
            current_step_index=(
                progress
                .current_step_index),
            attempt_count=(
                progress.attempt_count),
            blocked_reason=(
                reason
                if target_state
                == OperationState.BLOCKED
                else None),
            last_snapshot_id=(
                snapshot_id),
            last_updated_turn=int(
                turn),
            terminal_reason=(
                reason
                if target_state
                in TERMINAL_OPERATION_STATES
                else None))
        result = OperationRecord(
            record.spec, updated)
        self._records[
            operation_id] = result
        return result

    def record_attempt(
            self, operation_id,
            snapshot_id, turn):
        self._writable()
        record = self._records.get(
            operation_id)
        if record is None:
            raise OperationStoreError(
                "unknown operation")
        if record.progress.state != (
                OperationState.ACTIVE):
            raise OperationTransitionError(
                "only active operations can record attempts")
        step = record.spec.steps[
            record.progress
            .current_step_index]
        attempt_count = (
            record.progress
            .attempt_count + 1)
        if attempt_count > (
                step.maximum_attempts):
            raise OperationTransitionError(
                "operation step attempt limit exceeded")
        progress = OperationProgress(
            operation_id=operation_id,
            state=(
                record.progress.state),
            current_step_index=(
                record.progress
                .current_step_index),
            attempt_count=(
                attempt_count),
            blocked_reason=None,
            last_snapshot_id=(
                snapshot_id),
            last_updated_turn=int(
                turn))
        result = OperationRecord(
            record.spec, progress)
        self._records[
            operation_id] = result
        return result

    def advance_step(
            self, operation_id,
            snapshot_id, turn):
        self._writable()
        record = self._records.get(
            operation_id)
        if record is None:
            raise OperationStoreError(
                "unknown operation")
        if record.progress.state != (
                OperationState.ACTIVE):
            raise OperationTransitionError(
                "only active operations can advance")
        next_index = (
            record.progress
            .current_step_index + 1)
        if next_index >= len(
                record.spec.steps):
            return self.transition(
                operation_id,
                OperationState.COMPLETED,
                snapshot_id, turn,
                reason=(
                    "all-steps-completed"))
        progress = OperationProgress(
            operation_id=operation_id,
            state=OperationState.ACTIVE,
            current_step_index=(
                next_index),
            attempt_count=0,
            blocked_reason=None,
            last_snapshot_id=(
                snapshot_id),
            last_updated_turn=int(
                turn))
        result = OperationRecord(
            record.spec, progress)
        self._records[
            operation_id] = result
        return result

    def expire_due(self, turn, snapshot_id):
        expired = []
        for record in (
                self.nonterminal_records()):
            if int(turn) <= (
                    record.spec.expiry_turn):
                continue
            expired.append(
                self.transition(
                    record.spec.operation_id,
                    OperationState.EXPIRED,
                    snapshot_id, turn,
                    reason=(
                        "operation-deadline-passed")))
        return tuple(expired)

    def to_dict(
            self, include_digest=True):
        payload = {
            "persistence_identity":
                self.persistence_identity,
            "quarantine_reason":
                self.quarantine_reason,
            "records": [
                record.to_dict()
                for record in
                self.records()],
            "schema_version":
                OPERATION_STORE_SCHEMA_VERSION,
            "store_identity":
                self.STORE_IDENTITY,
        }
        if include_digest:
            payload["store_digest"] = (
                self.store_digest)
        return payload

    def save(self, path):
        self._writable()
        path = os.path.abspath(
            path)
        directory = os.path.dirname(
            path)
        if directory:
            os.makedirs(
                directory,
                exist_ok=True)
        descriptor, temporary = (
            tempfile.mkstemp(
                prefix=".operations-",
                suffix=".json",
                dir=directory or None))
        try:
            with os.fdopen(
                    descriptor, "wb") as stream:
                stream.write(
                    canonical_json_bytes(
                        self.to_dict()))
                stream.write(b"\n")
                stream.flush()
                os.fsync(
                    stream.fileno())
            os.replace(
                temporary, path)
        finally:
            if os.path.exists(
                    temporary):
                os.unlink(
                    temporary)

    @classmethod
    def _from_dict(
            cls, value,
            expected_identity):
        if value.get(
                "schema_version") != (
                OPERATION_STORE_SCHEMA_VERSION):
            raise ValueError(
                "unsupported operation store schema")
        if value.get(
                "store_identity") != (
                cls.STORE_IDENTITY):
            raise ValueError(
                "operation store identity mismatch")
        if value.get(
                "persistence_identity") != (
                expected_identity):
            raise ValueError(
                "operation persistence identity mismatch")
        store = cls(
            expected_identity,
            records=tuple(
                OperationRecord
                .from_dict(row)
                for row in
                value.get(
                    "records", ())),
            quarantine_reason=value.get(
                "quarantine_reason"))
        digest = value.get(
            "store_digest")
        if (not isinstance(digest, str)
                or digest
                != store.store_digest):
            raise ValueError(
                "operation store digest mismatch")
        return store

    @classmethod
    def load(
            cls, path,
            expected_identity):
        path = os.path.abspath(
            path)
        if not os.path.exists(path):
            return cls(
                expected_identity)
        try:
            with open(
                    path,
                    encoding="utf-8") as stream:
                value = json.load(
                    stream)
            if not isinstance(
                    value, dict):
                raise ValueError(
                    "operation store root is not an object")
            return cls._from_dict(
                value,
                expected_identity)
        except (
                OSError, TypeError,
                ValueError,
                KeyError,
                json.JSONDecodeError) as error:
            return cls(
                expected_identity,
                quarantine_reason=(
                    "load-failed:{}"
                    .format(
                        type(error)
                        .__name__)))
