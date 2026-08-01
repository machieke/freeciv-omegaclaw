import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (  # noqa: E402
    DeferredImpactOutcomeLedger,
    GroundedGoalRelief,
    ImpactCandidate,
    ImpactTurnBudget,
)
from freeciv_agent.planning import impact  # noqa: E402
from freeciv_agent.planning import impact_types  # noqa: E402


def test_impact_facade_reexports_exact_contract_and_policy_objects():
    assert impact.ImpactCandidate is impact_types.ImpactCandidate
    assert impact.ImpactDecision is impact_types.ImpactDecision
    assert impact.DeferredImpactOutcomeLedger is (
        impact_types.DeferredImpactOutcomeLedger)
    assert impact.GroundedGoalRelief is impact_types.GroundedGoalRelief
    assert impact.ImpactTurnBudget is impact_types.ImpactTurnBudget
    assert impact.DEFENDER_PRIORITY is impact_types.DEFENDER_PRIORITY
    assert impact.IMPROVEMENT_PRIORITY is impact_types.IMPROVEMENT_PRIORITY
    assert impact._normalized_type is impact_types.normalized_type
    assert impact._distance is impact_types.wrapped_distance
    assert impact._target_name is impact_types.target_name
    assert impact._spatial_target is impact_types.spatial_target


def test_extracted_candidate_scope_and_budget_behavior_remain_exact():
    candidate = ImpactCandidate(
        {"action_type": "unit_move", "actor_id": 7},
        "defense", 1.0, "move defender")
    budget = ImpactTurnBudget(1)

    assert candidate.scope == ("unit", 7)
    assert candidate.action_key == '{"action_type":"unit_move","actor_id":7}'
    assert budget.record(candidate, effect_observed=False) is False
    assert candidate.scope in budget.excluded_scopes
    assert GroundedGoalRelief("survival", 1.0, "snapshot").to_dict() == {
        "goal": "survival", "realized_relief": 1.0,
        "source": "snapshot"}


def test_extracted_deferred_ledger_keeps_later_snapshot_semantics():
    candidate = ImpactCandidate(
        {"action_type": "city_production", "city_id": 3},
        "production", 1.0, "start production")
    before = SimpleNamespace(turn=4)
    after = SimpleNamespace(turn=5)
    planner = SimpleNamespace(
        candidate_effect_observed=lambda _candidate, _before, _after: False)
    ledger = DeferredImpactOutcomeLedger()
    ledger.defer(candidate, before, "feedback-1")

    resolved = ledger.resolve(planner, after)

    assert len(ledger) == 0
    assert len(resolved) == 1
    assert resolved[0].candidate is candidate
    assert resolved[0].effect_observed is False
    assert resolved[0].feedback_id == "feedback-1"
