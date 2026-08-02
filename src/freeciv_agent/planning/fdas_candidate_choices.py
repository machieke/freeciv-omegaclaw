"""Durable outcome-safe choice sets for FDAS candidate calibration."""

from dataclasses import dataclass, replace
import json
import math
import os
import tempfile

from ..events.schema import canonical_json_bytes, structural_hash
from ..pressure.induction import InductionFeatureQuery
from .fdas import ShadowOperationCandidate
from .fdas_episode_induction import (
    FdasPromotedRuleCandidateImpactEvaluation,
)


CANDIDATE_CHOICE_SCHEMA_VERSION = 1
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


@dataclass(frozen=True)
class FdasCandidateChoice:
    """One offered candidate; nonselected rows are explicitly censored."""

    operation_id: str
    action_key: str
    candidate_hash: str
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
        if self.selection_role not in _SELECTION_ROLES:
            raise ValueError("invalid candidate selection role")

    def to_dict(self):
        return {
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

    @classmethod
    def from_dict(cls, value):
        return cls(
            value["operation_id"], value["action_key"],
            value["candidate_hash"],
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


class FdasCandidateChoiceSetRecorder(object):
    """Capture offered choices, then resolve only the executed candidate."""

    RECORDER_IDENTITY = "fdas-candidate-choice-set-recorder/1.0"

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
                candidate.candidate_hash, row.feature_query,
                row.admissible, row.baseline_rank, row.shadow_rank,
                row.baseline_priority, row.population_baseline_priority,
                row.shadow_priority, row.priority_delta, row.estimated,
                row.reason, prediction_hash,
                ("selected" if row.operation_id == selected_operation_id
                 else "nonselected-censored")))
        identity_material = {
            "evaluation_result_hash": evaluation.result_hash,
            "revision_id": str(revision_id),
            "schema_version": CANDIDATE_CHOICE_SCHEMA_VERSION,
            "selected_operation_id": selected_operation_id,
        }
        choice_set_id = "choice-set-" + structural_hash(
            identity_material)[:32]
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
            (self.RECORDER_IDENTITY,) + tuple(provenance_ids))
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
