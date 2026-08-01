"""Truth-free learning bridge from terminal FDAS decision episodes."""

from dataclasses import dataclass

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
