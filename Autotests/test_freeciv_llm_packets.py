"""Engine-live pressure-gated LLM compound-packet gates."""

import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.llm import (  # noqa: E402
    GatewayPacketLedger,
    GatewayRequest,
    PressureLLMGateway,
    QuarantinePolicy,
    TokenBudgetLedger,
    ValidationPlan,
)
from freeciv_agent.pressure import (  # noqa: E402
    AtomState,
    ConductanceState,
    GoalState,
    PacketBudget,
    PressureEngine,
    PressureGraph,
    Resolvability,
    ResourceKind,
    TruthState,
)


class Proposal:
    def to_dict(self):
        return {
            "proposal_id": "proposal",
            "schema_version": "1.0",
        }


class Proposer:
    def input_document(self, *args, **kwargs):
        return {"typed": "document"}

    def propose(self, *args, **kwargs):
        return Proposal(), 0


def _pressure(expand=1.0):
    graph = PressureGraph()
    graph.add_atom(
        AtomState("gap", TruthState(0.0, 1.0, crisp=True)),
        Resolvability(expand=expand))
    return PressureEngine().propagate(
        graph, (GoalState("goal", "gap"),))


def _request(request_id="request"):
    return GatewayRequest(
        request_id=request_id,
        goal_id="goal",
        atom_id="gap",
        context=(("ruleset", "civ2civ3"),),
        known_rule_ids=("rule:known",),
        unresolved_premise_ids=("premise:missing",),
        forbidden_assumption_ids=("assumption:omniscience",),
        action_budget=1,
        time_budget_seconds=5.0,
        expected_relief=0.8,
        useful_proposal_probability=0.7,
        token_limit=256,
        latency_cost=0.1,
        token_cost=0.001,
        validation_plan=ValidationPlan(
            ("formal-type-check",), 0.2),
        requested_schema_id="freeciv-expansion/1.0",
        alternative_expected_relief=(
            ("known-rule", 0.05),
            ("observation", 0.10),
            ("retrieval", 0.05),
            ("simulation", 0.15),
        ),
        expected_rejection_cost=0.3,
        evidence_dependencies=("state:turn-4",),
        quarantine_policy=QuarantinePolicy(
            0.2, expiration_turns=8,
            maximum_retries=2, retry_backoff_turns=3))


def _gateway():
    return PressureLLMGateway(
        "qwen3-coder-next:latest",
        "freeciv-expansion/1.0",
        engine_live=True,
        minimum_quality=0.0,
        clock=lambda: "2026-07-29T00:00:00Z")


def _packets(exact_rule=1):
    return GatewayPacketLedger((
        PacketBudget(ResourceKind.EXPANSION, 1),
        PacketBudget(ResourceKind.LLM_TOKEN, 1),
        PacketBudget(ResourceKind.EXACT_RULE, exact_rule),
    ))


def test_llm_call_requires_expansion_and_validation_packets():
    tokens = TokenBudgetLedger(512, 1024)
    missing = _gateway().admit(
        _request(), _pressure(), tokens, 4)
    assert not missing.accepted
    assert missing.reason == "typed_packets_required"

    insufficient = _packets(exact_rule=0)
    rejected = _gateway().admit(
        _request("request:insufficient"),
        _pressure(), tokens, 4,
        packet_ledger=insufficient)
    assert not rejected.accepted
    assert rejected.reason == (
        "compound_packet_budget_exhausted")
    assert tokens.reservation(rejected.call_id) is None

    accepted = _gateway().admit(
        _request("request:accepted"), _pressure(),
        tokens, 4, packet_ledger=_packets())
    assert accepted.accepted
    assert {
        row.resource for row in accepted.packet_costs
    } == {
        ResourceKind.EXACT_RULE,
        ResourceKind.EXPANSION,
        ResourceKind.LLM_TOKEN,
    }


def test_llm_proposal_remains_quarantined_after_probe_success():
    tokens = TokenBudgetLedger(512, 1024)
    packets = _packets()
    gateway = _gateway()
    decision = gateway.admit(
        _request(), _pressure(), tokens, 4,
        packet_ledger=packets)
    invocation = gateway.invoke(
        decision, Proposer(), tokens, object(),
        packet_ledger=packets)

    probe = gateway.probe(
        invocation.envelope, bridge_score=1.0)

    assert probe.creates_bridge
    assert not probe.promoted
    assert probe.lifecycle == "quarantined"
    assert invocation.envelope.lifecycle == "quarantined"


def test_prompt_contains_typed_gap_and_forbidden_assumptions():
    prompt = _request().prompt_context()

    assert prompt["requested_schema_id"] == (
        "freeciv-expansion/1.0")
    assert prompt["target_atom_id"] == "gap"
    assert prompt["unresolved_premise_ids"] == [
        "premise:missing"]
    assert prompt["forbidden_assumption_ids"] == [
        "assumption:omniscience"]


def test_low_pressure_request_is_not_admitted():
    decision = _gateway().admit(
        _request(), _pressure(expand=0.0),
        TokenBudgetLedger(512, 1024), 4,
        packet_ledger=_packets())

    assert not decision.accepted
    assert decision.reason == (
        "insufficient_expand_pressure")


def test_token_reservation_is_atomic_and_settled():
    tokens = TokenBudgetLedger(512, 1024)
    packets = _packets()
    gateway = _gateway()
    decision = gateway.admit(
        _request(), _pressure(), tokens, 4,
        packet_ledger=packets)

    assert tokens.reservation(decision.call_id)[
        "settled"] is False
    assert packets.reservation(decision.call_id)[
        "state"] == "reserved"

    invocation = gateway.invoke(
        decision, Proposer(), tokens, object(),
        packet_ledger=packets)

    assert invocation.status == (
        "quarantined_pending_validation")
    assert tokens.reservation(decision.call_id)[
        "settled"] is True
    assert packets.reservation(decision.call_id)[
        "state"] == "settled"
    envelope = invocation.envelope.to_dict()
    assert envelope["proposal_content_digest"]
    assert envelope["evidence_dependencies"] == [
        "state:turn-4"]
    assert envelope["expiration_and_retry"] == {
        "expires_turn": 12,
        "maximum_retries": 2,
        "retry_after_turn": 7,
    }


def test_rejected_proposal_does_not_change_truth_or_conductance_as_if_verified():
    truth = TruthState(0.3, 0.5)
    conductance = ConductanceState()
    conductance_before = conductance.state_hash
    gateway = PressureLLMGateway(
        "qwen3-coder-next:latest",
        "freeciv-expansion/1.0",
        engine_live=True,
        minimum_quality=1000.0)
    tokens = TokenBudgetLedger(512, 1024)
    packets = _packets()

    decision = gateway.admit(
        _request(), _pressure(), tokens, 4,
        packet_ledger=packets)

    assert not decision.accepted
    assert decision.reason == (
        "quality_below_cost_threshold")
    assert truth == TruthState(0.3, 0.5)
    assert conductance.state_hash == conductance_before
    assert tokens.snapshot()["reservations"] == []
    assert packets.snapshot()["reservations"] == []
