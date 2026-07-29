"""Belief, attention, and action explanations remain type-separated."""

import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (  # noqa: E402
    BeliefExplanation,
    DecisionExplainer,
    ImpactControlAdapter,
)
from Autotests.test_freeciv_advisory_control import (  # noqa: E402
    _ScalarRanker,
    _Snapshot,
    _candidates,
)


def _decision():
    snapshot = _Snapshot()
    adapter = ImpactControlAdapter(
        scalar_v2_ranker=_ScalarRanker())
    query = adapter.build_query(
        snapshot, _candidates(), 5, 40, 6,
        {"survival": {}, "expansion": {}},
        normalization_contract_hash="normalization-v1",
        ruleset_digest="ruleset-v1")
    return query, adapter.rank_or_schedule(
        query, "scalar_v2")


def test_belief_explanation_contains_only_epistemic_ancestry():
    explainer = DecisionExplainer()
    belief = explainer.register_belief(
        BeliefExplanation(
            semantic_id="atom:capital-safe",
            evidence_tokens=("observation:1",),
            truth_formula={"strength": 0.9, "confidence": 0.8},
            committed_proof_path=({
                "edge_kind": "deduction",
                "rule_id": "defense-rule",
            },),
            assumptions=("same-context",),
            contexts=("capital:1",),
            confidence=0.8,
            uncertainty=0.2,
            overlap_handling="deduplicated",
            conflict_handling="none"))

    result = explainer.belief_explanation(
        "atom:capital-safe")
    assert result == belief
    assert result.epistemic_authority
    assert "attention" not in str(
        result.to_dict()).lower()


@pytest.mark.parametrize("leak", (
    {"probe_support": 0.9},
    {"controller_score": 4.0},
    {"edge_kind": "resource_return"},
    {"flow_mass": 0.5},
))
def test_belief_explanation_rejects_control_telemetry(leak):
    with pytest.raises(
            ValueError,
            match="control-only material"):
        BeliefExplanation(
            semantic_id="atom:x",
            evidence_tokens=(leak,),
            truth_formula={"strength": 0.5},
            committed_proof_path=(),
            assumptions=(),
            contexts=(),
            confidence=0.5,
            uncertainty=0.5,
            overlap_handling=None,
            conflict_handling=None)


def test_attention_is_non_evidential_and_action_is_non_authoritative():
    query, decision = _decision()
    explainer = DecisionExplainer()
    decision_id = explainer.register_decision(
        query, decision,
        attention_fields={
            "cost_to_go": {"survival": 0.2},
            "bridge_factors": {
                "forward": 0.8, "backward": 0.9},
            "probe_support": {
                "count": 32, "ess": 28.0},
            "attention_summary": {"mass": 1.0},
            "congestion_summary": {"cpu": 0.1},
        },
        action_fields={
            "risk": {"cvar": 0.03},
            "deadline": {"fit": 0.95},
            "costs": {"cpu": 1},
            "safety_gates": {"passed": True},
            "provenance_gates": {"passed": True},
        })

    attention = explainer.attention_explanation(
        decision_id)
    action = explainer.action_explanation(decision_id)
    assert not attention.evidential_authority
    assert attention.probe_support["ess"] == 28.0
    assert not action.execution_authority
    assert action.candidate_key == (
        decision.selected_candidate_key)
    assert action.authoritative_grounding[
        "action"]["actor_id"] == 1
    assert "packet_use" in action.to_dict()
    assert action.fallback_chain == ()


def test_three_ledgers_do_not_cross_resolve_identifiers():
    query, decision = _decision()
    explainer = DecisionExplainer()
    decision_id = explainer.register_decision(
        query, decision)
    assert explainer.belief_explanation(
        decision_id) is None
    assert explainer.attention_explanation(
        "atom:not-a-decision") is None
    assert explainer.action_explanation(
        "atom:not-a-decision") is None
