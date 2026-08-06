"""Proposal-time retained-capacity features with mandatory abstention."""

from dataclasses import dataclass
import json
import os
import tempfile

from ..events.schema import canonical_json_bytes, structural_hash
from ..state.snapshot import AuthoritativeSnapshot
from .fdas_capacity_outcomes import FdasRetainedCapacityOutcomeLabel


RETAINED_CAPACITY_TRANSITION_FEATURE_SCHEMA = (
    "retained-capacity-transition-features/1.0")
RETAINED_CAPACITY_TRANSITION_QUERY_IDENTITY = (
    "fdas-retained-capacity-transition-query/1.0")
RETAINED_CAPACITY_TRANSITION_QUERY_STORE_IDENTITY = (
    "fdas-retained-capacity-transition-query-store/1.0")
_MECHANISM = "fdas-replacement-capacity-retained-queue-lifecycle"
_OPERATION_TYPE = (
    "fdas-shadow:city-replacement-capacity-deficit:city_production")
_ABSTENTION_REASON = "insufficient-independent-calibration-evidence"
_FEATURE_NAMES = frozenset((
    "action_category", "completion_horizon_band", "cross_city_deficit",
    "exact_queue_match", "lifecycle_state", "production_target",
    "source_city_disorder", "source_city_food_surplus_band",
    "source_city_own_unit_count_band", "source_city_shield_surplus_band",
    "source_city_size_band", "target_city_own_unit_count_band",
    "target_city_size_band", "turn_phase_band",
))


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


def _normalized(value):
    value = " ".join(str(value).strip().lower().replace("_", " ").split())
    return _required_text(value, "normalized production target")


def _turn_phase(turn):
    turn = int(turn)
    if turn < 0:
        raise ValueError("proposal turn is invalid")
    if turn <= 39:
        return "0-39"
    if turn <= 79:
        return "40-79"
    return "80+"


def _horizon_band(value):
    value = int(value)
    if value < 1:
        raise ValueError("completion horizon is invalid")
    if value <= 16:
        return "1-16"
    if value <= 32:
        return "17-32"
    if value <= 64:
        return "33-64"
    return "65+"


def _size_band(value):
    value = int(value)
    if value < 1:
        raise ValueError("city size is invalid")
    if value == 1:
        return "1"
    if value <= 4:
        return "2-4"
    if value <= 8:
        return "5-8"
    return "9+"


def _surplus_band(value):
    value = int(value)
    if value < 0:
        return "negative"
    if value == 0:
        return "zero"
    if value <= 4:
        return "1-4"
    return "5+"


def _count_band(value):
    value = int(value)
    if value < 0:
        raise ValueError("unit count is invalid")
    return str(value) if value < 3 else "3+"


def _optional_boolean(value):
    if value is None:
        return "unknown"
    return "true" if value is True else "false"


def retained_capacity_transition_features(
        snapshot, source_city_id, target_city_id, production_target,
        proposed_turn, deadline_turn):
    """Build the frozen PR95 feature vocabulary from current exact state."""
    if not isinstance(snapshot, AuthoritativeSnapshot):
        raise TypeError("retained capacity features require a snapshot")
    source = snapshot.city(source_city_id)
    target = snapshot.city(target_city_id)
    if (source is None or target is None
            or source.owner != snapshot.player_id
            or target.owner != snapshot.player_id
            or source_city_id == target_city_id
            or source.tile is None or target.tile is None
            or len(tuple(source.surplus or ())) < 2):
        raise ValueError("retained capacity feature city evidence differs")
    if (isinstance(proposed_turn, bool)
            or not isinstance(proposed_turn, int)
            or proposed_turn != snapshot.turn
            or isinstance(deadline_turn, bool)
            or not isinstance(deadline_turn, int)
            or deadline_turn <= proposed_turn):
        raise ValueError("retained capacity feature horizon differs")
    units = tuple(snapshot.units)
    return tuple(sorted({
        "action_category": "city_production",
        "completion_horizon_band": _horizon_band(
            deadline_turn - proposed_turn),
        "cross_city_deficit": "true",
        "exact_queue_match": "true",
        "lifecycle_state": "retained-authoritative-queue",
        "production_target": _normalized(production_target),
        "source_city_disorder": _optional_boolean(source.disorder),
        "source_city_food_surplus_band": _surplus_band(source.surplus[0]),
        "source_city_own_unit_count_band": _count_band(sum(
            unit.tile == source.tile and unit.transported is not True
            for unit in units)),
        "source_city_shield_surplus_band": _surplus_band(source.surplus[1]),
        "source_city_size_band": _size_band(source.size),
        "target_city_own_unit_count_band": _count_band(sum(
            unit.tile == target.tile and unit.transported is not True
            for unit in units)),
        "target_city_size_band": _size_band(target.size),
        "turn_phase_band": _turn_phase(proposed_turn),
    }.items()))


@dataclass(frozen=True)
class FdasRetainedCapacityTransitionQuery:
    schema_version: int
    query_id: str
    game_id: str
    player_id: int
    operation_id: str
    label_id: str
    proposal_event_id: str
    proposed_turn: int
    snapshot_id: str
    revision_id: str
    deficit_atom_id: str
    feature_schema: str
    features: tuple
    status: str
    reason: str
    estimate: object
    interval_lower: object
    interval_upper: object
    model_id: object
    provenance_ids: tuple
    result_hash: str

    def __post_init__(self):
        if self.schema_version != 1:
            raise ValueError("unsupported retained capacity query schema")
        for value, name in (
                (self.query_id, "query ID"), (self.game_id, "game ID"),
                (self.operation_id, "operation ID"),
                (self.label_id, "label ID"),
                (self.proposal_event_id, "proposal event ID"),
                (self.snapshot_id, "snapshot ID"),
                (self.revision_id, "revision ID"),
                (self.deficit_atom_id, "deficit atom ID"),
                (self.reason, "abstention reason")):
            _required_text(value, "retained capacity " + name)
        if (isinstance(self.player_id, bool)
                or not isinstance(self.player_id, int) or self.player_id < 0
                or isinstance(self.proposed_turn, bool)
                or not isinstance(self.proposed_turn, int)
                or self.proposed_turn < 0):
            raise ValueError("retained capacity query numeric identity differs")
        if self.feature_schema != RETAINED_CAPACITY_TRANSITION_FEATURE_SCHEMA:
            raise ValueError("retained capacity query feature schema differs")
        features = tuple(sorted((str(key), str(value))
                                for key, value in self.features))
        if (frozenset(key for key, _value in features) != _FEATURE_NAMES
                or len(features) != len(_FEATURE_NAMES)
                or any(not key or not value for key, value in features)):
            raise ValueError("retained capacity query features differ")
        object.__setattr__(self, "features", features)
        provenance = tuple(sorted(str(value) for value in self.provenance_ids))
        if (not provenance or len(provenance) != len(set(provenance))
                or any(not value for value in provenance)):
            raise ValueError("retained capacity query provenance differs")
        object.__setattr__(self, "provenance_ids", provenance)
        if (self.status != "abstained" or self.reason != _ABSTENTION_REASON
                or any(value is not None for value in (
                    self.estimate, self.interval_lower, self.interval_upper,
                    self.model_id))):
            raise ValueError("retained capacity query must abstain")
        expected_hash = structural_hash(self._semantic())
        if (self.result_hash != expected_hash
                or self.query_id != (
                    "retained-capacity-transition-query-" +
                    expected_hash[:24])):
            raise ValueError("retained capacity query hash differs")

    def _semantic(self):
        return {
            "deficit_atom_id": self.deficit_atom_id,
            "estimate": self.estimate,
            "feature_schema": self.feature_schema,
            "features": dict(self.features),
            "game_id": self.game_id,
            "interval_lower": self.interval_lower,
            "interval_upper": self.interval_upper,
            "label_id": self.label_id,
            "model_id": self.model_id,
            "operation_id": self.operation_id,
            "player_id": self.player_id,
            "proposal_event_id": self.proposal_event_id,
            "proposed_turn": self.proposed_turn,
            "provenance_ids": list(self.provenance_ids),
            "reason": self.reason,
            "revision_id": self.revision_id,
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "status": self.status,
        }

    def to_dict(self):
        return {
            **self._semantic(),
            "action_selection_changed": False,
            "learning_authority": False,
            "policy_authority": False,
            "query_id": self.query_id,
            "readout_authority": False,
            "result_hash": self.result_hash,
            "transition_value_estimated": False,
            "truth_mutated": False,
        }

    @classmethod
    def from_dict(cls, value):
        if any(value.get(name) is not False for name in (
                "action_selection_changed", "learning_authority",
                "policy_authority", "readout_authority",
                "transition_value_estimated", "truth_mutated")):
            raise ValueError("retained capacity query grants authority")
        return cls(
            value["schema_version"], value["query_id"], value["game_id"],
            value["player_id"], value["operation_id"], value["label_id"],
            value["proposal_event_id"], value["proposed_turn"],
            value["snapshot_id"], value["revision_id"],
            value["deficit_atom_id"], value["feature_schema"],
            tuple(sorted(value["features"].items())), value["status"],
            value["reason"], value.get("estimate"),
            value.get("interval_lower"), value.get("interval_upper"),
            value.get("model_id"), tuple(value["provenance_ids"]),
            value["result_hash"])


class FdasRetainedCapacityTransitionQueryBuilder(object):
    """Capture exact proposal-time categorical context and abstain."""

    BUILDER_IDENTITY = RETAINED_CAPACITY_TRANSITION_QUERY_IDENTITY

    @staticmethod
    def build(proposal_event, label, snapshot, revision):
        if not isinstance(label, FdasRetainedCapacityOutcomeLabel):
            raise TypeError("retained capacity query requires typed label")
        if label.status != "pending_product":
            raise ValueError("retained capacity query requires opened label")
        if not isinstance(snapshot, AuthoritativeSnapshot):
            raise TypeError("retained capacity query requires snapshot")
        payload = proposal_event.get("payload", {})
        event_id = proposal_event.get("event_id")
        if (proposal_event.get("type") != "operation_proposed"
                or proposal_event.get("game_id") != label.game_id
                or proposal_event.get("turn") != label.proposed_turn
                or payload.get("mechanism") != _MECHANISM
                or payload.get("operation_type") != _OPERATION_TYPE
                or payload.get("operation_id") != label.operation_id
                or payload.get("operation_digest") != label.operation_digest
                or payload.get("snapshot_id") != label.proposed_snapshot_id
                or payload.get("shadow_only") is not True
                or payload.get("policy_authority") is not False
                or "no-queue-action-submitted" not in payload.get(
                    "provenance", ())):
            raise ValueError("retained capacity query proposal differs")
        _required_text(event_id, "proposal event ID")
        if (snapshot.snapshot_id != label.proposed_snapshot_id
                or snapshot.turn != label.proposed_turn
                or snapshot.identity.game_id != label.game_id
                or snapshot.player_id != label.player_id):
            raise ValueError("retained capacity query snapshot differs")
        if (getattr(revision, "snapshot_id", None) != snapshot.snapshot_id
                or not isinstance(getattr(revision, "revision_id", None), str)
                or revision.record(label.deficit_atom_id) is None):
            raise ValueError("retained capacity query revision differs")
        source = snapshot.city(label.source_city_id)
        target = snapshot.city(label.target_city_id)
        if (source is None or target is None
                or source.owner != label.player_id
                or target.owner != label.player_id
                or source.tile is None or target.tile is None
                or len(tuple(source.surplus or ())) < 2):
            raise ValueError("retained capacity query city evidence differs")
        action = payload.get("next_action", {})
        action_target = action.get("target", {})
        if (action.get("action_type") != "city_production"
                or action.get("city_id") != label.source_city_id
                or action_target.get("production_type")
                    != label.production_target_name):
            raise ValueError("retained capacity query action differs")
        deadline = payload.get("deadline_turn")
        if (isinstance(deadline, bool) or not isinstance(deadline, int)
                or deadline <= label.proposed_turn):
            raise ValueError("retained capacity query deadline differs")
        features = retained_capacity_transition_features(
            snapshot, label.source_city_id, label.target_city_id,
            label.production_target_name, label.proposed_turn, deadline)
        provenance = tuple(sorted((
            FdasRetainedCapacityTransitionQueryBuilder.BUILDER_IDENTITY,
            "deficit-atom:" + label.deficit_atom_id,
            "outcome-label:" + label.label_id,
            "proposal-event:" + event_id,
            "proposal-revision:" + revision.revision_id,
            "snapshot:" + snapshot.snapshot_id,
        )))
        semantic = {
            "deficit_atom_id": label.deficit_atom_id,
            "estimate": None,
            "feature_schema": RETAINED_CAPACITY_TRANSITION_FEATURE_SCHEMA,
            "features": dict(features),
            "game_id": label.game_id,
            "interval_lower": None,
            "interval_upper": None,
            "label_id": label.label_id,
            "model_id": None,
            "operation_id": label.operation_id,
            "player_id": label.player_id,
            "proposal_event_id": event_id,
            "proposed_turn": label.proposed_turn,
            "provenance_ids": list(provenance),
            "reason": _ABSTENTION_REASON,
            "revision_id": revision.revision_id,
            "schema_version": 1,
            "snapshot_id": snapshot.snapshot_id,
            "status": "abstained",
        }
        result_hash = structural_hash(semantic)
        return FdasRetainedCapacityTransitionQuery(
            1, "retained-capacity-transition-query-" + result_hash[:24],
            label.game_id, label.player_id, label.operation_id, label.label_id,
            event_id, label.proposed_turn, snapshot.snapshot_id,
            revision.revision_id, label.deficit_atom_id,
            RETAINED_CAPACITY_TRANSITION_FEATURE_SCHEMA, features,
            "abstained", _ABSTENTION_REASON, None, None, None, None,
            provenance, result_hash)


class FdasRetainedCapacityTransitionQueryStore(object):
    """Atomic query store keyed one-to-one by operation and label."""

    STORE_IDENTITY = RETAINED_CAPACITY_TRANSITION_QUERY_STORE_IDENTITY

    def __init__(self, persistence_identity, queries=(), quarantine_reason=None):
        _required_text(persistence_identity, "query persistence identity")
        self.persistence_identity = persistence_identity
        self.quarantine_reason = quarantine_reason
        self._queries = {}
        self._operations = {}
        self._labels = {}
        for query in queries:
            self._insert(query)

    def _insert(self, query):
        if not isinstance(query, FdasRetainedCapacityTransitionQuery):
            raise TypeError("transition query store requires typed query")
        if (query.query_id in self._queries
                or query.operation_id in self._operations
                or query.label_id in self._labels):
            raise ValueError("duplicate retained capacity transition query")
        self._queries[query.query_id] = query
        self._operations[query.operation_id] = query.query_id
        self._labels[query.label_id] = query.query_id

    @property
    def quarantined(self):
        return self.quarantine_reason is not None

    def queries(self):
        return tuple(self._queries[key] for key in sorted(self._queries))

    def get(self, query_id):
        return self._queries.get(str(query_id))

    def for_operation(self, operation_id):
        query_id = self._operations.get(str(operation_id))
        return None if query_id is None else self._queries[query_id]

    @property
    def store_digest(self):
        return structural_hash(self.to_dict(include_digest=False))

    def record(self, query):
        if self.quarantined:
            raise ValueError("quarantined retained capacity transition store")
        prior = self.get(query.query_id)
        if prior is not None:
            if prior != query:
                raise ValueError("retained capacity transition query collision")
            return prior
        if (query.operation_id in self._operations
                or query.label_id in self._labels):
            raise ValueError("retained capacity transition binding collision")
        self._insert(query)
        return query

    def to_dict(self, include_digest=True):
        value = {
            "persistence_identity": self.persistence_identity,
            "quarantine_reason": self.quarantine_reason,
            "queries": [query.to_dict() for query in self.queries()],
            "schema_version": 1,
            "store_identity": self.STORE_IDENTITY,
        }
        if include_digest:
            value["store_digest"] = self.store_digest
        return value

    def save(self, path):
        if self.quarantined:
            raise ValueError("quarantined retained capacity transition store")
        path = os.path.abspath(path)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".fdas-capacity-transition-", suffix=".json",
            dir=directory or None)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(canonical_json_bytes(self.to_dict()) + b"\n")
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
                    or value.get("schema_version") != 1
                    or value.get("persistence_identity")
                        != persistence_identity):
                raise ValueError("transition query store identity mismatch")
            store = cls(
                persistence_identity,
                tuple(FdasRetainedCapacityTransitionQuery.from_dict(row)
                      for row in value["queries"]),
                value.get("quarantine_reason"))
            if (value.get("store_digest") != store.store_digest
                    or store.quarantined):
                raise ValueError("transition query store digest differs")
            return store
        except (KeyError, OSError, TypeError, UnicodeError, ValueError,
                json.JSONDecodeError) as error:
            return cls(
                persistence_identity,
                quarantine_reason="transition-query-store-load-failed:{}"
                .format(error))
