"""Calibrated realized goal-relief estimates for grounded control actions.

This module is deliberately control-only.  It consumes authoritative
post-action goal-relief measurements, but exposes no truth or evidence update
surface.
"""

import json
import math
import os
import threading
from dataclasses import dataclass

from ..events.schema import canonical_json_bytes, structural_hash


TRANSITION_VALUE_SCHEMA_VERSION = "1.0"
TRANSITION_VALUE_MODEL_ID = "category-lifecycle-relief-calibrator/1.0"


def _probability(value, name):
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("{} must be in [0,1]".format(name))
    return value


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


@dataclass(frozen=True, order=True)
class TransitionValueKey:
    """The exact support boundary for decision-authoritative calibration."""

    action_category: str
    lifecycle_state: str
    goal_id: str

    def __post_init__(self):
        _required_text(self.action_category, "action category")
        _required_text(self.lifecycle_state, "lifecycle state")
        _required_text(self.goal_id, "goal ID")

    @property
    def stable_id(self):
        return "{}|{}|{}".format(
            self.action_category,
            self.lifecycle_state,
            self.goal_id)

    def to_dict(self):
        return {
            "action_category": self.action_category,
            "goal_id": self.goal_id,
            "lifecycle_state": self.lifecycle_state,
        }


@dataclass(frozen=True)
class TransitionValueObservation:
    """One selected-action prediction paired with authoritative relief."""

    observation_id: str
    key: TransitionValueKey
    predicted_relief: float
    realized_relief: float
    effect_observed: bool
    relief_source: str
    context_digest: str
    selection_propensity: object = None
    update_scope: str = "control-model-only"

    def __post_init__(self):
        _required_text(self.observation_id, "observation ID")
        if not isinstance(self.key, TransitionValueKey):
            raise TypeError(
                "transition observation requires TransitionValueKey")
        _probability(self.predicted_relief, "predicted relief")
        realized = _probability(
            self.realized_relief, "realized relief")
        if not isinstance(self.effect_observed, bool):
            raise TypeError("effect observed must be boolean")
        if not self.effect_observed and realized != 0.0:
            raise ValueError(
                "goal relief cannot occur without an observed effect")
        _required_text(self.relief_source, "relief source")
        if not self.relief_source.startswith("authoritative:"):
            raise ValueError(
                "transition calibration requires authoritative relief")
        _required_text(self.context_digest, "context digest")
        if self.selection_propensity is not None:
            propensity = float(self.selection_propensity)
            if (not math.isfinite(propensity)
                    or not 0.0 < propensity <= 1.0):
                raise ValueError(
                    "selection propensity must be in (0,1]")
        if self.update_scope != "control-model-only":
            raise ValueError(
                "transition calibration cannot update truth")

    @property
    def residual(self):
        return (
            float(self.realized_relief)
            - float(self.predicted_relief))

    def to_dict(self):
        return {
            "context_digest": self.context_digest,
            "effect_observed": bool(self.effect_observed),
            "key": self.key.to_dict(),
            "observation_id": self.observation_id,
            "predicted_relief": float(self.predicted_relief),
            "realized_relief": float(self.realized_relief),
            "relief_source": self.relief_source,
            "selection_propensity": self.selection_propensity,
            "update_scope": self.update_scope,
        }


@dataclass(frozen=True)
class TransitionValueEstimate:
    """A confidence-bounded correction with explicit abstention."""

    key: TransitionValueKey
    raw_predicted_relief: float
    expected_realized_relief: float
    lower_bound: float
    upper_bound: float
    residual_mean: float
    residual_variance: float
    confidence_half_width: float
    sample_count: int
    calibrated: bool
    abstention_reason: object
    estimator_id: str
    model_state_hash: str
    support_source: str = "exact-category-lifecycle-goal"

    def __post_init__(self):
        if not isinstance(self.key, TransitionValueKey):
            raise TypeError(
                "transition estimate requires TransitionValueKey")
        for value, name in (
                (self.raw_predicted_relief, "raw predicted relief"),
                (self.expected_realized_relief,
                 "expected realized relief"),
                (self.lower_bound, "lower bound"),
                (self.upper_bound, "upper bound")):
            _probability(value, name)
        if not (
                self.lower_bound
                <= self.expected_realized_relief
                <= self.upper_bound):
            raise ValueError(
                "transition bounds must contain expectation")
        for value, name in (
                (self.residual_mean, "residual mean"),
                (self.residual_variance, "residual variance"),
                (self.confidence_half_width,
                 "confidence half width")):
            value = float(value)
            if not math.isfinite(value):
                raise ValueError("{} must be finite".format(name))
        if self.residual_variance < 0.0:
            raise ValueError(
                "residual variance must be non-negative")
        if self.confidence_half_width < 0.0:
            raise ValueError(
                "confidence half width must be non-negative")
        if (isinstance(self.sample_count, bool)
                or not isinstance(self.sample_count, int)
                or self.sample_count < 0):
            raise ValueError(
                "sample count must be non-negative")
        if not isinstance(self.calibrated, bool):
            raise TypeError("calibrated must be boolean")
        if self.calibrated != (
                self.abstention_reason is None):
            raise ValueError(
                "calibration state and abstention reason disagree")
        _required_text(self.estimator_id, "estimator ID")
        _required_text(self.model_state_hash, "model state hash")
        _required_text(self.support_source, "support source")

    @property
    def decision_relief(self):
        """Return a conservative value only when calibration has authority."""
        return (
            float(self.lower_bound)
            if self.calibrated
            else float(self.raw_predicted_relief))

    def to_dict(self):
        return {
            "abstention_reason": self.abstention_reason,
            "calibrated": bool(self.calibrated),
            "confidence_half_width": float(
                self.confidence_half_width),
            "decision_relief": float(self.decision_relief),
            "estimator_id": self.estimator_id,
            "expected_realized_relief": float(
                self.expected_realized_relief),
            "key": self.key.to_dict(),
            "lower_bound": float(self.lower_bound),
            "model_state_hash": self.model_state_hash,
            "raw_predicted_relief": float(
                self.raw_predicted_relief),
            "residual_mean": float(self.residual_mean),
            "residual_variance": float(
                self.residual_variance),
            "sample_count": int(self.sample_count),
            "support_source": self.support_source,
            "upper_bound": float(self.upper_bound),
        }


@dataclass(frozen=True)
class TransitionValueUpdate:
    observation_id: str
    applied: bool
    key: TransitionValueKey
    sample_count: int
    model_state_hash: str
    observation: TransitionValueObservation

    def __post_init__(self):
        if not isinstance(
                self.observation,
                TransitionValueObservation):
            raise TypeError(
                "transition update requires observation")
        if self.observation.observation_id != (
                self.observation_id):
            raise ValueError(
                "transition update observation ID mismatch")
        if self.observation.key != self.key:
            raise ValueError(
                "transition update key mismatch")

    def to_dict(self):
        return {
            "applied": bool(self.applied),
            "key": self.key.to_dict(),
            "model_state_hash": self.model_state_hash,
            "observation":
                self.observation.to_dict(),
            "observation_id": self.observation_id,
            "sample_count": int(self.sample_count),
        }


def candidate_lifecycle_state(candidate):
    """Return a bounded semantic lifecycle class for an Impact candidate."""
    projection = getattr(candidate, "projection", None) or {}
    for name in (
            "transition_lifecycle_state",
            "lifecycle_state", "lifecycle_stage"):
        declared = projection.get(name)
        if isinstance(declared, str) and declared:
            # Keep user-controlled labels bounded and artifact-safe.  Explicit
            # labels are semantic configuration, not inferred truth.
            return "declared:{}".format(declared[:64])
    if bool(getattr(candidate, "terminal_on_accept", False)):
        return "terminal-completion"
    action = getattr(candidate, "action", None) or {}
    action_type = str(action.get("action_type", "unknown"))
    if action_type == "unit_build_city":
        return "terminal-completion"
    if action_type in (
            "unit_move", "unit_transport", "unit_goto"):
        return "route-progress"
    if action_type == "city_production":
        return "production-commitment"
    if action_type in (
            "player_rates", "government_change"):
        return "policy-transition"
    if action_type in (
            "unit_attack", "unit_bombard",
            "unit_nuke", "unit_bribe"):
        return "tactical-execution"
    if bool(projection.get("reversible", True)):
        return "reversible-execution"
    return "irreversible-execution"


class TransitionValueModel:
    """Idempotent category/lifecycle residual calibration.

    Exact-key confidence is the only source of decision authority.  Broader
    support can be reported by downstream audits, but is never silently pooled
    into this estimate.
    """

    def __init__(
            self, path=None, identity="in-memory",
            minimum_samples=30,
            maximum_half_width=0.50,
            alpha=0.05, read_only=False):
        _required_text(str(identity), "transition model identity")
        if (isinstance(minimum_samples, bool)
                or not isinstance(minimum_samples, int)
                or minimum_samples < 1):
            raise ValueError(
                "minimum samples must be positive")
        maximum_half_width = float(maximum_half_width)
        if (not math.isfinite(maximum_half_width)
                or not 0.0 < maximum_half_width <= 1.0):
            raise ValueError(
                "maximum half width must be in (0,1]")
        alpha = float(alpha)
        if not math.isfinite(alpha) or not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be in (0,1)")
        if not isinstance(read_only, bool):
            raise TypeError("read_only must be boolean")
        self.path = None if path is None else os.path.abspath(path)
        self.identity = str(identity)
        self.minimum_samples = minimum_samples
        self.maximum_half_width = maximum_half_width
        self.alpha = alpha
        self.read_only = read_only
        self._lock = threading.RLock()
        self._observations = {}
        self._state_hash_cache = None
        if self.path is not None and os.path.isfile(self.path):
            self._load()
        elif self.read_only:
            raise ValueError(
                "frozen transition model path does not exist")

    def _configuration(self):
        return {
            "alpha": self.alpha,
            "estimator_id": TRANSITION_VALUE_MODEL_ID,
            "maximum_half_width": self.maximum_half_width,
            "minimum_samples": self.minimum_samples,
        }

    def _hash_material(self):
        return {
            "configuration": self._configuration(),
            "identity": self.identity,
            "observations": [
                self._observations[key].to_dict()
                for key in sorted(self._observations)
            ],
            "schema_version":
                TRANSITION_VALUE_SCHEMA_VERSION,
            "update_scope": "control-model-only",
        }

    @property
    def state_hash(self):
        with self._lock:
            if self._state_hash_cache is None:
                self._state_hash_cache = structural_hash(
                    self._hash_material())
            return self._state_hash_cache

    def snapshot(self, include_observations=True):
        with self._lock:
            value = self._hash_material()
            if not include_observations:
                value.pop("observations")
                value["observation_count"] = len(
                    self._observations)
            value["read_only"] = bool(self.read_only)
            value["state_hash"] = self.state_hash
            return value

    @staticmethod
    def _observation(value):
        key = value["key"]
        return TransitionValueObservation(
            observation_id=str(value["observation_id"]),
            key=TransitionValueKey(
                action_category=str(
                    key["action_category"]),
                lifecycle_state=str(
                    key["lifecycle_state"]),
                goal_id=str(key["goal_id"])),
            predicted_relief=float(
                value["predicted_relief"]),
            realized_relief=float(
                value["realized_relief"]),
            effect_observed=bool(
                value["effect_observed"]),
            relief_source=str(value["relief_source"]),
            context_digest=str(value["context_digest"]),
            selection_propensity=value.get(
                "selection_propensity"),
            update_scope=str(value.get(
                "update_scope",
                "control-model-only")))

    def _load(self):
        with open(self.path, encoding="utf-8") as stream:
            value = json.load(stream)
        if value.get("schema_version") != (
                TRANSITION_VALUE_SCHEMA_VERSION):
            raise ValueError(
                "unsupported transition-value schema")
        if value.get("identity") != self.identity:
            raise ValueError(
                "transition-value identity mismatch")
        if value.get("configuration") != self._configuration():
            raise ValueError(
                "transition-value configuration mismatch")
        rows = value.get("observations")
        if not isinstance(rows, list):
            raise ValueError(
                "transition-value observations must be a list")
        observations = {}
        for row in rows:
            observation = self._observation(row)
            existing = observations.get(
                observation.observation_id)
            if existing is not None and existing != observation:
                raise ValueError(
                    "transition observation identity collision")
            observations[
                observation.observation_id] = observation
        self._observations = observations
        self._state_hash_cache = None
        if value.get("state_hash") != self.state_hash:
            raise ValueError(
                "transition-value state hash mismatch")

    def save(self):
        with self._lock:
            value = self.snapshot()
            if self.path is None:
                return value["state_hash"]
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            temporary = self.path + ".tmp.{}".format(
                os.getpid())
            with open(temporary, "wb") as stream:
                stream.write(canonical_json_bytes(value))
                stream.write(b"\n")
            os.replace(temporary, self.path)
            return value["state_hash"]

    def observe(self, observation):
        return self.observe_many((observation,))[0]

    def observe_many(self, observations):
        """Apply a validated batch atomically and persist it once."""
        observations = tuple(observations)
        if not observations:
            return ()
        for observation in observations:
            if not isinstance(
                    observation,
                    TransitionValueObservation):
                raise TypeError(
                    "transition model requires "
                    "TransitionValueObservation")
        with self._lock:
            if self.read_only:
                raise ValueError(
                    "frozen transition model is read-only")
            staged = dict(self._observations)
            applied = []
            for observation in observations:
                existing = staged.get(
                    observation.observation_id)
                if (existing is not None
                        and existing != observation):
                    raise ValueError(
                        "transition observation identity collision")
                is_new = existing is None
                applied.append(is_new)
                if is_new:
                    staged[
                        observation.observation_id] = observation
            if any(applied):
                self._observations = staged
                self._state_hash_cache = None
                state_hash = self.save()
            else:
                state_hash = self.state_hash
            counts = {}
            for row in self._observations.values():
                counts[row.key] = (
                    counts.get(row.key, 0) + 1)
            return tuple(
                TransitionValueUpdate(
                    observation.observation_id,
                    was_applied,
                    observation.key,
                    counts[observation.key],
                    state_hash,
                    observation)
                for observation, was_applied
                in zip(observations, applied))

    def observations_for(self, key):
        if not isinstance(key, TransitionValueKey):
            raise TypeError(
                "transition support requires TransitionValueKey")
        with self._lock:
            return tuple(
                self._observations[name]
                for name in sorted(self._observations)
                if self._observations[name].key == key)

    def estimate(self, key, raw_predicted_relief):
        if not isinstance(key, TransitionValueKey):
            raise TypeError(
                "transition estimate requires TransitionValueKey")
        raw = _probability(
            raw_predicted_relief,
            "raw predicted relief")
        rows = self.observations_for(key)
        count = len(rows)
        residuals = tuple(row.residual for row in rows)
        residual_mean = (
            sum(residuals) / count if count else 0.0)
        residual_variance = (
            sum(
                (value - residual_mean) ** 2
                for value in residuals)
            / (count - 1)
            if count > 1 else 0.0)
        # A bounded Hoeffding interval remains valid when observed residual
        # variance happens to be zero. Residuals lie in [-1,1], hence range 2.
        half_width = (
            min(
                1.0,
                2.0 * math.sqrt(
                    math.log(2.0 / self.alpha)
                    / (2.0 * count)))
            if count else 1.0)
        expected = min(
            1.0, max(0.0, raw + residual_mean))
        lower = min(
            expected,
            max(0.0, expected - half_width))
        upper = max(
            expected,
            min(1.0, expected + half_width))
        if count < self.minimum_samples:
            reason = "insufficient-exact-support"
        elif half_width > self.maximum_half_width:
            reason = "confidence-interval-too-wide"
        else:
            reason = None
        return TransitionValueEstimate(
            key=key,
            raw_predicted_relief=raw,
            expected_realized_relief=expected,
            lower_bound=lower,
            upper_bound=upper,
            residual_mean=residual_mean,
            residual_variance=residual_variance,
            confidence_half_width=half_width,
            sample_count=count,
            calibrated=reason is None,
            abstention_reason=reason,
            estimator_id=TRANSITION_VALUE_MODEL_ID,
            model_state_hash=self.state_hash)

    def decision_snapshot(self):
        with self._lock:
            keys = sorted(set(
                row.key
                for row in self._observations.values()))
            return {
                "configuration": self._configuration(),
                "exact_support": [
                    {
                        "key": key.to_dict(),
                        "sample_count": len(
                            self.observations_for(key)),
                    }
                    for key in keys
                ],
                "identity": self.identity,
                "observation_count": len(
                    self._observations),
                "read_only": bool(self.read_only),
                "schema_version":
                    TRANSITION_VALUE_SCHEMA_VERSION,
                "state_hash": self.state_hash,
                "update_scope": "control-model-only",
            }
