"""PF-PLN contextual induction, analogy, and replay lifecycle gates."""

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
from freeciv_agent.pressure import (  # noqa: E402
    AtomState,
    ContextGeneralizer,
    CostVector,
    ExpansionGate,
    GoalState,
    InductionEpisode,
    InductionLedger,
    PatternMiner,
    PressureEngine,
    PressureGraph,
    RelationalProfile,
    ReplayValidator,
    Resolvability,
    StructuralAnalogy,
    TruthState,
    implied_similarity,
)


def _context(opponent):
    return (
        ("diplomacy", "peace"),
        ("era", "ancient"),
        ("geometry", "land-border"),
        ("opponent", opponent),
        ("ruleset", "classic"),
    )


def _episode(index, opponent, features, outcome, prefix="train"):
    episode_id = "{}-{}-{:03d}".format(prefix, opponent, index)
    return InductionEpisode(
        episode_id, _context(opponent), tuple(features), outcome,
        ("observation-" + episode_id,))


def _population(opponent, prefix="train", inverted=False):
    rows = []
    patterns = (
        (("border-road", "military-spike"), True),
        (("border-road",), False),
        (("military-spike",), False),
        (("settler-seen",), False),
    )
    for index in range(24):
        features, outcome = patterns[index % len(patterns)]
        if inverted and features == ("border-road", "military-spike"):
            outcome = False
        rows.append(_episode(
            index, opponent, features, outcome, prefix=prefix))
    return tuple(rows)


def _proposal(opponent="alpha"):
    candidates = PatternMiner(
        minimum_support=4, maximum_antecedents=2).mine(
            _population(opponent), "attack-within-six")
    return next(
        row for row in candidates
        if row.antecedent == ("border-road", "military-spike"))


def _pressure(expand):
    graph = PressureGraph()
    graph.add_atom(
        AtomState("attack-risk", TruthState(0.0, 1.0, crisp=True)),
        Resolvability(expand=expand, infer=1.0 - expand))
    return PressureEngine().propagate(
        graph, (GoalState("survive", "attack-risk"),))


def test_contextual_pattern_mining_is_deterministic_and_scoped():
    episodes = _population("alpha") + _population("bravo")
    miner = PatternMiner(minimum_support=4, maximum_antecedents=2)
    first = miner.mine(episodes, "attack-within-six")
    second = miner.mine(tuple(reversed(episodes)), "attack-within-six")
    assert [row.to_dict() for row in first] == [
        row.to_dict() for row in second]
    proposal = next(
        row for row in first
        if row.context == _context("alpha")
        and row.antecedent == ("border-road", "military-spike"))
    assert proposal.source == "pattern"
    assert proposal.support == 6
    assert proposal.trigger_pressure > 0
    assert proposal.applies(_population("alpha", "held")[0])
    assert not proposal.applies(_population("charlie", "held")[0])


def test_expand_pressure_and_expected_value_gate_validation_work():
    proposal = _proposal()
    gate = ExpansionGate(
        minimum_expand_pressure=0.05, minimum_value_cost_ratio=0.01)
    rejected = gate.decide(
        proposal, _pressure(0.0), "survive", "attack-risk",
        CostVector(compute=0.1))
    assert not rejected.accepted
    assert rejected.reason == "insufficient_expand_pressure"
    accepted = gate.decide(
        proposal, _pressure(1.0), "survive", "attack-risk",
        CostVector(compute=0.1))
    assert accepted.accepted
    assert accepted.operation.mode == "expand"
    assert accepted.operation.payload["validation_required"] is True
    assert accepted.operation.payload["proposal"]["proposal_id"] == (
        proposal.proposal_id)


def test_replay_promotes_contextual_rule_and_rejects_data_leakage():
    proposal = _proposal()
    validator = ReplayValidator(
        minimum_samples=16, minimum_activations=4)
    validation = validator.validate(
        proposal, _population("alpha", "validation"))
    assert validation.verdict == "promoted"
    assert validation.metrics.brier_improvement > 0
    assert validation.metrics.calibration_improvement > 0
    assert validation.metrics.candidate_contradiction_rate <= (
        validation.metrics.baseline_contradiction_rate)
    with pytest.raises(ValueError, match="overlap"):
        validator.validate(proposal, _population("alpha"))


def test_overgeneralized_rule_is_demoted_by_out_of_sample_replay():
    alpha = _proposal("alpha")
    bravo = _proposal("bravo")
    generalized = ContextGeneralizer.propose(
        (alpha, bravo), ("opponent",))
    assert generalized.context == tuple(
        row for row in _context("alpha") if row[0] != "opponent")
    hostile_validation = (
        _population("alpha", "validation")
        + _population("bravo", "validation")
        + _population("charlie", "validation", inverted=True)
        + _population("delta", "validation", inverted=True)
        + _population("echo", "validation", inverted=True)
        + _population("foxtrot", "validation", inverted=True))
    validation = ReplayValidator(
        minimum_samples=16, minimum_activations=4).validate(
            generalized, hostile_validation)
    assert validation.verdict == "demoted"
    assert validation.reason in (
        "no_out_of_sample_improvement", "contradiction_rate_increased")
    assert validation.metrics.candidate_contradiction_rate > (
        validation.metrics.baseline_contradiction_rate)


def test_structural_analogy_requires_context_and_relational_correspondence():
    rule = _proposal()
    source = RelationalProfile(
        "border-road-pattern", _context("alpha"),
        ("observed-by:scout", "precedes:attack"),
        ("supports:threat", "triggers:response"), ("profile-source",))
    target = RelationalProfile(
        "naval-buildup-pattern", _context("alpha"),
        ("observed-by:scout", "precedes:attack"),
        ("supports:threat", "triggers:response"), ("profile-target",))
    link = implied_similarity(source, target, transfer_reliability=0.8)
    assert link.score == pytest.approx(0.8)
    analogy = StructuralAnalogy(minimum_structural_match=0.7).propose(
        rule, source, target, (
            ("border-road", "coastal-road"),
            ("military-spike", "naval-production-spike"),
            ("attack-within-six", "landing-within-six"),
        ), transfer_reliability=0.8)
    assert analogy.source == "analogy"
    assert analogy.transfer_uncertainty > 0
    assert analogy.probability < rule.probability
    mismatched = RelationalProfile(
        "foreign-pattern", _context("bravo"),
        source.incoming_relations, source.outgoing_relations, ("foreign",))
    assert implied_similarity(source, mismatched) is None
    assert StructuralAnalogy().propose(
        rule, source, mismatched, (
            ("border-road", "coastal-road"),
            ("military-spike", "naval-production-spike"),
            ("attack-within-six", "landing-within-six"),
        )) is None


def test_ledger_persists_quarantine_promotion_and_valid_events():
    proposal = _proposal()
    decision = ExpansionGate().decide(
        proposal, _pressure(1.0), "survive", "attack-risk",
        CostVector(compute=0.1))
    validation = ReplayValidator().validate(
        proposal, _population("alpha", "validation"))
    with tempfile.TemporaryDirectory() as directory:
        ledger_path = os.path.join(directory, "induction.json")
        event_path = os.path.join(directory, "events.jsonl")
        ledger = InductionLedger(ledger_path, identity="classic-alpha")
        writer = EventWriter(
            event_path, "induction-test", durable=False,
            clock=lambda: "2026-07-25T00:00:00Z",
            id_factory=iter(("proposal-event", "validation-event")).__next__)
        proposed = ledger.emit_proposal(
            writer, 4, proposal, decision)
        assert ledger.status(proposal.proposal_id) == "quarantined"
        assert ledger.promoted_rules() == ()
        ledger.emit_validation(
            writer, 4, validation, caused_by=(proposed["event_id"],))
        assert ledger.status(proposal.proposal_id) == "promoted"
        assert ledger.promoted_rules() == (proposal,)
        state_hash = ledger.state_hash
        reloaded = InductionLedger(ledger_path, identity="classic-alpha")
        assert reloaded.state_hash == state_hash
        assert reloaded.promoted_rules() == (proposal,)
        report = validate_file(event_path)
        assert report.valid, report.errors
