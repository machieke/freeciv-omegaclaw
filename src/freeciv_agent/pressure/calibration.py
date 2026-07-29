"""Typed control calibration against authoritative realized relief."""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash
from .engine import ConductanceLearner
from .model import PressureRule


CONTROL_UPDATE_TARGETS = frozenset((
    "bridge_predictor",
    "cost_latency",
    "motif_usefulness",
    "operation_success",
    "route_conductance",
    "teleological_resolvability",
    "transition_model",
))


def _nonnegative(value, name):
    value = float(value)
    if value < 0.0 or not math.isfinite(value):
        raise ValueError(
            "{} must be finite and non-negative".format(name))
    return value


def _cost_rows(rows, name):
    result = []
    keys = []
    for row in tuple(rows):
        if not isinstance(row, tuple) or len(row) != 2:
            raise TypeError(
                "{} must contain (resource, value) rows".format(name))
        key, value = row
        if not isinstance(key, str) or not key:
            raise ValueError(
                "{} resource names must be strings".format(name))
        result.append((
            key, _nonnegative(value, name)))
        keys.append(key)
    if len(keys) != len(set(keys)):
        raise ValueError(
            "{} resources must be unique".format(name))
    return tuple(result)


@dataclass(frozen=True)
class ControlCalibrationRecord:
    context_signature: str
    rule_or_operation_id: str
    predicted_relief: float
    realized_relief: float
    predicted_success: float
    success: bool
    predicted_cost: tuple
    realized_cost: tuple
    selection_propensity: object
    update_targets: tuple
    frontier_signature: object = None
    generation: object = None
    relief_source: str = "authoritative-outcome"

    def __post_init__(self):
        if not self.context_signature or not self.rule_or_operation_id:
            raise ValueError(
                "control calibration requires context and target IDs")
        _nonnegative(
            self.predicted_relief, "predicted relief")
        _nonnegative(
            self.realized_relief, "realized relief")
        probability = float(self.predicted_success)
        if not 0.0 <= probability <= 1.0 or not math.isfinite(
                probability):
            raise ValueError(
                "predicted success must be in [0,1]")
        if not isinstance(self.success, bool):
            raise TypeError("calibration success must be boolean")
        _cost_rows(self.predicted_cost, "predicted cost")
        _cost_rows(self.realized_cost, "realized cost")
        if (self.selection_propensity is not None
                and not 0.0 < float(
                    self.selection_propensity) <= 1.0):
            raise ValueError(
                "selection propensity must be in (0,1]")
        targets = tuple(sorted(str(value)
                               for value in self.update_targets))
        if not targets:
            raise ValueError(
                "calibration requires declared update targets")
        if len(targets) != len(set(targets)):
            raise ValueError(
                "calibration update targets must be unique")
        unknown = set(targets) - CONTROL_UPDATE_TARGETS
        if unknown:
            raise ValueError(
                "unsupported control update targets {}".format(
                    sorted(unknown)))
        if "truth" in targets:
            raise ValueError(
                "control calibration cannot update truth")
        object.__setattr__(self, "update_targets", targets)
        if "route_conductance" in targets:
            if not self.frontier_signature:
                raise ValueError(
                    "route conductance calibration requires frontier")
            if (isinstance(self.generation, bool)
                    or not isinstance(self.generation, int)
                    or self.generation < 0):
                raise ValueError(
                    "route conductance calibration requires generation")
        if not self.relief_source:
            raise ValueError(
                "realized relief requires provenance")

    @property
    def record_id(self):
        return "control-calibration-{}".format(
            structural_hash(self.to_dict())[:24])

    @property
    def relief_error(self):
        return (
            float(self.realized_relief)
            - float(self.predicted_relief))

    def offpolicy_weight(self, assumption=None):
        if assumption != "missing-at-random-given-context":
            raise ValueError(
                "off-policy audit requires declared assumption")
        if self.selection_propensity is None:
            raise ValueError(
                "deterministic selection has no propensity weight")
        return 1.0 / float(self.selection_propensity)

    def to_dict(self):
        return {
            "context_signature": self.context_signature,
            "frontier_signature": self.frontier_signature,
            "generation": self.generation,
            "predicted_cost": dict(self.predicted_cost),
            "predicted_relief": float(self.predicted_relief),
            "predicted_success": float(self.predicted_success),
            "realized_cost": dict(self.realized_cost),
            "realized_relief": float(self.realized_relief),
            "relief_source": self.relief_source,
            "rule_or_operation_id": self.rule_or_operation_id,
            "selection_propensity": self.selection_propensity,
            "success": bool(self.success),
            "update_targets": list(self.update_targets),
        }


@dataclass(frozen=True, order=True)
class ContextualRouteKey:
    context_signature: str
    frontier_signature: str
    generation: int
    route_id: str

    def __post_init__(self):
        if (not self.context_signature
                or not self.frontier_signature
                or not self.route_id):
            raise ValueError(
                "contextual route key requires stable IDs")
        if (isinstance(self.generation, bool)
                or not isinstance(self.generation, int)
                or self.generation < 0):
            raise ValueError(
                "contextual route generation must be non-negative")

    def to_dict(self):
        return {
            "context_signature": self.context_signature,
            "frontier_signature": self.frontier_signature,
            "generation": int(self.generation),
            "route_id": self.route_id,
        }


@dataclass(frozen=True)
class ContextualConductanceUpdate:
    record_id: str
    key: ContextualRouteKey
    previous: float
    value: float
    applied: bool
    success: bool
    realized_relief: float

    def to_dict(self):
        return {
            "applied": bool(self.applied),
            "key": self.key.to_dict(),
            "previous": float(self.previous),
            "realized_relief": float(
                self.realized_relief),
            "record_id": self.record_id,
            "success": bool(self.success),
            "value": float(self.value),
        }


class ContextualConductanceStore:
    """Exact-context Hebbian prior; no unqualified cross-context reuse."""

    def __init__(
            self, initial_conductance=0.5,
            learning_rate=0.1, no_progress_rate=0.1):
        initial = float(initial_conductance)
        if not 0.0 <= initial <= 1.0:
            raise ValueError(
                "initial conductance must be in [0,1]")
        self.initial_conductance = initial
        self.learner = ConductanceLearner(
            learning_rate, no_progress_rate)
        self._rows = {}
        self._applied = set()

    @staticmethod
    def key_for(record):
        return ContextualRouteKey(
            record.context_signature,
            str(record.frontier_signature),
            int(record.generation),
            record.rule_or_operation_id)

    def value(
            self, route_id, context_signature,
            frontier_signature, generation):
        key = ContextualRouteKey(
            str(context_signature), str(frontier_signature),
            int(generation), str(route_id))
        return float(
            self._rows.get(key, self.initial_conductance))

    def unqualified_value(self, route_id):
        matches = [
            value for key, value in self._rows.items()
            if key.route_id == str(route_id)]
        if len(matches) > 1:
            raise ValueError(
                "route conductance is context-qualified")
        return (
            self.initial_conductance
            if not matches else float(matches[0]))

    def update(self, record):
        if not isinstance(record, ControlCalibrationRecord):
            raise TypeError(
                "conductance update requires "
                "ControlCalibrationRecord")
        if "route_conductance" not in record.update_targets:
            raise ValueError(
                "record does not declare route conductance target")
        key = self.key_for(record)
        previous = float(
            self._rows.get(key, self.initial_conductance))
        applied = record.record_id not in self._applied
        value = previous
        if applied:
            rule = PressureRule(
                "calibration:{}".format(
                    record.rule_or_operation_id),
                ("calibration-premise",),
                "calibration-goal",
                conductance=previous)
            if record.success and record.realized_relief > 0.0:
                updated = self.learner.credit(
                    rule,
                    min(1.0, float(record.realized_relief)))
            else:
                updated = self.learner.no_progress(rule)
            value = float(updated.conductance)
            self._rows[key] = value
            self._applied.add(record.record_id)
        return ContextualConductanceUpdate(
            record.record_id, key, previous, value,
            applied, record.success, record.realized_relief)

    @property
    def state_hash(self):
        return structural_hash({
            "applied_record_ids": sorted(self._applied),
            "configuration": {
                "initial_conductance": self.initial_conductance,
                "learning_rate": self.learner.learning_rate,
                "no_progress_rate": self.learner.no_progress_rate,
            },
            "routes": [
                {
                    "key": key.to_dict(),
                    "value": float(self._rows[key]),
                }
                for key in sorted(self._rows)
            ],
        })


class ControlCalibrationLedger:
    """Append-only typed records and explicitly routed updates."""

    def __init__(self):
        self._records = {}

    @property
    def records(self):
        return tuple(
            self._records[key] for key in sorted(self._records))

    def append(self, record):
        if not isinstance(record, ControlCalibrationRecord):
            raise TypeError(
                "control ledger requires "
                "ControlCalibrationRecord")
        existing = self._records.get(record.record_id)
        if existing is not None and existing != record:
            raise ValueError(
                "control calibration identity collision")
        self._records[record.record_id] = record
        return existing is None

    def apply(self, record, updaters):
        """Invoke only the updater named by each declared target."""
        self.append(record)
        updaters = dict(updaters)
        result = {}
        for target in record.update_targets:
            updater = updaters.get(target)
            if updater is None:
                continue
            method = (
                updater.update
                if hasattr(updater, "update") else updater)
            if not callable(method):
                raise TypeError(
                    "calibration updater must be callable")
            result[target] = method(record)
        return result
