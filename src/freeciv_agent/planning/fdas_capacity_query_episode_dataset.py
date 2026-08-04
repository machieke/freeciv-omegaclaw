"""Outcome-safe rows joining retained-capacity queries to later episodes."""

from dataclasses import dataclass

from ..events.schema import structural_hash
from .fdas_capacity_transition_queries import (
    FdasRetainedCapacityTransitionQuery,
    FdasRetainedCapacityTransitionQueryStore,
)
from .fdas_episodes import DecisionEpisode, DecisionEpisodeStore


RETAINED_CAPACITY_QUERY_EPISODE_ROW_IDENTITY = (
    "fdas-retained-capacity-query-episode-row/1.0")
_TERMINAL_STATUSES = frozenset((
    "effect-without-goal-relief",
    "goal-relief-observed",
    "no-effect-observed",
))
_TERMINAL = "terminal-observed"
_CENSORED = "right-censored"
_CENSORING_REASON = "terminal-episode-not-yet-observed"
_AUTHORITY_FIELDS = (
    "action_selection_changed", "learning_authority", "policy_authority",
    "readout_authority", "transition_value_estimated", "truth_mutated",
)


def _one_provenance(values, prefix):
    matches = tuple(
        value.split(":", 1)[1] for value in values
        if value.startswith(prefix + ":"))
    if len(matches) != 1 or not matches[0]:
        raise ValueError(
            "retained capacity episode lacks one {}".format(prefix))
    return matches[0]


def _validate_episode(query, episode):
    if not isinstance(episode, DecisionEpisode):
        raise TypeError("retained capacity query row requires typed episode")
    delta = episode.observed_delta
    context = dict(episode.context_signature)
    if (episode.game_id != query.game_id
            or episode.player_id != query.player_id
            or episode.operation_id != query.operation_id
            or not isinstance(delta, dict)
            or delta.get("label_id") != query.label_id):
        raise ValueError("retained capacity query episode identity differs")
    if (episode.before_revision_id != query.revision_id
            or episode.after_revision_id is None
            or episode.after_revision_id == query.revision_id):
        raise ValueError("retained capacity query episode revision differs")
    if (_one_provenance(episode.provenance_ids, "proposal-event")
            != query.proposal_event_id
            or _one_provenance(episode.provenance_ids, "outcome-label")
            != query.label_id):
        raise ValueError("retained capacity query episode provenance differs")
    observed_turn = delta.get("observed_turn")
    if (isinstance(observed_turn, bool) or not isinstance(observed_turn, int)
            or observed_turn < query.proposed_turn):
        raise ValueError("retained capacity query observed turn differs")
    if (episode.outcome_status not in _TERMINAL_STATUSES
            or context.get("episode_domain")
                != "retained-replacement-capacity"
            or context.get("proposed_turn") != str(query.proposed_turn)
            or episode.prediction_ids
            or episode.execution_event_id is not None):
        raise ValueError("retained capacity query episode semantics differ")


@dataclass(frozen=True)
class FdasRetainedCapacityQueryEpisodeRow:
    """One proposal-time query with a terminal or censored observation."""

    schema_version: int
    row_id: str
    query: FdasRetainedCapacityTransitionQuery
    episode: object
    observation_status: str
    censoring_reason: object
    result_hash: str

    def __post_init__(self):
        if self.schema_version != 1:
            raise ValueError("unsupported retained capacity query row schema")
        if not isinstance(self.query, FdasRetainedCapacityTransitionQuery):
            raise TypeError("retained capacity query row requires typed query")
        if self.episode is None:
            if (self.observation_status != _CENSORED
                    or self.censoring_reason != _CENSORING_REASON):
                raise ValueError("retained capacity censored row differs")
        else:
            _validate_episode(self.query, self.episode)
            if (self.observation_status != _TERMINAL
                    or self.censoring_reason is not None):
                raise ValueError("retained capacity terminal row differs")
        expected = structural_hash(self._semantic())
        if (self.result_hash != expected
                or self.row_id != (
                    "retained-capacity-query-episode-row-" + expected[:24])):
            raise ValueError("retained capacity query row hash differs")

    def _semantic(self):
        return {
            "censoring_reason": self.censoring_reason,
            "episode": (
                None if self.episode is None else self.episode.to_dict()),
            "observation_status": self.observation_status,
            "query": self.query.to_dict(),
            "row_identity": RETAINED_CAPACITY_QUERY_EPISODE_ROW_IDENTITY,
            "schema_version": self.schema_version,
        }

    @property
    def feature_signature(self):
        return structural_hash({
            "feature_schema": self.query.feature_schema,
            "features": dict(self.query.features),
        })

    @property
    def outcome_status(self):
        return None if self.episode is None else self.episode.outcome_status

    @property
    def observed_turn(self):
        return (None if self.episode is None
                else self.episode.observed_delta["observed_turn"])

    def to_dict(self):
        value = self._semantic()
        value.update({
            "after_revision_id": (
                None if self.episode is None
                else self.episode.after_revision_id),
            "episode_id": (
                None if self.episode is None else self.episode.episode_id),
            "feature_signature": self.feature_signature,
            "observed_turn": self.observed_turn,
            "outcome_status": self.outcome_status,
            "result_hash": self.result_hash,
            "row_id": self.row_id,
        })
        value.update(dict((name, False) for name in _AUTHORITY_FIELDS))
        return value

    @classmethod
    def from_dict(cls, value):
        if any(value.get(name) is not False for name in _AUTHORITY_FIELDS):
            raise ValueError("retained capacity query row grants authority")
        query = FdasRetainedCapacityTransitionQuery.from_dict(value["query"])
        episode = (
            None if value.get("episode") is None
            else DecisionEpisode.from_dict(value["episode"]))
        row = cls(
            value["schema_version"], value["row_id"], query, episode,
            value["observation_status"], value.get("censoring_reason"),
            value["result_hash"])
        expected_fields = {
            "after_revision_id": (
                None if episode is None else episode.after_revision_id),
            "episode_id": None if episode is None else episode.episode_id,
            "feature_signature": row.feature_signature,
            "observed_turn": row.observed_turn,
            "outcome_status": row.outcome_status,
            "row_identity": RETAINED_CAPACITY_QUERY_EPISODE_ROW_IDENTITY,
        }
        if any(value.get(name) != expected
               for name, expected in expected_fields.items()):
            raise ValueError("retained capacity query row projection differs")
        return row

    @classmethod
    def build(cls, query, episode=None):
        observation_status = _CENSORED if episode is None else _TERMINAL
        censoring_reason = _CENSORING_REASON if episode is None else None
        semantic = {
            "censoring_reason": censoring_reason,
            "episode": None if episode is None else episode.to_dict(),
            "observation_status": observation_status,
            "query": query.to_dict(),
            "row_identity": RETAINED_CAPACITY_QUERY_EPISODE_ROW_IDENTITY,
            "schema_version": 1,
        }
        result_hash = structural_hash(semantic)
        return cls(
            1, "retained-capacity-query-episode-row-" + result_hash[:24],
            query, episode, observation_status, censoring_reason, result_hash)


def join_retained_capacity_transition_queries(query_store, episode_store):
    """Join every query once and reject ambiguous or orphaned episodes."""
    if not isinstance(query_store, FdasRetainedCapacityTransitionQueryStore):
        raise TypeError("retained capacity join requires transition store")
    if not isinstance(episode_store, DecisionEpisodeStore):
        raise TypeError("retained capacity join requires episode store")
    if query_store.quarantined or episode_store.quarantined:
        raise ValueError("retained capacity join store is quarantined")

    queries = query_store.queries()
    query_by_operation = dict(
        (query.operation_id, query) for query in queries)
    query_by_label = dict((query.label_id, query) for query in queries)
    episode_by_query = {}
    for episode in episode_store.episodes():
        if not isinstance(episode.observed_delta, dict):
            raise ValueError("retained capacity join episode lacks label")
        label_id = episode.observed_delta.get("label_id")
        by_operation = query_by_operation.get(episode.operation_id)
        by_label = query_by_label.get(label_id)
        if by_operation is None or by_label is None or by_operation != by_label:
            raise ValueError("retained capacity join has orphan episode")
        if by_operation.query_id in episode_by_query:
            raise ValueError("retained capacity join has duplicate episode")
        _validate_episode(by_operation, episode)
        episode_by_query[by_operation.query_id] = episode

    return tuple(sorted((
        FdasRetainedCapacityQueryEpisodeRow.build(
            query, episode_by_query.get(query.query_id))
        for query in queries), key=lambda row: row.row_id))
