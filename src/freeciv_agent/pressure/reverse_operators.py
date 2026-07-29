"""Composite rule-local reverse operators for teleological demand.

The operators read truth and topology but return control requests only.  The
composite mixes normalized components into one request vector so adjoint,
requirement, counterfactual, and information signals cannot be double-counted.
"""

import math
from dataclasses import dataclass

from .coalitions import (
    FactorDemand,
    PremiseSupportRequest,
    premise_support_requests,
    requirement_set_for_rule,
)
from .differentiable import (
    DifferentiableTruthRule,
    adjoint_pressure,
    counterfactual_pressure,
    finite_difference_adjoint,
    requirement_pressure,
)
from .engine import PressureGraph
from .model import PressureRule


NUMERICAL_HEALTH = frozenset((
    "healthy", "fallback", "unhealthy"))


def _finite_nonnegative(value, name):
    value = float(value)
    if value < 0.0 or not math.isfinite(value):
        raise ValueError(
            "{} must be finite and non-negative".format(name))
    return value


def _named_nonnegative_rows(rows, name):
    result = []
    keys = []
    for row in tuple(rows):
        if not isinstance(row, tuple) or len(row) != 2:
            raise TypeError(
                "{} rows must be (name, value) tuples".format(name))
        key, value = row
        if not isinstance(key, str) or not key:
            raise ValueError(
                "{} names must be non-empty strings".format(name))
        result.append((
            key, _finite_nonnegative(
                value, "{} value".format(name))))
        keys.append(key)
    if len(keys) != len(set(keys)):
        raise ValueError("{} names must be unique".format(name))
    return tuple(result)


def _normalized_rows(rows, keys=()):
    """Return deterministic nonnegative rows summing to one."""
    values = dict(_named_nonnegative_rows(rows, "operator contribution"))
    identifiers = tuple(sorted(
        set(str(value) for value in keys) | set(values)))
    if not identifiers:
        return ()
    denominator = sum(values.get(key, 0.0) for key in identifiers)
    if denominator <= 0.0:
        return ()
    return tuple(
        (key, values.get(key, 0.0) / denominator)
        for key in identifiers)


def _requests(rule, incoming, shares, requirement_set_id=None):
    shares = _normalized_rows(shares, rule.premise_ids)
    if not shares:
        return ()
    request_id = (
        requirement_set_id
        or "reverse-request:{}".format(rule.rule_id))
    return tuple(
        PremiseSupportRequest(
            requirement_set_id=request_id,
            premise_id=premise_id,
            share=share,
            requested_amount=float(incoming.amount) * share,
            goal_id=incoming.goal_id,
            demand_component=incoming.demand_component)
        for premise_id, share in shares)


@dataclass(frozen=True)
class InformationRequest:
    premise_id: str
    expected_decision_value: float
    share: float
    requested_amount: float
    provenance: tuple

    def __post_init__(self):
        if not isinstance(self.premise_id, str) or not self.premise_id:
            raise ValueError("information request requires premise ID")
        _finite_nonnegative(
            self.expected_decision_value,
            "expected decision value")
        share = _finite_nonnegative(self.share, "information share")
        if share > 1.0:
            raise ValueError("information share must be in [0,1]")
        _finite_nonnegative(
            self.requested_amount,
            "information requested amount")
        if not self.provenance or any(
                not isinstance(value, str) or not value
                for value in self.provenance):
            raise ValueError(
                "information request requires provenance")

    def to_dict(self):
        return {
            "expected_decision_value": float(
                self.expected_decision_value),
            "premise_id": self.premise_id,
            "provenance": list(self.provenance),
            "requested_amount": float(self.requested_amount),
            "share": float(self.share),
        }


@dataclass(frozen=True)
class ReverseComponentContribution:
    operator_id: str
    configured_weight: float
    effective_weight: float
    premise_shares: tuple
    numerical_health: str
    assumptions: tuple

    def __post_init__(self):
        if not isinstance(self.operator_id, str) or not self.operator_id:
            raise ValueError("reverse component requires operator ID")
        _finite_nonnegative(
            self.configured_weight, "configured operator weight")
        effective = _finite_nonnegative(
            self.effective_weight, "effective operator weight")
        if effective > 1.0:
            raise ValueError(
                "effective operator weight must be in [0,1]")
        _named_nonnegative_rows(
            self.premise_shares, "component premise share")
        if self.numerical_health not in NUMERICAL_HEALTH:
            raise ValueError("unknown reverse numerical health")

    def to_dict(self):
        return {
            "assumptions": list(self.assumptions),
            "configured_weight": float(self.configured_weight),
            "effective_weight": float(self.effective_weight),
            "numerical_health": self.numerical_health,
            "operator_id": self.operator_id,
            "premise_shares": dict(self.premise_shares),
        }


@dataclass(frozen=True)
class ReverseContext:
    """Declared rule-local context; all fields are read-only control data."""

    situation: str = "auto"
    target_strength: float = 1.0
    achievable: tuple = ()
    information_values: tuple = ()
    information_provenance: tuple = ("declared-decision-value",)
    differentiable_kind: object = None
    audit_tolerance: float = 1e-5
    audit_enabled: bool = True
    threshold: object = None
    threshold_premise_id: object = None

    def __post_init__(self):
        if self.situation not in (
                "auto", "smooth", "hard-and", "threshold",
                "lifecycle", "observation", "alternative-routes",
                "expansion"):
            raise ValueError("unknown reverse-operator situation")
        value = float(self.target_strength)
        if not 0.0 <= value <= 1.0 or not math.isfinite(value):
            raise ValueError("reverse target strength must be in [0,1]")
        _named_nonnegative_rows(self.achievable, "achievable premise")
        if any(float(value) > 1.0 for _, value in self.achievable):
            raise ValueError("achievable premise values must be in [0,1]")
        _named_nonnegative_rows(
            self.information_values, "information value")
        if any(not isinstance(value, str) or not value
               for value in self.information_provenance):
            raise ValueError(
                "information provenance must contain strings")
        if self.differentiable_kind not in (
                None, "product-and", "probabilistic-or"):
            raise ValueError("unknown differentiable rule kind")
        _finite_nonnegative(
            self.audit_tolerance, "adjoint audit tolerance")
        if not isinstance(self.audit_enabled, bool):
            raise TypeError("adjoint audit flag must be boolean")
        if self.threshold is not None:
            value = float(self.threshold)
            if not 0.0 <= value <= 1.0 or not math.isfinite(value):
                raise ValueError("threshold must be in [0,1]")
        if (self.threshold_premise_id is not None
                and (not isinstance(self.threshold_premise_id, str)
                     or not self.threshold_premise_id)):
            raise ValueError(
                "threshold premise ID must be a non-empty string")


@dataclass(frozen=True)
class ReverseOperatorResult:
    premise_requests: tuple
    rule_request: float
    requirement_sets: tuple
    information_requests: tuple
    assumptions: tuple
    numerical_health: str
    component_contributions: tuple = ()
    operator_id: str = ""

    def __post_init__(self):
        if any(not isinstance(row, PremiseSupportRequest)
               for row in self.premise_requests):
            raise TypeError(
                "reverse premise requests must contain "
                "PremiseSupportRequest")
        premise_ids = [row.premise_id for row in self.premise_requests]
        if len(premise_ids) != len(set(premise_ids)):
            raise ValueError(
                "reverse result must contain one request per premise")
        total_share = sum(
            float(row.share) for row in self.premise_requests)
        if self.premise_requests and abs(total_share - 1.0) > 1e-9:
            raise ValueError(
                "reverse premise request shares must sum to one")
        _finite_nonnegative(self.rule_request, "rule request")
        from .coalitions import RequirementSet
        if any(not isinstance(row, RequirementSet)
               for row in self.requirement_sets):
            raise TypeError(
                "reverse requirement sets must contain RequirementSet")
        if any(not isinstance(row, InformationRequest)
               for row in self.information_requests):
            raise TypeError(
                "reverse information requests must contain "
                "InformationRequest")
        if any(not isinstance(value, str) or not value
               for value in self.assumptions):
            raise ValueError(
                "reverse assumptions must contain strings")
        if self.numerical_health not in NUMERICAL_HEALTH:
            raise ValueError("unknown reverse numerical health")
        if any(not isinstance(row, ReverseComponentContribution)
               for row in self.component_contributions):
            raise TypeError(
                "reverse components must contain "
                "ReverseComponentContribution")
        if self.operator_id and not isinstance(self.operator_id, str):
            raise TypeError("reverse operator ID must be a string")

    @property
    def premise_shares(self):
        return tuple(
            (row.premise_id, float(row.share))
            for row in self.premise_requests)

    def to_dict(self):
        return {
            "assumptions": list(self.assumptions),
            "component_contributions": [
                row.to_dict()
                for row in self.component_contributions],
            "information_requests": [
                row.to_dict()
                for row in self.information_requests],
            "numerical_health": self.numerical_health,
            "operator_id": self.operator_id,
            "premise_requests": [
                row.to_dict() for row in self.premise_requests],
            "requirement_sets": [
                row.to_dict() for row in self.requirement_sets],
            "rule_request": float(self.rule_request),
        }


class RequirementReverseOperator:
    operator_id = "requirement/1.0"

    def evaluate(self, rule, incoming, graph, context):
        _validate_inputs(rule, incoming, graph, context)
        values = _premise_values(rule, graph)
        shares = _normalized_rows(
            requirement_pressure(values, incoming=1.0),
            rule.premise_ids)
        if not shares:
            shares = tuple(
                (premise_id, 1.0 / len(rule.premise_ids))
                for premise_id in sorted(rule.premise_ids))
        requirement_set = requirement_set_for_rule(rule)
        requests = (
            premise_support_requests(
                requirement_set,
                incoming.amount,
                raw_weights=tuple(
                    dict(shares)[premise_id]
                    for premise_id in requirement_set.premise_ids),
                exploration_floor=0.0,
                goal_id=incoming.goal_id,
                demand_component=incoming.demand_component)
            if requirement_set is not None else
            _requests(rule, incoming, shares))
        return ReverseOperatorResult(
            premise_requests=requests,
            rule_request=(
                float(incoming.amount)
                * max(0.0, 1.0 - float(rule.conductance))),
            requirement_sets=(
                () if requirement_set is None
                else (requirement_set,)),
            information_requests=(),
            assumptions=("symbolic-requirement-semantics",),
            numerical_health="healthy",
            operator_id=self.operator_id)


class AdjointReverseOperator:
    operator_id = "adjoint/1.0"

    def evaluate(self, rule, incoming, graph, context):
        _validate_inputs(rule, incoming, graph, context)
        kind = _differentiable_kind(rule, context)
        if kind is None:
            return _unhealthy(
                self.operator_id, "rule-not-declared-smooth")
        differentiable = DifferentiableTruthRule(
            rule.rule_id, kind)
        values = _premise_values(rule, graph)
        adjoint = adjoint_pressure(
            differentiable, values,
            target=context.target_strength)
        raw = tuple(
            (premise_id, max(0.0, float(value)))
            for premise_id, value in adjoint.premise_rows)
        if context.audit_enabled:
            audit = finite_difference_adjoint(
                differentiable, values,
                target=context.target_strength)
            errors = tuple(
                abs(dict(raw).get(key, 0.0) - max(0.0, float(value)))
                for key, value in audit)
            if errors and max(errors) > float(context.audit_tolerance):
                return _unhealthy(
                    self.operator_id,
                    "finite-difference-audit-failed")
        shares = _normalized_rows(raw, rule.premise_ids)
        if not shares:
            return _unhealthy(
                self.operator_id, "zero-or-dead-gradient")
        return ReverseOperatorResult(
            premise_requests=_requests(
                rule, incoming, shares),
            rule_request=0.0,
            requirement_sets=(),
            information_requests=(),
            assumptions=(
                "smooth-truth-function:{}".format(kind),
                "finite-difference-audited"
                if context.audit_enabled else
                "audit-disabled"),
            numerical_health="healthy",
            operator_id=self.operator_id)


class CounterfactualReverseOperator:
    operator_id = "counterfactual/1.0"

    def evaluate(self, rule, incoming, graph, context):
        _validate_inputs(rule, incoming, graph, context)
        values = _premise_values(rule, graph)
        if context.situation in ("threshold", "lifecycle"):
            premise_id = (
                context.threshold_premise_id
                or min(rule.premise_ids))
            if premise_id not in rule.premise_ids:
                return _unhealthy(
                    self.operator_id,
                    "threshold-premise-not-in-rule")
            baseline = dict(values)[premise_id]
            achievable = dict(context.achievable).get(
                premise_id, 1.0)
            source = (
                rule.source
                if isinstance(rule.source, dict) else {})
            threshold = (
                float(context.threshold)
                if context.threshold is not None else
                float(source.get("threshold", 1.0)))
            gain = float(
                baseline < threshold <= achievable)
            if gain <= 0.0:
                return _unhealthy(
                    self.operator_id,
                    "threshold-not-achievable")
            shares = ((premise_id, 1.0),)
            assumption = "threshold-intervention"
        else:
            kind = _differentiable_kind(rule, context)
            if kind is None:
                return _unhealthy(
                    self.operator_id,
                    "counterfactual-evaluator-unavailable")
            differentiable = DifferentiableTruthRule(
                rule.rule_id, kind)
            counterfactual = counterfactual_pressure(
                differentiable, values,
                achievable=context.achievable)
            shares = _normalized_rows(
                counterfactual.individual_rows,
                rule.premise_ids)
            if not shares:
                return _unhealthy(
                    self.operator_id,
                    "no-individual-achievable-gain")
            assumption = "achievable-one-step-intervention"
        return ReverseOperatorResult(
            premise_requests=_requests(
                rule, incoming, shares),
            rule_request=0.0,
            requirement_sets=(),
            information_requests=(),
            assumptions=(assumption,),
            numerical_health="healthy",
            operator_id=self.operator_id)


class InformationReverseOperator:
    operator_id = "information/1.0"

    def evaluate(self, rule, incoming, graph, context):
        _validate_inputs(rule, incoming, graph, context)
        values = tuple(
            (key, value) for key, value in context.information_values
            if key in rule.premise_ids)
        shares = _normalized_rows(values, rule.premise_ids)
        if not shares:
            return _unhealthy(
                self.operator_id,
                "no-positive-decision-relevant-information-value")
        value_by_id = dict(values)
        information_requests = tuple(
            InformationRequest(
                premise_id=premise_id,
                expected_decision_value=value_by_id.get(
                    premise_id, 0.0),
                share=share,
                requested_amount=float(incoming.amount) * share,
                provenance=context.information_provenance)
            for premise_id, share in shares)
        return ReverseOperatorResult(
            premise_requests=_requests(
                rule, incoming, shares),
            rule_request=0.0,
            requirement_sets=(),
            information_requests=information_requests,
            assumptions=(
                "expected-decision-value-not-entropy-alone",),
            numerical_health="healthy",
            operator_id=self.operator_id)


class CompositeReverseOperator:
    """Situation-aware normalized mixture with symbolic safe fallback."""

    operator_id = "composite-reverse/1.0"
    DEFAULT_MIXTURES = {
        "smooth": (("adjoint", 0.8), ("counterfactual", 0.2)),
        "hard-and": (
            ("requirement", 0.7), ("counterfactual", 0.3)),
        "threshold": (
            ("counterfactual", 0.6), ("requirement", 0.4)),
        "lifecycle": (
            ("counterfactual", 0.6), ("requirement", 0.4)),
        "observation": (
            ("information", 0.8), ("counterfactual", 0.2)),
        "alternative-routes": (
            ("counterfactual", 0.7), ("requirement", 0.3)),
        "expansion": (
            ("information", 0.7), ("requirement", 0.3)),
        "default": (("requirement", 1.0),),
    }

    def __init__(self, mixture_by_situation=None):
        self.operators = {
            "adjoint": AdjointReverseOperator(),
            "counterfactual": CounterfactualReverseOperator(),
            "information": InformationReverseOperator(),
            "requirement": RequirementReverseOperator(),
        }
        declared = dict(self.DEFAULT_MIXTURES)
        if mixture_by_situation is not None:
            declared.update(dict(mixture_by_situation))
        self.mixture_by_situation = {}
        for situation, mixture in declared.items():
            rows = _named_nonnegative_rows(
                mixture, "operator mixture")
            if not rows or sum(value for _, value in rows) <= 0.0:
                raise ValueError(
                    "operator mixture requires positive weight")
            if any(name not in self.operators for name, _ in rows):
                raise ValueError(
                    "operator mixture references unknown operator")
            self.mixture_by_situation[str(situation)] = rows

    @staticmethod
    def _situation(rule, graph, context):
        if context.situation != "auto":
            return context.situation
        source = rule.source if isinstance(rule.source, dict) else {}
        declared = source.get("reverse_situation")
        if declared:
            return str(declared)
        if source.get("observation_dependent"):
            return "observation"
        if source.get("lifecycle_transition"):
            return "lifecycle"
        if source.get("threshold") is not None:
            return "threshold"
        if _differentiable_kind(rule, context) is not None:
            values = dict(_premise_values(rule, graph))
            if rule.kind == "and" and any(
                    value <= 0.0 for value in values.values()):
                return "hard-and"
            return "smooth"
        if rule.kind == "and":
            return "hard-and"
        if rule.kind == "or":
            return "alternative-routes"
        return "default"

    def evaluate(self, rule, incoming, graph, context=None):
        context = context or ReverseContext()
        _validate_inputs(rule, incoming, graph, context)
        situation = self._situation(
            rule, graph, context)
        mixture = self.mixture_by_situation.get(
            situation, self.mixture_by_situation["default"])
        evaluated = []
        invalid_assumptions = []
        for name, weight in mixture:
            result = self.operators[name].evaluate(
                rule, incoming, graph, context)
            if (result.numerical_health == "healthy"
                    and result.premise_requests):
                evaluated.append((name, weight, result))
            else:
                invalid_assumptions.extend(
                    "{}:{}".format(name, value)
                    for value in result.assumptions)
        used_fallback = False
        if not evaluated:
            fallback = self.operators["requirement"].evaluate(
                rule, incoming, graph, context)
            evaluated = (("requirement", 1.0, fallback),)
            used_fallback = True
        elif any(
                name == "adjoint" for name, _ in mixture
                ) and not any(name == "adjoint"
                              for name, _, _ in evaluated):
            # An unhealthy adjoint always introduces symbolic requirement
            # semantics, even if the audit-only counterfactual survived.
            fallback = self.operators["requirement"].evaluate(
                rule, incoming, graph, context)
            evaluated = tuple(evaluated) + (
                ("requirement", max(
                    weight for _, weight in mixture), fallback),)
            used_fallback = True
        weight_total = sum(weight for _, weight, _ in evaluated)
        effective = tuple(
            (name, weight, weight / weight_total, result)
            for name, weight, result in evaluated)
        combined = dict(
            (premise_id, 0.0)
            for premise_id in rule.premise_ids)
        components = []
        requirement_sets = {}
        information_requests = {}
        rule_request = 0.0
        assumptions = []
        for name, configured, effective_weight, result in effective:
            shares = result.premise_shares
            for premise_id, share in shares:
                combined[premise_id] += effective_weight * share
            rule_request += effective_weight * result.rule_request
            for requirement_set in result.requirement_sets:
                requirement_sets[
                    requirement_set.requirement_set_id
                ] = requirement_set
            for request in result.information_requests:
                existing = information_requests.get(request.premise_id)
                information_requests[request.premise_id] = (
                    request if existing is None else
                    InformationRequest(
                        request.premise_id,
                        max(
                            existing.expected_decision_value,
                            request.expected_decision_value),
                        existing.share + request.share,
                        existing.requested_amount
                        + request.requested_amount,
                        tuple(sorted(set(
                            existing.provenance
                            + request.provenance)))))
            assumptions.extend(result.assumptions)
            components.append(ReverseComponentContribution(
                operator_id=result.operator_id,
                configured_weight=configured,
                effective_weight=effective_weight,
                premise_shares=shares,
                numerical_health=result.numerical_health,
                assumptions=result.assumptions))
        final_shares = _normalized_rows(
            tuple(combined.items()), rule.premise_ids)
        final_requests = _requests(
            rule, incoming, final_shares,
            requirement_set_id=(
                next(iter(sorted(requirement_sets)))
                if len(requirement_sets) == 1 else None))
        assumptions.extend(invalid_assumptions)
        assumptions.append(
            "single-normalized-composite-request")
        if used_fallback:
            assumptions.append("symbolic-requirement-fallback")
        return ReverseOperatorResult(
            premise_requests=final_requests,
            rule_request=rule_request,
            requirement_sets=tuple(
                requirement_sets[key]
                for key in sorted(requirement_sets)),
            information_requests=tuple(
                information_requests[key]
                for key in sorted(information_requests)),
            assumptions=tuple(sorted(set(assumptions))),
            numerical_health=(
                "fallback" if used_fallback else "healthy"),
            component_contributions=tuple(components),
            operator_id=self.operator_id)


def _validate_inputs(rule, incoming, graph, context):
    if not isinstance(rule, PressureRule):
        raise TypeError("reverse operator requires PressureRule")
    if not isinstance(incoming, FactorDemand):
        raise TypeError("reverse operator requires FactorDemand")
    if not isinstance(graph, PressureGraph):
        raise TypeError("reverse operator requires PressureGraph")
    if not isinstance(context, ReverseContext):
        raise TypeError("reverse operator requires ReverseContext")
    requirement_set = requirement_set_for_rule(rule)
    valid_factor_ids = {
        rule.rule_id,
        requirement_set.requirement_set_id
        if requirement_set is not None else rule.rule_id,
    }
    if incoming.factor_id not in valid_factor_ids:
        source = rule.source if isinstance(rule.source, dict) else {}
        if not source.get("allow_factor_alias", False):
            raise ValueError(
                "incoming factor ID must match reverse rule ID")
    for premise_id in rule.premise_ids:
        graph.atom(premise_id)


def _premise_values(rule, graph):
    return tuple(
        (premise_id, float(graph.atom(premise_id).truth.strength))
        for premise_id in rule.premise_ids)


def _differentiable_kind(rule, context):
    if context.differentiable_kind is not None:
        return context.differentiable_kind
    source = rule.source if isinstance(rule.source, dict) else {}
    declared = source.get("differentiable_kind")
    if declared in ("product-and", "probabilistic-or"):
        return declared
    if source.get("smooth") is True:
        if rule.kind == "and":
            return "product-and"
        if rule.kind == "or":
            return "probabilistic-or"
    return None


def _unhealthy(operator_id, reason):
    return ReverseOperatorResult(
        premise_requests=(),
        rule_request=0.0,
        requirement_sets=(),
        information_requests=(),
        assumptions=(str(reason),),
        numerical_health="unhealthy",
        operator_id=operator_id)
