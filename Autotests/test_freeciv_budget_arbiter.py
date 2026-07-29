"""Cross-goal integer value-of-computation budget gates."""

import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    ActivityBid,
    BudgetArbiter,
    BudgetArbiterConfig,
    PacketBudget,
    ResourceKind,
)


def _bid(
        goal, value, minimum=0, maximum=10,
        safety=False, uncertainty=0.0,
        activity="infer", resource=ResourceKind.CPU):
    return ActivityBid(
        goal, activity, resource, value, uncertainty,
        minimum, maximum, safety)


def test_budget_arbiter_respects_resource_budgets():
    arbiter = BudgetArbiter()
    decision = arbiter.decide(
        (
            _bid("survival", 4.0, minimum=1, safety=True),
            _bid("score", 2.0),
            _bid(
                "observe", 3.0, activity="observe",
                resource=ResourceKind.OBSERVATION),
        ),
        (
            PacketBudget(ResourceKind.CPU, 7),
            PacketBudget(ResourceKind.OBSERVATION, 3),
        ))

    assert decision.conserved
    assert decision.accounting()["cpu"]["remaining"] >= 0
    assert decision.accounting()["observation"]["remaining"] >= 0


def test_safety_minimum_is_lexicographic():
    decision = BudgetArbiter(BudgetArbiterConfig(
        maximum_metacontrol_budget_fraction=0.0,
        metacontrol_cpu_packets=0,
        exploration_packets_per_goal=0,
    )).decide(
        (
            _bid(
                "score", 100.0, minimum=2,
                maximum=2),
            _bid(
                "survival", 0.1, minimum=2,
                maximum=2, safety=True),
        ),
        (PacketBudget(ResourceKind.CPU, 2),))

    safety = decision.allocation_for(
        "survival", "infer", ResourceKind.CPU)
    ordinary = decision.allocation_for(
        "score", "infer", ResourceKind.CPU)
    assert safety.packets == 2
    assert ordinary is None
    assert decision.unmet_minimums[0].bid_id.startswith(
        "score:")


def test_metacontrol_has_hard_budget_cap():
    arbiter = BudgetArbiter(BudgetArbiterConfig(
        maximum_metacontrol_budget_fraction=0.10,
        metacontrol_cpu_packets=50,
        exploration_packets_per_goal=0,
    ))
    decision = arbiter.decide(
        (_bid("score", 1.0),),
        (PacketBudget(ResourceKind.CPU, 25),))

    assert sum(
        row.quanta for row in decision.metacontrol_cost
        if row.resource == ResourceKind.CPU) == 2
    assert decision.accounting()["cpu"][
        "metacontrol_packets"] <= 2


def test_exploration_floor_survives_high_value_dominant_goal():
    arbiter = BudgetArbiter(BudgetArbiterConfig(
        maximum_metacontrol_budget_fraction=0.0,
        metacontrol_cpu_packets=0,
        exploration_packets_per_goal=1,
    ))
    decision = arbiter.decide(
        (
            _bid(
                "dominant", 100.0, uncertainty=0.1),
            _bid(
                "uncertain", 0.01, uncertainty=1.0),
        ),
        (PacketBudget(ResourceKind.CPU, 3),))

    assert decision.allocation_for(
        "uncertain", "infer", ResourceKind.CPU).packets >= 1
    assert {
        row.goal_id for row in decision.exploration_floor
    } == {"dominant", "uncertain"}


def test_static_fallback_is_used_when_value_calibration_is_unhealthy():
    decision = BudgetArbiter(BudgetArbiterConfig(
        maximum_metacontrol_budget_fraction=0.0,
        metacontrol_cpu_packets=0,
        exploration_packets_per_goal=0,
    )).decide(
        (
            _bid("a", 100.0, maximum=10),
            _bid("b", 1.0, maximum=10),
        ),
        (PacketBudget(ResourceKind.CPU, 4),),
        calibration_healthy=False)

    assert decision.fallback_used
    assert decision.allocation_for(
        "a", "infer", ResourceKind.CPU).packets == 2
    assert decision.allocation_for(
        "b", "infer", ResourceKind.CPU).packets == 2
    assert all(
        "static-fallback" in row.reasons
        for row in decision.allocations)


def test_non_update_cycle_uses_bounded_static_policy():
    arbiter = BudgetArbiter(BudgetArbiterConfig(
        maximum_metacontrol_budget_fraction=0.5,
        metacontrol_cpu_packets=5,
        exploration_packets_per_goal=0,
        update_cadence=4,
    ))
    decision = arbiter.decide(
        (_bid("goal", 1.0),),
        (PacketBudget(ResourceKind.CPU, 4),),
        cycle_index=1)

    assert decision.fallback_used
    assert decision.metacontrol_cost == ()
