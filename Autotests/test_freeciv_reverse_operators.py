"""Composite reverse-operator semantic and numerical safety gates."""

import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import freeciv_agent.pressure.reverse_operators as reverse_module  # noqa: E402
from freeciv_agent.pressure import (  # noqa: E402
    AdjointReverseOperator,
    AtomState,
    CompositeReverseOperator,
    FactorDemand,
    PressureGraph,
    PressureRule,
    ReverseContext,
    TruthState,
    requirement_set_for_rule,
)


def _fixture(
        values=(("a", 0.5), ("b", 0.75)),
        kind="and", source=None):
    graph = PressureGraph()
    for premise_id, value in values:
        graph.add_atom(
            AtomState(premise_id, TruthState(value, 1.0)))
    graph.add_atom(
        AtomState("conclusion", TruthState(0.0, 1.0)))
    rule = PressureRule(
        "rule", tuple(key for key, _ in values), "conclusion",
        kind=kind, causal_kind="procedural",
        source=source)
    graph.add_rule(rule)
    incoming = FactorDemand(
        "goal", "rule", 4.0, 1.0, 1.0, 1.0)
    return graph, rule, incoming


def test_smooth_rule_uses_adjoint_when_audit_passes():
    graph, rule, incoming = _fixture(
        source={"smooth": True})

    result = CompositeReverseOperator().evaluate(
        rule, incoming, graph)

    assert result.numerical_health == "healthy"
    assert any(
        row.operator_id == "adjoint/1.0"
        for row in result.component_contributions)
    assert abs(sum(
        row.share for row in result.premise_requests) - 1.0) < 1e-12


def test_dead_and_uses_requirement_not_zero_gradient():
    graph, rule, incoming = _fixture(
        values=(("a", 0.0), ("b", 0.0)),
        source={"smooth": True})

    result = CompositeReverseOperator().evaluate(
        rule, incoming, graph)

    assert result.numerical_health == "healthy"
    assert any(
        row.operator_id == "requirement/1.0"
        for row in result.component_contributions)
    assert dict(result.premise_shares) == {
        "a": 0.5, "b": 0.5}


def test_threshold_uses_counterfactual_or_requirement():
    graph, rule, incoming = _fixture(
        values=(("a", 0.4), ("b", 1.0)),
        source={"threshold": 0.8})
    context = ReverseContext(
        situation="threshold",
        achievable=(("a", 0.9),),
        threshold=0.8,
        threshold_premise_id="a")

    result = CompositeReverseOperator().evaluate(
        rule, incoming, graph, context)

    operators = {
        row.operator_id for row in result.component_contributions}
    assert "counterfactual/1.0" in operators
    assert "requirement/1.0" in operators
    assert dict(result.premise_shares)["a"] > 0.5


def test_operator_components_are_normalized_before_mixing():
    graph, rule, incoming = _fixture(
        kind="or",
        source={"smooth": True})
    composite = CompositeReverseOperator({
        "smooth": (("adjoint", 3.0), ("counterfactual", 1.0)),
    })

    result = composite.evaluate(rule, incoming, graph)

    weights = {
        row.operator_id: row.effective_weight
        for row in result.component_contributions}
    assert weights == {
        "adjoint/1.0": 0.75,
        "counterfactual/1.0": 0.25,
    }
    assert abs(sum(dict(result.premise_shares).values()) - 1.0) < 1e-12
    assert abs(sum(
        row.requested_amount for row in result.premise_requests)
        - incoming.amount) < 1e-12


def test_failed_adjoint_audit_falls_back_safely(monkeypatch):
    graph, rule, incoming = _fixture(
        source={"smooth": True})
    monkeypatch.setattr(
        reverse_module,
        "finite_difference_adjoint",
        lambda *args, **kwargs: (("a", 100.0), ("b", 100.0)))

    result = CompositeReverseOperator().evaluate(
        rule, incoming, graph)

    assert result.numerical_health == "fallback"
    assert "symbolic-requirement-fallback" in result.assumptions
    assert any(
        row.operator_id == "requirement/1.0"
        for row in result.component_contributions)


def test_reverse_operator_result_never_updates_truth():
    graph, rule, incoming = _fixture(
        source={"smooth": True})
    before = tuple(
        (atom.atom_id, atom.truth) for atom in graph.atoms)

    AdjointReverseOperator().evaluate(
        rule, incoming, graph, ReverseContext())
    CompositeReverseOperator().evaluate(
        rule, incoming, graph)

    after = tuple(
        (atom.atom_id, atom.truth) for atom in graph.atoms)
    assert after == before


def test_reverse_operator_accepts_engine_requirement_factor_identity():
    graph, rule, _ = _fixture(source={"smooth": True})
    requirement_set = requirement_set_for_rule(rule)
    incoming = FactorDemand(
        "goal", requirement_set.requirement_set_id,
        4.0, 1.0, 1.0, 1.0)

    result = CompositeReverseOperator().evaluate(
        rule, incoming, graph)

    assert result.premise_requests
