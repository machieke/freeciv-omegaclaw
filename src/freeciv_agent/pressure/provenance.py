"""Canonical immutable evidence-token accounting for PF-PLN."""

import math
from dataclasses import dataclass

from .model import TruthState


def confidence_to_weight(confidence, k=1.0):
    confidence = float(confidence)
    k = float(k)
    if not 0.0 <= confidence <= 1.0 or k <= 0:
        raise ValueError("confidence must be in [0,1] and k must be positive")
    if confidence == 1.0:
        raise ValueError("confidence 1 requires a logically-fixed flag, not evidence weight")
    return k * confidence / (1.0 - confidence)


def weight_to_confidence(weight, k=1.0):
    weight = float(weight)
    k = float(k)
    if weight < 0 or k <= 0:
        raise ValueError("weight must be nonnegative and k must be positive")
    return weight / (weight + k)


@dataclass(frozen=True)
class ObservationPolicy:
    goal_id: str
    channel: str
    priority: float
    propensity: object = None

    def __post_init__(self):
        if not self.goal_id or self.channel != "observe":
            raise ValueError("observation policy requires a goal and observe channel")
        if float(self.priority) < 0:
            raise ValueError("observation priority must be nonnegative")
        if self.propensity is not None and not 0 < float(self.propensity) <= 1:
            raise ValueError("observation propensity must be in (0,1]")

    def to_dict(self):
        return {
            "channel": self.channel,
            "goal_id": self.goal_id,
            "priority": float(self.priority),
            "propensity": self.propensity,
        }


@dataclass(frozen=True)
class EvidenceToken:
    token_id: str
    strength: float
    base_weight: float
    timestamp: int
    decay_class: str = "default"
    source: str = "unknown"
    observation_policy: object = None

    def __post_init__(self):
        if not self.token_id or not self.decay_class:
            raise ValueError("evidence token ID and decay class are required")
        if not 0 <= float(self.strength) <= 1:
            raise ValueError("token strength must be in [0,1]")
        if float(self.base_weight) < 0 or not math.isfinite(float(self.base_weight)):
            raise ValueError("token weight must be finite and nonnegative")
        if int(self.timestamp) < 0:
            raise ValueError("token timestamp must be nonnegative")
        if (self.observation_policy is not None
                and not isinstance(self.observation_policy, ObservationPolicy)):
            raise TypeError("observation policy must be ObservationPolicy")

    def weight_at(self, turn, decay_rates):
        age = max(0, int(turn) - int(self.timestamp))
        rate = float(dict(decay_rates).get(
            self.decay_class, dict(decay_rates).get("default", 0.0)))
        if rate < 0:
            raise ValueError("decay rates must be nonnegative")
        return float(self.base_weight) * math.exp(-rate * age)

    def to_dict(self):
        return {
            "base_weight": float(self.base_weight),
            "decay_class": self.decay_class,
            "observation_policy": (
                None if self.observation_policy is None
                else self.observation_policy.to_dict()),
            "source": self.source,
            "strength": float(self.strength),
            "timestamp": int(self.timestamp),
            "token_id": self.token_id,
        }


class EvidenceTokenConflict(ValueError):
    pass


class EvidenceLedger(object):
    """Token-set union makes repeated or multipath evidence exactly idempotent."""

    def __init__(self, confidence_k=1.0, decay_rates=(("default", 0.0),)):
        self.confidence_k = float(confidence_k)
        if self.confidence_k <= 0:
            raise ValueError("confidence_k must be positive")
        self.decay_rates = tuple(sorted(decay_rates))
        if any(float(value) < 0 for _, value in self.decay_rates):
            raise ValueError("decay rates must be nonnegative")
        self._tokens = {}

    def register(self, token):
        if not isinstance(token, EvidenceToken):
            raise TypeError("ledger accepts EvidenceToken")
        existing = self._tokens.get(token.token_id)
        if existing is not None and existing != token:
            raise EvidenceTokenConflict(
                "token ID {} reused with different evidence".format(token.token_id))
        self._tokens[token.token_id] = token
        return token

    def token(self, token_id):
        return self._tokens.get(str(token_id))

    def _selected(self, token_ids):
        unique = tuple(sorted(set(str(value) for value in token_ids)))
        missing = [value for value in unique if value not in self._tokens]
        if missing:
            raise KeyError("unknown evidence tokens {}".format(missing))
        return tuple(self._tokens[value] for value in unique)

    def truth(self, token_ids, turn):
        tokens = self._selected(token_ids)
        rows = [(token, token.weight_at(turn, self.decay_rates)) for token in tokens]
        weight = sum(row[1] for row in rows)
        strength = (
            sum(token.strength * current for token, current in rows) / weight
            if weight else 0.0)
        return TruthState(
            strength, weight_to_confidence(weight, self.confidence_k),
            tuple(token.token_id for token, current in rows if current > 0))

    def union(self, *lineages):
        return tuple(sorted(set(
            token_id for lineage in lineages for token_id in lineage)))

    def overlap(self, left, right, turn):
        left_ids = set(str(value) for value in left)
        right_ids = set(str(value) for value in right)
        union = left_ids | right_ids
        self._selected(union)
        if not union:
            return 0.0
        weights = dict(
            (token_id, self._tokens[token_id].weight_at(turn, self.decay_rates))
            for token_id in union)
        denominator = sum(weights.values())
        return (
            sum(weights[token_id] for token_id in left_ids & right_ids) / denominator
            if denominator else 0.0)

    def conflict_severity(self, left, right, turn):
        left_truth = self.truth(left, turn)
        right_truth = self.truth(right, turn)
        return (
            left_truth.confidence * right_truth.confidence
            * abs(left_truth.strength - right_truth.strength)
            * (1.0 - self.overlap(left, right, turn)))

    @property
    def tokens(self):
        return tuple(self._tokens[key] for key in sorted(self._tokens))
