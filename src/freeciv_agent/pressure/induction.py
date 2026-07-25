"""Pressure-gated contextual induction, analogy, and replay validation.

Candidates in this module are immutable, quarantined artifacts.  Mining or
analogy can never mutate a belief or executable rule graph.  A candidate only
becomes available through ``InductionLedger.promoted_rules`` after a disjoint,
out-of-sample replay has accepted it.
"""

import itertools
import json
import math
import os
import threading
from dataclasses import dataclass

from ..events.schema import structural_hash
from .model import CostVector, Operation


SCHEMA_VERSION = "1.0"
PROPOSAL_SOURCES = frozenset(("pattern", "generalization", "analogy"))
VALIDATION_VERDICTS = frozenset(("promoted", "demoted"))


def _unit(value, name):
    value = float(value)
    if not 0.0 <= value <= 1.0 or not math.isfinite(value):
        raise ValueError("{} must be in [0,1]".format(name))
    return value


def _canonical_strings(values, name):
    result = tuple(sorted(str(value) for value in values))
    if any(not value for value in result):
        raise ValueError("{} values must be nonempty".format(name))
    if len(result) != len(set(result)):
        raise ValueError("{} values must be unique".format(name))
    return result


def _canonical_context(values):
    result = tuple(sorted((str(key), str(value)) for key, value in values))
    if any(not key or not value for key, value in result):
        raise ValueError("context keys and values must be nonempty")
    if len(set(key for key, _ in result)) != len(result):
        raise ValueError("context keys must be unique")
    return result


def _context_contains(context, scope):
    values = dict(context)
    return all(values.get(key) == expected for key, expected in scope)


@dataclass(frozen=True)
class InductionEpisode:
    """One causally scoped, replayable experience row."""

    episode_id: str
    context: tuple
    features: tuple
    outcome: bool
    provenance_ids: tuple = ()

    def __post_init__(self):
        if not str(self.episode_id):
            raise ValueError("episode_id is required")
        object.__setattr__(self, "episode_id", str(self.episode_id))
        object.__setattr__(self, "context", _canonical_context(self.context))
        object.__setattr__(
            self, "features", _canonical_strings(self.features, "feature"))
        object.__setattr__(
            self, "provenance_ids",
            _canonical_strings(self.provenance_ids, "provenance"))
        object.__setattr__(self, "outcome", bool(self.outcome))

    def in_scope(self, scope):
        return _context_contains(self.context, scope)

    def to_dict(self):
        return {
            "context": [list(row) for row in self.context],
            "episode_id": self.episode_id,
            "features": list(self.features),
            "outcome": bool(self.outcome),
            "provenance_ids": list(self.provenance_ids),
        }


@dataclass(frozen=True)
class InducedRuleProposal:
    """A quarantined predictive rule plus its complete training provenance."""

    proposal_id: str
    antecedent: tuple
    consequent: str
    context: tuple
    probability: float
    baseline_probability: float
    support: int
    positives: int
    training_episode_ids: tuple
    provenance_ids: tuple
    prediction_residual: float
    compression_gain: float
    expected_generalization: float
    overfit_risk: float
    trigger_pressure: float
    source: str = "pattern"
    source_proposal_ids: tuple = ()
    transfer_uncertainty: float = 0.0

    def __post_init__(self):
        if not str(self.proposal_id) or not str(self.consequent):
            raise ValueError("proposal_id and consequent are required")
        object.__setattr__(self, "proposal_id", str(self.proposal_id))
        object.__setattr__(self, "consequent", str(self.consequent))
        object.__setattr__(
            self, "antecedent",
            _canonical_strings(self.antecedent, "antecedent"))
        if not self.antecedent:
            raise ValueError("an induced rule needs at least one antecedent")
        object.__setattr__(self, "context", _canonical_context(self.context))
        object.__setattr__(
            self, "training_episode_ids",
            _canonical_strings(self.training_episode_ids, "training episode"))
        object.__setattr__(
            self, "provenance_ids",
            _canonical_strings(self.provenance_ids, "provenance"))
        object.__setattr__(
            self, "source_proposal_ids",
            _canonical_strings(self.source_proposal_ids, "source proposal"))
        if self.source not in PROPOSAL_SOURCES:
            raise ValueError("unknown proposal source {}".format(self.source))
        support = int(self.support)
        positives = int(self.positives)
        if support < 1 or positives < 0 or positives > support:
            raise ValueError("invalid rule support")
        if len(self.training_episode_ids) < support:
            raise ValueError("training population cannot be smaller than support")
        object.__setattr__(self, "support", support)
        object.__setattr__(self, "positives", positives)
        for name in (
                "probability", "baseline_probability", "prediction_residual",
                "compression_gain", "expected_generalization", "overfit_risk",
                "transfer_uncertainty"):
            _unit(getattr(self, name), name)
        if float(self.trigger_pressure) < 0 or not math.isfinite(
                float(self.trigger_pressure)):
            raise ValueError("trigger pressure must be finite and nonnegative")

    @property
    def expected_gain(self):
        return (
            self.prediction_residual * self.expected_generalization
            * (1.0 - self.overfit_risk)
            * (1.0 - self.transfer_uncertainty))

    def applies(self, episode):
        return (
            episode.in_scope(self.context)
            and set(self.antecedent).issubset(episode.features))

    def to_dict(self):
        return {
            "antecedent": list(self.antecedent),
            "baseline_probability": float(self.baseline_probability),
            "compression_gain": float(self.compression_gain),
            "consequent": self.consequent,
            "context": [list(row) for row in self.context],
            "expected_gain": float(self.expected_gain),
            "expected_generalization": float(self.expected_generalization),
            "overfit_risk": float(self.overfit_risk),
            "positives": int(self.positives),
            "probability": float(self.probability),
            "proposal_id": self.proposal_id,
            "provenance_ids": list(self.provenance_ids),
            "source": self.source,
            "source_proposal_ids": list(self.source_proposal_ids),
            "support": int(self.support),
            "training_episode_ids": list(self.training_episode_ids),
            "transfer_uncertainty": float(self.transfer_uncertainty),
            "trigger_pressure": float(self.trigger_pressure),
            "prediction_residual": float(self.prediction_residual),
        }

    @classmethod
    def from_dict(cls, value):
        allowed = set(cls.__dataclass_fields__)
        return cls(**dict((key, value[key]) for key in allowed if key in value))


class PatternMiner(object):
    """Exact bounded pattern miner over independent training episodes."""

    def __init__(
            self, minimum_support=4, maximum_antecedents=2,
            minimum_residual=0.05, maximum_candidates=128):
        self.minimum_support = int(minimum_support)
        self.maximum_antecedents = int(maximum_antecedents)
        self.minimum_residual = float(minimum_residual)
        self.maximum_candidates = int(maximum_candidates)
        if (self.minimum_support < 2 or self.maximum_antecedents < 1
                or self.maximum_candidates < 1):
            raise ValueError("invalid pattern miner bounds")
        _unit(self.minimum_residual, "minimum residual")

    @staticmethod
    def _proposal(consequent, context, antecedent, matched, population):
        support = len(matched)
        positives = sum(row.outcome for row in matched)
        population_positives = sum(row.outcome for row in population)
        probability = (positives + 1.0) / (support + 2.0)
        baseline = (population_positives + 1.0) / (len(population) + 2.0)
        residual = abs(probability - baseline)
        compression = max(
            0.0, min(1.0, float(support - len(antecedent)) / support))
        generalization = min(
            1.0, float(support) / max(1.0, len(population) * 0.5))
        overfit = min(1.0, float(len(antecedent)) / support)
        trigger = (
            support * residual * compression * generalization
            * (1.0 - overfit))
        material = {
            "antecedent": list(antecedent),
            "consequent": str(consequent),
            "context": [list(row) for row in context],
            "source": "pattern",
            "training_episode_ids": sorted(row.episode_id for row in population),
        }
        provenance = sorted(set(
            value for row in population for value in row.provenance_ids))
        return InducedRuleProposal(
            proposal_id="induced-" + structural_hash(material)[:24],
            antecedent=antecedent,
            consequent=str(consequent),
            context=context,
            probability=probability,
            baseline_probability=baseline,
            support=support,
            positives=positives,
            training_episode_ids=tuple(
                sorted(row.episode_id for row in population)),
            provenance_ids=tuple(provenance),
            prediction_residual=residual,
            compression_gain=compression,
            expected_generalization=generalization,
            overfit_risk=overfit,
            trigger_pressure=trigger,
        )

    def mine(self, episodes, consequent):
        episodes = tuple(episodes)
        if not episodes or any(
                not isinstance(row, InductionEpisode) for row in episodes):
            raise ValueError("mine requires InductionEpisode values")
        episode_ids = [row.episode_id for row in episodes]
        if len(episode_ids) != len(set(episode_ids)):
            raise ValueError("training episode IDs must be unique")
        seen_provenance = set()
        for row in episodes:
            overlap = seen_provenance & set(row.provenance_ids)
            if overlap:
                raise ValueError(
                    "training provenance is not independent: {}".format(
                        sorted(overlap)))
            seen_provenance.update(row.provenance_ids)
        populations = {}
        for row in episodes:
            populations.setdefault(row.context, []).append(row)
        candidates = []
        for context in sorted(populations):
            population = tuple(populations[context])
            universe = sorted(set(
                feature for row in population for feature in row.features))
            for width in range(1, min(
                    self.maximum_antecedents, len(universe)) + 1):
                for antecedent in itertools.combinations(universe, width):
                    matched = tuple(
                        row for row in population
                        if set(antecedent).issubset(row.features))
                    if len(matched) < self.minimum_support:
                        continue
                    proposal = self._proposal(
                        consequent, context, antecedent, matched, population)
                    if proposal.prediction_residual >= self.minimum_residual:
                        candidates.append(proposal)
        candidates.sort(key=lambda row: (
            -row.trigger_pressure, len(row.antecedent), row.proposal_id))
        return tuple(candidates[:self.maximum_candidates])


class ContextGeneralizer(object):
    """Propose removal of context keys; replay still decides promotion."""

    @staticmethod
    def propose(proposals, drop_keys):
        proposals = tuple(proposals)
        if len(proposals) < 2:
            raise ValueError("generalization needs at least two source proposals")
        if any(not isinstance(row, InducedRuleProposal) for row in proposals):
            raise TypeError("generalization accepts induced rule proposals")
        antecedents = set(row.antecedent for row in proposals)
        consequents = set(row.consequent for row in proposals)
        if len(antecedents) != 1 or len(consequents) != 1:
            raise ValueError("source rules must share antecedent and consequent")
        drop_keys = set(str(value) for value in drop_keys)
        reduced = tuple(
            tuple(row for row in proposal.context if row[0] not in drop_keys)
            for proposal in proposals)
        if len(set(reduced)) != 1:
            raise ValueError("retained generalization context does not match")
        if len(set(row.context for row in proposals)) != len(proposals):
            raise ValueError("generalization needs distinct source contexts")
        episode_ids = sorted(set(
            value for row in proposals for value in row.training_episode_ids))
        if len(episode_ids) != sum(
                len(row.training_episode_ids) for row in proposals):
            raise ValueError("source proposal training populations overlap")
        support = sum(row.support for row in proposals)
        positives = sum(row.positives for row in proposals)
        probability = (positives + 1.0) / (support + 2.0)
        baseline = sum(
            row.baseline_probability * row.support for row in proposals) / support
        residual = abs(probability - baseline)
        compression = min(row.compression_gain for row in proposals)
        generalization = min(1.0, sum(
            row.expected_generalization for row in proposals) / len(proposals))
        overfit = max(row.overfit_risk for row in proposals)
        trigger = (
            support * residual * compression * generalization
            * (1.0 - overfit))
        material = {
            "antecedent": list(proposals[0].antecedent),
            "consequent": proposals[0].consequent,
            "context": [list(row) for row in reduced[0]],
            "source": "generalization",
            "source_proposal_ids": sorted(row.proposal_id for row in proposals),
        }
        return InducedRuleProposal(
            proposal_id="induced-" + structural_hash(material)[:24],
            antecedent=proposals[0].antecedent,
            consequent=proposals[0].consequent,
            context=reduced[0],
            probability=probability,
            baseline_probability=baseline,
            support=support,
            positives=positives,
            training_episode_ids=tuple(episode_ids),
            provenance_ids=tuple(sorted(set(
                value for row in proposals for value in row.provenance_ids))),
            prediction_residual=residual,
            compression_gain=compression,
            expected_generalization=generalization,
            overfit_risk=overfit,
            trigger_pressure=trigger,
            source="generalization",
            source_proposal_ids=tuple(
                sorted(row.proposal_id for row in proposals)),
        )


@dataclass(frozen=True)
class RelationalProfile:
    concept_id: str
    context: tuple
    incoming_relations: tuple
    outgoing_relations: tuple
    provenance_ids: tuple

    def __post_init__(self):
        if not str(self.concept_id):
            raise ValueError("concept_id is required")
        object.__setattr__(self, "concept_id", str(self.concept_id))
        object.__setattr__(self, "context", _canonical_context(self.context))
        for name in ("incoming_relations", "outgoing_relations",
                     "provenance_ids"):
            object.__setattr__(
                self, name, _canonical_strings(getattr(self, name), name))

    def to_dict(self):
        return {
            "concept_id": self.concept_id,
            "context": [list(row) for row in self.context],
            "incoming_relations": list(self.incoming_relations),
            "outgoing_relations": list(self.outgoing_relations),
            "provenance_ids": list(self.provenance_ids),
        }


@dataclass(frozen=True)
class SimilarityLink:
    source_id: str
    target_id: str
    context: tuple
    structural_match: float
    transfer_reliability: float
    provenance_ids: tuple

    def __post_init__(self):
        if not str(self.source_id) or not str(self.target_id):
            raise ValueError("similarity endpoints are required")
        object.__setattr__(self, "context", _canonical_context(self.context))
        object.__setattr__(
            self, "provenance_ids",
            _canonical_strings(self.provenance_ids, "provenance"))
        _unit(self.structural_match, "structural match")
        _unit(self.transfer_reliability, "transfer reliability")

    @property
    def score(self):
        return self.structural_match * self.transfer_reliability

    def to_dict(self):
        return {
            "context": [list(row) for row in self.context],
            "provenance_ids": list(self.provenance_ids),
            "score": float(self.score),
            "source_id": self.source_id,
            "structural_match": float(self.structural_match),
            "target_id": self.target_id,
            "transfer_reliability": float(self.transfer_reliability),
        }


def _jaccard(left, right):
    left = set(left)
    right = set(right)
    union = left | right
    return float(len(left & right)) / len(union) if union else 1.0


def implied_similarity(source, target, transfer_reliability=0.5):
    """Return context-safe neighborhood-kernel similarity, or ``None``."""
    if not isinstance(source, RelationalProfile) or not isinstance(
            target, RelationalProfile):
        raise TypeError("implied similarity needs relational profiles")
    if source.context != target.context:
        return None
    match = 0.5 * (
        _jaccard(source.incoming_relations, target.incoming_relations)
        + _jaccard(source.outgoing_relations, target.outgoing_relations))
    return SimilarityLink(
        source.concept_id, target.concept_id, source.context, match,
        _unit(transfer_reliability, "transfer reliability"),
        tuple(sorted(set(
            source.provenance_ids + target.provenance_ids))))


class StructuralAnalogy(object):
    """Role-profile checked rule transfer which always remains quarantined."""

    def __init__(self, minimum_structural_match=0.70):
        self.minimum_structural_match = _unit(
            minimum_structural_match, "minimum structural match")

    def propose(
            self, source_rule, source_profile, target_profile, mapping,
            transfer_reliability=0.5):
        if not isinstance(source_rule, InducedRuleProposal):
            raise TypeError("analogy source must be an induced rule")
        if source_rule.context != source_profile.context:
            raise ValueError("source rule/profile context mismatch")
        link = implied_similarity(
            source_profile, target_profile, transfer_reliability)
        if link is None or link.structural_match < self.minimum_structural_match:
            return None
        mapping = dict((str(left), str(right)) for left, right in mapping)
        required = set(source_rule.antecedent + (source_rule.consequent,))
        if set(mapping) != required or any(not value for value in mapping.values()):
            raise ValueError("analogy mapping must cover the entire rule exactly")
        antecedent = tuple(mapping[value] for value in source_rule.antecedent)
        consequent = mapping[source_rule.consequent]
        reliability = link.score
        probability = (
            source_rule.baseline_probability
            + (source_rule.probability - source_rule.baseline_probability)
            * reliability)
        material = {
            "antecedent": sorted(antecedent),
            "consequent": consequent,
            "context": [list(row) for row in target_profile.context],
            "source": "analogy",
            "source_proposal_ids": [source_rule.proposal_id],
            "similarity": link.to_dict(),
        }
        return InducedRuleProposal(
            proposal_id="induced-" + structural_hash(material)[:24],
            antecedent=antecedent,
            consequent=consequent,
            context=target_profile.context,
            probability=probability,
            baseline_probability=source_rule.baseline_probability,
            support=source_rule.support,
            positives=source_rule.positives,
            training_episode_ids=source_rule.training_episode_ids,
            provenance_ids=tuple(sorted(set(
                source_rule.provenance_ids + link.provenance_ids))),
            prediction_residual=(
                source_rule.prediction_residual * reliability),
            compression_gain=source_rule.compression_gain,
            expected_generalization=(
                source_rule.expected_generalization * reliability),
            overfit_risk=max(
                source_rule.overfit_risk, 1.0 - link.structural_match),
            trigger_pressure=source_rule.trigger_pressure * reliability,
            source="analogy",
            source_proposal_ids=(source_rule.proposal_id,),
            transfer_uncertainty=1.0 - reliability,
        )


@dataclass(frozen=True)
class ExpansionDecision:
    accepted: bool
    reason: object
    expand_pressure: float
    expected_value: float
    validation_cost: float
    operation: object = None

    def to_dict(self):
        return {
            "accepted": bool(self.accepted),
            "expand_pressure": float(self.expand_pressure),
            "expected_value": float(self.expected_value),
            "operation": (
                None if self.operation is None else self.operation.to_dict()),
            "reason": self.reason,
            "validation_cost": float(self.validation_cost),
        }


class ExpansionGate(object):
    """Materialize validation work only when typed expansion pressure pays."""

    def __init__(
            self, minimum_expand_pressure=0.05,
            minimum_value_cost_ratio=0.01):
        self.minimum_expand_pressure = float(minimum_expand_pressure)
        self.minimum_value_cost_ratio = float(minimum_value_cost_ratio)
        if self.minimum_expand_pressure < 0 or self.minimum_value_cost_ratio < 0:
            raise ValueError("expansion gate thresholds must be nonnegative")

    def decide(
            self, proposal, pressure_result, goal_id, atom_id,
            validation_cost=None):
        if not isinstance(proposal, InducedRuleProposal):
            raise TypeError("expansion gate requires an induced rule proposal")
        validation_cost = validation_cost or CostVector(compute=1.0)
        if not isinstance(validation_cost, CostVector):
            raise TypeError("validation cost must be CostVector")
        pressure = pressure_result.pressure(
            str(goal_id), str(atom_id)).value("expand")
        scalar_cost = sum(validation_cost.to_dict().values())
        expected = pressure * proposal.expected_gain
        if pressure < self.minimum_expand_pressure:
            return ExpansionDecision(
                False, "insufficient_expand_pressure", pressure, expected,
                scalar_cost)
        if expected < scalar_cost * self.minimum_value_cost_ratio:
            return ExpansionDecision(
                False, "validation_cost_exceeds_value", pressure, expected,
                scalar_cost)
        operation = Operation(
            operation_id="validate-" + proposal.proposal_id,
            atom_id=str(atom_id),
            mode="expand",
            cost=validation_cost,
            causal_kind="diagnostic",
            success_probability=(
                (1.0 - proposal.overfit_risk)
                * (1.0 - proposal.transfer_uncertainty)),
            information_gain=proposal.expected_gain,
            coherence_gain=proposal.compression_gain,
            future_option_value=proposal.expected_generalization,
            contradiction_risk=proposal.overfit_risk,
            payload={
                "proposal": proposal.to_dict(),
                "validation_required": True,
            },
        )
        return ExpansionDecision(
            True, None, pressure, expected, scalar_cost, operation)


@dataclass(frozen=True)
class ReplayMetrics:
    samples: int
    activations: int
    baseline_brier: float
    candidate_brier: float
    baseline_log_loss: float
    candidate_log_loss: float
    baseline_calibration_error: float
    candidate_calibration_error: float
    baseline_contradiction_rate: float
    candidate_contradiction_rate: float

    @property
    def brier_improvement(self):
        return self.baseline_brier - self.candidate_brier

    @property
    def calibration_improvement(self):
        return (
            self.baseline_calibration_error
            - self.candidate_calibration_error)

    def to_dict(self):
        return {
            "activations": int(self.activations),
            "baseline_brier": float(self.baseline_brier),
            "baseline_calibration_error": float(
                self.baseline_calibration_error),
            "baseline_contradiction_rate": float(
                self.baseline_contradiction_rate),
            "baseline_log_loss": float(self.baseline_log_loss),
            "brier_improvement": float(self.brier_improvement),
            "calibration_improvement": float(self.calibration_improvement),
            "candidate_brier": float(self.candidate_brier),
            "candidate_calibration_error": float(
                self.candidate_calibration_error),
            "candidate_contradiction_rate": float(
                self.candidate_contradiction_rate),
            "candidate_log_loss": float(self.candidate_log_loss),
            "samples": int(self.samples),
        }


@dataclass(frozen=True)
class ReplayValidation:
    validation_id: str
    proposal_id: str
    verdict: str
    reason: str
    validation_episode_ids: tuple
    metrics: ReplayMetrics
    configuration: tuple

    def __post_init__(self):
        if self.verdict not in VALIDATION_VERDICTS:
            raise ValueError("unknown replay verdict")
        object.__setattr__(
            self, "validation_episode_ids",
            _canonical_strings(
                self.validation_episode_ids, "validation episode"))
        object.__setattr__(
            self, "configuration",
            tuple(sorted((str(key), value) for key, value in self.configuration)))

    def to_dict(self):
        return {
            "configuration": dict(self.configuration),
            "metrics": self.metrics.to_dict(),
            "proposal_id": self.proposal_id,
            "reason": self.reason,
            "validation_episode_ids": list(self.validation_episode_ids),
            "validation_id": self.validation_id,
            "verdict": self.verdict,
        }


class ReplayValidator(object):
    """Deterministic out-of-sample calibration and contradiction gate."""

    def __init__(
            self, minimum_samples=8, minimum_activations=4,
            minimum_brier_improvement=0.001,
            minimum_calibration_improvement=0.0,
            contradiction_tolerance=0.0, contradiction_threshold=0.70):
        self.minimum_samples = int(minimum_samples)
        self.minimum_activations = int(minimum_activations)
        self.minimum_brier_improvement = float(minimum_brier_improvement)
        self.minimum_calibration_improvement = float(
            minimum_calibration_improvement)
        self.contradiction_tolerance = float(contradiction_tolerance)
        self.contradiction_threshold = _unit(
            contradiction_threshold, "contradiction threshold")
        if (self.minimum_samples < 1 or self.minimum_activations < 1
                or self.minimum_brier_improvement < 0
                or self.minimum_calibration_improvement < 0
                or self.contradiction_tolerance < 0):
            raise ValueError("invalid replay validation bounds")

    @staticmethod
    def _log_loss(probability, outcome):
        bounded = min(1.0 - 1e-12, max(1e-12, probability))
        return -math.log(bounded if outcome else 1.0 - bounded)

    def _contradiction(self, probability, outcome):
        return int(
            (probability >= self.contradiction_threshold and not outcome)
            or (probability <= 1.0 - self.contradiction_threshold and outcome))

    def validate(self, proposal, episodes):
        if not isinstance(proposal, InducedRuleProposal):
            raise TypeError("replay validation requires an induced rule")
        supplied = tuple(episodes)
        if any(not isinstance(row, InductionEpisode) for row in supplied):
            raise TypeError("replay requires InductionEpisode values")
        episodes = tuple(
            row for row in supplied if row.in_scope(proposal.context))
        episode_ids = [row.episode_id for row in episodes]
        if len(episode_ids) != len(set(episode_ids)):
            raise ValueError("validation episode IDs must be unique")
        overlap = set(episode_ids) & set(proposal.training_episode_ids)
        if overlap:
            raise ValueError(
                "training/validation episode overlap: {}".format(
                    sorted(overlap)))
        seen_provenance = set(proposal.provenance_ids)
        for row in episodes:
            overlap = seen_provenance & set(row.provenance_ids)
            if overlap:
                raise ValueError(
                    "training/validation provenance overlap: {}".format(
                        sorted(overlap)))
            seen_provenance.update(row.provenance_ids)
        baseline_predictions = []
        candidate_predictions = []
        outcomes = []
        active_outcomes = []
        activations = 0
        for row in sorted(episodes, key=lambda value: value.episode_id):
            active = proposal.applies(row)
            activations += int(active)
            if active:
                active_outcomes.append(row.outcome)
            baseline_predictions.append(proposal.baseline_probability)
            candidate_predictions.append(
                proposal.probability if active
                else proposal.baseline_probability)
            outcomes.append(row.outcome)
        samples = len(outcomes)
        denominator = float(samples or 1)
        baseline_brier = sum(
            (value - int(outcome)) ** 2
            for value, outcome in zip(
                baseline_predictions, outcomes)) / denominator
        candidate_brier = sum(
            (value - int(outcome)) ** 2
            for value, outcome in zip(
                candidate_predictions, outcomes)) / denominator
        baseline_log = sum(
            self._log_loss(value, outcome)
            for value, outcome in zip(
                baseline_predictions, outcomes)) / denominator
        candidate_log = sum(
            self._log_loss(value, outcome)
            for value, outcome in zip(
                candidate_predictions, outcomes)) / denominator
        active_denominator = float(activations or 1)
        active_empirical = float(sum(active_outcomes)) / active_denominator
        baseline_calibration = abs(
            proposal.baseline_probability - active_empirical)
        candidate_calibration = abs(
            proposal.probability - active_empirical)
        baseline_contradiction = sum(
            self._contradiction(value, outcome)
            for value, outcome in zip(
                baseline_predictions, outcomes)) / denominator
        candidate_contradiction = sum(
            self._contradiction(value, outcome)
            for value, outcome in zip(
                candidate_predictions, outcomes)) / denominator
        metrics = ReplayMetrics(
            samples, activations, baseline_brier, candidate_brier,
            baseline_log, candidate_log, baseline_calibration,
            candidate_calibration, baseline_contradiction,
            candidate_contradiction)
        if samples < self.minimum_samples:
            verdict, reason = "demoted", "insufficient_validation_samples"
        elif activations < self.minimum_activations:
            verdict, reason = "demoted", "insufficient_rule_activations"
        elif metrics.brier_improvement < self.minimum_brier_improvement:
            verdict, reason = "demoted", "no_out_of_sample_improvement"
        elif metrics.calibration_improvement <= (
                self.minimum_calibration_improvement):
            verdict, reason = "demoted", "no_out_of_sample_calibration_improvement"
        elif candidate_contradiction > (
                baseline_contradiction + self.contradiction_tolerance):
            verdict, reason = "demoted", "contradiction_rate_increased"
        else:
            verdict, reason = "promoted", "replay_gate_passed"
        configuration = (
            ("contradiction_threshold", self.contradiction_threshold),
            ("contradiction_tolerance", self.contradiction_tolerance),
            ("minimum_activations", self.minimum_activations),
            ("minimum_brier_improvement", self.minimum_brier_improvement),
            ("minimum_calibration_improvement",
             self.minimum_calibration_improvement),
            ("minimum_samples", self.minimum_samples),
        )
        material = {
            "configuration": dict(configuration),
            "episode_ids": sorted(episode_ids),
            "metrics": metrics.to_dict(),
            "proposal_id": proposal.proposal_id,
            "verdict": verdict,
        }
        return ReplayValidation(
            "validation-" + structural_hash(material)[:24],
            proposal.proposal_id, verdict, reason, tuple(sorted(episode_ids)),
            metrics, configuration)


class InductionLedger(object):
    """Atomic, idempotent proposal lifecycle with no unvalidated escape."""

    def __init__(self, path=None, identity="in-memory"):
        if not str(identity):
            raise ValueError("induction ledger identity is required")
        self.path = None if path is None else os.path.abspath(path)
        self.identity = str(identity)
        self._lock = threading.RLock()
        self._proposals = {}
        self._validations = {}
        if self.path is not None and os.path.isfile(self.path):
            self._load()

    def _material(self):
        return {
            "identity": self.identity,
            "proposals": dict(
                (key, self._proposals[key]) for key in sorted(self._proposals)),
            "schema_version": SCHEMA_VERSION,
            "validations": dict(
                (key, self._validations[key])
                for key in sorted(self._validations)),
        }

    @property
    def state_hash(self):
        with self._lock:
            return structural_hash(self._material())

    def snapshot(self):
        with self._lock:
            value = self._material()
            value["state_hash"] = structural_hash(value)
            return value

    def _load(self):
        with open(self.path, encoding="utf-8") as stream:
            value = json.load(stream)
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported induction ledger schema")
        if value.get("identity") != self.identity:
            raise ValueError("induction ledger identity mismatch")
        self._proposals = dict(value.get("proposals", {}))
        self._validations = dict(value.get("validations", {}))
        for proposal_id, row in self._proposals.items():
            proposal = InducedRuleProposal.from_dict(row["proposal"])
            if proposal.proposal_id != proposal_id:
                raise ValueError("persisted proposal identity mismatch")
            if row.get("status") not in (
                    "quarantined", "promoted", "demoted"):
                raise ValueError("invalid persisted proposal status")
        for validation_id, row in self._validations.items():
            if row.get("validation_id") != validation_id:
                raise ValueError("persisted validation identity mismatch")
            proposal_id = row.get("proposal_id")
            if proposal_id not in self._proposals:
                raise ValueError("persisted validation has no proposal")
            if validation_id not in self._proposals[
                    proposal_id].get("validation_ids", ()):
                raise ValueError("persisted validation is not linked")
        linked = [
            validation_id
            for row in self._proposals.values()
            for validation_id in row.get("validation_ids", ())]
        if len(linked) != len(set(linked)) or set(linked) != set(
                self._validations):
            raise ValueError("persisted validation links are inconsistent")
        for row in self._proposals.values():
            verdicts = [
                self._validations[value].get("verdict")
                for value in row.get("validation_ids", ())]
            if row["status"] == "quarantined" and verdicts:
                raise ValueError("quarantined proposal has a validation")
            if row["status"] != "quarantined" and row["status"] not in verdicts:
                raise ValueError("proposal status has no supporting validation")
        if value.get("state_hash") != self.state_hash:
            raise ValueError("induction ledger state hash mismatch")

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

    def propose(self, proposal):
        if not isinstance(proposal, InducedRuleProposal):
            raise TypeError("ledger accepts InducedRuleProposal")
        with self._lock:
            value = {
                "proposal": proposal.to_dict(),
                "status": "quarantined",
                "validation_ids": [],
            }
            existing = self._proposals.get(proposal.proposal_id)
            if existing is not None:
                if existing["proposal"] != value["proposal"]:
                    raise ValueError("proposal ID collision")
                return False
            self._proposals[proposal.proposal_id] = value
            self.save()
            return True

    def record_validation(self, validation):
        if not isinstance(validation, ReplayValidation):
            raise TypeError("ledger accepts ReplayValidation")
        with self._lock:
            proposal = self._proposals.get(validation.proposal_id)
            if proposal is None:
                raise KeyError("validation proposal is not quarantined")
            value = validation.to_dict()
            existing = self._validations.get(validation.validation_id)
            if existing is not None:
                if existing != value:
                    raise ValueError("validation ID collision")
                return False
            if proposal["status"] == "promoted" and validation.verdict != "promoted":
                raise ValueError("promoted rule cannot be silently demoted")
            self._validations[validation.validation_id] = value
            proposal["validation_ids"].append(validation.validation_id)
            proposal["validation_ids"].sort()
            proposal["status"] = validation.verdict
            self.save()
            return True

    def status(self, proposal_id):
        with self._lock:
            row = self._proposals.get(str(proposal_id))
            return None if row is None else row["status"]

    def promoted_rules(self):
        with self._lock:
            return tuple(
                InducedRuleProposal.from_dict(row["proposal"])
                for _, row in sorted(self._proposals.items())
                if row["status"] == "promoted")

    def emit_proposal(
            self, writer, turn, proposal, expansion_decision, caused_by=()):
        if not expansion_decision.accepted:
            raise ValueError("rejected expansion cannot emit a proposal")
        self.propose(proposal)
        return writer.emit("rule_proposed", turn, {
            "expansion": expansion_decision.to_dict(),
            "ledger_hash": self.state_hash,
            "lifecycle": "quarantined",
            "proposal": proposal.to_dict(),
            "proposal_id": proposal.proposal_id,
        }, caused_by=caused_by)

    def emit_validation(
            self, writer, turn, validation, caused_by=()):
        self.record_validation(validation)
        return writer.emit("rule_validated", turn, {
            "ledger_hash": self.state_hash,
            "metrics": validation.metrics.to_dict(),
            "proposal_id": validation.proposal_id,
            "reason": validation.reason,
            "validation_id": validation.validation_id,
            "verdict": validation.verdict,
        }, caused_by=caused_by)
