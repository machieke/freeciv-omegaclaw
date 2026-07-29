"""Goal-specific distributional risk semantics for scalar PF-v2."""

import math
from dataclasses import dataclass
from statistics import NormalDist


def _finite_nonnegative(value, name):
    value = float(value)
    if value < 0.0 or not math.isfinite(value):
        raise ValueError("{} must be finite and non-negative".format(name))
    return value


def _probability(value, name, open_zero=False):
    value = float(value)
    if not math.isfinite(value) or value > 1.0:
        raise ValueError("{} must be a probability".format(name))
    if (value <= 0.0 if open_zero else value < 0.0):
        raise ValueError("{} must be a probability".format(name))
    return value


@dataclass(frozen=True)
class RiskProfile:
    aversion: float = 0.0
    tail_alpha: float = 0.10
    max_expected_loss: object = None
    max_tail_loss: object = None
    hard_gate: bool = False
    hysteresis_enter: object = None
    hysteresis_exit: object = None

    def __post_init__(self):
        _finite_nonnegative(self.aversion, "risk aversion")
        _probability(self.tail_alpha, "tail alpha", open_zero=True)
        for name in (
                "max_expected_loss", "max_tail_loss",
                "hysteresis_enter", "hysteresis_exit"):
            value = getattr(self, name)
            if value is not None:
                _finite_nonnegative(value, name.replace("_", " "))
        if not isinstance(self.hard_gate, bool):
            raise TypeError("risk hard_gate must be boolean")
        if ((self.hysteresis_enter is None)
                != (self.hysteresis_exit is None)):
            raise ValueError(
                "risk hysteresis requires enter and exit thresholds")
        if (self.hysteresis_enter is not None
                and self.hysteresis_enter > self.hysteresis_exit):
            raise ValueError(
                "risk hysteresis enter must not exceed exit")

    def to_dict(self):
        return {
            "aversion": float(self.aversion),
            "hard_gate": bool(self.hard_gate),
            "hysteresis_enter": (
                None if self.hysteresis_enter is None
                else float(self.hysteresis_enter)),
            "hysteresis_exit": (
                None if self.hysteresis_exit is None
                else float(self.hysteresis_exit)),
            "max_expected_loss": (
                None if self.max_expected_loss is None
                else float(self.max_expected_loss)),
            "max_tail_loss": (
                None if self.max_tail_loss is None
                else float(self.max_tail_loss)),
            "tail_alpha": float(self.tail_alpha),
        }


@dataclass(frozen=True)
class RiskEstimate:
    expected_loss: float
    variance: float
    upper_quantile: float
    cvar: float
    confidence: float
    provenance: tuple = ()

    def __post_init__(self):
        _finite_nonnegative(self.expected_loss, "expected loss")
        _finite_nonnegative(self.variance, "loss variance")
        _finite_nonnegative(self.upper_quantile, "upper loss quantile")
        _finite_nonnegative(self.cvar, "conditional value at risk")
        _probability(self.confidence, "risk confidence")
        if self.upper_quantile < self.expected_loss:
            raise ValueError(
                "upper loss quantile cannot be below expected loss")
        if self.cvar < self.upper_quantile:
            raise ValueError(
                "conditional value at risk cannot be below upper quantile")
        if (any(not isinstance(value, str) or not value
                for value in self.provenance)
                or len(set(self.provenance)) != len(self.provenance)):
            raise ValueError(
                "risk provenance IDs must be unique non-empty strings")

    @property
    def tail_loss(self):
        return float(self.cvar)

    def to_dict(self):
        return {
            "confidence": float(self.confidence),
            "cvar": float(self.cvar),
            "expected_loss": float(self.expected_loss),
            "provenance": list(self.provenance),
            "upper_quantile": float(self.upper_quantile),
            "variance": float(self.variance),
        }


def estimate_uncertain_loss(
        expected_loss, outcome_variance=0.0, confidence=1.0,
        tail_alpha=0.10, provenance=()):
    """Build a conservative normal-moment estimate.

    Lower confidence widens the distribution; it never changes expected loss
    and therefore never becomes a harm probability.
    """
    expected = _finite_nonnegative(expected_loss, "expected loss")
    outcome_variance = _finite_nonnegative(
        outcome_variance, "outcome variance")
    confidence = _probability(confidence, "risk confidence")
    tail_alpha = _probability(
        tail_alpha, "tail alpha", open_zero=True)
    uncertainty_scale = max(1.0, abs(expected)) ** 2
    variance = (
        outcome_variance
        + (1.0 - confidence) * uncertainty_scale)
    standard_deviation = math.sqrt(variance)
    z_score = NormalDist().inv_cdf(1.0 - tail_alpha)
    density = math.exp(-0.5 * z_score * z_score) / math.sqrt(
        2.0 * math.pi)
    upper = max(expected, expected + z_score * standard_deviation)
    cvar = max(
        upper,
        expected + standard_deviation * density / tail_alpha)
    return RiskEstimate(
        expected, variance, upper, cvar, confidence,
        tuple(provenance))


@dataclass(frozen=True)
class RiskTrace:
    goal_id: str
    operation_id: str
    expected_loss: float
    tail_loss: float
    confidence: float
    aversion: float
    penalty: float
    hard_gate: bool
    gate_reason: object
    provenance: tuple

    def to_dict(self):
        return {
            "aversion": float(self.aversion),
            "confidence": float(self.confidence),
            "expected_loss": float(self.expected_loss),
            "gate_reason": self.gate_reason,
            "goal_id": self.goal_id,
            "hard_gate": bool(self.hard_gate),
            "operation_id": self.operation_id,
            "penalty": float(self.penalty),
            "provenance": list(self.provenance),
            "tail_loss": float(self.tail_loss),
        }


class RiskHysteresis:
    """Persistent-plan adoption/retention state under risk thresholds."""

    def __init__(self):
        self._active = set()

    def reset(self):
        self._active.clear()

    def evaluate(self, plan_id, tail_loss, profile):
        if not isinstance(plan_id, str) or not plan_id:
            raise ValueError("risk hysteresis requires a plan ID")
        if not isinstance(profile, RiskProfile):
            raise TypeError("risk hysteresis requires RiskProfile")
        tail_loss = _finite_nonnegative(tail_loss, "tail loss")
        if profile.hysteresis_enter is None:
            accepted = True
        elif plan_id in self._active:
            accepted = tail_loss <= profile.hysteresis_exit
        else:
            accepted = tail_loss <= profile.hysteresis_enter
        if accepted:
            self._active.add(plan_id)
        else:
            self._active.discard(plan_id)
        return accepted

    def active(self, plan_id):
        return str(plan_id) in self._active
