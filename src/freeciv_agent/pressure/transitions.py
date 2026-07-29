"""Typed, conservative expected-transition models for pressure control.

Transition models are control-layer predictors.  They consume immutable copies
of authoritative snapshots, wrap already-grounded planner projections, and
never create or revise epistemic truth.
"""

import copy
import math
from dataclasses import dataclass

from .model import Operation


_PROBABILITY_TOLERANCE = 1e-9


def _finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("{} must be finite".format(name))
    return value


def _nonnegative(value, name):
    value = _finite(value, name)
    if value < 0.0:
        raise ValueError("{} must be non-negative".format(name))
    return value


def _probability(value, name):
    value = _finite(value, name)
    if not 0.0 <= value <= 1.0:
        raise ValueError("{} must be in [0,1]".format(name))
    return value


def _named_numeric_rows(rows, name, nonnegative=False):
    rows = tuple(rows)
    keys = []
    normalized = []
    for row in rows:
        if not isinstance(row, tuple) or len(row) != 2:
            raise TypeError("{} rows must be (name, value) tuples".format(
                name))
        key, value = row
        if not isinstance(key, str) or not key:
            raise ValueError("{} names must be non-empty strings".format(
                name))
        value = (
            _nonnegative(value, "{} value".format(name))
            if nonnegative else
            _finite(value, "{} value".format(name)))
        keys.append(key)
        normalized.append((key, value))
    if len(keys) != len(set(keys)):
        raise ValueError("{} names must be unique".format(name))
    return tuple(normalized)


def _goal_feature_rows(rows):
    """Validate ``(goal_id, projected cost-to-go)`` rows."""
    return _named_numeric_rows(
        rows, "next goal feature", nonnegative=True)


def _truth_summary_rows(rows):
    """Validate ``(atom_id, strength, confidence)`` summaries."""
    rows = tuple(rows)
    keys = []
    normalized = []
    for row in rows:
        if not isinstance(row, tuple) or len(row) != 3:
            raise TypeError(
                "next truth summaries must be "
                "(atom_id, strength, confidence) tuples")
        atom_id, strength, confidence = row
        if not isinstance(atom_id, str) or not atom_id:
            raise ValueError(
                "next truth summary atom IDs must be non-empty strings")
        keys.append(atom_id)
        normalized.append((
            atom_id,
            _probability(strength, "predicted truth strength"),
            _probability(confidence, "predicted truth confidence"),
        ))
    if len(keys) != len(set(keys)):
        raise ValueError("next truth summary atom IDs must be unique")
    return tuple(normalized)


@dataclass(frozen=True)
class PredictedOutcome:
    """One explicitly modeled post-operation outcome."""

    outcome_id: str
    probability: float
    next_truth_summaries: tuple
    next_goal_features: tuple
    resource_delta: tuple
    completion_turn: object
    adverse_loss: float
    provenance: tuple

    def __post_init__(self):
        if not isinstance(self.outcome_id, str) or not self.outcome_id:
            raise ValueError("predicted outcome requires an outcome ID")
        _probability(self.probability, "outcome probability")
        _truth_summary_rows(self.next_truth_summaries)
        _goal_feature_rows(self.next_goal_features)
        _named_numeric_rows(self.resource_delta, "resource delta")
        if self.completion_turn is not None:
            _nonnegative(self.completion_turn, "completion turn")
        if not self.provenance or any(
                not isinstance(value, str) or not value
                for value in self.provenance):
            raise ValueError(
                "predicted outcome requires non-empty provenance strings")
        _nonnegative(self.adverse_loss, "adverse loss")

    def cost_to_go_for(self, goal_id):
        return dict(self.next_goal_features).get(str(goal_id))

    def to_dict(self):
        return {
            "adverse_loss": float(self.adverse_loss),
            "completion_turn": (
                None if self.completion_turn is None
                else float(self.completion_turn)),
            "next_goal_features": dict(
                (key, float(value))
                for key, value in self.next_goal_features),
            "next_truth_summaries": [
                {
                    "atom_id": row[0],
                    "confidence": float(row[2]),
                    "strength": float(row[1]),
                }
                for row in self.next_truth_summaries
            ],
            "outcome_id": self.outcome_id,
            "probability": float(self.probability),
            "provenance": list(self.provenance),
            "resource_delta": dict(
                (key, float(value))
                for key, value in self.resource_delta),
        }


@dataclass(frozen=True)
class ExpectedTransition:
    """A normalized transition distribution with explicit unknown mass."""

    operation_id: str
    outcomes: tuple
    residual_probability: float
    model_id: str
    calibration_group: str
    residual_goal_losses: tuple = (("*", 1.0),)

    def __post_init__(self):
        if not isinstance(self.operation_id, str) or not self.operation_id:
            raise ValueError("expected transition requires operation ID")
        if not isinstance(self.model_id, str) or not self.model_id:
            raise ValueError("expected transition requires model ID")
        if (not isinstance(self.calibration_group, str)
                or not self.calibration_group):
            raise ValueError(
                "expected transition requires calibration group")
        if any(not isinstance(row, PredictedOutcome)
               for row in self.outcomes):
            raise TypeError(
                "transition outcomes must contain PredictedOutcome")
        outcome_ids = [row.outcome_id for row in self.outcomes]
        if len(outcome_ids) != len(set(outcome_ids)):
            raise ValueError("transition outcome IDs must be unique")
        residual = _probability(
            self.residual_probability, "residual probability")
        total = sum(float(row.probability) for row in self.outcomes)
        if abs(total + residual - 1.0) > _PROBABILITY_TOLERANCE:
            raise ValueError(
                "outcome and residual probabilities must sum to one")
        losses = _named_numeric_rows(
            self.residual_goal_losses,
            "residual goal loss", nonnegative=True)
        if residual > 0.0:
            wildcard = dict(losses).get("*")
            if wildcard is None or wildcard <= 0.0:
                raise ValueError(
                    "unknown probability mass requires a positive "
                    "wildcard fallback loss")

    def residual_loss_for(self, goal_id):
        losses = dict(self.residual_goal_losses)
        return float(losses.get(str(goal_id), losses.get("*", 0.0)))

    def expected_cost_to_go(self, goal_id):
        """Return risk-aware loss including modeled adverse consequences."""
        fallback = self.residual_loss_for(goal_id)
        modeled = sum(
            float(outcome.probability) * (
                float(outcome.cost_to_go_for(goal_id))
                if outcome.cost_to_go_for(goal_id) is not None
                else fallback)
            for outcome in self.outcomes)
        adverse = sum(
            float(outcome.probability) * float(outcome.adverse_loss)
            for outcome in self.outcomes)
        return (
            modeled + adverse
            + float(self.residual_probability) * fallback)

    @property
    def expected_adverse_loss(self):
        fallback = self.residual_loss_for("*")
        return (
            sum(
                float(outcome.probability) * float(outcome.adverse_loss)
                for outcome in self.outcomes)
            + float(self.residual_probability) * fallback)

    @property
    def modeled_probability(self):
        return sum(float(row.probability) for row in self.outcomes)

    def to_dict(self):
        return {
            "calibration_group": self.calibration_group,
            "expected_adverse_loss": float(
                self.expected_adverse_loss),
            "model_id": self.model_id,
            "modeled_probability": float(
                self.modeled_probability),
            "operation_id": self.operation_id,
            "outcomes": [row.to_dict() for row in self.outcomes],
            "residual_goal_losses": dict(
                (key, float(value))
                for key, value in self.residual_goal_losses),
            "residual_probability": float(
                self.residual_probability),
        }


class DeclaredFallbackTransitionModel:
    """A full-unknown model with a declared conservative loss."""

    model_id = "declared-conservative-fallback/1.0"

    def __init__(self, fallback_loss=1.0):
        self.fallback_loss = _nonnegative(
            fallback_loss, "fallback loss")
        if self.fallback_loss <= 0.0:
            raise ValueError("fallback loss must be positive")

    def predict(self, snapshot, operation, operation_kind=None):
        del snapshot
        if not isinstance(operation, Operation):
            raise TypeError("transition prediction requires Operation")
        kind = str(operation_kind or "unclassified")
        return ExpectedTransition(
            operation_id=operation.operation_id,
            outcomes=(),
            residual_probability=1.0,
            model_id=self.model_id,
            calibration_group="missing-model:{}".format(kind),
            residual_goal_losses=(("*", self.fallback_loss),))


class ProjectionTransitionModel:
    """Wrap already-grounded candidate projections without resimulating."""

    _COMPLETION_ETA_FIELDS = (
        "settlement_eta_turns",
        "preexpansion_sequence_settlement_eta_turns",
        "repeat_completion_eta_turns",
        "completion_eta_turns",
        "founder_route_eta_turns",
    )

    def __init__(
            self, model_id, calibration_group,
            fallback_loss=1.0):
        if not isinstance(model_id, str) or not model_id:
            raise ValueError("projection model requires model ID")
        if not isinstance(calibration_group, str) or not calibration_group:
            raise ValueError(
                "projection model requires calibration group")
        self.model_id = model_id
        self.calibration_group = calibration_group
        self.fallback_loss = _nonnegative(
            fallback_loss, "fallback loss")
        if self.fallback_loss <= 0.0:
            raise ValueError("fallback loss must be positive")

    @staticmethod
    def _projection(operation):
        payload = operation.payload
        if not isinstance(payload, dict):
            return {}, {}
        projection = payload.get("projection", {})
        if not isinstance(projection, dict):
            return payload, {}
        return payload, projection

    @staticmethod
    def _completion_turn(snapshot, projection):
        eta = next((
            projection.get(name)
            for name in ProjectionTransitionModel._COMPLETION_ETA_FIELDS
            if projection.get(name) is not None), None)
        if eta is None:
            return None
        eta = _nonnegative(eta, "projected completion ETA")
        turn = getattr(snapshot, "turn", None)
        if turn is None and isinstance(snapshot, dict):
            turn = snapshot.get("turn")
        return eta if turn is None else _nonnegative(
            turn, "snapshot turn") + eta

    @staticmethod
    def _goal_features(operation, projection, fallback_loss):
        declared = projection.get("next_goal_cost_to_go", {})
        if declared:
            if not isinstance(declared, dict):
                raise TypeError(
                    "next_goal_cost_to_go must be an object")
            return tuple(sorted(
                (str(key), _nonnegative(
                    value, "next goal cost-to-go"))
                for key, value in declared.items()))
        return tuple(sorted(
            (
                advantage.goal_id,
                max(
                    0.0,
                    float(fallback_loss)
                    - float(advantage.expected_relief)),
            )
            for advantage in operation.typed_advantages))

    @staticmethod
    def _truth_summaries(projection):
        declared = projection.get("next_truth_summaries", ())
        if isinstance(declared, dict):
            declared = tuple(
                (str(key), value["strength"], value["confidence"])
                for key, value in sorted(declared.items()))
        else:
            declared = tuple(tuple(row) for row in declared)
        return _truth_summary_rows(declared)

    @staticmethod
    def _resource_delta(operation, projection):
        declared = projection.get("resource_delta", {})
        if declared:
            if not isinstance(declared, dict):
                raise TypeError("resource_delta must be an object")
            return tuple(sorted(
                (str(key), _finite(value, "resource delta"))
                for key, value in declared.items()))
        resources = {}
        for advantage in operation.typed_advantages:
            for key, value in advantage.predicted_resource_use:
                resources[key] = resources.get(key, 0.0) - float(value)
        return tuple(sorted(resources.items()))

    @staticmethod
    def _provenance(payload, projection):
        declared = projection.get("provenance", ())
        if isinstance(declared, str):
            declared = (declared,)
        sources = set(str(value) for value in declared if value)
        category = payload.get("category")
        if category:
            sources.add("candidate-projection:{}".format(category))
        sources.update(
            "{}={}".format(key, projection[key])
            for key in sorted(projection)
            if key.endswith("_source") and projection[key])
        return tuple(sorted(sources or ("grounded-operation-fields",)))

    def predict(self, snapshot, operation):
        if not isinstance(operation, Operation):
            raise TypeError("transition prediction requires Operation")
        payload, projection = self._projection(operation)
        explicit_probability = projection.get(
            "success_probability",
            float(operation.success_probability)
            * float(operation.feasibility))
        success_probability = _probability(
            explicit_probability, "projected success probability")
        risk = projection.get("risk_estimate", {})
        adverse_loss = (
            _nonnegative(
                risk.get("expected_loss", 0.0),
                "projected adverse loss")
            if isinstance(risk, dict) else 0.0)
        outcome = PredictedOutcome(
            outcome_id="{}:projected-success".format(
                operation.operation_id),
            probability=success_probability,
            next_truth_summaries=self._truth_summaries(projection),
            next_goal_features=self._goal_features(
                operation, projection, self.fallback_loss),
            resource_delta=self._resource_delta(
                operation, projection),
            completion_turn=self._completion_turn(
                snapshot, projection),
            adverse_loss=adverse_loss,
            provenance=self._provenance(payload, projection),
        )
        outcomes = () if success_probability == 0.0 else (outcome,)
        return ExpectedTransition(
            operation_id=operation.operation_id,
            outcomes=outcomes,
            residual_probability=1.0 - success_probability,
            model_id=self.model_id,
            calibration_group=self.calibration_group,
            residual_goal_losses=(("*", self.fallback_loss),))


class TransitionModelRegistry:
    """Deterministic operation-kind registry with snapshot isolation."""

    def __init__(self, fallback_model=None):
        self._models = {}
        self.fallback_model = (
            fallback_model or DeclaredFallbackTransitionModel())

    @property
    def registered_kinds(self):
        return tuple(sorted(self._models))

    def register(self, operation_kind, model):
        if not isinstance(operation_kind, str) or not operation_kind:
            raise ValueError("operation kind must be a non-empty string")
        if operation_kind in self._models:
            raise ValueError(
                "transition model already registered for {}".format(
                    operation_kind))
        if not getattr(model, "model_id", None):
            raise TypeError("transition model requires stable model_id")
        if not callable(getattr(model, "predict", None)):
            raise TypeError("transition model requires predict method")
        self._models[operation_kind] = model

    @staticmethod
    def operation_kind(operation):
        if not isinstance(operation, Operation):
            raise TypeError("transition prediction requires Operation")
        payload = operation.payload
        if isinstance(payload, dict):
            kind = payload.get(
                "operation_kind", payload.get("category"))
            if isinstance(kind, str) and kind:
                return kind
        return operation.mode

    def predict(self, snapshot, operation):
        kind = self.operation_kind(operation)
        model = self._models.get(kind)
        isolated_snapshot = copy.deepcopy(snapshot)
        if model is None:
            transition = self.fallback_model.predict(
                isolated_snapshot, operation, operation_kind=kind)
        else:
            transition = model.predict(
                isolated_snapshot, operation)
        if not isinstance(transition, ExpectedTransition):
            raise TypeError(
                "transition model must return ExpectedTransition")
        if transition.operation_id != operation.operation_id:
            raise ValueError(
                "transition operation ID must match operation")
        if model is not None and transition.model_id != model.model_id:
            raise ValueError(
                "transition model ID must match registered model")
        return transition


@dataclass(frozen=True)
class TransitionCalibrationRecord:
    """Predicted-versus-realized control evidence; never truth evidence."""

    operation_id: str
    operation_kind: str
    model_id: str
    calibration_group: str
    horizon: str
    context: str
    risk_class: str
    predicted_success_probability: float
    realized_success: bool
    predicted_completion_turn: object
    realized_completion_turn: object
    predicted_goal_relief: tuple
    realized_goal_relief: tuple
    predicted_resource_use: tuple
    realized_resource_use: tuple
    predicted_adverse_loss: float
    realized_adverse_loss: float
    predicted_information_gain: float
    realized_information_gain: float
    update_scope: str = "control-model-only"

    def __post_init__(self):
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.operation_kind, "operation kind"),
                (self.model_id, "model ID"),
                (self.calibration_group, "calibration group"),
                (self.horizon, "horizon"),
                (self.context, "context"),
                (self.risk_class, "risk class")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "calibration {} is required".format(name))
        _probability(
            self.predicted_success_probability,
            "predicted success probability")
        if not isinstance(self.realized_success, bool):
            raise TypeError("realized success must be boolean")
        for value, name in (
                (self.predicted_completion_turn,
                 "predicted completion turn"),
                (self.realized_completion_turn,
                 "realized completion turn")):
            if value is not None:
                _nonnegative(value, name)
        for rows, name in (
                (self.predicted_goal_relief,
                 "predicted goal relief"),
                (self.realized_goal_relief,
                 "realized goal relief"),
                (self.predicted_resource_use,
                 "predicted resource use"),
                (self.realized_resource_use,
                 "realized resource use")):
            _named_numeric_rows(rows, name)
        for value, name in (
                (self.predicted_adverse_loss,
                 "predicted adverse loss"),
                (self.realized_adverse_loss,
                 "realized adverse loss"),
                (self.predicted_information_gain,
                 "predicted information gain"),
                (self.realized_information_gain,
                 "realized information gain")):
            _nonnegative(value, name)
        if self.update_scope != "control-model-only":
            raise ValueError(
                "transition calibration cannot update epistemic truth")

    @property
    def reliability_key(self):
        return (
            self.operation_kind, self.horizon,
            self.context, self.risk_class)

    def to_dict(self):
        return {
            "calibration_group": self.calibration_group,
            "context": self.context,
            "horizon": self.horizon,
            "model_id": self.model_id,
            "operation_id": self.operation_id,
            "operation_kind": self.operation_kind,
            "predicted_adverse_loss": float(
                self.predicted_adverse_loss),
            "predicted_completion_turn": (
                None if self.predicted_completion_turn is None else
                float(self.predicted_completion_turn)),
            "predicted_goal_relief": dict(
                self.predicted_goal_relief),
            "predicted_information_gain": float(
                self.predicted_information_gain),
            "predicted_resource_use": dict(
                self.predicted_resource_use),
            "predicted_success_probability": float(
                self.predicted_success_probability),
            "realized_adverse_loss": float(
                self.realized_adverse_loss),
            "realized_completion_turn": (
                None if self.realized_completion_turn is None else
                float(self.realized_completion_turn)),
            "realized_goal_relief": dict(
                self.realized_goal_relief),
            "realized_information_gain": float(
                self.realized_information_gain),
            "realized_resource_use": dict(
                self.realized_resource_use),
            "realized_success": bool(self.realized_success),
            "risk_class": self.risk_class,
            "update_scope": self.update_scope,
        }


class TransitionCalibrationLedger:
    """Append-only control-model calibration and reliability curves."""

    def __init__(self):
        self._records = []

    @property
    def records(self):
        return tuple(self._records)

    def append(self, record):
        if not isinstance(record, TransitionCalibrationRecord):
            raise TypeError(
                "calibration ledger requires "
                "TransitionCalibrationRecord")
        self._records.append(record)
        return record

    def reliability_curves(self):
        """Aggregate prediction reliability by declared context key."""
        groups = {}
        for record in self._records:
            groups.setdefault(record.reliability_key, []).append(record)
        result = {}
        for key in sorted(groups):
            rows = groups[key]
            count = float(len(rows))
            result["|".join(key)] = {
                "count": int(count),
                "mean_predicted_success": sum(
                    row.predicted_success_probability
                    for row in rows) / count,
                "mean_realized_success": sum(
                    1.0 if row.realized_success else 0.0
                    for row in rows) / count,
                "mean_adverse_loss_error": sum(
                    abs(
                        row.predicted_adverse_loss
                        - row.realized_adverse_loss)
                    for row in rows) / count,
            }
        return result
