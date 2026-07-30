"""Grounded production queue estimates and completion boundaries."""

import json
import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402
from freeciv_agent.planning import ImpactCandidate  # noqa: E402
from freeciv_agent.planning.domain_models import (  # noqa: E402
    DomainEstimateRequest,
    EstimateAuthority,
    EstimateValidity,
    GroundedProductionTransitionModel,
    production_target_profile,
)
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402


CAPTURE = os.path.join(
    REPO, "benchmarks", "gdo",
    "captured_snapshots",
    "city_defense_grounded_160",
    "turn-153-201813e66ed0eb66.json")
RULESET_ROOT = os.path.join(
    REPO, "build", "freeciv",
    "ruleset-source")


def _rule(
        name="Riflemen",
        target_kind="unit",
        cost=50):
    return SimpleNamespace(
        target_kind=target_kind,
        display_name=name,
        rule_name=name,
        rule_id="rule:{}".format(name),
        quantitative={
            "build_cost": {
                "value": cost,
            },
            "happy_cost": {
                "value": 0,
            },
            "pop_cost": {
                "value": 0,
            },
            "uk_food": {
                "value": 1,
            },
            "uk_gold": {
                "value": 1,
            },
            "uk_shield": {
                "value": 1,
            },
            "upkeep": {
                "value": 0,
            },
        },
        traits={
            "class": {
                "values": ["Land"],
            },
            "flags": {
                "values": ["Capturer"],
            },
            "roles": {
                "values": ["DefendGood"],
            },
        })


def _action(
        target="Riflemen",
        kind=6, value=10):
    return {
        "action_type":
            "city_production",
        "city_id": 103,
        "production_kind": kind,
        "production_value": value,
        "target": {
            "production_type":
                target,
        },
    }


def _snapshot(
        action=None, current_kind=6,
        current_value=10,
        stock=30, rate=2):
    action = action or _action()
    target_name = action[
        "target"][
            "production_type"]
    buildable_kind = (
        "unit"
        if action[
            "production_kind"] == 6
        else "improvement")
    city = SimpleNamespace(
        city_id=103,
        owner=0,
        name="Roma",
        production_kind=current_kind,
        production_value=current_value,
        shield_stock=stock,
        surplus=(
            1, rate, 4, 3, 0, 2),
        buildability_available=True,
        buildable=((
            buildable_kind,
            action["production_value"],
            target_name),))
    return SimpleNamespace(
        player_id=0,
        turn=72,
        snapshot_id="snapshot",
        legal_actions_digest="legal",
        legal_action_json=(
            canonical_json_bytes(
                action).decode("utf-8"),),
        city=lambda city_id: (
            city if city_id == 103
            else None))


def _request(
        snapshot, action,
        ruleset=None, utility=100.0,
        horizon=90):
    return DomainEstimateRequest(
        request_id="p" * 64,
        snapshot=snapshot,
        ruleset_ir=(
            ruleset
            or SimpleNamespace(
                rules=(_rule(),))),
        legal_action=action,
        candidate=ImpactCandidate(
            action=action,
            category=(
                "production_defense"),
            utility=utility,
            rationale=(
                "test production")),
        goal_losses=((
            "pf-impact:defense",
            2.0),),
        operation_context=None,
        validity=EstimateValidity(
            "snapshot", "legal",
            "ruleset", 72, 72),
        horizon_turn=horizon)


def test_current_queue_has_grounded_eta_and_no_immediate_product():
    action = _action()
    estimate = (
        GroundedProductionTransitionModel()
        .estimate(
            _request(
                _snapshot(action),
                action)))
    artifact = estimate.to_dict()[
        "model_artifact"]

    assert estimate.authority == (
        EstimateAuthority
        .DETERMINISTIC_DERIVED)
    assert artifact[
        "current_production"][
            "same_target"]
    assert artifact[
        "switch_cost"][
            "status"] == "none"
    assert artifact[
        "completion_eta"][
            "earliest_turns"] == 10
    assert artifact[
        "completion_eta"][
            "latest_turns"] == 10
    assert not artifact[
        "availability"][
            "product_available_now"]
    assert not artifact[
        "availability"][
            "unit_under_construction_is_participant"]
    outcome = (
        estimate.transition
        .outcomes[0])
    assert outcome.completion_turn == 72
    assert dict(
        outcome.next_goal_features
    ) == {
        "pf-impact:defense": 2.0,
    }


def test_switch_exposes_history_uncertainty_and_conservative_eta_window():
    action = _action()
    snapshot = _snapshot(
        action,
        current_kind=3,
        current_value=14,
        stock=30,
        rate=2)

    estimate = (
        GroundedProductionTransitionModel()
        .estimate(
            _request(
                snapshot, action,
                horizon=80)))
    artifact = estimate.to_dict()[
        "model_artifact"]

    assert artifact[
        "switch_cost"][
            "status"] == "unresolved"
    assert "changed_from" in artifact[
        "switch_cost"][
            "missing_history_fields"]
    assert artifact[
        "completion_eta"][
            "earliest_turns"] == 1
    assert artifact[
        "completion_eta"][
            "latest_turns"] == 25
    assert artifact[
        "completion_eta"][
            "possible_by_request_horizon"]
    assert not artifact[
        "completion_eta"][
            "guaranteed_by_request_horizon"]


def test_zero_shield_output_is_explicitly_stalled():
    action = _action()
    estimate = (
        GroundedProductionTransitionModel()
        .estimate(
            _request(
                _snapshot(
                    action,
                    stock=10,
                    rate=0),
                action)))
    eta = estimate.to_dict()[
        "model_artifact"][
            "completion_eta"]

    assert eta["status"] == (
        "stalled-current-output")
    assert eta[
        "earliest_turns"] is None
    assert eta[
        "latest_turns"] is None
    assert not eta[
        "possible_by_request_horizon"]


def test_unadvertised_or_nonbuildable_target_abstains():
    action = _action()
    snapshot = _snapshot(action)
    snapshot.legal_action_json = ()

    estimate = (
        GroundedProductionTransitionModel()
        .estimate(
            _request(
                snapshot, action)))

    assert estimate.authority == (
        EstimateAuthority.ABSTAIN)
    assert "advertised_legal_action" in (
        estimate.to_dict()[
            "model_artifact"][
                "missing_fields"])


def test_production_estimate_is_candidate_utility_invariant():
    action = _action()
    snapshot = _snapshot(action)
    model = (
        GroundedProductionTransitionModel())

    first = model.estimate(
        _request(
            snapshot, action,
            utility=1.0))
    second = model.estimate(
        _request(
            snapshot, action,
            utility=1000000.0))

    assert first == second


def test_compiled_civ2civ3_profile_and_captured_action_match():
    with open(
            CAPTURE,
            encoding="utf-8") as stream:
        capture = json.load(stream)
    event = capture[
        "snapshot_event"]
    payload = event["payload"]
    city_payload = next(
        row for row in
        payload["own_state"]["cities"]
        if row["city_id"] == 109)
    action = next(
        row for row in
        payload[
            "grounded_context"][
                "legal_actions"]
        if (
            row.get(
                "action_type")
                == "city_production"
            and row.get(
                "city_id") == 109
            and row.get(
                "target", {}).get(
                    "production_type")
                == "Riflemen"))
    city = SimpleNamespace(
        city_id=city_payload[
            "city_id"],
        owner=city_payload["owner"],
        name=city_payload["name"],
        production_kind=(
            city_payload[
                "production_kind"]),
        production_value=(
            city_payload[
                "production_value"]),
        shield_stock=city_payload[
            "shield_stock"],
        surplus=tuple(
            city_payload["surplus"]),
        buildability_available=(
            city_payload[
                "buildability_available"]),
        buildable=tuple(
            tuple(row)
            for row in
            city_payload["buildable"]))
    snapshot = SimpleNamespace(
        player_id=payload[
            "player_id"],
        turn=event["turn"],
        snapshot_id=payload[
            "snapshot_id"],
        legal_actions_digest=payload[
            "legal_actions_digest"],
        legal_action_json=tuple(
            canonical_json_bytes(
                row).decode("utf-8")
            for row in payload[
                "grounded_context"][
                    "legal_actions"]),
        city=lambda city_id: (
            city if city_id
            == city.city_id else None))
    ruleset = compile_ruleset(
        RULESET_ROOT,
        "civ2civ3")

    profile = (
        production_target_profile(
            ruleset,
            "Riflemen"))
    estimate = (
        GroundedProductionTransitionModel()
        .estimate(
            _request(
                snapshot, action,
                ruleset=ruleset,
                horizon=200)))
    artifact = estimate.to_dict()[
        "model_artifact"]

    assert profile.build_cost == 50
    assert profile.food_upkeep == 1
    assert profile.shield_upkeep == 1
    assert profile.gold_upkeep == 1
    assert artifact[
        "buildability"] == {
            "option_id": 10,
            "option_kind": "unit",
            "option_name": "Riflemen",
            "source":
                "authoritative-city-buildability",
        }
    assert not artifact[
        "current_production"][
            "same_target"]
    assert artifact[
        "switch_cost"][
            "status"] == "unresolved"
