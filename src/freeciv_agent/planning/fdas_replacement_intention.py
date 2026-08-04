"""Paired, intention-indexed outcomes for coordinated replacement chains."""

from dataclasses import dataclass, replace
import json
import os
import tempfile

from ..events.schema import canonical_json_bytes, structural_hash
from ..state.atomspace.grounding import persistent_defender_type
from .fdas_replacement import FdasCoordinatedReplacementAdapter
from .fdas_replacement_readout import FdasCoordinatedReplacementReadout


REPLACEMENT_INTENTION_SCHEMA_VERSION = 1
REPLACEMENT_INTENTION_TREATMENT_ID = (
    "fdas-coordinated-replacement-intention-paired-pilot/1.0")
REPLACEMENT_INTENTION_ASSIGNMENT_UNIT = (
    "game-first-grounded-coordinated-replacement-chain-intention/1.0")
REPLACEMENT_INTENTION_OUTCOME_TARGET = (
    "first-grounded-coordinated-replacement/32-turn/vector/1.0")


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


def _nonnegative(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("{} is invalid".format(name))
    return value


@dataclass(frozen=True)
class FdasReplacementIntentionOutcome:
    status: str
    observed_turn: object
    observed_snapshot_id: object
    source_city_retained: object
    target_city_retained: object
    source_persistent_defender_count: object
    target_persistent_defender_count: object
    replacement_present: object
    replacement_at_source: object
    replacement_nontransported: object
    reinforcement_present: object
    reinforcement_at_target: object
    reinforcement_nontransported: object
    operation_state: object
    reason: str

    def __post_init__(self):
        if self.status not in ("observed", "censored"):
            raise ValueError("replacement intention outcome status differs")
        _required_text(self.reason, "replacement intention outcome reason")
        if self.status == "censored":
            if any(value is not None for value in (
                    self.observed_turn, self.observed_snapshot_id,
                    self.source_city_retained, self.target_city_retained,
                    self.source_persistent_defender_count,
                    self.target_persistent_defender_count,
                    self.replacement_present, self.replacement_at_source,
                    self.replacement_nontransported,
                    self.reinforcement_present,
                    self.reinforcement_at_target,
                    self.reinforcement_nontransported,
                    self.operation_state)):
                raise ValueError("censored replacement outcome invented value")
            return
        _nonnegative(self.observed_turn, "replacement observation turn")
        _required_text(
            self.observed_snapshot_id, "replacement observation snapshot")
        for value in (
                self.source_city_retained, self.target_city_retained,
                self.replacement_present, self.replacement_at_source,
                self.replacement_nontransported,
                self.reinforcement_present, self.reinforcement_at_target,
                self.reinforcement_nontransported):
            if not isinstance(value, bool):
                raise TypeError("replacement intention Boolean is invalid")
        _nonnegative(
            self.source_persistent_defender_count,
            "source persistent-defender count")
        _nonnegative(
            self.target_persistent_defender_count,
            "target persistent-defender count")
        _required_text(self.operation_state, "replacement operation state")

    @property
    def city_retention_count(self):
        if self.status != "observed":
            return None
        return int(self.source_city_retained) + int(self.target_city_retained)

    @property
    def defended_city_count(self):
        if self.status != "observed":
            return None
        return int(self.source_persistent_defender_count > 0) + int(
            self.target_persistent_defender_count > 0)

    @property
    def assigned_actor_survival_count(self):
        if self.status != "observed":
            return None
        return int(self.replacement_present) + int(self.reinforcement_present)

    def to_dict(self):
        return {
            "assigned_actor_survival_count": (
                self.assigned_actor_survival_count),
            "city_retention_count": self.city_retention_count,
            "defended_city_count": self.defended_city_count,
            "observed_snapshot_id": self.observed_snapshot_id,
            "observed_turn": self.observed_turn,
            "operation_state": self.operation_state,
            "reason": self.reason,
            "reinforcement_at_target": self.reinforcement_at_target,
            "reinforcement_nontransported": (
                self.reinforcement_nontransported),
            "reinforcement_present": self.reinforcement_present,
            "replacement_at_source": self.replacement_at_source,
            "replacement_nontransported": self.replacement_nontransported,
            "replacement_present": self.replacement_present,
            "source_city_retained": self.source_city_retained,
            "source_persistent_defender_count": (
                self.source_persistent_defender_count),
            "status": self.status,
            "target_city_retained": self.target_city_retained,
            "target_persistent_defender_count": (
                self.target_persistent_defender_count),
        }

    @classmethod
    def from_dict(cls, value):
        return cls(
            value["status"], value.get("observed_turn"),
            value.get("observed_snapshot_id"),
            value.get("source_city_retained"),
            value.get("target_city_retained"),
            value.get("source_persistent_defender_count"),
            value.get("target_persistent_defender_count"),
            value.get("replacement_present"),
            value.get("replacement_at_source"),
            value.get("replacement_nontransported"),
            value.get("reinforcement_present"),
            value.get("reinforcement_at_target"),
            value.get("reinforcement_nontransported"),
            value.get("operation_state"), value["reason"])


@dataclass(frozen=True)
class FdasReplacementIntentionAssignment:
    schema_version: int
    assignment_id: str
    treatment_id: str
    assignment_unit: str
    experiment_id: str
    assigned_arm: str
    game_id: str
    player_id: int
    operation_id: str
    operation_spec_digest: str
    replacement_actor_id: int
    reinforcement_actor_id: int
    source_city_id: int
    target_city_id: int
    assignment_turn: int
    assignment_snapshot_id: str
    due_turn: int
    outcome: object

    def __post_init__(self):
        if self.schema_version != REPLACEMENT_INTENTION_SCHEMA_VERSION:
            raise ValueError("unsupported replacement intention schema")
        if self.treatment_id != REPLACEMENT_INTENTION_TREATMENT_ID:
            raise ValueError("replacement intention treatment differs")
        if self.assignment_unit != REPLACEMENT_INTENTION_ASSIGNMENT_UNIT:
            raise ValueError("replacement intention assignment unit differs")
        if self.assigned_arm not in ("control", "treatment"):
            raise ValueError("replacement intention arm differs")
        for value, name in (
                (self.assignment_id, "replacement intention assignment ID"),
                (self.experiment_id, "replacement intention experiment ID"),
                (self.game_id, "replacement intention game ID"),
                (self.operation_id, "replacement intention operation ID"),
                (self.operation_spec_digest,
                 "replacement intention operation digest"),
                (self.assignment_snapshot_id,
                 "replacement intention assignment snapshot")):
            _required_text(value, name)
        for value, name in (
                (self.player_id, "replacement intention player"),
                (self.replacement_actor_id, "replacement actor"),
                (self.reinforcement_actor_id, "reinforcement actor"),
                (self.source_city_id, "replacement source city"),
                (self.target_city_id, "replacement target city"),
                (self.assignment_turn, "replacement assignment turn"),
                (self.due_turn, "replacement intention due turn")):
            _nonnegative(value, name)
        if self.due_turn != self.assignment_turn + 32:
            raise ValueError("replacement intention due turn must be +32")
        if self.outcome is not None and not isinstance(
                self.outcome, FdasReplacementIntentionOutcome):
            raise TypeError("replacement intention outcome is untyped")
        expected = "replacement-intention-assignment-" + structural_hash(
            self.identity_material)[:24]
        if self.assignment_id != expected:
            raise ValueError("replacement intention assignment identity differs")

    @property
    def logical_pair(self):
        return (
            self.replacement_actor_id, self.reinforcement_actor_id,
            self.source_city_id, self.target_city_id)

    @property
    def identity_material(self):
        return {
            "assigned_arm": self.assigned_arm,
            "assignment_snapshot_id": self.assignment_snapshot_id,
            "assignment_turn": self.assignment_turn,
            "assignment_unit": self.assignment_unit,
            "due_turn": self.due_turn,
            "experiment_id": self.experiment_id,
            "game_id": self.game_id,
            "operation_id": self.operation_id,
            "operation_spec_digest": self.operation_spec_digest,
            "player_id": self.player_id,
            "reinforcement_actor_id": self.reinforcement_actor_id,
            "replacement_actor_id": self.replacement_actor_id,
            "schema_version": self.schema_version,
            "source_city_id": self.source_city_id,
            "target_city_id": self.target_city_id,
            "treatment_id": self.treatment_id,
        }

    @property
    def state_digest(self):
        return structural_hash(self.to_dict(include_digest=False))

    def to_dict(self, include_digest=True):
        value = dict(self.identity_material)
        value.update({
            "assignment_id": self.assignment_id,
            "claim_eligible": False,
            "outcome": None if self.outcome is None else self.outcome.to_dict(),
            "outcome_target": REPLACEMENT_INTENTION_OUTCOME_TARGET,
            "truth_mutated": False,
        })
        if include_digest:
            value["state_digest"] = self.state_digest
        return value

    @classmethod
    def from_dict(cls, value):
        if (value.get("claim_eligible") is not False
                or value.get("truth_mutated") is not False
                or value.get("outcome_target")
                != REPLACEMENT_INTENTION_OUTCOME_TARGET):
            raise ValueError("replacement intention boundary differs")
        outcome = value.get("outcome")
        assignment = cls(
            value["schema_version"], value["assignment_id"],
            value["treatment_id"], value["assignment_unit"],
            value["experiment_id"], value["assigned_arm"], value["game_id"],
            value["player_id"], value["operation_id"],
            value["operation_spec_digest"], value["replacement_actor_id"],
            value["reinforcement_actor_id"], value["source_city_id"],
            value["target_city_id"], value["assignment_turn"],
            value["assignment_snapshot_id"], value["due_turn"],
            None if outcome is None else
            FdasReplacementIntentionOutcome.from_dict(outcome))
        if (value.get("state_digest") is not None
                and value["state_digest"] != assignment.state_digest):
            raise ValueError("replacement intention state digest differs")
        return assignment


class FdasReplacementIntentionStore(object):
    """Atomic one-assignment intention/outcome store."""

    STORE_IDENTITY = "fdas-replacement-intention-store/1.0"

    def __init__(self, persistence_identity, assignment=None,
                 quarantine_reason=None):
        _required_text(persistence_identity, "intention store identity")
        if assignment is not None and not isinstance(
                assignment, FdasReplacementIntentionAssignment):
            raise TypeError("replacement intention assignment is untyped")
        if quarantine_reason is not None:
            _required_text(quarantine_reason, "intention quarantine reason")
        self.persistence_identity = persistence_identity
        self.assignment = assignment
        self.quarantine_reason = quarantine_reason

    @property
    def quarantined(self):
        return self.quarantine_reason is not None

    @property
    def store_digest(self):
        return structural_hash(self.to_dict(include_digest=False))

    def record(self, assignment):
        if self.quarantined:
            raise ValueError("quarantined replacement intention store")
        if not isinstance(assignment, FdasReplacementIntentionAssignment):
            raise TypeError("replacement intention assignment is untyped")
        if self.assignment is None:
            self.assignment = assignment
            return assignment
        if (self.assignment.assignment_id != assignment.assignment_id
                or self.assignment.identity_material
                != assignment.identity_material):
            raise ValueError("replacement intention cannot reassign a game")
        if self.assignment.outcome is not None and self.assignment != assignment:
            raise ValueError("replacement intention outcome is immutable")
        self.assignment = assignment
        return assignment

    def to_dict(self, include_digest=True):
        value = {
            "assignment": (
                None if self.assignment is None else self.assignment.to_dict()),
            "persistence_identity": self.persistence_identity,
            "quarantine_reason": self.quarantine_reason,
            "schema_version": REPLACEMENT_INTENTION_SCHEMA_VERSION,
            "store_identity": self.STORE_IDENTITY,
        }
        if include_digest:
            value["store_digest"] = self.store_digest
        return value

    def save(self, path):
        if self.quarantined:
            raise ValueError("quarantined replacement intention store")
        path = os.path.abspath(path)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".fdas-replacement-intention-", suffix=".json",
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
                    != REPLACEMENT_INTENTION_SCHEMA_VERSION
                    or value.get("persistence_identity")
                    != persistence_identity):
                raise ValueError("replacement intention store identity differs")
            assignment = value.get("assignment")
            store = cls(
                persistence_identity,
                None if assignment is None else
                FdasReplacementIntentionAssignment.from_dict(assignment),
                value.get("quarantine_reason"))
            if (value.get("store_digest") is not None
                    and value["store_digest"] != store.store_digest):
                raise ValueError("replacement intention store digest differs")
            return store
        except (KeyError, OSError, TypeError, UnicodeError, ValueError,
                json.JSONDecodeError) as error:
            return cls(persistence_identity, quarantine_reason=(
                "replacement-intention-store-load-failed:{}".format(error)))


class FdasReplacementIntentionTracker(object):
    """Bind one opportunity and observe both paired arms identically."""

    def __init__(self, adapter, store, assigned_arm, experiment_id,
                 game_id, player_id, ruleset_ir=None):
        if not isinstance(adapter, FdasCoordinatedReplacementAdapter):
            raise TypeError("replacement intention tracker requires adapter")
        if not isinstance(store, FdasReplacementIntentionStore):
            raise TypeError("replacement intention tracker requires store")
        if assigned_arm not in ("control", "treatment"):
            raise ValueError("replacement intention tracker arm differs")
        _required_text(experiment_id, "replacement intention experiment")
        _required_text(game_id, "replacement intention game")
        _nonnegative(player_id, "replacement intention player")
        self.adapter = adapter
        self.store = store
        self.assigned_arm = assigned_arm
        self.experiment_id = experiment_id
        self.game_id = game_id
        self.player_id = player_id
        self.ruleset_ir = ruleset_ir

    def _new_assignment(self, pair, snapshot):
        record = self.adapter.store.get(pair.lifecycle_operation_id)
        if record is None:
            raise ValueError("replacement intention lifecycle is unavailable")
        values = {
            "assigned_arm": self.assigned_arm,
            "assignment_snapshot_id": snapshot.snapshot_id,
            "assignment_turn": int(snapshot.turn),
            "assignment_unit": REPLACEMENT_INTENTION_ASSIGNMENT_UNIT,
            "due_turn": int(snapshot.turn) + 32,
            "experiment_id": self.experiment_id,
            "game_id": self.game_id,
            "operation_id": record.spec.operation_id,
            "operation_spec_digest": record.spec.spec_digest,
            "player_id": self.player_id,
            "reinforcement_actor_id": pair.reinforcement_actor_id,
            "replacement_actor_id": pair.replacement_actor_id,
            "schema_version": REPLACEMENT_INTENTION_SCHEMA_VERSION,
            "source_city_id": pair.source_city_id,
            "target_city_id": pair.target_city_id,
            "treatment_id": REPLACEMENT_INTENTION_TREATMENT_ID,
        }
        return FdasReplacementIntentionAssignment(
            assignment_id="replacement-intention-assignment-" +
            structural_hash(values)[:24], outcome=None, **values)

    def _observe(self, assignment, snapshot):
        source = snapshot.city(assignment.source_city_id)
        target = snapshot.city(assignment.target_city_id)
        replacement = snapshot.unit(assignment.replacement_actor_id)
        reinforcement = snapshot.unit(assignment.reinforcement_actor_id)
        source_retained = bool(
            source is not None and source.owner == snapshot.player_id)
        target_retained = bool(
            target is not None and target.owner == snapshot.player_id)

        def defenders(city, retained):
            if not retained or city.tile is None:
                return 0
            return sum(
                unit.owner == snapshot.player_id
                and unit.tile == city.tile
                and persistent_defender_type(
                    self.ruleset_ir, unit.unit_type)
                for unit in snapshot.units)

        record = self.adapter.store.get(assignment.operation_id)
        outcome = FdasReplacementIntentionOutcome(
            "observed", int(snapshot.turn), snapshot.snapshot_id,
            source_retained, target_retained,
            defenders(source, source_retained),
            defenders(target, target_retained),
            replacement is not None,
            bool(source_retained and replacement is not None
                 and replacement.owner == snapshot.player_id
                 and replacement.tile == source.tile),
            bool(replacement is not None and replacement.transported is not True),
            reinforcement is not None,
            bool(target_retained and reinforcement is not None
                 and reinforcement.owner == snapshot.player_id
                 and reinforcement.tile == target.tile),
            bool(reinforcement is not None
                 and reinforcement.transported is not True),
            "unavailable" if record is None else record.progress.state.value,
            "assignment-window-observed")
        return self.store.record(replace(assignment, outcome=outcome))

    def evaluate(self, snapshot, readout):
        if not isinstance(readout, FdasCoordinatedReplacementReadout):
            raise TypeError("replacement intention requires grounded readout")
        if (snapshot.identity.game_id != self.game_id
                or snapshot.player_id != self.player_id):
            raise ValueError("replacement intention snapshot identity differs")
        assignment = self.store.assignment
        created = False
        if assignment is None and readout.pairs:
            pair = sorted(
                readout.pairs,
                key=lambda value: value.lifecycle_operation_id)[0]
            assignment = self.store.record(self._new_assignment(pair, snapshot))
            created = True
        if assignment is None:
            return "unassigned", None, False
        if (assignment.assigned_arm != self.assigned_arm
                or assignment.game_id != self.game_id
                or assignment.player_id != self.player_id
                or assignment.experiment_id != self.experiment_id):
            raise ValueError("replacement intention assignment context differs")
        return self.observe_due(snapshot) + (created,)

    def observe_due(self, snapshot):
        """Observe an assigned endpoint without requiring another opportunity."""
        if (snapshot.identity.game_id != self.game_id
                or snapshot.player_id != self.player_id):
            raise ValueError("replacement intention snapshot identity differs")
        assignment = self.store.assignment
        if assignment is None:
            return "unassigned", None
        if (assignment.assigned_arm != self.assigned_arm
                or assignment.game_id != self.game_id
                or assignment.player_id != self.player_id
                or assignment.experiment_id != self.experiment_id):
            raise ValueError("replacement intention assignment context differs")
        if (assignment.outcome is None
                and int(snapshot.turn) >= assignment.due_turn):
            assignment = self._observe(assignment, snapshot)
        return (
            assignment.outcome.status
            if assignment.outcome is not None else "pending",
            assignment)

    def censor(self, reason="assignment-due-turn-outside-horizon"):
        assignment = self.store.assignment
        if assignment is None:
            return None
        if assignment.outcome is not None:
            return assignment
        outcome = FdasReplacementIntentionOutcome(
            "censored", None, None, None, None, None, None, None, None,
            None, None, None, None, None, str(reason))
        return self.store.record(replace(assignment, outcome=outcome))
