"""Truth-free learning bridge and diagnostics for FDAS decision episodes."""

from dataclasses import dataclass
import math

from ..events.schema import structural_hash
from ..pressure.calibration import (
    ContextualConductanceStore,
    ControlCalibrationLedger,
    ControlCalibrationRecord,
)
from .fdas_episodes import DecisionEpisodeStore


@dataclass(frozen=True)
class EpisodeControlPrediction:
    prediction_id: str
    operation_id: str
    route_id: str
    calibration_group: str
    predicted_relief: float
    predicted_success: float
    predicted_cost: tuple
    selection_propensity: object
    frontier_signature: str
    generation: int

    def __post_init__(self):
        for value, name in (
                (self.prediction_id, "prediction ID"),
                (self.operation_id, "operation ID"),
                (self.route_id, "route ID"),
                (self.calibration_group, "calibration group"),
                (self.frontier_signature, "frontier signature")):
            if not isinstance(value, str) or not value:
                raise ValueError("episode control {} is required".format(name))
        if not 0.0 <= float(self.predicted_success) <= 1.0:
            raise ValueError("predicted success must be in 0..1")
        if float(self.predicted_relief) < 0.0:
            raise ValueError("predicted relief must be non-negative")
        if (isinstance(self.generation, bool)
                or not isinstance(self.generation, int)
                or self.generation < 0):
            raise ValueError("prediction generation must be non-negative")
        costs = tuple((str(key), float(value))
                      for key, value in self.predicted_cost)
        if (len({key for key, _value in costs}) != len(costs)
                or any(not key or value < 0.0 for key, value in costs)):
            raise ValueError("predicted costs are invalid")
        object.__setattr__(self, "predicted_cost", tuple(sorted(costs)))
        if (self.selection_propensity is not None
                and not 0.0 < float(self.selection_propensity) <= 1.0):
            raise ValueError("selection propensity must be in (0,1]")

    def to_dict(self):
        return {
            "calibration_group": self.calibration_group,
            "frontier_signature": self.frontier_signature,
            "generation": self.generation,
            "operation_id": self.operation_id,
            "predicted_cost": dict(self.predicted_cost),
            "predicted_relief": float(self.predicted_relief),
            "predicted_success": float(self.predicted_success),
            "prediction_id": self.prediction_id,
            "route_id": self.route_id,
            "selection_propensity": self.selection_propensity,
        }


@dataclass(frozen=True)
class EpisodeLearningResult:
    episode_id: str
    outcome_status: str
    applied: bool
    reason: str
    calibration_record: object
    conductance_update: object
    truth_mutated: bool
    policy_authority: bool
    result_hash: str

    def to_dict(self):
        return {
            "applied": self.applied,
            "calibration_record": (
                None if self.calibration_record is None else
                self.calibration_record.to_dict()),
            "conductance_update": (
                None if self.conductance_update is None else
                self.conductance_update.to_dict()),
            "episode_id": self.episode_id,
            "outcome_status": self.outcome_status,
            "policy_authority": self.policy_authority,
            "reason": self.reason,
            "result_hash": self.result_hash,
            "truth_mutated": self.truth_mutated,
        }


@dataclass(frozen=True)
class EpisodeLearningMetrics:
    outcome_counts: tuple
    episode_count: int
    attributable_terminal_count: int
    confounded_count: int
    calibration_sample_count: int
    contextual_route_count: int
    mean_absolute_relief_error: object
    success_brier_score: object
    conductance_state_hash: str
    truth_mutated: bool = False
    policy_authority: bool = False

    def to_dict(self):
        return {
            "attributable_terminal_count": self.attributable_terminal_count,
            "calibration_sample_count": self.calibration_sample_count,
            "conductance_state_hash": self.conductance_state_hash,
            "confounded_count": self.confounded_count,
            "contextual_route_count": self.contextual_route_count,
            "episode_count": self.episode_count,
            "mean_absolute_relief_error": self.mean_absolute_relief_error,
            "outcome_counts": dict(self.outcome_counts),
            "policy_authority": self.policy_authority,
            "success_brier_score": self.success_brier_score,
            "truth_mutated": self.truth_mutated,
        }


@dataclass(frozen=True)
class EpisodeLearningExplanation:
    episode_id: str
    outcome_status: str
    learning_eligible: bool
    reason: str
    prediction: object
    calibration_record: object
    contextual_conductance: object
    truth_mutated: bool
    policy_authority: bool
    explanation_hash: str

    def to_dict(self):
        return {
            "calibration_record": (
                None if self.calibration_record is None
                else self.calibration_record.to_dict()),
            "contextual_conductance": self.contextual_conductance,
            "episode_id": self.episode_id,
            "explanation_hash": self.explanation_hash,
            "learning_eligible": self.learning_eligible,
            "outcome_status": self.outcome_status,
            "policy_authority": self.policy_authority,
            "prediction": (
                None if self.prediction is None else self.prediction.to_dict()),
            "reason": self.reason,
            "truth_mutated": self.truth_mutated,
        }


class FdasEpisodeLearningAdapter(object):
    """Apply attributable episode outcomes to contextual control state only."""

    ADAPTER_IDENTITY = "fdas-episode-control-learning/1.0"
    _ELIGIBLE = frozenset((
        "goal-relief-observed",
        "effect-without-goal-relief",
        "no-effect-observed",
    ))

    def __init__(self, episode_store, predictions,
                 calibration_ledger=None, conductance_store=None):
        if not isinstance(episode_store, DecisionEpisodeStore):
            raise TypeError("episode learning requires DecisionEpisodeStore")
        predictions = tuple(predictions)
        if any(not isinstance(value, EpisodeControlPrediction)
               for value in predictions):
            raise TypeError(
                "episode learning predictions have the wrong type")
        if len({value.prediction_id for value in predictions}) != len(
                predictions):
            raise ValueError("episode learning prediction IDs must be unique")
        self.episode_store = episode_store
        self.predictions = dict(
            (value.prediction_id, value) for value in predictions)
        self.calibration_ledger = (
            calibration_ledger or ControlCalibrationLedger())
        self.conductance_store = (
            conductance_store or ContextualConductanceStore())

    @staticmethod
    def _result(episode, applied, reason, record=None, update=None):
        semantic = {
            "applied": bool(applied),
            "calibration_record": (
                None if record is None else record.to_dict()),
            "conductance_update": (
                None if update is None else update.to_dict()),
            "episode_id": episode.episode_id,
            "outcome_status": episode.outcome_status,
            "policy_authority": False,
            "reason": reason,
            "truth_mutated": False,
        }
        return EpisodeLearningResult(
            episode.episode_id, episode.outcome_status, bool(applied), reason,
            record, update, False, False, structural_hash(semantic))

    def apply(self, episode_id, realized_cost=()):
        if self.episode_store.quarantined:
            raise ValueError("quarantined episode store cannot train control")
        episode = self.episode_store.get(episode_id)
        if episode is None:
            raise KeyError("unknown decision episode")
        if episode.outcome_status not in self._ELIGIBLE:
            return self._result(
                episode, False, "episode-outcome-not-attributable-for-learning")
        if (len(episode.prediction_ids) != 1
                or episode.prediction_ids[0] not in self.predictions):
            return self._result(
                episode, False,
                "episode-requires-one-current-control-prediction")
        prediction = self.predictions[episode.prediction_ids[0]]
        if prediction.operation_id != episode.operation_id:
            return self._result(
                episode, False, "prediction-operation-mismatch")
        realized_relief = sum(
            value for _goal_id, value in episode.realized_goal_relief)
        effect_observed = bool(episode.attributed_effects)
        success = bool(
            episode.outcome_status == "goal-relief-observed"
            or (episode.outcome_status == "effect-without-goal-relief"
                and effect_observed))
        context_signature = "{}:episode-context-{}".format(
            prediction.calibration_group,
            structural_hash(dict(episode.context_signature))[:24])
        relief_source = {
            "goal-relief-observed": "authoritative-episode-goal-relief",
            "effect-without-goal-relief": (
                "authoritative-effect-without-goal-relief"),
            "no-effect-observed": "authoritative-no-effect-window-closed",
        }[episode.outcome_status] + ":episode:" + episode.episode_id
        record = ControlCalibrationRecord(
            context_signature=context_signature,
            rule_or_operation_id=prediction.route_id,
            predicted_relief=prediction.predicted_relief,
            realized_relief=realized_relief,
            predicted_success=prediction.predicted_success,
            success=success,
            predicted_cost=prediction.predicted_cost,
            realized_cost=tuple(realized_cost),
            selection_propensity=prediction.selection_propensity,
            update_targets=("route_conductance",),
            frontier_signature=prediction.frontier_signature,
            generation=prediction.generation,
            relief_source=relief_source,
            episode_id=episode.episode_id,
        )
        updates = self.calibration_ledger.apply(record, {
            "route_conductance": self.conductance_store,
        })
        update = updates["route_conductance"]
        reason = (
            "contextual-control-update-applied" if update.applied else
            "duplicate-episode-control-update")
        return self._result(
            episode, update.applied, reason, record, update)

    def metrics(self):
        episodes = self.episode_store.episodes()
        counts = {}
        for episode in episodes:
            counts[episode.outcome_status] = (
                counts.get(episode.outcome_status, 0) + 1)
        records = tuple(self.calibration_ledger.records)
        relief_mae = (
            None if not records else
            sum(abs(value.relief_error) for value in records) / len(records))
        brier = (
            None if not records else
            sum((float(value.predicted_success) - float(value.success)) ** 2
                for value in records) / len(records))
        if relief_mae is not None and not math.isfinite(relief_mae):
            raise ValueError("episode learning relief metric is not finite")
        if brier is not None and not math.isfinite(brier):
            raise ValueError("episode learning Brier metric is not finite")
        snapshot = self.conductance_store.snapshot()
        return EpisodeLearningMetrics(
            tuple(sorted(counts.items())),
            len(episodes),
            sum(counts.get(value, 0) for value in self._ELIGIBLE),
            counts.get("confounded-unattributable", 0),
            len(records),
            len(snapshot["routes"]),
            relief_mae,
            brier,
            self.conductance_store.state_hash,
        )

    def explain(self, episode_id):
        episode = self.episode_store.get(episode_id)
        if episode is None:
            raise KeyError("unknown decision episode")
        linked_predictions = tuple(
            self.predictions[value] for value in episode.prediction_ids
            if value in self.predictions)
        prediction = linked_predictions[0] if len(linked_predictions) == 1 else None
        records = tuple(
            value for value in self.calibration_ledger.records
            if value.episode_id == episode.episode_id)
        if len(records) > 1:
            raise ValueError("episode has ambiguous calibration records")
        record = records[0] if records else None
        conductance = None
        if record is not None:
            conductance = self.conductance_store.value(
                record.rule_or_operation_id,
                record.context_signature,
                record.frontier_signature,
                record.generation)
        if episode.outcome_status not in self._ELIGIBLE:
            eligible = False
            reason = "episode-outcome-not-attributable-for-learning"
        elif len(episode.prediction_ids) != 1 or prediction is None:
            eligible = False
            reason = "episode-requires-one-current-control-prediction"
        elif prediction.operation_id != episode.operation_id:
            eligible = False
            reason = "prediction-operation-mismatch"
        elif record is None:
            eligible = True
            reason = "eligible-not-yet-applied"
        else:
            eligible = True
            reason = "contextual-control-sample-recorded"
        semantic = {
            "calibration_record_id": (
                None if record is None else record.record_id),
            "contextual_conductance": conductance,
            "episode_id": episode.episode_id,
            "learning_eligible": eligible,
            "outcome_status": episode.outcome_status,
            "policy_authority": False,
            "prediction_id": (
                None if prediction is None else prediction.prediction_id),
            "reason": reason,
            "truth_mutated": False,
        }
        return EpisodeLearningExplanation(
            episode.episode_id, episode.outcome_status, eligible, reason,
            prediction, record, conductance, False, False,
            structural_hash(semantic))
