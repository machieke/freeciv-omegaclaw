"""Deterministic, pressure-only conductance feedback and persistence."""

import json
import os
import threading
from dataclasses import dataclass

from ..events.schema import structural_hash
from .engine import ConductanceLearner
from .model import PressureRule


SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ConductanceUpdate:
    feedback_id: str
    category: str
    rule_id: str
    effect_observed: bool
    applied: bool
    previous_conductance: float
    conductance: float
    successes: int
    no_progress: int
    state_hash: str

    def to_dict(self):
        return {
            "applied": bool(self.applied),
            "category": self.category,
            "conductance": float(self.conductance),
            "effect_observed": bool(self.effect_observed),
            "feedback_id": self.feedback_id,
            "learning_method": "grounded-effect-ema-v1",
            "no_progress": int(self.no_progress),
            "previous_conductance": float(self.previous_conductance),
            "rule_id": self.rule_id,
            "state_hash": self.state_hash,
            "successes": int(self.successes),
        }


class ConductanceState(object):
    """Attempt-scoped route credit that is idempotent by grounded feedback ID.

    The state owns no truth values and exposes no truth-revision method.  It can
    only change the conductance attached to reverse pressure routes.
    """

    def __init__(self, path=None, identity="in-memory",
                 learning_rate=0.10, no_progress_rate=0.10,
                 initial_conductance=0.50):
        if not str(identity):
            raise ValueError("conductance state identity is required")
        if not 0 <= float(initial_conductance) <= 1:
            raise ValueError("initial conductance must be in [0,1]")
        self.path = None if path is None else os.path.abspath(path)
        self.identity = str(identity)
        self.initial_conductance = float(initial_conductance)
        self.learner = ConductanceLearner(learning_rate, no_progress_rate)
        self._lock = threading.RLock()
        self._routes = {}
        self._applied_feedback_ids = set()
        if self.path is not None and os.path.isfile(self.path):
            self._load()

    @staticmethod
    def rule_id(category):
        return "pf-impact-category-route:{}".format(str(category))

    def _load(self):
        with open(self.path, encoding="utf-8") as stream:
            value = json.load(stream)
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported conductance state schema")
        if value.get("identity") != self.identity:
            raise ValueError("conductance state identity mismatch")
        configuration = value.get("configuration", {})
        expected = self._configuration()
        if configuration != expected:
            raise ValueError("conductance state configuration mismatch")
        routes = value.get("routes", {})
        if not isinstance(routes, dict):
            raise ValueError("conductance routes must be an object")
        checked = {}
        for category, row in routes.items():
            if not isinstance(row, dict):
                raise ValueError("conductance route rows must be objects")
            conductance = float(row.get("conductance"))
            successes = int(row.get("successes", 0))
            no_progress = int(row.get("no_progress", 0))
            if (not 0 <= conductance <= 1
                    or successes < 0 or no_progress < 0):
                raise ValueError("invalid persisted conductance route")
            checked[str(category)] = {
                "conductance": conductance,
                "no_progress": no_progress,
                "successes": successes,
            }
        feedback_ids = value.get("applied_feedback_ids", ())
        if (not isinstance(feedback_ids, list)
                or any(not str(item) for item in feedback_ids)
                or len(feedback_ids) != len(set(feedback_ids))):
            raise ValueError("invalid persisted conductance feedback IDs")
        self._routes = checked
        self._applied_feedback_ids = set(str(item) for item in feedback_ids)
        if value.get("state_hash") != self.state_hash:
            raise ValueError("conductance state hash mismatch")

    def _configuration(self):
        return {
            "initial_conductance": self.initial_conductance,
            "learning_rate": self.learner.learning_rate,
            "no_progress_rate": self.learner.no_progress_rate,
        }

    def _hash_material(self):
        return {
            "applied_feedback_ids": sorted(self._applied_feedback_ids),
            "configuration": self._configuration(),
            "identity": self.identity,
            "routes": dict(
                (category, dict(self._routes[category]))
                for category in sorted(self._routes)),
            "schema_version": SCHEMA_VERSION,
        }

    @property
    def state_hash(self):
        with self._lock:
            return structural_hash(self._hash_material())

    def value(self, category):
        with self._lock:
            return float(self._routes.get(str(category), {}).get(
                "conductance", self.initial_conductance))

    def snapshot(self):
        with self._lock:
            value = self._hash_material()
            value["state_hash"] = structural_hash(value)
            return value

    def decision_snapshot(self):
        """Return bounded replay context without repeating every feedback ID."""
        with self._lock:
            return {
                "applied_feedback_count": len(self._applied_feedback_ids),
                "configuration": self._configuration(),
                "identity": self.identity,
                "routes": dict(
                    (category, dict(self._routes[category]))
                    for category in sorted(self._routes)),
                "schema_version": SCHEMA_VERSION,
                "state_hash": self.state_hash,
            }

    def save(self):
        if self.path is None:
            return
        with self._lock:
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            temporary = self.path + ".tmp.{}".format(os.getpid())
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump(self.snapshot(), stream, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(temporary, self.path)

    def feedback(self, category, effect_observed, feedback_id):
        category = str(category)
        feedback_id = str(feedback_id)
        if not category or not feedback_id:
            raise ValueError("conductance feedback requires category and ID")
        with self._lock:
            row = self._routes.setdefault(category, {
                "conductance": self.initial_conductance,
                "no_progress": 0,
                "successes": 0,
            })
            previous = float(row["conductance"])
            applied = feedback_id not in self._applied_feedback_ids
            if applied:
                rule = PressureRule(
                    self.rule_id(category), ("feedback-premise",),
                    "feedback-goal", conductance=previous)
                if effect_observed:
                    updated = self.learner.update(
                        rule, calibration=1.0, realized_relief=1.0,
                        information_gain=0.0, failure_rate=0.0,
                        dependency_risk=0.0)
                    row["successes"] += 1
                else:
                    updated = self.learner.no_progress(rule)
                    row["no_progress"] += 1
                row["conductance"] = float(updated.conductance)
                self._applied_feedback_ids.add(feedback_id)
                self.save()
            return ConductanceUpdate(
                feedback_id, category, self.rule_id(category),
                bool(effect_observed), applied, previous,
                float(row["conductance"]), int(row["successes"]),
                int(row["no_progress"]), self.state_hash)
