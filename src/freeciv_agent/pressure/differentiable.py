"""Delimited scalar-tensor autodiff for differentiable PF-PLN truth paths.

Only smooth truth functions and rule-parameter calibration live here.
Requirement pressure, counterfactual pressure, lifecycle transitions, and
scheduler selection remain explicitly non-differentiable control operators.
"""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash


DIFFERENTIABLE_RULE_KINDS = frozenset(("product-and", "probabilistic-or"))


def _unit(value, name):
    result = float(value)
    if not 0.0 <= result <= 1.0 or not math.isfinite(result):
        raise ValueError("{} must be in [0,1]".format(name))
    return result


class ADScalar(object):
    """Minimal reverse-mode scalar tensor with explicit local Jacobians."""

    def __init__(self, value, label=None, parents=()):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("AD scalar must be finite")
        self.value = value
        self.label = None if label is None else str(label)
        self.parents = tuple(parents)
        self.gradient = 0.0

    @staticmethod
    def constant(value, label=None):
        return ADScalar(value, label)

    @staticmethod
    def _coerce(value):
        return value if isinstance(value, ADScalar) else ADScalar(value)

    def __add__(self, other):
        other = self._coerce(other)
        return ADScalar(
            self.value + other.value, parents=((self, 1.0), (other, 1.0)))

    __radd__ = __add__

    def __neg__(self):
        return ADScalar(-self.value, parents=((self, -1.0),))

    def __sub__(self, other):
        return self + (-self._coerce(other))

    def __rsub__(self, other):
        return self._coerce(other) - self

    def __mul__(self, other):
        other = self._coerce(other)
        return ADScalar(
            self.value * other.value,
            parents=((self, other.value), (other, self.value)))

    __rmul__ = __mul__

    def square(self):
        return self * self

    def _topology(self):
        result = []
        visited = set()

        def visit(node):
            marker = id(node)
            if marker in visited:
                return
            visited.add(marker)
            for parent, _ in node.parents:
                visit(parent)
            result.append(node)

        visit(self)
        return result

    def backward(self, seed=1.0):
        topology = self._topology()
        for node in topology:
            node.gradient = 0.0
        self.gradient = float(seed)
        for node in reversed(topology):
            for parent, derivative in node.parents:
                parent.gradient += node.gradient * float(derivative)
        return dict(
            (node.label, node.gradient)
            for node in topology if node.label is not None)


@dataclass(frozen=True)
class TensorTruth:
    """Two-component differentiable truth tensor, still pressure-free."""

    strength: ADScalar
    confidence: ADScalar
    evidence_ids: tuple = ()

    def __post_init__(self):
        if not isinstance(self.strength, ADScalar) or not isinstance(
                self.confidence, ADScalar):
            raise TypeError("tensor truth components must be ADScalar")
        _unit(self.strength.value, "tensor strength")
        _unit(self.confidence.value, "tensor confidence")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("tensor truth evidence IDs must be unique")

    @classmethod
    def leaf(cls, atom_id, strength, confidence, evidence_ids=()):
        return cls(
            ADScalar(strength, "{}.strength".format(atom_id)),
            ADScalar(confidence, "{}.confidence".format(atom_id)),
            tuple(sorted(str(value) for value in evidence_ids)))

    @property
    def supported(self):
        return self.strength * self.confidence

    def to_dict(self):
        return {
            "confidence": float(self.confidence.value),
            "evidence_ids": list(self.evidence_ids),
            "strength": float(self.strength.value),
        }


@dataclass(frozen=True)
class DifferentiableTruthRule:
    rule_id: str
    kind: str

    def __post_init__(self):
        if not str(self.rule_id):
            raise ValueError("differentiable rule ID is required")
        object.__setattr__(self, "rule_id", str(self.rule_id))
        if self.kind not in DIFFERENTIABLE_RULE_KINDS:
            raise ValueError("rule is outside the differentiable subset")

    def forward(self, premises):
        premises = tuple(premises)
        if not premises or any(
                not isinstance(value, ADScalar) for value in premises):
            raise TypeError("differentiable rule needs ADScalar premises")
        if self.kind == "product-and":
            result = ADScalar(1.0)
            for value in premises:
                result = result * value
            return result
        complement = ADScalar(1.0)
        for value in premises:
            complement = complement * (1.0 - value)
        return 1.0 - complement

    def evaluate(self, values):
        values = tuple(_unit(value, "premise") for value in values)
        if not values:
            raise ValueError("truth rule needs premises")
        if self.kind == "product-and":
            result = 1.0
            for value in values:
                result *= value
            return result
        complement = 1.0
        for value in values:
            complement *= 1.0 - value
        return 1.0 - complement


@dataclass(frozen=True)
class AdjointPressure:
    rule_id: str
    conclusion: float
    target: float
    incoming: float
    premise_rows: tuple

    def pressure(self, premise_id):
        return float(dict(self.premise_rows).get(str(premise_id), 0.0))

    def to_dict(self):
        return {
            "conclusion": float(self.conclusion),
            "incoming": float(self.incoming),
            "premise_pressure": dict(self.premise_rows),
            "rule_id": self.rule_id,
            "target": float(self.target),
        }


def adjoint_pressure(rule, premise_values, target=1.0):
    """Reverse goal-pressure adjoint, separately typed from learning loss."""
    if not isinstance(rule, DifferentiableTruthRule):
        raise TypeError("adjoint pressure requires a differentiable rule")
    target = _unit(target, "target")
    leaves = tuple(
        ADScalar(_unit(value, premise_id), str(premise_id))
        for premise_id, value in premise_values)
    if len(leaves) != len(set(row.label for row in leaves)):
        raise ValueError("premise IDs must be unique")
    conclusion = rule.forward(leaves)
    incoming = target - conclusion.value
    gradients = conclusion.backward(seed=incoming)
    return AdjointPressure(
        rule.rule_id, conclusion.value, target, incoming,
        tuple(sorted((row.label, gradients[row.label]) for row in leaves)))


def finite_difference_adjoint(
        rule, premise_values, target=1.0, epsilon=1e-6):
    """Numerical audit of the smooth local goal-pressure adjoint."""
    epsilon = float(epsilon)
    if epsilon <= 0:
        raise ValueError("finite difference epsilon must be positive")
    identifiers = [str(row[0]) for row in premise_values]
    values = [float(row[1]) for row in premise_values]
    conclusion = rule.evaluate(values)
    incoming = _unit(target, "target") - conclusion
    rows = []
    for index, premise_id in enumerate(identifiers):
        lower = max(0.0, values[index] - epsilon)
        upper = min(1.0, values[index] + epsilon)
        left = list(values)
        right = list(values)
        left[index] = lower
        right[index] = upper
        derivative = (
            rule.evaluate(right) - rule.evaluate(left)) / (upper - lower)
        rows.append((premise_id, derivative * incoming))
    return tuple(rows)


def requirement_pressure(premise_values, incoming=1.0):
    """Symbolic AND requirement allocation, including dead-gradient gates."""
    incoming = float(incoming)
    if incoming < 0 or not math.isfinite(incoming):
        raise ValueError("incoming requirement pressure must be nonnegative")
    rows = tuple(
        (str(premise_id), max(0.0, 1.0 - _unit(value, premise_id)))
        for premise_id, value in premise_values)
    denominator = sum(value for _, value in rows)
    if denominator == 0:
        return tuple((key, 0.0) for key, _ in rows)
    return tuple(
        (key, incoming * value / denominator) for key, value in rows)


@dataclass(frozen=True)
class CounterfactualPressure:
    baseline: float
    individual_rows: tuple
    coalition_gain: float

    def to_dict(self):
        return {
            "baseline": float(self.baseline),
            "coalition_gain": float(self.coalition_gain),
            "individual_gain": dict(self.individual_rows),
        }


def counterfactual_pressure(rule, premise_values, achievable=None):
    """Finite, intervention-style goal change; no gradients are used."""
    identifiers = [str(row[0]) for row in premise_values]
    values = [float(row[1]) for row in premise_values]
    achievable = dict(achievable or ())
    baseline = rule.evaluate(values)
    rows = []
    all_changed = list(values)
    for index, premise_id in enumerate(identifiers):
        changed = list(values)
        changed[index] = _unit(
            achievable.get(premise_id, 1.0), "achievable premise")
        all_changed[index] = changed[index]
        rows.append((
            premise_id, max(0.0, rule.evaluate(changed) - baseline)))
    return CounterfactualPressure(
        baseline, tuple(rows),
        max(0.0, rule.evaluate(all_changed) - baseline))


@dataclass(frozen=True)
class ThresholdCharacterization:
    value: float
    threshold: float
    baseline: float
    adjoint_available: bool
    requirement: float
    counterfactual_gain: float

    def to_dict(self):
        return {
            "adjoint_available": bool(self.adjoint_available),
            "baseline": float(self.baseline),
            "counterfactual_gain": float(self.counterfactual_gain),
            "requirement": float(self.requirement),
            "threshold": float(self.threshold),
            "value": float(self.value),
        }


def characterize_threshold(value, threshold, achievable):
    """Explicitly characterize a discontinuous gate outside autodiff."""
    value = float(value)
    threshold = float(threshold)
    achievable = float(achievable)
    if not all(math.isfinite(row) for row in (value, threshold, achievable)):
        raise ValueError("threshold benchmark values must be finite")
    baseline = float(value >= threshold)
    changed = float(achievable >= threshold)
    return ThresholdCharacterization(
        value, threshold, baseline, False,
        max(0.0, threshold - value), max(0.0, changed - baseline))


@dataclass(frozen=True)
class LearnableRuleParameter:
    parameter_id: str
    value: float
    lower: float = 0.0
    upper: float = 1.0

    def __post_init__(self):
        if not str(self.parameter_id):
            raise ValueError("parameter ID is required")
        if (not math.isfinite(float(self.value))
                or float(self.lower) > float(self.value)
                or float(self.value) > float(self.upper)):
            raise ValueError("learnable parameter is outside bounds")


@dataclass(frozen=True)
class ParameterUpdate:
    update_id: str
    parameter_id: str
    prior_value: float
    value: float
    gradient: float
    learning_rate: float
    prior_loss: float
    posterior_loss: float
    examples: int
    method: str = "reverse-mode-mse-v1"

    def to_dict(self):
        return {
            "examples": int(self.examples),
            "gradient": float(self.gradient),
            "learning_rate": float(self.learning_rate),
            "method": self.method,
            "parameter_id": self.parameter_id,
            "posterior_loss": float(self.posterior_loss),
            "prior_loss": float(self.prior_loss),
            "prior_value": float(self.prior_value),
            "update_id": self.update_id,
            "value": float(self.value),
        }

    def emit(self, writer, turn, caused_by=()):
        return writer.emit(
            "rule_parameter_updated", turn, self.to_dict(),
            caused_by=caused_by)


def _weighted_loss(weight, examples):
    return sum(
        (weight * float(feature) - float(outcome)) ** 2
        for feature, outcome in examples) / len(examples)


def learn_rule_parameter(parameter, examples, learning_rate=0.1):
    """One bounded reverse-mode MSE step, independent of goal pressure."""
    if not isinstance(parameter, LearnableRuleParameter):
        raise TypeError("parameter learning needs LearnableRuleParameter")
    examples = tuple(
        (_unit(x, "training feature"), _unit(y, "training outcome"))
        for x, y in examples)
    if not examples:
        raise ValueError("parameter learning needs examples")
    learning_rate = float(learning_rate)
    if learning_rate <= 0 or not math.isfinite(learning_rate):
        raise ValueError("learning rate must be positive")
    weight = ADScalar(parameter.value, parameter.parameter_id)
    loss = ADScalar(0.0)
    for feature, outcome in examples:
        residual = weight * feature - outcome
        loss = loss + residual.square()
    loss = loss * (1.0 / len(examples))
    loss.backward()
    prior_loss = _weighted_loss(parameter.value, examples)
    effective_rate = learning_rate
    value = parameter.value
    posterior_loss = prior_loss
    for _ in range(32):
        candidate = min(
            parameter.upper,
            max(parameter.lower, parameter.value
                - effective_rate * weight.gradient))
        candidate_loss = _weighted_loss(candidate, examples)
        if candidate_loss <= prior_loss:
            value = candidate
            posterior_loss = candidate_loss
            break
        effective_rate *= 0.5
    material = {
        "examples": examples,
        "learning_rate": effective_rate,
        "parameter_id": parameter.parameter_id,
        "prior_value": parameter.value,
        "value": value,
    }
    update = ParameterUpdate(
        "parameter-update-" + structural_hash(material)[:24],
        parameter.parameter_id, parameter.value, value, weight.gradient,
        effective_rate, prior_loss, posterior_loss, len(examples))
    return LearnableRuleParameter(
        parameter.parameter_id, value, parameter.lower, parameter.upper), update
