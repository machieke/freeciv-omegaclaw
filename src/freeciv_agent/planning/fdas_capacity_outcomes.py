"""Shadow-only delayed outcome labels for retained replacement queues."""

from dataclasses import dataclass, replace
import json
import os
import tempfile

from ..events.schema import canonical_json_bytes, structural_hash
from ..state.atomspace.model import AtomNamespace, EntityRef
from ..state.snapshot import AuthoritativeSnapshot


RETAINED_CAPACITY_OUTCOME_SCHEMA_VERSION = 1
RETAINED_CAPACITY_OUTCOME_TARGET = (
    "durable-retained-replacement-capacity-relief/32-turn/1.0")
_LABELER_IDENTITY = "fdas-retained-capacity-outcome-labeler/1.0"
_MECHANISM = "fdas-replacement-capacity-retained-queue-lifecycle"
_OPERATION_TYPE = (
    "fdas-shadow:city-replacement-capacity-deficit:city_production")
_TERMINAL_EVENT_TYPES = frozenset((
    "operation_abandoned", "operation_expired", "operation_failed"))


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


def _nonnegative_integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("{} is invalid".format(name))
    return value


def _unit_id(product_ref):
    if not isinstance(product_ref, str) or not product_ref.startswith("unit:"):
        raise ValueError("retained capacity product identity is invalid")
    try:
        value = int(product_ref.split(":", 1)[1])
    except (TypeError, ValueError):
        raise ValueError("retained capacity product identity is invalid")
    return _nonnegative_integer(value, "retained capacity product unit ID")


def _normal(value):
    return str(value).strip().lower().replace("_", " ")


@dataclass(frozen=True)
class FdasRetainedCapacityOutcomeLabel:
    """One idempotent retained-queue outcome and delayed relief label."""

    schema_version: int
    label_id: str
    operation_id: str
    operation_digest: str
    game_id: str
    player_id: int
    target_id: str
    deficit_atom_id: str
    source_city_id: int
    target_city_id: int
    production_target_name: str
    proposed_turn: int
    proposed_snapshot_id: str
    status: str
    product_ref: object
    product_turn: object
    product_snapshot_id: object
    due_turn: object
    observed_turn: object
    observed_revision_id: object
    outcome: object
    outcome_kind: object
    observed_value: tuple
    reason: object
    provenance_ids: tuple

    def __post_init__(self):
        if self.schema_version != RETAINED_CAPACITY_OUTCOME_SCHEMA_VERSION:
            raise ValueError("unsupported retained capacity outcome schema")
        for value, name in (
                (self.label_id, "retained capacity label ID"),
                (self.operation_id, "retained capacity operation ID"),
                (self.operation_digest, "retained capacity operation digest"),
                (self.game_id, "retained capacity game ID"),
                (self.target_id, "retained capacity target ID"),
                (self.deficit_atom_id, "retained capacity deficit atom ID"),
                (self.production_target_name, "production target name"),
                (self.proposed_snapshot_id, "proposal snapshot ID")):
            _required_text(value, name)
        if self.target_id != RETAINED_CAPACITY_OUTCOME_TARGET:
            raise ValueError("retained capacity outcome target differs")
        for value, name in (
                (self.player_id, "retained capacity player ID"),
                (self.source_city_id, "retained capacity source city ID"),
                (self.target_city_id, "retained capacity target city ID"),
                (self.proposed_turn, "retained capacity proposal turn")):
            _nonnegative_integer(value, name)
        if self.source_city_id == self.target_city_id:
            raise ValueError("retained capacity source and target cities overlap")
        if self.status not in (
                "pending_product", "pending_relief", "observed"):
            raise ValueError("retained capacity outcome status is invalid")
        object.__setattr__(self, "observed_value", tuple(sorted(
            (str(key), value) for key, value in self.observed_value)))
        provenance = tuple(sorted(str(value) for value in self.provenance_ids))
        if (not provenance or any(not value for value in provenance)
                or len(provenance) != len(set(provenance))):
            raise ValueError("retained capacity outcome provenance is invalid")
        object.__setattr__(self, "provenance_ids", provenance)
        product_fields = (
            self.product_ref, self.product_turn,
            self.product_snapshot_id, self.due_turn)
        terminal_fields = (
            self.observed_turn, self.observed_revision_id,
            self.outcome, self.outcome_kind, self.reason)
        if self.status == "pending_product":
            if (any(value is not None for value in product_fields)
                    or any(value is not None for value in terminal_fields)
                    or self.observed_value):
                raise ValueError("pending retained capacity label has outcome")
        elif self.status == "pending_relief":
            _unit_id(self.product_ref)
            _nonnegative_integer(self.product_turn, "product turn")
            _required_text(self.product_snapshot_id, "product snapshot ID")
            _nonnegative_integer(self.due_turn, "relief due turn")
            if self.due_turn != self.product_turn + 32:
                raise ValueError("retained capacity relief due turn must be +32")
            if (any(value is not None for value in terminal_fields)
                    or self.observed_value):
                raise ValueError("pending retained relief is terminal")
        else:
            _nonnegative_integer(self.observed_turn, "outcome observed turn")
            _required_text(self.observed_revision_id, "observed revision ID")
            if not isinstance(self.outcome, bool):
                raise ValueError("retained capacity terminal outcome is invalid")
            if self.outcome_kind not in (
                    "terminal-no-progress", "durable-capacity-relief"):
                raise ValueError("retained capacity outcome kind is invalid")
            _required_text(self.reason, "retained capacity outcome reason")
            if not self.observed_value:
                raise ValueError("retained capacity outcome lacks evidence")
            if self.outcome_kind == "terminal-no-progress":
                if (self.outcome is not False
                        or any(value is not None for value in product_fields)):
                    raise ValueError("terminal no-progress label differs")
            else:
                _unit_id(self.product_ref)
                _nonnegative_integer(self.product_turn, "product turn")
                _required_text(self.product_snapshot_id, "product snapshot ID")
                _nonnegative_integer(self.due_turn, "relief due turn")
                if (self.due_turn != self.product_turn + 32
                        or self.observed_turn < self.due_turn):
                    raise ValueError("durable relief window differs")
        expected = "retained-capacity-outcome-label-" + structural_hash(
            self.identity_material)[:24]
        if self.label_id != expected:
            raise ValueError("retained capacity label identity mismatch")

    @property
    def identity_material(self):
        return {
            "deficit_atom_id": self.deficit_atom_id,
            "game_id": self.game_id,
            "operation_digest": self.operation_digest,
            "operation_id": self.operation_id,
            "player_id": self.player_id,
            "production_target_name": self.production_target_name,
            "proposed_snapshot_id": self.proposed_snapshot_id,
            "proposed_turn": self.proposed_turn,
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
            "induction_readout": False,
            "label_id": self.label_id,
            "observed_revision_id": self.observed_revision_id,
            "observed_turn": self.observed_turn,
            "observed_value": dict(self.observed_value),
            "outcome": self.outcome,
            "outcome_kind": self.outcome_kind,
            "policy_authority": False,
            "product_ref": self.product_ref,
            "product_snapshot_id": self.product_snapshot_id,
            "product_turn": self.product_turn,
            "due_turn": self.due_turn,
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
                "action_selection_changed", "induction_readout",
                "policy_authority", "readout_authority",
                "transition_value_estimated", "truth_mutated")):
            raise ValueError("retained capacity outcome grants authority")
        label = cls(
            value["schema_version"], value["label_id"],
            value["operation_id"], value["operation_digest"],
            value["game_id"], value["player_id"], value["target_id"],
            value["deficit_atom_id"], value["source_city_id"],
            value["target_city_id"], value["production_target_name"],
            value["proposed_turn"], value["proposed_snapshot_id"],
            value["status"], value.get("product_ref"),
            value.get("product_turn"), value.get("product_snapshot_id"),
            value.get("due_turn"), value.get("observed_turn"),
            value.get("observed_revision_id"), value.get("outcome"),
            value.get("outcome_kind"),
            tuple(sorted(value.get("observed_value", {}).items())),
            value.get("reason"), tuple(value.get("provenance_ids", ())))
        if (value.get("state_digest") is not None
                and value["state_digest"] != label.state_digest):
            raise ValueError("retained capacity outcome digest mismatch")
        return label


class FdasRetainedCapacityOutcomeStore(object):
    """Atomic restart-safe outcome labels keyed one-to-one by operation."""

    STORE_IDENTITY = "fdas-retained-capacity-outcome-store/1.0"

    def __init__(self, persistence_identity, labels=(), quarantine_reason=None):
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
        if not isinstance(label, FdasRetainedCapacityOutcomeLabel):
            raise TypeError("retained capacity store requires typed labels")
        if (label.label_id in self._labels
                or label.operation_id in self._operations):
            raise ValueError("duplicate retained capacity outcome label")
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
            raise ValueError("quarantined retained capacity outcome store")
        if not isinstance(label, FdasRetainedCapacityOutcomeLabel):
            raise TypeError("retained capacity store requires typed labels")
        prior = self._labels.get(label.label_id)
        if prior is None:
            if label.operation_id in self._operations:
                raise ValueError("retained capacity operation label collision")
            self._insert(label)
            return label
        if prior == label:
            return prior
        if prior.identity_material != label.identity_material:
            raise ValueError("retained capacity outcome identity collision")
        allowed = {
            "pending_product": frozenset(("pending_relief", "observed")),
            "pending_relief": frozenset(("observed",)),
            "observed": frozenset(),
        }
        if label.status not in allowed[prior.status]:
            raise ValueError("retained capacity outcome transition differs")
        self._labels[label.label_id] = label
        return label

    def to_dict(self, include_digest=True):
        value = {
            "labels": [label.to_dict() for label in self.labels()],
            "persistence_identity": self.persistence_identity,
            "quarantine_reason": self.quarantine_reason,
            "schema_version": RETAINED_CAPACITY_OUTCOME_SCHEMA_VERSION,
            "store_identity": self.STORE_IDENTITY,
        }
        if include_digest:
            value["store_digest"] = self.store_digest
        return value

    def save(self, path):
        if self.quarantined:
            raise ValueError("quarantined retained capacity outcome store")
        path = os.path.abspath(path)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".fdas-retained-capacity-outcomes-", suffix=".json",
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
                    != RETAINED_CAPACITY_OUTCOME_SCHEMA_VERSION
                    or value.get("persistence_identity")
                    != persistence_identity):
                raise ValueError("retained capacity store identity mismatch")
            store = cls(
                persistence_identity,
                tuple(FdasRetainedCapacityOutcomeLabel.from_dict(row)
                      for row in value.get("labels", ())),
                value.get("quarantine_reason"))
            if (value.get("store_digest") is not None
                    and value["store_digest"] != store.store_digest):
                raise ValueError("retained capacity store digest mismatch")
            return store
        except (KeyError, OSError, TypeError, UnicodeError,
                ValueError, json.JSONDecodeError) as error:
            return cls(
                persistence_identity,
                quarantine_reason=(
                    "retained-capacity-outcome-store-load-failed:{}".format(
                        error)))


class FdasRetainedCapacityOutcomeLabeler(object):
    """Separate queue/product observation from durable deficit relief."""

    LABELER_IDENTITY = _LABELER_IDENTITY
    TARGET_ID = RETAINED_CAPACITY_OUTCOME_TARGET
    OBSERVATION_WINDOW_TURNS = 32

    def __init__(self, store):
        if not isinstance(store, FdasRetainedCapacityOutcomeStore):
            raise TypeError("retained capacity labeler requires its store")
        self.store = store

    def open(self, proposal_event, revision, game_id, player_id):
        if not isinstance(proposal_event, dict):
            raise TypeError("retained capacity proposal event is required")
        payload = proposal_event.get("payload", {})
        if (proposal_event.get("type") != "operation_proposed"
                or payload.get("mechanism") != _MECHANISM
                or payload.get("operation_type") != _OPERATION_TYPE
                or payload.get("policy_authority") is not False
                or payload.get("shadow_only") is not True):
            raise ValueError("retained capacity proposal event differs")
        _required_text(game_id, "retained capacity game ID")
        _nonnegative_integer(player_id, "retained capacity player ID")
        snapshot_id = _required_text(
            payload.get("snapshot_id"), "retained capacity snapshot ID")
        if getattr(revision, "snapshot_id", None) != snapshot_id:
            raise ValueError("retained capacity proposal revision is stale")
        downstream = _required_text(
            payload.get("downstream_operation_id"),
            "retained capacity downstream operation")
        prefix = "fdas-replacement-capacity:"
        if not downstream.startswith(prefix):
            raise ValueError("retained capacity downstream identity differs")
        deficit_atom_id = downstream[len(prefix):]
        deficit = revision.record(deficit_atom_id)
        if (deficit is None
                or deficit.key.namespace != AtomNamespace.DERIVED
                or deficit.key.predicate != (
                    "city-replacement-capacity-deficit")
                or len(deficit.key.arguments) != 2
                or any(not isinstance(value, EntityRef)
                       or value.kind != "city"
                       for value in deficit.key.arguments)):
            raise ValueError("retained capacity deficit atom is unavailable")
        source_city_id, target_city_id = tuple(
            int(value.entity_id) for value in deficit.key.arguments)
        next_action = payload.get("next_action")
        target = (
            next_action.get("target")
            if isinstance(next_action, dict) else None)
        production_name = (
            target.get("production_type")
            if isinstance(target, dict) else None)
        material = {
            "deficit_atom_id": deficit_atom_id,
            "game_id": game_id,
            "operation_digest": _required_text(
                payload.get("operation_digest"), "operation digest"),
            "operation_id": _required_text(
                payload.get("operation_id"), "operation ID"),
            "player_id": player_id,
            "production_target_name": _required_text(
                production_name, "production target name"),
            "proposed_snapshot_id": snapshot_id,
            "proposed_turn": _nonnegative_integer(
                proposal_event.get("turn"), "proposal turn"),
            "schema_version": RETAINED_CAPACITY_OUTCOME_SCHEMA_VERSION,
            "source_city_id": source_city_id,
            "target_city_id": target_city_id,
            "target_id": self.TARGET_ID,
        }
        label = FdasRetainedCapacityOutcomeLabel(
            RETAINED_CAPACITY_OUTCOME_SCHEMA_VERSION,
            "retained-capacity-outcome-label-" + structural_hash(material)[:24],
            material["operation_id"], material["operation_digest"], game_id,
            player_id, self.TARGET_ID, deficit_atom_id, source_city_id,
            target_city_id, production_name, material["proposed_turn"],
            snapshot_id, "pending_product", None, None, None, None,
            None, None, None, None, (), None,
            (
                self.LABELER_IDENTITY,
                "deficit-atom:" + deficit_atom_id,
                "proposal-event:" + _required_text(
                    proposal_event.get("event_id"), "proposal event ID"),
                "proposal-revision:" + _required_text(
                    getattr(revision, "revision_id", None),
                    "proposal revision ID"),
            ))
        existing = self.store.for_operation(label.operation_id)
        if existing is not None:
            if existing.identity_material != label.identity_material:
                raise ValueError("retained capacity operation identity changed")
            return existing
        return self.store.record(label)

    def observe_lifecycle_event(self, event, snapshot, revision_id):
        if not isinstance(snapshot, AuthoritativeSnapshot):
            raise TypeError("retained capacity outcome requires snapshot")
        _required_text(revision_id, "retained capacity revision ID")
        if not isinstance(event, dict):
            raise TypeError("retained capacity lifecycle event is required")
        payload = event.get("payload", {})
        if payload.get("mechanism") != _MECHANISM:
            raise ValueError("retained capacity lifecycle mechanism differs")
        label = self.store.for_operation(payload.get("operation_id"))
        if label is None:
            raise KeyError("retained capacity lifecycle lacks label")
        if label.status != "pending_product":
            return label
        event_type = event.get("type")
        provenance = tuple(sorted(set(label.provenance_ids + (
            "lifecycle-event:" + _required_text(
                event.get("event_id"), "lifecycle event ID"),
            "lifecycle-revision:" + revision_id,
        ))))
        if event_type == "operation_completed":
            if payload.get("resolution_status") != "resolved_success":
                raise ValueError("retained capacity product resolution differs")
            product_ref = _required_text(
                payload.get("product_ref"), "retained capacity product")
            _unit_id(product_ref)
            observed = replace(
                label, status="pending_relief", product_ref=product_ref,
                product_turn=_nonnegative_integer(event.get("turn"),
                                                  "product turn"),
                product_snapshot_id=_required_text(
                    payload.get("resolution_snapshot_id"),
                    "product resolution snapshot"),
                due_turn=int(event["turn"]) + self.OBSERVATION_WINDOW_TURNS,
                provenance_ids=provenance)
            return self.store.record(observed)
        if event_type not in _TERMINAL_EVENT_TYPES:
            raise ValueError("retained capacity terminal event differs")
        reason = _required_text(
            payload.get("reason_code"), "terminal no-progress reason")
        observed = replace(
            label, status="observed",
            observed_turn=_nonnegative_integer(event.get("turn"),
                                               "terminal turn"),
            observed_revision_id=revision_id, outcome=False,
            outcome_kind="terminal-no-progress",
            observed_value=tuple(sorted({
                "event_type": event_type,
                "reason_code": reason,
            }.items())),
            reason="retained-capacity-terminal-no-progress:" + reason,
            provenance_ids=provenance)
        return self.store.record(observed)

    def observe_due_relief(self, label_id, snapshot, revision):
        if not isinstance(snapshot, AuthoritativeSnapshot):
            raise TypeError("retained capacity relief requires snapshot")
        label = self.store.get(label_id)
        if label is None:
            raise KeyError("unknown retained capacity outcome label")
        if label.status == "observed" or label.status == "pending_product":
            return label
        if (getattr(revision, "snapshot_id", None) != snapshot.snapshot_id
                or not isinstance(getattr(revision, "revision_id", None), str)):
            raise ValueError("retained capacity relief revision is stale")
        if snapshot.turn < label.due_turn:
            return label
        source = snapshot.city(label.source_city_id)
        target = snapshot.city(label.target_city_id)
        product = snapshot.unit(_unit_id(label.product_ref))
        source_owned = bool(
            source is not None and source.owner == snapshot.player_id)
        target_owned = bool(
            target is not None and target.owner == snapshot.player_id)
        product_present = product is not None
        product_owned = bool(
            product is not None and product.owner == snapshot.player_id)
        product_at_source = bool(
            product is not None and source is not None
            and product.tile is not None and product.tile == source.tile)
        product_type_matches = bool(
            product is not None
            and _normal(product.unit_type) == _normal(
                label.production_target_name))
        deficit_absent = revision.record(label.deficit_atom_id) is None
        values = {
            "deficit_absent": deficit_absent,
            "product_at_source": product_at_source,
            "product_owned": product_owned,
            "product_present": product_present,
            "product_type_matches": product_type_matches,
            "source_city_owned_and_present": source_owned,
            "target_city_owned_and_present": target_owned,
        }
        outcome = all(values.values())
        failed = tuple(sorted(
            key.replace("_", "-") for key, value in values.items()
            if not value))
        reason = (
            "retained-capacity-relief-durable-at-due-turn"
            if outcome else
            "retained-capacity-relief-not-durable:" + ",".join(failed))
        observed = replace(
            label, status="observed", observed_turn=snapshot.turn,
            observed_revision_id=revision.revision_id, outcome=outcome,
            outcome_kind="durable-capacity-relief",
            observed_value=tuple(sorted(values.items())), reason=reason,
            provenance_ids=tuple(sorted(set(label.provenance_ids + (
                "relief-assessment-revision:" + revision.revision_id,)))))
        return self.store.record(observed)
