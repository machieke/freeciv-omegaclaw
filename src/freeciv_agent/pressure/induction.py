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
from .model import CostVector, Operation, PressureConfig
from .scheduler import OperationScore


SCHEMA_VERSION = "1.0"
PROMOTION_APPROVAL_SCHEMA_VERSION = "1.0"
PROMOTION_GATE_ID = "fdas-heldout-induction-promotion/1.0"
PROMOTED_RULE_CONSOLIDATION_SCHEMA_VERSION = "1.0"
PROMOTED_RULE_CONSOLIDATION_ALGORITHM_ID = (
    "fdas-promoted-rule-structural-subsumption/1.0")
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
class InductionFeatureQuery:
    """Outcome-free contextual features for prediction-time readout."""

    query_id: str
    context: tuple
    features: tuple
    provenance_ids: tuple = ()

    def __post_init__(self):
        if not isinstance(self.query_id, str) or not self.query_id:
            raise ValueError("induction feature query requires an ID")
        object.__setattr__(self, "context", _canonical_context(self.context))
        object.__setattr__(
            self, "features", _canonical_strings(self.features, "feature"))
        object.__setattr__(
            self, "provenance_ids",
            _canonical_strings(self.provenance_ids, "provenance"))

    @property
    def episode_id(self):
        """Compatibility identity for outcome-blind readout results."""
        return self.query_id

    def in_scope(self, scope):
        return _context_contains(self.context, scope)

    def to_dict(self):
        return {
            "context": [list(row) for row in self.context],
            "features": list(self.features),
            "provenance_ids": list(self.provenance_ids),
            "query_id": self.query_id,
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
            population_positives = sum(row.outcome for row in population)
            if population_positives in (0, len(population)):
                # Support-dependent smoothing alone can otherwise create an
                # apparent subgroup residual in a single-class population.
                # There is no observed contrast from which to induce a rule.
                continue
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

    @classmethod
    def from_dict(cls, value):
        return cls(**dict(
            (key, value[key]) for key in cls.__dataclass_fields__))


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

    @classmethod
    def from_dict(cls, value):
        return cls(
            value["validation_id"], value["proposal_id"], value["verdict"],
            value["reason"], tuple(value["validation_episode_ids"]),
            ReplayMetrics.from_dict(value["metrics"]),
            tuple(sorted(value["configuration"].items())))


@dataclass(frozen=True)
class InductionPromotionApproval:
    """Versioned proof that one disjoint held-out promotion was approved.

    Promotion changes only the induction ledger lifecycle.  It deliberately
    grants neither policy authority nor induced-rule readout authority.
    """

    schema_version: str
    approval_id: str
    gate_id: str
    proposal_id: str
    validation_id: str
    training_episode_ids: tuple
    validation_episode_ids: tuple
    training_artifact_hash: str
    holdout_artifact_hash: str
    validation_result_hash: str

    def __post_init__(self):
        if self.schema_version != PROMOTION_APPROVAL_SCHEMA_VERSION:
            raise ValueError("unsupported induction approval schema")
        for value, name in (
                (self.approval_id, "approval ID"),
                (self.gate_id, "gate ID"),
                (self.proposal_id, "proposal ID"),
                (self.validation_id, "validation ID")):
            if not isinstance(value, str) or not value:
                raise ValueError("induction {} is required".format(name))
        object.__setattr__(
            self, "training_episode_ids", _canonical_strings(
                self.training_episode_ids, "approval training episode"))
        object.__setattr__(
            self, "validation_episode_ids", _canonical_strings(
                self.validation_episode_ids, "approval validation episode"))
        if set(self.training_episode_ids) & set(self.validation_episode_ids):
            raise ValueError("approval training/validation episodes overlap")
        for value, name in (
                (self.training_artifact_hash, "training artifact hash"),
                (self.holdout_artifact_hash, "holdout artifact hash"),
                (self.validation_result_hash, "validation result hash")):
            if (not isinstance(value, str) or len(value) != 64
                    or any(character not in "0123456789abcdef"
                           for character in value)):
                raise ValueError("induction {} is invalid".format(name))
        if self.training_artifact_hash == self.holdout_artifact_hash:
            raise ValueError("training and holdout artifacts must be disjoint")
        expected = "approval-" + structural_hash(self._material())[:24]
        if self.approval_id != expected:
            raise ValueError("induction approval identity mismatch")

    def _material(self):
        return {
            "gate_id": self.gate_id,
            "holdout_artifact_hash": self.holdout_artifact_hash,
            "proposal_id": self.proposal_id,
            "schema_version": self.schema_version,
            "training_artifact_hash": self.training_artifact_hash,
            "training_episode_ids": list(self.training_episode_ids),
            "validation_episode_ids": list(self.validation_episode_ids),
            "validation_id": self.validation_id,
            "validation_result_hash": self.validation_result_hash,
        }

    def to_dict(self):
        value = self._material()
        value.update({
            "approval_id": self.approval_id,
            "policy_authority": False,
            "readout_authority": False,
        })
        return value

    @classmethod
    def issue(
            cls, proposal, validation, training_artifact_hash,
            holdout_artifact_hash, gate_id=PROMOTION_GATE_ID):
        if not isinstance(proposal, InducedRuleProposal):
            raise TypeError("induction approval requires a proposal")
        if not isinstance(validation, ReplayValidation):
            raise TypeError("induction approval requires replay validation")
        if validation.verdict != "promoted":
            raise ValueError("only a promoted validation can be approved")
        if validation.proposal_id != proposal.proposal_id:
            raise ValueError("approval proposal/validation mismatch")
        material = {
            "gate_id": str(gate_id),
            "holdout_artifact_hash": str(holdout_artifact_hash),
            "proposal_id": proposal.proposal_id,
            "schema_version": PROMOTION_APPROVAL_SCHEMA_VERSION,
            "training_artifact_hash": str(training_artifact_hash),
            "training_episode_ids": list(proposal.training_episode_ids),
            "validation_episode_ids": list(
                validation.validation_episode_ids),
            "validation_id": validation.validation_id,
            "validation_result_hash": structural_hash(validation.to_dict()),
        }
        return cls(
            PROMOTION_APPROVAL_SCHEMA_VERSION,
            "approval-" + structural_hash(material)[:24],
            str(gate_id), proposal.proposal_id, validation.validation_id,
            proposal.training_episode_ids, validation.validation_episode_ids,
            str(training_artifact_hash), str(holdout_artifact_hash),
            structural_hash(validation.to_dict()))

    @classmethod
    def from_dict(cls, value):
        if (value.get("policy_authority") is not False
                or value.get("readout_authority") is not False):
            raise ValueError("induction approval cannot grant authority")
        return cls(
            value["schema_version"], value["approval_id"], value["gate_id"],
            value["proposal_id"], value["validation_id"],
            tuple(value["training_episode_ids"]),
            tuple(value["validation_episode_ids"]),
            value["training_artifact_hash"], value["holdout_artifact_hash"],
            value["validation_result_hash"])

    def validate(self, proposal, validation):
        if not isinstance(proposal, InducedRuleProposal):
            raise TypeError("approval validation requires a proposal")
        if not isinstance(validation, ReplayValidation):
            raise TypeError("approval validation requires replay validation")
        if validation.verdict != "promoted":
            raise ValueError("approval cannot accompany a demotion")
        checks = (
            self.proposal_id == proposal.proposal_id,
            self.validation_id == validation.validation_id,
            self.training_episode_ids == proposal.training_episode_ids,
            self.validation_episode_ids == validation.validation_episode_ids,
            self.validation_result_hash == structural_hash(
                validation.to_dict()),
        )
        if not all(checks):
            raise ValueError("induction approval does not match validation")
        return True


@dataclass(frozen=True)
class PromotedRuleSuppression:
    """One deterministic, training-only structural redundancy witness."""

    proposal_id: str
    retained_proposal_id: str
    retained_antecedent: tuple
    removed_antecedents: tuple
    reason: str = "strict_antecedent_subsumption_same_prediction"

    def __post_init__(self):
        for value, name in (
                (self.proposal_id, "suppressed proposal ID"),
                (self.retained_proposal_id, "retained proposal ID")):
            if not isinstance(value, str) or not value:
                raise ValueError("{} is required".format(name))
        if self.proposal_id == self.retained_proposal_id:
            raise ValueError("a proposal cannot suppress itself")
        object.__setattr__(
            self, "retained_antecedent",
            _canonical_strings(self.retained_antecedent, "retained antecedent"))
        object.__setattr__(
            self, "removed_antecedents",
            _canonical_strings(self.removed_antecedents, "removed antecedent"))
        if not self.retained_antecedent or not self.removed_antecedents:
            raise ValueError("structural suppression must remove an antecedent")
        if self.reason != "strict_antecedent_subsumption_same_prediction":
            raise ValueError("unknown promoted-rule suppression reason")

    def to_dict(self):
        return {
            "proposal_id": self.proposal_id,
            "reason": self.reason,
            "removed_antecedents": list(self.removed_antecedents),
            "retained_antecedent": list(self.retained_antecedent),
            "retained_proposal_id": self.retained_proposal_id,
        }

    @classmethod
    def from_dict(cls, value):
        return cls(
            value["proposal_id"],
            value["retained_proposal_id"],
            tuple(value["retained_antecedent"]),
            tuple(value["removed_antecedents"]),
            value["reason"])


@dataclass(frozen=True)
class PromotedRuleConsolidation:
    """A non-authorizing minimal basis for approved promoted rules."""

    input_rule_ids: tuple
    retained_rule_ids: tuple
    suppressions: tuple

    def __post_init__(self):
        object.__setattr__(
            self, "input_rule_ids",
            _canonical_strings(self.input_rule_ids, "input rule"))
        object.__setattr__(
            self, "retained_rule_ids",
            _canonical_strings(self.retained_rule_ids, "retained rule"))
        suppressions = tuple(self.suppressions)
        if any(not isinstance(row, PromotedRuleSuppression)
               for row in suppressions):
            raise TypeError(
                "consolidation suppressions require structural witnesses")
        suppressions = tuple(sorted(
            suppressions, key=lambda row: row.proposal_id))
        object.__setattr__(self, "suppressions", suppressions)
        suppressed_ids = tuple(row.proposal_id for row in suppressions)
        if len(suppressed_ids) != len(set(suppressed_ids)):
            raise ValueError("suppressed proposal IDs must be unique")
        if set(self.retained_rule_ids) & set(suppressed_ids):
            raise ValueError("retained and suppressed rules overlap")
        if set(self.input_rule_ids) != (
                set(self.retained_rule_ids) | set(suppressed_ids)):
            raise ValueError(
                "retained and suppressed rules must partition the input")
        if any(row.retained_proposal_id not in self.retained_rule_ids
               for row in suppressions):
            raise ValueError("suppression must point to a retained rule")

    def _material(self):
        return {
            "algorithm_id": PROMOTED_RULE_CONSOLIDATION_ALGORITHM_ID,
            "input_rule_ids": list(self.input_rule_ids),
            "retained_rule_ids": list(self.retained_rule_ids),
            "schema_version": PROMOTED_RULE_CONSOLIDATION_SCHEMA_VERSION,
            "suppressions": [row.to_dict() for row in self.suppressions],
        }

    @property
    def consolidation_id(self):
        return "consolidation-" + structural_hash(self._material())[:24]

    @property
    def result_hash(self):
        return structural_hash(self._value_without_hash())

    def _value_without_hash(self):
        value = self._material()
        value.update({
            "consolidation_id": self.consolidation_id,
            "policy_authority": False,
            "readout_authority": False,
            "truth_mutated": False,
        })
        return value

    def to_dict(self):
        value = self._value_without_hash()
        value["result_hash"] = structural_hash(value)
        return value

    @classmethod
    def from_dict(cls, value):
        if (value.get("policy_authority") is not False
                or value.get("readout_authority") is not False
                or value.get("truth_mutated") is not False):
            raise ValueError("promoted-rule consolidation cannot grant authority")
        if value.get("schema_version") != (
                PROMOTED_RULE_CONSOLIDATION_SCHEMA_VERSION):
            raise ValueError("unsupported promoted-rule consolidation schema")
        if value.get("algorithm_id") != (
                PROMOTED_RULE_CONSOLIDATION_ALGORITHM_ID):
            raise ValueError("unsupported promoted-rule consolidation algorithm")
        result = cls(
            tuple(value["input_rule_ids"]),
            tuple(value["retained_rule_ids"]),
            tuple(PromotedRuleSuppression.from_dict(row)
                  for row in value["suppressions"]))
        expected = result.to_dict()
        if (value.get("consolidation_id") != expected["consolidation_id"]
                or value.get("result_hash") != expected["result_hash"]):
            raise ValueError("promoted-rule consolidation identity mismatch")
        return result


class PromotedRuleConsolidator(object):
    """Remove only provably redundant approved rule conjunctions.

    The algorithm never examines held-out outcomes or validation metrics.  A
    more-specific rule is redundant only when an already retained strict
    antecedent subset was trained on the same population and has the same
    calibrated prediction semantics.  Matching approvals are mandatory, but
    promotion grants no readout or policy authority.
    """

    @staticmethod
    def _prediction_signature(proposal):
        return (
            proposal.consequent,
            proposal.context,
            float(proposal.probability),
            float(proposal.baseline_probability),
            int(proposal.support),
            int(proposal.positives),
            proposal.training_episode_ids,
            proposal.provenance_ids,
            proposal.source,
            proposal.source_proposal_ids,
            float(proposal.prediction_residual),
            float(proposal.expected_generalization),
            float(proposal.transfer_uncertainty),
        )

    @staticmethod
    def _indexed(values, expected_type, label, identifier):
        values = tuple(values)
        if any(not isinstance(value, expected_type) for value in values):
            raise TypeError("{} have wrong type".format(label))
        result = {}
        for value in values:
            key = str(getattr(value, identifier))
            if key in result:
                raise ValueError("{} IDs must be unique".format(label))
            result[key] = value
        return result

    def consolidate(self, proposals, validations, approvals):
        proposal_by_id = self._indexed(
            proposals, InducedRuleProposal, "consolidation proposals",
            "proposal_id")
        validation_by_proposal = self._indexed(
            validations, ReplayValidation, "consolidation validations",
            "proposal_id")
        approval_by_proposal = self._indexed(
            approvals, InductionPromotionApproval,
            "consolidation approvals", "proposal_id")
        proposal_ids = set(proposal_by_id)
        if (set(validation_by_proposal) != proposal_ids
                or set(approval_by_proposal) != proposal_ids):
            raise ValueError(
                "consolidation requires one validation and approval per rule")
        cohort_identities = set()
        for proposal_id in sorted(proposal_by_id):
            proposal = proposal_by_id[proposal_id]
            validation = validation_by_proposal[proposal_id]
            approval = approval_by_proposal[proposal_id]
            approval.validate(proposal, validation)
            cohort_identities.add((
                approval.gate_id,
                approval.training_artifact_hash,
                approval.holdout_artifact_hash))
        if len(cohort_identities) > 1:
            raise ValueError(
                "consolidation inputs must share one approved cohort")

        ordered = tuple(sorted(proposal_by_id.values(), key=lambda row: (
            len(row.antecedent), row.antecedent, row.proposal_id)))
        retained = []
        suppressions = []
        for proposal in ordered:
            signature = self._prediction_signature(proposal)
            antecedent = set(proposal.antecedent)
            subsumers = tuple(
                candidate for candidate in retained
                if self._prediction_signature(candidate) == signature
                and set(candidate.antecedent) < antecedent)
            if not subsumers:
                retained.append(proposal)
                continue
            retained_proposal = min(subsumers, key=lambda row: (
                len(row.antecedent), row.antecedent, row.proposal_id))
            suppressions.append(PromotedRuleSuppression(
                proposal.proposal_id,
                retained_proposal.proposal_id,
                retained_proposal.antecedent,
                tuple(sorted(
                    antecedent - set(retained_proposal.antecedent)))))
        return PromotedRuleConsolidation(
            tuple(proposal_by_id),
            tuple(row.proposal_id for row in retained),
            tuple(suppressions))


@dataclass(frozen=True)
class PromotedRuleShadowPrediction:
    """One bounded training estimate exposed only as a shadow diagnostic."""

    proposal_id: str
    probability: float
    baseline_probability: float
    interval_lower: float
    interval_upper: float
    support: int
    positives: int

    def __post_init__(self):
        if not isinstance(self.proposal_id, str) or not self.proposal_id:
            raise ValueError("shadow prediction requires a proposal ID")
        for name in (
                "probability", "baseline_probability", "interval_lower",
                "interval_upper"):
            _unit(getattr(self, name), name)
        if self.interval_lower > self.interval_upper:
            raise ValueError("shadow prediction interval is inverted")
        if int(self.support) < 1:
            raise ValueError("shadow prediction support must be positive")
        if int(self.positives) < 0 or int(self.positives) > int(self.support):
            raise ValueError("shadow prediction positives are invalid")

    def to_dict(self):
        return {
            "baseline_probability": float(self.baseline_probability),
            "interval": {
                "confidence": 0.95,
                "lower": float(self.interval_lower),
                "method": "wilson-score/1.0",
                "upper": float(self.interval_upper),
            },
            "positives": int(self.positives),
            "probability": float(self.probability),
            "proposal_id": self.proposal_id,
            "support": int(self.support),
        }


@dataclass(frozen=True)
class PromotedRuleShadowResult:
    """Outcome-blind diagnostic readout with explicit abstention."""

    episode_id: str
    consequent: str
    accepted: bool
    reason: str
    matching_rule_ids: tuple
    maximal_rule_ids: tuple
    predictions: tuple
    selected_rule_id: object
    selected_probability: object
    selected_baseline_probability: object
    prediction_direction: object
    truth_mutated: bool
    policy_authority: bool
    readout_authority: bool
    action_selection_changed: bool
    result_hash: str

    def to_dict(self):
        return {
            "accepted": bool(self.accepted),
            "action_selection_changed": bool(self.action_selection_changed),
            "consequent": self.consequent,
            "episode_id": self.episode_id,
            "matching_rule_ids": list(self.matching_rule_ids),
            "maximal_rule_ids": list(self.maximal_rule_ids),
            "policy_authority": bool(self.policy_authority),
            "prediction_direction": self.prediction_direction,
            "predictions": [value.to_dict() for value in self.predictions],
            "readout_authority": bool(self.readout_authority),
            "reason": self.reason,
            "result_hash": self.result_hash,
            "selected_baseline_probability": (
                None if self.selected_baseline_probability is None
                else float(self.selected_baseline_probability)),
            "selected_probability": (
                None if self.selected_probability is None
                else float(self.selected_probability)),
            "selected_rule_id": self.selected_rule_id,
            "truth_mutated": bool(self.truth_mutated),
        }


class PromotedRuleShadowReadout(object):
    """Read an approved consolidated rule basis without control authority."""

    READOUT_IDENTITY = "fdas-promoted-rule-shadow-readout/1.0"

    def __init__(
            self, proposals, validations, approvals, consolidation):
        if not isinstance(consolidation, PromotedRuleConsolidation):
            raise TypeError("shadow readout requires typed consolidation")
        proposals = tuple(proposals)
        expected = PromotedRuleConsolidator().consolidate(
            proposals, validations, approvals)
        if expected.to_dict() != consolidation.to_dict():
            raise ValueError(
                "shadow readout consolidation does not match approvals")
        retained_ids = set(consolidation.retained_rule_ids)
        rules = tuple(sorted(
            (value for value in proposals
             if value.proposal_id in retained_ids),
            key=lambda row: row.proposal_id))
        if not rules:
            raise ValueError("shadow readout requires a nonempty rule basis")
        if len(set(value.consequent for value in rules)) != 1:
            raise ValueError("shadow readout requires one consequent")
        if len(set(value.context for value in rules)) != 1:
            raise ValueError("shadow readout requires one scoped context")
        self.rules = rules
        self.consolidation = consolidation
        self.consequent = rules[0].consequent

    @staticmethod
    def _interval(proposal):
        count = float(proposal.support)
        observed = float(proposal.positives) / count
        z = 1.959963984540054
        z_squared = z * z
        denominator = 1.0 + z_squared / count
        center = (observed + z_squared / (2.0 * count)) / denominator
        radius = z * math.sqrt(
            observed * (1.0 - observed) / count
            + z_squared / (4.0 * count * count)) / denominator
        return max(0.0, center - radius), min(1.0, center + radius)

    @classmethod
    def _prediction(cls, proposal):
        lower, upper = cls._interval(proposal)
        return PromotedRuleShadowPrediction(
            proposal.proposal_id,
            proposal.probability,
            proposal.baseline_probability,
            lower,
            upper,
            proposal.support,
            proposal.positives)

    @staticmethod
    def _direction(proposal):
        if proposal.probability > proposal.baseline_probability:
            return "above_baseline"
        if proposal.probability < proposal.baseline_probability:
            return "below_baseline"
        return "at_baseline"

    def _result(
            self, episode, accepted, reason, matching=(), maximal=(),
            selected=None):
        predictions = tuple(
            self._prediction(value)
            for value in sorted(maximal, key=lambda row: row.proposal_id))
        probability = None if selected is None else selected.probability
        baseline = (
            None if selected is None else selected.baseline_probability)
        if selected is None:
            direction = None
        else:
            direction = self._direction(selected)
        semantic = {
            "accepted": bool(accepted),
            "action_selection_changed": False,
            "consequent": self.consequent,
            "consolidation_id": self.consolidation.consolidation_id,
            "episode_id": episode.episode_id,
            "matching_rule_ids": sorted(
                value.proposal_id for value in matching),
            "maximal_rule_ids": sorted(
                value.proposal_id for value in maximal),
            "policy_authority": False,
            "prediction_direction": direction,
            "predictions": [value.to_dict() for value in predictions],
            "readout_authority": False,
            "readout_identity": self.READOUT_IDENTITY,
            "reason": str(reason),
            "selected_baseline_probability": baseline,
            "selected_probability": probability,
            "selected_rule_id": (
                None if selected is None else selected.proposal_id),
            "truth_mutated": False,
        }
        return PromotedRuleShadowResult(
            episode.episode_id,
            self.consequent,
            bool(accepted),
            str(reason),
            tuple(semantic["matching_rule_ids"]),
            tuple(semantic["maximal_rule_ids"]),
            predictions,
            semantic["selected_rule_id"],
            probability,
            baseline,
            direction,
            False,
            False,
            False,
            False,
            structural_hash(semantic))

    def read(self, episode):
        if not isinstance(episode, (InductionEpisode, InductionFeatureQuery)):
            raise TypeError(
                "shadow readout requires an outcome-free query or episode")
        matching = tuple(
            value for value in self.rules if value.applies(episode))
        if not matching:
            return self._result(
                episode, False, "no_approved_rule_matches")
        maximal = tuple(
            candidate for candidate in matching
            if not any(
                set(candidate.antecedent) < set(other.antecedent)
                for other in matching))
        directions = set(self._direction(value) for value in maximal)
        intervals = tuple(self._interval(value) for value in maximal)
        common_interval = (
            max(value[0] for value in intervals)
            <= min(value[1] for value in intervals))
        if len(directions) != 1 or not common_interval:
            return self._result(
                episode, False, "ambiguous_maximal_predictions",
                matching, maximal)
        direction = next(iter(directions))
        selected = min(maximal, key=lambda row: (
            abs(row.probability - row.baseline_probability),
            row.proposal_id))
        return self._result(
            episode,
            True,
            ("approved_shadow_prediction_available"
             if len(maximal) == 1 else
             "compatible_maximal_predictions_conservative_{}".format(
                 direction)),
            matching,
            maximal,
            selected)


@dataclass(frozen=True)
class PromotedRuleCandidateImpactRow:
    """One action-preserving counterfactual candidate score."""

    operation_id: str
    query_id: object
    admissible: bool
    baseline_rank: object
    shadow_rank: object
    baseline_priority: float
    population_baseline_priority: float
    shadow_priority: float
    priority_delta: float
    positive_goal_effect: float
    estimated: bool
    reason: str
    prediction: object

    def to_dict(self):
        return {
            "admissible": bool(self.admissible),
            "baseline_priority": float(self.baseline_priority),
            "baseline_rank": self.baseline_rank,
            "estimated": bool(self.estimated),
            "operation_id": self.operation_id,
            "population_baseline_priority": float(
                self.population_baseline_priority),
            "positive_goal_effect": float(self.positive_goal_effect),
            "prediction": (
                None if self.prediction is None
                else self.prediction.to_dict()),
            "priority_delta": float(self.priority_delta),
            "query_id": self.query_id,
            "reason": self.reason,
            "shadow_priority": float(self.shadow_priority),
            "shadow_rank": self.shadow_rank,
        }


@dataclass(frozen=True)
class PromotedRuleCandidateImpactResult:
    """A complete candidate ranking diagnostic with no selection authority."""

    actual_selected_operation_id: str
    counterfactual_selected_operation_id: object
    counterfactual_winner_changed: object
    complete_prediction_coverage: bool
    rows: tuple
    truth_mutated: bool
    policy_authority: bool
    readout_authority: bool
    action_selection_changed: bool
    result_hash: str

    def to_dict(self):
        return {
            "action_selection_changed": bool(self.action_selection_changed),
            "actual_selected_operation_id": (
                self.actual_selected_operation_id),
            "complete_prediction_coverage": bool(
                self.complete_prediction_coverage),
            "counterfactual_selected_operation_id": (
                self.counterfactual_selected_operation_id),
            "counterfactual_winner_changed": (
                self.counterfactual_winner_changed),
            "policy_authority": bool(self.policy_authority),
            "readout_authority": bool(self.readout_authority),
            "result_hash": self.result_hash,
            "rows": [value.to_dict() for value in self.rows],
            "truth_mutated": bool(self.truth_mutated),
        }


class PromotedRuleCandidateImpactAnalyzer(object):
    """Join shadow predictions to PF scores without changing their winner."""

    ANALYZER_IDENTITY = "fdas-promoted-rule-candidate-impact-shadow/1.0"

    def __init__(self, readout, config=None):
        if not isinstance(readout, PromotedRuleShadowReadout):
            raise TypeError("candidate impact requires promoted-rule readout")
        if config is not None and not isinstance(config, PressureConfig):
            raise TypeError("candidate impact requires PressureConfig")
        self.readout = readout
        self.config = config or PressureConfig()

    def _calibrated_priority(self, score, positive_effect, probability):
        if not score.admissible or positive_effect <= 0.0:
            return float(score.priority)
        operation = score.operation
        denominator = float(score.scalar_cost) + self.config.cost_epsilon
        multiplier = (
            operation.feasibility * operation.effective_deadline_fit
            / denominator)
        full_formula = (
            score.value * multiplier
            - operation.redundancy - operation.contradiction_risk)
        calibrated_value = (
            score.value - positive_effect
            + positive_effect * float(probability))
        calibrated_formula = (
            calibrated_value * multiplier
            - operation.redundancy - operation.contradiction_risk)
        # Preserve bridge, path-persistence, and other already-applied score
        # adjustments; change only the declared positive relief component.
        return float(score.priority) + calibrated_formula - full_formula

    @staticmethod
    def _rank(rows, field):
        eligible = tuple(
            value for value in rows if value["score"].admissible)
        ordered = tuple(sorted(eligible, key=lambda value: (
            -float(value[field]), value["score"].operation_id)))
        return dict(
            (value["score"].operation_id, index + 1)
            for index, value in enumerate(ordered))

    def analyze(self, scores, queries_by_operation,
                actual_selected_operation_id):
        scores = tuple(scores)
        if not scores or any(
                not isinstance(value, OperationScore) for value in scores):
            raise TypeError("candidate impact requires OperationScore values")
        score_ids = tuple(value.operation_id for value in scores)
        if len(score_ids) != len(set(score_ids)):
            raise ValueError("candidate impact score IDs must be unique")
        queries = dict(queries_by_operation)
        if set(queries).difference(score_ids):
            raise ValueError("candidate impact query references unknown score")
        if any(
                not isinstance(value, InductionFeatureQuery)
                for value in queries.values()):
            raise TypeError(
                "candidate impact requires outcome-free feature queries")
        actual_selected_operation_id = str(actual_selected_operation_id)
        selected = tuple(
            value for value in scores
            if value.operation_id == actual_selected_operation_id)
        if len(selected) != 1 or not selected[0].admissible:
            raise ValueError(
                "actual selected operation must be uniquely admissible")

        intermediate = []
        for score in scores:
            positive_effect = sum(
                max(0.0, float(value.weighted_effect))
                for value in score.goal_effects)
            query = queries.get(score.operation_id)
            prediction = (
                None if query is None else self.readout.read(query))
            estimated = bool(
                score.admissible
                and prediction is not None
                and prediction.accepted
                and positive_effect > 0.0)
            if not score.admissible:
                reason = "candidate_inadmissible"
            elif query is None:
                reason = "candidate_feature_query_missing"
            elif not prediction.accepted:
                reason = "shadow_readout_abstained:{}".format(
                    prediction.reason)
            elif positive_effect <= 0.0:
                reason = "candidate_has_no_positive_goal_effect"
            else:
                reason = "shadow_impact_estimate_available"
            population_priority = (
                self._calibrated_priority(
                    score, positive_effect,
                    prediction.selected_baseline_probability)
                if estimated else float(score.priority))
            shadow_priority = (
                self._calibrated_priority(
                    score, positive_effect,
                    prediction.selected_probability)
                if estimated else float(score.priority))
            intermediate.append({
                "estimated": estimated,
                "population_priority": population_priority,
                "positive_effect": positive_effect,
                "prediction": prediction,
                "query": query,
                "reason": reason,
                "score": score,
                "shadow_priority": shadow_priority,
            })
        baseline_ranks = self._rank(
            tuple(dict(value, baseline_priority=value["score"].priority)
                  for value in intermediate),
            "baseline_priority")
        if baseline_ranks.get(actual_selected_operation_id) != 1:
            raise ValueError(
                "actual selected operation does not match baseline winner")
        shadow_ranks = self._rank(intermediate, "shadow_priority")
        admissible = tuple(
            value for value in intermediate if value["score"].admissible)
        complete = bool(admissible) and all(
            value["estimated"] for value in admissible)
        counterfactual = (
            min(admissible, key=lambda value: (
                -value["shadow_priority"], value["score"].operation_id))[
                    "score"].operation_id
            if complete else None)
        changed = (
            counterfactual != actual_selected_operation_id
            if counterfactual is not None else None)
        rows = tuple(
            PromotedRuleCandidateImpactRow(
                value["score"].operation_id,
                None if value["query"] is None else value["query"].query_id,
                value["score"].admissible,
                baseline_ranks.get(value["score"].operation_id),
                shadow_ranks.get(value["score"].operation_id),
                value["score"].priority,
                value["population_priority"],
                value["shadow_priority"],
                value["shadow_priority"] - value["score"].priority,
                value["positive_effect"],
                value["estimated"],
                value["reason"],
                value["prediction"])
            for value in sorted(
                intermediate, key=lambda row: row["score"].operation_id))
        semantic = {
            "action_selection_changed": False,
            "actual_selected_operation_id": actual_selected_operation_id,
            "analyzer_identity": self.ANALYZER_IDENTITY,
            "complete_prediction_coverage": complete,
            "counterfactual_selected_operation_id": counterfactual,
            "counterfactual_winner_changed": changed,
            "policy_authority": False,
            "readout_authority": False,
            "rows": [value.to_dict() for value in rows],
            "truth_mutated": False,
        }
        return PromotedRuleCandidateImpactResult(
            actual_selected_operation_id,
            counterfactual,
            changed,
            complete,
            rows,
            False,
            False,
            False,
            False,
            structural_hash(semantic))


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
            validation = ReplayValidation.from_dict(row)
            if validation.verdict == "promoted":
                approval_value = row.get("approval")
                if not isinstance(approval_value, dict):
                    raise ValueError(
                        "persisted promotion has no versioned approval")
                approval = InductionPromotionApproval.from_dict(
                    approval_value)
                approval.validate(
                    InducedRuleProposal.from_dict(
                        self._proposals[proposal_id]["proposal"]),
                    validation)
            elif row.get("approval") is not None:
                raise ValueError("persisted demotion cannot carry approval")
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

    def record_validation(self, validation, approval=None):
        if not isinstance(validation, ReplayValidation):
            raise TypeError("ledger accepts ReplayValidation")
        with self._lock:
            proposal = self._proposals.get(validation.proposal_id)
            if proposal is None:
                raise KeyError("validation proposal is not quarantined")
            value = validation.to_dict()
            proposal_value = InducedRuleProposal.from_dict(
                proposal["proposal"])
            if validation.verdict == "promoted":
                if not isinstance(approval, InductionPromotionApproval):
                    raise ValueError(
                        "promoted validation requires versioned approval")
                approval.validate(proposal_value, validation)
                value["approval"] = approval.to_dict()
            elif approval is not None:
                raise ValueError("demoted validation cannot carry approval")
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
            self, writer, turn, validation, approval=None, caused_by=()):
        self.record_validation(validation, approval=approval)
        payload = {
            "ledger_hash": self.state_hash,
            "metrics": validation.metrics.to_dict(),
            "proposal_id": validation.proposal_id,
            "reason": validation.reason,
            "validation_id": validation.validation_id,
            "verdict": validation.verdict,
        }
        if approval is not None:
            payload["approval"] = approval.to_dict()
        return writer.emit(
            "rule_validated", turn, payload, caused_by=caused_by)
