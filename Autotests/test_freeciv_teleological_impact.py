"""Opt-in live Impact teleology and strong-scalar feature parity gates."""

import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for candidate in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks"),
):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from freeciv.pf_unified.teleology_benchmark import (  # noqa: E402
    run_g2_verification,
)
from freeciv_agent.planning import GroundedImpactPlanner  # noqa: E402
from freeciv_agent.pressure import (  # noqa: E402
    ContextualTransitionValueModel,
    CostVector,
    ImpactPressureRankerV2,
    Operation,
    SmoothedScalarController,
    TypedAdvantage,
)
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


def _snapshot():
    path = os.path.join(
        REPO, "benchmarks", "freeciv", "samples",
        "real_state_turn1.json")
    with open(path, encoding="utf-8") as stream:
        return ProxyStateDTO.parse(
            "teleological-impact", 1,
            json.load(stream)).to_snapshot()


def test_live_impact_emits_complete_teleological_path_and_stays_legal():
    snapshot = _snapshot()
    candidates = GroundedImpactPlanner({
        "pressure_enabled": False}).candidates(snapshot)
    before = snapshot.event_payload()
    ranker = ImpactPressureRankerV2(
        teleological_enabled=True)

    ordered, artifact = ranker.rank(
        snapshot, candidates,
        expansion_city_target=5,
        horizon_turn=int(snapshot.turn) + 200)

    teleology = artifact["teleology"]
    selected_id = artifact["schedule"][
        "selected_operation_id"]
    selected = next(
        row for row in artifact["schedule"]["scores"]
        if row["operation"]["operation_id"] == selected_id)
    estimate = next(
        row for row in teleology["operation_estimates"]
        if row["operation_id"] == selected_id)

    assert ordered[0].action_key in {
        row.action_key for row in candidates}
    assert snapshot.event_payload() == before
    assert teleology["goal_losses"]
    assert estimate["cost_to_go"]["estimator_id"].startswith(
        "grounded-impact-one-step:")
    assert estimate["transition"]["operation_id"] == selected_id
    assert estimate["leverage"]["method"] == "counterfactual"
    assert estimate["advantage"] == selected["operation"][
        "typed_advantages"][0]
    assert selected["scalar_cost"] == sum(
        selected["operation"]["cost"].values())


def test_teleological_impact_is_deterministic_for_same_snapshot():
    snapshot = _snapshot()
    candidates = GroundedImpactPlanner({
        "pressure_enabled": False}).candidates(snapshot)
    ranker = ImpactPressureRankerV2(
        teleological_enabled=True)
    arguments = {
        "expansion_city_target": 5,
        "horizon_turn": int(snapshot.turn) + 200,
    }

    first = ranker.rank(
        snapshot, candidates, **arguments)[1]
    second = ranker.rank(
        snapshot, candidates, **arguments)[1]

    assert first["teleology"] == second["teleology"]
    assert first["schedule"] == second["schedule"]


def test_contextual_v2_shadow_records_versioned_outcome_without_authority():
    snapshot = _snapshot()
    candidates = GroundedImpactPlanner({
        "pressure_enabled": False}).candidates(snapshot)
    model = ContextualTransitionValueModel(
        identity="live-shadow-test",
        minimum_samples=1,
        maximum_half_width=1.0,
        shrinkage_kappa=0.0)
    ranker = ImpactPressureRankerV2(
        teleological_enabled=True,
        ruleset_digest="test-ruleset-digest",
        contextual_ruleset_family="test-ruleset",
        contextual_transition_value_model=model)

    ordered, artifact = ranker.rank(
        snapshot, candidates,
        expansion_city_target=5,
        horizon_turn=int(snapshot.turn) + 6)
    update = ranker.record_transition_outcome(
        ordered[0],
        effect_observed=False,
        realized_relief=0.0,
        relief_source="authoritative:test-no-effect",
        feedback_id="contextual-live-outcome")

    calibration = artifact[
        "teleology"]["calibration"]
    estimate = artifact[
        "teleology"][
            "operation_estimates"][0][
                "transition_value"]
    assert not calibration["authority_active"]
    assert calibration["model"][
        "schema_version"] == "2.0"
    assert estimate["key"][
        "schema_version"] == "2.0"
    assert update.observation.outcome_status == (
        "no-effect")
    assert update.observation.adverse_loss is None
    assert update.observation.adverse_loss_status == (
        "unknown")
    assert model.decision_snapshot()[
        "outcome_count"] == 1


def test_strong_scalar_consumes_same_typed_advantage_with_one_cost():
    advantage = TypedAdvantage(
        "goal", "target", "act",
        expected_relief=3.0,
        relief_variance=0.2,
        information_gain=0.5,
        option_value=0.25,
        predicted_latency=1.0,
        predicted_resource_use=(),
        estimator_id="test")
    operation = Operation(
        "route", "target", "act",
        CostVector(compute=2.0),
        causal_kind="procedural",
        typed_advantages=(advantage,))

    bid = SmoothedScalarController.bid_from_typed_operation(
        operation)

    assert bid.pf_advantage == advantage.pre_cost_value
    assert bid.instantaneous_score == -2.0
    assert bid.combined_score == 1.75


def test_g2_verification_gate_covers_live_parity_and_contracts():
    report = run_g2_verification()

    assert report["valid"]
    assert report["claim_status"] == "implementation-acceptance-only"
    assert report["live_impact"]["complete_teleological_paths"]
    assert report["live_impact"]["operation_estimate_count"] == (
        report["live_impact"]["candidate_count"])
    assert report["calibration"]["relief_plot"]
    assert not report["calibration"]["claim_eligible"]
    assert report["no_bridge_or_flow_required"]
