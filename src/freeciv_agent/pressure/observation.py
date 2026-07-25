"""Exact one-step value-of-information planning with simulator provenance."""

import math
from dataclasses import dataclass

from .engine import PressureEngine, PressureGraph
from .model import (
    AtomState,
    CostVector,
    GoalState,
    Operation,
    PressureConfig,
    Resolvability,
    TruthState,
)
from .provenance import ObservationPolicy
from .scheduler import PressureScheduler


_PROBABILITY_TOLERANCE = 1e-9


def _probability(value, name):
    value = float(value)
    if not 0.0 <= value <= 1.0 or not math.isfinite(value):
        raise ValueError("{} must be a finite probability".format(name))
    return value


def _entropy(probabilities):
    return -sum(
        value * math.log(value, 2)
        for value in probabilities if value > 0.0)


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    probability: float

    def __post_init__(self):
        if not self.hypothesis_id:
            raise ValueError("hypothesis ID is required")
        _probability(self.probability, "hypothesis probability")

    def to_dict(self):
        return {
            "hypothesis_id": self.hypothesis_id,
            "probability": float(self.probability),
        }


@dataclass(frozen=True)
class ObservationOutcome:
    outcome_id: str
    likelihoods: tuple

    def __post_init__(self):
        if not self.outcome_id or not self.likelihoods:
            raise ValueError("observation outcome requires ID and likelihoods")
        keys = [str(row[0]) for row in self.likelihoods]
        if len(keys) != len(set(keys)):
            raise ValueError("outcome hypothesis likelihoods must be unique")
        for _, value in self.likelihoods:
            _probability(value, "outcome likelihood")

    def likelihood(self, hypothesis_id):
        return float(dict(self.likelihoods)[str(hypothesis_id)])

    def to_dict(self):
        return {
            "likelihoods": dict(
                (str(key), float(value)) for key, value in self.likelihoods),
            "outcome_id": self.outcome_id,
        }


@dataclass(frozen=True)
class ObservationTest:
    test_id: str
    atom_id: str
    outcomes: tuple
    cost: CostVector
    model_provenance: object
    success_probability: float = 1.0
    feasibility: float = 1.0
    deadline_fit: float = 1.0

    def __post_init__(self):
        if not self.test_id or not self.atom_id or not self.outcomes:
            raise ValueError("observation test requires ID, atom, and outcomes")
        if len({row.outcome_id for row in self.outcomes}) != len(self.outcomes):
            raise ValueError("observation outcome IDs must be unique")
        if not isinstance(self.cost, CostVector):
            raise TypeError("observation test cost must be CostVector")
        if not all((
                hasattr(self.model_provenance, "to_dict"),
                getattr(self.model_provenance, "source_kind", None)
                == "simulator",
                bool(getattr(self.model_provenance, "model_id", "")),
                bool(getattr(self.model_provenance, "model_hash", "")),
        )):
            raise ValueError(
                "observation tests require explicit simulator provenance")
        _probability(self.success_probability, "test success probability")
        _probability(self.feasibility, "test feasibility")
        _probability(self.deadline_fit, "test deadline fit")

    def to_dict(self):
        return {
            "atom_id": self.atom_id,
            "cost": self.cost.to_dict(),
            "deadline_fit": float(self.deadline_fit),
            "feasibility": float(self.feasibility),
            "model_provenance": self.model_provenance.to_dict(),
            "outcomes": [row.to_dict() for row in self.outcomes],
            "success_probability": float(self.success_probability),
            "test_id": self.test_id,
        }


@dataclass(frozen=True)
class InformationValue:
    test: ObservationTest
    prior_entropy: float
    expected_posterior_entropy: float
    expected_information_gain: float
    outcome_probabilities: tuple

    def to_dict(self):
        return {
            "expected_information_gain": float(
                self.expected_information_gain),
            "expected_posterior_entropy": float(
                self.expected_posterior_entropy),
            "outcome_probabilities": dict(self.outcome_probabilities),
            "prior_entropy": float(self.prior_entropy),
            "test": self.test.to_dict(),
        }


def expected_information_value(hypotheses, test):
    """Enumerate all outcomes and return exact one-step expected entropy relief."""
    hypotheses = tuple(hypotheses)
    if not hypotheses or not isinstance(test, ObservationTest):
        raise ValueError("VOI requires hypotheses and an ObservationTest")
    hypothesis_ids = [row.hypothesis_id for row in hypotheses]
    if len(hypothesis_ids) != len(set(hypothesis_ids)):
        raise ValueError("hypothesis IDs must be unique")
    prior_total = sum(row.probability for row in hypotheses)
    if abs(prior_total - 1.0) > _PROBABILITY_TOLERANCE:
        raise ValueError("hypothesis probabilities must sum to one")
    expected_ids = set(hypothesis_ids)
    for outcome in test.outcomes:
        if set(str(row[0]) for row in outcome.likelihoods) != expected_ids:
            raise ValueError(
                "each outcome must declare every hypothesis likelihood")
    for hypothesis_id in hypothesis_ids:
        total = sum(
            outcome.likelihood(hypothesis_id) for outcome in test.outcomes)
        if abs(total - 1.0) > _PROBABILITY_TOLERANCE:
            raise ValueError(
                "outcome likelihoods for {} must sum to one".format(
                    hypothesis_id))

    prior_entropy = _entropy(
        tuple(row.probability for row in hypotheses))
    expected_posterior = 0.0
    outcome_probabilities = []
    for outcome in test.outcomes:
        outcome_probability = sum(
            hypothesis.probability
            * outcome.likelihood(hypothesis.hypothesis_id)
            for hypothesis in hypotheses)
        outcome_probabilities.append(
            (outcome.outcome_id, outcome_probability))
        if outcome_probability <= 0.0:
            continue
        posterior = tuple(
            hypothesis.probability
            * outcome.likelihood(hypothesis.hypothesis_id)
            / outcome_probability
            for hypothesis in hypotheses)
        expected_posterior += outcome_probability * _entropy(posterior)
    gain = max(
        0.0,
        (prior_entropy - expected_posterior)
        * float(test.success_probability))
    return InformationValue(
        test=test,
        prior_entropy=prior_entropy,
        expected_posterior_entropy=expected_posterior,
        expected_information_gain=gain,
        outcome_probabilities=tuple(outcome_probabilities),
    )


class ValueOfInformationPlanner(object):
    """Ranks bounded hypothesis tests and schedules them through typed pressure."""

    def __init__(self, config=None):
        self.config = config or PressureConfig()
        self.engine = PressureEngine(self.config)
        self.scheduler = PressureScheduler(self.config)

    @staticmethod
    def rank(hypotheses, tests):
        rows = [
            expected_information_value(hypotheses, test) for test in tests]
        return tuple(sorted(
            rows,
            key=lambda row: (
                -row.expected_information_gain, row.test.test_id)))

    @staticmethod
    def operation(value, goal_id):
        if not isinstance(value, InformationValue):
            raise TypeError("operation requires InformationValue")
        policy = ObservationPolicy(
            str(goal_id), "observe",
            value.expected_information_gain, propensity=None)
        test = value.test
        return Operation(
            operation_id="observe:{}".format(test.test_id),
            atom_id=test.atom_id,
            mode="observe",
            cost=test.cost,
            causal_kind="diagnostic",
            success_probability=test.success_probability,
            feasibility=test.feasibility,
            deadline_fit=test.deadline_fit,
            information_gain=value.expected_information_gain,
            payload={
                "expected_information_value": value.to_dict(),
                "model_provenance": test.model_provenance.to_dict(),
                "observation_policy": policy.to_dict(),
            },
        )

    def decision_for_conflict(
            self, conflict, hypotheses, tests, utility=1.0, urgency=1.0):
        """Schedule tests for one explicit conflict without revising its truth."""
        conflict_atom = conflict.atom()
        graph = PressureGraph()
        graph.add_atom(
            AtomState(
                conflict.conflict_id,
                TruthState(
                    conflict.severity,
                    conflict_atom["tv"]["confidence"],
                    tuple(conflict.provenance_ids),
                    crisp=False),
                expression=conflict_atom,
                context=tuple(conflict.context_ids)),
            Resolvability(observe=1.0, infer=0.2, expand=0.2))
        goal = GoalState(
            "resolve:{}".format(conflict.conflict_id),
            conflict.conflict_id,
            target_strength=0.0,
            utility=utility,
            urgency=urgency,
            context=tuple(conflict.context_ids))
        pressure = self.engine.propagate(graph, (goal,))
        values = self.rank(hypotheses, tests)
        if any(row.test.atom_id != conflict.conflict_id for row in values):
            raise ValueError("conflict tests must target the conflict atom")
        operations = tuple(
            self.operation(value, goal.goal_id) for value in values)
        return {
            "goal": goal,
            "graph": graph,
            "information_values": values,
            "operations": operations,
            "pressure": pressure,
            "schedule": self.scheduler.decision_artifact(
                operations, pressure),
        }
