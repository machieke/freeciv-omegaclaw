"""Decision-safe realized-relief calibration gates."""

import os
import sys
import tempfile

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning.impact import ImpactCandidate  # noqa: E402
from freeciv_agent.pressure import (  # noqa: E402
    TransitionValueKey,
    TransitionValueModel,
    TransitionValueObservation,
    candidate_action_category,
    candidate_lifecycle_state,
)


def _observation(
        index, key=None, predicted=0.6,
        realized=0.4, effect=True):
    return TransitionValueObservation(
        observation_id="outcome-{:03d}".format(index),
        key=key or TransitionValueKey(
            "expansion_move", "route-progress",
            "pf-impact:expansion"),
        predicted_relief=predicted,
        realized_relief=realized,
        effect_observed=effect,
        relief_source=(
            "authoritative:owned-city-count-progress"
            if realized else
            "authoritative:no-measurable-expansion-goal-progress"),
        context_digest="context-{:03d}".format(index),
        selection_propensity=None)


def test_transition_value_observations_are_idempotent_and_truth_free():
    model = TransitionValueModel(
        minimum_samples=2,
        maximum_half_width=1.0)
    observation = _observation(1)

    first = model.observe(observation)
    state_hash = model.state_hash
    duplicate = model.observe(observation)

    assert first.applied
    assert not duplicate.applied
    assert model.state_hash == state_hash
    assert model.snapshot()["update_scope"] == (
        "control-model-only")


def test_exact_category_lifecycle_support_is_not_pooled():
    model = TransitionValueModel(
        minimum_samples=2,
        maximum_half_width=1.0)
    route = TransitionValueKey(
        "expansion_move", "route-progress",
        "pf-impact:expansion")
    terminal = TransitionValueKey(
        "expansion_move", "terminal-completion",
        "pf-impact:expansion")
    model.observe(_observation(1, key=route))
    model.observe(_observation(2, key=route))

    supported = model.estimate(route, 0.6)
    mismatched = model.estimate(terminal, 0.6)

    assert supported.calibrated
    assert supported.sample_count == 2
    assert not mismatched.calibrated
    assert mismatched.sample_count == 0
    assert mismatched.abstention_reason == (
        "insufficient-exact-support")
    assert mismatched.decision_relief == 0.6


def test_calibration_corrects_bias_and_uses_conservative_decision_bound():
    model = TransitionValueModel(
        minimum_samples=2,
        maximum_half_width=1.0)
    model.observe(_observation(1, predicted=0.7, realized=0.4))
    model.observe(_observation(2, predicted=0.5, realized=0.4))

    estimate = model.estimate(
        _observation(1).key, 0.8)

    assert estimate.calibrated
    assert abs(estimate.residual_mean + 0.2) < 1e-12
    assert abs(estimate.expected_realized_relief - 0.6) < 1e-12
    assert estimate.decision_relief == estimate.lower_bound
    assert estimate.decision_relief <= (
        estimate.expected_realized_relief)


def test_frozen_model_reloads_with_stable_identity_and_rejects_updates():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "transition-value.json")
        training = TransitionValueModel(
            path=path, identity="frozen-test",
            minimum_samples=2,
            maximum_half_width=1.0)
        training.observe(_observation(1))
        training.observe(_observation(2))
        expected_hash = training.state_hash
        frozen = TransitionValueModel(
            path=path, identity="frozen-test",
            minimum_samples=2,
            maximum_half_width=1.0,
            read_only=True)

        assert frozen.state_hash == expected_hash
        assert frozen.estimate(
            _observation(1).key, 0.6).calibrated
        try:
            frozen.observe(_observation(3))
        except ValueError as error:
            assert "read-only" in str(error)
        else:
            raise AssertionError(
                "frozen transition model accepted an update")


def test_frozen_model_requires_existing_path():
    with tempfile.TemporaryDirectory() as directory:
        with pytest.raises(
                ValueError,
                match="does not exist"):
            TransitionValueModel(
                path=os.path.join(
                    directory, "missing.json"),
                identity="missing-frozen",
                read_only=True)


def test_lifecycle_classifier_separates_route_terminal_and_production():
    move = ImpactCandidate(
        {"action_type": "unit_move", "actor_id": 1},
        "expansion_move", 1.0, "move")
    found = ImpactCandidate(
        {"action_type": "unit_build_city", "actor_id": 1},
        "city_founding", 1.0, "found")
    production = ImpactCandidate(
        {"action_type": "city_production", "city_id": 2},
        "production_industrialization", 1.0, "build")

    assert candidate_lifecycle_state(move) == "route-progress"
    assert candidate_lifecycle_state(found) == "terminal-completion"
    assert candidate_lifecycle_state(production) == (
        "production-commitment")
    assert candidate_action_category(move) == "movement"
    assert candidate_action_category(found) == "settlement"
    assert candidate_action_category(production) == "production"


def test_transition_model_batch_is_atomic_and_persists_once():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory, "transition-batch.json")
        key = TransitionValueKey(
            "expansion", "route-progress",
            "pf-impact:expansion")
        model = TransitionValueModel(
            path, identity="batch-test",
            minimum_samples=2,
            maximum_half_width=1.0)
        rows = tuple(
            TransitionValueObservation(
                observation_id="batch-{}".format(index),
                key=key,
                predicted_relief=0.2,
                realized_relief=0.4,
                effect_observed=True,
                relief_source="authoritative:test",
                context_digest="context-{}".format(index))
            for index in range(3))
        updates = model.observe_many(rows)
        assert all(update.applied for update in updates)
        assert all(
            update.sample_count == 3
            for update in updates)
        assert len(set(
            update.model_state_hash
            for update in updates)) == 1
        frozen = TransitionValueModel(
            path, identity="batch-test",
            minimum_samples=2,
            maximum_half_width=1.0,
            read_only=True)
        assert frozen.state_hash == model.state_hash

        collision = TransitionValueObservation(
            observation_id="batch-1",
            key=key,
            predicted_relief=0.2,
            realized_relief=0.9,
            effect_observed=True,
            relief_source="authoritative:test",
            context_digest="collision")
        state_hash = model.state_hash
        with pytest.raises(
                ValueError,
                match="identity collision"):
            model.observe_many((
                TransitionValueObservation(
                    observation_id=(
                        "new-before-collision"),
                    key=key,
                    predicted_relief=0.2,
                    realized_relief=0.4,
                    effect_observed=True,
                    relief_source="authoritative:test",
                    context_digest="new"),
                collision,
            ))
        assert model.state_hash == state_hash
        assert all(
            row.observation_id
            != "new-before-collision"
            for row in model.observations_for(key))
