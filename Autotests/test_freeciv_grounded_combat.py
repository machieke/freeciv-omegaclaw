"""Finite duel mechanics and conservative grounded combat readout."""

import copy
import json
import os
import random
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import ImpactCandidate  # noqa: E402
from freeciv_agent.planning.domain_models import (  # noqa: E402
    DomainEstimateRequest,
    EstimateAuthority,
    EstimateValidity,
    GroundedCombatTransitionModel,
    finite_duel_distribution,
)
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


def _unit_rule(
        name, attack, defense, hp,
        firepower, cost):
    return SimpleNamespace(
        target_kind="unit",
        display_name=name,
        rule_name=name,
        rule_id="unit:{}".format(name),
        quantitative={
            "attack": {"value": attack},
            "defense": {"value": defense},
            "hitpoints": {"value": hp},
            "firepower": {"value": firepower},
            "build_cost": {"value": cost},
        })


def _ruleset():
    return SimpleNamespace(rules=(
        _unit_rule(
            "Warriors", 1, 1, 10, 1, 10),
        _unit_rule(
            "Phalanx", 1, 2, 10, 1, 20),
    ))


def _combat_snapshot(context=True, veteran=0):
    path = os.path.join(
        REPO, "benchmarks", "freeciv",
        "samples", "real_state_turn1.json")
    with open(path, encoding="utf-8") as stream:
        payload = json.load(stream)
    payload = copy.deepcopy(payload)
    payload["units"]["102"].update({
        "activity": "idle",
        "hp": 10,
        "transported": False,
        "type": "Warriors",
        "veteran": veteran,
    })
    payload["units"]["999"] = {
        "activity": "idle",
        "done_moving": False,
        "hp": 10,
        "id": 999,
        "moves_left": 3,
        "owner": 1,
        "tile": 1982,
        "transported": False,
        "type": "Phalanx",
        "type_id": 2,
        "veteran": 0,
        "x": 14,
        "y": 41,
    }
    action = {
        "action_type": "unit_attack",
        "actor_id": 102,
        "is_valid": True,
        "target": {
            "target_unit_id": 999,
            "x": 14,
            "y": 41,
        },
    }
    if context:
        action["combat_context"] = {
            "attacker_advances_on_win": True,
            "city_defense_multiplier": 1.0,
            "city_target": False,
            "effects_complete": True,
            "fortification_multiplier": 1.0,
            "selected_defender_id": 999,
            "terrain_defense_multiplier": 1.0,
        }
    payload["legal_actions"]["102"].append(
        action)
    snapshot = ProxyStateDTO.parse(
        "grounded-combat", 1,
        payload).to_snapshot()
    normalized = next(
        json.loads(value)
        for value in snapshot.legal_action_json
        if json.loads(value).get(
            "action_type") == "unit_attack")
    return snapshot, normalized


def _request(snapshot, action, utility=900.0):
    return DomainEstimateRequest(
        request_id="c" * 64,
        snapshot=snapshot,
        ruleset_ir=_ruleset(),
        legal_action=action,
        candidate=ImpactCandidate(
            action, "tactical_attack",
            utility, "test"),
        goal_losses=(
            ("pf-impact:survival", 2.0),),
        operation_context=None,
        validity=EstimateValidity(
            snapshot.snapshot_id,
            snapshot.legal_actions_digest,
            "ruleset",
            snapshot.turn,
            snapshot.turn),
        horizon_turn=snapshot.turn + 1)


def test_finite_duel_conserves_mass_and_is_symmetric():
    duel = finite_duel_distribution(
        1, 1, 1, 1, 1, 1)

    assert duel.attacker_win_probability == pytest.approx(
        0.5)
    assert duel.defender_win_probability == pytest.approx(
        0.5)
    assert sum(
        row.probability
        for row in duel.terminal_outcomes
    ) == pytest.approx(1.0)


def test_damaged_defender_increases_target_destruction_probability():
    healthy = finite_duel_distribution(
        1, 2, 10, 10, 1, 1)
    damaged = finite_duel_distribution(
        1, 2, 10, 2, 1, 1)

    assert (
        damaged.attacker_win_probability
        > healthy.attacker_win_probability)


def test_finite_duel_randomized_probability_mass_and_material_bounds():
    rng = random.Random(20260730)
    for _ in range(200):
        attacker_hp = rng.randint(1, 40)
        defender_hp = rng.randint(1, 40)
        attacker_cost = rng.randint(1, 300)
        defender_cost = rng.randint(1, 300)
        duel = finite_duel_distribution(
            rng.randint(1, 30),
            rng.randint(1, 30),
            attacker_hp,
            defender_hp,
            rng.randint(1, 10),
            rng.randint(1, 10))

        assert sum(
            row.probability
            for row in duel.terminal_outcomes
        ) == pytest.approx(1.0)
        assert 0.0 <= (
            duel.attacker_win_probability
        ) <= 1.0
        assert 0.0 <= (
            duel.expected_friendly_shield_loss(
                attacker_cost)
        ) <= attacker_cost
        assert 0.0 <= (
            duel.expected_enemy_shield_loss(
                defender_cost)
        ) <= defender_cost


def test_finite_duel_rejects_unbounded_terminal_distribution():
    with pytest.raises(
            ValueError,
            match="terminal-outcome budget"):
        finite_duel_distribution(
            1, 1, 10001, 10001, 1, 1)


def test_combat_abstains_for_invalid_ruleset_mechanics():
    snapshot, action = _combat_snapshot()
    invalid_ruleset = SimpleNamespace(
        rules=(
            _unit_rule(
                "Warriors", 1, 1,
                10, 0, 10),
            _unit_rule(
                "Phalanx", 1, 2,
                10, 1, 20),
        ))
    request = _request(
        snapshot, action)
    request = replace(
        request,
        ruleset_ir=invalid_ruleset)

    estimate = GroundedCombatTransitionModel().estimate(
        request)

    assert estimate.authority == EstimateAuthority.ABSTAIN
    assert estimate.abstention_reason == (
        "combat-nonpositive-mechanics")


def test_explicit_unmodified_combat_is_heuristic_until_native_parity():
    snapshot, action = _combat_snapshot()
    estimate = GroundedCombatTransitionModel().estimate(
        _request(snapshot, action))
    artifact = estimate.to_dict()[
        "model_artifact"]

    assert estimate.authority == (
        EstimateAuthority.HEURISTIC)
    assert estimate.transition.residual_probability == 0.0
    assert (
        estimate.transition.modeled_probability
        == pytest.approx(1.0))
    assert 0.0 < artifact[
        "probability_target_destroyed"] < 1.0
    assert artifact[
        "probability_attacker_survives"] == (
            artifact[
                "probability_target_destroyed"])
    assert artifact[
        "expected_friendly_shield_equivalent_loss"] >= 0.0
    assert artifact[
        "expected_enemy_shield_equivalent_loss"] >= 0.0
    assert artifact["parity_status"] == "unverified"


def test_combat_probability_is_candidate_utility_invariant():
    snapshot, action = _combat_snapshot()
    model = GroundedCombatTransitionModel()

    first = model.estimate(
        _request(snapshot, action, 1.0))
    second = model.estimate(
        _request(snapshot, action, 999999.0))

    assert first == second


def test_combat_abstains_without_context_or_for_veteran_modifier():
    absent_snapshot, absent_action = (
        _combat_snapshot(context=False))
    veteran_snapshot, veteran_action = (
        _combat_snapshot(veteran=1))
    model = GroundedCombatTransitionModel()

    absent = model.estimate(
        _request(
            absent_snapshot,
            absent_action))
    veteran = model.estimate(
        _request(
            veteran_snapshot,
            veteran_action))

    assert absent.authority == (
        EstimateAuthority.ABSTAIN)
    assert "combat_context" in (
        absent.to_dict()[
            "model_artifact"][
                "missing_fields"])
    assert veteran.authority == (
        EstimateAuthority.ABSTAIN)
    assert "attacker_veteran_modifier" in (
        veteran.to_dict()[
            "model_artifact"][
                "missing_fields"])


def test_unsupported_combat_kind_and_multiple_defenders_abstain():
    snapshot, action = _combat_snapshot()
    bombard = dict(action)
    bombard["action_type"] = "unit_bombard"
    bombard_estimate = (
        GroundedCombatTransitionModel().estimate(
            _request(snapshot, bombard)))
    assert bombard_estimate.authority == (
        EstimateAuthority.ABSTAIN)
    assert bombard_estimate.abstention_reason == (
        "unsupported-combat-action-kind")

    defender = snapshot.visible_enemy_units[0]
    ambiguous_action = copy.deepcopy(action)
    ambiguous_action["target"].pop(
        "target_unit_id")
    ambiguous_snapshot = replace(
        snapshot,
        visible_enemy_units=(
            snapshot.visible_enemy_units
            + (replace(
                defender, unit_id=998),)),
        legal_action_json=tuple(sorted(
            set(snapshot.legal_action_json)
            | {
                json.dumps(
                    ambiguous_action,
                    sort_keys=True,
                    separators=(",", ":"))
            })))
    ambiguous = GroundedCombatTransitionModel().estimate(
        _request(
            ambiguous_snapshot,
            ambiguous_action))

    assert ambiguous.authority == (
        EstimateAuthority.ABSTAIN)
    assert "unique_selected_defender" in (
        ambiguous.to_dict()[
            "model_artifact"][
                "missing_fields"])
