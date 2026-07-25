#!/usr/bin/env python3
"""Deterministic validated-proposals-per-token benchmark for PF-PLN Phase 7."""

import argparse
import hashlib
import json
import os
import platform
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.llm import (  # noqa: E402
    ClaimRouter,
    ConstrainedProposer,
    GatewayRequest,
    PressureLLMGateway,
    QuarantineStore,
    TokenBudgetLedger,
    ValidationPlan,
    VerifiedBeliefSink,
    estimated_tokens,
)
from freeciv_agent.pressure import (  # noqa: E402
    AtomState,
    GoalState,
    PressureEngine,
    PressureGraph,
    Resolvability,
    TruthState,
)


class _Catalog:
    def prompt_catalog(self):
        return {
            "claims": ["has-tech"],
            "goals": [{
                "predicate": "researchable",
                "target_id": "tech:Writing",
            }],
        }

    def validate_goal(self, goal):
        valid = (
            goal.target_id == "tech:Writing"
            and goal.predicate == "researchable"
            and goal.arguments == ("player", "Writing"))
        return valid, None if valid else "unknown_goal"

    def validate_claim(self, claim):
        valid = (
            claim.predicate == "has-tech"
            and len(claim.arguments) == 2
            and claim.arguments[0] == "player")
        return valid, None if valid else "unknown_claim"


class _Summary:
    def __init__(self, index):
        self.index = int(index)

    def to_dict(self):
        return {
            "known_techs": ["Alphabet"],
            "snapshot_id": "snapshot-{:03d}".format(self.index),
            "turn": self.index,
        }


def _proposal(index, valid):
    technology = "Alphabet" if valid else "Future-Tech"
    return json.dumps({
        "claims": [{
            "arguments": ["player", technology],
            "asserted": True,
            "claim_id": "claim-{:03d}".format(index),
            "predicate": "has-tech",
            "text": "typed claim",
        }],
        "goals": [{
            "arguments": ["player", "Writing"],
            "goal_id": "goal-writing",
            "predicate": "researchable",
            "target_id": "tech:Writing",
        }],
        "proposal_id": "proposal-{:03d}".format(index),
        "rationale": "typed candidate",
        "schema_version": "1.0",
        "selection": "goal-writing",
    }, sort_keys=True)


def _pressure(expand):
    graph = PressureGraph()
    graph.add_atom(
        AtomState("gap:attack-route", TruthState(0.0, 1.0, crisp=True)),
        Resolvability(expand=expand, infer=1.0 - expand))
    return PressureEngine().propagate(
        graph, (GoalState("goal:survive", "gap:attack-route"),))


def _request(index, high_pressure):
    return GatewayRequest(
        request_id="request:{:03d}".format(index),
        goal_id="goal:survive",
        atom_id="gap:attack-route",
        context=(
            ("diplomacy", "peace"),
            ("opponent", "opponent-{:02d}".format(index % 5)),
            ("ruleset", "classic"),
        ),
        known_rule_ids=("rule:defense-production",),
        unresolved_premise_ids=("premise:alternate-route",),
        forbidden_assumption_ids=("assumption:omniscient-map",),
        action_budget=2,
        time_budget_seconds=20.0,
        expected_relief=0.8 if high_pressure else 0.2,
        useful_proposal_probability=0.8 if high_pressure else 0.1,
        token_limit=4096,
        latency_cost=0.1,
        token_cost=0.0001,
        validation_plan=ValidationPlan((
            "authoritative-rule-lookup",
            "contradiction-test",
            "formal-type-check",
        ), maximum_cost=0.1),
    )


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _route(catalog, proposal, quarantine, sink):
    verified = ClaimRouter(
        catalog, {("has-tech", ("player", "Alphabet"))},
        quarantine=quarantine, belief_sink=sink).route_proposal(proposal)
    return bool(verified) and all(row.verdict == "believe" for row in verified)


def run(cases=100, high_pressure_cases=40):
    cases = int(cases)
    high_pressure_cases = int(high_pressure_cases)
    if cases < 20 or not 1 <= high_pressure_cases < cases:
        raise ValueError("invalid benchmark corpus size")
    catalog = _Catalog()
    corpus = []
    for index in range(cases):
        high = index < high_pressure_cases
        valid = (
            index % 5 != 0 if high
            else (index - high_pressure_cases) % 10 == 0)
        corpus.append((index, high, valid))

    unconditional_tokens = 0
    unconditional_validated = 0
    unconditional_quarantine = QuarantineStore()
    unconditional_sink = VerifiedBeliefSink()
    for index, _, valid in corpus:
        summary = _Summary(index)
        proposer = ConstrainedProposer(
            lambda _document, row=_proposal(index, valid): row,
            catalog, "qwen3-coder-next:latest")
        document = proposer.input_document(summary)
        proposal, _ = proposer.propose(summary)
        unconditional_tokens += (
            estimated_tokens(document) + estimated_tokens(proposal.to_dict()))
        unconditional_validated += int(_route(
            catalog, proposal, unconditional_quarantine,
            unconditional_sink))

    ledger = TokenBudgetLedger(
        per_turn_limit=4096,
        total_limit=cases * 4096,
        maximum_calls_per_turn=1)
    gateway = PressureLLMGateway(
        "qwen3-coder-next:latest", "freeciv-constrained-proposer/1.0",
        minimum_expand_pressure=0.05, minimum_quality=0.1,
        clock=lambda: "2026-07-25T00:00:00Z")
    gated_calls = gated_validated = 0
    gated_quarantine = QuarantineStore()
    gated_sink = VerifiedBeliefSink()
    high_selected = low_selected = 0
    for index, high, valid in corpus:
        request = _request(index, high)
        decision = gateway.admit(
            request, _pressure(1.0 if high else 0.0), ledger, index)
        if not decision.accepted:
            continue
        high_selected += int(high)
        low_selected += int(not high)
        gated_calls += 1
        proposer = ConstrainedProposer(
            lambda _document, row=_proposal(index, valid): row,
            catalog, "qwen3-coder-next:latest")
        invocation = gateway.invoke(
            decision, proposer, ledger, _Summary(index))
        if invocation.envelope is None:
            continue
        gated_validated += int(_route(
            catalog, invocation.envelope.proposal,
            gated_quarantine, gated_sink))

    unconditional_rate = (
        float(unconditional_validated) / unconditional_tokens)
    gated_rate = float(gated_validated) / ledger.charged_tokens
    false_claim = ("player", "Future-Tech")
    quarantine_escapes = sum(
        claim.claim.arguments == false_claim
        for claim in gated_sink.claims())
    report = {
        "acceptance": {
            "higher_validated_proposals_per_token": (
                gated_rate > unconditional_rate),
            "no_low_pressure_calls": low_selected == 0,
            "quarantine_escapes_zero": quarantine_escapes == 0,
            "token_budget_respected": (
                ledger.charged_tokens <= ledger.total_limit),
        },
        "benchmark": "pf-pln-phase-7-llm-gateway",
        "configuration": {
            "cases": cases,
            "high_pressure_cases": high_pressure_cases,
            "model": "qwen3-coder-next:latest",
            "random_seed": None,
            "structured_fixture": True,
        },
        "implementation": {
            "benchmark_sha256": _sha256(__file__),
            "gateway_sha256": _sha256(os.path.join(
                SRC, "freeciv_agent", "llm", "gateway.py")),
            "python_version": platform.python_version(),
        },
        "pressure_gated": {
            "calls": gated_calls,
            "high_pressure_calls": high_selected,
            "low_pressure_calls": low_selected,
            "quarantined_proposals": len(
                gated_quarantine.audit_entries()),
            "quarantine_escapes": quarantine_escapes,
            "tokens": ledger.charged_tokens,
            "validated_proposal_rate_per_token": gated_rate,
            "validated_proposals": gated_validated,
        },
        "rate_improvement": {
            "absolute": gated_rate - unconditional_rate,
            "relative": (
                (gated_rate - unconditional_rate) / unconditional_rate),
        },
        "schema_version": "1.0",
        "unconditional": {
            "calls": cases,
            "quarantined_proposals": len(
                unconditional_quarantine.audit_entries()),
            "tokens": unconditional_tokens,
            "validated_proposal_rate_per_token": unconditional_rate,
            "validated_proposals": unconditional_validated,
        },
    }
    report["artifact_hash"] = structural_hash(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=100)
    parser.add_argument("--high-pressure-cases", type=int, default=40)
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    report = run(args.cases, args.high_pressure_cases)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        parent = os.path.dirname(os.path.abspath(args.out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as stream:
            stream.write(rendered)
    sys.stdout.write(rendered)
    return 0 if all(report["acceptance"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
