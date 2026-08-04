"""Completion-indexed outcome labels for coordinated replacement chains."""

from dataclasses import dataclass, replace
import json
import os
import tempfile

from ..events.schema import canonical_json_bytes, structural_hash
from ..state.snapshot import AuthoritativeSnapshot
from .operation_store import OperationRecord
from .operations import OperationState


REPLACEMENT_CHAIN_OUTCOME_SCHEMA_VERSION = 1
REPLACEMENT_CHAIN_OUTCOME_TARGET = (
    "durable-completed-coordinated-replacement/32-turn/1.0")
_OPERATION_TYPE = "fdas-defense:coordinated-replacement"
_TERMINAL_LABEL_STATUS = "observed"


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


def _city_id(target_ref):
    if not isinstance(target_ref, str) or not target_ref.startswith("city:"):
        raise ValueError("replacement outcome requires city target")
    try:
        value = int(target_ref.split(":", 1)[1])
    except (TypeError, ValueError):
        raise ValueError("replacement outcome city target is invalid")
    if value < 0:
        raise ValueError("replacement outcome city target is invalid")
    return value


def _operation_context(record):
    if not isinstance(record, OperationRecord):
        raise TypeError("replacement outcome requires OperationRecord")
    spec = record.spec
    if spec.operation_type != _OPERATION_TYPE:
        raise ValueError("replacement outcome requires coordinated operation")
    if (len(spec.steps) != 2
            or tuple(value.actor_role for value in spec.steps)
            != ("replacement", "reinforcement")):
        raise ValueError("replacement outcome requires two operation steps")
    participants = dict(
        (value.role, int(value.actor_id)) for value in spec.participants)
    if set(participants) != {"replacement", "reinforcement"}:
        raise ValueError("replacement outcome participants are invalid")
    source_city_id = _city_id(spec.steps[0].target_ref)
    target_city_id = _city_id(spec.target_ref)
    if _city_id(spec.steps[1].target_ref) != target_city_id:
        raise ValueError("replacement outcome step target differs")
    if participants["replacement"] == participants["reinforcement"]:
        raise ValueError("replacement outcome actors must be distinct")
    return {
        "reinforcement_actor_id": participants["reinforcement"],
        "replacement_actor_id": participants["replacement"],
        "source_city_id": source_city_id,
        "target_city_id": target_city_id,
    }


@dataclass(frozen=True)
class FdasReplacementChainOutcomeLabel:
    """One immutable, completion-indexed chain durability observation."""

    schema_version: int
    label_id: str
    operation_id: str
    operation_spec_digest: str
    game_id: str
    player_id: int
    target_id: str
    replacement_actor_id: int
    reinforcement_actor_id: int
    source_city_id: int
    target_city_id: int
    completion_turn: int
    due_turn: int
    completion_snapshot_id: str
    status: str
    observed_turn: object
    observed_revision_id: object
    outcome: object
    observed_value: tuple
    reason: object
    provenance_ids: tuple

    def __post_init__(self):
        if self.schema_version != REPLACEMENT_CHAIN_OUTCOME_SCHEMA_VERSION:
            raise ValueError("unsupported replacement outcome-label schema")
        for value, name in (
                (self.label_id, "label ID"),
                (self.operation_id, "operation ID"),
                (self.operation_spec_digest, "operation spec digest"),
                (self.game_id, "game ID"),
                (self.target_id, "target ID"),
                (self.completion_snapshot_id, "completion snapshot ID")):
            _required_text(value, name)
        if self.target_id != REPLACEMENT_CHAIN_OUTCOME_TARGET:
            raise ValueError("replacement outcome target differs")
        for value, name in (
                (self.player_id, "player ID"),
                (self.replacement_actor_id, "replacement actor ID"),
                (self.reinforcement_actor_id, "reinforcement actor ID"),
                (self.source_city_id, "source city ID"),
                (self.target_city_id, "target city ID"),
                (self.completion_turn, "completion turn"),
                (self.due_turn, "due turn")):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("replacement outcome {} is invalid".format(
                    name))
        if self.due_turn != self.completion_turn + 32:
            raise ValueError("replacement outcome due turn must be +32")
        if self.status not in ("pending", _TERMINAL_LABEL_STATUS):
            raise ValueError("replacement outcome status is invalid")
        object.__setattr__(self, "observed_value", tuple(sorted(
            (str(key), value) for key, value in self.observed_value)))
        provenance = tuple(sorted(str(value) for value in self.provenance_ids))
        if (not provenance or any(not value for value in provenance)
                or len(provenance) != len(set(provenance))):
            raise ValueError("replacement outcome provenance is invalid")
        object.__setattr__(self, "provenance_ids", provenance)
        if self.status == "pending":
            if (self.observed_turn is not None
                    or self.observed_revision_id is not None
                    or self.outcome is not None
                    or self.observed_value
                    or self.reason is not None):
                raise ValueError("pending replacement outcome is terminal")
        else:
            if (isinstance(self.observed_turn, bool)
                    or not isinstance(self.observed_turn, int)
                    or self.observed_turn < self.due_turn):
                raise ValueError("replacement outcome observed turn is invalid")
            _required_text(
                self.observed_revision_id, "observed revision ID")
            if not isinstance(self.outcome, bool) or not self.observed_value:
                raise ValueError("observed replacement outcome lacks value")
            _required_text(self.reason, "outcome reason")
        expected = "replacement-outcome-label-" + structural_hash(
            self.identity_material)[:24]
        if self.label_id != expected:
            raise ValueError("replacement outcome label identity mismatch")

    @property
    def identity_material(self):
        return {
            "completion_snapshot_id": self.completion_snapshot_id,
            "completion_turn": self.completion_turn,
            "due_turn": self.due_turn,
            "game_id": self.game_id,
            "operation_id": self.operation_id,
            "operation_spec_digest": self.operation_spec_digest,
            "player_id": self.player_id,
            "reinforcement_actor_id": self.reinforcement_actor_id,
            "replacement_actor_id": self.replacement_actor_id,
            "schema_version": self.schema_version,
            "source_city_id": self.source_city_id,
            "target_city_id": self.target_city_id,
            "target_id": self.target_id,
        }

    @property
    def state_digest(self):
        return structural_hash(self.to_dict(include_digest=False))

    def to_dict(self, include_digest=True):
        value = dict(self.identity_material)
        value.update({
            "action_selection_changed": False,
            "label_id": self.label_id,
            "observed_revision_id": self.observed_revision_id,
            "observed_turn": self.observed_turn,
            "observed_value": dict(self.observed_value),
            "outcome": self.outcome,
            "policy_authority": False,
            "provenance_ids": list(self.provenance_ids),
            "readout_authority": False,
            "reason": self.reason,
            "status": self.status,
            "transition_value_estimated": False,
            "truth_mutated": False,
        })
        if include_digest:
            value["state_digest"] = self.state_digest
        return value

    @classmethod
    def from_dict(cls, value):
        if any(value.get(name) is not False for name in (
                "action_selection_changed", "policy_authority",
                "readout_authority", "transition_value_estimated",
                "truth_mutated")):
            raise ValueError("replacement outcome label grants authority")
        label = cls(
            value["schema_version"], value["label_id"],
            value["operation_id"], value["operation_spec_digest"],
            value["game_id"], value["player_id"], value["target_id"],
            value["replacement_actor_id"], value["reinforcement_actor_id"],
            value["source_city_id"], value["target_city_id"],
            value["completion_turn"], value["due_turn"],
            value["completion_snapshot_id"], value["status"],
            value.get("observed_turn"), value.get("observed_revision_id"),
            value.get("outcome"),
            tuple(sorted(value.get("observed_value", {}).items())),
            value.get("reason"), tuple(value.get("provenance_ids", ())))
        if (value.get("state_digest") is not None
                and value["state_digest"] != label.state_digest):
            raise ValueError("replacement outcome state digest mismatch")
        return label


class FdasReplacementChainOutcomeStore(object):
    """Atomic, restart-safe labels keyed one-to-one by operation."""

    STORE_IDENTITY = "fdas-replacement-chain-outcome-store/1.0"

    def __init__(self, persistence_identity, labels=(),
                 quarantine_reason=None):
        _required_text(persistence_identity, "outcome store identity")
        if quarantine_reason is not None:
            _required_text(quarantine_reason, "outcome quarantine reason")
        self.persistence_identity = persistence_identity
        self.quarantine_reason = quarantine_reason
        self._labels = {}
        self._operations = {}
        for label in labels:
            self._insert(label)

    @property
    def quarantined(self):
        return self.quarantine_reason is not None

    def _insert(self, label):
        if not isinstance(label, FdasReplacementChainOutcomeLabel):
            raise TypeError("replacement outcome store requires typed labels")
        if (label.label_id in self._labels
                or label.operation_id in self._operations):
            raise ValueError("duplicate replacement outcome label")
        self._labels[label.label_id] = label
        self._operations[label.operation_id] = label.label_id

    def labels(self):
        return tuple(self._labels[key] for key in sorted(self._labels))

    def get(self, label_id):
        return self._labels.get(str(label_id))

    def for_operation(self, operation_id):
        label_id = self._operations.get(str(operation_id))
        return None if label_id is None else self._labels[label_id]

    @property
    def store_digest(self):
        return structural_hash(self.to_dict(include_digest=False))

    def record(self, label):
        if self.quarantined:
            raise ValueError("quarantined replacement outcome store")
        if not isinstance(label, FdasReplacementChainOutcomeLabel):
            raise TypeError("replacement outcome store requires typed labels")
        prior = self._labels.get(label.label_id)
        if prior is None:
            if label.operation_id in self._operations:
                raise ValueError("replacement operation label collision")
            self._insert(label)
            return label
        if prior == label:
            return prior
        if prior.identity_material != label.identity_material:
            raise ValueError("replacement outcome identity collision")
        if prior.status == _TERMINAL_LABEL_STATUS:
            raise ValueError("terminal replacement outcome cannot transition")
        if label.status != _TERMINAL_LABEL_STATUS:
            raise ValueError("replacement outcome cannot return to pending")
        self._labels[label.label_id] = label
        return label

    def to_dict(self, include_digest=True):
        value = {
            "labels": [label.to_dict() for label in self.labels()],
            "persistence_identity": self.persistence_identity,
            "quarantine_reason": self.quarantine_reason,
            "schema_version": REPLACEMENT_CHAIN_OUTCOME_SCHEMA_VERSION,
            "store_identity": self.STORE_IDENTITY,
        }
        if include_digest:
            value["store_digest"] = self.store_digest
        return value

    def save(self, path):
        if self.quarantined:
            raise ValueError("quarantined replacement outcome store")
        path = os.path.abspath(path)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".fdas-replacement-outcomes-", suffix=".json",
            dir=directory or None)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(canonical_json_bytes(self.to_dict()))
                stream.write(b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def load(cls, path, persistence_identity):
        if not os.path.exists(path):
            return cls(persistence_identity)
        try:
            with open(path, "rb") as stream:
                value = json.loads(stream.read().decode("utf-8"))
            if (value.get("store_identity") != cls.STORE_IDENTITY
                    or value.get("schema_version")
                    != REPLACEMENT_CHAIN_OUTCOME_SCHEMA_VERSION
                    or value.get("persistence_identity")
                    != persistence_identity):
                raise ValueError("replacement outcome store identity mismatch")
            store = cls(
                persistence_identity,
                tuple(FdasReplacementChainOutcomeLabel.from_dict(row)
                      for row in value.get("labels", ())),
                value.get("quarantine_reason"))
            if (value.get("store_digest") is not None
                    and value["store_digest"] != store.store_digest):
                raise ValueError("replacement outcome store digest mismatch")
            return store
        except (KeyError, OSError, TypeError, UnicodeError,
                ValueError, json.JSONDecodeError) as error:
            return cls(
                persistence_identity,
                quarantine_reason=(
                    "replacement-outcome-store-load-failed:{}".format(error)))


class FdasReplacementChainOutcomeLabeler(object):
    """Index one durability label only after both chain steps complete."""

    LABELER_IDENTITY = "fdas-replacement-chain-outcome-labeler/1.0"
    TARGET_ID = REPLACEMENT_CHAIN_OUTCOME_TARGET
    OBSERVATION_WINDOW_TURNS = 32

    def __init__(self, store):
        if not isinstance(store, FdasReplacementChainOutcomeStore):
            raise TypeError("replacement outcome labeler requires its store")
        self.store = store

    @staticmethod
    def eligible_record(record):
        try:
            _operation_context(record)
        except (TypeError, ValueError):
            return False
        return bool(
            record.progress.state == OperationState.COMPLETED
            and record.progress.current_step_index
            == len(record.spec.steps) - 1)

    def open(self, record, game_id, player_id):
        if not self.eligible_record(record):
            raise ValueError(
                "replacement outcome requires completed operation")
        _required_text(game_id, "replacement outcome game ID")
        if (isinstance(player_id, bool)
                or not isinstance(player_id, int) or player_id < 0):
            raise ValueError("replacement outcome player ID is invalid")
        context = _operation_context(record)
        material = {
            "completion_snapshot_id": record.progress.last_snapshot_id,
            "completion_turn": record.progress.last_updated_turn,
            "due_turn": (
                record.progress.last_updated_turn
                + self.OBSERVATION_WINDOW_TURNS),
            "game_id": game_id,
            "operation_id": record.spec.operation_id,
            "operation_spec_digest": record.spec.spec_digest,
            "player_id": player_id,
            "reinforcement_actor_id": context["reinforcement_actor_id"],
            "replacement_actor_id": context["replacement_actor_id"],
            "schema_version": REPLACEMENT_CHAIN_OUTCOME_SCHEMA_VERSION,
            "source_city_id": context["source_city_id"],
            "target_city_id": context["target_city_id"],
            "target_id": self.TARGET_ID,
        }
        label = FdasReplacementChainOutcomeLabel(
            REPLACEMENT_CHAIN_OUTCOME_SCHEMA_VERSION,
            "replacement-outcome-label-" + structural_hash(material)[:24],
            record.spec.operation_id, record.spec.spec_digest,
            game_id, player_id, self.TARGET_ID,
            context["replacement_actor_id"],
            context["reinforcement_actor_id"],
            context["source_city_id"], context["target_city_id"],
            record.progress.last_updated_turn,
            record.progress.last_updated_turn + self.OBSERVATION_WINDOW_TURNS,
            record.progress.last_snapshot_id,
            "pending", None, None, None, (), None,
            (
                self.LABELER_IDENTITY,
                "completion-snapshot:" + record.progress.last_snapshot_id,
                "operation-spec:" + record.spec.spec_digest,
            ))
        existing = self.store.for_operation(record.spec.operation_id)
        if existing is not None:
            if existing.identity_material != label.identity_material:
                raise ValueError("replacement outcome operation changed")
            return existing
        return self.store.record(label)

    def observe(self, label_id, snapshot, revision_id):
        if not isinstance(snapshot, AuthoritativeSnapshot):
            raise TypeError("replacement outcome requires snapshot")
        _required_text(revision_id, "replacement outcome revision ID")
        label = self.store.get(label_id)
        if label is None:
            raise KeyError("unknown replacement outcome label")
        if (snapshot.identity.game_id != label.game_id
                or snapshot.player_id != label.player_id):
            raise ValueError("replacement outcome observation identity differs")
        if label.status == _TERMINAL_LABEL_STATUS:
            return label
        if snapshot.turn < label.due_turn:
            return label
        outcome, observed_value, reason = self._assessment(label, snapshot)
        observed = replace(
            label,
            status=_TERMINAL_LABEL_STATUS,
            observed_turn=snapshot.turn,
            observed_revision_id=revision_id,
            outcome=outcome,
            observed_value=tuple(sorted(observed_value.items())),
            reason=reason,
            provenance_ids=tuple(sorted(set(
                label.provenance_ids + (
                    "assessment-revision:" + revision_id,)))))
        return self.store.record(observed)

    @staticmethod
    def _assessment(label, snapshot):
        source = snapshot.city(label.source_city_id)
        target = snapshot.city(label.target_city_id)
        replacement = snapshot.unit(label.replacement_actor_id)
        reinforcement = snapshot.unit(label.reinforcement_actor_id)
        source_owned = bool(
            source is not None and source.owner == snapshot.player_id)
        target_owned = bool(
            target is not None and target.owner == snapshot.player_id)
        replacement_present = replacement is not None
        reinforcement_present = reinforcement is not None
        replacement_at_source = bool(
            source_owned and replacement_present
            and replacement.owner == snapshot.player_id
            and replacement.tile == source.tile)
        reinforcement_at_target = bool(
            target_owned and reinforcement_present
            and reinforcement.owner == snapshot.player_id
            and reinforcement.tile == target.tile)
        replacement_nontransported = bool(
            replacement_present and replacement.transported is not True)
        reinforcement_nontransported = bool(
            reinforcement_present and reinforcement.transported is not True)
        outcome = bool(
            source_owned and target_owned
            and replacement_at_source and reinforcement_at_target
            and replacement_nontransported and reinforcement_nontransported)
        failed = []
        for name, value in (
                ("source-city-owned-and-present", source_owned),
                ("target-city-owned-and-present", target_owned),
                ("replacement-at-source", replacement_at_source),
                ("reinforcement-at-target", reinforcement_at_target),
                ("replacement-nontransported", replacement_nontransported),
                ("reinforcement-nontransported", reinforcement_nontransported)):
            if not value:
                failed.append(name)
        reason = (
            "completed-replacement-chain-durable-at-due-turn"
            if outcome else
            "completed-replacement-chain-not-durable:" + ",".join(failed))
        return outcome, {
            "reinforcement_actor_id": label.reinforcement_actor_id,
            "reinforcement_at_target": reinforcement_at_target,
            "reinforcement_nontransported": reinforcement_nontransported,
            "reinforcement_present": reinforcement_present,
            "replacement_actor_id": label.replacement_actor_id,
            "replacement_at_source": replacement_at_source,
            "replacement_nontransported": replacement_nontransported,
            "replacement_present": replacement_present,
            "source_city_id": label.source_city_id,
            "source_city_owned_and_present": source_owned,
            "target_city_id": label.target_city_id,
            "target_city_owned_and_present": target_owned,
        }, reason
