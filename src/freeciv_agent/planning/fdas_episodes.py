"""Durable, compact FDAS decision episodes and defense attribution."""

from dataclasses import dataclass, replace
import json
import math
import os
import tempfile

from ..events.schema import canonical_json_bytes, structural_hash
from .fdas_defense import FdasDefenseActionBinding
from .operation_store import OperationRecord


EPISODE_SCHEMA_VERSION = 1
_OUTCOME_STATES = frozenset((
    "proposed", "selected", "reserved", "commit-revalidated", "sent",
    "accepted-by-server", "immediate-effect-observed",
    "delayed-effect-pending", "goal-relief-observed",
    "effect-without-goal-relief",
    "no-effect-observed", "contradicted", "expired-unresolved",
    "confounded-unattributable",
))
_TERMINAL_STATES = frozenset((
    "goal-relief-observed", "effect-without-goal-relief",
    "no-effect-observed", "contradicted",
    "expired-unresolved", "confounded-unattributable",
))
_STATE_RANK = {
    value: index for index, value in enumerate((
        "proposed", "selected", "reserved", "commit-revalidated", "sent",
        "accepted-by-server", "delayed-effect-pending",
        "immediate-effect-observed", "goal-relief-observed"))
}


def _strings(values, name, unique=True):
    values = tuple(values)
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("episode {} values must be non-empty strings".format(
            name))
    if unique and len(values) != len(set(values)):
        raise ValueError("episode {} values must be unique".format(name))
    return values


@dataclass(frozen=True)
class DecisionEpisode:
    schema_version: int
    episode_id: str
    game_id: str
    player_id: int
    operation_id: str
    action_key: str
    before_revision_id: str
    after_revision_id: object
    goal_ids: tuple
    context_signature: tuple
    source_atom_ids: tuple
    source_support_ids: tuple
    grounding_result_ids: tuple
    prediction_ids: tuple
    resource_claim_ids: tuple
    validation_result_hash: str
    execution_event_id: object
    observed_delta: object
    attributed_effects: tuple
    realized_goal_relief: tuple
    outcome_status: str
    provenance_ids: tuple

    def __post_init__(self):
        if self.schema_version != EPISODE_SCHEMA_VERSION:
            raise ValueError("unsupported decision episode schema")
        for value, name in (
                (self.episode_id, "ID"), (self.game_id, "game ID"),
                (self.operation_id, "operation ID"),
                (self.action_key, "action key"),
                (self.before_revision_id, "before revision ID"),
                (self.validation_result_hash, "validation hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("episode {} is required".format(name))
        if (isinstance(self.player_id, bool)
                or not isinstance(self.player_id, int) or self.player_id < 0):
            raise ValueError("episode player ID must be non-negative")
        for value, name in (
                (self.after_revision_id, "after revision ID"),
                (self.execution_event_id, "execution event ID")):
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError("episode {} must be non-empty or absent".format(
                    name))
        for name in (
                "goal_ids", "source_atom_ids", "source_support_ids",
                "grounding_result_ids", "prediction_ids",
                "resource_claim_ids", "provenance_ids"):
            object.__setattr__(self, name, _strings(
                getattr(self, name), name, unique=True))
        context = tuple(tuple(value) for value in self.context_signature)
        if any(len(value) != 2 or any(
                not isinstance(item, str) or not item for item in value)
               for value in context):
            raise ValueError("episode context must contain string pairs")
        if len({value[0] for value in context}) != len(context):
            raise ValueError("episode context keys must be unique")
        object.__setattr__(self, "context_signature", tuple(sorted(context)))
        effects = tuple(dict(value) for value in self.attributed_effects)
        object.__setattr__(self, "attributed_effects", effects)
        relief = tuple((str(goal_id), float(value))
                       for goal_id, value in self.realized_goal_relief)
        if (len({value[0] for value in relief}) != len(relief)
                or any(not goal_id or not math.isfinite(value) or value < 0.0
                       for goal_id, value in relief)):
            raise ValueError("episode goal relief is invalid")
        object.__setattr__(self, "realized_goal_relief", tuple(sorted(relief)))
        if self.outcome_status not in _OUTCOME_STATES:
            raise ValueError("unknown episode outcome status")
        if (self.outcome_status in _TERMINAL_STATES
                and self.after_revision_id is None):
            raise ValueError("terminal episode requires an after revision")
        if (any(value > 0.0 for _goal, value in relief)
                and self.outcome_status != "goal-relief-observed"):
            raise ValueError("positive relief requires goal-relief outcome")
        if (self.outcome_status == "goal-relief-observed"
                and not any(value > 0.0 for _goal, value in relief)):
            raise ValueError("goal-relief outcome requires positive relief")
        if (self.outcome_status == "no-effect-observed" and effects):
            raise ValueError("no-effect outcome cannot carry effects")
        if self.observed_delta is not None and not isinstance(
                self.observed_delta, dict):
            raise TypeError("episode observed delta must be an object or absent")

    @property
    def immutable_digest(self):
        return structural_hash({
            "action_key": self.action_key,
            "before_revision_id": self.before_revision_id,
            "context_signature": dict(self.context_signature),
            "episode_id": self.episode_id,
            "execution_event_id": self.execution_event_id,
            "game_id": self.game_id,
            "goal_ids": list(self.goal_ids),
            "grounding_result_ids": list(self.grounding_result_ids),
            "operation_id": self.operation_id,
            "player_id": self.player_id,
            "prediction_ids": list(self.prediction_ids),
            "provenance_ids": list(self.provenance_ids),
            "resource_claim_ids": list(self.resource_claim_ids),
            "source_atom_ids": list(self.source_atom_ids),
            "source_support_ids": list(self.source_support_ids),
            "validation_result_hash": self.validation_result_hash,
        })

    def to_dict(self):
        return {
            "action_key": self.action_key,
            "after_revision_id": self.after_revision_id,
            "attributed_effects": list(self.attributed_effects),
            "before_revision_id": self.before_revision_id,
            "context_signature": dict(self.context_signature),
            "episode_id": self.episode_id,
            "execution_event_id": self.execution_event_id,
            "game_id": self.game_id,
            "goal_ids": list(self.goal_ids),
            "grounding_result_ids": list(self.grounding_result_ids),
            "immutable_digest": self.immutable_digest,
            "observed_delta": self.observed_delta,
            "operation_id": self.operation_id,
            "outcome_status": self.outcome_status,
            "player_id": self.player_id,
            "prediction_ids": list(self.prediction_ids),
            "provenance_ids": list(self.provenance_ids),
            "realized_goal_relief": dict(self.realized_goal_relief),
            "resource_claim_ids": list(self.resource_claim_ids),
            "schema_version": self.schema_version,
            "source_atom_ids": list(self.source_atom_ids),
            "source_support_ids": list(self.source_support_ids),
            "validation_result_hash": self.validation_result_hash,
        }

    @classmethod
    def from_dict(cls, value):
        episode = cls(
            value["schema_version"], value["episode_id"], value["game_id"],
            value["player_id"], value["operation_id"], value["action_key"],
            value["before_revision_id"], value.get("after_revision_id"),
            tuple(value["goal_ids"]),
            tuple(sorted(value["context_signature"].items())),
            tuple(value["source_atom_ids"]), tuple(value["source_support_ids"]),
            tuple(value["grounding_result_ids"]), tuple(value["prediction_ids"]),
            tuple(value["resource_claim_ids"]), value["validation_result_hash"],
            value.get("execution_event_id"), value.get("observed_delta"),
            tuple(value["attributed_effects"]),
            tuple(sorted(value["realized_goal_relief"].items())),
            value["outcome_status"], tuple(value["provenance_ids"]))
        if (value.get("immutable_digest") is not None
                and value["immutable_digest"] != episode.immutable_digest):
            raise ValueError("episode immutable digest mismatch")
        return episode


class DecisionEpisodeStore(object):
    STORE_IDENTITY = "fdas-decision-episode-store/1.0"

    def __init__(self, persistence_identity, episodes=(), quarantine_reason=None):
        if not isinstance(persistence_identity, str) or not persistence_identity:
            raise ValueError("episode persistence identity is required")
        self.persistence_identity = persistence_identity
        self.quarantine_reason = quarantine_reason
        self._episodes = {}
        for episode in episodes:
            if not isinstance(episode, DecisionEpisode):
                raise TypeError("episode store accepts DecisionEpisode values")
            if episode.episode_id in self._episodes:
                raise ValueError("duplicate decision episode")
            self._episodes[episode.episode_id] = episode

    @property
    def quarantined(self):
        return self.quarantine_reason is not None

    @property
    def store_digest(self):
        return structural_hash(self.to_dict(include_digest=False))

    def episodes(self):
        return tuple(self._episodes[key] for key in sorted(self._episodes))

    def get(self, episode_id):
        return self._episodes.get(str(episode_id))

    def pending_for_operation(self, operation_id):
        """Return nonterminal delayed/effect episodes for one operation."""
        operation_id = str(operation_id)
        return tuple(
            value for value in self.episodes()
            if (value.operation_id == operation_id
                and value.outcome_status in (
                    "accepted-by-server", "delayed-effect-pending",
                    "immediate-effect-observed")))

    @staticmethod
    def _transition_allowed(before, after):
        if before == after:
            return True
        if before in _TERMINAL_STATES:
            return False
        if after in ("contradicted", "expired-unresolved",
                     "confounded-unattributable", "no-effect-observed",
                     "effect-without-goal-relief"):
            return True
        return _STATE_RANK.get(after, -1) >= _STATE_RANK.get(before, -1)

    def record(self, episode):
        if self.quarantined:
            raise ValueError("quarantined episode store cannot record")
        if not isinstance(episode, DecisionEpisode):
            raise TypeError("episode store accepts DecisionEpisode values")
        prior = self._episodes.get(episode.episode_id)
        if prior is None:
            self._episodes[episode.episode_id] = episode
            return episode
        if prior == episode:
            return prior
        if prior.immutable_digest != episode.immutable_digest:
            raise ValueError("decision episode identity collision")
        if not self._transition_allowed(
                prior.outcome_status, episode.outcome_status):
            raise ValueError("invalid decision episode outcome transition")
        self._episodes[episode.episode_id] = episode
        return episode

    def to_dict(self, include_digest=True):
        value = {
            "episodes": [episode.to_dict() for episode in self.episodes()],
            "persistence_identity": self.persistence_identity,
            "quarantine_reason": self.quarantine_reason,
            "schema_version": EPISODE_SCHEMA_VERSION,
            "store_identity": self.STORE_IDENTITY,
        }
        if include_digest:
            value["store_digest"] = self.store_digest
        return value

    def save(self, path):
        if self.quarantined:
            raise ValueError("quarantined episode store cannot save")
        path = os.path.abspath(path)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".fdas-episodes-", suffix=".json", dir=directory or None)
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
                    or value.get("schema_version") != EPISODE_SCHEMA_VERSION
                    or value.get("persistence_identity")
                    != persistence_identity):
                raise ValueError("episode store identity mismatch")
            store = cls(
                persistence_identity,
                tuple(DecisionEpisode.from_dict(row)
                      for row in value["episodes"]),
                value.get("quarantine_reason"))
            if (value.get("store_digest") is not None
                    and value["store_digest"] != store.store_digest):
                raise ValueError("episode store digest mismatch")
            return store
        except (KeyError, OSError, TypeError, UnicodeError,
                ValueError, json.JSONDecodeError) as error:
            return cls(
                persistence_identity,
                quarantine_reason="episode-store-load-failed:{}".format(error))


class FdasDefenseEpisodeRecorder(object):
    RECORDER_IDENTITY = "fdas-defense-episode-recorder/1.0"

    def __init__(self, store):
        if not isinstance(store, DecisionEpisodeStore):
            raise TypeError("defense episode recorder requires episode store")
        self.store = store

    def begin(self, binding, operation_record, before_snapshot,
              before_revision_id, validation_result_hash,
              execution_event_id=None, source_atom_ids=(),
              source_support_ids=(), grounding_result_ids=(),
              prediction_ids=(), resource_claim_ids=(),
              outcome_status="accepted-by-server"):
        if not isinstance(binding, FdasDefenseActionBinding):
            raise TypeError("defense episode requires exact action binding")
        if not binding.legal_bound:
            raise ValueError("defense episode requires a legal-bound action")
        if not isinstance(operation_record, OperationRecord):
            raise TypeError("defense episode requires operation record")
        spec = operation_record.spec
        if spec.operation_id != binding.operation_id:
            raise ValueError("episode operation/binding mismatch")
        participant = spec.participants[0]
        actor_ref = participant.actor_id
        normalized_actor_ref = (
            "unit:{}".format(actor_ref)
            if participant.actor_class == "unit"
            and not actor_ref.startswith("unit:") else actor_ref)
        actor = (
            before_snapshot.unit(int(normalized_actor_ref.split(":", 1)[1]))
            if normalized_actor_ref.startswith("unit:") else None)
        city_id = int(spec.target_ref.split(":", 1)[1])
        city = before_snapshot.city(city_id)
        context = tuple(sorted({
            "actor_id": normalized_actor_ref,
            "actor_tile_before": str(None if actor is None else actor.tile),
            "city_id": str(city_id),
            "operation_type": spec.operation_type,
            "target_tile": str(None if city is None else city.tile),
        }.items()))
        material = {
            "action_key": binding.action_key,
            "before_revision_id": before_revision_id,
            "operation_id": spec.operation_id,
            "schema_version": EPISODE_SCHEMA_VERSION,
        }
        episode = DecisionEpisode(
            EPISODE_SCHEMA_VERSION,
            "episode-" + structural_hash(material)[:32],
            before_snapshot.identity.game_id,
            before_snapshot.player_id,
            spec.operation_id,
            binding.action_key,
            str(before_revision_id),
            None,
            spec.goal_ids,
            context,
            tuple(source_atom_ids), tuple(source_support_ids),
            tuple(grounding_result_ids), tuple(prediction_ids),
            tuple(resource_claim_ids), str(validation_result_hash),
            execution_event_id,
            None, (), (), outcome_status,
            (self.RECORDER_IDENTITY,) + tuple(spec.provenance),
        )
        existing = self.store.get(episode.episode_id)
        if existing is not None:
            if existing.immutable_digest != episode.immutable_digest:
                raise ValueError("decision episode identity collision")
            return existing
        return self.store.record(episode)

    def observe(self, episode_id, after_snapshot, after_revision_id,
                observation_window_closed=False):
        prior = self.store.get(episode_id)
        if prior is None:
            raise KeyError("unknown decision episode")
        if prior.outcome_status in _TERMINAL_STATES:
            if str(after_revision_id) != prior.after_revision_id:
                raise ValueError(
                    "terminal episode replay references another revision")
            return prior
        if (after_snapshot.identity.game_id != prior.game_id
                or after_snapshot.player_id != prior.player_id):
            raise ValueError("episode after snapshot identity mismatch")
        context = dict(prior.context_signature)
        actor_ref = context["actor_id"]
        actor = (
            after_snapshot.unit(int(actor_ref.split(":", 1)[1]))
            if actor_ref.startswith("unit:") else None)
        before_tile = (
            None if context["actor_tile_before"] == "None"
            else int(context["actor_tile_before"]))
        target_tile = (
            None if context["target_tile"] == "None"
            else int(context["target_tile"]))
        if actor is None:
            status = "confounded-unattributable"
            effects = ()
            relief = ()
            delta = {
                "actor_present_after": False,
                "reason": "actor-disappeared-without-attributable-cause",
            }
        else:
            moved = actor.tile != before_tile
            reached = bool(target_tile is not None and actor.tile == target_tile)
            fortified = str(actor.activity or "").lower() in (
                "fortify", "fortified", "fortifying")
            operation_type = context["operation_type"]
            relieved = bool(
                (operation_type == "move_defender_to_city" and reached)
                or (operation_type in (
                        "fortify_existing_defender",
                        "fdas-shadow:unit-fortification-opportunity:unit_fortify")
                    and reached and fortified))
            effects = tuple(
                value for value in (
                    {"effect": "actor-tile-changed",
                     "from": before_tile, "to": actor.tile}
                    if moved else None,
                    {"effect": "actor-fortified", "tile": actor.tile}
                    if fortified else None,
                ) if value is not None)
            relief = tuple(
                (goal_id, 1.0) for goal_id in prior.goal_ids) if relieved else ()
            if relieved:
                status = "goal-relief-observed"
            elif effects and observation_window_closed:
                status = "effect-without-goal-relief"
            elif effects:
                status = "immediate-effect-observed"
            elif observation_window_closed:
                status = "no-effect-observed"
            else:
                status = "delayed-effect-pending"
            delta = {
                "actor_activity_after": actor.activity,
                "actor_present_after": True,
                "actor_tile_after": actor.tile,
                "actor_tile_before": before_tile,
                "target_tile": target_tile,
            }
        updated = replace(
            prior,
            after_revision_id=str(after_revision_id),
            observed_delta=delta,
            attributed_effects=effects,
            realized_goal_relief=relief,
            outcome_status=status,
        )
        return self.store.record(updated)

    def observe_operation(
            self, operation_id, after_snapshot, after_revision_id,
            observation_window_closed=False):
        pending = self.store.pending_for_operation(operation_id)
        if not pending:
            raise KeyError("operation has no pending decision episode")
        if len(pending) != 1:
            raise ValueError("operation has ambiguous pending decision episodes")
        return self.observe(
            pending[0].episode_id, after_snapshot, after_revision_id,
            observation_window_closed=observation_window_closed)
