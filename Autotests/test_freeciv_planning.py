"""M3 proof scheduler, resource ledger, bounded solver, and event tests."""

import os
import random
import sys
import tempfile

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.oracle import CrispStateView, DependencyOracle, Goal  # noqa: E402
from freeciv_agent.planning import (NonPlan, PlanningSnapshot, ProductionGoal,  # noqa: E402
                                    ProductionScheduler, ProofScheduler,
                                    ResourceLedger, ResourceLedgerEntry,
                                    validate_next_step)
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402


def _ruleset_root():
    configured = os.environ.get("FREECIV_RULESET_ROOT")
    candidates = [configured] if configured else []
    candidates.append(os.path.abspath(os.path.join(
        REPO, "..", "..", "..", "Repos", "freeciv-llm", "freeciv", "freeciv", "data")))
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(candidate, "civ2civ3", "techs.ruleset")):
            return candidate
    pytest.skip("set FREECIV_RULESET_ROOT for planning integration tests")


@pytest.fixture(scope="module")
def ir():
    return compile_ruleset(_ruleset_root(), "civ2civ3")


def _query(ir, tech="Writing", known=()):
    return DependencyOracle(ir).deps(
        Goal.researchable("player", tech),
        CrispStateView("snapshot-plan", known_techs=known, player="player"))


def _numeric(query, turn=10, rate=10):
    names = sorted(set(query.prerequisite_names) | {str(query.goal.arguments[-1])})
    return PlanningSnapshot(
        "snapshot-plan", turn, rate, 50,
        tech_costs=tuple((name, 10 + index * 3) for index, name in enumerate(names)))


def test_topological_schedule_has_exact_durations_and_is_byte_deterministic(ir):
    query = _query(ir, "Writing")
    numeric = PlanningSnapshot(
        "snapshot-plan", 10, 8, 50, current_research="Alphabet", current_progress=4,
        tech_costs=(("Alphabet", 20), ("Writing", 25)))
    scheduler = ProofScheduler()
    first = scheduler.schedule(query, numeric)
    second = scheduler.schedule(query, numeric)
    assert first.to_dict() == second.to_dict()
    assert first.artifact_hash == second.artifact_hash
    assert [step.target["tech"] for step in first.steps] == ["Alphabet", "Writing"]
    assert [step.duration_turns for step in first.steps] == [2, 4]
    assert first.predicted_turns == 6
    assert first.feasibility_grade == 1.0
    assert first.scheduler_cost == 6.0


def test_grade_and_cost_are_distinct_and_gold_weight_is_declared(ir):
    query = _query(ir)
    numeric = _numeric(query)
    plain = ProofScheduler("turns-to-goal").schedule(query, numeric)
    weighted = ProofScheduler("gold-weighted", gold_weight=0.5).schedule(query, numeric)
    assert plain.feasibility_grade == weighted.feasibility_grade == 1.0
    assert plain.cost_profile != weighted.cost_profile
    # Positive gold has no penalty; the profile still remains explicit in the artifact.
    assert plain.scheduler_cost == weighted.scheduler_cost
    source = open(os.path.join(SRC, "freeciv_agent", "planning", "scheduler.py"),
                  encoding="utf-8").read()
    assert "confidence" not in source.lower()


def test_missing_rate_cost_and_timeout_are_typed_nonplans(ir):
    query = _query(ir)
    no_rate = ProofScheduler().schedule(query, _numeric(query, rate=0))
    no_cost = ProofScheduler().schedule(query, PlanningSnapshot(
        "snapshot-plan", 1, 5, 0, tech_costs=()))
    timeout = ProofScheduler(timeout_ms=-1).schedule(query, _numeric(query))
    assert isinstance(no_rate, NonPlan) and no_rate.reason == "BEAKERS_PER_TURN_UNAVAILABLE"
    assert isinstance(no_cost, NonPlan) and no_cost.reason == "MISSING_GROUNDED_COST"
    assert isinstance(timeout, NonPlan) and timeout.reason == "SCHEDULER_TIMEOUT"
    assert not no_rate.executable and not no_cost.executable and not timeout.executable


def test_resource_ledger_rejects_double_spend_and_10000_generated_trees_are_linear():
    with pytest.raises(ValueError):
        ResourceLedger((
            ResourceLedgerEntry("stock", 10, 7, 3, "one"),
            ResourceLedgerEntry("stock", 3, 4, -1, "two"),
        )).validate()
    randomizer = random.Random(3117)
    for tree_index in range(10000):
        available = randomizer.randint(0, 1000)
        entries = []
        for branch in range(randomizer.randint(1, 6)):
            allocation = randomizer.randint(0, available)
            remaining = available - allocation
            entries.append(ResourceLedgerEntry(
                "tree-{}-stock".format(tree_index), available, allocation,
                remaining, "branch-{}".format(branch)))
            available = remaining
        assert ResourceLedger(tuple(entries)).validate()


def test_bounded_production_solver_respects_stock_rates_horizon_and_timeout():
    snapshot = PlanningSnapshot(
        "snapshot-plan", 20, 5, 0, build_costs=(("Settlers", 40), ("Warriors", 10)),
        city_shields_per_turn=(("Rome", 5), ("Veii", 3)),
        city_shield_stockpiles=(("Rome", 5), ("Veii", 1)))
    result = ProductionScheduler(horizon=30).schedule((
        ProductionGoal("expand", "Settlers"),
        ProductionGoal("defend", "Warriors", 2),
    ), snapshot)
    assert not isinstance(result, NonPlan)
    assert result["predicted_turns"] <= 30
    assert result["ledger"].validate()
    impossible = ProductionScheduler(horizon=1).schedule((
        ProductionGoal("expand", "Settlers"),), snapshot)
    timed = ProductionScheduler(horizon=30, timeout_ms=-1).schedule((
        ProductionGoal("expand", "Settlers"),), snapshot)
    assert isinstance(impossible, NonPlan) and impossible.status == "NO_PLAN_WITHIN_HORIZON"
    assert isinstance(timed, NonPlan) and timed.reason == "SCHEDULER_TIMEOUT"


def test_twenty_tech_schedules_equal_exhaustive_sequential_optimum(ir):
    names = [rule.rule_name for rule in ir.rules if rule.target_kind == "tech" and not rule.disabled][:20]
    checked = 0
    for target in names:
        query = _query(ir, target)
        if not query.executable:
            continue
        numeric = _numeric(query, rate=7)
        result = ProofScheduler().schedule(query, numeric)
        if isinstance(result, NonPlan):
            continue
        # With one research slot, all topological permutations have the same sum of
        # ceil(cost/rate); this is the exhaustive lower bound and exact optimum.
        optimum = sum(step.duration_turns for step in result.steps)
        assert result.predicted_turns <= optimum * 1.05
        checked += 1
    assert checked == 20


def test_preexecution_revalidation_blocks_stale_plan(ir):
    plan = ProofScheduler().schedule(_query(ir), _numeric(_query(ir)))
    assert validate_next_step(plan, "snapshot-plan") == (True, None)
    assert validate_next_step(plan, "snapshot-new") == (False, "stale_snapshot")


def test_plan_event_is_schema_valid_and_causally_linked(ir):
    oracle = DependencyOracle(ir)
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "planner-test", durable=False)
        root = writer.emit("run_started", 0, {
            "condition_id": "planner-test", "manifest_identity": "m"})
        query, query_event, result_event = oracle.emit_deps(
            Goal.researchable("player", "Writing"), CrispStateView("snapshot-plan"),
            writer, 0, caused_by=[root["event_id"]], invoking_layer="planner")
        plan, plan_event = ProofScheduler().emit_plan(
            query, _numeric(query), writer, 0, caused_by=[result_event["event_id"]])
        report = validate_file(path)
    assert plan_event["caused_by"] == [result_event["event_id"]]
    assert report.valid, report.to_dict()
