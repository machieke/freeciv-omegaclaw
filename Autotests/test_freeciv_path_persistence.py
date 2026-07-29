"""Cheap calibrated path-persistence comparator gates."""

import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning.impact import ImpactCandidate  # noqa: E402
from freeciv_agent.pressure import (  # noqa: E402
    CostVector,
    ImpactPressureRankerV2,
    Operation,
    ScalarBaselineConfig,
    TransitionValueModel,
)
from freeciv_agent.pressure.scheduler import OperationScore  # noqa: E402


def _candidate(actor, category, target, action_type="unit_move"):
    return ImpactCandidate(
        {
            "action_type": action_type,
            "actor_id": actor,
            "target": {"x": target, "y": target},
        },
        category, 1.0, category)


def _score(operation_id, candidate, priority, reversible=True):
    operation = Operation(
        operation_id, "target:" + operation_id,
        "act", CostVector(compute=1.0),
        causal_kind="procedural",
        reversible=reversible,
        externally_consequential=True,
        payload=candidate.to_dict())
    return OperationScore(
        operation=operation,
        admissible=True,
        reason=None,
        priority=priority,
        value=priority,
        scalar_cost=1.0,
        conflict_penalty=0.0,
        goal_effects=())


def _ranker(maximum_regret=0.05):
    return ImpactPressureRankerV2(
        teleological_enabled=True,
        transition_value_model=TransitionValueModel(),
        transition_value_authority_enabled=True,
        path_persistence_enabled=True,
        path_persistence_config=ScalarBaselineConfig(
            smoothing=1.0,
            route_momentum=0.0,
            minimum_dwell_steps=2,
            dwell_bonus=0.0,
            switch_margin=0.0,
            diversity_floor=0.0),
        path_persistence_maximum_priority_regret=(
            maximum_regret))


def _calibrated():
    return {"calibration": {"authority_active": True}}


def test_path_persistence_retains_a_near_tie_and_replays_idempotently():
    ranker = _ranker()
    first_a = _candidate(1, "route_a", 1)
    first_b = _candidate(2, "route_b", 1)
    first_scores = (
        _score("a:1", first_a, 1.0),
        _score("b:1", first_b, 0.99),
    )
    ranker._path_persistent_scores(
        SimpleNamespace(turn=1),
        first_scores,
        {"a:1": first_a, "b:1": first_b},
        _calibrated())

    second_a = _candidate(1, "route_a", 2)
    second_b = _candidate(2, "route_b", 2)
    second_scores = (
        _score("b:2", second_b, 1.0),
        _score("a:2", second_a, 0.99),
    )
    arguments = (
        SimpleNamespace(turn=2),
        second_scores,
        {"a:2": second_a, "b:2": second_b},
        _calibrated(),
    )
    ordered, artifact = ranker._path_persistent_scores(
        *arguments)
    replay_ordered, replay_artifact = (
        ranker._path_persistent_scores(
            *arguments))

    assert ordered[0].operation_id == "a:2"
    assert artifact["reordered"]
    assert artifact["decision"]["retained_by_dwell"]
    assert replay_ordered == ordered
    assert replay_artifact == artifact


def test_path_persistence_rejects_large_regret_and_reanchors():
    ranker = _ranker(maximum_regret=0.01)
    first_a = _candidate(1, "route_a", 1)
    first_b = _candidate(2, "route_b", 1)
    ranker._path_persistent_scores(
        SimpleNamespace(turn=1),
        (
            _score("a:1", first_a, 1.0),
            _score("b:1", first_b, 0.9),
        ),
        {"a:1": first_a, "b:1": first_b},
        _calibrated())
    second_a = _candidate(1, "route_a", 2)
    second_b = _candidate(2, "route_b", 2)

    ordered, artifact = (
        ranker._path_persistent_scores(
            SimpleNamespace(turn=2),
            (
                _score("b:2", second_b, 1.0),
                _score("a:2", second_a, 0.5),
            ),
            {"a:2": second_a, "b:2": second_b},
            _calibrated()))

    assert ordered[0].operation_id == "b:2"
    assert not artifact["reordered"]
    assert artifact["fallback_reason"] == (
        "priority-regret-exceeded")


def test_path_persistence_abstains_without_calibration_and_protects_terminal():
    ranker = _ranker()
    move = _candidate(1, "route_a", 1)
    terminal = _candidate(
        2, "city_founding", 1,
        action_type="unit_build_city")
    scores = (
        _score("terminal", terminal, 1.0, reversible=False),
        _score("move", move, 0.99),
    )
    candidates = {
        "terminal": terminal,
        "move": move,
    }

    uncalibrated, first_artifact = (
        ranker._path_persistent_scores(
            SimpleNamespace(turn=1),
            scores, candidates,
            {"calibration": {
                "authority_active": False}}))
    protected, second_artifact = (
        ranker._path_persistent_scores(
            SimpleNamespace(turn=1),
            scores, candidates,
            _calibrated()))

    assert uncalibrated == scores
    assert first_artifact["fallback_reason"] == (
        "calibrated-transition-authority-required")
    assert protected == scores
    assert second_artifact["fallback_reason"] == (
        "terminal-or-irreversible-scalar-protected")
