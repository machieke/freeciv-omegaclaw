import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (  # noqa: E402
    DecisionEpisode,
    DecisionEpisodeStore,
    EPISODE_SCHEMA_VERSION,
    EpisodeControlPrediction,
    FdasEpisodeLearningAdapter,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.pressure import (  # noqa: E402
    ContextualConductanceStore,
    ControlCalibrationLedger,
)


def _episode(
        episode_id, status, effects=(), relief=(),
        prediction_ids=("prediction-route",)):
    terminal = status in (
        "goal-relief-observed", "effect-without-goal-relief",
        "no-effect-observed", "confounded-unattributable")
    return DecisionEpisode(
        EPISODE_SCHEMA_VERSION,
        episode_id,
        "episode-learning",
        0,
        "operation-route",
        '{"action_type":"unit_move","actor_id":7}',
        "revision-before",
        "revision-after" if terminal else None,
        ("pf-impact:survival",),
        (("operation_type", "move_defender_to_city"),
         ("terrain", "land")),
        ("atom-source",),
        ("support-source",),
        ("grounding-route",),
        tuple(prediction_ids),
        ("claim-unit-7",),
        "validation-current",
        "execution-accepted",
        {} if terminal else None,
        tuple(effects),
        tuple(relief),
        status,
        ("episode-learning-test",),
    )


def _prediction():
    return EpisodeControlPrediction(
        "prediction-route",
        "operation-route",
        "route:defense",
        "defense-route-v1",
        0.7,
        0.8,
        (("cpu", 1.0), ("latency", 1.0)),
        None,
        "frontier:north",
        4,
    )


def _adapter(episodes):
    episode_store = DecisionEpisodeStore(
        "episode-learning-proof", tuple(episodes))
    conductance = ContextualConductanceStore()
    adapter = FdasEpisodeLearningAdapter(
        episode_store, (_prediction(),),
        ControlCalibrationLedger(), conductance)
    return adapter, conductance


def test_goal_relief_credits_contextual_route_once_without_truth_authority():
    episode = _episode(
        "episode-relief", "goal-relief-observed",
        effects=({"effect": "defender-arrived"},),
        relief=(("pf-impact:survival", 1.0),))
    adapter, conductance = _adapter((episode,))
    before = conductance.value(
        "route:defense",
        "defense-route-v1:episode-context-" + structural_hash(
            dict(episode.context_signature))[:24],
        "frontier:north", 4)

    first = adapter.apply(episode.episode_id, realized_cost=(("cpu", 1.0),))
    second = adapter.apply(episode.episode_id, realized_cost=(("cpu", 1.0),))

    assert first.applied is True
    assert first.conductance_update.value > before
    assert first.calibration_record.success is True
    assert first.calibration_record.realized_relief == 1.0
    assert first.truth_mutated is False
    assert first.policy_authority is False
    assert second.applied is False
    assert second.reason == "duplicate-episode-control-update"
    assert second.conductance_update.value == first.conductance_update.value


def test_live_prediction_registration_is_idempotent_and_collision_safe():
    adapter, _conductance = _adapter(())
    prediction = EpisodeControlPrediction(
        "prediction-live", "operation-live", "route:live", "defense-live",
        1.0, 1.0, (("action", 1.0),), 1.0, "frontier:live", 0)

    assert adapter.register_prediction(prediction) == prediction
    assert adapter.register_prediction(prediction) == prediction
    with pytest.raises(ValueError, match="collision"):
        adapter.register_prediction(EpisodeControlPrediction(
            "prediction-live", "operation-other", "route:live",
            "defense-live", 1.0, 1.0, (("action", 1.0),), 1.0,
            "frontier:live", 0))


def test_no_effect_and_effect_without_relief_are_distinct_no_progress_samples():
    no_effect = _episode("episode-no-effect", "no-effect-observed")
    effect_only = _episode(
        "episode-effect-only", "effect-without-goal-relief",
        effects=({"effect": "actor-tile-changed"},))
    adapter, conductance = _adapter((no_effect, effect_only))
    first = adapter.apply(no_effect.episode_id)
    second = adapter.apply(effect_only.episode_id)

    assert first.applied and second.applied
    assert first.calibration_record.success is False
    assert second.calibration_record.success is True
    assert first.calibration_record.realized_relief == 0.0
    assert second.calibration_record.realized_relief == 0.0
    assert first.calibration_record.relief_source.startswith(
        "authoritative-no-effect-window-closed")
    assert second.calibration_record.relief_source.startswith(
        "authoritative-effect-without-goal-relief")
    assert second.conductance_update.value < first.conductance_update.value
    assert conductance.state_hash


def test_pending_confounded_or_unlinked_episode_cannot_update_control():
    pending = _episode("episode-pending", "delayed-effect-pending")
    confounded = _episode(
        "episode-confounded", "confounded-unattributable")
    unlinked = _episode(
        "episode-unlinked", "no-effect-observed", prediction_ids=())
    adapter, conductance = _adapter((pending, confounded, unlinked))
    before = conductance.state_hash

    results = tuple(adapter.apply(value.episode_id) for value in (
        pending, confounded, unlinked))

    assert not any(value.applied for value in results)
    assert results[0].reason == (
        "episode-outcome-not-attributable-for-learning")
    assert results[1].reason == (
        "episode-outcome-not-attributable-for-learning")
    assert results[2].reason == (
        "episode-requires-one-current-control-prediction")
    assert conductance.state_hash == before


def test_learning_metrics_and_explanations_are_read_only_and_episode_linked():
    relief = _episode(
        "episode-relief", "goal-relief-observed",
        effects=({"effect": "defender-arrived"},),
        relief=(("pf-impact:survival", 1.0),))
    no_effect = _episode("episode-no-effect", "no-effect-observed")
    confounded = _episode(
        "episode-confounded", "confounded-unattributable")
    adapter, conductance = _adapter((relief, no_effect, confounded))
    before = conductance.state_hash

    pending_explanation = adapter.explain(relief.episode_id)
    assert pending_explanation.learning_eligible is True
    assert pending_explanation.reason == "eligible-not-yet-applied"
    assert pending_explanation.calibration_record is None
    assert conductance.state_hash == before

    adapter.apply(relief.episode_id)
    adapter.apply(no_effect.episode_id)
    report = adapter.metrics()
    explanation = adapter.explain(relief.episode_id)
    abstention = adapter.explain(confounded.episode_id)
    after = conductance.state_hash

    assert report.episode_count == 3
    assert report.attributable_terminal_count == 2
    assert report.confounded_count == 1
    assert report.calibration_sample_count == 2
    assert report.contextual_route_count == 1
    assert report.mean_absolute_relief_error == 0.5
    assert round(report.success_brier_score, 8) == 0.34
    assert report.outcome_counts == (
        ("confounded-unattributable", 1),
        ("goal-relief-observed", 1),
        ("no-effect-observed", 1),
    )
    assert report.truth_mutated is False
    assert report.policy_authority is False
    assert explanation.calibration_record.episode_id == relief.episode_id
    assert explanation.contextual_conductance == (
        conductance.snapshot()["routes"][0]["value"])
    assert explanation.reason == "contextual-control-sample-recorded"
    assert abstention.learning_eligible is False
    assert abstention.calibration_record is None
    assert conductance.state_hash == after


def test_conductance_snapshot_is_deterministic_and_does_not_expose_mutators():
    episode = _episode("episode-relief", "goal-relief-observed",
                       effects=({"effect": "defender-arrived"},),
                       relief=(("pf-impact:survival", 1.0),))
    adapter, conductance = _adapter((episode,))
    adapter.apply(episode.episode_id)

    first = conductance.snapshot()
    second = conductance.snapshot()

    assert first == second
    assert structural_hash(first) == conductance.state_hash
    assert first["routes"][0]["key"]["route_id"] == "route:defense"
    first["routes"][0]["value"] = 0.0
    assert conductance.snapshot()["routes"][0]["value"] > 0.5
