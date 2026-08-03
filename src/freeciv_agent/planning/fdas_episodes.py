"""Durable, compact FDAS decision episodes and defense attribution."""

from dataclasses import dataclass, replace
import json
import math
import os
import tempfile

from ..events.schema import canonical_json_bytes, structural_hash
from .fdas import ShadowOperationCandidate
from .fdas_authority import FdasAuthorityReadout
from .fdas_defense import FdasDefenseActionBinding
from .operation_store import OperationRecord, OperationStore
from .operations import OperationSpec


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

INDUCTION_FEATURE_SCHEMA = "defense-episode-features/2.0"
CAUSAL_INDUCTION_FEATURE_SCHEMA = "defense-episode-features/3.0"
_INDUCTION_FEATURE_SCHEMAS = frozenset((
    INDUCTION_FEATURE_SCHEMA,
    CAUSAL_INDUCTION_FEATURE_SCHEMA,
))


def _count_band(value):
    value = max(0, int(value))
    return str(value) if value < 3 else "3+"


def _city_size_band(value):
    if value is None:
        return "unknown"
    value = int(value)
    if value <= 1:
        return "1"
    if value <= 4:
        return "2-4"
    if value <= 8:
        return "5-8"
    return "9+"


def _optional_band(value):
    if value is None:
        return "unknown"
    value = int(value)
    if value <= 0:
        return "none"
    if value == 1:
        return "one"
    return "2+"


def _optional_boolean(value):
    if value is None:
        return "unknown"
    return "true" if value else "false"


def _turn_phase_band(value):
    value = max(0, int(value))
    if value <= 31:
        return "0-31"
    if value <= 63:
        return "32-63"
    if value <= 95:
        return "64-95"
    return "96+"


def _homecity_relation(actor, city):
    if actor is None or actor.homecity is None or city is None:
        return "unknown"
    if int(actor.homecity) <= 0:
        return "none"
    return "target" if int(actor.homecity) == int(city.city_id) else "other"


def _production_class(city):
    if city is None or city.production_kind is None:
        return "unknown"
    return {6: "unit", 3: "improvement"}.get(
        int(city.production_kind), "other")


def _operating_gold_band(economy):
    value = economy.operating_gold_per_turn
    if value is None:
        value = economy.gold_per_turn
    if value is None:
        return "unknown"
    if int(value) < 0:
        return "negative"
    if int(value) == 0:
        return "zero"
    return "positive"


def _wrapped_city_enemy_distance(snapshot, city, enemy):
    if (city is None
            or None in (
                city.x, city.y, enemy.x, enemy.y,
                snapshot.map_wrap_x, snapshot.map_wrap_y)
            or snapshot.map_width <= 0 or snapshot.map_height <= 0):
        return None
    dx = abs(int(city.x) - int(enemy.x))
    dy = abs(int(city.y) - int(enemy.y))
    if snapshot.map_wrap_x:
        dx = min(dx, int(snapshot.map_width) - dx)
    if snapshot.map_wrap_y:
        dy = min(dy, int(snapshot.map_height) - dy)
    return max(dx, dy)


def _visible_threat_context(snapshot, city):
    enemies = tuple(snapshot.visible_enemy_units)
    if not enemies:
        return "none-visible", "0"
    distances = tuple(
        _wrapped_city_enemy_distance(snapshot, city, enemy)
        for enemy in enemies)
    if any(value is None for value in distances):
        return "unknown", "unknown"
    nearest = min(distances)
    if nearest <= 1:
        proximity = "adjacent"
    elif nearest <= 3:
        proximity = "near"
    elif nearest <= 6:
        proximity = "regional"
    else:
        proximity = "distant"
    return proximity, _count_band(sum(value <= 3 for value in distances))


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

    def __init__(self, store, induction_feature_schema=INDUCTION_FEATURE_SCHEMA):
        if not isinstance(store, DecisionEpisodeStore):
            raise TypeError("defense episode recorder requires episode store")
        if induction_feature_schema not in _INDUCTION_FEATURE_SCHEMAS:
            raise ValueError("unsupported defense induction feature schema")
        self.store = store
        self.induction_feature_schema = induction_feature_schema

    def context_for_operation(self, operation, before_snapshot):
        """Project snapshot-bound defense features without opening an episode."""
        if not isinstance(operation, OperationSpec):
            raise TypeError("defense feature context requires OperationSpec")
        if (not operation.participants
                or not isinstance(operation.target_ref, str)
                or not operation.target_ref.startswith("city:")):
            raise ValueError("defense feature context requires a city target")
        participant = operation.participants[0]
        actor_ref = participant.actor_id
        normalized_actor_ref = (
            "unit:{}".format(actor_ref)
            if participant.actor_class == "unit"
            and not actor_ref.startswith("unit:") else actor_ref)
        actor = (
            before_snapshot.unit(int(normalized_actor_ref.split(":", 1)[1]))
            if normalized_actor_ref.startswith("unit:") else None)
        city_id = int(operation.target_ref.split(":", 1)[1])
        city = before_snapshot.city(city_id)
        target_units = tuple(
            value for value in before_snapshot.units
            if city is not None and value.tile == city.tile
            and value.transported is not True)
        other_target_units = tuple(
            value for value in target_units
            if actor is None or value.unit_id != actor.unit_id)
        context = {
            "actor_id": normalized_actor_ref,
            "actor_moves_band": _optional_band(
                None if actor is None else actor.moves_left),
            "actor_tile_before": str(None if actor is None else actor.tile),
            "actor_unit_type": (
                "unknown" if actor is None else str(actor.unit_type)),
            "actor_veteran_band": _optional_band(
                None if actor is None else actor.veteran),
            "city_id": str(city_id),
            "city_disorder": _optional_boolean(
                None if city is None else city.disorder),
            "city_size_band": _city_size_band(
                None if city is None else city.size),
            "induction_feature_schema": self.induction_feature_schema,
            "operation_type": operation.operation_type,
            "other_own_units_at_target_band": _count_band(
                len(other_target_units)),
            "own_units_at_target_band": _count_band(len(target_units)),
            "target_tile": str(None if city is None else city.tile),
        }
        if operation.operation_type == (
                "fdas-shadow:city-garrison-deficit:unit_move"):
            context["goal_relief_due_turn"] = str(operation.expiry_turn)
        if self.induction_feature_schema == CAUSAL_INDUCTION_FEATURE_SCHEMA:
            fortified_activities = frozenset((
                "fortify", "fortified", "fortifying"))
            other_fortified_units = tuple(
                value for value in other_target_units
                if str(value.activity or "").lower()
                in fortified_activities)
            threat_proximity, nearby_threat_count = (
                _visible_threat_context(before_snapshot, city))
            context.update({
                "actor_homecity_relation": _homecity_relation(actor, city),
                "city_production_class": _production_class(city),
                "empire_city_count_band": _count_band(
                    len(before_snapshot.cities)),
                "economy_operating_gold_band": _operating_gold_band(
                    before_snapshot.economy),
                "other_fortified_units_at_target_band": _count_band(
                    len(other_fortified_units)),
                "turn_phase_band": _turn_phase_band(before_snapshot.turn),
                "visible_enemy_count_near_city_band": nearby_threat_count,
                "visible_enemy_proximity_band": threat_proximity,
            })
        return tuple(sorted(context.items()))

    @staticmethod
    def observation_window_should_close(
            episode, current_turn, turn_boundary_closed):
        """Close route attribution only at its grounded completion turn."""
        if not isinstance(episode, DecisionEpisode):
            raise TypeError("observation window requires decision episode")
        if not turn_boundary_closed:
            return False
        context = dict(episode.context_signature)
        due_turn = context.get("goal_relief_due_turn")
        if due_turn is None:
            return True
        try:
            due_turn = int(due_turn)
        except (TypeError, ValueError):
            raise ValueError("episode goal-relief due turn is invalid")
        if due_turn < 0:
            raise ValueError("episode goal-relief due turn is invalid")
        # FreeCiv actions execute during the numbered turn.  A route whose
        # ETA is turn N must remain observable through that turn and close at
        # the next turn boundary.
        return int(current_turn) > due_turn

    def begin(self, binding, operation_record, before_snapshot,
              before_revision_id, validation_result_hash,
              execution_event_id=None, source_atom_ids=(),
              source_support_ids=(), grounding_result_ids=(),
              prediction_ids=(), resource_claim_ids=(),
              extra_provenance_ids=(),
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
        context = self.context_for_operation(spec, before_snapshot)
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
            (self.RECORDER_IDENTITY,) + tuple(spec.provenance)
            + tuple(extra_provenance_ids),
        )
        existing = self.store.get(episode.episode_id)
        if existing is not None:
            if existing.immutable_digest != episode.immutable_digest:
                raise ValueError("decision episode identity collision")
            return existing
        return self.store.record(episode)

    def begin_authorized(
            self, candidate, readout, shadow_evaluation, before_snapshot,
            before_revision, execution_event_id, prediction_ids=()):
        """Open an episode from one exact accepted defense authority action."""
        if not isinstance(candidate, ShadowOperationCandidate):
            raise TypeError("authorized episode requires shadow candidate")
        if not isinstance(readout, FdasAuthorityReadout):
            raise TypeError("authorized episode requires authority readout")
        if (not readout.authorized
                or readout.authority_slice
                != "fdas-bounded-defense-fortification/1.0"
                or readout.snapshot_id != before_snapshot.snapshot_id
                or readout.revision_id != before_revision.revision_id
                or readout.operation_id != candidate.operation.operation_id
                or readout.action_key != candidate.action_key):
            raise ValueError("authorized episode evidence is inconsistent")
        if (shadow_evaluation.snapshot_id != before_snapshot.snapshot_id
                or shadow_evaluation.revision_id
                != before_revision.revision_id):
            raise ValueError("authorized episode shadow evidence is stale")
        validation_hash = (readout.commit_validation or {}).get("result_hash")
        if not validation_hash:
            raise ValueError("authorized episode lacks commit validation")
        action = candidate.action
        if (action.get("action_type") != "unit_fortify"
                or candidate.action_key
                not in before_snapshot.legal_action_json):
            raise ValueError("authorized episode is outside defense slice")
        operation_store = OperationStore(
            "fdas-defense-episode-operation:{}".format(
                candidate.operation.operation_id))
        operation_record = operation_store.propose(
            candidate.operation, before_snapshot.snapshot_id,
            before_snapshot.turn)
        binding_material = {
            "action": action,
            "action_key": candidate.action_key,
            "domain_operation_id": candidate.operation.operation_id,
            "legal_actions_digest": before_snapshot.legal_actions_digest,
            "legal_bound": True,
            "operation_id": candidate.operation.operation_id,
            "snapshot_id": before_snapshot.snapshot_id,
        }
        binding = FdasDefenseActionBinding(
            candidate.operation.operation_id,
            candidate.operation.operation_id,
            before_snapshot.snapshot_id,
            before_snapshot.legal_actions_digest,
            action,
            candidate.action_key,
            True,
            structural_hash(binding_material),
        )
        goal_ids = frozenset(candidate.operation.goal_ids)
        source_atom_ids = tuple(sorted(
            value.deficit_atom_id for value in shadow_evaluation.goals
            if value.goal.goal_id in goal_ids))
        source_support_ids = tuple(sorted({
            support.support_id
            for atom_id in source_atom_ids
            for support in before_revision.record(atom_id).supports
        }))
        resource_claim_ids = tuple(sorted(
            structural_hash(claim)
            for request in readout.scheduling["resource_schedule"]["requests"]
            for claim in request["claims"]))
        instantiation_hash = (
            shadow_evaluation.candidate_instantiation.instantiation_hash)
        return self.begin(
            binding, operation_record, before_snapshot,
            before_revision.revision_id, validation_hash,
            execution_event_id=execution_event_id,
            source_atom_ids=source_atom_ids,
            source_support_ids=source_support_ids,
            grounding_result_ids=(instantiation_hash,),
            prediction_ids=tuple(prediction_ids),
            resource_claim_ids=resource_claim_ids,
        )

    def begin_observed_selection(
            self, candidate, shadow_evaluation, before_snapshot,
            before_revision, execution_event_id, selection_evidence_hash,
            selection_policy_authority=False,
            selection_provenance_ids=()):
        """Open an episode for one exact accepted defense-surface selection."""
        if not isinstance(candidate, ShadowOperationCandidate):
            raise TypeError("observed episode requires shadow candidate")
        if (shadow_evaluation.snapshot_id != before_snapshot.snapshot_id
                or shadow_evaluation.revision_id
                != before_revision.revision_id):
            raise ValueError("observed episode shadow evidence is stale")
        if (not isinstance(selection_evidence_hash, str)
                or not selection_evidence_hash):
            raise ValueError("observed episode requires selection evidence")
        if not isinstance(selection_policy_authority, bool):
            raise TypeError("observed episode policy authority must be boolean")
        selection_provenance_ids = _strings(
            selection_provenance_ids, "selection provenance", unique=True)
        if selection_policy_authority and not selection_provenance_ids:
            raise ValueError(
                "authorizing observed selection requires policy provenance")
        action = candidate.action
        operation_type = candidate.operation.operation_type
        supported = {
            ("unit_fortify",
             "fdas-shadow:unit-fortification-opportunity:unit_fortify"),
            ("unit_move", "fdas-shadow:city-garrison-deficit:unit_move"),
        }
        if ((action.get("action_type"), operation_type) not in supported
                or not candidate.legal_bound
                or candidate.action_key
                not in before_snapshot.legal_action_json):
            raise ValueError(
                "observed episode is outside exact defense choice surface")
        operation_store = OperationStore(
            "fdas-observed-defense-episode-operation:{}".format(
                candidate.operation.operation_id))
        operation_record = operation_store.propose(
            candidate.operation, before_snapshot.snapshot_id,
            before_snapshot.turn)
        binding_material = {
            "action": action,
            "action_key": candidate.action_key,
            "domain_operation_id": candidate.operation.operation_id,
            "legal_actions_digest": before_snapshot.legal_actions_digest,
            "legal_bound": True,
            "operation_id": candidate.operation.operation_id,
            "snapshot_id": before_snapshot.snapshot_id,
        }
        binding = FdasDefenseActionBinding(
            candidate.operation.operation_id,
            candidate.operation.operation_id,
            before_snapshot.snapshot_id,
            before_snapshot.legal_actions_digest,
            action,
            candidate.action_key,
            True,
            structural_hash(binding_material),
        )
        goal_ids = frozenset(candidate.operation.goal_ids)
        source_atom_ids = tuple(sorted(
            value.deficit_atom_id for value in shadow_evaluation.goals
            if value.goal.goal_id in goal_ids))
        source_support_ids = tuple(sorted({
            support.support_id
            for atom_id in source_atom_ids
            for support in before_revision.record(atom_id).supports
        }))
        return self.begin(
            binding, operation_record, before_snapshot,
            before_revision.revision_id, selection_evidence_hash,
            execution_event_id=execution_event_id,
            source_atom_ids=source_atom_ids,
            source_support_ids=source_support_ids,
            grounding_result_ids=(candidate.candidate_hash,),
            extra_provenance_ids=(
                ("fdas-observed-randomized-defense-selection/1.0"
                 if selection_policy_authority else
                 "fdas-observed-legacy-defense-selection/1.0"),
                "selection-evidence:" + selection_evidence_hash,
                "policy-authority:{}".format(
                    str(selection_policy_authority).lower()),
            ) + selection_provenance_ids)

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
                "observed_turn": after_snapshot.turn,
                "reason": "actor-disappeared-without-attributable-cause",
            }
        else:
            moved = actor.tile != before_tile
            reached = bool(target_tile is not None and actor.tile == target_tile)
            fortified = str(actor.activity or "").lower() in (
                "fortify", "fortified", "fortifying")
            operation_type = context["operation_type"]
            relieved = bool(
                (operation_type in (
                    "move_defender_to_city",
                    "fdas-shadow:city-garrison-deficit:unit_move")
                 and reached)
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
                "observed_turn": after_snapshot.turn,
                "target_tile": target_tile,
            }
            if prior.attributed_effects and not relieved:
                historical = tuple(prior.attributed_effects)
                historical_hashes = set(
                    structural_hash(value) for value in historical)
                current_hashes = set(
                    structural_hash(value) for value in effects)
                effects = historical + tuple(
                    value for value in effects
                    if structural_hash(value) not in historical_hashes)
                status = (
                    "effect-without-goal-relief"
                    if observation_window_closed else
                    "immediate-effect-observed")
                if historical_hashes.difference(current_hashes):
                    delta["historical_effect_retained"] = True
        prior_delta = dict(prior.observed_delta or {})
        comparable_prior_delta = dict(
            (key, value) for key, value in prior_delta.items()
            if key != "observed_turn")
        comparable_delta = dict(
            (key, value) for key, value in delta.items()
            if key != "observed_turn")
        if (prior.outcome_status == "immediate-effect-observed"
                and status == "immediate-effect-observed"
                and prior.attributed_effects == effects
                and prior.realized_goal_relief == relief
                and comparable_prior_delta == comparable_delta):
            return prior
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
