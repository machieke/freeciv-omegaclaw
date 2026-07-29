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


@dataclass(frozen=True)
class EvidenceRiskSummary:
    """Read-only evidence risk available to control scheduling."""

    overlap_weight: float
    conflict_severity: float
    lineage_depth: int
    independent_source_count: int
    quarantine_required: bool

    def __post_init__(self):
        for value, name in (
                (self.overlap_weight, "overlap weight"),
                (self.conflict_severity, "conflict severity")):
            if (not 0.0 <= float(value) <= 1.0
                    or not math.isfinite(float(value))):
                raise ValueError("{} must be in [0,1]".format(name))
        for value, name in (
                (self.lineage_depth, "lineage depth"),
                (self.independent_source_count,
                 "independent source count")):
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0):
                raise ValueError(
                    "{} must be a non-negative integer".format(name))
        if not isinstance(self.quarantine_required, bool):
            raise TypeError(
                "quarantine requirement must be boolean")

    @property
    def duplicate_suppression(self):
        return max(0.0, 1.0 - float(self.overlap_weight))

    def to_dict(self):
        return {
            "conflict_severity": float(self.conflict_severity),
            "duplicate_suppression": float(
                self.duplicate_suppression),
            "independent_source_count": int(
                self.independent_source_count),
            "lineage_depth": int(self.lineage_depth),
            "overlap_weight": float(self.overlap_weight),
            "quarantine_required": bool(
                self.quarantine_required),
        }


@dataclass(frozen=True)
class SelectionExposure:
    region_id: str
    pressure_exposure: float
    observation_count: int
    evidence_update_weight: float
    audit_coverage: float
    context_id: str = "global"

    def __post_init__(self):
        if not self.region_id or not self.context_id:
            raise ValueError(
                "selection exposure requires region and context IDs")
        for value, name in (
                (self.pressure_exposure, "pressure exposure"),
                (self.evidence_update_weight,
                 "evidence update weight"),
                (self.audit_coverage, "audit coverage")):
            if float(value) < 0.0 or not math.isfinite(float(value)):
                raise ValueError(
                    "{} must be finite and non-negative".format(name))
        if (isinstance(self.observation_count, bool)
                or not isinstance(self.observation_count, int)
                or self.observation_count < 0):
            raise ValueError(
                "observation count must be non-negative")
        if float(self.audit_coverage) > 1.0:
            raise ValueError("audit coverage must be in [0,1]")

    def to_dict(self):
        return {
            "audit_coverage": float(self.audit_coverage),
            "context_id": self.context_id,
            "evidence_update_weight": float(
                self.evidence_update_weight),
            "observation_count": int(self.observation_count),
            "pressure_exposure": float(self.pressure_exposure),
            "region_id": self.region_id,
        }


@dataclass(frozen=True)
class SelectionCoverageRecord:
    region_id: str
    context_id: str
    operation_id: str
    selected: bool
    propensity: object
    reason: str
    audit: bool

    def __post_init__(self):
        if not self.region_id or not self.context_id or not self.operation_id:
            raise ValueError(
                "selection coverage record requires stable IDs")
        if not isinstance(self.selected, bool):
            raise TypeError(
                "coverage selection must be boolean")
        if (self.propensity is not None
                and not 0.0 < float(self.propensity) <= 1.0):
            raise ValueError(
                "coverage propensity must be in (0,1]")
        if not self.reason:
            raise ValueError(
                "coverage selection requires a reason")
        if self.propensity is None and not self.reason.startswith(
                "deterministic:"):
            raise ValueError(
                "unknown propensity requires deterministic reason")
        if not isinstance(self.audit, bool):
            raise TypeError("coverage audit flag must be boolean")

    def to_dict(self):
        return {
            "audit": bool(self.audit),
            "context_id": self.context_id,
            "operation_id": self.operation_id,
            "propensity": self.propensity,
            "reason": self.reason,
            "region_id": self.region_id,
            "selected": bool(self.selected),
        }


class SelectionBiasMonitor:
    """Control-only pressure, selection, and belief-update coverage."""

    def __init__(self):
        self._pressure = {}
        self._updates = {}
        self._selections = []

    @staticmethod
    def _key(region_id, context_id):
        region_id = str(region_id)
        context_id = str(context_id)
        if not region_id or not context_id:
            raise ValueError(
                "coverage requires region and context IDs")
        return context_id, region_id

    @property
    def selection_records(self):
        return tuple(self._selections)

    def record_pressure(
            self, region_id, amount, context_id="global"):
        key = self._key(region_id, context_id)
        amount = float(amount)
        if amount < 0.0 or not math.isfinite(amount):
            raise ValueError(
                "pressure exposure must be finite and non-negative")
        self._pressure[key] = self._pressure.get(key, 0.0) + amount

    def record_selection(
            self, region_id, operation_id, selected,
            context_id="global", propensity=None,
            reason="deterministic:ranked-control", audit=False):
        self._key(region_id, context_id)
        record = SelectionCoverageRecord(
            str(region_id), str(context_id), str(operation_id),
            selected, propensity, str(reason), audit)
        self._selections.append(record)
        return record

    def record_evidence_update(
            self, region_id, update_weight,
            context_id="global"):
        key = self._key(region_id, context_id)
        update_weight = float(update_weight)
        if update_weight < 0.0 or not math.isfinite(update_weight):
            raise ValueError(
                "evidence update weight must be non-negative")
        self._updates[key] = (
            self._updates.get(key, 0.0) + update_weight)

    def summaries(self):
        keys = set(self._pressure) | set(self._updates)
        keys.update(
            (row.context_id, row.region_id)
            for row in self._selections)
        result = []
        for context_id, region_id in sorted(keys):
            selected = [
                row for row in self._selections
                if row.context_id == context_id
                and row.region_id == region_id
                and row.selected]
            audits = sum(row.audit for row in selected)
            observations = len(selected)
            result.append(SelectionExposure(
                region_id=region_id,
                pressure_exposure=self._pressure.get(
                    (context_id, region_id), 0.0),
                observation_count=observations,
                evidence_update_weight=self._updates.get(
                    (context_id, region_id), 0.0),
                audit_coverage=(
                    float(audits) / observations
                    if observations else 0.0),
                context_id=context_id))
        return tuple(result)

    def low_pressure_audit_regions(
            self, context_id="global", limit=1):
        if (isinstance(limit, bool)
                or not isinstance(limit, int)
                or limit < 0):
            raise ValueError(
                "audit region limit must be non-negative")
        context_id = str(context_id)
        rows = [
            row for row in self.summaries()
            if row.context_id == context_id]
        return tuple(
            row.region_id
            for row in sorted(rows, key=lambda row: (
                row.audit_coverage > 0.0,
                row.pressure_exposure,
                row.observation_count,
                row.region_id))[:limit])

    def exposure_update_correlation(self, context_id):
        rows = [
            row for row in self.summaries()
            if row.context_id == str(context_id)]
        if len(rows) < 2:
            return None
        exposures = [row.pressure_exposure for row in rows]
        updates = [row.evidence_update_weight for row in rows]
        mean_exposure = sum(exposures) / len(exposures)
        mean_update = sum(updates) / len(updates)
        variance_exposure = sum(
            (value - mean_exposure) ** 2 for value in exposures)
        variance_update = sum(
            (value - mean_update) ** 2 for value in updates)
        if variance_exposure == 0.0 or variance_update == 0.0:
            return 0.0
        covariance = sum(
            (left - mean_exposure) * (right - mean_update)
            for left, right in zip(exposures, updates))
        return covariance / math.sqrt(
            variance_exposure * variance_update)

    @staticmethod
    def inverse_propensity_weight(
            record, assumption=None):
        if not isinstance(record, SelectionCoverageRecord):
            raise TypeError(
                "propensity audit requires selection record")
        if assumption != "missing-at-random-given-context":
            raise ValueError(
                "inverse propensity audit requires declared assumption")
        if record.propensity is None:
            raise ValueError(
                "deterministic selection has no inverse propensity")
        return 1.0 / float(record.propensity)


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

    def risk_summary(
            self, left, right, turn, lineage_depth=0,
            conflict_quarantine_threshold=0.5):
        """Summarize evidence risk without changing token or truth state."""
        if (isinstance(lineage_depth, bool)
                or not isinstance(lineage_depth, int)
                or lineage_depth < 0):
            raise ValueError(
                "lineage depth must be a non-negative integer")
        left = tuple(str(value) for value in left)
        right = tuple(str(value) for value in right)
        selected = self._selected(set(left) | set(right))
        overlap = self.overlap(left, right, turn)
        conflict = self.conflict_severity(left, right, turn)
        threshold = float(conflict_quarantine_threshold)
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                "conflict quarantine threshold must be in [0,1]")
        return EvidenceRiskSummary(
            overlap_weight=overlap,
            conflict_severity=conflict,
            lineage_depth=lineage_depth,
            independent_source_count=len(set(
                token.source for token in selected)),
            quarantine_required=conflict >= threshold)

    @property
    def tokens(self):
        return tuple(self._tokens[key] for key in sorted(self._tokens))
