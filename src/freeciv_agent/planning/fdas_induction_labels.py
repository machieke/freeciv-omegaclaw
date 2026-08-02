"""Durable, non-authorizing delayed outcome labels for FDAS induction."""

from dataclasses import dataclass, replace
import json
import os
import tempfile

from ..events.schema import canonical_json_bytes, structural_hash
from ..state.snapshot import AuthoritativeSnapshot
from .fdas_episodes import DecisionEpisode


LABEL_SCHEMA_VERSION = 1
DURABLE_CITY_COVERAGE_TARGET = "durable-own-unit-city-coverage/8-turn/1.0"
_LABEL_STATES = frozenset(("pending", "observed", "confounded", "expired"))
_TERMINAL_LABEL_STATES = frozenset(("observed", "confounded", "expired"))


def _strings(values, name):
    result = tuple(sorted(str(value) for value in values))
    if any(not value for value in result) or len(result) != len(set(result)):
        raise ValueError("{} must be unique non-empty strings".format(name))
    return result


def combine_outcome_label_stores(stores, persistence_identity):
    """Combine verified delayed-label artifacts without losing provenance."""
    stores = tuple(stores)
    if not stores:
        raise ValueError("outcome-label cohort requires a source store")
    if not isinstance(persistence_identity, str) or not persistence_identity:
        raise ValueError("outcome-label cohort identity is required")
    if any(not isinstance(value, EpisodeInductionOutcomeLabelStore)
           for value in stores):
        raise TypeError(
            "outcome-label cohort accepts typed outcome-label stores")
    if any(value.quarantined for value in stores):
        raise ValueError(
            "quarantined outcome-label source cannot enter cohort")
    identities = [value.persistence_identity for value in stores]
    digests = [value.store_digest for value in stores]
    if len(identities) != len(set(identities)):
        raise ValueError("outcome-label cohort source identities overlap")
    if len(digests) != len(set(digests)):
        raise ValueError("outcome-label cohort source artifacts overlap")
    labels = tuple(label for store in stores for label in store.labels())
    label_ids = [value.label_id for value in labels]
    episode_targets = [
        (value.episode_id, value.target_id) for value in labels]
    if len(label_ids) != len(set(label_ids)):
        raise ValueError("outcome-label cohort IDs overlap")
    if len(episode_targets) != len(set(episode_targets)):
        raise ValueError("outcome-label cohort episode targets overlap")
    return EpisodeInductionOutcomeLabelStore(persistence_identity, labels)


@dataclass(frozen=True)
class EpisodeInductionOutcomeLabel:
    """One revision-bound delayed predictive label for an immutable episode."""

    schema_version: int
    label_id: str
    episode_id: str
    episode_digest: str
    game_id: str
    player_id: int
    target_id: str
    relief_turn: int
    due_turn: int
    relief_revision_id: str
    status: str
    observed_turn: object
    observed_revision_id: object
    outcome: object
    observed_value: tuple
    reason: object
    provenance_ids: tuple

    def __post_init__(self):
        if self.schema_version != LABEL_SCHEMA_VERSION:
            raise ValueError("unsupported outcome-label schema")
        for value, name in (
                (self.label_id, "label ID"),
                (self.episode_id, "episode ID"),
                (self.episode_digest, "episode digest"),
                (self.game_id, "game ID"),
                (self.target_id, "target ID"),
                (self.relief_revision_id, "relief revision ID")):
            if not isinstance(value, str) or not value:
                raise ValueError("outcome-label {} is required".format(name))
        if (isinstance(self.player_id, bool)
                or not isinstance(self.player_id, int) or self.player_id < 0):
            raise ValueError("outcome-label player ID is invalid")
        for value, name in (
                (self.relief_turn, "relief turn"),
                (self.due_turn, "due turn")):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("outcome-label {} is invalid".format(name))
        if self.due_turn <= self.relief_turn:
            raise ValueError("outcome-label due turn must follow relief")
        if self.status not in _LABEL_STATES:
            raise ValueError("unknown outcome-label status")
        observed_value = tuple(sorted(
            (str(key), value) for key, value in self.observed_value))
        if any(not key for key, _value in observed_value):
            raise ValueError("outcome-label observed keys are invalid")
        object.__setattr__(self, "observed_value", observed_value)
        object.__setattr__(
            self, "provenance_ids", _strings(
                self.provenance_ids, "outcome-label provenance"))
        if self.status == "pending":
            if any(value is not None for value in (
                    self.observed_turn, self.observed_revision_id,
                    self.outcome, self.reason)) or observed_value:
                raise ValueError("pending outcome label has terminal fields")
        else:
            if (isinstance(self.observed_turn, bool)
                    or not isinstance(self.observed_turn, int)
                    or self.observed_turn < self.due_turn):
                raise ValueError("terminal outcome label has invalid turn")
            if not isinstance(self.observed_revision_id, str) or not (
                    self.observed_revision_id):
                raise ValueError("terminal outcome label requires revision")
            if not isinstance(self.reason, str) or not self.reason:
                raise ValueError("terminal outcome label requires reason")
            if self.status == "observed":
                if not isinstance(self.outcome, bool) or not observed_value:
                    raise ValueError(
                        "observed outcome label requires value and boolean")
            elif self.outcome is not None:
                raise ValueError("non-observed terminal label has outcome")
        expected = "outcome-label-" + structural_hash(
            self.identity_material)[:24]
        if self.label_id != expected:
            raise ValueError("outcome-label identity mismatch")

    @property
    def identity_material(self):
        return {
            "due_turn": self.due_turn,
            "episode_digest": self.episode_digest,
            "episode_id": self.episode_id,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "relief_revision_id": self.relief_revision_id,
            "relief_turn": self.relief_turn,
            "schema_version": self.schema_version,
            "target_id": self.target_id,
        }

    @property
    def state_digest(self):
        return structural_hash(self.to_dict(include_digest=False))

    def to_dict(self, include_digest=True):
        value = dict(self.identity_material)
        value.update({
            "label_id": self.label_id,
            "observed_revision_id": self.observed_revision_id,
            "observed_turn": self.observed_turn,
            "observed_value": dict(self.observed_value),
            "outcome": self.outcome,
            "policy_authority": False,
            "provenance_ids": list(self.provenance_ids),
            "reason": self.reason,
            "status": self.status,
            "truth_mutated": False,
        })
        if include_digest:
            value["state_digest"] = self.state_digest
        return value

    @classmethod
    def from_dict(cls, value):
        if (value.get("policy_authority") is not False
                or value.get("truth_mutated") is not False):
            raise ValueError("outcome label cannot mutate truth or policy")
        label = cls(
            value["schema_version"], value["label_id"], value["episode_id"],
            value["episode_digest"], value["game_id"], value["player_id"],
            value["target_id"], value["relief_turn"], value["due_turn"],
            value["relief_revision_id"], value["status"],
            value.get("observed_turn"), value.get("observed_revision_id"),
            value.get("outcome"),
            tuple(sorted(value.get("observed_value", {}).items())),
            value.get("reason"), tuple(value.get("provenance_ids", ())))
        if (value.get("state_digest") is not None
                and value["state_digest"] != label.state_digest):
            raise ValueError("outcome-label state digest mismatch")
        return label


class EpisodeInductionOutcomeLabelStore(object):
    """Atomic and restart-safe delayed-label lifecycle."""

    STORE_IDENTITY = "fdas-induction-outcome-label-store/1.0"

    def __init__(self, persistence_identity, labels=(), quarantine_reason=None):
        if not isinstance(persistence_identity, str) or not persistence_identity:
            raise ValueError("outcome-label persistence identity is required")
        self.persistence_identity = persistence_identity
        self.quarantine_reason = quarantine_reason
        self._labels = {}
        self._episode_targets = {}
        for label in labels:
            self._insert(label)

    @property
    def quarantined(self):
        return self.quarantine_reason is not None

    def _insert(self, label):
        if not isinstance(label, EpisodeInductionOutcomeLabel):
            raise TypeError("outcome-label store accepts typed labels")
        key = (label.episode_id, label.target_id)
        if label.label_id in self._labels or key in self._episode_targets:
            raise ValueError("duplicate outcome label")
        self._labels[label.label_id] = label
        self._episode_targets[key] = label.label_id

    def labels(self):
        return tuple(self._labels[key] for key in sorted(self._labels))

    def get(self, label_id):
        return self._labels.get(str(label_id))

    def for_episode(self, episode_id, target_id):
        label_id = self._episode_targets.get((str(episode_id), str(target_id)))
        return None if label_id is None else self._labels[label_id]

    @property
    def store_digest(self):
        return structural_hash(self.to_dict(include_digest=False))

    def record(self, label):
        if self.quarantined:
            raise ValueError("quarantined outcome-label store cannot record")
        if not isinstance(label, EpisodeInductionOutcomeLabel):
            raise TypeError("outcome-label store accepts typed labels")
        prior = self._labels.get(label.label_id)
        if prior is None:
            self._insert(label)
            return label
        if prior == label:
            return prior
        if prior.identity_material != label.identity_material:
            raise ValueError("outcome-label identity collision")
        if prior.status in _TERMINAL_LABEL_STATES:
            raise ValueError("terminal outcome label cannot transition")
        if label.status == "pending":
            raise ValueError("outcome label cannot return to pending")
        self._labels[label.label_id] = label
        return label

    def to_dict(self, include_digest=True):
        value = {
            "labels": [value.to_dict() for value in self.labels()],
            "persistence_identity": self.persistence_identity,
            "quarantine_reason": self.quarantine_reason,
            "schema_version": LABEL_SCHEMA_VERSION,
            "store_identity": self.STORE_IDENTITY,
        }
        if include_digest:
            value["store_digest"] = self.store_digest
        return value

    def save(self, path):
        if self.quarantined:
            raise ValueError("quarantined outcome-label store cannot save")
        path = os.path.abspath(path)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".fdas-outcome-labels-", suffix=".json",
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
                    or value.get("schema_version") != LABEL_SCHEMA_VERSION
                    or value.get("persistence_identity")
                    != persistence_identity):
                raise ValueError("outcome-label store identity mismatch")
            store = cls(
                persistence_identity,
                tuple(EpisodeInductionOutcomeLabel.from_dict(row)
                      for row in value.get("labels", ())),
                value.get("quarantine_reason"))
            if (value.get("store_digest") is not None
                    and value["store_digest"] != store.store_digest):
                raise ValueError("outcome-label store digest mismatch")
            return store
        except (KeyError, OSError, TypeError, UnicodeError,
                ValueError, json.JSONDecodeError) as error:
            return cls(
                persistence_identity,
                quarantine_reason="outcome-label-store-load-failed:{}".format(
                    error))


class FdasDefenseDurabilityLabeler(object):
    """Observe bounded delayed city coverage from authoritative own state."""

    LABELER_IDENTITY = "fdas-defense-durability-labeler/1.0"

    def __init__(self, store, observation_window_turns=8):
        if not isinstance(store, EpisodeInductionOutcomeLabelStore):
            raise TypeError("durability labeler requires outcome-label store")
        self.store = store
        self.observation_window_turns = int(observation_window_turns)
        if self.observation_window_turns != 8:
            raise ValueError("durability target requires its declared 8 turns")

    def open(self, episode, relief_turn, relief_revision_id):
        if not isinstance(episode, DecisionEpisode):
            raise TypeError("durability label requires decision episode")
        if episode.outcome_status != "goal-relief-observed":
            raise ValueError("durability label requires observed immediate relief")
        if episode.after_revision_id != str(relief_revision_id):
            raise ValueError("durability label relief revision mismatch")
        relief_turn = int(relief_turn)
        due_turn = relief_turn + self.observation_window_turns
        material = {
            "due_turn": due_turn,
            "episode_digest": episode.immutable_digest,
            "episode_id": episode.episode_id,
            "game_id": episode.game_id,
            "player_id": episode.player_id,
            "relief_revision_id": str(relief_revision_id),
            "relief_turn": relief_turn,
            "schema_version": LABEL_SCHEMA_VERSION,
            "target_id": DURABLE_CITY_COVERAGE_TARGET,
        }
        label = EpisodeInductionOutcomeLabel(
            LABEL_SCHEMA_VERSION,
            "outcome-label-" + structural_hash(material)[:24],
            episode.episode_id,
            episode.immutable_digest,
            episode.game_id,
            episode.player_id,
            DURABLE_CITY_COVERAGE_TARGET,
            relief_turn,
            due_turn,
            str(relief_revision_id),
            "pending",
            None,
            None,
            None,
            (),
            None,
            (
                self.LABELER_IDENTITY,
                "episode:" + episode.immutable_digest,
                "relief-revision:" + str(relief_revision_id),
            ))
        existing = self.store.for_episode(
            episode.episode_id, DURABLE_CITY_COVERAGE_TARGET)
        if existing is not None:
            if existing.identity_material != label.identity_material:
                raise ValueError("durability label identity collision")
            return existing
        return self.store.record(label)

    def observe(self, episode, snapshot, revision_id):
        if not isinstance(episode, DecisionEpisode):
            raise TypeError("durability observation requires decision episode")
        if not isinstance(snapshot, AuthoritativeSnapshot):
            raise TypeError("durability observation requires snapshot")
        label = self.store.for_episode(
            episode.episode_id, DURABLE_CITY_COVERAGE_TARGET)
        if label is None:
            raise KeyError("episode has no durability outcome label")
        if label.episode_digest != episode.immutable_digest:
            raise ValueError("durability label episode digest mismatch")
        if (snapshot.identity.game_id != label.game_id
                or snapshot.player_id != label.player_id):
            raise ValueError("durability observation identity mismatch")
        if label.status in _TERMINAL_LABEL_STATES:
            if str(revision_id) != label.observed_revision_id:
                raise ValueError(
                    "terminal durability replay references another revision")
            return label
        if snapshot.turn < label.due_turn:
            return label
        context = dict(episode.context_signature)
        city_id = int(context["city_id"])
        city = snapshot.city(city_id)
        own_units = tuple(
            value for value in snapshot.units
            if city is not None and value.tile == city.tile
            and value.transported is not True)
        outcome = bool(city is not None and own_units)
        if city is None:
            reason = "city-no-longer-owned-or-present-at-due-turn"
        elif own_units:
            reason = "authoritative-own-unit-coverage-observed-at-due-turn"
        else:
            reason = "authoritative-own-unit-coverage-absent-at-due-turn"
        resolved = replace(
            label,
            status="observed",
            observed_turn=snapshot.turn,
            observed_revision_id=str(revision_id),
            outcome=outcome,
            observed_value=tuple(sorted({
                "city_id": city_id,
                "city_owned_and_present": city is not None,
                "own_unit_count_at_city": len(own_units),
            }.items())),
            reason=reason,
            provenance_ids=tuple(sorted(set(
                label.provenance_ids + (
                    "assessment-revision:" + str(revision_id),))))
        )
        return self.store.record(resolved)
