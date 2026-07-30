"""GDO-8 support-aware contextual calibration and conductance tests."""

import os
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest


REPO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    CONTEXTUAL_TRANSITION_VALUE_MODEL_ID,
    ContextualCalibrationGate,
    ContextualOutcomeRecord,
    ContextualTransitionValueKey,
    ContextualTransitionValueModel,
    TransitionContextKey,
    TransitionValueKey,
    TransitionValueModel,
    TransitionValueObservation,
    candidate_transition_context,
)
from freeciv_agent.planning import ImpactCandidate  # noqa: E402


def _key(
        exact="terrain-plains",
        action="unit_move",
        category="movement",
        actor="unit:settlers",
        target="tile:land",
        threat="distant:4+",
        horizon="medium:4-10",
        lifecycle="route-progress",
        ruleset_digest="ruleset-a",
        ruleset_family="civ2civ3",
        goal="pf-impact:expansion",
        estimator=(
            CONTEXTUAL_TRANSITION_VALUE_MODEL_ID),
        policy="scalar-v2/1.0"):
    return ContextualTransitionValueKey(
        goal_id=goal,
        context=TransitionContextKey(
            exact_context_digest=exact,
            action_type=action,
            action_category=category,
            actor_class=actor,
            target_class=target,
            threat_bucket=threat,
            horizon_bucket=horizon,
            lifecycle_state=lifecycle,
            ruleset_digest=ruleset_digest,
            ruleset_family=ruleset_family),
        estimator_version=estimator,
        policy_version=policy)


def _outcome(
        index, key=None,
        predicted=0.8, realized=0.2,
        adverse=0.0,
        outcome_status="terminal",
        causal_status="eligible",
        stochastic=False):
    unknown = (
        outcome_status == "unknown"
        or causal_status == "unknown")
    return ContextualOutcomeRecord(
        observation_id="v2-outcome-{:03d}".format(
            index),
        key=key or _key(),
        selected_policy_id="scalar-v2",
        selection_policy_kind=(
            "stochastic"
            if stochastic else "deterministic"),
        selection_propensity=(
            0.5 if stochastic else None),
        action_id="action-{:03d}".format(index),
        operation_id="operation-{:03d}".format(
            index),
        predicted_transition_digest=(
            "prediction-{:03d}".format(index)),
        predicted_relief=predicted,
        realized_outcome_digest=(
            None if unknown
            else "realized-{:03d}".format(index)),
        realized_goal_relief=(
            None if unknown else realized),
        adverse_loss=(
            None if unknown else adverse),
        adverse_loss_status=(
            "unknown"
            if unknown else "observed"),
        eligibility_trace=(
            "authoritative-next-snapshot",
            "selected-action-identity-matched",
        ),
        causal_status=causal_status,
        outcome_status=outcome_status,
        estimator_version=(
            CONTEXTUAL_TRANSITION_VALUE_MODEL_ID),
        policy_version="scalar-v2/1.0",
        relief_source=(
            None if unknown
            else "authoritative:test-goal-relief"))


def _frozen(tmp_path, outcomes, **configuration):
    path = tmp_path / "contextual-value.json"
    training = ContextualTransitionValueModel(
        str(path), identity="gdo8-test",
        minimum_samples=configuration.get(
            "minimum_samples", 2),
        maximum_half_width=configuration.get(
            "maximum_half_width", 1.0),
        shrinkage_kappa=configuration.get(
            "shrinkage_kappa", 0.0))
    training.observe_many(tuple(outcomes))
    return ContextualTransitionValueModel(
        str(path), identity="gdo8-test",
        minimum_samples=configuration.get(
            "minimum_samples", 2),
        maximum_half_width=configuration.get(
            "maximum_half_width", 1.0),
        shrinkage_kappa=configuration.get(
            "shrinkage_kappa", 0.0),
        read_only=True)


def test_context_hierarchy_is_predeclared_and_exact():
    levels = tuple(
        row.level
        for row in
        _key().support_hierarchy())

    assert levels == (
        "exact-context",
        "action-actor-target-threat-horizon",
        "action-actor",
        "action-category",
        "global-prior",
    )


def test_candidate_context_uses_semantics_not_snapshot_identity():
    unit = SimpleNamespace(
        unit_id=7,
        unit_type="Settlers")
    candidate = ImpactCandidate(
        action={
            "action_type": "unit_move",
            "actor_id": 7,
            "target": {"x": 3, "y": 4},
        },
        category="expansion_move",
        utility=10.0,
        rationale="context test",
        projection={
            "threat_eta_turns": 5,
            "transition_context_features": {
                "terrain": "plains",
            },
        })
    first = SimpleNamespace(
        turn=10,
        snapshot_id="snapshot-a",
        unit=lambda unit_id: (
            unit if unit_id == 7 else None))
    second = SimpleNamespace(
        turn=10,
        snapshot_id="snapshot-b",
        unit=lambda unit_id: (
            unit if unit_id == 7 else None))

    first_key = candidate_transition_context(
        candidate, first,
        "ruleset-a", "civ2civ3",
        16, "pf-impact:expansion")
    second_key = candidate_transition_context(
        candidate, second,
        "ruleset-a", "civ2civ3",
        16, "pf-impact:expansion")

    assert first_key == second_key
    assert first_key.context.actor_class == (
        "unit:Settlers")
    assert first_key.context.threat_bucket == (
        "distant:4+")


def test_exact_contexts_back_off_only_to_declared_parent(tmp_path):
    first = _key(exact="plains")
    second = _key(exact="grassland")
    frozen = _frozen(
        tmp_path,
        (
            _outcome(1, first),
            _outcome(2, second),
        ))

    estimate = frozen.estimate(
        _key(exact="forest"), 0.8)

    assert estimate.calibrated
    assert estimate.sample_count == 2
    assert estimate.support_source == (
        "action-actor-target-threat-horizon")
    assert estimate.declared_parent.level == (
        "action-actor")
    assert estimate.expected_realized_relief == (
        pytest.approx(0.2))


def test_actor_and_ruleset_contexts_do_not_silently_pool(tmp_path):
    frozen = _frozen(
        tmp_path,
        (
            _outcome(1, _key()),
            _outcome(2, _key()),
        ))

    actor_mismatch = frozen.estimate(
        _key(
            actor="unit:warriors"),
        0.8)
    ruleset_mismatch = frozen.estimate(
        _key(
            ruleset_digest="ruleset-b",
            ruleset_family="classic"),
        0.8)

    assert actor_mismatch.calibrated
    assert actor_mismatch.support_source == (
        "action-category")
    assert actor_mismatch.sample_count == 2
    assert not ruleset_mismatch.calibrated
    assert ruleset_mismatch.sample_count == 0


def test_estimator_and_policy_versions_do_not_pool(tmp_path):
    frozen = _frozen(
        tmp_path,
        (
            _outcome(1),
            _outcome(2),
        ))

    policy_mismatch = frozen.estimate(
        _key(policy="scalar-v2/2.0"),
        0.8)
    estimator_mismatch = frozen.estimate(
        _key(estimator="different-estimator/1.0"),
        0.8)

    assert not policy_mismatch.calibrated
    assert policy_mismatch.sample_count == 0
    assert not estimator_mismatch.calibrated
    assert estimator_mismatch.sample_count == 0


def test_unknown_and_causally_ineligible_outcomes_are_excluded(tmp_path):
    path = tmp_path / "unknowns.json"
    model = ContextualTransitionValueModel(
        str(path), identity="unknown-test",
        minimum_samples=1,
        maximum_half_width=1.0,
        shrinkage_kappa=0.0)
    model.observe_many((
        _outcome(
            1, outcome_status="unknown",
            causal_status="unknown"),
        _outcome(
            2, causal_status="ineligible"),
    ))

    assert model.decision_snapshot()[
        "outcome_count"] == 2
    assert model.decision_snapshot()[
        "eligible_outcome_count"] == 0
    assert model.outcomes_for_support(
        _key().support_hierarchy()[0]) == ()


def test_unknown_adverse_loss_calibrates_relief_but_not_conductance(
        tmp_path):
    path = tmp_path / "unknown-adverse.json"
    model = ContextualTransitionValueModel(
        str(path), identity="unknown-adverse",
        minimum_samples=1,
        maximum_half_width=1.0,
        shrinkage_kappa=0.0)
    known_relief = _outcome(1)
    model.observe(replace(
        known_relief,
        adverse_loss=None,
        adverse_loss_status="unknown"))
    frozen = ContextualTransitionValueModel(
        str(path), identity="unknown-adverse",
        minimum_samples=1,
        maximum_half_width=1.0,
        shrinkage_kappa=0.0,
        read_only=True)

    estimate = frozen.estimate(_key(), 0.8)

    assert estimate.calibrated
    assert estimate.sample_count == 1
    assert estimate.conductance_sample_count == 0
    assert not estimate.conductance_supported


def test_stochastic_policy_requires_propensity():
    with pytest.raises(
            ValueError,
            match="requires propensity"):
        ContextualOutcomeRecord(
            observation_id="missing-propensity",
            key=_key(),
            selected_policy_id="explorer",
            selection_policy_kind="stochastic",
            selection_propensity=None,
            action_id="action",
            operation_id="operation",
            predicted_transition_digest="predicted",
            predicted_relief=0.5,
            realized_outcome_digest="realized",
            realized_goal_relief=0.5,
            adverse_loss=0.0,
            adverse_loss_status="observed",
            eligibility_trace=("matched",),
            causal_status="eligible",
            outcome_status="terminal",
            estimator_version=(
                CONTEXTUAL_TRANSITION_VALUE_MODEL_ID),
            policy_version="scalar-v2/1.0",
            relief_source="authoritative:test")


def test_frozen_model_is_immutable_and_serialization_is_deterministic(
        tmp_path):
    frozen = _frozen(
        tmp_path,
        (
            _outcome(1),
            _outcome(2),
        ))
    state_hash = frozen.state_hash

    assert frozen.snapshot() == (
        frozen.snapshot())
    with pytest.raises(
            ValueError, match="read-only"):
        frozen.observe(_outcome(3))
    assert frozen.state_hash == state_hash


def test_v1_migration_is_category_prior_not_exact_support(tmp_path):
    legacy_path = tmp_path / "legacy-v1.json"
    legacy = TransitionValueModel(
        str(legacy_path),
        identity="legacy",
        minimum_samples=1,
        maximum_half_width=1.0)
    legacy_key = TransitionValueKey(
        "movement", "route-progress",
        "pf-impact:expansion")
    legacy.observe(TransitionValueObservation(
        observation_id="legacy-row",
        key=legacy_key,
        predicted_relief=0.8,
        realized_relief=0.2,
        effect_observed=True,
        relief_source="authoritative:test",
        context_digest="legacy-context"))

    v2_path = tmp_path / "v2.json"
    v2 = ContextualTransitionValueModel(
        str(v2_path), identity="v2",
        minimum_samples=1,
        maximum_half_width=1.0)
    assert v2.import_legacy_v1(
        str(legacy_path), "civ2civ3")
    assert not v2.import_legacy_v1(
        str(legacy_path), "civ2civ3")
    estimate = v2.estimate(_key(), 0.8)

    assert v2.decision_snapshot()[
        "legacy_category_prior_count"] == 1
    assert v2.decision_snapshot()[
        "outcome_count"] == 0
    assert estimate.sample_count == 0
    assert not estimate.calibrated
    assert estimate.support_source == (
        "action-category")
    assert estimate.expected_realized_relief == (
        pytest.approx(0.2))
    assert estimate.decision_relief == 0.8
    assert estimate.abstention_reason == (
        "insufficient-declared-support")


def test_holdout_gate_improves_brier_without_evaluation_updates(
        tmp_path):
    frozen = _frozen(
        tmp_path,
        (
            _outcome(1),
            _outcome(2),
            _outcome(3),
            _outcome(4),
        ),
        shrinkage_kappa=0.0)
    state_hash = frozen.state_hash
    holdout = tuple(
        _outcome(index)
        for index in range(101, 109)) + (
            _outcome(
                109,
                outcome_status="unknown",
                causal_status="unknown"),)

    report = ContextualCalibrationGate(
        minimum_coverage=0.8,
        maximum_context_brier_regression=0.02,
        bootstrap_iterations=200
    ).evaluate(frozen, holdout)

    assert report["authority_approved"]
    assert report["aggregate"][
        "coverage"] == 1.0
    assert report["aggregate"][
        "unknown_or_ineligible_count"] == 1
    assert report["aggregate"][
        "contextual_brier"] == pytest.approx(0.0)
    assert report["aggregate"][
        "bootstrap_improvement_interval"][0] > 0.0
    assert frozen.state_hash == state_hash


def test_holdout_gate_rejects_training_overlap(tmp_path):
    training = _outcome(1)
    frozen = _frozen(
        tmp_path, (training, _outcome(2)))

    with pytest.raises(
            ValueError,
            match="overlap"):
        ContextualCalibrationGate(
            bootstrap_iterations=100
        ).evaluate(frozen, (training,))


def test_holdout_gate_rejects_supported_context_regression(
        tmp_path):
    frozen = _frozen(
        tmp_path,
        tuple(
            _outcome(index)
            for index in range(4)),
        shrinkage_kappa=0.0)
    holdout = tuple(
        _outcome(
            100 + index,
            predicted=0.8,
            realized=0.8)
        for index in range(4))

    report = ContextualCalibrationGate(
        minimum_coverage=0.8,
        maximum_context_brier_regression=0.02,
        bootstrap_iterations=100
    ).evaluate(frozen, holdout)

    assert not report["authority_approved"]
    assert not report["gates"][
        "aggregate_95pct_interval_excludes_no_improvement"]
    assert not report["gates"][
        "no_high_volume_context_regression"]
