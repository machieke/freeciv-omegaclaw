"""Grounded impact-policy selection, safety, and diversity regressions."""

import json
import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (DeferredImpactOutcomeLedger,
                                    GroundedImpactPlanner, ImpactCandidate,
                                    ImpactTurnBudget)  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


def _snapshot(units, actions, cities=None, source_seq=1, turn=4,
              city_surplus=None, known_hut_tiles=None):
    cities = cities if cities is not None else [_city()]
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
            "known_hut_tiles": list(known_hut_tiles or ()),
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


def _city(size=2, food_stock=4, shield_stock=0,
          surplus=(1, 4, 2, 1, 0, 3), production_kind=6, production_value=11):
    return {
        "id": 10, "owner": 0, "name": "Rome", "tile": 0, "x": 0, "y": 0,
        "size": size, "production_kind": production_kind,
        "production_value": production_value,
        "food_stock": food_stock, "shield_stock": shield_stock,
        "surplus": list(surplus), "prod": [2, 5, 3, 1, 0, 4],
        "buildability": {"available": True, "options": [
            {"type": "unit", "id": 0, "name": "Settlers"},
            {"type": "unit", "id": 11, "name": "Alpine Troops"},
            {"type": "improvement", "id": 14, "name": "Granary"},
            {"type": "improvement", "id": 17, "name": "Library"},
        ]},
    }


def _ruleset_ir(costs, founders=("Settlers",),
                workers=("Settlers", "Migrants", "Workers", "Engineers"),
                add_to_city=None, pop_costs=None,
                growth_food=(20,), growth_increment=10):
    pop_costs = dict(pop_costs or {})
    add_to_city = set(founders if add_to_city is None else add_to_city)
    rules = []
    for name, kind, cost in costs:
        flags = []
        if name in workers:
            flags.append("Settlers")
        if name in founders:
            flags.append("Cities")
        if name in add_to_city:
            flags.append("AddToCity")
        rules.append(SimpleNamespace(
            target_kind=kind, display_name=name, rule_name=name,
            quantitative={
                "build_cost": {"value": cost, "source": {}},
                "pop_cost": {"value": pop_costs.get(name, 0), "source": {}},
            },
            traits={"flags": {"values": flags, "source": {}}}))
    return SimpleNamespace(rules=tuple(rules), parameters={
        "granary_food_ini": {"value": list(growth_food), "source": {}},
        "granary_food_inc": {"value": growth_increment, "source": {}},
    })


def test_policy_produces_founder_then_infrastructure_without_midbuild_switching():
    actions = [
        _production(10, "Settlers", 6, 0),
        _production(10, "Alpine Troops", 6, 11),
        _production(10, "Granary", 3, 14),
        _production(10, "Library", 3, 17),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ir = _ruleset_ir((
        ("Settlers", "unit", 30), ("Alpine Troops", "unit", 60),
        ("Granary", "improvement", 40), ("Library", "improvement", 60),
    ))
    planner = GroundedImpactPlanner(
        {"expansion_city_target": 2}, ruleset_ir=ir)
    without_founder = _snapshot([_unit(11, "Alpine Troops")], actions)
    decision = planner.plan(without_founder)
    assert decision.candidate.category == "production_expansion"
    assert decision.candidate.action["target"]["production_type"] == "Settlers"

    with_founder = _snapshot([
        _unit(1, "Settlers"), _unit(11, "Alpine Troops")], actions, source_seq=2)
    planner = GroundedImpactPlanner(
        {"expansion_city_target": 2}, ruleset_ir=ir)
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
    zero_stock_switch = GroundedImpactPlanner(
        {"expansion_city_target": 2}, ruleset_ir=ir).plan(_snapshot(
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
    assert GroundedImpactPlanner(
        {"expansion_city_target": 2}, ruleset_ir=ir).plan(_snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")], actions,
        cities=midbuild_city, source_seq=3)) is None


def test_founder_moves_outward_then_founds_only_at_configured_spacing():
    move_near = {"action_type": "unit_move", "actor_id": 1,
                 "target": {"x": 1, "y": 0}, "is_valid": True}
    move_far = {"action_type": "unit_move", "actor_id": 1,
                "target": {"x": 2, "y": 0}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")],
        [move_near, move_far,
         {"action_type": "unit_build_city", "actor_id": 1, "is_valid": True},
         {"action_type": "end_turn", "is_valid": True}])
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


def test_founder_route_uses_city_network_separation_instead_of_action_order():
    capital = _city()
    capital.update({"tile": 33, "x": 3, "y": 3})
    neighbor = _city()
    neighbor.update({"id": 12, "name": "Antium", "tile": 31, "x": 1, "y": 3})
    toward_network = {"action_type": "unit_move", "actor_id": 1,
                      "target": {"x": 2, "y": 3}, "is_valid": True}
    toward_frontier = {"action_type": "unit_move", "actor_id": 1,
                       "target": {"x": 4, "y": 3}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(1, "Settlers", 3, 3), _unit(11, "Alpine Troops", 3, 3)],
        [toward_network, toward_frontier,
         {"action_type": "end_turn", "is_valid": True}],
        cities=[capital, neighbor])
    planner = GroundedImpactPlanner(ruleset_ir=_ruleset_ir((
        ("Settlers", "unit", 30), ("Alpine Troops", "unit", 60))))
    # Exploration history alone must not pull the founder back toward the city
    # network when the outward edge has already been visited by another unit.
    planner.visited_positions.add((4, 3))

    decision = planner.plan(snapshot)

    assert decision.candidate.action["target"] == {"x": 4, "y": 3}
    assert decision.candidate.projection["city_separation_gain"] == 1.0
    assert decision.candidate.projection["founder_route_eta_turns"] == 3

    baseline = GroundedImpactPlanner(
        {"production_strategy": "static_priority"}, ruleset_ir=_ruleset_ir((
            ("Settlers", "unit", 30), ("Alpine Troops", "unit", 60))))
    baseline.visited_positions.add((4, 3))
    assert baseline.plan(snapshot).candidate.action["target"] == {"x": 2, "y": 3}

    # Once routing has left a city tile, city-network separation no longer
    # imposes straight-line momentum over the established distance ranking.
    bent_capital = _city()
    bent_capital.update({"tile": 33, "x": 3, "y": 3})
    bent_neighbor = _city()
    bent_neighbor.update({"id": 12, "name": "Antium", "tile": 40,
                          "x": 0, "y": 4})
    bend = _snapshot(
        [_unit(1, "Settlers", 4, 4)], [
            {"action_type": "unit_move", "actor_id": 1,
             "target": {"x": 4, "y": 5}, "is_valid": True},
            {"action_type": "unit_move", "actor_id": 1,
             "target": {"x": 5, "y": 4}, "is_valid": True},
            {"action_type": "end_turn", "is_valid": True},
        ], cities=[bent_capital, bent_neighbor], source_seq=2)
    bent_decision = planner.plan(bend)
    assert bent_decision.candidate.action["target"] == {"x": 4, "y": 5}
    assert not bent_decision.candidate.projection[
        "city_separation_tiebreak_active"]


def test_founder_route_learns_exact_traversal_for_another_founder():
    ir = _ruleset_ir((("Settlers", "unit", 30),))
    planner = GroundedImpactPlanner(ruleset_ir=ir)
    east = {"action_type": "unit_move", "actor_id": 1,
            "target": {"x": 1, "y": 0}, "is_valid": True}
    before = _snapshot(
        [_unit(1, "Settlers")],
        [east, {"action_type": "end_turn", "is_valid": True}])
    candidate = ImpactCandidate(
        {key: value for key, value in east.items() if key != "is_valid"},
        "expansion_move", 1.0, "route evidence regression")
    after = _snapshot(
        [_unit(1, "Settlers", 1, 0)],
        [{"action_type": "end_turn", "is_valid": True}], source_seq=2)

    planner.record_outcome(
        candidate, before, effect_observed=True, after_snapshot=after)

    assert planner.founder_route_successes == 1
    assert planner.founder_route_failures == 0
    demonstrated = _snapshot(
        [_unit(2, "Settlers")], [
            {"action_type": "unit_move", "actor_id": 2,
             "target": {"x": 0, "y": 1}, "is_valid": True},
            {"action_type": "unit_move", "actor_id": 2,
             "target": {"x": 1, "y": 0}, "is_valid": True},
            {"action_type": "end_turn", "is_valid": True},
        ], source_seq=3)
    decision = planner.plan(demonstrated)
    assert decision.candidate.action["target"] == {"x": 1, "y": 0}
    assert decision.candidate.projection["traversable_edge"]


def test_founder_route_continues_only_a_pre_spacing_cardinal_corridor():
    ir = _ruleset_ir((("Settlers", "unit", 30),))
    capital = _city()
    capital.update({"tile": 33, "x": 3, "y": 3})
    neighbor = _city()
    neighbor.update({"id": 12, "name": "Antium", "tile": 40,
                     "x": 0, "y": 4})
    cities = [capital, neighbor]
    east = {"action_type": "unit_move", "actor_id": 1,
            "target": {"x": 4, "y": 4}}
    before = _snapshot(
        [_unit(1, "Settlers", 3, 4)],
        [dict(east, is_valid=True),
         {"action_type": "end_turn", "is_valid": True}], cities=cities)
    after = _snapshot(
        [_unit(1, "Settlers", 4, 4)],
        [{"action_type": "end_turn", "is_valid": True}],
        cities=cities, source_seq=2)
    planner = GroundedImpactPlanner(ruleset_ir=ir)
    planner.record_outcome(
        ImpactCandidate(east, "expansion_move", 1.0, "cardinal route"),
        before, effect_observed=True, after_snapshot=after)

    continuation = _snapshot(
        [_unit(1, "Settlers", 4, 4)], [
            {"action_type": "unit_move", "actor_id": 1,
             "target": {"x": 4, "y": 5}, "is_valid": True},
            {"action_type": "unit_move", "actor_id": 1,
             "target": {"x": 5, "y": 4}, "is_valid": True},
            {"action_type": "end_turn", "is_valid": True},
        ], cities=cities, source_seq=3)
    decision = planner.plan(continuation)
    assert decision.candidate.action["target"] == {"x": 5, "y": 4}
    assert decision.candidate.projection["cardinal_corridor_match"]

    counter = GroundedImpactPlanner(ruleset_ir=ir)
    counter.record_outcome(
        ImpactCandidate(east, "expansion_move", 1.0, "cardinal route"),
        before, effect_observed=True, after_snapshot=after)
    corridor_decision = counter.plan(continuation)
    corridor_after = _snapshot(
        [_unit(1, "Settlers", 5, 4)],
        [{"action_type": "end_turn", "is_valid": True}],
        cities=cities, source_seq=4)
    counter.record_outcome(
        corridor_decision.candidate, continuation, effect_observed=True,
        after_snapshot=corridor_after)
    assert counter.founder_cardinal_corridor_attempts == 1
    assert counter.founder_cardinal_corridor_successes == 1

    # A settlement attempt proves that the current movement corridor has ended,
    # including when the advertised site itself has no effect.
    planner.record_outcome(
        ImpactCandidate({"action_type": "unit_build_city", "actor_id": 1},
                        "city_founding", 1.0, "site search"),
        continuation, effect_observed=False)
    decision = planner.plan(continuation)
    assert decision.candidate.action["target"] == {"x": 4, "y": 5}
    assert not decision.candidate.projection["cardinal_corridor_match"]

    diagonal_planner = GroundedImpactPlanner(ruleset_ir=ir)
    diagonal_before = _snapshot(
        [_unit(1, "Settlers", 3, 3)], [
            {"action_type": "unit_move", "actor_id": 1,
             "target": {"x": 4, "y": 4}, "is_valid": True},
            {"action_type": "end_turn", "is_valid": True},
        ], cities=cities, source_seq=5)
    diagonal_planner.record_outcome(
        ImpactCandidate(east, "expansion_move", 1.0, "diagonal route"),
        diagonal_before, effect_observed=True, after_snapshot=after)
    decision = diagonal_planner.plan(continuation)
    assert decision.candidate.action["target"] == {"x": 4, "y": 5}
    assert not decision.candidate.projection["cardinal_corridor_match"]


def test_deferred_confirmation_recovers_late_founder_route_effect():
    ir = _ruleset_ir((("Settlers", "unit", 30),))
    planner = GroundedImpactPlanner(ruleset_ir=ir)
    ledger = DeferredImpactOutcomeLedger()
    action = {"action_type": "unit_move", "actor_id": 1,
              "target": {"x": 1, "y": 0}}
    candidate = ImpactCandidate(
        action, "expansion_move", 1.0, "delayed route effect")
    before = _snapshot(
        [_unit(1, "Settlers")],
        [dict(action, is_valid=True),
         {"action_type": "end_turn", "is_valid": True}], turn=4)
    unrelated = _snapshot(
        [_unit(1, "Settlers")],
        [{"action_type": "end_turn", "is_valid": True}],
        source_seq=2, turn=4)
    applied = _snapshot(
        [_unit(1, "Settlers", 1, 0)],
        [{"action_type": "end_turn", "is_valid": True}],
        source_seq=3, turn=5)

    ledger.defer(candidate, before)

    assert ledger.resolve(planner, unrelated) == ()
    assert len(ledger) == 1
    resolutions = ledger.resolve(planner, applied)
    assert len(resolutions) == 1
    assert resolutions[0].effect_observed
    assert len(ledger) == 0

    planner.record_outcome(
        resolutions[0].candidate, resolutions[0].before_snapshot,
        resolutions[0].effect_observed,
        after_snapshot=resolutions[0].after_snapshot)
    assert planner.founder_route_successes == 1
    assert planner.founder_route_failures == 0


def test_deferred_confirmation_expires_unchanged_action_on_next_turn():
    planner = GroundedImpactPlanner()
    ledger = DeferredImpactOutcomeLedger()
    action = {"action_type": "unit_move", "actor_id": 20,
              "target": {"x": 1, "y": 0}}
    candidate = ImpactCandidate(
        action, "exploration_move", 1.0, "unchanged delayed action")
    before = _snapshot(
        [_unit(20, "Explorer")],
        [dict(action, is_valid=True),
         {"action_type": "end_turn", "is_valid": True}], turn=4)
    unchanged_next_turn = _snapshot(
        [_unit(20, "Explorer")],
        [dict(action, is_valid=True),
         {"action_type": "end_turn", "is_valid": True}],
        source_seq=2, turn=5)

    ledger.defer(candidate, before)
    resolutions = ledger.resolve(planner, unchanged_next_turn)

    assert len(resolutions) == 1
    assert not resolutions[0].effect_observed
    assert len(ledger) == 0


def test_explorer_prunes_destination_only_after_two_distinct_source_failures():
    planner = GroundedImpactPlanner()
    target = {"x": 2, "y": 2}

    def failure(source_x, source_y, turn):
        action = {"action_type": "unit_move", "actor_id": 20,
                  "target": dict(target)}
        before = _snapshot(
            [_unit(20, "Explorer", source_x, source_y)],
            [dict(action, is_valid=True),
             {"action_type": "end_turn", "is_valid": True}], turn=turn)
        after = _snapshot(
            [_unit(20, "Explorer", source_x, source_y)],
            [{"action_type": "end_turn", "is_valid": True}],
            source_seq=turn + 1, turn=turn + 1)
        candidate = ImpactCandidate(
            action, "exploration_move", 1.0, "failed destination evidence")
        planner.record_outcome(
            candidate, before, effect_observed=False, after_snapshot=after)
        return before, action

    first, action = failure(1, 1, 4)
    assert not planner._exploration_destination_reliably_failed(first, action)

    second, action = failure(2, 1, 6)
    assert planner._exploration_destination_reliably_failed(second, action)

    alternative = {"action_type": "unit_move", "actor_id": 20,
                   "target": {"x": 1, "y": 3}, "is_valid": True}
    current = _snapshot(
        [_unit(20, "Explorer", 1, 2)],
        [dict(action, is_valid=True), alternative,
         {"action_type": "end_turn", "is_valid": True}], turn=8)
    decision = planner.plan(current)

    assert decision.candidate.action["target"] == {"x": 1, "y": 3}
    assert planner.repeated_failed_destination_moves_pruned == 1

    reached = _snapshot(
        [_unit(20, "Explorer", 2, 2)],
        [{"action_type": "end_turn", "is_valid": True}],
        source_seq=10, turn=9)
    planner.record_outcome(
        ImpactCandidate(action, "exploration_move", 1.0,
                        "successful destination evidence"),
        current, effect_observed=True, after_snapshot=reached)
    assert not planner._exploration_destination_reliably_failed(current, action)


def test_founder_route_prunes_stationary_actor_edge_and_penalizes_shared_failure():
    ir = _ruleset_ir((("Settlers", "unit", 30),))
    planner = GroundedImpactPlanner(ruleset_ir=ir)
    north = {"action_type": "unit_move", "actor_id": 1,
             "target": {"x": 0, "y": 1}, "is_valid": True}
    east = {"action_type": "unit_move", "actor_id": 1,
            "target": {"x": 1, "y": 0}, "is_valid": True}
    before = _snapshot(
        [_unit(1, "Settlers")],
        [north, east, {"action_type": "end_turn", "is_valid": True}])
    failed_action = {key: value for key, value in north.items()
                     if key != "is_valid"}
    candidate = ImpactCandidate(
        failed_action, "expansion_move", 1.0, "route failure regression")
    spent = _unit(1, "Settlers")
    spent["moves_left"] = 0
    stationary = _snapshot(
        [spent], [north, east, {"action_type": "end_turn", "is_valid": True}],
        source_seq=2)

    # Movement-point consumption is an actor effect, but not proof that the
    # advertised destination was traversable.
    planner.record_outcome(
        candidate, before, effect_observed=True, after_snapshot=stationary)

    assert planner.founder_route_failures == 1
    assert planner.founder_route_successes == 0
    assert planner.founder_unreachable_move_keys(stationary) == (
        json.dumps(failed_action, sort_keys=True, separators=(",", ":")),)
    assert planner.plan(stationary).candidate.action["target"] == {"x": 1, "y": 0}

    changed_city = _city()
    changed_city.update({"id": 12, "name": "Antium", "tile": 55, "x": 5, "y": 5})
    changed_layout = _snapshot(
        [spent], [north, {"action_type": "end_turn", "is_valid": True}],
        cities=[_city(), changed_city], source_seq=3)
    assert planner.plan(changed_layout).candidate.action["target"] == {"x": 0, "y": 1}

    other_actor = _snapshot(
        [_unit(2, "Settlers")], [
            dict(north, actor_id=2), dict(east, actor_id=2),
            {"action_type": "end_turn", "is_valid": True},
        ], source_seq=4)
    decision = planner.plan(other_actor)
    assert decision.candidate.action["target"] == {"x": 1, "y": 0}
    assert decision.candidate.projection["failed_edge_attempts"] == 0

    projection = planner._production_projection(
        other_actor.cities[0], "Settlers", 20, snapshot=other_actor,
        founder_types=frozenset(("settlers",)))
    assert projection["founder_route_eta_turns"] == 4
    assert projection["founder_route_eta_source"] == "observed_route_effects"


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
              "target": {"x": 2, "y": 0}, "is_valid": True}
    move = {"action_type": "unit_move", "actor_id": 20,
            "target": {"x": 1, "y": 0}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(20, "Explorer"),
         _enemy(99, "Warriors", 2, 0)],
        [attack, move, {"action_type": "end_turn", "is_valid": True}])
    planner = GroundedImpactPlanner(
        {"expansion_city_target": 2}, ruleset_ir=_ruleset_ir((
        ("Settlers", "unit", 30), ("Granary", "improvement", 40),
        ("Library", "improvement", 60))))
    decision = planner.plan(snapshot)
    assert decision.candidate.category == "tactical_attack"
    fallback = planner.plan(snapshot, excluded=(decision.candidate.action_key,))
    assert fallback.candidate.category == "tactical_move"


def test_moves_require_novel_exploration_or_strict_tactical_progress():
    targetless = {"action_type": "unit_move", "actor_id": 11,
                  "target": {"x": 3, "y": 2}, "is_valid": True}
    no_enemy = _snapshot(
        [_unit(11, "Alpine Troops", 2, 2)],
        [targetless, {"action_type": "end_turn", "is_valid": True}])
    planner = GroundedImpactPlanner()
    assert planner.plan(no_enemy) is None
    assert planner.nonprogress_move_keys(no_enemy) == (
        json.dumps({key: value for key, value in targetless.items()
                    if key != "is_valid"},
                   sort_keys=True, separators=(",", ":")),)

    away = {"action_type": "unit_move", "actor_id": 11,
            "target": {"x": 1, "y": 2}, "is_valid": True}
    closer = {"action_type": "unit_move", "actor_id": 11,
              "target": {"x": 3, "y": 2}, "is_valid": True}
    tactical = _snapshot(
        [_unit(11, "Alpine Troops", 2, 2), _enemy(99, "Warriors", 5, 2)],
        [away, closer, {"action_type": "end_turn", "is_valid": True}],
        source_seq=2)
    candidates = planner.candidates(tactical)
    assert len(candidates) == 1
    assert candidates[0].category == "tactical_move"
    assert candidates[0].action["target"] == {"x": 3, "y": 2}

    revisit = {"action_type": "unit_move", "actor_id": 20,
               "target": {"x": 1, "y": 0}, "is_valid": True}
    explored = _snapshot(
        [_unit(20, "Explorer")],
        [revisit, {"action_type": "end_turn", "is_valid": True}],
        source_seq=3)
    planner.visited_positions.add((1, 0))
    assert planner.plan(explored) is None
    assert len(planner.nonprogress_move_keys(explored)) == 1


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
                   {"foodbox_percent": 0},
                   {"unit_build_score_divisor": 0},
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
    planner = GroundedImpactPlanner(
        {"expansion_city_target": 2}, ruleset_ir=_ruleset_ir((
        ("Settlers", "unit", 30), ("Granary", "improvement", 40),
        ("Library", "improvement", 60))))
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


def test_offensive_effect_observes_target_stack_when_attacker_is_unchanged():
    attack = {"action_type": "unit_attack", "actor_id": 11,
              "target": {"x": 2, "y": 0}, "is_valid": True}
    actor = _unit(11, "Riflemen", 1, 0)
    target = _enemy(99, "Diplomat", 2, 0)
    before = _snapshot(
        [actor, target], [attack, {"action_type": "end_turn", "is_valid": True}])
    candidate = ImpactCandidate(
        attack, "tactical_attack", 1.0, "target effect regression")

    unchanged = _snapshot(
        [actor, target], [attack, {"action_type": "end_turn", "is_valid": True}],
        source_seq=2)
    assert not GroundedImpactPlanner().candidate_effect_observed(
        candidate, before, unchanged)

    target_removed = _snapshot(
        [actor], [{"action_type": "end_turn", "is_valid": True}], source_seq=3)
    assert GroundedImpactPlanner().candidate_effect_observed(
        candidate, before, target_removed)


def test_plain_move_into_packet_visible_foreign_stack_is_not_a_candidate():
    move = {"action_type": "unit_move", "actor_id": 20,
            "target": {"x": 1, "y": 0}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(20, "Diplomat"), _enemy(99, "Warriors", 1, 0)],
        [move, {"action_type": "end_turn", "is_valid": True}])

    assert GroundedImpactPlanner().plan(snapshot) is None


def test_explorer_routes_toward_exact_packet_known_hut():
    toward_hut = {"action_type": "unit_move", "actor_id": 20,
                  "target": {"x": 1, "y": 0}, "is_valid": True}
    wandering = {"action_type": "unit_move", "actor_id": 20,
                 "target": {"x": 0, "y": 1}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(20, "Diplomat")],
        [wandering, toward_hut,
         {"action_type": "end_turn", "is_valid": True}],
        known_hut_tiles=[2])

    decision = GroundedImpactPlanner().plan(snapshot)

    assert decision.candidate.category == "hut_exploration"
    assert decision.candidate.action == {
        "action_type": "unit_move", "actor_id": 20,
        "target": {"x": 1, "y": 0},
    }
    assert decision.candidate.projection == {
        "current_hut_distance": 2,
        "target_hut_distance": 1,
        "target_is_known_hut": False,
    }


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


def test_settlement_effect_requires_actor_consumption_and_a_new_city():
    action = {"action_type": "unit_build_city", "actor_id": 1}
    candidate = ImpactCandidate(
        action, "city_founding", 1.0, "exact settlement effect regression")
    before = _snapshot(
        [_unit(1, "Settlers", 3, 0), _unit(11, "Alpine Troops")],
        [dict(action, is_valid=True),
         {"action_type": "end_turn", "is_valid": True}])
    spent = _unit(1, "Settlers", 3, 0)
    spent["moves_left"] = 0
    only_spent_movement = _snapshot(
        [spent, _unit(11, "Alpine Troops")],
        [dict(action, is_valid=True),
         {"action_type": "end_turn", "is_valid": True}], source_seq=2)
    assert not GroundedImpactPlanner().candidate_effect_observed(
        candidate, before, only_spent_movement)

    founded_city = _city()
    founded_city.update({"id": 12, "name": "Neapolis", "tile": 3, "x": 3})
    completed = _snapshot(
        [_unit(11, "Alpine Troops")],
        [{"action_type": "end_turn", "is_valid": True}],
        cities=[_city(), founded_city], source_seq=3)
    assert GroundedImpactPlanner().candidate_effect_observed(
        candidate, before, completed)


def test_surplus_founder_recovers_exact_ruleset_population_after_city_target():
    cities = [_city()]
    for city_id, name, x in ((12, "Antium", 3), (13, "Cumae", 6)):
        city = _city()
        city.update({"id": city_id, "name": name, "tile": x, "x": x})
        cities.append(city)
    join = {
        "action_type": "unit_join_city", "actor_id": 1,
        "target": {"city": "Rome", "city_id": 10}, "is_valid": True,
    }
    actions = [join, {"action_type": "end_turn", "is_valid": True}]
    ir = _ruleset_ir(
        (("Settlers", "unit", 30), ("Migrants", "unit", 20)),
        founders=("Settlers",), pop_costs={"Settlers": 2, "Migrants": 1})
    snapshot = _snapshot(
        [_unit(1, "Settlers")], actions, cities=cities, turn=18)

    planner = GroundedImpactPlanner(ruleset_ir=ir)
    decision = planner.plan(snapshot)

    assert decision.candidate.category == "population_recovery"
    assert decision.candidate.action["target"]["city_id"] == 10
    assert decision.candidate.projection == {
        "recovered_population": 2,
        "population_value_source": "ruleset_ir",
        "target_city_id": 10,
    }
    assert decision.candidate.terminal_on_accept

    # The paired static baseline stays unchanged, and expansion capacity is not
    # sacrificed before the configured city target has actually been reached.
    assert GroundedImpactPlanner(
        {"production_strategy": "static_priority"}, ruleset_ir=ir
    ).plan(snapshot) is None
    assert GroundedImpactPlanner(ruleset_ir=ir).plan(_snapshot(
        [_unit(1, "Settlers")], actions, cities=cities[:2], turn=18)) is None

    # Worker/AddToCity capability is not enough: only a ruleset Cities founder
    # may be retired by this score policy.
    migrant_join = dict(join, actor_id=2)
    assert GroundedImpactPlanner(ruleset_ir=ir).plan(_snapshot(
        [_unit(2, "Migrants")], [migrant_join, actions[-1]],
        cities=cities, turn=18)) is None


def test_surplus_founder_routes_back_for_packet_grounded_population_recovery():
    cities = [_city()]
    for city_id, x in ((12, 3), (13, 8)):
        city = _city()
        city.update({"id": city_id, "tile": x, "x": x})
        cities.append(city)
    toward = {"action_type": "unit_move", "actor_id": 1,
              "target": {"x": 4, "y": 0}, "is_valid": True}
    away = {"action_type": "unit_move", "actor_id": 1,
            "target": {"x": 5, "y": 1}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(1, "Settlers", 5, 0)],
        [away, toward, {"action_type": "end_turn", "is_valid": True}],
        cities=cities, turn=18)
    ir = _ruleset_ir(
        (("Settlers", "unit", 30),), pop_costs={"Settlers": 2})
    planner = GroundedImpactPlanner(ruleset_ir=ir)

    decision = planner.plan(snapshot)

    assert decision.candidate.category == "population_recovery_move"
    assert decision.candidate.action["target"] == {"x": 4, "y": 0}
    assert decision.candidate.projection == {
        "current_city_distance": 2,
        "recovered_population": 2,
        "target_city_distance": 1,
        "target_city_ids": [12],
    }
    assert GroundedImpactPlanner(
        {"production_strategy": "static_priority"},
        ruleset_ir=ir).plan(snapshot) is None

    arrived = _snapshot(
        [_unit(1, "Settlers", 4, 0)],
        [{"action_type": "end_turn", "is_valid": True}],
        cities=cities, turn=18, source_seq=2)
    planner.record_outcome(
        decision.candidate, snapshot, True, after_snapshot=arrived)
    assert planner.population_recovery_route_attempts == 1
    assert planner.population_recovery_route_successes == 1


def test_population_recovery_route_fails_closed_without_exact_capabilities_or_progress():
    cities = [_city()]
    for city_id, x in ((12, 3), (13, 8)):
        city = _city()
        city.update({"id": city_id, "tile": x, "x": x})
        cities.append(city)
    move = {"action_type": "unit_move", "actor_id": 1,
            "target": {"x": 4, "y": 0}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(1, "Settlers", 5, 0)],
        [move, {"action_type": "end_turn", "is_valid": True}],
        cities=cities, turn=18)
    invalid_rulesets = (
        _ruleset_ir(
            (("Settlers", "unit", 30),), add_to_city=(),
            pop_costs={"Settlers": 2}),
        _ruleset_ir(
            (("Settlers", "unit", 30),), founders=(),
            add_to_city=("Settlers",), pop_costs={"Settlers": 2}),
        _ruleset_ir(
            (("Settlers", "unit", 30),), pop_costs={"Settlers": 0}),
    )
    for ruleset in invalid_rulesets:
        assert GroundedImpactPlanner(ruleset_ir=ruleset).plan(snapshot) is None

    nonprogress = dict(move, target={"x": 5, "y": 1})
    ruleset = _ruleset_ir(
        (("Settlers", "unit", 30),), pop_costs={"Settlers": 2})
    assert GroundedImpactPlanner(ruleset_ir=ruleset).plan(_snapshot(
        [_unit(1, "Settlers", 5, 0)],
        [nonprogress, {"action_type": "end_turn", "is_valid": True}],
        cities=cities, turn=18)) is None


def test_population_recovery_effect_requires_unit_consumption_and_exact_city_gain():
    cities = [_city()]
    for city_id, x in ((12, 3), (13, 6)):
        city = _city()
        city.update({"id": city_id, "tile": x, "x": x})
        cities.append(city)
    action = {
        "action_type": "unit_join_city", "actor_id": 1,
        "target": {"city": "Rome", "city_id": 10}, "is_valid": True,
    }
    ir = _ruleset_ir(
        (("Settlers", "unit", 30),), pop_costs={"Settlers": 2})
    before = _snapshot([_unit(1, "Settlers")], [
        action, {"action_type": "end_turn", "is_valid": True}], cities=cities)
    planner = GroundedImpactPlanner(ruleset_ir=ir)
    candidate = planner.plan(before).candidate

    unchanged = _snapshot([_unit(1, "Settlers")], [
        action, {"action_type": "end_turn", "is_valid": True}],
        cities=cities, source_seq=2)
    assert not planner.candidate_effect_observed(candidate, before, unchanged)

    grown = [dict(city) for city in cities]
    grown[0]["size"] = 4
    completed = _snapshot([], [{"action_type": "end_turn", "is_valid": True}],
                          cities=grown, source_seq=3)
    assert planner.candidate_effect_observed(candidate, before, completed)
    planner.record_outcome(candidate, before, True, completed)
    assert planner.population_recovery_attempts == 1
    assert planner.population_recovery_completions == 1
    assert planner.population_recovered == 2

    wrong_gain = [dict(city) for city in cities]
    wrong_gain[0]["size"] = 3
    assert not planner.candidate_effect_observed(
        candidate, before, _snapshot(
            [], [{"action_type": "end_turn", "is_valid": True}],
            cities=wrong_gain, source_seq=4))


def test_production_candidates_require_fixed_horizon_runway():
    granary = _production(10, "Granary", 3, 14)
    actions = [granary, {"action_type": "end_turn", "is_valid": True}]
    units = [_unit(1, "Settlers"), _unit(11, "Alpine Troops")]
    planner = GroundedImpactPlanner({
            "horizon_turn": 30, "production_minimum_remaining_turns": 8,
        "expansion_minimum_remaining_turns": 12,
        "expansion_city_target": 2}, ruleset_ir=_ruleset_ir((
            ("Settlers", "unit", 30),
            ("Alpine Troops", "unit", 1000),
            ("Granary", "building", 8),
        )))

    assert planner.plan(_snapshot(
        units, actions, turn=22, city_surplus=(10, 4, 2, 1, 0, 3))) is not None
    assert planner.plan(_snapshot(
        units, actions, turn=23, city_surplus=(10, 4, 2, 1, 0, 3))) is None


def test_population_delayed_founder_uses_start_runway_and_settles_by_horizon():
    founder = _production(10, "Settlers", 6, 0)
    actions = [founder, {"action_type": "end_turn", "is_valid": True}]
    city = _city(size=1, food_stock=0, shield_stock=0,
                 surplus=(1, 5, 4, 3, 0, 2),
                 production_kind=6, production_value=11)
    ir = _ruleset_ir((
        ("Settlers", "unit", 40),
        ("Alpine Troops", "unit", 60),
    ), pop_costs={"Settlers": 1})
    values = {
        "horizon_turn": 30,
        "expansion_city_target": 2,
        "expansion_minimum_remaining_turns": 12,
    }

    decision = GroundedImpactPlanner(values, ruleset_ir=ir).plan(_snapshot(
        [_unit(11, "Alpine Troops")], actions, cities=[city], turn=1))

    assert decision.candidate.category == "production_expansion"
    assert decision.candidate.projection["population_ready_eta_turns"] == 20
    assert decision.candidate.projection["settlement_eta_turns"] == 23
    assert decision.candidate.projection["settlement_runway_turns"] == 6
    assert decision.candidate.projection["score_value"] > 0

    # A build that begins after the configured expansion-start cutoff remains
    # excluded even if a mature city could technically complete it by turn 30.
    mature = dict(city, size=2, food_stock=20)
    assert GroundedImpactPlanner(values, ruleset_ir=ir).plan(_snapshot(
        [_unit(11, "Alpine Troops")], actions, cities=[mature], turn=19)) is None


def test_paired_production_strategy_contrasts_static_and_horizon_value():
    actions = [
        _production(10, "Granary", 3, 14),
        _production(10, "Library", 3, 17),
        {"action_type": "end_turn", "is_valid": True},
    ]
    snapshot = _snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")], actions)
    ir = _ruleset_ir((
        ("Settlers", "unit", 30),
        ("Alpine Troops", "unit", 60),
        ("Granary", "improvement", 40),
        ("Library", "improvement", 60),
    ))
    baseline = GroundedImpactPlanner(
        {"production_strategy": "static_priority"}, ruleset_ir=ir).plan(snapshot)
    treatment = GroundedImpactPlanner(
        {"production_strategy": "horizon_score", "expansion_city_target": 2},
        ruleset_ir=ir).plan(snapshot)
    assert baseline.candidate.action["target"]["production_type"] == "Granary"
    assert baseline.candidate.projection is None
    assert treatment.candidate.action["target"]["production_type"] == "Library"
    assert treatment.candidate.projection["score_value"] > 0


def test_horizon_policy_avoids_military_churn_and_nonfounder_worker_production():
    military = [_production(10, "Warriors", 6, 4),
                {"action_type": "end_turn", "is_valid": True}]
    military_ir = _ruleset_ir((
        ("Settlers", "unit", 30), ("Alpine Troops", "unit", 60),
        ("Warriors", "unit", 10)))
    assert GroundedImpactPlanner(ruleset_ir=military_ir).plan(_snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")], military)) is None

    founder_ir = _ruleset_ir((
        ("Settlers", "unit", 30), ("Alpine Troops", "unit", 60),
        ("Migrants", "unit", 10), ("Engineers", "unit", 30)))
    founders = [
        _production(10, "Settlers", 6, 0),
        _production(10, "Migrants", 6, 1),
        _production(10, "Engineers", 6, 3),
        {"action_type": "end_turn", "is_valid": True},
    ]
    decision = GroundedImpactPlanner(ruleset_ir=founder_ir).plan(_snapshot(
        [_unit(11, "Alpine Troops")], founders, turn=4))
    assert decision.candidate.action["target"]["production_type"] == "Settlers"
    assert decision.candidate.projection["founder_capable"]
    assert decision.candidate.projection["founder_capability_source"] == (
        "ruleset_flag:Cities")


def test_horizon_policy_projects_repeated_units_and_guaranteed_score():
    warriors = [_production(10, "Warriors", 6, 4),
                {"action_type": "end_turn", "is_valid": True}]
    ir = _ruleset_ir((
        ("Settlers", "unit", 30), ("Alpine Troops", "unit", 60),
        ("Warriors", "unit", 10)))
    snapshot = _snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")], warriors,
        turn=1, city_surplus=(1, 5, 2, 1, 0, 3))

    decision = GroundedImpactPlanner(
        {"expansion_city_target": 2}, ruleset_ir=ir).plan(snapshot)

    assert decision.candidate.category == "production_military_score"
    assert decision.candidate.projection["completion_eta_turns"] == 2
    assert decision.candidate.projection["repeat_completion_eta_turns"] == 2
    assert decision.candidate.projection["projected_unit_completions"] == 14
    assert decision.candidate.projection["unit_build_score_divisor"] == 10
    assert decision.candidate.projection["guaranteed_unit_score_points"] == 1
    assert decision.candidate.projection["score_value"] == 1.4


def test_horizon_policy_commits_civilization_wide_unit_score_batch():
    cities = []
    actions = []
    for city_id, x in ((10, 0), (12, 3), (13, 6)):
        city = _city(
            production_kind=3, production_value=18,
            surplus=(1, 5, 2, 1, 0, 3))
        city.update({"id": city_id, "name": "City{}".format(city_id),
                     "tile": x, "x": x})
        city["buildability"]["options"].extend([
            {"type": "improvement", "id": 18, "name": "Marketplace"},
            {"type": "unit", "id": 9, "name": "Musketeers"},
        ])
        cities.append(city)
        actions.append(_production(city_id, "Musketeers", 6, 9))
    actions.append({"action_type": "end_turn", "is_valid": True})
    ir = _ruleset_ir((
        ("Alpine Troops", "unit", 60),
        ("Musketeers", "unit", 30),
        ("Marketplace", "improvement", 40),
    ), founders=(), workers=())
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(12, "Alpine Troops"),
         _unit(13, "Alpine Troops")],
        actions, cities=cities, turn=1)
    planner = GroundedImpactPlanner(
        {"expansion_city_target": 3}, ruleset_ir=ir)

    first = planner.plan(snapshot)

    assert first.candidate.category == "production_military_score"
    assert first.candidate.projection["projected_unit_completions"] == 4
    assert first.candidate.projection["guaranteed_unit_score_points"] == 0
    assert first.candidate.projection["batch_current_projected_unit_completions"] == 0
    assert first.candidate.projection["batch_optimized_projected_unit_completions"] == 12
    assert first.candidate.projection["batch_incremental_unit_completions"] == 12
    assert first.candidate.projection["batch_guaranteed_unit_score_points"] == 1
    assert first.candidate.projection["batch_selected_city_count"] == 3

    # A batch member must be authoritatively confirmed before the next member.
    assert planner.plan(
        snapshot, excluded=(first.candidate.action_key,)) is None
    changed = [dict(city) for city in cities]
    changed_city_id = first.candidate.action["city_id"]
    for city in changed:
        if city["id"] == changed_city_id:
            city["production_kind"] = 6
            city["production_value"] = 9
    after = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(12, "Alpine Troops"),
         _unit(13, "Alpine Troops")], actions, cities=changed,
        turn=1, source_seq=2)
    planner.record_outcome(first.candidate, snapshot, True, after)
    second = planner.plan(after, excluded=(first.candidate.action_key,))
    assert second.candidate.category == "production_military_score"
    assert second.candidate.action["city_id"] != changed_city_id


def test_failed_unit_score_batch_member_cancels_remaining_switches():
    cities = []
    actions = []
    for city_id, x in ((10, 0), (12, 3), (13, 6)):
        city = _city(production_kind=3, production_value=18,
                     surplus=(1, 5, 2, 1, 0, 3))
        city.update({"id": city_id, "tile": x, "x": x})
        city["buildability"]["options"].extend([
            {"type": "improvement", "id": 18, "name": "Marketplace"},
            {"type": "unit", "id": 9, "name": "Musketeers"},
        ])
        cities.append(city)
        actions.append(_production(city_id, "Musketeers", 6, 9))
    actions.append({"action_type": "end_turn", "is_valid": True})
    ir = _ruleset_ir((
        ("Alpine Troops", "unit", 60), ("Musketeers", "unit", 30),
        ("Marketplace", "improvement", 40)), founders=(), workers=())
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(12, "Alpine Troops"),
         _unit(13, "Alpine Troops")], actions, cities=cities, turn=1)
    planner = GroundedImpactPlanner(
        {"expansion_city_target": 3}, ruleset_ir=ir)
    first = planner.plan(snapshot)

    planner.record_outcome(first.candidate, snapshot, False, snapshot)

    assert planner.plan(
        snapshot, excluded=(first.candidate.action_key,)) is None


def test_unit_score_batch_is_memoized_per_snapshot_and_legal_set():
    city = _city(production_kind=3, production_value=18,
                 surplus=(1, 5, 2, 1, 0, 3))
    city["buildability"]["options"].extend([
        {"type": "improvement", "id": 18, "name": "Marketplace"},
        {"type": "unit", "id": 9, "name": "Musketeers"},
    ])
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [_production(10, "Musketeers", 6, 9),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[city], turn=1)
    planner = GroundedImpactPlanner(ruleset_ir=_ruleset_ir((
        ("Alpine Troops", "unit", 60), ("Musketeers", "unit", 30),
        ("Marketplace", "improvement", 40)), founders=(), workers=()))
    actions = planner._actions(snapshot)
    original = planner._production_projection
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    planner._production_projection = counted
    first = planner._unit_score_batch_members(snapshot, actions, frozenset())
    first_call_count = len(calls)
    second = planner._unit_score_batch_members(snapshot, actions, frozenset())

    assert first == second
    assert first_call_count > 0
    assert len(calls) == first_call_count


def test_horizon_policy_retires_redundant_founder_production():
    defender = [_production(10, "Alpine Troops", 6, 11),
                {"action_type": "end_turn", "is_valid": True}]
    ir = _ruleset_ir((
        ("Settlers", "unit", 30), ("Alpine Troops", "unit", 60),
    ), pop_costs={"Settlers": 2})
    city = _city(
        production_kind=6, production_value=0,
        surplus=(1, 5, 2, 1, 0, 3))
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")], defender, cities=[city], turn=1)

    decision = GroundedImpactPlanner(
        {"expansion_city_target": 1}, ruleset_ir=ir).plan(snapshot)

    assert decision.candidate.category == "production_repurpose"
    assert decision.candidate.action["target"]["production_type"] == (
        "Alpine Troops")
    assert decision.candidate.projection["projected_unit_completions"] == 2
    assert decision.candidate.projection["guaranteed_unit_score_points"] == 0
    baseline = GroundedImpactPlanner(
        {"expansion_city_target": 1, "production_strategy": "static_priority"},
        ruleset_ir=ir).plan(snapshot)
    assert baseline.candidate.category == "production_military"
    assert baseline.candidate.projection is None


def test_production_projection_fails_closed_without_shield_surplus():
    ir = _ruleset_ir((("Warriors", "unit", 10),), founders=(), workers=())
    planner = GroundedImpactPlanner(ruleset_ir=ir)
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [_production(10, "Warriors", 6, 4),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[_city(surplus=(1, 0, 2, 1, 0, 3))])

    projection = planner._production_projection(
        snapshot.cities[0], "Warriors", 20, snapshot=snapshot)

    assert projection["completion_eta_turns"] is None
    assert projection["score_value"] == 0.0


def test_horizon_policy_pipelines_only_the_missing_ruleset_capable_founder():
    actions = [
        _production(10, "Settlers", 6, 0),
        _production(10, "Library", 3, 17),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ir = _ruleset_ir((
        ("Settlers", "unit", 30), ("Library", "improvement", 60),
    ), pop_costs={"Settlers": 2}, growth_food=(20, 20), growth_increment=0)
    snapshot = _snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")], actions,
        cities=[_city(size=1, food_stock=0,
                      surplus=(5, 4, 2, 1, 0, 3))], turn=1)
    planner = GroundedImpactPlanner(ruleset_ir=ir)

    decision = planner.plan(snapshot)
    assert decision.candidate.category == "production_expansion"
    assert decision.candidate.projection["existing_founders"] == 1
    assert decision.candidate.projection["queued_founders"] == 0
    assert decision.candidate.projection["founder_deficit_before"] == 1
    assert decision.candidate.projection["population_ready_eta_turns"] == 8
    assert decision.candidate.projection["completion_eta_turns"] == 8
    assert decision.candidate.projection["settlement_runway_turns"] == 18
    assert "projected_unit_completions" not in decision.candidate.projection

    city = dict(json.loads(json.dumps(snapshot.cities[0].to_dict())),
                id=10, production_kind=6, production_value=0)
    city["buildability"] = {"available": True, "options": [
        {"type": kind, "id": item_id, "name": name}
        for kind, item_id, name in snapshot.cities[0].buildable]}
    city["prod"] = city.pop("production")
    city.pop("buildability_available", None)
    city.pop("buildability_diagnostic", None)
    queued = _snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")], actions,
        cities=[city], source_seq=2, city_surplus=(5, 4, 2, 1, 0, 3))
    assert not any(candidate.category == "production_expansion"
                   for candidate in planner.candidates(queued))


def test_population_bound_founder_is_rejected_without_post_build_runway():
    founder = _production(10, "Settlers", 6, 0)
    ir = _ruleset_ir(
        (("Settlers", "unit", 30),), pop_costs={"Settlers": 2},
        growth_food=(20, 20), growth_increment=0)
    planner = GroundedImpactPlanner(ruleset_ir=ir)
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [founder, {"action_type": "end_turn", "is_valid": True}], turn=4,
        cities=[_city(size=1, food_stock=0,
                      surplus=(2, 4, 2, 1, 0, 3))])

    projection = planner._production_projection(
        snapshot.cities[0], "Settlers", 26, snapshot=snapshot,
        founder_types=frozenset(("settlers",)))
    assert projection["shield_completion_eta_turns"] == 8
    assert projection["population_ready_eta_turns"] == 20
    assert projection["completion_eta_turns"] == 20
    assert projection["settlement_runway_turns"] == 3
    assert planner.plan(snapshot) is None


def test_ruleset_and_server_capabilities_exclude_nonfounder_workers():
    ir = _ruleset_ir((
        ("Settlers", "unit", 30), ("Migrants", "unit", 10),
        ("Workers", "unit", 20), ("Engineers", "unit", 30),
        ("Alpine Troops", "unit", 60)))
    actions = [
        {"action_type": "unit_build_city", "actor_id": 1, "is_valid": True},
        {"action_type": "unit_move", "actor_id": 1,
         "target": {"x": 2, "y": 0}, "is_valid": True},
        {"action_type": "unit_move", "actor_id": 3,
         "target": {"x": 2, "y": 0}, "is_valid": True},
        {"action_type": "end_turn", "is_valid": True},
    ]
    snapshot = _snapshot([
        _unit(1, "Settlers"), _unit(3, "Engineers"),
        _unit(11, "Alpine Troops")], actions)
    planner = GroundedImpactPlanner(ruleset_ir=ir)

    assert tuple(unit.unit_type for unit in planner._founders(snapshot)) == ("Settlers",)
    assert planner.founder_capable_types == ("settlers",)
    candidates = planner.candidates(snapshot)
    assert any(row.category == "expansion_move" and row.action["actor_id"] == 1
               for row in candidates)
    assert not any(row.action.get("actor_id") == 3 for row in candidates)
    assert planner.capability_pruned_worker_move_keys(snapshot) == (
        json.dumps({key: value for key, value in actions[2].items()
                    if key != "is_valid"},
                   sort_keys=True, separators=(",", ":")),)
    assert planner.visited_positions == set()


def test_observed_server_city_action_caches_founder_type_without_ruleset_traits():
    demonstrated = _snapshot(
        [_unit(7, "Colony Pod", 3, 0), _unit(11, "Alpine Troops")],
        [{"action_type": "unit_build_city", "actor_id": 7, "is_valid": True},
         {"action_type": "end_turn", "is_valid": True}])
    planner = GroundedImpactPlanner()
    planner.observe(demonstrated)
    later = _snapshot(
        [_unit(8, "Colony Pod"), _unit(11, "Alpine Troops")],
        [{"action_type": "unit_move", "actor_id": 8,
          "target": {"x": 2, "y": 0}, "is_valid": True},
         {"action_type": "end_turn", "is_valid": True}], source_seq=2)

    assert planner.founder_capable_types == ("colony pod",)
    assert planner.plan(later).candidate.category == "expansion_move"


def test_candidate_enumeration_does_not_mutate_exploration_history():
    move = {"action_type": "unit_move", "actor_id": 20,
            "target": {"x": 0, "y": 2}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(20, "Explorer")],
        [move, {"action_type": "end_turn", "is_valid": True}])
    planner = GroundedImpactPlanner(ruleset_ir=_ruleset_ir((
        ("Settlers", "unit", 30), ("Granary", "improvement", 40))))

    planner.plan(snapshot)
    assert planner.visited_positions == set()
    assert planner.founder_route_successes == 0
    assert planner.founder_route_failures == 0
    assert planner.founder_cardinal_corridor_attempts == 0
    assert planner.founder_cardinal_corridor_successes == 0
    assert planner._founder_cardinal_intents == {}
    assert planner._founder_traversable_edges == set()
    assert planner._founder_failed_edges == {}
    assert planner._founder_actor_failed_edges == set()
    planner.observe(snapshot)
    assert planner.visited_positions == {(0, 0)}


def test_candidate_enumeration_decodes_legal_actions_once():
    actions = [
        _production(10, "Settlers", 6, 0),
        {"action_type": "unit_move", "actor_id": 1,
         "target": {"x": 2, "y": 0}, "is_valid": True},
        {"action_type": "unit_move", "actor_id": 3,
         "target": {"x": 1, "y": 0}, "is_valid": True},
        {"action_type": "unit_fortify", "actor_id": 11, "is_valid": True},
        {"action_type": "end_turn", "is_valid": True},
    ]
    snapshot = _snapshot([
        _unit(1, "Settlers"), _unit(3, "Engineers"),
        _unit(11, "Alpine Troops")], actions)
    planner = GroundedImpactPlanner(ruleset_ir=_ruleset_ir((
        ("Settlers", "unit", 30), ("Engineers", "unit", 30),
        ("Alpine Troops", "unit", 60))))
    calls = []
    original = planner._actions

    def counted(value):
        calls.append(value.snapshot_id)
        return original(value)

    planner._actions = counted
    planner.candidates(snapshot)
    assert calls == [snapshot.snapshot_id]


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
    planner = GroundedImpactPlanner(ruleset_ir=_ruleset_ir((
        ("Settlers", "unit", 30), ("Granary", "improvement", 40))))
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
