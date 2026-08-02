"""Exact one-step value-of-information planning with simulator provenance."""

import math
from dataclasses import dataclass, replace

from .engine import (
    PressureEngine,
    PressureEngineV2,
    PressureGraph,
    PressureV2Policy,
)
from .model import (
    AtomState,
    CostVector,
    GoalState,
    Operation,
    PressureConfig,
    Resolvability,
    TruthAssessment,
    TruthState,
)
from .provenance import ObservationPolicy
from .packets import PacketBudget, PacketCost, PacketScheduler, ResourceKind
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
    decision_sensitivity: float = 1.0
    evidence_overlap: float = 0.0
    execution_kind: str = "observation"

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
        _probability(
            self.decision_sensitivity, "decision sensitivity")
        _probability(self.evidence_overlap, "evidence overlap")
        if self.execution_kind not in ("observation", "simulation"):
            raise ValueError(
                "observation execution kind must be "
                "observation or simulation")

    def to_dict(self):
        value = {
            "atom_id": self.atom_id,
            "cost": self.cost.to_dict(),
            "deadline_fit": float(self.deadline_fit),
            "feasibility": float(self.feasibility),
            "model_provenance": self.model_provenance.to_dict(),
            "outcomes": [row.to_dict() for row in self.outcomes],
            "success_probability": float(self.success_probability),
            "test_id": self.test_id,
        }
        if self.decision_sensitivity != 1.0:
            value["decision_sensitivity"] = float(
                self.decision_sensitivity)
        if self.evidence_overlap:
            value["evidence_overlap"] = float(
                self.evidence_overlap)
        if self.execution_kind != "observation":
            value["execution_kind"] = self.execution_kind
        return value


@dataclass(frozen=True)
class BoundedDecision:
    """One explicit binary readout whose result an observation may change."""

    decision_id: str
    positive_hypothesis_id: str
    threshold: float
    below_threshold_action_id: str
    at_or_above_threshold_action_id: str

    def __post_init__(self):
        if not self.decision_id or not self.positive_hypothesis_id:
            raise ValueError("bounded decision requires decision and hypothesis IDs")
        _probability(self.threshold, "bounded decision threshold")
        if (not self.below_threshold_action_id
                or not self.at_or_above_threshold_action_id):
            raise ValueError("bounded decision requires both action IDs")
        if (self.below_threshold_action_id
                == self.at_or_above_threshold_action_id):
            raise ValueError("bounded decision actions must differ")

    def action(self, positive_probability):
        _probability(positive_probability, "bounded decision probability")
        return (
            self.at_or_above_threshold_action_id
            if float(positive_probability) >= float(self.threshold)
            else self.below_threshold_action_id)

    def to_dict(self):
        return {
            "at_or_above_threshold_action_id":
                self.at_or_above_threshold_action_id,
            "below_threshold_action_id": self.below_threshold_action_id,
            "decision_id": self.decision_id,
            "positive_hypothesis_id": self.positive_hypothesis_id,
            "threshold": float(self.threshold),
        }


@dataclass(frozen=True)
class BoundedDecisionAnalysis:
    """Counterfactual decision readout for every observation outcome."""

    decision: BoundedDecision
    prior_positive_probability: float
    prior_action_id: str
    outcome_rows: tuple
    decision_change_probability: float

    @property
    def decision_sensitive(self):
        return self.decision_change_probability > _PROBABILITY_TOLERANCE

    def to_dict(self):
        return {
            "decision": self.decision.to_dict(),
            "decision_change_probability": float(
                self.decision_change_probability),
            "decision_sensitive": bool(self.decision_sensitive),
            "outcomes": [dict(row) for row in self.outcome_rows],
            "prior_action_id": self.prior_action_id,
            "prior_positive_probability": float(
                self.prior_positive_probability),
            "semantics": "bounded-decision-counterfactual/1.0",
        }


@dataclass(frozen=True)
class InformationValue:
    test: ObservationTest
    prior_entropy: float
    expected_posterior_entropy: float
    expected_information_gain: float
    outcome_probabilities: tuple
    raw_information_gain: object = None
    decision_relevance_factor: float = 1.0
    overlap_discount: float = 1.0
    bounded_decision_analysis: object = None

    def to_dict(self):
        value = {
            "expected_information_gain": float(
                self.expected_information_gain),
            "expected_posterior_entropy": float(
                self.expected_posterior_entropy),
            "outcome_probabilities": dict(self.outcome_probabilities),
            "prior_entropy": float(self.prior_entropy),
            "test": self.test.to_dict(),
        }
        if self.raw_information_gain is not None:
            value["raw_information_gain"] = float(
                self.raw_information_gain)
        if self.decision_relevance_factor != 1.0:
            value["decision_relevance_factor"] = float(
                self.decision_relevance_factor)
        if self.overlap_discount != 1.0:
            value["overlap_discount"] = float(
                self.overlap_discount)
        if self.bounded_decision_analysis is not None:
            value["bounded_decision_analysis"] = (
                self.bounded_decision_analysis.to_dict())
        return value


@dataclass(frozen=True)
class ObservationSelectionRecord:
    operation_id: str
    goal_id: str
    selected: bool
    priority: float
    propensity: object
    reason: str
    recorded_before_execution: bool = True

    def __post_init__(self):
        if not self.operation_id or not self.goal_id:
            raise ValueError(
                "observation selection requires operation and goal IDs")
        if not isinstance(self.selected, bool):
            raise TypeError("observation selection flag must be boolean")
        if float(self.priority) < 0.0 or not math.isfinite(
                float(self.priority)):
            raise ValueError(
                "observation selection priority must be non-negative")
        if (self.propensity is not None
                and not 0.0 < float(self.propensity) <= 1.0):
            raise ValueError(
                "selection propensity must be in (0,1]")
        if not self.reason:
            raise ValueError(
                "observation selection requires reason")
        if not self.recorded_before_execution:
            raise ValueError(
                "selection must be recorded before execution")

    def to_dict(self):
        return {
            "goal_id": self.goal_id,
            "operation_id": self.operation_id,
            "priority": float(self.priority),
            "propensity": self.propensity,
            "reason": self.reason,
            "recorded_before_execution": True,
            "selected": bool(self.selected),
        }


class ObservationEvidenceGate:
    """Register evidence only for selected authoritative completions."""

    def __init__(self, evidence_ledger):
        from .provenance import EvidenceLedger
        if not isinstance(evidence_ledger, EvidenceLedger):
            raise TypeError(
                "observation gate requires EvidenceLedger")
        self.evidence_ledger = evidence_ledger
        self._selections = {}
        self._completed = {}

    @property
    def selection_records(self):
        return tuple(
            self._selections[key]
            for key in sorted(self._selections))

    def record_selection(self, record):
        if not isinstance(record, ObservationSelectionRecord):
            raise TypeError(
                "selection log requires "
                "ObservationSelectionRecord")
        existing = self._selections.get(record.operation_id)
        if existing is not None and existing != record:
            raise ValueError(
                "observation selection identity reused")
        self._selections[record.operation_id] = record
        return record

    def authoritative_return(
            self, operation_id, evidence_token,
            authoritative=True):
        from .provenance import EvidenceToken
        record = self._selections.get(str(operation_id))
        if record is None or not record.selected:
            raise ValueError(
                "evidence requires a selected observation")
        if not isinstance(authoritative, bool):
            raise TypeError(
                "authoritative flag must be boolean")
        if not authoritative:
            raise ValueError(
                "non-authoritative observation cannot register evidence")
        if not isinstance(evidence_token, EvidenceToken):
            raise TypeError(
                "authoritative return requires EvidenceToken")
        if record.operation_id in self._completed:
            if self._completed[record.operation_id] != evidence_token:
                raise ValueError(
                    "observation completion identity reused")
            return evidence_token
        registered = self.evidence_ledger.register(evidence_token)
        self._completed[record.operation_id] = registered
        return registered


@dataclass(frozen=True)
class DecisionRelevantUncertainty:
    """Epistemic uncertainty after declared decision sensitivity."""

    assessment: TruthAssessment
    decision_sensitivity: float
    amount: float

    def to_dict(self):
        return {
            "amount": float(self.amount),
            "assessment": self.assessment.to_dict(),
            "decision_sensitivity": float(self.decision_sensitivity),
            "semantics": "decision-relevant-uncertainty/1.0",
        }


def decision_relevant_uncertainty(
        truth, decision_sensitivity=1.0, posterior_variance=None):
    """Return uncertainty demand without treating it as state failure."""
    if not isinstance(truth, TruthState):
        raise TypeError("uncertainty source must be TruthState")
    sensitivity = float(decision_sensitivity)
    if sensitivity < 0.0 or not math.isfinite(sensitivity):
        raise ValueError(
            "decision sensitivity must be finite and non-negative")
    assessment = TruthAssessment.from_truth(
        truth, posterior_variance=posterior_variance)
    return DecisionRelevantUncertainty(
        assessment, sensitivity,
        sensitivity * assessment.epistemic_uncertainty())


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
    raw_gain = max(
        0.0, prior_entropy - expected_posterior)
    relevance = float(test.decision_sensitivity)
    overlap_discount = 1.0 - float(test.evidence_overlap)
    gain = (
        raw_gain * float(test.success_probability)
        * relevance * overlap_discount)
    return InformationValue(
        test=test,
        prior_entropy=prior_entropy,
        expected_posterior_entropy=expected_posterior,
        expected_information_gain=gain,
        outcome_probabilities=tuple(outcome_probabilities),
        raw_information_gain=(
            raw_gain
            if relevance != 1.0 or overlap_discount != 1.0
            else None),
        decision_relevance_factor=relevance,
        overlap_discount=overlap_discount,
    )


def bounded_decision_information_value(hypotheses, test, decision):
    """Bind VOI to observed counterfactual action changes, not a label."""
    hypotheses = tuple(hypotheses)
    if not isinstance(test, ObservationTest):
        raise TypeError("bounded decision VOI requires ObservationTest")
    if not isinstance(decision, BoundedDecision):
        raise TypeError("bounded decision VOI requires BoundedDecision")
    by_id = dict((row.hypothesis_id, row) for row in hypotheses)
    if decision.positive_hypothesis_id not in by_id:
        raise ValueError("bounded decision hypothesis is not in the prior")
    # Validate the probability table before deriving any readout from it.
    raw = expected_information_value(hypotheses, test)
    prior_positive = float(
        by_id[decision.positive_hypothesis_id].probability)
    prior_action = decision.action(prior_positive)
    outcome_probability_by_id = dict(raw.outcome_probabilities)
    outcome_rows = []
    change_probability = 0.0
    for outcome in test.outcomes:
        outcome_probability = float(
            outcome_probability_by_id[outcome.outcome_id])
        posterior_positive = (
            prior_positive
            * outcome.likelihood(decision.positive_hypothesis_id)
            / outcome_probability
            if outcome_probability > 0.0 else prior_positive)
        action_id = decision.action(posterior_positive)
        changes_decision = (
            outcome_probability > 0.0 and action_id != prior_action)
        if changes_decision:
            change_probability += outcome_probability
        outcome_rows.append({
            "action_id": action_id,
            "changes_decision": bool(changes_decision),
            "outcome_id": outcome.outcome_id,
            "outcome_probability": outcome_probability,
            "posterior_positive_probability": posterior_positive,
        })
    analysis = BoundedDecisionAnalysis(
        decision=decision,
        prior_positive_probability=prior_positive,
        prior_action_id=prior_action,
        outcome_rows=tuple(outcome_rows),
        decision_change_probability=min(1.0, change_probability))
    bound_test = replace(
        test, decision_sensitivity=analysis.decision_change_probability)
    value = expected_information_value(hypotheses, bound_test)
    return replace(value, bounded_decision_analysis=analysis)


class ValueOfInformationPlanner(object):
    """Ranks bounded hypothesis tests and schedules them through typed pressure."""

    def __init__(self, config=None, engine_live=False):
        self.config = config or PressureConfig()
        self.engine = PressureEngine(self.config)
        self.scheduler = PressureScheduler(self.config)
        if not isinstance(engine_live, bool):
            raise TypeError("engine_live must be boolean")
        self.engine_live = engine_live

    @staticmethod
    def rank(hypotheses, tests):
        rows = [
            expected_information_value(hypotheses, test) for test in tests]
        return tuple(sorted(
            rows,
            key=lambda row: (
                -row.expected_information_gain, row.test.test_id)))

    @staticmethod
    def eligibility(value):
        """Fail closed unless an observation can affect a bounded decision."""
        if not isinstance(value, InformationValue):
            raise TypeError("observation eligibility requires InformationValue")
        test = value.test
        if test.decision_sensitivity <= 0.0:
            return False, "decision-insensitive-uncertainty"
        if value.expected_information_gain <= _PROBABILITY_TOLERANCE:
            return False, "no-bounded-decision-information-gain"
        if test.success_probability <= 0.0:
            return False, "observation-cannot-succeed"
        if test.feasibility <= 0.0:
            return False, "observation-not-feasible"
        if test.deadline_fit <= 0.0:
            return False, "observation-misses-decision-deadline"
        return True, None

    def operation(
            self, value, goal_id, propensity=None,
            deterministic_reason=None):
        if not isinstance(value, InformationValue):
            raise TypeError("operation requires InformationValue")
        eligible, reason = self.eligibility(value)
        if not eligible:
            raise ValueError(
                "observation cannot change bounded decision: {}".format(
                    reason))
        policy = ObservationPolicy(
            str(goal_id), "observe",
            value.expected_information_gain,
            propensity=propensity)
        test = value.test
        packet_costs = ()
        if self.engine_live:
            packet_resource = (
                ResourceKind.SIMULATION
                if test.execution_kind == "simulation" else
                ResourceKind.OBSERVATION)
            packet_costs = (
                PacketCost(ResourceKind.CPU, 1),
                PacketCost(packet_resource, 1),
            )
        payload = {
            "expected_information_value": value.to_dict(),
            "model_provenance": test.model_provenance.to_dict(),
            "observation_policy": policy.to_dict(),
        }
        if deterministic_reason is not None:
            payload["selection_declaration"] = {
                "propensity": propensity,
                "reason": str(deterministic_reason),
            }
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
            payload=payload,
            packet_costs=packet_costs,
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
        eligible_values = []
        omitted_tests = []
        for value in values:
            eligible, reason = self.eligibility(value)
            if eligible:
                eligible_values.append(value)
            else:
                omitted_tests.append({
                    "reason": reason,
                    "test_id": value.test.test_id,
                })
        operations = tuple(
            self.operation(
                value, goal.goal_id,
                deterministic_reason=(
                    "deterministic-highest-priority"))
            for value in eligible_values)
        schedule = self.scheduler.decision_artifact(
            operations, pressure)
        selected_id = schedule["selected_operation_id"]
        score_by_id = dict(
            (row["operation"]["operation_id"], row["priority"])
            for row in schedule["scores"])
        selection_records = tuple(
            ObservationSelectionRecord(
                operation.operation_id,
                goal.goal_id,
                operation.operation_id == selected_id,
                max(0.0, float(score_by_id[operation.operation_id])),
                None,
                "deterministic-highest-priority")
            for operation in operations)
        return {
            "goal": goal,
            "graph": graph,
            "information_values": values,
            "omitted_tests": tuple(omitted_tests),
            "operations": operations,
            "pressure": pressure,
            "schedule": schedule,
            "selection_records": selection_records,
        }

    def decision_for_uncertainty(
            self, atom, decision, hypotheses, tests,
            utility=1.0, urgency=1.0):
        """Schedule only tests proven able to change one bounded readout."""
        if not isinstance(atom, AtomState):
            raise TypeError("uncertainty decision requires AtomState")
        if atom.truth.crisp:
            raise ValueError("crisp facts cannot create observation pressure")
        if not isinstance(decision, BoundedDecision):
            raise TypeError("uncertainty decision requires BoundedDecision")
        values = tuple(sorted(
            (bounded_decision_information_value(
                hypotheses, test, decision) for test in tests),
            key=lambda row: (
                -row.expected_information_gain, row.test.test_id)))
        if any(row.test.atom_id != atom.atom_id for row in values):
            raise ValueError("uncertainty tests must target the uncertain atom")
        eligible_values = []
        omitted_tests = []
        for value in values:
            eligible, reason = self.eligibility(value)
            if eligible:
                eligible_values.append(value)
            else:
                omitted_tests.append({
                    "reason": reason,
                    "test_id": value.test.test_id,
                })
        maximum_sensitivity = max(
            (value.test.decision_sensitivity for value in values),
            default=0.0)
        graph = PressureGraph()
        graph.add_atom(
            atom, Resolvability(observe=1.0, infer=0.2, expand=0.2))
        goal = GoalState(
            "observe:{}".format(decision.decision_id),
            atom.atom_id,
            # No achievement deficit is invented: the only demand is the
            # confidence gap on the existing uncertain belief.
            target_strength=atom.truth.strength,
            utility=utility,
            urgency=urgency,
            context=tuple(atom.context))
        uncertainty_engine = PressureEngineV2(
            self.config,
            PressureV2Policy(decision_sensitivity=maximum_sensitivity))
        pressure = uncertainty_engine.propagate(graph, (goal,))
        operations = tuple(
            self.operation(
                value, goal.goal_id,
                deterministic_reason="bounded-decision-counterfactual")
            for value in eligible_values)
        schedule = self.scheduler.decision_artifact(
            operations, pressure)
        selected_id = schedule["selected_operation_id"]
        score_by_id = dict(
            (row["operation"]["operation_id"], row["priority"])
            for row in schedule["scores"])
        selection_records = tuple(
            ObservationSelectionRecord(
                operation.operation_id,
                goal.goal_id,
                operation.operation_id == selected_id,
                max(0.0, float(score_by_id[operation.operation_id])),
                None,
                "bounded-decision-counterfactual")
            for operation in operations)
        return {
            "bounded_decision": decision,
            "goal": goal,
            "graph": graph,
            "information_values": values,
            "omitted_tests": tuple(omitted_tests),
            "operations": operations,
            "pressure": pressure,
            "schedule": schedule,
            "selection_records": selection_records,
        }

    def _packetize(self, decision, packet_budgets):
        packet_budgets = tuple(packet_budgets)
        if any(not isinstance(value, PacketBudget) for value in packet_budgets):
            raise TypeError("observation packet budgets require PacketBudget")
        scores = self.scheduler.score_all(
            decision["operations"], decision["pressure"])
        packet_schedule = PacketScheduler().schedule(
            decision["operations"], scores, packet_budgets)
        committed = frozenset(packet_schedule.committed_operation_ids)
        score_by_id = dict(
            (value.operation_id, value) for value in scores)
        selection_records = tuple(
            ObservationSelectionRecord(
                operation.operation_id,
                decision["goal"].goal_id,
                operation.operation_id in committed,
                max(0.0, float(score_by_id[operation.operation_id].priority)),
                None,
                ("atomic-packet-budget-committed"
                 if operation.operation_id in committed else
                 "atomic-packet-budget-not-committed"))
            for operation in decision["operations"])
        result = dict(decision)
        result["packet_schedule"] = packet_schedule
        result["selection_records"] = selection_records
        result["selected_operation_ids"] = tuple(
            packet_schedule.committed_operation_ids)
        return result

    def packet_decision_for_uncertainty(
            self, atom, decision, hypotheses, tests, packet_budgets,
            utility=1.0, urgency=1.0):
        """Budget a decision-sensitive belief observation atomically."""
        if not self.engine_live:
            raise ValueError(
                "packet observation decisions require engine_live")
        planned = self.decision_for_uncertainty(
            atom, decision, hypotheses, tests,
            utility=utility, urgency=urgency)
        return self._packetize(planned, packet_budgets)

    def packet_decision_for_conflict(
            self, conflict, hypotheses, tests, packet_budgets,
            utility=1.0, urgency=1.0):
        """Atomically budget CPU plus observation/simulation packets."""
        if not self.engine_live:
            raise ValueError(
                "packet observation decisions require engine_live")
        decision = self.decision_for_conflict(
            conflict, hypotheses, tests, utility=utility, urgency=urgency)
        return self._packetize(decision, packet_budgets)
