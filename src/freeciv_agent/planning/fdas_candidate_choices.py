"""Durable outcome-safe choice sets for FDAS candidate calibration."""

from dataclasses import dataclass, replace
import json
import math
import os
import tempfile

from ..events.schema import canonical_json_bytes, structural_hash
from ..pressure.induction import InductionEpisode, InductionFeatureQuery
from ..pressure.scheduler import OperationScore
from .fdas import ShadowOperationCandidate
from .fdas_episode_induction import (
    FdasPromotedRuleCandidateImpactEvaluation,
)


CANDIDATE_CHOICE_SCHEMA_VERSION = 1
DEFENSE_CANDIDATE_CHOICE_SURFACE = "fdas-defense-choice-surface/1.0"
DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES = (
    "fdas-shadow:city-garrison-deficit:unit_move",
    "fdas-shadow:unit-fortification-opportunity:unit_fortify",
)
DEFENSE_CANDIDATE_CHOICE_SELECTION_ACTION_TYPES = (
    "unit_fortify", "unit_move")
_SELECTION_ROLES = frozenset(("selected", "nonselected-censored"))
_EXECUTION_STATES = frozenset((
    "pending", "accepted", "rejected", "not-applicable"))
_OUTCOME_STATES = frozenset((
    "pending-execution", "pending-observation", "observed",
    "censored-no-selection", "censored-execution-rejected",
    "censored-no-linked-episode"))


def _optional_string(value, name):
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError("choice set {} must be non-empty or absent".format(
            name))


def _finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("choice set {} must be finite".format(name))
    return value


def _query_from_dict(value):
    if not isinstance(value, dict) or "outcome" in value:
        raise ValueError("candidate choice requires an outcome-free query")
    return InductionFeatureQuery(
        value["query_id"], tuple(tuple(row) for row in value["context"]),
        tuple(value["features"]), tuple(value.get("provenance_ids", ())))


def unambiguous_defense_choice_surface_candidates(
        candidates, legal_action_json):
    """Return exact surface bindings whose action maps to one operation."""
    candidates = tuple(candidates)
    if any(not isinstance(value, ShadowOperationCandidate)
           for value in candidates):
        raise TypeError("defense surface requires shadow candidates")
    legal_action_json = frozenset(legal_action_json)
    scoped = tuple(
        value for value in candidates
        if (value.operation.operation_type
            in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES
            and value.legal_bound
            and value.action_key in legal_action_json))
    action_key_counts = {}
    for candidate in scoped:
        action_key_counts[candidate.action_key] = (
            action_key_counts.get(candidate.action_key, 0) + 1)
    ambiguous = tuple(sorted(
        key for key, count in action_key_counts.items() if count > 1))
    unique = tuple(sorted(
        (value for value in scoped
         if action_key_counts[value.action_key] == 1),
        key=lambda value: value.operation.operation_id))
    return unique, ambiguous


def candidate_choice_lineage_id(candidate, game_id):
    """Identify a game-local actor/target/action lifecycle across route steps."""
    if not isinstance(candidate, ShadowOperationCandidate):
        raise TypeError("candidate lineage requires shadow candidate")
    if not isinstance(game_id, str) or not game_id:
        raise ValueError("candidate lineage requires game identity")
    actors = tuple(sorted(
        "{}:{}".format(value.actor_class, value.actor_id)
        for value in candidate.operation.participants))
    if not actors:
        raise ValueError("candidate lineage requires operation participants")
    return "candidate-lineage-" + structural_hash({
        "actors": list(actors),
        "game_id": game_id,
        "operation_type": candidate.operation.operation_type,
        "target_ref": candidate.operation.target_ref,
    })[:32]


def _choice_set_identity(
        game_id, player_id, turn, snapshot_id, revision_id,
        evaluation_result_hash, operation_type, outcome_target,
        global_baseline_selected_operation_id,
        category_baseline_selected_operation_id, selected_operation_id,
        choices, provenance_ids):
    """Bind an ID to every immutable choice-set field.

    A decision loop may evaluate the same revision and selected operation more
    than once with different selection provenance.  Those are distinct
    evidence records, not mutable transitions of one record.
    """
    return "choice-set-" + structural_hash({
        "category_baseline_selected_operation_id": (
            category_baseline_selected_operation_id),
        "choices": [value.to_dict() for value in sorted(
            choices, key=lambda row: row.operation_id)],
        "evaluation_result_hash": evaluation_result_hash,
        "game_id": game_id,
        "global_baseline_selected_operation_id": (
            global_baseline_selected_operation_id),
        "operation_type": operation_type,
        "outcome_target": outcome_target,
        "player_id": int(player_id),
        "provenance_ids": sorted(str(value) for value in provenance_ids),
        "revision_id": str(revision_id),
        "schema_version": CANDIDATE_CHOICE_SCHEMA_VERSION,
        "selected_operation_id": selected_operation_id,
        "snapshot_id": snapshot_id,
        "turn": int(turn),
    })[:32]


@dataclass(frozen=True)
class FdasCandidateChoice:
    """One offered candidate; nonselected rows are explicitly censored."""

    operation_id: str
    action_key: str
    candidate_hash: str
    candidate_lineage_id: object
    feature_query: InductionFeatureQuery
    admissible: bool
    baseline_rank: object
    shadow_rank: object
    baseline_priority: float
    population_baseline_priority: float
    shadow_priority: float
    priority_delta: float
    estimated: bool
    estimate_reason: str
    prediction_result_hash: object
    selection_role: str

    def __post_init__(self):
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.action_key, "action key"),
                (self.candidate_hash, "candidate hash"),
                (self.estimate_reason, "estimate reason")):
            if not isinstance(value, str) or not value:
                raise ValueError("choice {} is required".format(name))
        if not isinstance(self.feature_query, InductionFeatureQuery):
            raise TypeError("choice requires an outcome-free feature query")
        if self.feature_query.to_dict().get("outcome") is not None:
            raise ValueError("choice query cannot carry an outcome")
        for name in (
                "baseline_priority", "population_baseline_priority",
                "shadow_priority", "priority_delta"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        for name in ("baseline_rank", "shadow_rank"):
            rank = getattr(self, name)
            if (rank is not None and (
                    isinstance(rank, bool) or not isinstance(rank, int)
                    or rank < 1)):
                raise ValueError("choice {} is invalid".format(name))
        _optional_string(self.prediction_result_hash, "prediction hash")
        _optional_string(self.candidate_lineage_id, "candidate lineage ID")
        if self.selection_role not in _SELECTION_ROLES:
            raise ValueError("invalid candidate selection role")

    def to_dict(self):
        value = {
            "action_key": self.action_key,
            "admissible": bool(self.admissible),
            "baseline_priority": float(self.baseline_priority),
            "baseline_rank": self.baseline_rank,
            "candidate_hash": self.candidate_hash,
            "estimated": bool(self.estimated),
            "estimate_reason": self.estimate_reason,
            "feature_query": self.feature_query.to_dict(),
            "operation_id": self.operation_id,
            "population_baseline_priority": float(
                self.population_baseline_priority),
            "prediction_result_hash": self.prediction_result_hash,
            "priority_delta": float(self.priority_delta),
            "selection_role": self.selection_role,
            "shadow_priority": float(self.shadow_priority),
            "shadow_rank": self.shadow_rank,
        }
        if self.candidate_lineage_id is not None:
            value["candidate_lineage_id"] = self.candidate_lineage_id
        return value

    @classmethod
    def from_dict(cls, value):
        return cls(
            value["operation_id"], value["action_key"],
            value["candidate_hash"],
            value.get("candidate_lineage_id"),
            _query_from_dict(value["feature_query"]),
            value["admissible"], value.get("baseline_rank"),
            value.get("shadow_rank"), value["baseline_priority"],
            value["population_baseline_priority"], value["shadow_priority"],
            value["priority_delta"], value["estimated"],
            value["estimate_reason"], value.get("prediction_result_hash"),
            value["selection_role"])


@dataclass(frozen=True)
class FdasCandidateChoiceSet:
    """A complete category-local decision set and its selected-only label."""

    schema_version: int
    choice_set_id: str
    game_id: str
    player_id: int
    turn: int
    snapshot_id: str
    revision_id: str
    evaluation_result_hash: str
    operation_type: str
    outcome_target: str
    global_baseline_selected_operation_id: object
    category_baseline_selected_operation_id: str
    selected_operation_id: object
    choices: tuple
    execution_status: str
    execution_event_id: object
    selected_episode_id: object
    outcome_status: str
    outcome_label_id: object
    observed_outcome: object
    observed_revision_id: object
    provenance_ids: tuple

    def __post_init__(self):
        if self.schema_version != CANDIDATE_CHOICE_SCHEMA_VERSION:
            raise ValueError("unsupported candidate choice schema")
        for value, name in (
                (self.choice_set_id, "ID"), (self.game_id, "game ID"),
                (self.snapshot_id, "snapshot ID"),
                (self.revision_id, "revision ID"),
                (self.evaluation_result_hash, "evaluation hash"),
                (self.operation_type, "operation type"),
                (self.outcome_target, "outcome target"),
                (self.category_baseline_selected_operation_id,
                 "category baseline operation ID")):
            if not isinstance(value, str) or not value:
                raise ValueError("choice set {} is required".format(name))
        if (isinstance(self.player_id, bool)
                or not isinstance(self.player_id, int) or self.player_id < 0):
            raise ValueError("choice set player ID must be non-negative")
        if (isinstance(self.turn, bool)
                or not isinstance(self.turn, int) or self.turn < 0):
            raise ValueError("choice set turn must be non-negative")
        for value, name in (
                (self.global_baseline_selected_operation_id,
                 "global baseline operation ID"),
                (self.selected_operation_id, "selected operation ID"),
                (self.execution_event_id, "execution event ID"),
                (self.selected_episode_id, "selected episode ID"),
                (self.outcome_label_id, "outcome label ID"),
                (self.observed_revision_id, "observed revision ID")):
            _optional_string(value, name)
        choices = tuple(self.choices)
        if (not choices
                or any(not isinstance(value, FdasCandidateChoice)
                       for value in choices)):
            raise TypeError("choice set requires typed choices")
        choices = tuple(sorted(choices, key=lambda row: row.operation_id))
        if len({row.operation_id for row in choices}) != len(choices):
            raise ValueError("choice set operation IDs must be unique")
        if len({row.action_key for row in choices}) != len(choices):
            raise ValueError("choice set action keys must be unique")
        object.__setattr__(self, "choices", choices)
        selected_rows = tuple(
            row for row in choices if row.selection_role == "selected")
        if self.selected_operation_id is None:
            if selected_rows:
                raise ValueError("unselected choice set contains selected row")
        elif (len(selected_rows) != 1
              or selected_rows[0].operation_id
              != self.selected_operation_id):
            raise ValueError("choice set selected row differs from selection")
        if (self.category_baseline_selected_operation_id
                not in {row.operation_id for row in choices}):
            raise ValueError("category baseline is absent from choice set")
        if self.execution_status not in _EXECUTION_STATES:
            raise ValueError("invalid choice set execution status")
        if self.outcome_status not in _OUTCOME_STATES:
            raise ValueError("invalid choice set outcome status")
        if self.observed_outcome is not None and not isinstance(
                self.observed_outcome, bool):
            raise TypeError("observed choice outcome must be boolean or absent")
        if self.outcome_status == "observed":
            if (self.observed_outcome is None or self.outcome_label_id is None
                    or self.selected_episode_id is None
                    or self.observed_revision_id is None):
                raise ValueError("observed choice outcome is incomplete")
        elif self.observed_outcome is not None:
            raise ValueError("unobserved choice set cannot carry an outcome")
        provenance = tuple(sorted(str(value) for value in self.provenance_ids))
        if (any(not value for value in provenance)
                or len(provenance) != len(set(provenance))):
            raise ValueError("choice set provenance must be unique strings")
        object.__setattr__(self, "provenance_ids", provenance)

    @property
    def immutable_digest(self):
        return structural_hash({
            "category_baseline_selected_operation_id": (
                self.category_baseline_selected_operation_id),
            "choice_set_id": self.choice_set_id,
            "choices": [row.to_dict() for row in self.choices],
            "evaluation_result_hash": self.evaluation_result_hash,
            "game_id": self.game_id,
            "global_baseline_selected_operation_id": (
                self.global_baseline_selected_operation_id),
            "operation_type": self.operation_type,
            "outcome_target": self.outcome_target,
            "player_id": self.player_id,
            "provenance_ids": list(self.provenance_ids),
            "revision_id": self.revision_id,
            "schema_version": self.schema_version,
            "selected_operation_id": self.selected_operation_id,
            "snapshot_id": self.snapshot_id,
            "turn": self.turn,
        })

    def to_dict(self):
        return {
            "category_baseline_selected_operation_id": (
                self.category_baseline_selected_operation_id),
            "choice_set_id": self.choice_set_id,
            "choices": [row.to_dict() for row in self.choices],
            "evaluation_result_hash": self.evaluation_result_hash,
            "execution_event_id": self.execution_event_id,
            "execution_status": self.execution_status,
            "game_id": self.game_id,
            "global_baseline_selected_operation_id": (
                self.global_baseline_selected_operation_id),
            "immutable_digest": self.immutable_digest,
            "observed_outcome": self.observed_outcome,
            "observed_revision_id": self.observed_revision_id,
            "operation_type": self.operation_type,
            "outcome_label_id": self.outcome_label_id,
            "outcome_status": self.outcome_status,
            "outcome_target": self.outcome_target,
            "player_id": self.player_id,
            "provenance_ids": list(self.provenance_ids),
            "revision_id": self.revision_id,
            "schema_version": self.schema_version,
            "selected_episode_id": self.selected_episode_id,
            "selected_operation_id": self.selected_operation_id,
            "snapshot_id": self.snapshot_id,
            "turn": self.turn,
        }

    @classmethod
    def from_dict(cls, value):
        result = cls(
            value["schema_version"], value["choice_set_id"],
            value["game_id"], value["player_id"], value["turn"],
            value["snapshot_id"], value["revision_id"],
            value["evaluation_result_hash"], value["operation_type"],
            value["outcome_target"],
            value.get("global_baseline_selected_operation_id"),
            value["category_baseline_selected_operation_id"],
            value.get("selected_operation_id"),
            tuple(FdasCandidateChoice.from_dict(row)
                  for row in value["choices"]),
            value["execution_status"], value.get("execution_event_id"),
            value.get("selected_episode_id"), value["outcome_status"],
            value.get("outcome_label_id"), value.get("observed_outcome"),
            value.get("observed_revision_id"),
            tuple(value.get("provenance_ids", ())))
        if (value.get("immutable_digest") is not None
                and value["immutable_digest"] != result.immutable_digest):
            raise ValueError("candidate choice immutable digest mismatch")
        return result


class FdasCandidateChoiceSetStore(object):
    """Atomic, idempotent store for selected-only calibration evidence."""

    STORE_IDENTITY = "fdas-candidate-choice-set-store/1.0"

    def __init__(self, persistence_identity, choice_sets=(),
                 quarantine_reason=None):
        if not isinstance(persistence_identity, str) or not persistence_identity:
            raise ValueError("choice set persistence identity is required")
        self.persistence_identity = persistence_identity
        self.quarantine_reason = quarantine_reason
        self._choice_sets = {}
        for value in choice_sets:
            self.record(value)

    @property
    def quarantined(self):
        return self.quarantine_reason is not None

    @property
    def store_digest(self):
        return structural_hash(self.to_dict(include_digest=False))

    def choice_sets(self):
        return tuple(self._choice_sets[key] for key in sorted(
            self._choice_sets))

    def get(self, choice_set_id):
        return self._choice_sets.get(str(choice_set_id))

    def for_episode(self, episode_id):
        matches = tuple(
            value for value in self.choice_sets()
            if value.selected_episode_id == str(episode_id))
        if len(matches) > 1:
            raise ValueError("episode is linked to multiple choice sets")
        return matches[0] if matches else None

    def record(self, value):
        if self.quarantined:
            raise ValueError("quarantined choice store cannot record")
        if not isinstance(value, FdasCandidateChoiceSet):
            raise TypeError("choice store accepts FdasCandidateChoiceSet values")
        prior = self._choice_sets.get(value.choice_set_id)
        if prior is not None:
            if prior == value:
                return prior
            if prior.immutable_digest != value.immutable_digest:
                raise ValueError("candidate choice set identity collision")
            allowed = {
                "pending": frozenset(("pending", "accepted", "rejected")),
                "accepted": frozenset(("accepted",)),
                "rejected": frozenset(("rejected",)),
                "not-applicable": frozenset(("not-applicable",)),
            }
            if value.execution_status not in allowed[prior.execution_status]:
                raise ValueError("invalid candidate choice execution transition")
            outcome_allowed = {
                "pending-execution": frozenset((
                    "pending-execution", "pending-observation",
                    "censored-execution-rejected",
                    "censored-no-linked-episode")),
                "pending-observation": frozenset((
                    "pending-observation", "observed")),
                "observed": frozenset(("observed",)),
                "censored-no-selection": frozenset((
                    "censored-no-selection",)),
                "censored-execution-rejected": frozenset((
                    "censored-execution-rejected",)),
                "censored-no-linked-episode": frozenset((
                    "censored-no-linked-episode",)),
            }
            if value.outcome_status not in outcome_allowed[prior.outcome_status]:
                raise ValueError("invalid candidate choice outcome transition")
        self._choice_sets[value.choice_set_id] = value
        return value

    def to_dict(self, include_digest=True):
        value = {
            "choice_sets": [row.to_dict() for row in self.choice_sets()],
            "persistence_identity": self.persistence_identity,
            "quarantine_reason": self.quarantine_reason,
            "schema_version": CANDIDATE_CHOICE_SCHEMA_VERSION,
            "store_identity": self.STORE_IDENTITY,
        }
        if include_digest:
            value["store_digest"] = self.store_digest
        return value

    def save(self, path):
        if self.quarantined:
            raise ValueError("quarantined choice store cannot save")
        path = os.path.abspath(path)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".fdas-candidate-choices-", suffix=".json",
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
                    != CANDIDATE_CHOICE_SCHEMA_VERSION
                    or value.get("persistence_identity")
                    != persistence_identity):
                raise ValueError("candidate choice store identity mismatch")
            result = cls(
                persistence_identity,
                tuple(FdasCandidateChoiceSet.from_dict(row)
                      for row in value["choice_sets"]),
                value.get("quarantine_reason"))
            if (value.get("store_digest") is not None
                    and value["store_digest"] != result.store_digest):
                raise ValueError("candidate choice store digest mismatch")
            return result
        except (KeyError, OSError, TypeError, UnicodeError,
                ValueError, json.JSONDecodeError) as error:
            return cls(
                persistence_identity,
                quarantine_reason="candidate-choice-store-load-failed:{}"
                .format(error))


def combine_candidate_choice_stores(stores, persistence_identity):
    """Combine independent exact-scope stores without pseudo-replication."""
    stores = tuple(stores)
    if not stores:
        raise ValueError("candidate choice cohort requires a source store")
    if not isinstance(persistence_identity, str) or not persistence_identity:
        raise ValueError("candidate choice cohort identity is required")
    if any(not isinstance(value, FdasCandidateChoiceSetStore)
           for value in stores):
        raise TypeError("candidate choice cohort requires typed stores")
    if any(value.quarantined for value in stores):
        raise ValueError("quarantined choice store cannot enter cohort")
    identities = tuple(value.persistence_identity for value in stores)
    digests = tuple(value.store_digest for value in stores)
    if len(identities) != len(set(identities)):
        raise ValueError("candidate choice cohort identities overlap")
    if len(digests) != len(set(digests)):
        raise ValueError("candidate choice cohort artifacts overlap")
    rows = tuple(row for store in stores for row in store.choice_sets())
    scopes = set((row.operation_type, row.outcome_target) for row in rows)
    if len(scopes) > 1:
        raise ValueError("candidate choice cohort scopes differ")
    choice_set_ids = tuple(row.choice_set_id for row in rows)
    execution_event_ids = tuple(
        row.execution_event_id for row in rows
        if row.execution_event_id is not None)
    episode_ids = tuple(
        row.selected_episode_id for row in rows
        if row.selected_episode_id is not None)
    for values, name in (
            (choice_set_ids, "choice set"),
            (execution_event_ids, "execution event"),
            (episode_ids, "selected episode")):
        if len(values) != len(set(values)):
            raise ValueError(
                "candidate choice cohort {} lineage overlaps".format(name))
    return FdasCandidateChoiceSetStore(persistence_identity, rows)


class FdasCandidateChoiceSetRecorder(object):
    """Capture offered choices, then resolve only the executed candidate."""

    RECORDER_IDENTITY = "fdas-candidate-choice-set-recorder/1.1"

    def __init__(self, store):
        if not isinstance(store, FdasCandidateChoiceSetStore):
            raise TypeError("candidate choice recorder requires typed store")
        self.store = store

    def capture(self, evaluation, candidates, snapshot, revision_id,
                selected_action_key, provenance_ids=()):
        if not isinstance(
                evaluation, FdasPromotedRuleCandidateImpactEvaluation):
            raise TypeError("choice capture requires candidate evaluation")
        if evaluation.status != "evaluated" or evaluation.impact is None:
            raise ValueError("choice capture requires evaluated candidate impact")
        if evaluation.snapshot_id != snapshot.snapshot_id:
            raise ValueError("choice capture evaluation is stale")
        candidates = tuple(candidates)
        if any(not isinstance(value, ShadowOperationCandidate)
               for value in candidates):
            raise TypeError("choice capture requires shadow candidates")
        candidate_by_id = dict(
            (value.operation.operation_id, value) for value in candidates)
        impact_rows = evaluation.impact.rows
        if any(row.operation_id not in candidate_by_id for row in impact_rows):
            raise ValueError("choice impact row lacks candidate")
        selected_matches = tuple(
            row.operation_id for row in impact_rows
            if (selected_action_key is not None
                and candidate_by_id[row.operation_id].action_key
                == selected_action_key))
        if len(selected_matches) > 1:
            raise ValueError("selected action matches multiple candidates")
        selected_operation_id = (
            selected_matches[0] if selected_matches else None)
        choices = []
        for row in impact_rows:
            candidate = candidate_by_id[row.operation_id]
            if row.feature_query is None:
                raise ValueError("choice row lacks outcome-free feature query")
            prediction_hash = (
                None if row.prediction is None
                else row.prediction.result_hash)
            choices.append(FdasCandidateChoice(
                row.operation_id, candidate.action_key,
                candidate.candidate_hash,
                candidate_choice_lineage_id(
                    candidate, snapshot.identity.game_id),
                row.feature_query,
                row.admissible, row.baseline_rank, row.shadow_rank,
                row.baseline_priority, row.population_baseline_priority,
                row.shadow_priority, row.priority_delta, row.estimated,
                row.reason, prediction_hash,
                ("selected" if row.operation_id == selected_operation_id
                 else "nonselected-censored")))
        provenance = (self.RECORDER_IDENTITY,) + tuple(provenance_ids)
        choice_set_id = _choice_set_identity(
            snapshot.identity.game_id, snapshot.player_id, snapshot.turn,
            snapshot.snapshot_id, revision_id, evaluation.result_hash,
            evaluation.operation_type, evaluation.outcome_target,
            evaluation.global_baseline_selected_operation_id,
            evaluation.baseline_selected_operation_id,
            selected_operation_id, choices, provenance)
        result = FdasCandidateChoiceSet(
            CANDIDATE_CHOICE_SCHEMA_VERSION, choice_set_id,
            snapshot.identity.game_id, snapshot.player_id, snapshot.turn,
            snapshot.snapshot_id, str(revision_id), evaluation.result_hash,
            evaluation.operation_type, evaluation.outcome_target,
            evaluation.global_baseline_selected_operation_id,
            evaluation.baseline_selected_operation_id,
            selected_operation_id, tuple(choices),
            "pending" if selected_operation_id is not None else "not-applicable",
            None, None,
            ("pending-execution" if selected_operation_id is not None
             else "censored-no-selection"),
            None, None, None,
            provenance)
        return self.store.record(result)

    def capture_defense_surface(
            self, candidates, scores, snapshot, revision_id,
            selected_action_key, outcome_target, feature_queries,
            global_baseline_selected_operation_id=None, provenance_ids=()):
        """Capture exact legal move/fortify choices without scoring claims."""
        candidates = tuple(candidates)
        scores = tuple(scores)
        if any(not isinstance(value, ShadowOperationCandidate)
               for value in candidates):
            raise TypeError("defense surface requires shadow candidates")
        if any(not isinstance(value, OperationScore) for value in scores):
            raise TypeError("defense surface requires typed operation scores")
        if not isinstance(outcome_target, str) or not outcome_target:
            raise ValueError("defense surface requires an outcome target")
        if not isinstance(feature_queries, dict):
            raise TypeError("defense surface requires feature-query mapping")
        score_by_id = dict((value.operation_id, value) for value in scores)
        if len(score_by_id) != len(scores):
            raise ValueError("defense surface score IDs overlap")
        scoped, _ambiguous = (
            unambiguous_defense_choice_surface_candidates(
                candidates, snapshot.legal_action_json))
        if not scoped:
            raise ValueError("defense surface has no exact legal candidates")
        if any(value.operation.operation_id not in score_by_id
               for value in scoped):
            raise ValueError("defense surface candidate lacks score")
        if any(value.operation.operation_id not in feature_queries
               for value in scoped):
            raise ValueError("defense surface candidate lacks feature query")
        ranked = tuple(sorted(
            scoped,
            key=lambda value: (
                not score_by_id[value.operation.operation_id].admissible,
                -score_by_id[value.operation.operation_id].priority,
                value.operation.operation_id)))
        admissible = tuple(
            value for value in ranked
            if score_by_id[value.operation.operation_id].admissible)
        if not admissible:
            raise ValueError("defense surface has no admissible candidates")
        baseline_rank = dict(
            (value.operation.operation_id, index + 1)
            for index, value in enumerate(admissible))
        selected_matches = tuple(
            value.operation.operation_id for value in scoped
            if (selected_action_key is not None
                and value.action_key == selected_action_key))
        if len(selected_matches) > 1:
            raise ValueError("selected action matches multiple candidates")
        selected_operation_id = (
            selected_matches[0] if selected_matches else None)
        choices = []
        for candidate in ranked:
            operation_id = candidate.operation.operation_id
            score = score_by_id[operation_id]
            query = feature_queries[operation_id]
            if not isinstance(query, InductionFeatureQuery):
                raise TypeError("defense surface requires typed feature query")
            if query.to_dict().get("outcome") is not None:
                raise ValueError("defense surface query cannot carry outcome")
            choices.append(FdasCandidateChoice(
                operation_id, candidate.action_key,
                candidate.candidate_hash,
                candidate_choice_lineage_id(
                    candidate, snapshot.identity.game_id),
                query, score.admissible,
                baseline_rank.get(operation_id),
                baseline_rank.get(operation_id), score.priority,
                score.priority, score.priority, 0.0, False,
                "unmodeled-action-stratum", None,
                ("selected" if operation_id == selected_operation_id
                 else "nonselected-censored")))
        evaluation_material = {
            "candidate_hashes": [
                value.candidate_hash for value in ranked],
            "global_baseline_selected_operation_id": (
                global_baseline_selected_operation_id),
            "operation_type": DEFENSE_CANDIDATE_CHOICE_SURFACE,
            "outcome_target": outcome_target,
            "revision_id": str(revision_id),
            "score_rows": [score_by_id[value.operation.operation_id].to_dict()
                           for value in ranked],
            "snapshot_id": snapshot.snapshot_id,
        }
        evaluation_hash = structural_hash(evaluation_material)
        provenance = (
            self.RECORDER_IDENTITY,
            "fdas-defense-choice-surface-recorder/1.1",
        ) + tuple(provenance_ids)
        choice_set_id = _choice_set_identity(
            snapshot.identity.game_id, snapshot.player_id, snapshot.turn,
            snapshot.snapshot_id, revision_id, evaluation_hash,
            DEFENSE_CANDIDATE_CHOICE_SURFACE, outcome_target,
            global_baseline_selected_operation_id,
            admissible[0].operation.operation_id,
            selected_operation_id, choices, provenance)
        result = FdasCandidateChoiceSet(
            CANDIDATE_CHOICE_SCHEMA_VERSION, choice_set_id,
            snapshot.identity.game_id, snapshot.player_id, snapshot.turn,
            snapshot.snapshot_id, str(revision_id), evaluation_hash,
            DEFENSE_CANDIDATE_CHOICE_SURFACE, outcome_target,
            global_baseline_selected_operation_id,
            admissible[0].operation.operation_id,
            selected_operation_id, tuple(choices),
            "pending" if selected_operation_id is not None else "not-applicable",
            None, None,
            ("pending-execution" if selected_operation_id is not None
             else "censored-no-selection"),
            None, None, None,
            provenance)
        return self.store.record(result)

    def record_execution(self, choice_set_id, accepted, execution_event_id,
                         episode_id=None):
        prior = self.store.get(choice_set_id)
        if prior is None:
            raise KeyError("unknown candidate choice set")
        if prior.selected_operation_id is None:
            raise ValueError("unselected choice set cannot record execution")
        _optional_string(execution_event_id, "execution event ID")
        _optional_string(episode_id, "selected episode ID")
        if accepted:
            status = "pending-observation" if episode_id else (
                "censored-no-linked-episode")
        else:
            if episode_id is not None:
                raise ValueError("rejected execution cannot link an episode")
            status = "censored-execution-rejected"
        return self.store.record(replace(
            prior,
            execution_status="accepted" if accepted else "rejected",
            execution_event_id=execution_event_id,
            selected_episode_id=episode_id,
            outcome_status=status))

    def observe_outcome(self, episode_id, label):
        prior = self.store.for_episode(episode_id)
        if prior is None:
            raise KeyError("episode has no linked candidate choice set")
        if label.episode_id != str(episode_id):
            raise ValueError("choice outcome label episode mismatch")
        if label.target_id != prior.outcome_target:
            raise ValueError("choice outcome target mismatch")
        if label.status != "observed" or label.outcome is None:
            raise ValueError("choice outcome requires an observed label")
        return self.store.record(replace(
            prior,
            outcome_status="observed",
            outcome_label_id=label.label_id,
            observed_outcome=bool(label.outcome),
            observed_revision_id=label.observed_revision_id))


@dataclass(frozen=True)
class FdasCandidateChoiceCalibrationExport:
    """Selected-only examples plus explicit censor accounting."""

    operation_type: str
    outcome_target: str
    source_store_digest: str
    examples: tuple
    choice_set_count: int
    nonselected_censored_count: int
    selected_pending_or_censored_count: int
    no_in_scope_selection_count: int
    result_hash: str

    def __post_init__(self):
        for value, name in (
                (self.operation_type, "operation type"),
                (self.outcome_target, "outcome target"),
                (self.source_store_digest, "source store digest"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("calibration export {} is required".format(
                    name))
        if any(not isinstance(value, InductionEpisode)
               for value in self.examples):
            raise TypeError("calibration export requires induction examples")
        for name in (
                "choice_set_count", "nonselected_censored_count",
                "selected_pending_or_censored_count",
                "no_in_scope_selection_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("calibration export count is invalid")
        if len({value.episode_id for value in self.examples}) != len(
                self.examples):
            raise ValueError("calibration export example IDs overlap")
        semantic = {
            "choice_set_count": self.choice_set_count,
            "examples": [value.to_dict() for value in self.examples],
            "no_in_scope_selection_count": (
                self.no_in_scope_selection_count),
            "nonselected_censored_count": self.nonselected_censored_count,
            "operation_type": self.operation_type,
            "outcome_target": self.outcome_target,
            "policy_authority": False,
            "readout_authority": False,
            "selected_observed_count": len(self.examples),
            "selected_pending_or_censored_count": (
                self.selected_pending_or_censored_count),
            "source_store_digest": self.source_store_digest,
            "truth_mutated": False,
        }
        if self.result_hash != structural_hash(semantic):
            raise ValueError("calibration export result hash differs")

    def to_dict(self):
        return {
            "choice_set_count": self.choice_set_count,
            "examples": [value.to_dict() for value in self.examples],
            "no_in_scope_selection_count": self.no_in_scope_selection_count,
            "nonselected_censored_count": self.nonselected_censored_count,
            "operation_type": self.operation_type,
            "outcome_target": self.outcome_target,
            "policy_authority": False,
            "readout_authority": False,
            "result_hash": self.result_hash,
            "selected_observed_count": len(self.examples),
            "selected_pending_or_censored_count": (
                self.selected_pending_or_censored_count),
            "source_store_digest": self.source_store_digest,
            "truth_mutated": False,
        }


def export_candidate_choice_calibration(
        store, operation_type, outcome_target):
    """Export only observed selected candidates; alternatives stay censored."""
    if not isinstance(store, FdasCandidateChoiceSetStore):
        raise TypeError("candidate calibration requires a typed choice store")
    if store.quarantined:
        raise ValueError("quarantined choice store cannot be calibrated")
    operation_type = str(operation_type)
    outcome_target = str(outcome_target)
    if not operation_type or not outcome_target:
        raise ValueError("candidate calibration scope is required")
    scoped = tuple(
        value for value in store.choice_sets()
        if (value.operation_type == operation_type
            and value.outcome_target == outcome_target))
    if len(scoped) != len(store.choice_sets()):
        raise ValueError("candidate calibration store contains mixed scope")
    examples = []
    for choice_set in scoped:
        if choice_set.outcome_status != "observed":
            continue
        selected = tuple(
            row for row in choice_set.choices
            if row.selection_role == "selected")
        if len(selected) != 1:
            raise ValueError("observed choice set lacks exact selected row")
        row = selected[0]
        selected_action = json.loads(row.action_key)
        selected_actor_id = selected_action.get("actor_id")
        if (isinstance(selected_actor_id, bool)
                or not isinstance(selected_actor_id, int)
                or selected_actor_id < 0):
            raise ValueError(
                "selected candidate calibration lacks unit actor")
        selected_operation_type = dict(
            row.feature_query.context).get("operation_type")
        if selected_operation_type not in (
                DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES):
            raise ValueError(
                "selected candidate calibration operation type differs")
        lineage_provenance = (
            () if row.candidate_lineage_id is None else
            ("candidate-lineage:" + row.candidate_lineage_id,))
        examples.append(InductionEpisode(
            "candidate-example-" + choice_set.choice_set_id,
            row.feature_query.context,
            row.feature_query.features,
            choice_set.observed_outcome,
            tuple(sorted(set(
                row.feature_query.provenance_ids + (
                    "choice-set:" + choice_set.choice_set_id,
                    "game-id:" + choice_set.game_id,
                    "outcome-label:" + choice_set.outcome_label_id,
                    "selected-action-type:" + str(
                        selected_action.get("action_type")),
                    "selected-actor-id:" + str(selected_actor_id),
                    "selected-operation:" + row.operation_id,
                    "selected-operation-type:" + selected_operation_type,
                    "selected-episode:" + choice_set.selected_episode_id,
                ) + lineage_provenance)))))
    examples = tuple(sorted(examples, key=lambda value: value.episode_id))
    semantic = {
        "choice_set_count": len(scoped),
        "examples": [value.to_dict() for value in examples],
        "no_in_scope_selection_count": sum(
            value.selected_operation_id is None for value in scoped),
        "nonselected_censored_count": sum(
            row.selection_role == "nonselected-censored"
            for value in scoped for row in value.choices),
        "operation_type": operation_type,
        "outcome_target": outcome_target,
        "policy_authority": False,
        "readout_authority": False,
        "selected_observed_count": len(examples),
        "selected_pending_or_censored_count": sum(
            value.selected_operation_id is not None
            and value.outcome_status != "observed"
            for value in scoped),
        "source_store_digest": store.store_digest,
        "truth_mutated": False,
    }
    return FdasCandidateChoiceCalibrationExport(
        operation_type, outcome_target, store.store_digest, examples,
        semantic["choice_set_count"],
        semantic["nonselected_censored_count"],
        semantic["selected_pending_or_censored_count"],
        semantic["no_in_scope_selection_count"],
        structural_hash(semantic))
