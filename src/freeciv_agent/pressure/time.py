"""Structured deadline and completion-time semantics for scalar PF-v2."""

import math
from dataclasses import dataclass
from statistics import NormalDist


@dataclass(frozen=True)
class DeadlineState:
    current_turn: int
    deadline_turn: object
    expected_completion_turn: object
    completion_variance: float = 0.0

    def __post_init__(self):
        if (isinstance(self.current_turn, bool)
                or not isinstance(self.current_turn, int)
                or self.current_turn < 0):
            raise ValueError("current turn must be a non-negative integer")
        if self.deadline_turn is not None:
            if (isinstance(self.deadline_turn, bool)
                    or not isinstance(self.deadline_turn, int)
                    or self.deadline_turn < 0):
                raise ValueError(
                    "deadline turn must be a non-negative integer")
        if self.expected_completion_turn is not None:
            value = float(self.expected_completion_turn)
            if value < 0.0 or not math.isfinite(value):
                raise ValueError(
                    "expected completion turn must be finite "
                    "and non-negative")
        variance = float(self.completion_variance)
        if variance < 0.0 or not math.isfinite(variance):
            raise ValueError(
                "completion variance must be finite and non-negative")

    @property
    def slack(self):
        if (self.deadline_turn is None
                or self.expected_completion_turn is None):
            return None
        return (
            float(self.deadline_turn)
            - float(self.expected_completion_turn))

    def to_dict(self):
        return {
            "completion_variance": float(self.completion_variance),
            "current_turn": int(self.current_turn),
            "deadline_turn": (
                None if self.deadline_turn is None
                else int(self.deadline_turn)),
            "expected_completion_turn": (
                None if self.expected_completion_turn is None
                else float(self.expected_completion_turn)),
            "slack": self.slack,
        }


@dataclass(frozen=True)
class DeadlineFit:
    state: DeadlineState
    probability: float
    deadline_urgency: float
    hard_gate: bool
    gate_reason: object
    method: str

    def __post_init__(self):
        if not isinstance(self.state, DeadlineState):
            raise TypeError("deadline fit requires DeadlineState")
        if not 0.0 <= float(self.probability) <= 1.0:
            raise ValueError("deadline probability must be in [0,1]")
        if (float(self.deadline_urgency) < 0.0
                or not math.isfinite(float(self.deadline_urgency))):
            raise ValueError(
                "deadline urgency must be finite and non-negative")
        if not isinstance(self.hard_gate, bool):
            raise TypeError("deadline hard gate must be boolean")
        if not isinstance(self.method, str) or not self.method:
            raise ValueError("deadline fit method is required")

    def to_dict(self):
        return {
            "deadline_urgency": float(self.deadline_urgency),
            "gate_reason": self.gate_reason,
            "hard_gate": bool(self.hard_gate),
            "method": self.method,
            "probability": float(self.probability),
            "state": self.state.to_dict(),
        }


def evaluate_deadline(
        state, hard_horizon_turn=None, urgency_scale=4.0):
    """Estimate completion probability and separate deadline-only urgency."""
    if not isinstance(state, DeadlineState):
        raise TypeError("deadline evaluation requires DeadlineState")
    urgency_scale = float(urgency_scale)
    if urgency_scale <= 0.0 or not math.isfinite(urgency_scale):
        raise ValueError("deadline urgency scale must be positive")
    if hard_horizon_turn is not None:
        if (isinstance(hard_horizon_turn, bool)
                or not isinstance(hard_horizon_turn, int)
                or hard_horizon_turn < 0):
            raise ValueError(
                "hard horizon must be a non-negative integer")
        if (state.expected_completion_turn is not None
                and state.expected_completion_turn > hard_horizon_turn):
            return DeadlineFit(
                state, 0.0, 1.0, True,
                "known-completion-after-horizon",
                "known-hard-horizon/1.0")
    if state.deadline_turn is None:
        return DeadlineFit(
            state, 1.0, 0.0, False, None,
            "no-deadline/1.0")
    if state.expected_completion_turn is None:
        return DeadlineFit(
            state, 1.0, 0.0, False,
            "completion-time-unknown",
            "uncalibrated-completion/1.0")
    slack = state.slack
    deadline_urgency = 1.0 / (
        1.0 + math.exp(max(
            -60.0, min(60.0, slack / urgency_scale))))
    if state.completion_variance == 0.0:
        probability = 1.0 if slack >= 0.0 else 0.0
        return DeadlineFit(
            state, probability, deadline_urgency,
            False, None,
            "deterministic-completion/1.0")
    z_score = slack / math.sqrt(state.completion_variance)
    probability = NormalDist().cdf(z_score)
    return DeadlineFit(
        state, probability, deadline_urgency,
        False, None,
        "normal-completion/1.0")
