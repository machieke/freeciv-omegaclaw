"""Lazy RequirementSet factors and bounded premise-support allocation."""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash
from .model import PressureRule


@dataclass(frozen=True)
class RequirementSet:
    requirement_set_id: str
    rule_id: str
    premise_ids: tuple
    role_ids: tuple
    context_digest: str
    completion_policy: str = "all"
    packet_thresholds: tuple = ()

    def __post_init__(self):
        if not self.requirement_set_id or not self.rule_id:
            raise ValueError("requirement set requires IDs")
        if not self.premise_ids:
            raise ValueError("requirement set requires premises")
        if len(set(self.premise_ids)) != len(self.premise_ids):
            raise ValueError("requirement set premises must be unique")
        if len(self.role_ids) != len(self.premise_ids):
            raise ValueError("requirement roles must match premises")
        if any(not isinstance(role, str) or not role
               for role in self.role_ids):
            raise ValueError("requirement roles must be non-empty strings")
        if not isinstance(self.context_digest, str) or not self.context_digest:
            raise ValueError("requirement context digest is required")
        if self.completion_policy != "all":
            raise ValueError(
                "the initial RequirementSet supports only all completion")
        thresholds = dict(self.packet_thresholds)
        if len(thresholds) != len(self.packet_thresholds):
            raise ValueError("packet threshold resources must be unique")
        if any(not isinstance(name, str) or not name
               or isinstance(value, bool) or not isinstance(value, int)
               or value < 0
               for name, value in self.packet_thresholds):
            raise ValueError(
                "packet thresholds require non-negative integer quanta")

    def threshold_for(self, premise_id):
        if premise_id not in self.premise_ids:
            raise KeyError("unknown requirement premise {}".format(
                premise_id))
        return int(dict(self.packet_thresholds).get(premise_id, 1))

    def complete(self, premise_packets):
        premise_packets = dict(premise_packets)
        return all(
            int(premise_packets.get(premise_id, 0))
            >= self.threshold_for(premise_id)
            for premise_id in self.premise_ids)

    def to_dict(self):
        return {
            "completion_policy": self.completion_policy,
            "context_digest": self.context_digest,
            "packet_thresholds": dict(self.packet_thresholds),
            "premise_ids": list(self.premise_ids),
            "requirement_set_id": self.requirement_set_id,
            "role_ids": list(self.role_ids),
            "rule_id": self.rule_id,
        }


@dataclass(frozen=True)
class FactorDemand:
    goal_id: str
    factor_id: str
    amount: float
    residual: float
    conductance: float
    compatibility: float
    demand_component: str = "achievement"

    def __post_init__(self):
        if not self.goal_id or not self.factor_id:
            raise ValueError("factor demand requires goal and factor IDs")
        for name in (
                "amount", "residual", "conductance", "compatibility"):
            value = float(getattr(self, name))
            if value < 0.0 or not math.isfinite(value):
                raise ValueError(
                    "{} must be finite and non-negative".format(name))
        for name in ("residual", "conductance", "compatibility"):
            if float(getattr(self, name)) > 1.0:
                raise ValueError("{} must be at most one".format(name))
        if self.demand_component not in (
                "achievement", "epistemic", "deadline", "safety"):
            raise ValueError("unknown factor demand component")

    def to_dict(self):
        return {
            "amount": float(self.amount),
            "compatibility": float(self.compatibility),
            "conductance": float(self.conductance),
            "demand_component": self.demand_component,
            "factor_id": self.factor_id,
            "goal_id": self.goal_id,
            "residual": float(self.residual),
        }


@dataclass(frozen=True)
class PremiseSupportRequest:
    requirement_set_id: str
    premise_id: str
    share: float
    requested_amount: float
    goal_id: str = ""
    demand_component: str = "achievement"

    def __post_init__(self):
        if not self.requirement_set_id or not self.premise_id:
            raise ValueError(
                "premise support requires requirement and premise IDs")
        if not 0.0 <= float(self.share) <= 1.0:
            raise ValueError("premise support share must be in [0,1]")
        if (float(self.requested_amount) < 0.0
                or not math.isfinite(float(self.requested_amount))):
            raise ValueError(
                "premise requested amount must be finite and non-negative")

    def to_dict(self):
        return {
            "demand_component": self.demand_component,
            "goal_id": self.goal_id,
            "premise_id": self.premise_id,
            "requested_amount": float(self.requested_amount),
            "requirement_set_id": self.requirement_set_id,
            "share": float(self.share),
        }


def requirement_set_for_rule(
        rule, context_digest=None, role_ids=(),
        packet_thresholds=()):
    """Materialize at most one explicit coalition for one AND rule."""
    if not isinstance(rule, PressureRule):
        raise TypeError("requirement set source must be PressureRule")
    if rule.kind != "and":
        return None
    context_digest = context_digest or structural_hash({
        "context_guard": list(rule.context_guard),
        "rule_id": rule.rule_id,
    })
    roles = tuple(role_ids) or tuple(
        "premise:{}".format(premise_id)
        for premise_id in rule.premise_ids)
    material = {
        "context_digest": context_digest,
        "premise_ids": list(rule.premise_ids),
        "role_ids": list(roles),
        "rule_id": rule.rule_id,
    }
    return RequirementSet(
        requirement_set_id="requirement-set:{}".format(
            structural_hash(material)[:24]),
        rule_id=rule.rule_id,
        premise_ids=tuple(rule.premise_ids),
        role_ids=roles,
        context_digest=context_digest,
        packet_thresholds=tuple(packet_thresholds))


def premise_support_requests(
        requirement_set, parent_demand, raw_weights=None,
        exploration_floor=0.05, goal_id="",
        demand_component="achievement"):
    """Allocate bounded attention while retaining full factor demand."""
    if not isinstance(requirement_set, RequirementSet):
        raise TypeError("premise support requires RequirementSet")
    amount = float(parent_demand)
    if amount < 0.0:
        raise ValueError("parent demand must be non-negative")
    floor = float(exploration_floor)
    if not 0.0 <= floor <= 1.0:
        raise ValueError("exploration floor must be in [0,1]")
    weights = (
        tuple(float(value) for value in raw_weights)
        if raw_weights is not None else
        tuple(1.0 for _ in requirement_set.premise_ids))
    if (len(weights) != len(requirement_set.premise_ids)
            or any(value < 0.0 for value in weights)):
        raise ValueError("support weights must match premises")
    if not any(weights):
        weights = tuple(1.0 for _ in weights)
    total = sum(weights)
    uniform = floor / len(weights)
    shares = tuple(
        (1.0 - floor) * value / total + uniform
        for value in weights)
    return tuple(
        PremiseSupportRequest(
            requirement_set.requirement_set_id,
            premise_id, share, amount * share,
            str(goal_id), str(demand_component))
        for premise_id, share in zip(
            requirement_set.premise_ids, shares))
