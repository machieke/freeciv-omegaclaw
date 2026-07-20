"""Grounded impact-policy selection, safety, and diversity regressions."""

import json
import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (GroundedImpactPlanner, ImpactCandidate,
                                    ImpactTurnBudget)  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


def _snapshot(units, actions, cities=None, source_seq=1, turn=4, city_surplus=None):
    cities = cities if cities is not None else [{
        "id": 10, "owner": 0, "name": "Rome", "tile": 0, "x": 0, "y": 0,
        "size": 2, "production_kind": 6, "production_value": 11,
        "food_stock": 4, "shield_stock": 0,
        "surplus": [1, 4, 2, 1, 0, 3], "prod": [2, 5, 3, 1, 0, 4],
        "buildability": {"available": True, "options": [
            {"type": "unit", "id": 0, "name": "Settlers"},
            {"type": "unit", "id": 11, "name": "Alpine Troops"},
            {"type": "improvement", "id": 14, "name": "Granary"},
            {"type": "improvement", "id": 17, "name": "Library"},
        ]},
    }]
    if city_surplus is not None:
        cities[0]["surplus"] = list(city_surplus)
    payload = {
        "format": "pln_authoritative", "turn": turn, "phase": "movement",
        "player_id": 0,
        "authoritative": {
            "source_seq": source_seq,
            "player": {"gold": 30, "gold_per_turn": 3, "tax": 40,
                       "science": 60, "luxury": 0},
            "research": {"researching": 5, "researching_name": "Writing",
                         "researching_cost": 40, "bulbs_researched": 10,
                         "beakers_per_turn": 5},
            "ruleset": {"ready": True},
        },
        "techs": {"player0": ["Alphabet"]},
        "units": {str(row["id"]): row for row in units},
        "cities": {str(row["id"]): row for row in cities},
        "map": {"width": 10, "height": 10, "tiles": []},
        "visible_tiles": [], "legal_actions": actions,
    }
    return ProxyStateDTO.parse("impact-test", source_seq, payload).to_snapshot()


def _unit(unit_id, unit_type, x=0, y=0):
    return {"id": unit_id, "owner": 0, "type": unit_type, "type_id": unit_id,
            "tile": y * 10 + x, "x": x, "y": y, "moves_left": 3,
            "hp": 20, "activity": "idle", "upkeep": [0, 0, 0, 0, 0, 0]}


def _enemy(unit_id, unit_type, x, y):
    row = _unit(unit_id, unit_type, x, y)
    row["owner"] = 1
    return row


def _production(city_id, name, kind, value):
    return {"action_type": "city_production", "city_id": city_id,
            "target": {"production_type": name}, "production_kind": kind,
            "production_value": value, "is_valid": True}


def _ruleset_ir(costs):
    return SimpleNamespace(rules=tuple(SimpleNamespace(
        target_kind=kind, display_name=name, rule_name=name,
        quantitative={"build_cost": {"value": cost, "source": {}}})
        for name, kind, cost in costs))


def test_policy_produces_founder_then_infrastructure_without_midbuild_switching():
    actions = [
        _production(10, "Settlers", 6, 0),
        _production(10, "Alpine Troops", 6, 11),
        _production(10, "Granary", 3, 14),
        _production(10, "Library", 3, 17),
        {"action_type": "end_turn", "is_valid": True},
    ]
    planner = GroundedImpactPlanner({"expansion_city_target": 3})
    without_founder = _snapshot([_unit(11, "Alpine Troops")], actions)
    decision = planner.plan(without_founder)
    assert decision.candidate.category == "production_expansion"
    assert decision.candidate.action["target"]["production_type"] == "Settlers"

    with_founder = _snapshot([
        _unit(1, "Settlers"), _unit(11, "Alpine Troops")], actions, source_seq=2)
    planner = GroundedImpactPlanner(ruleset_ir=_ruleset_ir((
        ("Settlers", "unit", 30), ("Alpine Troops", "unit", 60),
        ("Granary", "improvement", 40), ("Library", "improvement", 60),
    )))
    decision = planner.plan(with_founder)
    assert decision.candidate.category == "production_economy"
    assert decision.candidate.action["target"]["production_type"] == "Library"
    assert decision.candidate.projection["build_cost"] == 60
    assert decision.candidate.projection["completion_eta_turns"] == 15
    assert decision.candidate.projection["cost_source"] == "ruleset_ir"

    granary_city = [dict(json.loads(json.dumps(with_founder.cities[0].to_dict())),
                         id=10, production_kind=3, production_value=14)]
    granary_city[0]["buildability"] = {"available": True, "options": [
        {"type": kind, "id": item_id, "name": option_name}
        for kind, item_id, option_name in with_founder.cities[0].buildable]}
    granary_city[0]["prod"] = granary_city[0].pop("production")
    granary_city[0].pop("buildability_available", None)
    granary_city[0].pop("buildability_diagnostic", None)
    zero_stock_switch = GroundedImpactPlanner().plan(_snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")], actions,
        cities=granary_city, source_seq=4))
    assert zero_stock_switch.candidate.action["target"]["production_type"] == "Library"

    midbuild_city = [dict(json.loads(json.dumps(with_founder.cities[0].to_dict())),
                          id=10, shield_stock=7)]
    # Convert typed buildability tuples back to the proxy option dialect.
    midbuild_city[0]["buildability"] = {"available": True, "options": [
        {"type": kind, "id": item_id, "name": name}
        for kind, item_id, name in with_founder.cities[0].buildable]}
    midbuild_city[0]["prod"] = midbuild_city[0].pop("production")
    midbuild_city[0].pop("buildability_available", None)
    midbuild_city[0].pop("buildability_diagnostic", None)
    assert GroundedImpactPlanner().plan(_snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")], actions,
        cities=midbuild_city, source_seq=3)) is None


def test_founder_moves_outward_then_founds_only_at_configured_spacing():
    move_near = {"action_type": "unit_move", "actor_id": 1,
                 "target": {"x": 1, "y": 0}, "is_valid": True}
    move_far = {"action_type": "unit_move", "actor_id": 1,
                "target": {"x": 2, "y": 0}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")],
        [move_near, move_far, {"action_type": "end_turn", "is_valid": True}])
    decision = GroundedImpactPlanner().plan(snapshot)
    assert decision.candidate.category == "expansion_move"
    assert decision.candidate.action["target"] == {"x": 2, "y": 0}

    build = {"action_type": "unit_build_city", "actor_id": 1, "is_valid": True}
    spaced = _snapshot(
        [_unit(1, "Settlers", 3, 0), _unit(11, "Alpine Troops")],
        [build, {"action_type": "end_turn", "is_valid": True}], source_seq=2)
    decision = GroundedImpactPlanner({"settle_min_distance": 3}).plan(spaced)
    assert decision.candidate.category == "city_founding"
    assert decision.plan.steps[0].target == decision.candidate.action
    assert decision.candidate.action == {"action_type": "unit_build_city", "actor_id": 1}


def test_policy_preserves_sole_garrison_and_uses_explorer_with_exact_plan_identity():
    garrison_move = {"action_type": "unit_move", "actor_id": 11,
                     "target": {"x": 1, "y": 0}, "is_valid": True}
    explorer_move = {"action_type": "unit_move", "actor_id": 20,
                     "target": {"x": 0, "y": 2}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(20, "Explorer")],
        [garrison_move, explorer_move, {"action_type": "end_turn", "is_valid": True}])
    planner = GroundedImpactPlanner()
    first = planner.plan(snapshot)
    second = GroundedImpactPlanner().plan(snapshot)
    assert first.candidate.category == "exploration_move"
    assert first.candidate.action["actor_id"] == 20
    assert first.plan.to_dict() == second.plan.to_dict()
    assert first.plan.snapshot_id == snapshot.snapshot_id
    assert first.plan.steps[0].legal_actions_digest == snapshot.legal_actions_digest
    assert json.dumps(first.plan.steps[0].target, sort_keys=True, separators=(",", ":")) \
        in snapshot.legal_action_json


def test_offensive_action_wins_ranking_and_exclusions_bound_retries():
    attack = {"action_type": "unit_attack", "actor_id": 11,
              "target": {"x": 1, "y": 0}, "is_valid": True}
    move = {"action_type": "unit_move", "actor_id": 20,
            "target": {"x": 0, "y": 1}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(20, "Explorer"),
         _enemy(99, "Warriors", 1, 0)],
        [attack, move, {"action_type": "end_turn", "is_valid": True}])
    planner = GroundedImpactPlanner()
    decision = planner.plan(snapshot)
    assert decision.candidate.category == "tactical_attack"
    fallback = planner.plan(snapshot, excluded=(decision.candidate.action_key,))
    assert fallback.candidate.category == "tactical_move"


def test_attack_order_without_packet_visible_target_is_not_counted_as_impact():
    attack = {"action_type": "unit_attack", "actor_id": 11,
              "target": {"x": 1, "y": 0}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [attack, {"action_type": "end_turn", "is_valid": True}])
    assert GroundedImpactPlanner().plan(snapshot) is None


def test_policy_budget_is_bounded_and_end_turn_is_never_an_impact_candidate():
    snapshot = _snapshot([_unit(11, "Alpine Troops")], [
        {"action_type": "end_turn", "is_valid": True}])
    assert GroundedImpactPlanner().plan(snapshot) is None
    for config in ({"max_actions_per_turn": 0}, {"max_actions_per_turn": 33},
                   {"settle_min_distance": 0}, {"expansion_city_target": 21},
                   {"horizon_turn": 0},
                   {"production_minimum_remaining_turns": 0},
                   {"production_minimum_remaining_turns": 9,
                    "expansion_minimum_remaining_turns": 8},
                   {"refresh_timeout_seconds": 0.1},
                   {"refresh_timeout_seconds": 11},
                   {"no_effect_retry_limit": 0}, {"no_effect_retry_limit": 9},
                   {"max_no_effect_failovers_per_scope": -1},
                   {"max_no_effect_failovers_per_scope": 9},
                   {"production_strategy": "unknown"}):
        try:
            GroundedImpactPlanner(config)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid impact-policy budget was accepted")


def test_action_scopes_limit_one_unit_and_one_city_choice_per_turn():
    actions = [
        _production(10, "Granary", 3, 14),
        _production(10, "Library", 3, 17),
        {"action_type": "unit_move", "actor_id": 1,
         "target": {"x": 0, "y": 1}, "is_valid": True},
        {"action_type": "unit_move", "actor_id": 1,
         "target": {"x": 1, "y": 0}, "is_valid": True},
        {"action_type": "end_turn", "is_valid": True},
    ]
    snapshot = _snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops"), _unit(20, "Explorer")],
        actions)
    planner = GroundedImpactPlanner()
    first = planner.plan(snapshot)
    assert first.candidate.scope == ("unit", 1)
    second = planner.plan(snapshot, excluded_scopes=(first.candidate.scope,))
    assert second.candidate.scope == ("production", 10)
    assert planner.plan(snapshot, excluded_scopes=(
        first.candidate.scope, second.candidate.scope)) is None


def test_committed_fortification_is_not_reissued_every_turn():
    fortify = {"action_type": "unit_fortify", "actor_id": 11, "is_valid": True}
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [fortify, {"action_type": "end_turn", "is_valid": True}])
    planner = GroundedImpactPlanner()
    decision = planner.plan(snapshot)
    assert decision.candidate.category == "city_defense"
    planner.commit(decision.candidate)
    assert planner.plan(snapshot) is None


def test_no_effect_action_is_suppressed_until_local_grounding_changes():
    preferred = {"action_type": "unit_move", "actor_id": 20,
                 "target": {"x": 0, "y": 2}, "is_valid": True}
    alternative = {"action_type": "unit_move", "actor_id": 20,
                   "target": {"x": 1, "y": 0}, "is_valid": True}
    actions = [preferred, alternative, {"action_type": "end_turn", "is_valid": True}]
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(20, "Explorer")], actions)
    planner = GroundedImpactPlanner({"no_effect_retry_limit": 1})

    first = planner.plan(snapshot)
    assert first.candidate.action["target"] == preferred["target"]
    planner.record_outcome(first.candidate, snapshot, effect_observed=False)

    second = planner.plan(snapshot)
    assert second.candidate.action["target"] == alternative["target"]
    assert planner.no_effect_retries_blocked == 1
    # Re-evaluating one snapshot does not inflate the suppression telemetry.
    planner.plan(snapshot)
    assert planner.no_effect_retries_blocked == 1

    refreshed = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(20, "Explorer")],
        actions, source_seq=2)
    assert planner.plan(refreshed).candidate.action["target"] == alternative["target"]

    moved = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(20, "Explorer", x=0, y=1)],
        actions, source_seq=3)
    assert planner.plan(moved).candidate.action["target"] == preferred["target"]


def test_actor_resource_change_is_an_observed_effect_even_when_position_is_stable():
    move = {"action_type": "unit_move", "actor_id": 20,
            "target": {"x": 0, "y": 2}, "is_valid": True}
    before_unit = _unit(20, "Explorer")
    before_unit["moves_left"] = 6
    before = _snapshot(
        [_unit(11, "Alpine Troops"), before_unit],
        [move, {"action_type": "end_turn", "is_valid": True}])
    decision = GroundedImpactPlanner().plan(before)

    unchanged = _snapshot(
        [_unit(11, "Alpine Troops"), before_unit],
        [move, {"action_type": "end_turn", "is_valid": True}], source_seq=2)
    assert not GroundedImpactPlanner().local_actor_effect_observed(
        decision.candidate, before, unchanged)

    spent_unit = dict(before_unit, moves_left=0)
    spent = _snapshot(
        [_unit(11, "Alpine Troops"), spent_unit],
        [move, {"action_type": "end_turn", "is_valid": True}], source_seq=3)
    assert GroundedImpactPlanner().local_actor_effect_observed(
        decision.candidate, before, spent)


def test_production_effect_requires_the_exact_requested_city_target():
    action = _production(10, "Granary", 3, 14)
    before = _snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")],
        [action, {"action_type": "end_turn", "is_valid": True}])
    planner = GroundedImpactPlanner()
    candidate = ImpactCandidate(
        action, "production_economy", 1.0, "effect predicate regression")

    unrelated_refresh = _snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")],
        [action, {"action_type": "end_turn", "is_valid": True}], source_seq=2)
    assert not planner.candidate_effect_observed(
        candidate, before, unrelated_refresh)

    city = before.cities[0].to_dict()
    city.update({"id": city.pop("city_id"), "production_kind": 3,
                 "production_value": 14})
    city["prod"] = city.pop("production")
    city["buildability"] = {"available": True, "options": [
        {"type": kind, "id": item_id, "name": name}
        for kind, item_id, name in city.pop("buildable")]}
    city.pop("buildability_available")
    city.pop("buildability_diagnostic")
    applied = _snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")],
        [action, {"action_type": "end_turn", "is_valid": True}],
        cities=[city], source_seq=3)
    assert planner.candidate_effect_observed(candidate, before, applied)


def test_production_candidates_require_fixed_horizon_runway():
    granary = _production(10, "Granary", 3, 14)
    actions = [granary, {"action_type": "end_turn", "is_valid": True}]
    units = [_unit(1, "Settlers"), _unit(11, "Alpine Troops")]
    planner = GroundedImpactPlanner({
            "horizon_turn": 30, "production_minimum_remaining_turns": 8,
        "expansion_minimum_remaining_turns": 12}, ruleset_ir=_ruleset_ir((
            ("Alpine Troops", "unit", 1000),
            ("Granary", "building", 8),
        )))

    assert planner.plan(_snapshot(
        units, actions, turn=22, city_surplus=(10, 4, 2, 1, 0, 3))) is not None
    assert planner.plan(_snapshot(
        units, actions, turn=23, city_surplus=(10, 4, 2, 1, 0, 3))) is None


def test_paired_production_strategy_contrasts_static_and_horizon_value():
    actions = [
        _production(10, "Granary", 3, 14),
        _production(10, "Library", 3, 17),
        {"action_type": "end_turn", "is_valid": True},
    ]
    snapshot = _snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")], actions)
    ir = _ruleset_ir((
        ("Alpine Troops", "unit", 60),
        ("Granary", "improvement", 40),
        ("Library", "improvement", 60),
    ))
    baseline = GroundedImpactPlanner(
        {"production_strategy": "static_priority"}, ruleset_ir=ir).plan(snapshot)
    treatment = GroundedImpactPlanner(
        {"production_strategy": "horizon_score"}, ruleset_ir=ir).plan(snapshot)
    assert baseline.candidate.action["target"]["production_type"] == "Granary"
    assert baseline.candidate.projection is None
    assert treatment.candidate.action["target"]["production_type"] == "Library"
    assert treatment.candidate.projection["score_value"] > 0


def test_horizon_policy_avoids_military_churn_and_short_runway_population_loss():
    military = [_production(10, "Warriors", 6, 4),
                {"action_type": "end_turn", "is_valid": True}]
    military_ir = _ruleset_ir((
        ("Alpine Troops", "unit", 60), ("Warriors", "unit", 10)))
    assert GroundedImpactPlanner(ruleset_ir=military_ir).plan(_snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")], military)) is None

    founder_ir = SimpleNamespace(rules=tuple((
        SimpleNamespace(
            target_kind="unit", display_name=name, rule_name=name,
            quantitative={
                "build_cost": {"value": cost, "source": {}},
                "pop_cost": {"value": pop, "source": {}},
            })
        for name, cost, pop in (
            ("Alpine Troops", 60, 0), ("Migrants", 10, 1),
            ("Engineers", 30, 0)))))
    founders = [
        _production(10, "Migrants", 6, 1),
        _production(10, "Engineers", 6, 3),
        {"action_type": "end_turn", "is_valid": True},
    ]
    decision = GroundedImpactPlanner(ruleset_ir=founder_ir).plan(_snapshot(
        [_unit(11, "Alpine Troops")], founders, turn=15))
    assert decision.candidate.action["target"]["production_type"] == "Engineers"
    assert decision.candidate.projection["pop_cost"] == 0


def test_candidate_enumeration_does_not_mutate_exploration_history():
    move = {"action_type": "unit_move", "actor_id": 20,
            "target": {"x": 0, "y": 2}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(20, "Explorer")],
        [move, {"action_type": "end_turn", "is_valid": True}])
    planner = GroundedImpactPlanner()

    planner.plan(snapshot)
    assert planner.visited_positions == set()
    planner.observe(snapshot)
    assert planner.visited_positions == {(0, 0)}


def test_configured_no_effect_retry_limit_allows_one_controlled_retry():
    move = {"action_type": "unit_move", "actor_id": 20,
            "target": {"x": 0, "y": 2}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(20, "Explorer")],
        [move, {"action_type": "end_turn", "is_valid": True}])
    planner = GroundedImpactPlanner({"no_effect_retry_limit": 2})

    first = planner.plan(snapshot)
    planner.record_outcome(first.candidate, snapshot, effect_observed=False)
    assert planner.plan(snapshot) is not None
    planner.record_outcome(first.candidate, snapshot, effect_observed=False)
    assert planner.plan(snapshot) is None
    assert planner.no_effect_retries_blocked == 1


def test_turn_budget_releases_failed_scope_for_bounded_alternative_recovery():
    preferred = _production(10, "Settlers", 6, 0)
    alternative = _production(10, "Granary", 3, 14)
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(20, "Explorer")],
        [preferred, alternative, {"action_type": "end_turn", "is_valid": True}])
    planner = GroundedImpactPlanner()
    budget = ImpactTurnBudget(max_no_effect_failovers=2)

    first = planner.plan(snapshot, excluded_scopes=budget.excluded_scopes)
    planner.record_outcome(first.candidate, snapshot, effect_observed=False)
    assert budget.record(first.candidate, effect_observed=False) is False
    assert first.candidate.scope not in budget.excluded_scopes

    second = planner.plan(
        snapshot, excluded=(first.candidate.action_key,),
        excluded_scopes=budget.excluded_scopes)
    assert second is None
    # Expansion protection intentionally refuses to convert a failed founder
    # request into economy production while no founder exists.
    assert budget.failover_attempts == 0
    assert budget.recoveries == 0

    fail_closed = ImpactTurnBudget(max_no_effect_failovers=0)
    fail_closed.record(first.candidate, effect_observed=False)
    assert first.candidate.scope in fail_closed.excluded_scopes

    ambiguous = ImpactTurnBudget(max_no_effect_failovers=4)
    ambiguous.record(
        first.candidate, effect_observed=False, authoritative_refresh=False)
    assert first.candidate.scope in ambiguous.excluded_scopes
    assert ambiguous.failover_attempts == 0


def test_accepted_terminal_action_closes_actor_scope_before_delayed_state_effect():
    build = {"action_type": "unit_build_city", "actor_id": 1, "is_valid": True}
    snapshot = _snapshot(
        [_unit(1, "Settlers", 3, 0), _unit(11, "Alpine Troops")],
        [build, {"action_type": "end_turn", "is_valid": True}])
    decision = GroundedImpactPlanner({"settle_min_distance": 3}).plan(snapshot)
    assert decision.candidate.terminal_on_accept
    assert decision.candidate.scope == ("unit", 1)

    budget = ImpactTurnBudget(max_no_effect_failovers=4)
    budget.record(decision.candidate, effect_observed=False)
    assert decision.candidate.scope in budget.excluded_scopes
    assert budget.failover_attempts == 0
    assert budget.recoveries == 0


def test_accepted_unit_order_closes_scope_when_proxy_snapshot_stays_stale():
    move = {"action_type": "unit_move", "actor_id": 20,
            "target": {"x": 0, "y": 2}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(20, "Explorer")],
        [move, {"action_type": "end_turn", "is_valid": True}])
    decision = GroundedImpactPlanner().plan(snapshot)
    assert decision.candidate.unit_scope_consumed_on_accept

    budget = ImpactTurnBudget(max_no_effect_failovers=4)
    budget.record(decision.candidate, effect_observed=False)
    assert decision.candidate.scope in budget.excluded_scopes
    assert budget.failover_attempts == 0
