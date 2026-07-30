"""Candidate-set metamorphic gates for intrinsic transition estimates."""

import os
import sys
from dataclasses import replace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import ImpactCandidate  # noqa: E402
from freeciv_agent.planning.domain_models import (  # noqa: E402
    DomainEstimateRequest,
    DomainTransitionModelRegistry,
    EstimateValidity,
    LegacyProjectionTransitionModel,
)


def _request(candidate):
    return DomainEstimateRequest(
        request_id="f" * 64,
        snapshot={"turn": 3, "state": "fixed"},
        ruleset_ir=None,
        legal_action=dict(candidate.action),
        candidate=candidate,
        goal_losses=(("goal", 2.0),),
        operation_context=None,
        validity=EstimateValidity(
            "snapshot", "legal", "ruleset", 3, 3),
        horizon_turn=20)


def _candidate(utility):
    return ImpactCandidate(
        action={
            "action_type": "city_production",
            "city_id": 2,
            "target": {"production_type": "Riflemen"},
        },
        category="production_defense",
        utility=utility,
        rationale="fixed action",
        projection={
            "completion_eta_turns": 4,
            "next_goal_cost_to_go": {"goal": 0.5},
            "success_probability": 0.8,
        })


def _intrinsic(candidate):
    registry = DomainTransitionModelRegistry(
        fallback_model=LegacyProjectionTransitionModel())
    return registry.estimate(
        _request(candidate)).to_dict()


def test_scaling_legacy_utility_does_not_change_typed_estimate():
    low = _intrinsic(_candidate(1.0))
    high = _intrinsic(_candidate(1000000.0))

    assert low == high


def test_unrelated_candidate_add_duplicate_and_permutation_are_irrelevant():
    target = _candidate(10.0)
    unrelated = ImpactCandidate(
        {"action_type": "unit_move", "actor_id": 9},
        "hut_exploration", 999.0, "unrelated")
    candidate_sets = (
        (target,),
        (target, unrelated),
        (unrelated, target),
        (unrelated, replace(unrelated), target),
    )

    estimates = tuple(
        _intrinsic(next(
            row for row in candidates
            if row.action == target.action))
        for candidates in candidate_sets)

    assert all(row == estimates[0] for row in estimates)
