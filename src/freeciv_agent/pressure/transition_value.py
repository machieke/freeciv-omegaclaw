"""Calibrated realized goal-relief estimates for grounded control actions.

This module is deliberately control-only.  It consumes authoritative
post-action goal-relief measurements, but exposes no truth or evidence update
surface.
"""

import json
import math
import os
import random
import threading
from dataclasses import dataclass

from ..events.schema import canonical_json_bytes, structural_hash


TRANSITION_VALUE_SCHEMA_VERSION = "1.0"
TRANSITION_VALUE_MODEL_ID = "category-lifecycle-relief-calibrator/1.0"
CONTEXTUAL_TRANSITION_VALUE_SCHEMA_VERSION = "2.0"
CONTEXTUAL_TRANSITION_VALUE_MODEL_ID = (
    "support-aware-contextual-relief-calibrator/2.0")
CONTEXTUAL_SUPPORT_LEVELS = (
    "exact-context",
    "action-actor-target-threat-horizon",
    "action-actor",
    "action-category",
    "global-prior",
)


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


def candidate_action_category(candidate):
    """Return a bounded grounded-action family for calibration support.

    Planner microcategories describe tactical rationale and are too sparse for
    selected-action calibration. Goal ID preserves the strategic objective;
    this field identifies the grounded kind of transition being attempted.
    """
    action = getattr(candidate, "action", None) or {}
    action_type = str(
        action.get("action_type", "")).strip()
    if action_type == "city_production":
        return "production"
    if action_type == "city_governor":
        return "city-policy"
    if action_type == "player_rates":
        return "fiscal-policy"
    if action_type == "government_change":
        return "government-policy"
    if action_type == "unit_build_city":
        return "settlement"
    if action_type in (
            "unit_move", "unit_goto",
            "unit_transport"):
        return "movement"
    if action_type in (
            "unit_fortify", "unit_sentry",
            "unit_pillage"):
        return "unit-posture"
    if action_type in (
            "unit_attack", "unit_bombard",
            "unit_nuke", "unit_bribe",
            "unit_suicide_attack"):
        return "combat"
    if action_type:
        return "grounded:{}".format(
            action_type[:64])
    category = str(
        getattr(candidate, "category", "")).strip()
    return "planner:{}".format(
        category[:64] or "unknown")


def candidate_transition_context(
        candidate, snapshot,
        ruleset_digest, ruleset_family,
        horizon_turn, goal_id,
        estimator_version=(
            CONTEXTUAL_TRANSITION_VALUE_MODEL_ID),
        policy_version="scalar-v2/1.0"):
    """Build a bounded context solely from declared/player-visible inputs."""
    _required_text(
        str(ruleset_digest),
        "ruleset digest")
    _required_text(
        str(ruleset_family),
        "ruleset family")
    _required_text(
        str(goal_id), "goal ID")
    if (
            isinstance(horizon_turn, bool)
            or not isinstance(
                horizon_turn, int)
    ):
        raise ValueError(
            "context horizon turn must be an integer")
    current_turn = int(
        getattr(snapshot, "turn", 0))
    horizon = max(
        0, horizon_turn - current_turn)
    if horizon <= 1:
        horizon_bucket = "immediate:0-1"
    elif horizon <= 3:
        horizon_bucket = "short:2-3"
    elif horizon <= 10:
        horizon_bucket = "medium:4-10"
    else:
        horizon_bucket = "long:11+"
    action = getattr(
        candidate, "action", None) or {}
    projection = getattr(
        candidate, "projection", None) or {}
    action_type = str(
        action.get(
            "action_type", "unknown"))
    actor_class = projection.get(
        "transition_actor_class")
    if not isinstance(
            actor_class, str) or not actor_class:
        if action_type.startswith("city_"):
            actor_class = "city"
        elif action_type.startswith("unit_"):
            actor_class = "unit:unknown"
            actor_id = action.get("actor_id")
            unit_accessor = getattr(
                snapshot, "unit", None)
            unit = (
                unit_accessor(actor_id)
                if callable(unit_accessor)
                and isinstance(actor_id, int)
                and not isinstance(actor_id, bool)
                else None)
            unit_type = getattr(
                unit, "unit_type", None)
            if (
                    isinstance(unit_type, str)
                    and unit_type
            ):
                actor_class = (
                    "unit:{}".format(
                        unit_type[:64]))
        elif action_type.startswith(
                ("player_", "government_")):
            actor_class = "player"
        else:
            actor_class = "actor:unknown"
    target_class = projection.get(
        "transition_target_class")
    if not isinstance(
            target_class, str) or not target_class:
        target = action.get("target")
        target = (
            target
            if isinstance(target, dict)
            else {})
        if (
                "city_id" in target
                or "city_id" in action
        ):
            target_class = "city"
        elif (
                "unit_id" in target
                or "target_unit_id" in action
        ):
            target_class = "unit"
        elif any(
                name in target
                for name in (
                    "tile", "tile_id",
                    "x", "y")):
            target_class = "tile"
        elif action_type in (
                "player_rates",
                "government_change",
                "tech_research"):
            target_class = "player-policy"
        else:
            target_class = "target:unknown"
    threat_bucket = projection.get(
        "transition_threat_bucket")
    if not isinstance(
            threat_bucket, str) or not threat_bucket:
        threat_eta = projection.get(
            "threat_eta_turns")
        if (
                isinstance(threat_eta, (int, float))
                and not isinstance(
                    threat_eta, bool)
                and math.isfinite(
                    float(threat_eta))
        ):
            if float(threat_eta) <= 1.0:
                threat_bucket = "immediate:0-1"
            elif float(threat_eta) <= 3.0:
                threat_bucket = "near:2-3"
            else:
                threat_bucket = "distant:4+"
        else:
            threat_bucket = "unknown"
    context_features = projection.get(
        "transition_context_features")
    if not isinstance(
            context_features, dict):
        context_features = {}
    context = TransitionContextKey(
        exact_context_digest=structural_hash({
            "action_category":
                candidate_action_category(
                    candidate),
            "action_type": action_type,
            "actor_class": actor_class,
            "context_features":
                context_features,
            "horizon_bucket":
                horizon_bucket,
            "lifecycle_state":
                candidate_lifecycle_state(
                    candidate),
            "ruleset_digest":
                str(ruleset_digest),
            "target_class":
                target_class,
            "threat_bucket":
                threat_bucket,
        }),
        action_type=action_type,
        action_category=(
            candidate_action_category(
                candidate)),
        actor_class=actor_class,
        target_class=target_class,
        threat_bucket=threat_bucket,
        horizon_bucket=horizon_bucket,
        lifecycle_state=(
            candidate_lifecycle_state(
                candidate)),
        ruleset_digest=str(
            ruleset_digest),
        ruleset_family=str(
            ruleset_family))
    return ContextualTransitionValueKey(
        goal_id=str(goal_id),
        context=context,
        estimator_version=str(
            estimator_version),
        policy_version=str(
            policy_version))


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


@dataclass(frozen=True, order=True)
class TransitionContextKey:
    """Predeclared semantic context for a v2 transition-value estimate."""

    exact_context_digest: str
    action_type: str
    action_category: str
    actor_class: str
    target_class: str
    threat_bucket: str
    horizon_bucket: str
    lifecycle_state: str
    ruleset_digest: str
    ruleset_family: str

    def __post_init__(self):
        for value, name in (
                (self.exact_context_digest,
                 "exact context digest"),
                (self.action_type, "action type"),
                (self.action_category,
                 "action category"),
                (self.actor_class, "actor class"),
                (self.target_class, "target class"),
                (self.threat_bucket, "threat bucket"),
                (self.horizon_bucket, "horizon bucket"),
                (self.lifecycle_state,
                 "lifecycle state"),
                (self.ruleset_digest,
                 "ruleset digest"),
                (self.ruleset_family,
                 "ruleset family")):
            _required_text(value, name)

    def to_dict(self):
        return {
            "action_category":
                self.action_category,
            "action_type": self.action_type,
            "actor_class": self.actor_class,
            "exact_context_digest":
                self.exact_context_digest,
            "horizon_bucket":
                self.horizon_bucket,
            "lifecycle_state":
                self.lifecycle_state,
            "ruleset_digest":
                self.ruleset_digest,
            "ruleset_family":
                self.ruleset_family,
            "target_class": self.target_class,
            "threat_bucket": self.threat_bucket,
        }


@dataclass(frozen=True, order=True)
class TransitionSupportKey:
    """One explicit node in the declared contextual backoff hierarchy."""

    level: str
    goal_id: str
    ruleset_family: str
    estimator_version: str
    policy_version: str
    ruleset_digest: str = ""
    action_category: str = ""
    action_type: str = ""
    actor_class: str = ""
    target_class: str = ""
    threat_bucket: str = ""
    horizon_bucket: str = ""
    lifecycle_state: str = ""
    exact_context_digest: str = ""

    def __post_init__(self):
        if self.level not in CONTEXTUAL_SUPPORT_LEVELS:
            raise ValueError(
                "unknown contextual support level")
        _required_text(self.goal_id, "goal ID")
        _required_text(
            self.ruleset_family,
            "ruleset family")
        _required_text(
            self.estimator_version,
            "estimator version")
        _required_text(
            self.policy_version,
            "policy version")
        required = {
            "exact-context": (
                "ruleset_digest",
                "action_category", "action_type",
                "actor_class", "target_class",
                "threat_bucket", "horizon_bucket",
                "lifecycle_state",
                "exact_context_digest",
            ),
            "action-actor-target-threat-horizon": (
                "ruleset_digest",
                "action_category", "action_type",
                "actor_class", "target_class",
                "threat_bucket", "horizon_bucket",
                "lifecycle_state",
            ),
            "action-actor": (
                "action_type", "actor_class",
            ),
            "action-category": (
                "action_category",),
            "global-prior": (),
        }[self.level]
        for name in required:
            _required_text(
                getattr(self, name),
                "{} {}".format(
                    self.level, name))

    @property
    def stable_id(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "action_category":
                self.action_category or None,
            "action_type":
                self.action_type or None,
            "actor_class":
                self.actor_class or None,
            "exact_context_digest":
                self.exact_context_digest or None,
            "estimator_version":
                self.estimator_version,
            "goal_id": self.goal_id,
            "horizon_bucket":
                self.horizon_bucket or None,
            "level": self.level,
            "lifecycle_state":
                self.lifecycle_state or None,
            "ruleset_digest":
                self.ruleset_digest or None,
            "ruleset_family":
                self.ruleset_family,
            "policy_version":
                self.policy_version,
            "target_class":
                self.target_class or None,
            "threat_bucket":
                self.threat_bucket or None,
        }


@dataclass(frozen=True, order=True)
class ContextualTransitionValueKey:
    """Versioned v2 value key with an explicit context hierarchy."""

    goal_id: str
    context: TransitionContextKey
    estimator_version: str
    policy_version: str

    def __post_init__(self):
        _required_text(self.goal_id, "goal ID")
        if not isinstance(
                self.context,
                TransitionContextKey):
            raise TypeError(
                "contextual value key requires TransitionContextKey")
        _required_text(
            self.estimator_version,
            "estimator version")
        _required_text(
            self.policy_version,
            "policy version")

    @property
    def stable_id(self):
        return structural_hash(self.to_dict())

    def support_hierarchy(self):
        """Return the exact, declared parent chain without implicit pooling."""
        context = self.context
        common = {
            "estimator_version":
                self.estimator_version,
            "goal_id": self.goal_id,
            "policy_version":
                self.policy_version,
            "ruleset_family":
                context.ruleset_family,
        }
        return (
            TransitionSupportKey(
                level="exact-context",
                ruleset_digest=(
                    context.ruleset_digest),
                action_category=(
                    context.action_category),
                action_type=context.action_type,
                actor_class=context.actor_class,
                target_class=context.target_class,
                threat_bucket=(
                    context.threat_bucket),
                horizon_bucket=(
                    context.horizon_bucket),
                lifecycle_state=(
                    context.lifecycle_state),
                exact_context_digest=(
                    context.exact_context_digest),
                **common),
            TransitionSupportKey(
                level=(
                    "action-actor-target-"
                    "threat-horizon"),
                ruleset_digest=(
                    context.ruleset_digest),
                action_category=(
                    context.action_category),
                action_type=context.action_type,
                actor_class=context.actor_class,
                target_class=context.target_class,
                threat_bucket=(
                    context.threat_bucket),
                horizon_bucket=(
                    context.horizon_bucket),
                lifecycle_state=(
                    context.lifecycle_state),
                **common),
            TransitionSupportKey(
                level="action-actor",
                action_type=context.action_type,
                actor_class=context.actor_class,
                **common),
            TransitionSupportKey(
                level="action-category",
                action_category=(
                    context.action_category),
                **common),
            TransitionSupportKey(
                level="global-prior",
                **common),
        )

    def to_dict(self):
        return {
            "context": self.context.to_dict(),
            "estimator_version":
                self.estimator_version,
            "goal_id": self.goal_id,
            "policy_version":
                self.policy_version,
            "schema_version":
                CONTEXTUAL_TRANSITION_VALUE_SCHEMA_VERSION,
        }


@dataclass(frozen=True)
class ContextualOutcomeRecord:
    """One v2 prediction paired with an authoritative causal outcome."""

    observation_id: str
    key: ContextualTransitionValueKey
    selected_policy_id: str
    selection_policy_kind: str
    selection_propensity: object
    action_id: str
    operation_id: str
    predicted_transition_digest: str
    predicted_relief: float
    realized_outcome_digest: object
    realized_goal_relief: object
    adverse_loss: object
    adverse_loss_status: str
    eligibility_trace: tuple
    causal_status: str
    outcome_status: str
    estimator_version: str
    policy_version: str
    relief_source: object
    update_scope: str = "control-model-only"

    def __post_init__(self):
        _required_text(
            self.observation_id,
            "observation ID")
        if not isinstance(
                self.key,
                ContextualTransitionValueKey):
            raise TypeError(
                "contextual outcome requires a v2 value key")
        _required_text(
            self.selected_policy_id,
            "selected policy ID")
        if self.selection_policy_kind not in (
                "deterministic", "stochastic"):
            raise ValueError(
                "selection policy kind must be deterministic or stochastic")
        if self.selection_policy_kind == "stochastic":
            if self.selection_propensity is None:
                raise ValueError(
                    "stochastic selection requires propensity")
            propensity = float(
                self.selection_propensity)
            if (
                    not math.isfinite(propensity)
                    or not 0.0 < propensity <= 1.0
            ):
                raise ValueError(
                    "selection propensity must be in (0,1]")
        elif self.selection_propensity is not None:
            raise ValueError(
                "deterministic selection cannot invent propensity")
        for value, name in (
                (self.action_id, "action ID"),
                (self.operation_id, "operation ID"),
                (self.predicted_transition_digest,
                 "predicted transition digest"),
                (self.estimator_version,
                 "estimator version"),
                (self.policy_version,
                 "policy version")):
            _required_text(value, name)
        if (
                self.estimator_version
                != self.key.estimator_version
                or self.policy_version
                != self.key.policy_version
        ):
            raise ValueError(
                "outcome versions must match contextual key")
        _probability(
            self.predicted_relief,
            "predicted relief")
        if self.causal_status not in (
                "eligible", "ineligible", "unknown"):
            raise ValueError(
                "unknown causal status")
        if self.outcome_status not in (
                "terminal", "no-effect", "unknown"):
            raise ValueError(
                "unknown outcome status")
        trace = tuple(self.eligibility_trace)
        if (
                not trace
                or trace != tuple(sorted(set(trace)))
                or any(
                    not isinstance(value, str)
                    or not value
                    for value in trace)
        ):
            raise ValueError(
                "eligibility trace must be non-empty, unique, and sorted")
        known = (
            self.outcome_status != "unknown"
            and self.causal_status
            != "unknown")
        if self.adverse_loss_status not in (
                "observed", "unknown"):
            raise ValueError(
                "adverse loss status must be observed or unknown")
        if known:
            if self.realized_outcome_digest is None:
                raise ValueError(
                    "known outcome requires digest")
            _required_text(
                self.realized_outcome_digest,
                "realized outcome digest")
            _probability(
                self.realized_goal_relief,
                "realized goal relief")
            if self.adverse_loss_status == "observed":
                _probability(
                    self.adverse_loss,
                    "adverse loss")
            elif self.adverse_loss is not None:
                raise ValueError(
                    "unknown adverse loss must remain absent")
            _required_text(
                self.relief_source,
                "relief source")
            if not self.relief_source.startswith(
                    "authoritative:"):
                raise ValueError(
                    "contextual calibration requires authoritative relief")
            if (
                    self.outcome_status == "no-effect"
                    and float(
                        self.realized_goal_relief)
                    != 0.0
            ):
                raise ValueError(
                    "no-effect outcome cannot claim goal relief")
        elif (
                self.adverse_loss_status != "unknown"
                or any(value is not None for value in (
                    self.realized_outcome_digest,
                    self.realized_goal_relief,
                    self.adverse_loss,
                    self.relief_source))
        ):
            raise ValueError(
                "unknown outcome fields must remain absent")
        if self.update_scope != (
                "control-model-only"):
            raise ValueError(
                "contextual calibration cannot update truth")

    @property
    def eligible_for_calibration(self):
        return bool(
            self.causal_status == "eligible"
            and self.outcome_status
            in ("terminal", "no-effect"))

    @property
    def residual(self):
        if not self.eligible_for_calibration:
            return None
        return (
            float(self.realized_goal_relief)
            - float(self.predicted_relief))

    @property
    def conductance_value(self):
        if (
                not self.eligible_for_calibration
                or self.adverse_loss_status
                != "observed"
        ):
            return None
        return min(
            1.0, max(
                0.0,
                float(self.realized_goal_relief)
                - float(self.adverse_loss)))

    def to_dict(self):
        return {
            "action_id": self.action_id,
            "adverse_loss": self.adverse_loss,
            "adverse_loss_status":
                self.adverse_loss_status,
            "causal_status": self.causal_status,
            "eligibility_trace": list(
                self.eligibility_trace),
            "estimator_version":
                self.estimator_version,
            "key": self.key.to_dict(),
            "observation_id":
                self.observation_id,
            "operation_id": self.operation_id,
            "outcome_status":
                self.outcome_status,
            "policy_version":
                self.policy_version,
            "predicted_relief":
                float(self.predicted_relief),
            "predicted_transition_digest":
                self.predicted_transition_digest,
            "realized_goal_relief":
                self.realized_goal_relief,
            "realized_outcome_digest":
                self.realized_outcome_digest,
            "relief_source": self.relief_source,
            "selected_policy_id":
                self.selected_policy_id,
            "selection_policy_kind":
                self.selection_policy_kind,
            "selection_propensity":
                self.selection_propensity,
            "update_scope": self.update_scope,
        }


@dataclass(frozen=True)
class ContextualTransitionValueEstimate:
    """Support-aware v2 correction with a conservative authority boundary."""

    key: ContextualTransitionValueKey
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
    support_key: object
    declared_parent: object
    parent_expected_realized_relief: float
    contextual_conductance: float
    conductance_sample_count: int
    conductance_supported: bool
    frozen_model: bool

    def __post_init__(self):
        if not isinstance(
                self.key,
                ContextualTransitionValueKey):
            raise TypeError(
                "contextual estimate requires v2 key")
        for value, name in (
                (self.raw_predicted_relief,
                 "raw predicted relief"),
                (self.expected_realized_relief,
                 "expected realized relief"),
                (self.lower_bound, "lower bound"),
                (self.upper_bound, "upper bound"),
                (self.parent_expected_realized_relief,
                 "parent expected relief"),
                (self.contextual_conductance,
                 "contextual conductance")):
            _probability(value, name)
        if not (
                self.lower_bound
                <= self.expected_realized_relief
                <= self.upper_bound):
            raise ValueError(
                "contextual bounds must contain expectation")
        if (
                isinstance(self.sample_count, bool)
                or not isinstance(
                    self.sample_count, int)
                or self.sample_count < 0
        ):
            raise ValueError(
                "contextual sample count must be non-negative")
        if (
                isinstance(
                    self.conductance_sample_count,
                    bool)
                or not isinstance(
                    self.conductance_sample_count,
                    int)
                or self.conductance_sample_count < 0
        ):
            raise ValueError(
                "conductance sample count must be non-negative")
        if not isinstance(
                self.conductance_supported, bool):
            raise TypeError(
                "conductance support must be boolean")
        if self.calibrated != (
                self.abstention_reason is None):
            raise ValueError(
                "contextual calibration and abstention disagree")
        if self.support_key is not None and not isinstance(
                self.support_key,
                TransitionSupportKey):
            raise TypeError(
                "contextual support key has wrong type")
        if self.declared_parent is not None and not isinstance(
                self.declared_parent,
                TransitionSupportKey):
            raise TypeError(
                "declared parent has wrong type")
        if not isinstance(self.frozen_model, bool):
            raise TypeError(
                "frozen model status must be boolean")

    @property
    def decision_relief(self):
        return (
            float(self.lower_bound)
            if self.calibrated
            and self.frozen_model
            else float(
                self.raw_predicted_relief))

    @property
    def support_source(self):
        return (
            self.support_key.level
            if self.support_key is not None
            else "no-supported-context")

    def to_dict(self):
        return {
            "abstention_reason":
                self.abstention_reason,
            "calibrated": self.calibrated,
            "confidence_half_width":
                float(
                    self.confidence_half_width),
            "contextual_conductance":
                float(
                    self.contextual_conductance),
            "conductance_sample_count":
                self.conductance_sample_count,
            "conductance_supported":
                self.conductance_supported,
            "decision_relief":
                float(self.decision_relief),
            "declared_parent": (
                self.declared_parent.to_dict()
                if self.declared_parent
                is not None else None),
            "estimator_id": self.estimator_id,
            "expected_realized_relief":
                float(
                    self.expected_realized_relief),
            "frozen_model":
                self.frozen_model,
            "key": self.key.to_dict(),
            "lower_bound":
                float(self.lower_bound),
            "model_state_hash":
                self.model_state_hash,
            "parent_expected_realized_relief":
                float(
                    self.parent_expected_realized_relief),
            "raw_predicted_relief":
                float(
                    self.raw_predicted_relief),
            "residual_mean":
                float(self.residual_mean),
            "residual_variance":
                float(
                    self.residual_variance),
            "sample_count": self.sample_count,
            "support_key": (
                self.support_key.to_dict()
                if self.support_key
                is not None else None),
            "support_source":
                self.support_source,
            "upper_bound":
                float(self.upper_bound),
        }


@dataclass(frozen=True)
class ContextualTransitionValueUpdate:
    observation_id: str
    applied: bool
    exact_sample_count: int
    model_state_hash: str
    observation: ContextualOutcomeRecord

    def to_dict(self):
        return {
            "applied": self.applied,
            "exact_sample_count":
                self.exact_sample_count,
            "model_state_hash":
                self.model_state_hash,
            "observation":
                self.observation.to_dict(),
            "observation_id":
                self.observation_id,
            "schema_version":
                CONTEXTUAL_TRANSITION_VALUE_SCHEMA_VERSION,
        }


def _contextual_key(value):
    if not isinstance(value, dict):
        raise ValueError(
            "contextual transition key must be an object")
    context = value.get("context")
    if not isinstance(context, dict):
        raise ValueError(
            "contextual transition context is required")
    return ContextualTransitionValueKey(
        goal_id=str(value.get("goal_id", "")),
        context=TransitionContextKey(
            exact_context_digest=str(
                context.get(
                    "exact_context_digest", "")),
            action_type=str(
                context.get("action_type", "")),
            action_category=str(
                context.get(
                    "action_category", "")),
            actor_class=str(
                context.get("actor_class", "")),
            target_class=str(
                context.get("target_class", "")),
            threat_bucket=str(
                context.get("threat_bucket", "")),
            horizon_bucket=str(
                context.get("horizon_bucket", "")),
            lifecycle_state=str(
                context.get(
                    "lifecycle_state", "")),
            ruleset_digest=str(
                context.get("ruleset_digest", "")),
            ruleset_family=str(
                context.get("ruleset_family", ""))),
        estimator_version=str(
            value.get("estimator_version", "")),
        policy_version=str(
            value.get("policy_version", "")))


def _contextual_outcome(value):
    if not isinstance(value, dict):
        raise ValueError(
            "contextual outcome must be an object")
    return ContextualOutcomeRecord(
        observation_id=str(
            value.get("observation_id", "")),
        key=_contextual_key(value.get("key")),
        selected_policy_id=str(
            value.get("selected_policy_id", "")),
        selection_policy_kind=str(
            value.get(
                "selection_policy_kind", "")),
        selection_propensity=value.get(
            "selection_propensity"),
        action_id=str(
            value.get("action_id", "")),
        operation_id=str(
            value.get("operation_id", "")),
        predicted_transition_digest=str(
            value.get(
                "predicted_transition_digest", "")),
        predicted_relief=float(
            value.get("predicted_relief")),
        realized_outcome_digest=value.get(
            "realized_outcome_digest"),
        realized_goal_relief=value.get(
            "realized_goal_relief"),
        adverse_loss=value.get(
            "adverse_loss"),
        adverse_loss_status=str(
            value.get(
                "adverse_loss_status",
                "unknown")),
        eligibility_trace=tuple(
            value.get("eligibility_trace", ())),
        causal_status=str(
            value.get("causal_status", "")),
        outcome_status=str(
            value.get("outcome_status", "")),
        estimator_version=str(
            value.get("estimator_version", "")),
        policy_version=str(
            value.get("policy_version", "")),
        relief_source=value.get(
            "relief_source"),
        update_scope=str(value.get(
            "update_scope",
            "control-model-only")))


def contextual_outcome_from_dict(value):
    """Parse and validate one persisted v2 contextual outcome."""
    return _contextual_outcome(value)


class ContextualTransitionValueModel:
    """Frozen, support-aware v2 transition calibration and conductance."""

    def __init__(
            self, path=None, identity="in-memory-v2",
            minimum_samples=30,
            maximum_half_width=0.50,
            alpha=0.05, shrinkage_kappa=10.0,
            read_only=False):
        _required_text(
            str(identity),
            "contextual model identity")
        if (
                isinstance(minimum_samples, bool)
                or not isinstance(
                    minimum_samples, int)
                or minimum_samples < 1
        ):
            raise ValueError(
                "contextual minimum samples must be positive")
        maximum_half_width = float(
            maximum_half_width)
        if (
                not math.isfinite(
                    maximum_half_width)
                or not 0.0
                < maximum_half_width <= 1.0
        ):
            raise ValueError(
                "contextual maximum half width must be in (0,1]")
        alpha = float(alpha)
        if (
                not math.isfinite(alpha)
                or not 0.0 < alpha < 1.0
        ):
            raise ValueError(
                "contextual alpha must be in (0,1)")
        shrinkage_kappa = float(
            shrinkage_kappa)
        if (
                not math.isfinite(
                    shrinkage_kappa)
                or shrinkage_kappa < 0.0
        ):
            raise ValueError(
                "contextual shrinkage kappa must be non-negative")
        if not isinstance(read_only, bool):
            raise TypeError(
                "contextual read-only must be boolean")
        self.path = (
            None if path is None
            else os.path.abspath(path))
        self.identity = str(identity)
        self.minimum_samples = minimum_samples
        self.maximum_half_width = (
            maximum_half_width)
        self.alpha = alpha
        self.shrinkage_kappa = (
            shrinkage_kappa)
        self.read_only = read_only
        self._lock = threading.RLock()
        self._outcomes = {}
        self._support_index = {}
        self._legacy_category_priors = {}
        self._legacy_source_hashes = set()
        self._state_hash_cache = None
        if (
                self.path is not None
                and os.path.isfile(self.path)
        ):
            self._load()
        elif self.read_only:
            raise ValueError(
                "frozen contextual model path does not exist")

    def _configuration(self):
        return {
            "alpha": self.alpha,
            "estimator_id":
                CONTEXTUAL_TRANSITION_VALUE_MODEL_ID,
            "maximum_half_width":
                self.maximum_half_width,
            "minimum_samples":
                self.minimum_samples,
            "shrinkage_kappa":
                self.shrinkage_kappa,
            "support_hierarchy":
                list(CONTEXTUAL_SUPPORT_LEVELS),
        }

    def _hash_material(self):
        return {
            "configuration":
                self._configuration(),
            "identity": self.identity,
            "legacy_category_priors": [
                self._legacy_category_priors[key]
                for key in sorted(
                    self._legacy_category_priors)
            ],
            "legacy_source_hashes":
                sorted(
                    self._legacy_source_hashes),
            "outcomes": [
                self._outcomes[key].to_dict()
                for key in sorted(
                    self._outcomes)
            ],
            "schema_version":
                CONTEXTUAL_TRANSITION_VALUE_SCHEMA_VERSION,
            "update_scope":
                "control-model-only",
        }

    @property
    def state_hash(self):
        with self._lock:
            if self._state_hash_cache is None:
                self._state_hash_cache = (
                    structural_hash(
                        self._hash_material()))
            return self._state_hash_cache

    @property
    def outcome_ids(self):
        with self._lock:
            return frozenset(
                self._outcomes)

    def snapshot(
            self, include_outcomes=True):
        with self._lock:
            value = self._hash_material()
            if not include_outcomes:
                value.pop("outcomes")
                value["outcome_count"] = len(
                    self._outcomes)
            value["read_only"] = (
                self.read_only)
            value["state_hash"] = (
                self.state_hash)
            return value

    def _load(self):
        with open(
                self.path,
                encoding="utf-8") as stream:
            value = json.load(stream)
        if value.get("schema_version") != (
                CONTEXTUAL_TRANSITION_VALUE_SCHEMA_VERSION):
            raise ValueError(
                "unsupported contextual transition-value schema; "
                "v1 requires explicit category-prior migration")
        if value.get("identity") != (
                self.identity):
            raise ValueError(
                "contextual transition-value identity mismatch")
        if value.get("configuration") != (
                self._configuration()):
            raise ValueError(
                "contextual transition-value configuration mismatch")
        outcomes = {}
        for row in value.get("outcomes", ()):
            outcome = _contextual_outcome(row)
            existing = outcomes.get(
                outcome.observation_id)
            if (
                    existing is not None
                    and existing != outcome
            ):
                raise ValueError(
                    "contextual outcome identity collision")
            outcomes[
                outcome.observation_id] = outcome
        priors = {}
        for row in value.get(
                "legacy_category_priors", ()):
            if not isinstance(row, dict):
                raise ValueError(
                    "legacy category prior must be an object")
            support_value = row.get(
                "support_key")
            support = (
                TransitionSupportKey(
                    level=str(
                        support_value.get(
                            "level", "")),
                    goal_id=str(
                        support_value.get(
                            "goal_id", "")),
                    ruleset_family=str(
                        support_value.get(
                            "ruleset_family", "")),
                    estimator_version=str(
                        support_value.get(
                            "estimator_version", "")),
                    policy_version=str(
                        support_value.get(
                            "policy_version", "")),
                    action_category=str(
                        support_value.get(
                            "action_category")
                        or ""))
                if isinstance(
                    support_value, dict)
                else None)
            if (
                    support is None
                    or support.level
                    != "action-category"
            ):
                raise ValueError(
                    "legacy prior must remain category-only")
            checked = {
                "count": int(row["count"]),
                "mean_realized_relief":
                    _probability(
                        row[
                            "mean_realized_relief"],
                        "legacy mean relief"),
                "mean_residual": float(
                    row["mean_residual"]),
                "source_schema_version":
                    str(
                        row[
                            "source_schema_version"]),
                "support_key":
                    support.to_dict(),
            }
            if (
                    checked["count"] < 1
                    or not math.isfinite(
                        checked["mean_residual"])
            ):
                raise ValueError(
                    "legacy category prior is invalid")
            priors[
                support.stable_id] = checked
        hashes = value.get(
            "legacy_source_hashes", ())
        if (
                not isinstance(hashes, list)
                or any(
                    not isinstance(row, str)
                    or not row
                    for row in hashes)
        ):
            raise ValueError(
                "legacy source hashes are invalid")
        self._outcomes = outcomes
        self._rebuild_support_index()
        self._legacy_category_priors = (
            priors)
        self._legacy_source_hashes = set(
            hashes)
        self._state_hash_cache = None
        if value.get("state_hash") != (
                self.state_hash):
            raise ValueError(
                "contextual transition-value state hash mismatch")

    def save(self):
        with self._lock:
            value = self.snapshot()
            if self.path is None:
                return value["state_hash"]
            parent = os.path.dirname(
                self.path)
            if parent:
                os.makedirs(
                    parent, exist_ok=True)
            temporary = (
                self.path
                + ".tmp.{}".format(
                    os.getpid()))
            with open(
                    temporary, "wb") as stream:
                stream.write(
                    canonical_json_bytes(value))
                stream.write(b"\n")
            os.replace(
                temporary, self.path)
            return value["state_hash"]

    def import_legacy_v1(
            self, path, ruleset_family):
        """Import v1 rows strictly as a category prior, never exact support."""
        _required_text(
            ruleset_family,
            "legacy ruleset family")
        with open(
                os.path.abspath(path),
                encoding="utf-8") as stream:
            value = json.load(stream)
        if value.get("schema_version") != (
                TRANSITION_VALUE_SCHEMA_VERSION):
            raise ValueError(
                "legacy transition source must use schema 1.0")
        material = dict(value)
        source_hash = str(
            material.pop("state_hash", ""))
        material.pop("read_only", None)
        if (
                not source_hash
                or structural_hash(material)
                != source_hash
        ):
            raise ValueError(
                "legacy transition source hash mismatch")
        with self._lock:
            if self.read_only:
                raise ValueError(
                    "frozen contextual model is read-only")
            if source_hash in (
                    self._legacy_source_hashes):
                return False
            grouped = {}
            for row in value.get(
                    "observations", ()):
                key = row.get("key") or {}
                category = str(
                    key.get(
                        "action_category", ""))
                goal_id = str(
                    key.get("goal_id", ""))
                _required_text(
                    category,
                    "legacy action category")
                _required_text(
                    goal_id,
                    "legacy goal ID")
                predicted = _probability(
                    row.get("predicted_relief"),
                    "legacy predicted relief")
                realized = _probability(
                    row.get("realized_relief"),
                    "legacy realized relief")
                group = grouped.setdefault(
                    (category, goal_id), [])
                group.append((
                    realized - predicted,
                    realized))
            staged = dict(
                self._legacy_category_priors)
            for (
                    category, goal_id
                    ), rows in sorted(
                        grouped.items()):
                support = (
                    TransitionSupportKey(
                        level="action-category",
                        goal_id=goal_id,
                        ruleset_family=(
                            ruleset_family),
                        estimator_version=(
                            "legacy-v1/"
                            "category-prior"),
                        policy_version=(
                            "legacy-v1/"
                            "unknown-policy"),
                        action_category=category))
                existing = staged.get(
                    support.stable_id)
                if existing is not None:
                    raise ValueError(
                        "legacy category prior collision")
                staged[support.stable_id] = {
                    "count": len(rows),
                    "mean_realized_relief":
                        sum(
                            row[1] for row in rows)
                        / len(rows),
                    "mean_residual":
                        sum(
                            row[0] for row in rows)
                        / len(rows),
                    "source_schema_version":
                        TRANSITION_VALUE_SCHEMA_VERSION,
                    "support_key":
                        support.to_dict(),
                }
            self._legacy_category_priors = (
                staged)
            self._legacy_source_hashes.add(
                source_hash)
            self._state_hash_cache = None
            self.save()
            return True

    def observe(self, outcome):
        return self.observe_many((outcome,))[0]

    def _rebuild_support_index(self):
        index = {}
        for name in sorted(self._outcomes):
            outcome = self._outcomes[name]
            if not outcome.eligible_for_calibration:
                continue
            for support in (
                    outcome.key.support_hierarchy()):
                index.setdefault(
                    support, []).append(name)
        self._support_index = {
            support: tuple(names)
            for support, names in
            index.items()
        }

    def observe_many(self, outcomes):
        """Persist v2 records atomically; unknown outcomes remain excluded."""
        outcomes = tuple(outcomes)
        if not outcomes:
            return ()
        if any(
                not isinstance(
                    outcome,
                    ContextualOutcomeRecord)
                for outcome in outcomes):
            raise TypeError(
                "contextual model requires v2 outcome records")
        with self._lock:
            if self.read_only:
                raise ValueError(
                    "frozen contextual model is read-only")
            staged = dict(self._outcomes)
            applied = []
            for outcome in outcomes:
                existing = staged.get(
                    outcome.observation_id)
                if (
                        existing is not None
                        and existing != outcome
                ):
                    raise ValueError(
                        "contextual outcome identity collision")
                is_new = existing is None
                applied.append(is_new)
                if is_new:
                    staged[
                        outcome.observation_id] = outcome
            if any(applied):
                self._outcomes = staged
                self._rebuild_support_index()
                self._state_hash_cache = None
                state_hash = self.save()
            else:
                state_hash = self.state_hash
            updates = []
            for outcome, was_applied in zip(
                    outcomes, applied):
                exact = outcome.key.support_hierarchy()[0]
                count = len(
                    self.outcomes_for_support(
                        exact))
                updates.append(
                    ContextualTransitionValueUpdate(
                        observation_id=(
                            outcome.observation_id),
                        applied=was_applied,
                        exact_sample_count=count,
                        model_state_hash=(
                            state_hash),
                        observation=outcome))
            return tuple(updates)

    def outcomes_for_support(
            self, support_key,
            eligible_only=True):
        if not isinstance(
                support_key,
                TransitionSupportKey):
            raise TypeError(
                "contextual support requires TransitionSupportKey")
        with self._lock:
            names = (
                self._support_index.get(
                    support_key, ())
                if eligible_only
                else tuple(
                    name
                    for name in sorted(
                        self._outcomes)
                    if support_key in (
                        self._outcomes[name]
                        .key.support_hierarchy())))
            rows = tuple(
                self._outcomes[name]
                for name in names)
            return rows

    def _legacy_prior_for(
            self, support_key):
        if support_key.level != (
                "action-category"):
            return None
        matches = tuple(
            row
            for row in
            self._legacy_category_priors.values()
            if (
                row["support_key"][
                    "action_category"]
                == support_key.action_category
                and row["support_key"][
                    "goal_id"]
                == support_key.goal_id
                and row["support_key"][
                    "ruleset_family"]
                == support_key.ruleset_family
            ))
        if len(matches) > 1:
            raise ValueError(
                "multiple legacy priors match one category")
        return (
            matches[0]
            if matches else None)

    def _support_state(
            self, support_key,
            raw, parent):
        rows = self.outcomes_for_support(
            support_key)
        residuals = tuple(
            row.residual for row in rows)
        conductances = tuple(
            row.conductance_value
            for row in rows
            if row.conductance_value
            is not None)
        count = len(rows)
        conductance_count = len(
            conductances)
        observed_residual = (
            sum(residuals) / count
            if count else 0.0)
        observed_conductance = (
            sum(conductances)
            / conductance_count
            if conductance_count else 0.5)
        parent_residual = (
            parent["residual_mean"]
            if parent is not None
            else 0.0)
        parent_conductance = (
            parent["conductance"]
            if parent is not None
            else 0.5)
        legacy = self._legacy_prior_for(
            support_key)
        if legacy is not None:
            parent_residual = float(
                legacy["mean_residual"])
            parent_conductance = float(
                legacy[
                    "mean_realized_relief"])
        denominator = (
            count + self.shrinkage_kappa)
        if count and denominator > 0.0:
            residual_mean = (
                count * observed_residual
                + self.shrinkage_kappa
                * parent_residual
            ) / denominator
            conductance_denominator = (
                conductance_count
                + self.shrinkage_kappa)
            conductance = (
                (
                    conductance_count
                    * observed_conductance
                    + self.shrinkage_kappa
                    * parent_conductance)
                / conductance_denominator
                if conductance_denominator
                > 0.0
                else parent_conductance)
        elif count:
            residual_mean = observed_residual
            conductance = (
                observed_conductance
                if conductance_count
                else parent_conductance)
        else:
            residual_mean = parent_residual
            conductance = parent_conductance
        variance = (
            sum(
                (
                    value
                    - observed_residual) ** 2
                for value in residuals)
            / (count - 1)
            if count > 1 else 0.0)
        half_width = (
            min(
                1.0,
                2.0 * math.sqrt(
                    math.log(
                        2.0 / self.alpha)
                    / (2.0 * count)))
            if count else 1.0)
        expected = min(
            1.0, max(
                0.0,
                raw + residual_mean))
        return {
            "conductance": min(
                1.0, max(
                    0.0, conductance)),
            "count": count,
            "conductance_count":
                conductance_count,
            "expected": expected,
            "half_width": half_width,
            "legacy_prior": (
                legacy is not None),
            "residual_mean":
                residual_mean,
            "variance": variance,
        }

    def estimate(
            self, key,
            raw_predicted_relief):
        if not isinstance(
                key,
                ContextualTransitionValueKey):
            raise TypeError(
                "contextual estimate requires v2 key")
        raw = _probability(
            raw_predicted_relief,
            "raw predicted relief")
        hierarchy = (
            key.support_hierarchy())
        states = {}
        parent = None
        for support in reversed(hierarchy):
            state = self._support_state(
                support, raw, parent)
            states[support] = state
            parent = state
        supported = next((
            support
            for support in hierarchy
            if states[support]["count"]
            >= self.minimum_samples
            and states[support]["half_width"]
            <= self.maximum_half_width
        ), None)
        display = (
            supported
            or next((
                support
                for support in hierarchy
                if states[support]["count"]
                > 0
                or states[support][
                    "legacy_prior"]
            ), hierarchy[-1]))
        state = states[display]
        display_index = hierarchy.index(
            display)
        declared_parent = (
            hierarchy[display_index + 1]
            if display_index + 1
            < len(hierarchy)
            else None)
        parent_state = (
            states[declared_parent]
            if declared_parent is not None
            else {
                "expected": raw})
        if supported is None:
            reason = (
                "insufficient-declared-support")
        elif not self.read_only:
            reason = "mutable-model"
        else:
            reason = None
        expected = float(state["expected"])
        half_width = float(
            state["half_width"])
        return (
            ContextualTransitionValueEstimate(
                key=key,
                raw_predicted_relief=raw,
                expected_realized_relief=(
                    expected),
                lower_bound=min(
                    expected,
                    max(
                        0.0,
                        expected - half_width)),
                upper_bound=max(
                    expected,
                    min(
                        1.0,
                        expected + half_width)),
                residual_mean=float(
                    state["residual_mean"]),
                residual_variance=float(
                    state["variance"]),
                confidence_half_width=(
                    half_width),
                sample_count=int(
                    state["count"]),
                calibrated=reason is None,
                abstention_reason=reason,
                estimator_id=(
                    CONTEXTUAL_TRANSITION_VALUE_MODEL_ID),
                model_state_hash=(
                    self.state_hash),
                support_key=display,
                declared_parent=(
                    declared_parent),
                parent_expected_realized_relief=(
                    float(
                        parent_state[
                            "expected"])),
                contextual_conductance=float(
                    state["conductance"]),
                conductance_sample_count=int(
                    state[
                        "conductance_count"]),
                conductance_supported=bool(
                    state[
                        "conductance_count"]
                    >= self.minimum_samples),
                frozen_model=(
                    self.read_only)))

    def decision_snapshot(self):
        with self._lock:
            eligible = sum(
                row.eligible_for_calibration
                for row in
                self._outcomes.values())
            unknown = sum(
                row.outcome_status == "unknown"
                for row in
                self._outcomes.values())
            return {
                "configuration":
                    self._configuration(),
                "eligible_outcome_count":
                    eligible,
                "identity": self.identity,
                "legacy_category_prior_count":
                    len(
                        self._legacy_category_priors),
                "legacy_migration_scope":
                    "category-prior-only",
                "outcome_count":
                    len(self._outcomes),
                "read_only": self.read_only,
                "schema_version":
                    CONTEXTUAL_TRANSITION_VALUE_SCHEMA_VERSION,
                "state_hash": self.state_hash,
                "unknown_outcome_count":
                    unknown,
                "update_scope":
                    "control-model-only",
            }


@dataclass(frozen=True)
class ContextualCalibrationGate:
    """Predeclared holdout authority gate for one frozen v2 model."""

    minimum_coverage: float = 0.80
    maximum_context_brier_regression: float = 0.02
    bootstrap_iterations: int = 2000
    confidence_level: float = 0.95
    gate_id: str = "gdo8-contextual-holdout-gate/1.0"

    def __post_init__(self):
        for value, name in (
                (self.minimum_coverage,
                 "minimum coverage"),
                (self.maximum_context_brier_regression,
                 "maximum context Brier regression"),
                (self.confidence_level,
                 "confidence level")):
            value = float(value)
            if (
                    not math.isfinite(value)
                    or not 0.0 <= value <= 1.0
            ):
                raise ValueError(
                    "{} must be in [0,1]".format(
                        name))
        if (
                self.minimum_coverage <= 0.0
                or self.confidence_level
                <= 0.0
                or self.confidence_level
                >= 1.0
        ):
            raise ValueError(
                "coverage and confidence must be strictly bounded")
        if (
                isinstance(
                    self.bootstrap_iterations,
                    bool)
                or not isinstance(
                    self.bootstrap_iterations,
                    int)
                or self.bootstrap_iterations < 100
        ):
            raise ValueError(
                "bootstrap iterations must be at least 100")
        _required_text(
            self.gate_id, "gate ID")

    def to_dict(self):
        return {
            "bootstrap_iterations":
                self.bootstrap_iterations,
            "confidence_level":
                float(self.confidence_level),
            "gate_id": self.gate_id,
            "maximum_context_brier_regression":
                float(
                    self.maximum_context_brier_regression),
            "minimum_coverage":
                float(self.minimum_coverage),
        }

    @staticmethod
    def _mean(values):
        return (
            sum(values) / len(values)
            if values else 0.0)

    def _bootstrap_interval(
            self, improvements,
            seed_material):
        improvements = tuple(
            float(value)
            for value in improvements)
        if not improvements:
            return (0.0, 0.0)
        seed = int(
            structural_hash(
                seed_material)[:16], 16)
        generator = random.Random(seed)
        count = len(improvements)
        means = sorted(
            self._mean(tuple(
                improvements[
                    generator.randrange(count)]
                for _ in range(count)))
            for _ in range(
                self.bootstrap_iterations))
        tail = (
            1.0
            - float(self.confidence_level))
        low_index = max(
            0, int(math.floor(
                tail / 2.0
                * len(means))))
        high_index = min(
            len(means) - 1,
            int(math.ceil(
                (
                    1.0 - tail / 2.0)
                * len(means))) - 1)
        return (
            means[low_index],
            means[high_index])

    def evaluate(
            self, model, holdout_outcomes):
        """Evaluate without updating the frozen fit or coercing unknowns."""
        if not isinstance(
                model,
                ContextualTransitionValueModel):
            raise TypeError(
                "contextual holdout gate requires v2 model")
        if not model.read_only:
            raise ValueError(
                "contextual holdout evaluation requires frozen model")
        initial_state_hash = (
            model.state_hash)
        outcomes = tuple(
            holdout_outcomes)
        if any(
                not isinstance(
                    row,
                    ContextualOutcomeRecord)
                for row in outcomes):
            raise TypeError(
                "holdout rows must be contextual outcomes")
        ids = tuple(
            row.observation_id
            for row in outcomes)
        if (
                len(set(ids)) != len(ids)
                or set(ids).intersection(
                    model.outcome_ids)
        ):
            raise ValueError(
                "holdout outcomes overlap training or each other")
        eligible = tuple(
            row for row in outcomes
            if row.eligible_for_calibration)
        rows = []
        for outcome in eligible:
            estimate = model.estimate(
                outcome.key,
                outcome.predicted_relief)
            baseline = float(
                outcome.predicted_relief)
            contextual = (
                float(
                    estimate
                    .expected_realized_relief)
                if estimate.calibrated
                else baseline)
            realized = float(
                outcome.realized_goal_relief)
            baseline_brier = (
                baseline - realized) ** 2
            contextual_brier = (
                contextual - realized) ** 2
            rows.append({
                "baseline_brier":
                    baseline_brier,
                "contextual_brier":
                    contextual_brier,
                "improvement":
                    baseline_brier
                    - contextual_brier,
                "observation_id":
                    outcome.observation_id,
                "support_key": (
                    estimate.support_key),
                "supported":
                    estimate.calibrated,
            })
        coverage = (
            sum(row["supported"] for row in rows)
            / float(len(rows))
            if rows else 0.0)
        improvements = tuple(
            row["improvement"]
            for row in rows)
        interval = self._bootstrap_interval(
            improvements, {
                "gate": self.to_dict(),
                "model_state_hash":
                    model.state_hash,
                "observation_ids":
                    sorted(ids),
            })
        contexts = {}
        for row in rows:
            support = row["support_key"]
            if (
                    not row["supported"]
                    or support is None
            ):
                continue
            contexts.setdefault(
                support.stable_id, {
                    "baseline": [],
                    "contextual": [],
                    "support_key":
                        support.to_dict(),
                })
            contexts[
                support.stable_id][
                    "baseline"].append(
                        row[
                            "baseline_brier"])
            contexts[
                support.stable_id][
                    "contextual"].append(
                        row[
                            "contextual_brier"])
        context_rows = []
        for key in sorted(contexts):
            value = contexts[key]
            baseline = self._mean(
                value["baseline"])
            contextual = self._mean(
                value["contextual"])
            context_rows.append({
                "baseline_brier":
                    baseline,
                "brier_regression":
                    contextual - baseline,
                "contextual_brier":
                    contextual,
                "holdout_count": len(
                    value["baseline"]),
                "support_key":
                    value["support_key"],
            })
        high_volume = tuple(
            row for row in context_rows
            if row["holdout_count"]
            >= model.minimum_samples)
        gates = {
            "aggregate_95pct_interval_excludes_no_improvement":
                interval[0] > 0.0,
            "coverage_at_least_predeclared_minimum":
                coverage
                >= self.minimum_coverage,
            "frozen_model":
                model.read_only,
            "no_evaluation_updates":
                model.state_hash
                == initial_state_hash,
            "no_high_volume_context_regression":
                all(
                    row["brier_regression"]
                    <= (
                        self
                        .maximum_context_brier_regression)
                    for row in high_volume),
            "nonempty_eligible_holdout":
                bool(rows),
            "propensity_contract_complete":
                all(
                    row.selection_policy_kind
                    == "deterministic"
                    or row.selection_propensity
                    is not None
                    for row in outcomes),
            "unknown_outcomes_excluded":
                len(rows)
                == sum(
                    row.eligible_for_calibration
                    for row in outcomes),
        }
        report = {
            "aggregate": {
                "baseline_brier":
                    self._mean(tuple(
                        row["baseline_brier"]
                        for row in rows)),
                "bootstrap_improvement_interval":
                    list(interval),
                "contextual_brier":
                    self._mean(tuple(
                        row["contextual_brier"]
                        for row in rows)),
                "coverage": coverage,
                "eligible_holdout_count":
                    len(rows),
                "mean_brier_improvement":
                    self._mean(
                        improvements),
                "total_holdout_count":
                    len(outcomes),
                "unknown_or_ineligible_count":
                    len(outcomes) - len(rows),
            },
            "authority_approved":
                all(gates.values()),
            "context_results":
                context_rows,
            "gate": self.to_dict(),
            "gates": gates,
            "model_state_hash":
                model.state_hash,
            "schema_version":
                CONTEXTUAL_TRANSITION_VALUE_SCHEMA_VERSION,
        }
        report["report_hash"] = (
            structural_hash(report))
        return report


def validate_contextual_calibration_bundle(
        path, model):
    """Load a frozen holdout approval and bind it to the exact model state."""
    if not isinstance(
            model,
            ContextualTransitionValueModel):
        raise TypeError(
            "contextual approval requires v2 model")
    if not model.read_only:
        raise ValueError(
            "contextual approval requires frozen model")
    with open(
            os.path.abspath(path),
            encoding="utf-8") as stream:
        value = json.load(stream)
    if value.get("schema_version") != (
            CONTEXTUAL_TRANSITION_VALUE_SCHEMA_VERSION):
        raise ValueError(
            "unsupported contextual calibration bundle schema")
    report_hash = value.get(
        "report_hash")
    material = dict(value)
    material.pop("report_hash", None)
    if (
            not isinstance(report_hash, str)
            or structural_hash(material)
            != report_hash
    ):
        raise ValueError(
            "contextual calibration bundle hash mismatch")
    if value.get("model_state_hash") != (
            model.state_hash):
        raise ValueError(
            "contextual calibration bundle model mismatch")
    if value.get(
            "authority_approved") is not True:
        raise ValueError(
            "contextual calibration bundle is not approved")
    gates = value.get("gates")
    if (
            not isinstance(gates, dict)
            or not gates
            or not all(
                item is True
                for item in gates.values())
    ):
        raise ValueError(
            "contextual calibration gates are incomplete")
    return value
