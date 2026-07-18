"""M6 constrained proposal, three-sink, grading, security, and latency gates."""

import json
import os
import sys
import tempfile

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.llm import (ClaimRouter, ConstrainedProposer,  # noqa: E402
                               ConstrainedTurnLoop, FactualClaim,
                               GoalGrader, PROMPT_VERSION, ProposalError,
                               QuarantineStore, SymbolCatalog,
                               VerifiedBeliefSink)
from freeciv_agent.oracle import CrispStateView, DependencyOracle  # noqa: E402
from freeciv_agent.planning import PlanningSnapshot, ProofScheduler  # noqa: E402
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402


def _ruleset_root():
    configured = os.environ.get("FREECIV_RULESET_ROOT")
    candidates = [configured] if configured else []
    candidates.append(os.path.abspath(os.path.join(
        REPO, "..", "..", "..", "Repos", "freeciv-llm", "freeciv", "freeciv", "data")))
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(candidate, "civ2civ3", "techs.ruleset")):
            return candidate
    pytest.skip("set FREECIV_RULESET_ROOT for M6 tests")


@pytest.fixture(scope="module")
def stack():
    ir = compile_ruleset(_ruleset_root(), "civ2civ3")
    catalog = SymbolCatalog(ir)
    tech = next(rule for rule in ir.rules if rule.target_kind == "tech" and not rule.disabled
                and rule.rule_name != "None")
    return ir, catalog, tech


def _proposal(tech, index=1, claim=None, selection=True):
    value = {
        "schema_version": "1.0", "proposal_id": "proposal-{}".format(index),
        "goals": [{
            "goal_id": "goal-{}".format(index), "target_id": tech.rule_id,
            "predicate": "researchable", "arguments": ["player", tech.rule_name],
        }],
        "claims": [] if claim is None else [claim],
        "rationale": "Choose a mechanically catalogued target.",
        "selection": "goal-{}".format(index) if selection else None,
    }
    return json.dumps(value, sort_keys=True)


class Summary:
    def to_dict(self):
        return {"snapshot_id": "snapshot", "turn": 1, "known_techs": ["Alphabet"]}


def test_100_seeded_outputs_quarantine_all_40_false_claims_with_zero_write_through(stack):
    _, catalog, tech = stack
    quarantine = QuarantineStore()
    sink = VerifiedBeliefSink()
    router = ClaimRouter(
        catalog, {("has-tech", ("player", "Alphabet"))},
        quarantine=quarantine, belief_sink=sink, model="qwen3-coder-next:latest",
        model_config={"temperature": 0.0})
    parser = ConstrainedProposer(lambda _: "", catalog, "model").parser
    for index in range(100):
        known_false = index < 40
        claim = {
            "claim_id": "claim-{}".format(index),
            "text": ("We know Future Tech" if known_false else "We know Alphabet"),
            "predicate": "has-tech",
            "arguments": ["player", "Future Tech" if known_false else "Alphabet"],
            "asserted": True,
        }
        proposal = parser.parse(_proposal(tech, index, claim))
        verified, = router.route_proposal(proposal)
        assert verified.verdict == ("quarantine" if known_false else "believe")
    assert len(quarantine.audit_entries()) == 40
    assert len(sink.claims()) == 60
    assert not any(item.claim.arguments[-1] == "Future Tech" for item in sink.claims())
    assert all(item.model == "qwen3-coder-next:latest" for item in quarantine.audit_entries())


def test_goal_translation_reaches_95_percent_and_bounded_correction_never_crashes(stack):
    _, catalog, tech = stack
    outputs = []
    calls = {"count": 0}
    for index in range(100):
        if index < 95:
            outputs.append(_proposal(tech, index))
        else:
            invalid = json.loads(_proposal(tech, index))
            invalid["goals"][0]["target_id"] = "invented:target"
            outputs.extend((json.dumps(invalid), _proposal(tech, index)))

    def client(_request):
        value = outputs[calls["count"]]
        calls["count"] += 1
        return value

    proposer = ConstrainedProposer(client, catalog, "model", max_corrections=1)
    translated = 0
    for _ in range(100):
        proposal, corrections = proposer.propose(Summary())
        translated += int(bool(proposal.goals))
        assert corrections in (0, 1)
    assert translated == 100
    exhausted = ConstrainedProposer(lambda _: "{}", catalog, "model", max_corrections=1)
    with pytest.raises(ProposalError, match="correction_exhausted"):
        exhausted.propose(Summary())


def test_input_is_query_summary_only_and_security_boundaries_fail_closed(stack):
    _, catalog, tech = stack
    proposer = ConstrainedProposer(lambda _: _proposal(tech), catalog, "model")
    with pytest.raises(TypeError, match="query summary"):
        proposer.input_document({"raw_proxy_state": {"private": True}})
    sink = VerifiedBeliefSink()
    with pytest.raises(PermissionError):
        sink.write(FactualClaim("id", "raw", "has-tech", ("p", "x"), True))
    parser = proposer.parser
    injected = json.loads(_proposal(tech))
    injected["claims"] = [{
        "claim_id": "inject", "text": "raw state", "predicate": "raw-proxy-state",
        "arguments": ["all"], "asserted": True}]
    with pytest.raises(ProposalError, match="unknown_claim_predicate"):
        parser.parse(json.dumps(injected))


def test_candidate_grade_and_cost_remain_distinct(stack):
    ir, catalog, tech = stack
    proposal = ConstrainedProposer(lambda _: _proposal(tech), catalog, "model").propose(Summary())[0]
    oracle = DependencyOracle(ir)
    state = CrispStateView("snapshot", known_techs=(), player="player")
    query = oracle.deps(
        __import__("freeciv_agent.oracle", fromlist=["Goal"]).Goal(
            "researchable", ("player", tech.rule_name)), state)
    names = set(query.prerequisite_names) | {tech.rule_name}
    numeric = PlanningSnapshot(
        "snapshot", 1, 10, 0, tech_costs=tuple((name, 20) for name in names))
    grade, = GoalGrader(oracle, ProofScheduler()).grade_all(proposal, state, numeric)
    assert grade.valid
    assert grade.feasibility_grade == 1.0
    assert grade.scheduler_cost >= 0
    assert "feasibility_grade" in grade.to_dict() and "scheduler_cost" in grade.to_dict()


def test_200_turn_fixture_loop_meets_30_second_budget_on_every_turn(stack):
    ir, catalog, tech = stack
    proposer = ConstrainedProposer(lambda _: _proposal(tech), catalog, "model")
    router = ClaimRouter(catalog, set())
    oracle = DependencyOracle(ir)
    state = CrispStateView("snapshot", player="player")
    query = oracle.deps(
        __import__("freeciv_agent.oracle", fromlist=["Goal"]).Goal(
            "researchable", ("player", tech.rule_name)), state)
    names = set(query.prerequisite_names) | {tech.rule_name}
    numeric = PlanningSnapshot(
        "snapshot", 1, 10, 0, tech_costs=tuple((name, 20) for name in names))
    loop = ConstrainedTurnLoop(proposer, router, GoalGrader(oracle, ProofScheduler()))
    decisions = [loop.run(Summary(), state, numeric) for _ in range(200)]
    assert sum(item.elapsed_ms < 30_000 for item in decisions) == 200
    assert all(item.status in ("SELECTED", "NO_PLAN") for item in decisions)


def test_timeout_has_safe_end_turn_and_cannot_bypass_verification(stack):
    ir, catalog, tech = stack
    proposer = ConstrainedProposer(lambda _: _proposal(tech), catalog, "model")
    router = ClaimRouter(catalog, set())
    loop = ConstrainedTurnLoop(
        proposer, router, GoalGrader(DependencyOracle(ir), ProofScheduler()),
        timeout_seconds=-1)
    decision = loop.run(Summary(), CrispStateView("snapshot"), PlanningSnapshot(
        "snapshot", 1, 10, 0, tech_costs=((tech.rule_name, 20),)))
    assert decision.status == "SAFE_FALLBACK"
    assert decision.fallback_action == {"type": "end_turn"}
    assert decision.grades == () and decision.selected is None


def test_proposal_verification_quarantine_events_are_causal_and_schema_valid(stack):
    _, catalog, tech = stack
    claim = {
        "claim_id": "false", "text": "Future Tech is known", "predicate": "has-tech",
        "arguments": ["player", "Future Tech"], "asserted": True}
    proposal = ConstrainedProposer(
        lambda _: _proposal(tech, claim=claim), catalog, "qwen3-coder-next:latest").propose(Summary())[0]
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "llm-test", durable=False)
        root = writer.emit("run_started", 0, {
            "condition_id": "e_full_loop", "manifest_identity": "m"})
        proposal_event, rows = ClaimRouter(
            catalog, set(), model="qwen3-coder-next:latest",
            model_config={"temperature": 0.0}).emit_route_proposal(
                proposal, writer, 1, PROMPT_VERSION, [root["event_id"]])
        report = validate_file(path)
        assert rows[0][1]["caused_by"] == [proposal_event["event_id"]]
        assert rows[0][2]["caused_by"] == [rows[0][1]["event_id"]]
        assert report.valid, report.to_dict()
