"""Grounded impact-policy selection, safety, and diversity regressions."""

import json
import os
import sys
import tempfile
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (DeferredImpactOutcomeLedger,
                                    GroundedImpactPlanner, ImpactCandidate,
                                    ImpactTurnBudget,
                                    OperationAuthorityKind,
                                    OperationAuthorityReadout)  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


def _snapshot(units, actions, cities=None, source_seq=1, turn=4,
              city_surplus=None, known_hut_tiles=None, government=None,
              player=None, research=None, own_score=None, opponent_score=None):
    cities = cities if cities is not None else [_city()]
    if city_surplus is not None:
        cities[0]["surplus"] = list(city_surplus)
    payload = {
        "format": "pln_authoritative", "turn": turn, "phase": "movement",
        "player_id": 0,
        "authoritative": {
            "source_seq": source_seq,
            "player": dict(
                {"gold": 30, "gold_per_turn": 3, "tax": 40,
                 "science": 60, "luxury": 0},
                **dict(player or {})),
            "research": dict(
                {"researching": 5, "researching_name": "Writing",
                 "researching_cost": 40, "bulbs_researched": 10,
                 "beakers_per_turn": 5},
                **dict(research or {})),
            "ruleset": {"ready": True},
            "known_hut_tiles": list(known_hut_tiles or ()),
        },
        "techs": {"player0": ["Alphabet"]},
        "units": {str(row["id"]): row for row in units},
        "cities": {str(row["id"]): row for row in cities},
        "map": {"width": 10, "height": 10, "tiles": []},
        "visible_tiles": [], "legal_actions": actions,
    }
    if government is not None:
        payload["authoritative"]["government"] = dict(government)
    if own_score is not None or opponent_score is not None:
        payload["authoritative"]["score"] = {
            "own": own_score,
            "opponents": [{
                "player_id": 1, "name": "Opponent",
                "score": opponent_score, "is_alive": True,
            }],
        }
    return ProxyStateDTO.parse("impact-test", source_seq, payload).to_snapshot()


def _unit(unit_id, unit_type, x=0, y=0, homecity=None, upkeep=None):
    row = {"id": unit_id, "owner": 0, "type": unit_type, "type_id": unit_id,
           "tile": y * 10 + x, "x": x, "y": y, "moves_left": 3,
           "hp": 20, "activity": "idle",
           "upkeep": list(upkeep or (0, 0, 0, 0, 0, 0))}
    if homecity is not None:
        row["homecity"] = homecity
    return row


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
                growth_food=(20,), growth_increment=10, upkeeps=None,
                capabilities=None):
    pop_costs = dict(pop_costs or {})
    upkeeps = dict(upkeeps or {})
    capabilities = dict(capabilities or {})
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
                **{
                    key: {"value": value, "source": {}}
                    for key, value in upkeeps.get(name, {}).items()
                },
                **{
                    key: {"value": value, "source": {}}
                    for key, value in capabilities.get(name, {}).items()
                    if key != "class"
                },
            },
            traits={
                "flags": {"values": flags, "source": {}},
                "class": {
                    "values": [capabilities.get(name, {}).get(
                        "class", "Land")],
                    "source": {},
                },
            }))
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


def test_candidate_enumeration_skips_unplanned_production_projection():
    actions = [
        _production(10, "Pyramids", 3, 1),
        _production(10, "Library", 3, 17),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ir = _ruleset_ir((
        ("Pyramids", "improvement", 200),
        ("Library", "improvement", 60),
    ))
    planner = GroundedImpactPlanner(
        {"expansion_city_target": 1}, ruleset_ir=ir)
    projected = []
    project = planner._production_projection

    def recording_projection(city, name, remaining_turns, **kwargs):
        projected.append(name)
        return project(city, name, remaining_turns, **kwargs)

    planner._production_projection = recording_projection
    decision = planner.plan(_snapshot(
        [_unit(1, "Settlers"), _unit(11, "Alpine Troops")], actions))

    assert decision.candidate.action["target"]["production_type"] == "Library"
    assert isinstance(planner.last_candidate_catalog, tuple)
    assert decision.candidate in planner.last_candidate_catalog
    assert {
        candidate.action_key for candidate in planner.last_candidate_catalog
    } == {
        candidate.action_key for candidate in planner.candidates(_snapshot(
            [_unit(1, "Settlers"), _unit(11, "Alpine Troops")], actions))
    }
    assert "Pyramids" not in projected


def test_exact_authority_rematerializes_only_a_cached_legal_candidate():
    actions = [
        {"action_type": "unit_fortify", "actor_id": 11,
         "is_valid": True},
        {"action_type": "unit_fortify", "actor_id": 12,
         "is_valid": True},
        {"action_type": "end_turn", "is_valid": True},
    ]
    snapshot = _snapshot([
        _unit(11, "Alpine Troops"),
        _unit(12, "Alpine Troops"),
    ], actions)
    planner = GroundedImpactPlanner()
    control = ImpactCandidate(
        {"action_type": "unit_fortify", "actor_id": 11},
        "city_defense", 10.0, "control")
    treatment = ImpactCandidate(
        {"action_type": "unit_fortify", "actor_id": 12},
        "city_defense", 10.0, "treatment")
    planner.last_candidate_catalog = (control, treatment)
    prior = planner._materialize_candidate(snapshot, control)
    authority = OperationAuthorityReadout(
        OperationAuthorityKind.CITY_DEFENSE,
        "test-randomized-operation", "test-defense-operation",
        treatment.action, treatment.action_key, treatment.category,
        snapshot.snapshot_id, snapshot.legal_actions_digest, 0.0,
        ("test-randomized-authority",))

    rematerialized = planner.rematerialize_exact_authority(
        snapshot, prior, authority)

    assert rematerialized.candidate == treatment
    assert rematerialized.plan.steps[0].target == treatment.action
    assert rematerialized.operation_authority["applied"] is True
    assert rematerialized.operation_authority["changed_winner"] is True
    assert rematerialized.operation_authority[
        "baseline_candidate_key"] == control.action_key
    assert rematerialized.pressure_artifact is None

    uncached = OperationAuthorityReadout(
        OperationAuthorityKind.CITY_DEFENSE,
        "test-uncached-operation", "test-defense-operation",
        {"action_type": "end_turn"},
        '{"action_type":"end_turn"}', "city_defense",
        snapshot.snapshot_id, snapshot.legal_actions_digest, 0.0,
        ("test-randomized-authority",))
    try:
        planner.rematerialize_exact_authority(snapshot, prior, uncached)
    except ValueError as error:
        assert "outside authority kind" in str(error)
    else:
        raise AssertionError("uncached authority unexpectedly materialized")


def test_exact_authority_handles_duplicate_or_broader_current_candidate():
    actions = [
        {"action_type": "unit_fortify", "actor_id": 11,
         "is_valid": True},
        {"action_type": "unit_fortify", "actor_id": 12,
         "is_valid": True},
        {"action_type": "end_turn", "is_valid": True},
    ]
    snapshot = _snapshot([
        _unit(11, "Alpine Troops"),
        _unit(12, "Alpine Troops"),
    ], actions)
    planner = GroundedImpactPlanner()
    control = ImpactCandidate(
        {"action_type": "unit_fortify", "actor_id": 11},
        "city_defense", 10.0, "control")
    treatment = ImpactCandidate(
        {"action_type": "unit_fortify", "actor_id": 12},
        "city_defense", 10.0, "treatment")
    prior = planner._materialize_candidate(snapshot, control)
    authority = OperationAuthorityReadout(
        OperationAuthorityKind.CITY_DEFENSE,
        "test-broader-operation", "test-defense-operation",
        treatment.action, treatment.action_key, treatment.category,
        snapshot.snapshot_id, snapshot.legal_actions_digest, 0.0,
        ("test-randomized-authority",))

    planner.last_candidate_catalog = (treatment, treatment)
    duplicate = planner.rematerialize_exact_authority(
        snapshot, prior, authority)
    assert duplicate.candidate == treatment

    planner.last_candidate_catalog = (control,)
    diagnostics = {}
    reprojected = planner.rematerialize_exact_authority(
        snapshot, prior, authority, diagnostics=diagnostics)
    assert reprojected.candidate.action_key == treatment.action_key
    assert reprojected.candidate.category == treatment.category
    assert diagnostics["authority_catalog_reprojections"] == 1


def test_ruleset_driven_policy_answers_naval_threat_with_buildable_vessel():
    city = _city(production_kind=6, production_value=11)
    city["buildability"]["options"].extend([
        {"type": "unit", "id": 20, "name": "Armor"},
        {"type": "unit", "id": 21, "name": "Destroyer"},
        {"type": "unit", "id": 22, "name": "Transport"},
    ])
    actions = [
        _production(10, "Armor", 6, 20),
        _production(10, "Destroyer", 6, 21),
        _production(10, "Transport", 6, 22),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ir = _ruleset_ir((
        ("Alpine Troops", "unit", 60),
        ("Armor", "unit", 80),
        ("Destroyer", "unit", 60),
        ("Transport", "unit", 50),
    ), capabilities={
        "Alpine Troops": {
            "class": "Land", "attack": 5, "defense": 5,
            "hitpoints": 20, "firepower": 1,
        },
        "Armor": {
            "class": "Land", "attack": 10, "defense": 5,
            "hitpoints": 20, "firepower": 1,
        },
        "Destroyer": {
            "class": "Sea", "attack": 4, "defense": 4,
            "hitpoints": 30, "firepower": 1, "move_rate": 6,
        },
        "Transport": {
            "class": "Sea", "attack": 0, "defense": 3,
            "hitpoints": 30, "firepower": 1, "move_rate": 5,
            "transport_cap": 8,
        },
    })
    planner = GroundedImpactPlanner({
        "expansion_city_target": 1,
        "horizon_turn": 100,
        "ruleset_driven_production_enabled": True,
        "naval_response_enabled": True,
        "modernization_enabled": True,
    }, ruleset_ir=ir)
    snapshot = _snapshot([
        _unit(11, "Alpine Troops"),
        _enemy(90, "Destroyer", 4, 4),
    ], actions, cities=[city], own_score=20, opponent_score=35)

    planner.observe(snapshot)
    decision = planner.plan(snapshot)

    assert decision.candidate.category == "production_naval_response"
    assert decision.candidate.action["target"]["production_type"] == "Destroyer"
    assert decision.candidate.projection["capability_domain"] == "sea"
    assert decision.candidate.projection["score_gap_to_leader"] == -15


def test_naval_response_keeps_funded_queue_until_safety_or_completion():
    city = _city(
        shield_stock=5, production_kind=6, production_value=21)
    city["buildability"]["options"].extend([
        {"type": "unit", "id": 21, "name": "Destroyer"},
        {"type": "unit", "id": 22, "name": "Transport"},
    ])
    ruleset = _ruleset_ir((
        ("Alpine Troops", "unit", 60),
        ("Destroyer", "unit", 60),
        ("Transport", "unit", 50),
    ), upkeeps={
        "Destroyer": {"uk_food": 1},
    }, capabilities={
        "Alpine Troops": {
            "class": "Land", "attack": 5, "defense": 5,
            "hitpoints": 20, "firepower": 1,
        },
        "Destroyer": {
            "class": "Sea", "attack": 4, "defense": 4,
            "hitpoints": 30, "firepower": 1, "move_rate": 6,
        },
        "Transport": {
            "class": "Sea", "attack": 0, "defense": 3,
            "hitpoints": 30, "firepower": 1, "move_rate": 5,
            "transport_cap": 8,
        },
    })
    planner = GroundedImpactPlanner({
        "expansion_city_target": 1,
        "horizon_turn": 100,
        "ruleset_driven_production_enabled": True,
        "naval_response_enabled": True,
    }, ruleset_ir=ruleset)
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops", 4, 4),
         _enemy(90, "Destroyer", 4, 4)],
        [_production(10, "Alpine Troops", 6, 11),
         _production(10, "Transport", 6, 22),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[city], own_score=20, opponent_score=35)

    planner.observe(snapshot)

    assert planner.plan(snapshot) is None

    deficit = _snapshot(
        [_unit(11, "Alpine Troops", 4, 4),
         _enemy(90, "Destroyer", 4, 4)],
        [_production(10, "Marketplace", 3, 18),
         _production(10, "Coinage", 3, 72),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[city], source_seq=2, turn=5,
        player={
            "gold": 0, "city_gold_surplus_per_turn": -1,
            "gold_per_turn": -1, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
        })
    planner.observe(deficit)
    assert planner._production_sustainability_route(
        deficit, deficit.cities[0], "destroyer", "marketplace",
        frozenset()) is None
    assert planner._production_sustainability_route(
        deficit, deficit.cities[0], "destroyer", "granary",
        frozenset()) is None
    immediate = planner._production_sustainability_route(
        deficit, deficit.cities[0], "destroyer", "coinage", frozenset())
    assert immediate[0] == "production_treasury_stabilization"

    recovery_city = _city(production_kind=3, production_value=72)
    recovery_city.update({"id": 11, "name": "Antium", "x": 2, "y": 2})
    distributed = _snapshot(
        [_unit(11, "Alpine Troops", 4, 4),
         _enemy(90, "Destroyer", 4, 4)],
        [_production(10, "Coinage", 3, 72),
         _production(11, "Coinage", 3, 72),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[city, recovery_city], source_seq=3, turn=6,
        player={
            "gold": 0, "city_gold_surplus_per_turn": -1,
            "gold_per_turn": -1, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
        })
    planner.observe(distributed)
    reserve_breach = planner._production_sustainability_route(
        distributed, distributed.cities[0], "destroyer", "coinage",
        frozenset())
    assert reserve_breach[0] == "production_treasury_stabilization"

    delivered = _snapshot(
        [_unit(21, "Destroyer"), _enemy(91, "Cruiser", 4, 4)],
        [_production(10, "Granary", 3, 14),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[city], source_seq=4, turn=7)
    planner.observe(delivered)
    assert planner._production_sustainability_route(
        delivered, delivered.cities[0], "destroyer", "granary",
        frozenset())[0] == "production_food_stabilization"


def test_hidden_negative_score_sentinel_does_not_create_score_pressure():
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [{"action_type": "end_turn", "is_valid": True}],
        own_score=109, opponent_score=-1)

    assert snapshot.opponent_scores[0].score is None
    assert GroundedImpactPlanner._score_gap(snapshot) is None


def test_ruleset_driven_policy_modernizes_and_repairs_industry():
    modernization_city = _city(production_kind=6, production_value=11)
    modernization_city["buildability"]["options"].extend([
        {"type": "unit", "id": 20, "name": "Armor"},
        {"type": "unit", "id": 21, "name": "Nuclear"},
    ])
    modernization_ir = _ruleset_ir((
        ("Alpine Troops", "unit", 60),
        ("Armor", "unit", 80),
        ("Nuclear", "unit", 160),
    ), capabilities={
        "Alpine Troops": {
            "class": "Land", "attack": 5, "defense": 5,
            "hitpoints": 20, "firepower": 1,
        },
        "Armor": {
            "class": "Land", "attack": 10, "defense": 5,
            "hitpoints": 20, "firepower": 1,
        },
        "Nuclear": {
            "class": "Missile", "attack": 99, "defense": 0,
            "hitpoints": 10, "firepower": 1,
        },
    })
    settings = {
        "expansion_city_target": 1,
        "horizon_turn": 100,
        "ruleset_driven_production_enabled": True,
        "modernization_enabled": True,
    }
    modernization = GroundedImpactPlanner(
        settings, ruleset_ir=modernization_ir).plan(_snapshot(
            [_unit(11, "Alpine Troops")],
            [_production(10, "Armor", 6, 20),
             _production(10, "Nuclear", 6, 21),
             {"action_type": "end_turn", "is_valid": True}],
            cities=[modernization_city]))
    assert modernization.candidate.category == "production_modernization"
    assert modernization.candidate.action["target"]["production_type"] == "Armor"
    threatened = GroundedImpactPlanner(
        settings, ruleset_ir=modernization_ir).plan(_snapshot(
            [_unit(11, "Alpine Troops"), _enemy(90, "Armor", 3, 0)],
            [_production(10, "Armor", 6, 20),
             {"action_type": "end_turn", "is_valid": True}],
            cities=[modernization_city]))
    assert threatened.candidate.category == "production_threat_modernization"
    assert threatened.candidate.projection[
        "visible_enemy_domain_power"] > threatened.candidate.projection[
            "current_domain_power"]
    offensive_deficit = GroundedImpactPlanner(
        settings, ruleset_ir=modernization_ir).plan(_snapshot(
            [_unit(11, "Alpine Troops", 4, 4)],
            [_production(10, "Armor", 6, 20),
             {"action_type": "end_turn", "is_valid": True}],
            cities=[modernization_city]))
    assert offensive_deficit.candidate.category == "production_modernization"
    assert "garrison_role_source" not in offensive_deficit.candidate.projection

    defensive_city = _city(production_kind=6, production_value=11)
    defensive_city["buildability"]["options"].extend([
        {"type": "unit", "id": 22, "name": "Mech. Inf."},
        {"type": "unit", "id": 23, "name": "Engineers"},
    ])
    second_city = json.loads(json.dumps(defensive_city))
    second_city.update({"id": 11, "name": "Antium", "x": 2, "y": 2})
    defensive_ir = _ruleset_ir((
        ("Alpine Troops", "unit", 60),
        ("Mech. Inf.", "unit", 60),
        ("Engineers", "unit", 40),
    ), capabilities={
        "Alpine Troops": {
            "class": "Land", "attack": 7, "defense": 4,
            "hitpoints": 20, "firepower": 1,
        },
        "Mech. Inf.": {
            "class": "Land", "attack": 6, "defense": 6,
            "hitpoints": 30, "firepower": 1,
        },
        # A worker can have nonzero combat scalars in a ruleset, but it is not
        # persistent force modernization.
        "Engineers": {
            "class": "Land", "attack": 20, "defense": 20,
            "hitpoints": 20, "firepower": 1,
        },
    })
    defensive = GroundedImpactPlanner(dict(
        settings, expansion_city_target=2, pressure_enabled=True,
        pressure_score_alignment_enabled=True),
        ruleset_ir=defensive_ir).plan(_snapshot(
            [_unit(11, "Alpine Troops", 4, 4)],
            [_production(10, "Mech. Inf.", 6, 22),
             _production(10, "Engineers", 6, 23),
             {"action_type": "end_turn", "is_valid": True}],
            cities=[defensive_city, second_city],
            own_score=20, opponent_score=35))
    assert defensive.candidate.category == "production_defense"
    assert defensive.candidate.action[
        "target"]["production_type"] == "Mech. Inf."
    assert defensive.candidate.projection["defensive_modernization"] is True
    assert defensive.candidate.projection[
        "garrison_role_source"] == "explicit_defender_priority"

    industry_city = _city(production_kind=3, production_value=99)
    industry_city["buildability"]["options"].append(
        {"type": "improvement", "id": 30, "name": "Factory"})
    industry_ir = _ruleset_ir((
        ("Alpine Troops", "unit", 60),
        ("Factory", "building", 100),
    ), capabilities={
        "Alpine Troops": {
            "class": "Land", "attack": 5, "defense": 5,
            "hitpoints": 20, "firepower": 1,
        },
    })
    industry = GroundedImpactPlanner(dict(
        settings, modernization_enabled=False,
        industrialization_enabled=True), ruleset_ir=industry_ir).plan(
            _snapshot(
                [_unit(11, "Alpine Troops")],
                [_production(10, "Factory", 3, 30),
                 {"action_type": "end_turn", "is_valid": True}],
                cities=[industry_city], own_score=20, opponent_score=35))
    assert industry.candidate.category == "production_industrialization"
    assert industry.candidate.action["target"]["production_type"] == "Factory"

    unfunded_industry = _snapshot(
        [_unit(11, "Alpine Troops")],
        [_production(10, "Factory", 3, 30),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[industry_city], own_score=20, opponent_score=35,
        player={
            "gold": 10, "gold_per_turn": 2,
            "operating_gold_per_turn": -10,
            "capitalization_gold_per_turn": 12,
            "city_gold_surplus_per_turn": -10,
            "unit_gold_upkeep": 0, "gold_upkeep_reserve": 0,
        })
    assert GroundedImpactPlanner(dict(
        settings, modernization_enabled=False,
        industrialization_enabled=True),
        ruleset_ir=industry_ir).plan(unfunded_industry) is None

    funded_industry = _snapshot(
        [_unit(11, "Alpine Troops")],
        [_production(10, "Factory", 3, 30),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[industry_city], source_seq=2,
        own_score=20, opponent_score=35,
        player={
            "gold": 500, "gold_per_turn": 2,
            "operating_gold_per_turn": -10,
            "capitalization_gold_per_turn": 12,
            "city_gold_surplus_per_turn": -10,
            "unit_gold_upkeep": 0, "gold_upkeep_reserve": 0,
        })
    funded = GroundedImpactPlanner(dict(
        settings, modernization_enabled=False,
        industrialization_enabled=True),
        ruleset_ir=industry_ir).plan(funded_industry)
    assert funded.candidate.category == "production_industrialization"
    assert funded.candidate.projection[
        "treasury_construction_runway_turns"] > 0


def test_missing_land_capability_is_funded_retained_survival_work():
    city = _city(
        shield_stock=0, surplus=(1, 5, 2, 1, 0, 3),
        production_kind=3, production_value=72)
    city["buildability"]["options"].extend([
        {"type": "unit", "id": 20, "name": "Armor"},
        {"type": "unit", "id": 21, "name": "Marines"},
        {"type": "improvement", "id": 72, "name": "Coinage"},
    ])
    ruleset = _ruleset_ir((
        ("Workers", "unit", 20),
        ("Armor", "unit", 80),
        ("Marines", "unit", 100),
        ("Coinage", "improvement", 10),
    ), founders=(), workers=("Workers",), capabilities={
        "Workers": {
            "class": "Land", "attack": 1, "defense": 1,
            "hitpoints": 10, "firepower": 1,
        },
        "Armor": {
            "class": "Land", "attack": 10, "defense": 5,
            "hitpoints": 20, "firepower": 1,
        },
        "Marines": {
            "class": "Land", "attack": 12, "defense": 5,
            "hitpoints": 20, "firepower": 1,
        },
    })
    settings = {
        "expansion_city_target": 1,
        "horizon_turn": 100,
        "ruleset_driven_production_enabled": True,
        "modernization_enabled": True,
        "pressure_enabled": True,
        "pressure_score_alignment_enabled": True,
    }
    snapshot = _snapshot(
        [_unit(30, "Workers")],
        [_production(10, "Armor", 6, 20),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[city],
        player={
            "gold": 200, "gold_per_turn": 6,
            "operating_gold_per_turn": -5,
            "capitalization_gold_per_turn": 11,
            "city_gold_surplus_per_turn": -5,
            "unit_gold_upkeep": 0, "gold_upkeep_reserve": 0,
        })
    planner = GroundedImpactPlanner(settings, ruleset_ir=ruleset)

    decision = planner.plan(snapshot)

    assert decision.candidate.category == "production_land_capability"
    assert decision.candidate.action["target"]["production_type"] == "Armor"
    assert decision.candidate.projection["land_capability_deficit"] is True
    assert decision.candidate.projection[
        "treasury_at_completion"] >= decision.candidate.projection[
            "treasury_reserve_required"]

    queued_city = dict(city, shield_stock=5, production_kind=6,
                       production_value=20)
    queued = _snapshot(
        [_unit(30, "Workers")],
        [_production(10, "Marines", 6, 21),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[queued_city], source_seq=2, turn=5,
        player={
            "gold": 200, "gold_per_turn": -5,
            "operating_gold_per_turn": -5,
            "capitalization_gold_per_turn": 0,
            "city_gold_surplus_per_turn": -5,
            "unit_gold_upkeep": 0, "gold_upkeep_reserve": 0,
        })
    assert planner.plan(queued) is None


def test_commerce_infrastructure_requires_structural_construction_runway():
    city = _city(production_kind=3, production_value=31)
    city["buildability"]["options"].extend([
        {"type": "improvement", "id": 30, "name": "Bank"},
        {"type": "improvement", "id": 31, "name": "Coinage"},
    ])
    ruleset = _ruleset_ir((
        ("Alpine Troops", "unit", 60),
        ("Bank", "building", 100),
        ("Coinage", "building", 10),
    ))
    actions = [
        _production(10, "Bank", 3, 30),
        {"action_type": "end_turn", "is_valid": True},
    ]
    settings = {
        "expansion_city_target": 1,
        "horizon_turn": 100,
        "ruleset_driven_production_enabled": True,
        "structural_economy_maximum_completion_turns": 30,
    }
    insufficient = _snapshot(
        [_unit(11, "Alpine Troops")], actions, cities=[city],
        player={
            "gold": 4, "gold_per_turn": 5,
            "operating_gold_per_turn": -10,
            "capitalization_gold_per_turn": 15,
            "gold_upkeep_style": "Mixed",
        })
    durable = _snapshot(
        [_unit(11, "Alpine Troops")], actions, cities=[city], source_seq=2,
        player={
            "gold": 500, "gold_per_turn": 5,
            "operating_gold_per_turn": -10,
            "capitalization_gold_per_turn": 15,
            "gold_upkeep_style": "Mixed",
        })
    treasury_funded_but_not_self_financing = _snapshot(
        [_unit(11, "Alpine Troops")], actions, cities=[city], source_seq=3,
        player={
            "gold": 500, "gold_per_turn": 3,
            "operating_gold_per_turn": -10,
            "capitalization_gold_per_turn": 13,
            "gold_upkeep_style": "Mixed",
        })

    assert GroundedImpactPlanner(
        settings, ruleset_ir=ruleset).plan(insufficient) is None
    assert GroundedImpactPlanner(
        settings, ruleset_ir=ruleset).plan(
            treasury_funded_but_not_self_financing) is None
    assert GroundedImpactPlanner(
        dict(settings, structural_economy_maximum_completion_turns=20),
        ruleset_ir=ruleset).plan(durable) is None
    decision = GroundedImpactPlanner(
        settings, ruleset_ir=ruleset).plan(durable)
    assert decision.candidate.category == "production_commerce_infrastructure"
    assert decision.candidate.projection["operating_gold_per_turn"] == -10
    assert decision.candidate.projection["effective_gold_per_turn"] == 5
    assert decision.candidate.projection["selected_city_coinage_removed"] == 4
    assert decision.candidate.projection["construction_gold_per_turn"] == 1
    assert decision.candidate.projection[
        "treasury_after_post_completion_runway"] >= (
            decision.candidate.projection[
                "structural_treasury_reserve_required"])
    assert decision.candidate.projection[
        "structural_benefit_assumption"] == "none-until-observed"


def test_structural_commerce_recovery_is_one_at_a_time_and_held_from_zero_stock():
    first = _city(
        shield_stock=0, production_kind=3, production_value=30)
    first["buildability"]["options"].extend([
        {"type": "improvement", "id": 30, "name": "Marketplace"},
        {"type": "improvement", "id": 31, "name": "Coinage"},
    ])
    second = dict(
        _city(
            shield_stock=0, production_kind=3, production_value=31),
        id=20, name="Antium", tile=2, x=2)
    second["buildability"] = {"available": True, "options": [
        {"type": "improvement", "id": 30, "name": "Marketplace"},
        {"type": "improvement", "id": 31, "name": "Coinage"},
        {"type": "improvement", "id": 32, "name": "Bank"},
    ]}
    ruleset = _ruleset_ir((
        ("Alpine Troops", "unit", 60),
        ("Marketplace", "building", 60),
        ("Bank", "building", 100),
        ("Coinage", "building", 10),
    ))
    settings = {
        "expansion_city_target": 1,
        "horizon_turn": 100,
        "ruleset_driven_production_enabled": True,
    }
    player = {
        "gold": 500, "gold_per_turn": 4,
        "operating_gold_per_turn": -4,
        "capitalization_gold_per_turn": 8,
        "gold_upkeep_style": "Mixed",
    }

    held = _snapshot(
        [_unit(11, "Alpine Troops")],
        [_production(10, "Coinage", 3, 31),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[first, second], player=player)
    parallel = _snapshot(
        [_unit(11, "Alpine Troops")],
        [_production(20, "Bank", 3, 32),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[first, second], source_seq=2, player=player)

    planner = GroundedImpactPlanner(settings, ruleset_ir=ruleset)
    assert planner.plan(held) is None
    assert planner.plan(parallel) is None
    assert planner._structural_commerce_projects(parallel) == (
        (10, "marketplace", 0),)


def test_structural_commerce_financing_includes_ruleset_building_upkeep():
    city = _city(production_kind=3, production_value=31)
    city["buildability"]["options"].extend([
        {"type": "improvement", "id": 30, "name": "Bank"},
        {"type": "improvement", "id": 31, "name": "Coinage"},
    ])
    ruleset = _ruleset_ir((
        ("Alpine Troops", "unit", 60),
        ("Bank", "building", 100),
        ("Coinage", "building", 10),
    ), upkeeps={"Bank": {"upkeep": 3}})
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [_production(10, "Bank", 3, 30),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[city],
        player={
            "gold": 12, "gold_per_turn": 4,
            "operating_gold_per_turn": -10,
            "capitalization_gold_per_turn": 14,
            "gold_upkeep_style": "Mixed",
        })

    planner = GroundedImpactPlanner({
        "expansion_city_target": 1,
        "horizon_turn": 100,
        "ruleset_driven_production_enabled": True,
        "structural_economy_maximum_completion_turns": 30,
    }, ruleset_ir=ruleset)

    assert planner._production_specs["bank"]["building_upkeep"] == 3
    assert planner.plan(snapshot) is None


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
    assert decision.plan.steps[0].spatial == {"x": 2, "y": 0}

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


def test_founder_prefers_adjacent_packet_confirmed_settlement_site():
    confirmed = {
        "action_type": "unit_move", "actor_id": 1,
        "settlement_site_eligible": True,
        "target": {"x": 3, "y": 1}, "is_valid": True,
    }
    farther = {
        "action_type": "unit_move", "actor_id": 1,
        "settlement_site_eligible": False,
        "target": {"x": 4, "y": 0}, "is_valid": True,
    }
    snapshot = _snapshot(
        [_unit(1, "Settlers", 3, 0)],
        [farther, confirmed,
         {"action_type": "end_turn", "is_valid": True}])
    ir = _ruleset_ir((("Settlers", "unit", 30),))

    preferred = GroundedImpactPlanner(ruleset_ir=ir).plan(snapshot)

    assert preferred.candidate.action["target"] == {"x": 3, "y": 1}
    assert preferred.candidate.utility == 990.0
    assert preferred.candidate.projection[
        "settlement_site_preference_active"] is True
    assert preferred.candidate.projection[
        "settlement_site_preference_source"] == (
            "packet-ruleset-found-city-preconditions")

    disabled = GroundedImpactPlanner({
        "expansion_packet_site_preference_enabled": False,
    }, ruleset_ir=ir).plan(snapshot)
    assert disabled.candidate.action["target"] == {"x": 4, "y": 0}
    assert disabled.candidate.projection[
        "settlement_site_preference_active"] is False

    unknown = _snapshot(
        [_unit(1, "Settlers", 3, 0)],
        [{key: value for key, value in farther.items()
          if key != "settlement_site_eligible"},
         {key: value for key, value in confirmed.items()
          if key != "settlement_site_eligible"},
         {"action_type": "end_turn", "is_valid": True}],
        source_seq=2)
    assert GroundedImpactPlanner(ruleset_ir=ir).plan(
        unknown).candidate.action["target"] == {"x": 4, "y": 0}


def test_packet_site_preference_never_preempts_founding_current_site():
    move = {
        "action_type": "unit_move", "actor_id": 1,
        "settlement_site_eligible": True,
        "target": {"x": 4, "y": 0}, "is_valid": True,
    }
    found = {
        "action_type": "unit_build_city", "actor_id": 1, "is_valid": True,
    }
    snapshot = _snapshot(
        [_unit(1, "Settlers", 3, 0)],
        [move, found, {"action_type": "end_turn", "is_valid": True}])

    decision = GroundedImpactPlanner().plan(snapshot)

    assert decision.candidate.category == "city_founding"
    assert decision.candidate.action["action_type"] == "unit_build_city"


def test_founder_escort_retention_waits_routes_and_confirms_settlement():
    build = {
        "action_type": "unit_build_city", "actor_id": 1, "is_valid": True,
    }
    end_turn = {"action_type": "end_turn", "is_valid": True}
    ir = _ruleset_ir((
        ("Settlers", "unit", 30),
        ("Alpine Troops", "unit", 60),
        ("Riflemen", "unit", 40),
    ))
    values = {"expansion_escort_retention_enabled": True}
    unescorted = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(11, "Alpine Troops", 0, 0),
    ], [build, end_turn])

    compatible = GroundedImpactPlanner(ruleset_ir=ir).plan(unescorted)
    assert compatible.candidate.category == "city_founding"

    planner = GroundedImpactPlanner(values, ruleset_ir=ir)
    assert planner.plan(unescorted) is None
    assert planner.founder_escort_deferral_snapshots == 1

    diplomat_move = {
        "action_type": "unit_move", "actor_id": 7,
        "target": {"x": 1, "y": 1}, "is_valid": True,
    }
    noncombat = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(7, "Diplomat", 0, 1),
        _unit(11, "Alpine Troops", 0, 0),
    ], [build, diplomat_move, end_turn], source_seq=2)
    assert planner.plan(noncombat).candidate.category == "exploration_move"

    escort_move = {
        "action_type": "unit_move", "actor_id": 12,
        "target": {"x": 1, "y": 0}, "is_valid": True,
    }
    approaching = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(11, "Alpine Troops", 0, 0),
        _unit(12, "Riflemen", 0, 0),
    ], [build, escort_move, end_turn], source_seq=2)
    decision = planner.plan(approaching)
    assert decision.candidate.category == "founder_escort_move"
    assert decision.candidate.projection["current_founder_distance"] == 3
    assert decision.candidate.projection["target_founder_distance"] == 2
    assert decision.candidate.projection["target_founder_ids"] == (1,)

    moved = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(11, "Alpine Troops", 0, 0),
        _unit(12, "Riflemen", 1, 0),
    ], [build, end_turn], source_seq=3)
    planner.record_outcome(decision.candidate, approaching, True, moved)
    assert planner.founder_escort_move_attempts == 1
    assert planner.founder_escort_move_successes == 1

    escorted = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(11, "Alpine Troops", 0, 0),
        _unit(12, "Riflemen", 3, 0),
    ], [build, end_turn], source_seq=4)
    founding = planner.plan(escorted)
    assert founding.candidate.category == "city_founding"
    assert founding.candidate.projection["settlement_escort_present"] is True
    assert founding.candidate.projection[
        "settlement_escort_unit_ids"] == (12,)

    second_city = _city()
    second_city.update({
        "id": 13, "name": "Antium", "tile": 3, "x": 3, "size": 1,
    })
    settled = _snapshot([
        _unit(11, "Alpine Troops", 0, 0),
        _unit(12, "Riflemen", 3, 0),
    ], [end_turn], cities=[_city(), second_city], source_seq=5)
    planner.record_outcome(
        founding.candidate, escorted, True, settled)
    assert planner.founder_escorted_settlement_attempts == 1
    assert planner.founder_escorted_settlement_completions == 1


def test_founder_escort_threat_gate_bypasses_safe_sites_and_guards_local_threats():
    build = {
        "action_type": "unit_build_city", "actor_id": 1, "is_valid": True,
    }
    end_turn = {"action_type": "end_turn", "is_valid": True}
    ir = _ruleset_ir((
        ("Settlers", "unit", 30),
        ("Alpine Troops", "unit", 60),
        ("Riflemen", "unit", 40),
    ))
    values = {
        "expansion_escort_retention_enabled": True,
        "expansion_escort_threat_gating_enabled": True,
        "pressure_survival_threat_radius": 3,
    }
    planner = GroundedImpactPlanner(values, ruleset_ir=ir)

    safe = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(11, "Alpine Troops", 0, 0),
        _enemy(90, "Warriors", 7, 0),
    ], [build, end_turn])
    founding = planner.plan(safe)

    assert founding.candidate.category == "city_founding"
    assert founding.candidate.projection[
        "settlement_escort_required"] is False
    assert founding.candidate.projection[
        "settlement_escort_safe_bypass"] is True
    assert founding.candidate.projection[
        "settlement_visible_threat_unit_ids"] == ()
    settled_city = _city()
    settled_city.update({
        "id": 13, "name": "Antium", "tile": 3, "x": 3, "size": 1,
    })
    settled = _snapshot([
        _unit(11, "Alpine Troops", 0, 0),
        _enemy(90, "Warriors", 7, 0),
    ], [end_turn], cities=[_city(), settled_city], source_seq=2)
    planner.record_outcome(
        founding.candidate, safe, True, settled)
    assert planner.founder_unescorted_safe_settlement_attempts == 1
    assert planner.founder_unescorted_safe_settlement_completions == 1

    threatened = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(11, "Alpine Troops", 0, 0),
        _enemy(91, "Settlers", 5, 0),
    ], [build, end_turn], source_seq=3)

    assert planner.plan(threatened) is None
    assert planner.founder_escort_deferral_snapshots == 1
    assert planner.founder_escort_threat_deferral_snapshots == 1

    escort_move = {
        "action_type": "unit_move", "actor_id": 12,
        "target": {"x": 1, "y": 0}, "is_valid": True,
    }
    approaching = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(11, "Alpine Troops", 0, 0),
        _unit(12, "Riflemen", 0, 0),
        _enemy(91, "Settlers", 5, 0),
    ], [build, escort_move, end_turn], source_seq=4)
    escort = planner.plan(approaching)

    assert escort.candidate.category == "founder_escort_move"
    assert escort.candidate.projection["target_founder_ids"] == (1,)


def test_founder_route_threat_memory_persists_local_contestation_until_settlement():
    move = {
        "action_type": "unit_move", "actor_id": 1,
        "target": {"x": 3, "y": 0}, "is_valid": True,
    }
    build = {
        "action_type": "unit_build_city", "actor_id": 1, "is_valid": True,
    }
    end_turn = {"action_type": "end_turn", "is_valid": True}
    ir = _ruleset_ir((
        ("Settlers", "unit", 30),
        ("Alpine Troops", "unit", 60),
    ))
    planner = GroundedImpactPlanner({
        "expansion_escort_retention_enabled": True,
        "expansion_escort_threat_gating_enabled": True,
        "expansion_escort_route_threat_memory_enabled": True,
        "pressure_survival_threat_radius": 3,
        "pressure_enabled": True,
    }, ruleset_ir=ir)
    contested_route = _snapshot([
        _unit(1, "Settlers", 2, 0),
        _unit(11, "Alpine Troops", 0, 0),
        _enemy(91, "Settlers", 4, 0),
    ], [move, end_turn], turn=8)

    planner.candidates(contested_route)
    assert planner.founder_route_threat_observations == 1

    disappeared_before_founding = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(11, "Alpine Troops", 0, 0),
    ], [build, end_turn], source_seq=2, turn=9)

    assert planner.plan(disappeared_before_founding) is None
    assert planner.founder_escort_threat_deferral_snapshots == 1
    assert planner.founder_escort_persisted_threat_deferral_snapshots == 1

    escape = {
        "action_type": "unit_move", "actor_id": 1,
        "target": {"x": 2, "y": 0}, "is_valid": True,
    }
    can_relocate = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(11, "Alpine Troops", 0, 0),
    ], [build, escape, end_turn], source_seq=3, turn=9)
    avoidance = planner.plan(can_relocate)
    assert avoidance.candidate.category == "founder_threat_avoidance_move"
    assert avoidance.candidate.projection[
        "current_route_threat_distance"] == 1
    assert avoidance.candidate.projection[
        "target_route_threat_distance"] == 2
    relocated = _snapshot([
        _unit(1, "Settlers", 2, 0),
        _unit(11, "Alpine Troops", 0, 0),
    ], [end_turn], source_seq=4, turn=9)
    planner.record_outcome(
        avoidance.candidate, can_relocate, True, relocated)
    assert planner.founder_threat_avoidance_move_attempts == 1
    assert planner.founder_threat_avoidance_move_successes == 1

    no_memory = GroundedImpactPlanner({
        "expansion_escort_retention_enabled": True,
        "expansion_escort_threat_gating_enabled": True,
        "expansion_escort_route_threat_memory_enabled": False,
        "pressure_survival_threat_radius": 3,
    }, ruleset_ir=ir)
    no_memory.candidates(contested_route)
    bypass = no_memory.plan(disappeared_before_founding)
    assert bypass.candidate.category == "city_founding"
    assert bypass.candidate.projection[
        "settlement_escort_safe_bypass"] is True


def test_contested_founder_can_ground_empty_stock_escort_production():
    city = _city(
        size=4, food_stock=20, shield_stock=0,
        production_kind=3, production_value=14)
    build = {
        "action_type": "unit_build_city", "actor_id": 1, "is_valid": True,
    }
    actions = [
        build,
        _production(10, "Alpine Troops", 6, 11),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ir = _ruleset_ir((
        ("Settlers", "unit", 30),
        ("Alpine Troops", "unit", 40),
        ("Granary", "improvement", 40),
    ), pop_costs={"Settlers": 1})
    planner = GroundedImpactPlanner({
        "expansion_escort_retention_enabled": True,
        "expansion_escort_threat_gating_enabled": True,
        "expansion_escort_route_threat_memory_enabled": True,
        "horizon_turn": 60,
    }, ruleset_ir=ir)
    contested = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(11, "Alpine Troops", 0, 0),
        _enemy(91, "Settlers", 5, 0),
    ], actions, cities=[city], turn=20)

    decision = planner.plan(contested)

    assert decision.candidate.category == "production_defense"
    assert decision.candidate.action["target"][
        "production_type"] == "Alpine Troops"
    assert decision.candidate.projection[
        "settlement_escort_defense"] is True
    assert "repurpose_discarded_shield_stock" not in (
        decision.candidate.projection)


def test_unescorted_legal_site_repurposes_founder_queue_to_defense():
    city = _city(
        size=4, food_stock=20, shield_stock=10,
        production_kind=6, production_value=0)
    actions = [
        {
            "action_type": "unit_build_city", "actor_id": 1,
            "is_valid": True,
        },
        _production(10, "Alpine Troops", 6, 11),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ir = _ruleset_ir((
        ("Settlers", "unit", 30),
        ("Alpine Troops", "unit", 40),
    ), pop_costs={"Settlers": 1})
    planner = GroundedImpactPlanner({
        "expansion_escort_retention_enabled": True,
        "horizon_turn": 60,
    }, ruleset_ir=ir)

    decision = planner.plan(_snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(11, "Alpine Troops", 0, 0),
    ], actions, cities=[city], turn=6))

    assert decision.candidate.category == "production_defense"
    assert decision.candidate.action["target"][
        "production_type"] == "Alpine Troops"
    assert decision.candidate.projection[
        "settlement_escort_defense"] is True
    assert decision.candidate.projection[
        "unescorted_founder_ids"] == (1,)
    assert decision.candidate.projection[
        "repurpose_discarded_shield_stock"] == 10
    changed_city = dict(city, production_kind=6, production_value=11)
    changed = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(11, "Alpine Troops", 0, 0),
    ], [{"action_type": "end_turn", "is_valid": True}],
        cities=[changed_city], source_seq=2, turn=6)
    planner.record_outcome(
        decision.candidate, _snapshot([
            _unit(1, "Settlers", 3, 0),
            _unit(11, "Alpine Troops", 0, 0),
        ], actions, cities=[city], turn=6), True, changed)
    assert planner.founder_escort_defense_production_attempts == 1
    assert planner.founder_escort_defense_production_successes == 1


def test_final_settlement_escort_prepares_early_and_tracks_only_last_founder():
    second_city = dict(
        _city(), id=20, name="Antium", tile=30, x=0, y=3,
        production_kind=3, production_value=14, shield_stock=0)
    founder_city = _city(
        size=3, food_stock=20, shield_stock=50,
        production_kind=6, production_value=0)
    production_actions = [
        _production(10, "Alpine Troops", 6, 11),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ir = _ruleset_ir((
        ("Settlers", "unit", 30),
        ("Alpine Troops", "unit", 40),
        ("Granary", "improvement", 40),
    ), pop_costs={"Settlers": 1})
    values = {
        "expansion_city_target": 4,
        "expansion_escort_retention_enabled": True,
        "expansion_escort_threat_gating_enabled": True,
        "expansion_final_settlement_escort_enabled": True,
        "horizon_turn": 60,
    }
    planner = GroundedImpactPlanner(values, ruleset_ir=ir)
    before = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(2, "Settlers", 5, 3),
        _unit(11, "Alpine Troops", 0, 0),
    ], production_actions, cities=[founder_city, second_city], turn=20)

    preparation = planner.plan(before)

    assert preparation.candidate.category == "production_defense"
    assert preparation.candidate.action["target"][
        "production_type"] == "Alpine Troops"
    assert preparation.candidate.projection[
        "settlement_final_escort_preparation"] is True
    assert preparation.candidate.projection[
        "repurpose_same_production_kind"] is True
    assert preparation.candidate.projection[
        "repurpose_shield_stock_assumption"] == 50
    assert preparation.candidate.projection[
        "repurpose_discarded_shield_stock"] == 0
    changed_city = dict(
        founder_city, production_kind=6, production_value=11)
    changed = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(2, "Settlers", 5, 3),
        _unit(11, "Alpine Troops", 0, 0),
    ], [{"action_type": "end_turn", "is_valid": True}],
        cities=[changed_city, second_city], source_seq=2, turn=20)
    planner.record_outcome(
        preparation.candidate, before, True, changed)
    assert planner.founder_final_escort_preparation_production_attempts == 1
    assert planner.founder_final_escort_preparation_production_successes == 1

    escort_move = {
        "action_type": "unit_move", "actor_id": 12,
        "target": {"x": 1, "y": 1}, "is_valid": True,
    }
    premature_founder_move = {
        "action_type": "unit_move", "actor_id": 2,
        "target": {"x": 6, "y": 3}, "is_valid": True,
    }
    routing = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(2, "Settlers", 5, 3),
        _unit(11, "Alpine Troops", 0, 0),
        _unit(12, "Riflemen", 0, 0),
        _enemy(91, "Settlers", 7, 3),
    ], [premature_founder_move, escort_move,
        {"action_type": "end_turn", "is_valid": True}],
        cities=[founder_city, second_city], source_seq=3, turn=21)
    escort = planner.plan(routing)
    assert escort.candidate.category == "founder_escort_move"
    assert escort.candidate.projection[
        "settlement_final_escort_preparation"] is True
    assert escort.candidate.projection["target_founder_ids"] == (2,)
    assert planner.founder_final_escort_rendezvous_hold_snapshots == 1

    coordinated_route = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(2, "Settlers", 5, 3),
        _unit(11, "Alpine Troops", 0, 0),
        _unit(12, "Riflemen", 5, 3),
        _enemy(91, "Settlers", 7, 3),
    ], [premature_founder_move,
        {"action_type": "end_turn", "is_valid": True}],
        cities=[founder_city, second_city], source_seq=4, turn=22)
    founder_route = planner.plan(coordinated_route)
    assert founder_route.candidate.category == "expansion_move"
    assert founder_route.candidate.action["actor_id"] == 2
    assert planner.founder_final_escort_rendezvous_hold_snapshots == 1

    third_city = dict(
        _city(), id=30, name="Cumae", tile=60, x=0, y=6,
        production_kind=3, production_value=14, shield_stock=0)
    build = {
        "action_type": "unit_build_city", "actor_id": 2, "is_valid": True,
    }
    final_site = _snapshot([
        _unit(2, "Settlers", 5, 3),
        _unit(11, "Alpine Troops", 0, 0),
        _enemy(91, "Settlers", 7, 3),
    ], [build, {"action_type": "end_turn", "is_valid": True}],
        cities=[founder_city, second_city, third_city],
        source_seq=5, turn=25)
    assert planner.plan(final_site) is None
    assert planner.founder_final_escort_deferral_snapshots == 1

    escorted_site = _snapshot([
        _unit(2, "Settlers", 5, 3),
        _unit(11, "Alpine Troops", 0, 0),
        _unit(12, "Riflemen", 5, 3),
        _enemy(91, "Settlers", 7, 3),
    ], [build, {"action_type": "end_turn", "is_valid": True}],
        cities=[founder_city, second_city, third_city],
        source_seq=6, turn=26)
    founding = planner.plan(escorted_site)
    assert founding.candidate.category == "city_founding"
    assert founding.candidate.projection["settlement_final_escort"] is True
    assert founding.candidate.projection["settlement_escort_present"] is True


def test_final_founder_does_not_wait_without_a_legal_escort_progress_step():
    second_city = dict(
        _city(), id=20, name="Antium", tile=30, x=0, y=3,
        production_kind=3, production_value=14, shield_stock=0)
    founder_move = {
        "action_type": "unit_move", "actor_id": 2,
        "target": {"x": 6, "y": 3}, "is_valid": True,
    }
    planner = GroundedImpactPlanner({
        "expansion_city_target": 4,
        "expansion_escort_retention_enabled": True,
        "expansion_escort_threat_gating_enabled": True,
        "expansion_final_settlement_escort_enabled": True,
        "horizon_turn": 60,
    }, ruleset_ir=_ruleset_ir((
        ("Settlers", "unit", 30),
        ("Riflemen", "unit", 30),
    ), pop_costs={"Settlers": 1}))
    snapshot = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(2, "Settlers", 5, 3),
        _unit(12, "Riflemen", 1, 1),
    ], [founder_move, {"action_type": "end_turn", "is_valid": True}],
        cities=[_city(), second_city], source_seq=3, turn=21)

    unprepared = planner.plan(snapshot)

    assert unprepared.candidate.category == "expansion_move"
    assert unprepared.candidate.action["actor_id"] == 2
    assert (
        planner.founder_final_escort_unprepared_route_bypass_snapshots == 1)
    assert planner.founder_final_escort_rendezvous_hold_snapshots == 0
    assert (
        planner.founder_final_escort_rendezvous_no_progress_snapshots == 0)

    planner.founder_final_escort_preparation_production_successes = 1
    prepared_snapshot = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(2, "Settlers", 5, 3),
        _unit(12, "Riflemen", 1, 1),
    ], [founder_move, {"action_type": "end_turn", "is_valid": True}],
        cities=[_city(), second_city], source_seq=4, turn=21)
    decision = planner.plan(prepared_snapshot)

    assert decision.candidate.category == "expansion_move"
    assert decision.candidate.action["actor_id"] == 2
    assert planner.founder_final_escort_rendezvous_hold_snapshots == 0
    assert (
        planner.founder_final_escort_unthreatened_route_bypass_snapshots == 1)
    assert (
        planner.founder_final_escort_rendezvous_no_progress_snapshots == 0)

    threatened_snapshot = _snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(2, "Settlers", 5, 3),
        _unit(12, "Riflemen", 1, 1),
        _enemy(91, "Settlers", 7, 3),
    ], [founder_move, {"action_type": "end_turn", "is_valid": True}],
        cities=[_city(), second_city], source_seq=5, turn=21)
    threatened = planner.plan(threatened_snapshot)

    assert threatened.candidate.category == "expansion_move"
    assert threatened.candidate.action["actor_id"] == 2
    assert (
        planner.founder_final_escort_rendezvous_no_progress_snapshots == 1)


def test_final_escort_preparation_requires_immediate_spare_delivery():
    second_city = dict(
        _city(), id=20, name="Antium", tile=30, x=0, y=3,
        production_kind=3, production_value=14, shield_stock=0)
    actions = [
        _production(10, "Alpine Troops", 6, 11),
        _production(10, "Granary", 3, 14),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ir = _ruleset_ir((
        ("Settlers", "unit", 30),
        ("Alpine Troops", "unit", 40),
        ("Granary", "improvement", 40),
    ), pop_costs={"Settlers": 1})
    values = {
        "expansion_city_target": 4,
        "expansion_escort_retention_enabled": True,
        "expansion_escort_threat_gating_enabled": True,
        "expansion_final_settlement_escort_enabled": True,
        "horizon_turn": 60,
    }

    undefended = GroundedImpactPlanner(values, ruleset_ir=ir).plan(_snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(2, "Settlers", 5, 3),
    ], actions, cities=[
        _city(size=3, food_stock=20, shield_stock=50,
              production_kind=6, production_value=0),
        second_city,
    ], turn=20))
    assert undefended.candidate.category == "production_defense"
    assert undefended.candidate.projection["mandatory_local_garrison"] is True
    assert not (undefended.candidate.projection or {}).get(
        "settlement_final_escort_preparation", False)

    delayed = GroundedImpactPlanner(values, ruleset_ir=ir).plan(_snapshot([
        _unit(1, "Settlers", 3, 0),
        _unit(2, "Settlers", 5, 3),
        _unit(11, "Alpine Troops", 0, 0),
    ], actions, cities=[
        _city(size=3, food_stock=20, shield_stock=10,
              production_kind=6, production_value=0),
        second_city,
    ], turn=20))
    assert delayed.candidate.category == "production_repurpose"
    assert not (delayed.candidate.projection or {}).get(
        "settlement_final_escort_preparation", False)


def test_ineligible_final_preparation_does_not_suppress_ordinary_defense():
    second_city = dict(
        _city(), id=20, name="Antium", tile=30, x=0, y=3,
        production_kind=3, production_value=14, shield_stock=0)
    cities = [
        _city(
            production_kind=3, production_value=14, shield_stock=0),
        second_city,
    ]
    actions = [
        _production(10, "Alpine Troops", 6, 11),
        {"action_type": "end_turn", "is_valid": True},
    ]
    units = [
        _unit(1, "Settlers", 3, 0),
        _unit(11, "Alpine Troops", 0, 0),
    ]
    ir = _ruleset_ir((
        ("Settlers", "unit", 30),
        ("Alpine Troops", "unit", 40),
        ("Granary", "improvement", 40),
    ), pop_costs={"Settlers": 1})
    common = {
        "expansion_city_target": 3,
        "expansion_escort_retention_enabled": True,
        "expansion_escort_threat_gating_enabled": True,
        "horizon_turn": 60,
    }

    baseline = GroundedImpactPlanner(
        dict(common, expansion_final_settlement_escort_enabled=False),
        ruleset_ir=ir).plan(
            _snapshot(units, actions, cities=cities, turn=20))
    treatment = GroundedImpactPlanner(
        dict(common, expansion_final_settlement_escort_enabled=True),
        ruleset_ir=ir).plan(
            _snapshot(units, actions, cities=cities, turn=20))

    assert baseline.candidate.category == "production_defense"
    assert treatment.candidate.action == baseline.candidate.action
    assert treatment.candidate.category == baseline.candidate.category
    assert not (treatment.candidate.projection or {}).get(
        "settlement_final_escort_preparation", False)


def test_packet_site_preference_records_exact_move_outcome():
    action = {
        "action_type": "unit_move", "actor_id": 1,
        "settlement_site_eligible": True,
        "target": {"x": 3, "y": 1}, "is_valid": True,
    }
    before = _snapshot(
        [_unit(1, "Settlers", 3, 0)],
        [action, {"action_type": "end_turn", "is_valid": True}])
    after = _snapshot(
        [_unit(1, "Settlers", 3, 1)],
        [{"action_type": "end_turn", "is_valid": True}], source_seq=2)
    planner = GroundedImpactPlanner(
        ruleset_ir=_ruleset_ir((("Settlers", "unit", 30),)))
    candidate = planner.plan(before).candidate

    planner.record_outcome(
        candidate, before, effect_observed=True, after_snapshot=after)

    assert planner.founder_settlement_site_preference_attempts == 1
    assert planner.founder_settlement_site_preference_successes == 1


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

    # Founding a city changes which outward corridor is strategically useful.
    # The exact edge remains terrain evidence, but must not receive a stale
    # route bonus under a different city layout.
    frontier_city = _city()
    frontier_city.update({"id": 12, "name": "Antium", "tile": 5,
                          "x": 5, "y": 0})
    changed_layout = _snapshot(
        [_unit(2, "Settlers")], [
            {"action_type": "unit_move", "actor_id": 2,
             "target": {"x": 0, "y": 1}, "is_valid": True},
            {"action_type": "unit_move", "actor_id": 2,
             "target": {"x": 1, "y": 0}, "is_valid": True},
            {"action_type": "end_turn", "is_valid": True},
        ], cities=[_city(), frontier_city], source_seq=4)
    changed_decision = planner.plan(changed_layout)
    assert changed_decision.candidate.action["target"] == {"x": 0, "y": 1}
    assert not changed_decision.candidate.projection["traversable_edge"]


def test_founder_move_candidate_reuses_route_evidence_and_action_catalog():
    advertised = [
        {"action_type": "unit_move", "actor_id": 1,
         "target": {"x": 1, "y": 0}, "is_valid": True},
        {"action_type": "unit_move", "actor_id": 1,
         "target": {"x": 0, "y": 1}, "is_valid": True},
        {"action_type": "end_turn", "is_valid": True},
    ]
    snapshot = _snapshot([_unit(1, "Settlers")], advertised)
    planner = GroundedImpactPlanner(
        ruleset_ir=_ruleset_ir((("Settlers", "unit", 30),)))
    actions = planner._actions(snapshot)
    founder_types = planner._founder_types(snapshot, actions)
    evidence_calls = []
    evidence = planner._founder_move_evidence

    def recording_evidence(current, action, current_founder_types):
        evidence_calls.append(action)
        return evidence(current, action, current_founder_types)

    planner._founder_move_evidence = recording_evidence
    candidates = [
        planner._move_candidate(
            snapshot, action, founder_types, actions=actions)
        for action in actions if action.get("action_type") == "unit_move"
    ]

    assert all(candidate is not None for candidate in candidates)
    assert evidence_calls == [
        action for action in actions
        if action.get("action_type") == "unit_move"]


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


def test_founder_route_breaks_two_tile_cycle_but_allows_only_escape():
    ir = _ruleset_ir((("Settlers", "unit", 30),))
    planner = GroundedImpactPlanner(ruleset_ir=ir)
    branch = (1, 0)
    dead_end = (2, 0)
    alternative = (1, 1)

    def move(source, target):
        action = {"action_type": "unit_move", "actor_id": 1,
                  "target": {"x": target[0], "y": target[1]}}
        before = _snapshot(
            [_unit(1, "Settlers", source[0], source[1])],
            [dict(action, is_valid=True),
             {"action_type": "end_turn", "is_valid": True}])
        after = _snapshot(
            [_unit(1, "Settlers", target[0], target[1])],
            [{"action_type": "end_turn", "is_valid": True}], source_seq=2)
        planner.record_outcome(
            ImpactCandidate(action, "expansion_move", 1.0, "route history"),
            before, effect_observed=True, after_snapshot=after)

    move(branch, dead_end)
    move(dead_end, branch)
    backtrack = {"action_type": "unit_move", "actor_id": 1,
                 "target": {"x": dead_end[0], "y": dead_end[1]},
                 "is_valid": True}
    detour = {"action_type": "unit_move", "actor_id": 1,
              "target": {"x": alternative[0], "y": alternative[1]},
              "is_valid": True}
    cycle = _snapshot(
        [_unit(1, "Settlers", branch[0], branch[1])],
        [backtrack, detour, {"action_type": "end_turn", "is_valid": True}],
        source_seq=3)

    assert planner.founder_cycle_move_keys(cycle) == (
        json.dumps({key: value for key, value in backtrack.items()
                    if key != "is_valid"}, sort_keys=True, separators=(",", ":")),)
    decision = planner.plan(cycle)
    assert decision.candidate.action["target"] == {
        "x": alternative[0], "y": alternative[1]}
    assert not decision.candidate.projection["immediate_backtrack"]

    trapped = _snapshot(
        [_unit(1, "Settlers", branch[0], branch[1])],
        [backtrack, {"action_type": "end_turn", "is_valid": True}],
        source_seq=4)
    assert planner.founder_cycle_move_keys(trapped) == ()
    escape = planner.plan(trapped)
    assert escape.candidate.action["target"] == backtrack["target"]
    assert escape.candidate.projection["immediate_backtrack"]


def test_founder_route_breaks_four_tile_cycle_with_fresh_exit():
    ir = _ruleset_ir((("Settlers", "unit", 30),))
    planner = GroundedImpactPlanner(ruleset_ir=ir)
    route = ((1, 0), (2, 0), (2, 1), (1, 1))

    def record_move(source, target):
        action = {"action_type": "unit_move", "actor_id": 1,
                  "target": {"x": target[0], "y": target[1]}}
        before = _snapshot(
            [_unit(1, "Settlers", source[0], source[1])],
            [dict(action, is_valid=True),
             {"action_type": "end_turn", "is_valid": True}])
        after = _snapshot(
            [_unit(1, "Settlers", target[0], target[1])],
            [{"action_type": "end_turn", "is_valid": True}], source_seq=2)
        planner.record_outcome(
            ImpactCandidate(action, "expansion_move", 1.0, "route history"),
            before, effect_observed=True, after_snapshot=after)

    for source, target in zip(route, route[1:]):
        record_move(source, target)

    closing = {"action_type": "unit_move", "actor_id": 1,
               "target": {"x": route[0][0], "y": route[0][1]},
               "is_valid": True}
    fresh = {"action_type": "unit_move", "actor_id": 1,
             "target": {"x": 0, "y": 2}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(1, "Settlers", route[-1][0], route[-1][1])],
        [closing, fresh, {"action_type": "end_turn", "is_valid": True}],
        source_seq=4)

    assert planner.founder_cycle_move_keys(snapshot) == (
        json.dumps({key: value for key, value in closing.items()
                    if key != "is_valid"}, sort_keys=True, separators=(",", ":")),)
    decision = planner.plan(snapshot)
    assert decision.candidate.action["target"] == fresh["target"]
    assert not decision.candidate.projection["recent_route_revisit"]
    assert decision.candidate.projection["route_cycle_length"] == 0

    trapped = _snapshot(
        [_unit(1, "Settlers", route[-1][0], route[-1][1])],
        [closing, {"action_type": "end_turn", "is_valid": True}],
        source_seq=5)
    assert planner.founder_cycle_move_keys(trapped) == ()
    only_exit = planner.plan(trapped)
    assert only_exit.candidate.action["target"] == closing["target"]
    assert only_exit.candidate.projection["recent_route_revisit"]
    assert only_exit.candidate.projection["route_cycle_length"] == 4


def test_founder_route_avoids_observed_attrition_but_allows_only_exit():
    ir = _ruleset_ir((("Settlers", "unit", 30),))
    planner = GroundedImpactPlanner(ruleset_ir=ir)
    lost = _snapshot(
        [_unit(1, "Settlers", 2, 0)],
        [{"action_type": "end_turn", "is_valid": True}], turn=4)
    disappeared = _snapshot(
        [], [{"action_type": "end_turn", "is_valid": True}],
        source_seq=2, turn=5)

    planner.observe(lost)
    planner.observe(disappeared)

    hazardous = {"action_type": "unit_move", "actor_id": 2,
                 "target": {"x": 2, "y": 0}, "is_valid": True}
    safe = {"action_type": "unit_move", "actor_id": 2,
            "target": {"x": 1, "y": 1}, "is_valid": True}
    routed = _snapshot(
        [_unit(2, "Settlers", 1, 0)],
        [hazardous, safe, {"action_type": "end_turn", "is_valid": True}],
        source_seq=3, turn=6)

    assert planner.founder_attrition_move_keys(routed) == (
        json.dumps({key: value for key, value in hazardous.items()
                    if key != "is_valid"},
                   sort_keys=True, separators=(",", ":")),)
    decision = planner.plan(routed)
    assert decision.candidate.action["target"] == safe["target"]
    assert decision.candidate.projection[
        "founder_attrition_position_failures"] == 0

    trapped = _snapshot(
        [_unit(2, "Settlers", 1, 0)],
        [hazardous, {"action_type": "end_turn", "is_valid": True}],
        source_seq=4, turn=7)
    assert planner.founder_attrition_move_keys(trapped) == ()
    only_exit = planner.plan(trapped)
    assert only_exit.candidate.action["target"] == hazardous["target"]
    assert only_exit.candidate.projection[
        "founder_attrition_position_failures"] == 1


def test_successful_founding_is_not_learned_as_founder_attrition():
    ir = _ruleset_ir((("Settlers", "unit", 30),))
    planner = GroundedImpactPlanner(
        {"expansion_city_target": 3}, ruleset_ir=ir)
    before = _snapshot(
        [_unit(1, "Settlers", 3, 0)],
        [{"action_type": "end_turn", "is_valid": True}], turn=4)
    founded = _city()
    founded.update({"id": 12, "name": "Antium", "tile": 3,
                    "x": 3, "y": 0})
    after = _snapshot(
        [], [{"action_type": "end_turn", "is_valid": True}],
        cities=[_city(), founded], source_seq=2, turn=5)

    planner.observe(before)
    planner.observe(after)

    assert planner._founder_attrition_positions == {}


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

    ledger.defer(candidate, before, feedback_id="action-result-late")

    assert ledger.resolve(planner, unrelated) == ()
    assert len(ledger) == 1
    resolutions = ledger.resolve(planner, applied)
    assert len(resolutions) == 1
    assert resolutions[0].effect_observed
    assert resolutions[0].feedback_id == "action-result-late"
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
        [_unit(10, "Alpine Troops"), _unit(11, "Alpine Troops"),
         _unit(20, "Explorer"),
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
                   {"horizon_turn": 0}, {"horizon_turn": 2001},
                   {"preferred_government": 3},
                   {"preferred_government": "x" * 65},
                   {"government_minimum_remaining_turns": True},
                   {"government_minimum_remaining_turns": -1},
                   {"government_minimum_remaining_turns": 1.5},
                   {"government_minimum_remaining_turns": 101},
                   {"government_minimum_city_count": True},
                   {"government_minimum_city_count": -1},
                   {"government_minimum_city_count": 1.5},
                   {"government_minimum_city_count": 21},
                   {"founder_attrition_rebuild_limit": True},
                   {"founder_attrition_rebuild_limit": -1},
                   {"founder_attrition_rebuild_limit": 1.5},
                   {"founder_attrition_rebuild_limit": 21},
                   {"founder_attrition_memory_turns": True},
                   {"founder_attrition_memory_turns": 0},
                   {"founder_attrition_memory_turns": 1.5},
                   {"founder_attrition_memory_turns": 201},
                   {"coinage_bridge_max_turns": True},
                   {"coinage_bridge_max_turns": 0},
                   {"coinage_bridge_max_turns": 1.5},
                   {"coinage_bridge_max_turns": 201},
                   {"disorder_luxury_recovery_enabled": 1},
                   {"disorder_luxury_trigger_turns": True},
                   {"disorder_luxury_trigger_turns": 0},
                   {"disorder_luxury_trigger_turns": 1.5},
                   {"disorder_luxury_trigger_turns": 21},
                   {"disorder_luxury_minimum_city_size": True},
                   {"disorder_luxury_minimum_city_size": 0},
                   {"disorder_luxury_minimum_city_size": 1.5},
                   {"disorder_luxury_minimum_city_size": 31},
                   {"disorder_luxury_bridge_max_turns": True},
                   {"disorder_luxury_bridge_max_turns": 0},
                   {"disorder_luxury_bridge_max_turns": 1.5},
                   {"disorder_luxury_bridge_max_turns": 101},
                   {"city_happiness_governor_enabled": 1},
                   {"production_minimum_remaining_turns": 0},
                   {"expansion_minimum_settlement_runway_turns": True},
                   {"expansion_minimum_settlement_runway_turns": -1},
                   {"expansion_minimum_settlement_runway_turns": 1.5},
                   {"expansion_minimum_settlement_runway_turns": 101},
                   {"expansion_settlement_deadline_recovery_enabled": 1},
                   {"expansion_packet_site_preference_enabled": 1},
                   {"expansion_escort_retention_enabled": 1},
                   {"expansion_escort_threat_gating_enabled": 1},
                   {"expansion_escort_route_threat_memory_enabled": 1},
                   {"expansion_final_settlement_escort_enabled": 1},
                   {"foodbox_percent": 0},
                   {"unit_build_score_divisor": 0},
                   {"production_minimum_remaining_turns": 9,
                    "expansion_minimum_remaining_turns": 8},
                   {"refresh_timeout_seconds": 0.1},
                   {"refresh_timeout_seconds": 11},
                   {"terminal_refresh_timeout_seconds": 0.1},
                   {"terminal_refresh_timeout_seconds": 11},
                   {"refresh_timeout_seconds": 2.0,
                    "terminal_refresh_timeout_seconds": 1.0},
                   {"refresh_stability_interval_seconds": 0.01},
                   {"refresh_stability_interval_seconds": 0.51},
                   {"no_effect_retry_limit": 0}, {"no_effect_retry_limit": 9},
                   {"max_no_effect_failovers_per_scope": -1},
                   {"max_no_effect_failovers_per_scope": 9},
                   {"production_strategy": "unknown"},
                   {"pressure_enabled": "yes"},
                   {"pressure_learning_enabled": "yes"},
                   {"pressure_learning_enabled": True},
                   {"pressure_score_alignment_enabled": "yes"},
                   {"pressure_exploration_information_enabled": "yes"},
                   {"pressure_score_alignment_utility_tolerance": True},
                   {"pressure_score_alignment_utility_tolerance": -0.01},
                   {"pressure_score_alignment_utility_tolerance": 0.26},
                   {"pressure_damping": 1.0},
                   {"pressure_exploration_floor": 1.1},
                   {"pressure_temperature": 0.0},
                   {"pressure_max_routes_per_conclusion": 0},
                   {"pressure_enabled": True,
                    "pressure_learning_rate": 0.0},
                   {"pressure_enabled": True,
                    "pressure_no_progress_rate": -0.1},
                   {"pressure_enabled": True,
                    "pressure_initial_conductance": 1.1}):
        try:
            GroundedImpactPlanner(config)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid impact-policy budget was accepted")

    assert GroundedImpactPlanner({"horizon_turn": 2000}).horizon_turn == 2000


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


def test_pressure_feedback_replays_idempotently_through_impact_planner():
    fortify = {"action_type": "unit_fortify", "actor_id": 11, "is_valid": True}
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [fortify, {"action_type": "end_turn", "is_valid": True}])
    config = {
        "pressure_enabled": True,
        "pressure_learning_enabled": True,
    }
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "pressure-conductance.json")
        planner = GroundedImpactPlanner(
            config, pressure_state_path=path,
            pressure_state_identity="impact-attempt")
        decision = planner.plan(snapshot)
        update = planner.record_outcome(
            decision.candidate, snapshot, False, snapshot,
            feedback_id="action-result-1")
        assert update.applied
        assert update.no_progress == 1

        replay = GroundedImpactPlanner(
            config, pressure_state_path=path,
            pressure_state_identity="impact-attempt")
        duplicate = replay.record_outcome(
            decision.candidate, snapshot, False, snapshot,
            feedback_id="action-result-1")
        assert not duplicate.applied
        assert duplicate.conductance == update.conductance


def test_plan_diagnostics_attribute_candidate_pressure_and_materialization():
    fortify = {"action_type": "unit_fortify", "actor_id": 11, "is_valid": True}
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [fortify, {"action_type": "end_turn", "is_valid": True}])
    planner = GroundedImpactPlanner({"pressure_enabled": True})
    diagnostics = {}

    decision = planner.plan(snapshot, diagnostics=diagnostics)

    assert decision.candidate.category == "city_defense"
    assert diagnostics["calls"] == 1
    assert diagnostics["candidate_count"] == 1
    assert diagnostics["legal_action_count"] == 2
    assert diagnostics["pressure_calls"] == 1
    assert diagnostics["candidate_latency_ms"] >= 0.0
    assert diagnostics["catalog_latency_ms"] >= 0.0
    assert diagnostics["candidate_setup_latency_ms"] >= 0.0
    assert diagnostics["candidate_other_latency_ms"] >= 0.0
    assert diagnostics["candidate_finalize_latency_ms"] >= 0.0
    assert diagnostics["pressure_latency_ms"] >= 0.0
    assert diagnostics["pressure_graph_latency_ms"] >= 0.0
    assert diagnostics["pressure_propagation_latency_ms"] >= 0.0
    assert diagnostics["pressure_operation_latency_ms"] >= 0.0
    assert diagnostics["pressure_schedule_latency_ms"] >= 0.0
    assert diagnostics["pressure_artifact_latency_ms"] >= 0.0
    assert diagnostics["materialization_latency_ms"] >= 0.0


def test_plan_retains_pressure_when_active_goals_have_no_candidates():
    snapshot = _snapshot(
        [], [{"action_type": "end_turn", "is_valid": True}],
        research={
            "beakers_per_turn": -1,
            "gross_beakers_per_turn": 0,
            "tech_upkeep": 1,
        })
    planner = GroundedImpactPlanner({
        "pressure_enabled": True,
        "expansion_city_target": 2,
    })
    diagnostics = {}

    assert planner.plan(snapshot, diagnostics=diagnostics) is None

    artifact = planner.last_stranded_pressure_artifact
    assert artifact is not None
    assert artifact["schedule"]["selected_operation_id"] is None
    assert artifact["pressure"]["traces"] == []
    assert artifact["pressure"]["dependency"]["pf-impact:expansion"][
        "pf-impact-goal:expansion"] > 0.0
    assert diagnostics["stranded_pressure_calls"] == 1
    assert diagnostics["stranded_goal_count"] >= 2


def test_legal_actions_are_decoded_once_per_immutable_snapshot():
    move = {"action_type": "unit_move", "actor_id": 20,
            "target": {"x": 0, "y": 2}, "is_valid": True}
    snapshot = _snapshot(
        [_unit(20, "Explorer")],
        [move, {"action_type": "end_turn", "is_valid": True}])
    planner = GroundedImpactPlanner()

    first = planner._actions(snapshot)
    second = planner._actions(snapshot)
    refreshed = _snapshot(
        [_unit(20, "Explorer")],
        [move, {"action_type": "end_turn", "is_valid": True}], source_seq=2)
    third = planner._actions(refreshed)

    assert second is first
    assert third is not first
    assert third == first


def test_downstream_city_progress_credits_one_pending_expansion_route():
    move_action = {
        "action_type": "unit_move", "actor_id": 1,
        "target": {"x": 4, "y": 5}, "is_valid": True,
    }
    found_action = {
        "action_type": "unit_build_city", "actor_id": 1,
        "target": {"x": 4, "y": 5}, "is_valid": True,
    }
    before_move = _snapshot(
        [_unit(1, "Settlers", x=4, y=4)],
        [move_action, {"action_type": "end_turn", "is_valid": True}],
        source_seq=1)
    after_move = _snapshot(
        [_unit(1, "Settlers", x=4, y=5)],
        [found_action, {"action_type": "end_turn", "is_valid": True}],
        source_seq=2)
    second_city = dict(_city(), id=20, name="Antium", tile=54, x=4, y=5)
    after_founding = _snapshot(
        [], [{"action_type": "end_turn", "is_valid": True}],
        cities=[_city(), second_city], source_seq=3)
    planner = GroundedImpactPlanner({
        "expansion_city_target": 3,
        "pressure_enabled": True,
        "pressure_learning_enabled": True,
    })
    move = ImpactCandidate(
        move_action, "expansion_move", 800.0, "grounded expansion step")
    moved = planner.record_outcome(
        move, before_move, True, after_move, feedback_id="move-result")
    assert moved.credit_kind == "effect_without_goal_relief"
    assert moved.realized_relief == 0.0
    assert moved.conductance < moved.previous_conductance
    assert planner.drain_conductance_updates() == ()

    founding = ImpactCandidate(
        found_action, "city_founding", 1000.0, "grounded city completion")
    assert planner.candidate_effect_observed(
        founding, after_move, after_founding)
    relief = planner.candidate_goal_relief(
        founding, after_move, after_founding, True)
    assert relief.goal == "expansion"
    assert abs(relief.realized_relief - 1.0 / 3.0) < 1e-12
    direct = planner.record_outcome(
        founding, after_move, True, after_founding,
        feedback_id="found-result")
    downstream = planner.drain_conductance_updates()
    assert direct.credit_kind == "direct_goal_relief"
    assert len(downstream) == 1
    assert downstream[0].category == "expansion_move"
    assert downstream[0].credit_kind == "downstream_goal_relief"
    assert downstream[0].caused_by_feedback_id == "found-result"
    assert downstream[0].successes == moved.successes
    assert downstream[0].conductance > moved.conductance
    # Draining is idempotent and a goal event cannot multiply route credit.
    assert planner.drain_conductance_updates() == ()


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


def test_player_rate_effect_and_retry_grounding_use_exact_economy_rates():
    action = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 50, "science_rate": 50, "luxury_rate": 0,
        },
        "is_valid": True,
    }
    candidate = ImpactCandidate(
        action, "treasury_tax_restore", 760.0,
        "exact player-rate effect regression")
    before = _snapshot(
        [], [action, {"action_type": "end_turn", "is_valid": True}],
        player={"tax": 60, "science": 40, "luxury": 0})
    unchanged = _snapshot(
        [], [action, {"action_type": "end_turn", "is_valid": True}],
        source_seq=2,
        player={"tax": 60, "science": 40, "luxury": 0})
    applied = _snapshot(
        [], [{"action_type": "end_turn", "is_valid": True}],
        source_seq=3,
        player={"tax": 50, "science": 50, "luxury": 0})
    planner = GroundedImpactPlanner({"no_effect_retry_limit": 1})

    assert not planner.candidate_effect_observed(
        candidate, before, unchanged)
    assert planner.candidate_effect_observed(candidate, before, applied)
    assert planner._grounding_signature(
        before, candidate) != planner._grounding_signature(
            applied, candidate)

    planner.record_outcome(candidate, before, effect_observed=False)
    assert planner._no_effect_suppressed(before, candidate)
    assert not planner._no_effect_suppressed(applied, candidate)


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


def test_finished_revolution_is_recovered_before_ordinary_planning():
    actions = [
        {
            "action_type": "government_change", "actor_id": 0,
            "target": {"government_id": 2, "government_name": "Monarchy"},
            "is_valid": True,
        },
        {
            "action_type": "government_change", "actor_id": 0,
            "target": {"government_id": 1, "government_name": "Despotism"},
            "is_valid": True,
        },
        {"action_type": "end_turn", "is_valid": True},
    ]
    government = {
        "available": True, "current_id": 0, "current_name": "Anarchy",
        "target_id": 0, "target_name": "Anarchy",
        "revolution_finishes": 4, "in_revolution": True,
        "selection_required": True, "diagnostic": None,
    }
    snapshot = _snapshot([], actions, government=government)

    decision = GroundedImpactPlanner().plan(snapshot)

    assert decision.candidate.category == "government_recovery"
    assert decision.candidate.action["target"] == {
        "government_id": 1, "government_name": "Despotism"}
    assert decision.candidate.utility > 2000
    assert decision.candidate.terminal_on_accept
    budget = ImpactTurnBudget(max_no_effect_failovers=4)
    budget.record(decision.candidate, effect_observed=False)
    assert decision.candidate.scope in budget.excluded_scopes


def test_finished_revolution_selects_intended_preferred_government():
    actions = [
        {
            "action_type": "government_change", "actor_id": 0,
            "target": {"government_id": 2, "government_name": "Monarchy"},
            "is_valid": True,
        },
        {
            "action_type": "government_change", "actor_id": 0,
            "target": {"government_id": 1, "government_name": "Despotism"},
            "is_valid": True,
        },
        _production(10, "Alpine Troops", 6, 11),
        {"action_type": "end_turn", "is_valid": True},
    ]
    government = {
        "available": True, "current_id": 0, "current_name": "Anarchy",
        "target_id": 2, "target_name": "Monarchy",
        "revolution_finishes": 4, "in_revolution": True,
        "selection_required": True, "diagnostic": None,
    }
    snapshot = _snapshot([], actions, government=government)
    planner = GroundedImpactPlanner(
        {"preferred_government": "Monarchy", "pressure_enabled": True},
        ruleset_ir=_ruleset_ir((("Alpine Troops", "unit", 20),)))

    decision = planner.plan(snapshot)

    assert decision.candidate.category == "government_recovery"
    assert decision.candidate.action["target"] == {
        "government_id": 2, "government_name": "Monarchy"}
    governance = next(
        row for row in decision.pressure_artifact["pressure"]["goals"]
        if row["goal_id"] == "pf-impact:governance")
    assert governance["safety"] is True


def test_stable_government_transitions_to_configured_legal_target():
    actions = [
        {
            "action_type": "government_change", "actor_id": 0,
            "target": {"government_id": 2, "government_name": "Monarchy"},
            "is_valid": True,
        },
        {
            "action_type": "government_change", "actor_id": 0,
            "target": {"government_id": 3, "government_name": "Republic"},
            "is_valid": True,
        },
        {"action_type": "end_turn", "is_valid": True},
    ]
    government = {
        "available": True, "current_id": 1, "current_name": "Despotism",
        "target_id": 1, "target_name": "Despotism",
        "revolution_finishes": -1, "in_revolution": False,
        "selection_required": False, "diagnostic": None,
    }
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")], actions, government=government)
    planner = GroundedImpactPlanner({
        "preferred_government": "Monarchy",
        "government_minimum_remaining_turns": 12,
        "horizon_turn": 30,
        "pressure_enabled": True,
    })

    decision = planner.plan(snapshot)

    assert decision.candidate.category == "government_transition"
    assert decision.candidate.action["target"] == {
        "government_id": 2, "government_name": "Monarchy"}
    assert decision.candidate.projection["remaining_turns"] == 26


def test_stable_government_waits_for_configured_city_base():
    action = {
        "action_type": "government_change", "actor_id": 0,
        "target": {"government_id": 2, "government_name": "Monarchy"},
        "is_valid": True,
    }
    government = {
        "available": True, "current_id": 1, "current_name": "Despotism",
        "target_id": 1, "target_name": "Despotism",
        "revolution_finishes": -1, "in_revolution": False,
        "selection_required": False, "diagnostic": None,
    }
    actions = [action, {"action_type": "end_turn", "is_valid": True}]
    planner = GroundedImpactPlanner({
        "preferred_government": "Monarchy",
        "government_minimum_city_count": 2,
    })
    one_city = _snapshot(
        [_unit(11, "Alpine Troops")], actions, government=government)
    second = dict(_city(), id=20, name="Antium", tile=2, x=2, y=0)
    two_cities = _snapshot(
        [_unit(11, "Alpine Troops")], actions,
        cities=[_city(), second], government=government, source_seq=2)

    assert planner.plan(one_city) is None
    decision = planner.plan(two_cities)
    assert decision.candidate.category == "government_transition"
    assert decision.candidate.projection["observed_city_count"] == 2
    assert decision.candidate.projection["government_minimum_city_count"] == 2


def test_government_transition_is_disabled_without_policy_or_runway():
    action = {
        "action_type": "government_change", "actor_id": 0,
        "target": {"government_id": 2, "government_name": "Monarchy"},
        "is_valid": True,
    }
    government = {
        "available": True, "current_id": 1, "current_name": "Despotism",
        "target_id": 1, "target_name": "Despotism",
        "revolution_finishes": -1, "in_revolution": False,
        "selection_required": False, "diagnostic": None,
    }
    actions = [action, {"action_type": "end_turn", "is_valid": True}]
    no_policy = _snapshot(
        [_unit(11, "Alpine Troops")], actions, government=government)
    no_runway = _snapshot(
        [_unit(11, "Alpine Troops")], actions, government=government,
        turn=25, source_seq=2)

    assert GroundedImpactPlanner().plan(no_policy) is None
    assert GroundedImpactPlanner({
        "preferred_government": "Monarchy",
        "government_minimum_remaining_turns": 6,
        "horizon_turn": 30,
    }).plan(no_runway) is None


def test_government_economic_gate_prices_downtime_and_declared_payback():
    action = {
        "action_type": "government_change", "actor_id": 0,
        "target": {"government_id": 2, "government_name": "Monarchy"},
        "is_valid": True,
    }
    government = {
        "available": True, "current_id": 1, "current_name": "Despotism",
        "target_id": 1, "target_name": "Despotism",
        "revolution_finishes": -1, "in_revolution": False,
        "selection_required": False, "diagnostic": None,
    }
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [action, {"action_type": "end_turn", "is_valid": True}],
        government=government,
        player={
            "gold": 200, "gold_per_turn": 5,
            "operating_gold_per_turn": 5,
            "capitalization_gold_per_turn": 0,
        },
        research={
            "gross_beakers_per_turn": 5,
            "tech_upkeep": 0,
        })
    values = {
        "preferred_government": "Monarchy",
        "government_economic_gate_enabled": True,
        "government_transition_cost_turns": 2,
        "government_maximum_payback_turns": 20,
        "government_expected_operating_gold_gain": 3,
        "government_minimum_remaining_turns": 12,
        "horizon_turn": 30,
    }

    decision = GroundedImpactPlanner(values).plan(snapshot)

    assert decision.candidate.category == "government_transition"
    projection = decision.candidate.projection
    assert projection["productive_output_per_turn_before"] == 14
    assert projection["transition_downtime_cost"] == 28
    assert projection["declared_benefit_over_payback"] == 60
    assert projection["declared_net_value"] == 32
    assert projection["treasury_after_transition"] == 200
    assert projection["economic_gate_evidence"] == (
        "authoritative-current-output-plus-declared-target-delta")

    uneconomic = dict(
        values, government_expected_operating_gold_gain=1)
    assert GroundedImpactPlanner(uneconomic).plan(snapshot) is None


def test_government_economic_gate_rejects_unsafe_transition_runway():
    action = {
        "action_type": "government_change", "actor_id": 0,
        "target": {"government_id": 2, "government_name": "Monarchy"},
        "is_valid": True,
    }
    government = {
        "available": True, "current_id": 1, "current_name": "Despotism",
        "target_id": 1, "target_name": "Despotism",
        "revolution_finishes": -1, "in_revolution": False,
        "selection_required": False, "diagnostic": None,
    }
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [action, {"action_type": "end_turn", "is_valid": True}],
        government=government,
        player={
            "gold": 12, "gold_per_turn": -4,
            "operating_gold_per_turn": -4,
            "capitalization_gold_per_turn": 0,
        },
        research={
            "gross_beakers_per_turn": 0,
            "tech_upkeep": 0,
        })
    values = {
        "preferred_government": "Monarchy",
        "government_economic_gate_enabled": True,
        "government_transition_cost_turns": 3,
        "government_maximum_payback_turns": 20,
        "government_expected_operating_gold_gain": 20,
        "horizon_turn": 30,
    }

    assert GroundedImpactPlanner(values).plan(snapshot) is None


def test_disorder_risk_prioritizes_city_local_martial_law_garrison():
    city = _city(production_kind=3, production_value=14)
    city.update({
        "ppl_happy": [0], "ppl_content": [0],
        "ppl_unhappy": [2], "ppl_angry": [0],
        "disorder": True,
    })
    action = _production(10, "Alpine Troops", 6, 11)
    ruleset = _ruleset_ir((
        ("Settlers", "unit", 30),
        ("Alpine Troops", "unit", 20),
    ))
    snapshot = _snapshot(
        [], [action, {"action_type": "end_turn", "is_valid": True}],
        cities=[city])

    decision = GroundedImpactPlanner(ruleset_ir=ruleset).plan(snapshot)

    assert decision.candidate.category == "production_defense"
    assert decision.candidate.projection["required_garrison"] == 2
    assert "martial-law" in decision.candidate.rationale


def test_stable_martial_law_city_releases_only_packet_proven_spare_attacker():
    city = _city(
        size=6,
        production_kind=6,
        production_value=0)
    city.update({
        "ppl_happy": [0, 0, 0, 0, 0, 0],
        "ppl_content": [4, 4, 4, 4, 6, 6],
        "ppl_unhappy": [2, 2, 2, 2, 0, 0],
        "ppl_angry": [0, 0, 0, 0, 0, 0],
        "disorder": False,
    })
    attack = {
        "action_type": "unit_attack",
        "actor_id": 11,
        "target": {"x": 1, "y": 0},
        "is_valid": True,
    }
    units = [
        _unit(11, "Alpine Troops"),
        _unit(12, "Riflemen"),
        _unit(13, "Riflemen"),
        _enemy(99, "Riflemen", 1, 0),
    ]
    planner = GroundedImpactPlanner()
    snapshot = _snapshot(
        units,
        [attack, {
            "action_type": "end_turn",
            "is_valid": True,
        }],
        cities=[city])

    assert planner._city_martial_law_relief(
        snapshot.cities[0]) == 2
    assert planner._required_garrison_count(
        snapshot.cities[0]) == 2
    assert [
        row.category
        for row in planner.candidates(
            snapshot)
    ] == ["tactical_attack"]

    no_spare = _snapshot(
        units[:2] + units[3:],
        [attack, {
            "action_type": "end_turn",
            "is_valid": True,
        }],
        cities=[city],
        source_seq=2)
    assert planner.candidates(
        no_spare) == ()


def test_food_support_unit_is_not_queued_by_a_zero_food_surplus_city():
    city = _city(surplus=(0, 5, 2, 1, 0, 3))
    action = _production(10, "Alpine Troops", 6, 11)
    ruleset = _ruleset_ir((
        ("Alpine Troops", "unit", 20),
    ), founders=(), workers=(), upkeeps={
        "Alpine Troops": {"uk_food": 1},
    })
    snapshot = _snapshot(
        [], [action, {"action_type": "end_turn", "is_valid": True}],
        cities=[city])

    assert GroundedImpactPlanner(
        {"expansion_city_target": 1}, ruleset_ir=ruleset
    ).plan(snapshot) is None


def test_non_city_unit_concentration_is_not_created_by_plain_movement():
    move = {
        "action_type": "unit_move", "actor_id": 20,
        "target": {"x": 1, "y": 0}, "is_valid": True,
    }
    snapshot = _snapshot(
        [_unit(20, "Diplomat"), _unit(21, "Warriors", 1, 0)],
        [move, {"action_type": "end_turn", "is_valid": True}])

    assert GroundedImpactPlanner().plan(snapshot) is None


def test_killstack_heuristic_does_not_change_packet_grounded_founder_route():
    move = {
        "action_type": "unit_move", "actor_id": 20,
        "target": {"x": 1, "y": 0}, "is_valid": True,
    }
    ruleset = _ruleset_ir((("Settlers", "unit", 30),))
    snapshot = _snapshot(
        [_unit(20, "Settlers"), _unit(21, "Warriors", 1, 0)],
        [move, {"action_type": "end_turn", "is_valid": True}])

    decision = GroundedImpactPlanner(
        {"expansion_city_target": 2}, ruleset_ir=ruleset).plan(snapshot)

    assert decision.candidate.category == "expansion_move"
    assert decision.candidate.action == {
        "action_type": "unit_move", "actor_id": 20,
        "target": {"x": 1, "y": 0},
    }


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


def test_failed_settlement_site_is_suppressed_across_founders_until_layout_changes():
    action = {"action_type": "unit_build_city", "actor_id": 1}
    candidate = ImpactCandidate(
        action, "city_founding", 1.0, "failed settlement site")
    before = _snapshot(
        [_unit(1, "Settlers", 3, 0)],
        [dict(action, is_valid=True),
         {"action_type": "end_turn", "is_valid": True}])
    unchanged = _snapshot(
        [_unit(1, "Settlers", 3, 0)],
        [{"action_type": "end_turn", "is_valid": True}], source_seq=2)
    planner = GroundedImpactPlanner()

    planner.record_outcome(
        candidate, before, effect_observed=False, after_snapshot=unchanged)

    repeated = {"action_type": "unit_build_city", "actor_id": 2,
                "is_valid": True}
    move = {"action_type": "unit_move", "actor_id": 2,
            "target": {"x": 4, "y": 0}, "is_valid": True}
    same_layout = _snapshot(
        [_unit(2, "Settlers", 3, 0)],
        [repeated, move, {"action_type": "end_turn", "is_valid": True}],
        source_seq=3)
    assert planner.failed_settlement_site_action_keys(same_layout) == (
        json.dumps({key: value for key, value in repeated.items()
                    if key != "is_valid"},
                   sort_keys=True, separators=(",", ":")),)
    assert planner.plan(same_layout).candidate.action["action_type"] == "unit_move"
    assert planner.failed_settlement_sites_pruned == 1

    added = _city()
    added.update({"id": 12, "name": "Antium", "tile": 55,
                  "x": 5, "y": 5})
    changed_layout = _snapshot(
        [_unit(2, "Settlers", 3, 0)],
        [repeated, move, {"action_type": "end_turn", "is_valid": True}],
        cities=[_city(), added], source_seq=4)
    assert planner.failed_settlement_site_action_keys(changed_layout) == ()
    assert planner.plan(changed_layout).candidate.category == "city_founding"

    successful = GroundedImpactPlanner()
    successful.record_outcome(
        candidate, before, effect_observed=True, after_snapshot=changed_layout)
    assert successful._failed_settlement_sites == set()


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


def test_existing_founder_honors_post_settlement_runway_deadline():
    ir = _ruleset_ir(
        (("Settlers", "unit", 30),), pop_costs={"Settlers": 2})
    values = {
        "horizon_turn": 60,
        "expansion_city_target": 4,
        "expansion_minimum_settlement_runway_turns": 15,
    }
    build = {
        "action_type": "unit_build_city", "actor_id": 1,
        "is_valid": True,
    }
    end_turn = {"action_type": "end_turn", "is_valid": True}

    # Immediate settlement is valid at the exact boundary.
    boundary = GroundedImpactPlanner(values, ruleset_ir=ir).plan(_snapshot(
        [_unit(1, "Settlers", 3, 0)], [build, end_turn], turn=45))
    assert boundary.candidate.category == "city_founding"
    assert boundary.candidate.projection == {
        "settlement_runway_remaining_turns": 15,
        "settlement_runway_required_turns": 15,
    }

    # The same site is no longer score-bearing one turn later.
    assert GroundedImpactPlanner(values, ruleset_ir=ir).plan(_snapshot(
        [_unit(1, "Settlers", 3, 0)], [build, end_turn], turn=46)) is None

    cities = [_city()]
    second = _city()
    second.update({"id": 12, "name": "Antium", "tile": 3, "x": 3})
    cities.append(second)
    toward_city = {
        "action_type": "unit_move", "actor_id": 1,
        "target": {"x": 4, "y": 0}, "is_valid": True,
    }
    toward_frontier = {
        "action_type": "unit_move", "actor_id": 1,
        "target": {"x": 6, "y": 0}, "is_valid": True,
    }
    move_actions = [toward_city, toward_frontier, end_turn]

    # One turn before the deadline an outward move can still preserve the
    # configured runway. At the deadline the same founder must route home.
    expanding = GroundedImpactPlanner(values, ruleset_ir=ir).plan(_snapshot(
        [_unit(1, "Settlers", 5, 0)], move_actions,
        cities=cities, turn=44))
    assert expanding.candidate.category == "expansion_move"
    assert expanding.candidate.action["target"] == {"x": 6, "y": 0}

    recovering = GroundedImpactPlanner(values, ruleset_ir=ir).plan(_snapshot(
        [_unit(1, "Settlers", 5, 0)], move_actions,
        cities=cities, turn=45))
    assert recovering.candidate.category == "population_recovery_move"
    assert recovering.candidate.action["target"] == {"x": 4, "y": 0}
    assert recovering.candidate.projection[
        "population_recovery_reason"] == "settlement_runway_exhausted"
    assert recovering.candidate.projection[
        "settlement_runway_remaining_turns"] == 15
    assert recovering.candidate.projection[
        "settlement_runway_required_turns"] == 15

    no_recovery_ir = _ruleset_ir(
        (("Settlers", "unit", 30),), add_to_city=(),
        pop_costs={"Settlers": 2})
    assert GroundedImpactPlanner(
        values, ruleset_ir=no_recovery_ir).plan(_snapshot(
            [_unit(1, "Settlers", 5, 0)], move_actions,
            cities=cities, turn=45)) is None

    join = {
        "action_type": "unit_join_city", "actor_id": 1,
        "target": {"city": "Rome", "city_id": 10}, "is_valid": True,
    }
    recovered = GroundedImpactPlanner(values, ruleset_ir=ir).plan(_snapshot(
        [_unit(1, "Settlers")], [join, end_turn],
        cities=cities, turn=46))
    assert recovered.candidate.category == "population_recovery"
    assert recovered.candidate.projection[
        "population_recovery_reason"] == "settlement_runway_exhausted"

    ablation_values = dict(
        values, expansion_settlement_deadline_recovery_enabled=False)
    ablation_build = GroundedImpactPlanner(
        ablation_values, ruleset_ir=ir).plan(_snapshot(
            [_unit(1, "Settlers", 3, 0)], [build, end_turn], turn=46))
    assert ablation_build.candidate.category == "city_founding"
    ablation_move = GroundedImpactPlanner(
        ablation_values, ruleset_ir=ir).plan(_snapshot(
            [_unit(1, "Settlers", 5, 0)], move_actions,
            cities=cities, turn=45))
    assert ablation_move.candidate.category == "expansion_move"
    assert ablation_move.candidate.action["target"] == {"x": 6, "y": 0}

    # The default zero runway retains historical expansion behavior.
    compatible = GroundedImpactPlanner(
        dict(values, expansion_minimum_settlement_runway_turns=0),
        ruleset_ir=ir).plan(_snapshot(
            [_unit(1, "Settlers", 5, 0)], move_actions,
            cities=cities, turn=59))
    assert compatible.candidate.category == "expansion_move"
    assert compatible.candidate.action["target"] == {"x": 6, "y": 0}


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


def test_founder_production_requires_declared_post_settlement_runway():
    founder = _production(10, "Settlers", 6, 0)
    actions = [founder, {"action_type": "end_turn", "is_valid": True}]
    city = _city(
        size=3, food_stock=0, shield_stock=0,
        surplus=(3, 5, 4, 3, 0, 2),
        production_kind=6, production_value=11)
    ir = _ruleset_ir((
        ("Settlers", "unit", 30),
        ("Alpine Troops", "unit", 60),
    ), pop_costs={"Settlers": 2})
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")], actions, cities=[city], turn=36)
    values = {
        "horizon_turn": 60,
        "expansion_city_target": 2,
        "expansion_minimum_remaining_turns": 12,
        "expansion_minimum_settlement_runway_turns": 15,
    }

    decision = GroundedImpactPlanner(values, ruleset_ir=ir).plan(snapshot)
    assert decision.candidate.category == "production_expansion"
    assert decision.candidate.projection["settlement_runway_turns"] == 15

    too_short = _snapshot(
        [_unit(11, "Alpine Troops")], actions, cities=[city], turn=37)
    assert GroundedImpactPlanner(values, ruleset_ir=ir).plan(too_short) is None


def test_preexpansion_sequence_requires_declared_post_settlement_runway():
    actions = [
        _production(10, "Settlers", 6, 0),
        _production(10, "Granary", 3, 14),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ir = _ruleset_ir((
        ("Settlers", "unit", 30), ("Granary", "improvement", 40),
    ), pop_costs={"Settlers": 2})
    city = _city(
        size=1, food_stock=0, shield_stock=0,
        surplus=(2, 3, 4, 3, 0, 2))
    snapshot = _snapshot(
        [_unit(1, "Settlers")], actions, cities=[city], turn=1)

    decision = GroundedImpactPlanner({
        "horizon_turn": 60,
        "expansion_city_target": 3,
        "expansion_minimum_settlement_runway_turns": 18,
    }, ruleset_ir=ir).plan(snapshot)

    assert decision.candidate.category == "production_expansion"
    assert decision.candidate.action["target"]["production_type"] == "Settlers"


def test_horizon_policy_sequences_granary_before_last_slow_growth_founder():
    actions = [
        _production(10, "Settlers", 6, 0),
        _production(10, "Granary", 3, 14),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ir = _ruleset_ir((
        ("Settlers", "unit", 30), ("Granary", "improvement", 40),
    ), pop_costs={"Settlers": 2})
    city = _city(
        size=1, food_stock=0, shield_stock=0,
        surplus=(2, 3, 4, 3, 0, 2))
    snapshot = _snapshot(
        [_unit(1, "Settlers")], actions, cities=[city], turn=1)

    planner = GroundedImpactPlanner({
        "horizon_turn": 60, "expansion_city_target": 3,
        "production_minimum_remaining_turns": 8,
        "expansion_minimum_remaining_turns": 12,
    }, ruleset_ir=ir)
    decision = planner.plan(snapshot)

    assert decision.candidate.category == "production_preexpansion_growth"
    assert decision.candidate.action["target"]["production_type"] == "Granary"
    assert decision.candidate.projection[
        "preexpansion_founder"] == "Settlers"
    assert decision.candidate.projection[
        "preexpansion_founder_completion_eta_turns"] == 25
    assert decision.candidate.projection[
        "preexpansion_founder_population_ready_eta_turns"] == 25
    assert decision.candidate.projection[
        "preexpansion_direct_founder_population_ready_eta_turns"] == 25
    assert decision.candidate.projection[
        "preexpansion_direct_founder_shield_completion_eta_turns"] == 10
    assert decision.candidate.projection[
        "preexpansion_sequence_settlement_eta_turns"] == 42
    assert decision.candidate.projection[
        "preexpansion_sequence_settlement_runway_turns"] == 17
    assert decision.candidate.projection[
        "preexpansion_shield_stock_assumption"] == 0

    granary_installed = _snapshot(
        [_unit(1, "Settlers")], actions,
        cities=[_city(
            size=1, food_stock=0, shield_stock=0,
            surplus=(2, 3, 4, 3, 0, 2),
            production_kind=3, production_value=14)],
        turn=2, source_seq=2)
    planner.record_outcome(
        decision.candidate, snapshot, effect_observed=True,
        after_snapshot=granary_installed)

    followup_actions = [
        _production(10, "Settlers", 6, 0),
        {"action_type": "end_turn", "is_valid": True},
    ]
    completed = _snapshot(
        [_unit(1, "Settlers")], followup_actions,
        cities=[_city(
            size=3, food_stock=0, shield_stock=3,
            surplus=(2, 3, 4, 3, 0, 2),
            production_kind=3, production_value=17)],
        turn=18, source_seq=3)
    followup = planner.plan(completed)
    assert followup.candidate.category == "production_preexpansion_founder"
    assert followup.candidate.action["target"]["production_type"] == "Settlers"
    assert followup.candidate.projection["preexpansion_followup"]
    assert followup.candidate.projection[
        "preexpansion_followup_discarded_shield_stock"] == 3
    assert followup.candidate.projection[
        "preexpansion_followup_discard_limit"] == 3

    missed_boundary = _snapshot(
        [_unit(1, "Settlers")], followup_actions,
        cities=[_city(
            size=3, food_stock=0, shield_stock=4,
            surplus=(2, 3, 4, 3, 0, 2),
            production_kind=3, production_value=17)],
        turn=19, source_seq=4)
    assert planner.plan(missed_boundary) is None

    zero_pop_ir = _ruleset_ir((
        ("Settlers", "unit", 30), ("Granary", "improvement", 40),
    ), pop_costs={"Settlers": 0})
    assert GroundedImpactPlanner({
        "horizon_turn": 60, "expansion_city_target": 3,
        "production_minimum_remaining_turns": 8,
        "expansion_minimum_remaining_turns": 12,
    }, ruleset_ir=zero_pop_ir).plan(snapshot).candidate.category == (
        "production_expansion")

    population_ready = _snapshot(
        [_unit(1, "Settlers")], actions,
        cities=[_city(
            size=4, food_stock=16, shield_stock=0,
            surplus=(3, 4, 6, 2, 0, 4))],
        turn=21, source_seq=5)
    direct = GroundedImpactPlanner({
        "horizon_turn": 60, "expansion_city_target": 3,
        "production_minimum_remaining_turns": 8,
        "expansion_minimum_remaining_turns": 12,
    }, ruleset_ir=ir).plan(population_ready)
    assert direct.candidate.category == "production_expansion"
    assert direct.candidate.action["target"]["production_type"] == "Settlers"
    assert direct.candidate.projection["population_ready_eta_turns"] == 0
    assert direct.candidate.projection["shield_completion_eta_turns"] == 8


def test_horizon_policy_keeps_direct_founder_when_granary_leaves_short_runway():
    actions = [
        _production(10, "Settlers", 6, 0),
        _production(10, "Granary", 3, 14),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ir = _ruleset_ir((
        ("Settlers", "unit", 30), ("Granary", "improvement", 40),
    ), pop_costs={"Settlers": 2})
    city = _city(
        size=1, food_stock=0, shield_stock=0,
        surplus=(5, 4, 2, 1, 0, 1))
    snapshot = _snapshot(
        [_unit(1, "Settlers")], actions, cities=[city], turn=1)

    decision = GroundedImpactPlanner({
        "horizon_turn": 30, "expansion_city_target": 3,
        "production_minimum_remaining_turns": 8,
        "expansion_minimum_remaining_turns": 12,
    }, ruleset_ir=ir).plan(snapshot)

    assert decision.candidate.category == "production_expansion"
    assert decision.candidate.action["target"]["production_type"] == "Settlers"


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
        [_unit(11, "Alpine Troops", 0, 0),
         _unit(12, "Alpine Troops", 3, 0),
         _unit(13, "Alpine Troops", 6, 0)],
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
        [_unit(11, "Alpine Troops", 0, 0),
         _unit(12, "Alpine Troops", 3, 0),
         _unit(13, "Alpine Troops", 6, 0)], actions, cities=changed,
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
        [_unit(11, "Alpine Troops", 0, 0),
         _unit(12, "Alpine Troops", 3, 0),
         _unit(13, "Alpine Troops", 6, 0)],
        actions, cities=cities, turn=1)
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


def test_candidate_enumeration_reuses_snapshot_production_context():
    city = _city(production_kind=3, production_value=18,
                 surplus=(1, 5, 2, 1, 0, 3))
    city["buildability"]["options"].extend([
        {"type": "improvement", "id": 18, "name": "Marketplace"},
        {"type": "unit", "id": 9, "name": "Musketeers"},
        {"type": "unit", "id": 11, "name": "Alpine Troops"},
    ])
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [_production(10, "Musketeers", 6, 9),
         _production(10, "Alpine Troops", 6, 11),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[city], turn=1)
    planner = GroundedImpactPlanner(
        {"expansion_city_target": 1},
        ruleset_ir=_ruleset_ir((
            ("Alpine Troops", "unit", 60),
            ("Musketeers", "unit", 30),
            ("Marketplace", "improvement", 40),
        ), founders=(), workers=()))
    calls = {}
    for name in (
            "_current_production_name", "_founders",
            "_queued_founder_count", "_unit_score_batch_members",
            "_combat_units"):
        original = getattr(planner, name)

        def counted(*args, _name=name, _original=original, **kwargs):
            calls[_name] = calls.get(_name, 0) + 1
            return _original(*args, **kwargs)

        setattr(planner, name, counted)

    planner.candidates(snapshot)

    assert calls == {
        "_combat_units": 1,
        # One direct lookup plus the independent queued-founder and unit-batch
        # scans; neither lookup repeats per production alternative.
        "_current_production_name": 3,
        "_founders": 1,
        "_queued_founder_count": 1,
        "_unit_score_batch_members": 1,
    }


def test_candidate_enumeration_skips_unit_batch_when_expansion_is_required():
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [_production(10, "Settlers", 6, 0),
         _production(10, "Granary", 3, 14),
         {"action_type": "end_turn", "is_valid": True}],
        turn=1)
    planner = GroundedImpactPlanner(ruleset_ir=_ruleset_ir((
        ("Settlers", "unit", 30),
        ("Alpine Troops", "unit", 60),
        ("Granary", "improvement", 60),
    )))
    original = planner._unit_score_batch_members
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    planner._unit_score_batch_members = counted
    candidates = planner.candidates(snapshot)

    assert any(row.category == "production_expansion" for row in candidates)
    assert calls == []


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


def test_horizon_policy_stops_repeated_population_founders_midbuild():
    cities = []
    for city_id, x in ((10, 0), (12, 3), (13, 6)):
        city = _city(
            size=5, shield_stock=25 if city_id == 10 else 4,
            surplus=(5, 5, 2, 1, 0, 3),
            production_kind=6 if city_id == 10 else 3,
            production_value=0 if city_id == 10 else 14)
        city.update({"id": city_id, "tile": x, "x": x})
        cities.append(city)
    actions = [
        _production(10, "Granary", 3, 14),
        _production(10, "Alpine Troops", 6, 11),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ir = _ruleset_ir((
        ("Settlers", "unit", 30), ("Alpine Troops", "unit", 60),
        ("Granary", "improvement", 40),
    ), pop_costs={"Settlers": 2})
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")], actions, cities=cities, turn=1)

    decision = GroundedImpactPlanner(
        {"expansion_city_target": 3}, ruleset_ir=ir).plan(snapshot)

    assert decision.candidate.category == "production_repurpose"
    assert decision.candidate.action["target"]["production_type"] == "Granary"
    assert decision.candidate.projection["avoided_population_cost"] == 2
    assert decision.candidate.projection[
        "expansion_capacity_without_current"] == 3
    assert decision.candidate.projection["repurpose_discarded_shield_stock"] == 25
    assert decision.candidate.projection["repurpose_shield_stock_assumption"] == 0
    assert decision.candidate.projection["projected_shield_stock"] == 0
    assert decision.candidate.projection["completion_eta_turns"] == 8
    assert decision.candidate.projection[
        "repurpose_target_completes_by_horizon"] is True
    assert GroundedImpactPlanner(
        {"expansion_city_target": 3, "production_strategy": "static_priority"},
        ruleset_ir=ir).plan(snapshot) is None


def test_horizon_policy_preserves_necessary_or_noncompleting_founder_queue():
    actions = [
        _production(10, "Granary", 3, 14),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ir = _ruleset_ir((
        ("Settlers", "unit", 30), ("Granary", "improvement", 40),
    ), pop_costs={"Settlers": 2})
    necessary_city = _city(
        size=5, shield_stock=25, surplus=(5, 5, 2, 1, 0, 3),
        production_kind=6, production_value=0)
    necessary = _snapshot(
        [_unit(1, "Settlers")], actions, cities=[necessary_city], turn=1)
    planner = GroundedImpactPlanner(
        {"expansion_city_target": 3}, ruleset_ir=ir)

    # City + existing founder + this queue exactly meets the target. Excluding
    # the queue leaves a deficit, so it is necessary rather than redundant.
    assert planner.plan(necessary) is None

    late_cities = []
    for city_id, x in ((10, 0), (12, 3), (13, 6)):
        city = dict(necessary_city)
        city.update({"id": city_id, "tile": x, "x": x,
                     "shield_stock": 1})
        late_cities.append(city)
    late = _snapshot([], actions, cities=late_cities, turn=29)
    # The current founder cannot complete by turn 30, so its population cost
    # cannot affect the fixed-horizon score and does not justify shield loss.
    assert GroundedImpactPlanner(
        {"expansion_city_target": 3}, ruleset_ir=ir).plan(late) is None


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


def test_batched_pruning_observations_match_individual_helpers():
    ir = _ruleset_ir((
        ("Settlers", "unit", 30), ("Engineers", "unit", 30),
        ("Alpine Troops", "unit", 60)))
    planner = GroundedImpactPlanner(ruleset_ir=ir)
    snapshot = _snapshot(
        [_unit(1, "Settlers"), _unit(3, "Engineers"),
         _unit(11, "Alpine Troops", 5, 5)],
        [
            {"action_type": "unit_move", "actor_id": 1,
             "target": {"x": 2, "y": 0}, "is_valid": True},
            {"action_type": "unit_move", "actor_id": 3,
             "target": {"x": 2, "y": 0}, "is_valid": True},
            {"action_type": "unit_move", "actor_id": 11,
             "target": {"x": 6, "y": 5}, "is_valid": True},
            {"action_type": "end_turn", "is_valid": True},
        ])
    planner.observe(snapshot)

    assert planner.pruning_move_keys(snapshot) == {
        "capability_pruned_worker_moves": (
            planner.capability_pruned_worker_move_keys(snapshot)),
        "nonprogress_moves": planner.nonprogress_move_keys(snapshot),
        "unreachable_founder_moves": (
            planner.founder_unreachable_move_keys(snapshot)),
        "founder_cycle_moves": planner.founder_cycle_move_keys(snapshot),
        "founder_attrition_moves": (
            planner.founder_attrition_move_keys(snapshot)),
    }


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


def test_repeating_support_unit_is_interrupted_before_food_reserve_breach():
    city = _city(
        surplus=(1, 5, 2, 1, 0, 3), shield_stock=12,
        production_kind=6, production_value=11)
    granary = _production(10, "Granary", 3, 14)
    ruleset = _ruleset_ir((
        ("Alpine Troops", "unit", 20),
        ("Granary", "improvement", 40),
    ), founders=(), workers=(), upkeeps={
        "Alpine Troops": {"uk_food": 1},
    })
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [granary, {"action_type": "end_turn", "is_valid": True}],
        cities=[city])

    decision = GroundedImpactPlanner(
        {"expansion_city_target": 1}, ruleset_ir=ruleset).plan(snapshot)

    assert decision.candidate.category == "production_food_stabilization"
    assert decision.candidate.projection["sustainability_override"] is True
    assert decision.candidate.projection["discarded_shield_stock"] == 12


def test_treasury_deficit_redirects_repeating_unit_queue_to_coinage():
    city = _city(
        surplus=(3, 5, 2, 0, 0, 3), shield_stock=7,
        production_kind=6, production_value=11)
    coinage = _production(10, "Coinage", 3, 99)
    ruleset = _ruleset_ir((
        ("Alpine Troops", "unit", 20),
        ("Coinage", "improvement", 10),
    ), founders=(), workers=(), upkeeps={
        "Alpine Troops": {"uk_gold": 1},
    })
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [coinage, {"action_type": "end_turn", "is_valid": True}],
        cities=[city],
        player={
            "gold": 0, "city_gold_surplus_per_turn": 0,
            "gold_per_turn": 0, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
        })

    decision = GroundedImpactPlanner(
        {"expansion_city_target": 1}, ruleset_ir=ruleset).plan(snapshot)

    assert decision.candidate.category == "production_treasury_stabilization"
    assert decision.candidate.action["target"]["production_type"] == "Coinage"


def test_negative_gold_flow_is_safe_when_treasury_funds_configured_runway():
    snapshot = _snapshot(
        [], [{"action_type": "end_turn", "is_valid": True}],
        player={
            "gold": 50, "city_gold_surplus_per_turn": -1,
            "gold_per_turn": -1, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
        })
    planner = GroundedImpactPlanner({
        "treasury_minimum_gold": 5, "treasury_reserve_turns": 2,
    })

    assert planner._treasury_deficit(snapshot) is False

    near_reserve = _snapshot(
        [], [{"action_type": "end_turn", "is_valid": True}],
        player={
            "gold": 6, "city_gold_surplus_per_turn": -1,
            "gold_per_turn": -1, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
        })
    assert planner._treasury_deficit(near_reserve) is True


def test_existing_treasury_stabilizer_is_not_replaced_by_another_one():
    city = _city(
        surplus=(3, 5, 2, 0, 0, 3), shield_stock=7,
        production_kind=3, production_value=99)
    ruleset = _ruleset_ir((
        ("Coinage", "improvement", 10),
        ("Marketplace", "improvement", 60),
    ), founders=(), workers=())
    snapshot = _snapshot(
        [], [_production(10, "Marketplace", 3, 98),
             {"action_type": "end_turn", "is_valid": True}],
        cities=[city],
        player={
            "gold": 0, "city_gold_surplus_per_turn": -1,
            "gold_per_turn": -1, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
        })
    planner = GroundedImpactPlanner(
        {"expansion_city_target": 1}, ruleset_ir=ruleset)

    assert planner._production_sustainability_route(
        snapshot, city, "coinage", "marketplace", frozenset()) is None


def test_treasury_stabilizer_requires_extra_runway_before_expansion_release():
    city = _city(
        surplus=(3, 5, 2, -9, 0, 3), production_kind=3,
        production_value=72)
    city["buildability"]["options"].append(
        {"type": "improvement", "id": 72, "name": "Coinage"})
    settler = _production(10, "Settlers", 6, 0)
    ruleset = _ruleset_ir((
        ("Settlers", "unit", 20),
        ("Coinage", "improvement", 10),
    ))
    planner = GroundedImpactPlanner({
        "expansion_city_target": 2,
        "treasury_minimum_gold": 5,
        "treasury_reserve_turns": 2,
    }, ruleset_ir=ruleset)
    actions = [settler, {"action_type": "end_turn", "is_valid": True}]
    boundary = _snapshot(
        [_unit(11, "Alpine Troops")], actions, cities=[city],
        player={
            "gold": 29, "city_gold_surplus_per_turn": -9,
            "gold_per_turn": -9, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
        })
    durable = _snapshot(
        [_unit(11, "Alpine Troops")], actions, cities=[city],
        player={
            "gold": 80, "city_gold_surplus_per_turn": -9,
            "gold_per_turn": -9, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
        }, source_seq=2)

    assert planner._treasury_deficit(boundary) is False
    assert planner._treasury_recovery_can_release(boundary) is False
    assert planner.plan(boundary) is None
    assert planner._treasury_recovery_can_release(durable) is True
    decision = planner.plan(durable)
    assert decision.candidate.category == "production_expansion"
    assert decision.candidate.projection[
        "founder_financing_gold_at_settlement"] >= (
            decision.candidate.projection[
                "founder_financing_reserve_required"])


def test_coinage_release_uses_post_switch_cash_flow_for_garrison_runway():
    city = _city(
        size=4, shield_stock=0, surplus=(2, 5, 3, -5, 0, 2),
        production_kind=3, production_value=72)
    city["buildability"]["options"].extend([
        {"type": "unit", "id": 10, "name": "Riflemen"},
        {"type": "improvement", "id": 72, "name": "Coinage"},
    ])
    defender = _production(10, "Riflemen", 6, 10)
    ruleset = _ruleset_ir((
        ("Riflemen", "unit", 20),
        ("Coinage", "improvement", 999),
    ), founders=(), workers=())
    planner = GroundedImpactPlanner({
        "expansion_city_target": 1,
        "treasury_minimum_gold": 5,
        "treasury_reserve_turns": 2,
    }, ruleset_ir=ruleset)
    actions = [defender, {"action_type": "end_turn", "is_valid": True}]
    boundary = _snapshot(
        [], actions, cities=[city],
        player={
            "gold": 19, "gold_per_turn": 0,
            "operating_gold_per_turn": -5,
            "capitalization_gold_per_turn": 5,
            "city_gold_surplus_per_turn": -5,
            "gold_upkeep_style": "Mixed",
            "unit_gold_upkeep": 0, "gold_upkeep_reserve": 0,
        })
    funded = _snapshot(
        [], actions, cities=[city], source_seq=2,
        player={
            "gold": 30, "gold_per_turn": 0,
            "operating_gold_per_turn": -5,
            "capitalization_gold_per_turn": 5,
            "city_gold_surplus_per_turn": -5,
            "gold_upkeep_style": "Mixed",
            "unit_gold_upkeep": 0, "gold_upkeep_reserve": 0,
        })

    assert planner._treasury_deficit(boundary) is False
    assert planner._treasury_recovery_can_release(
        boundary, boundary.cities[0]) is False
    assert planner.plan(boundary) is None
    decision = planner.plan(funded)
    assert decision.candidate.category == "production_defense"
    assert decision.candidate.projection["treasury_at_completion"] == 10


def test_funded_structural_treasury_recovery_finishes_before_garrison():
    city = _city(
        size=4, shield_stock=7, surplus=(2, 5, 3, 2, 0, 2),
        production_kind=3, production_value=18)
    city["buildability"]["options"].extend([
        {"type": "unit", "id": 10, "name": "Riflemen"},
        {"type": "improvement", "id": 18, "name": "Marketplace"},
    ])
    ruleset = _ruleset_ir((
        ("Riflemen", "unit", 20),
        ("Marketplace", "improvement", 60),
    ), founders=(), workers=())
    snapshot = _snapshot(
        [], [_production(10, "Riflemen", 6, 10),
             {"action_type": "end_turn", "is_valid": True}],
        cities=[city],
        player={
            "gold": 100, "gold_per_turn": 2,
            "operating_gold_per_turn": 2,
            "capitalization_gold_per_turn": 0,
            "city_gold_surplus_per_turn": 2,
            "unit_gold_upkeep": 0, "gold_upkeep_reserve": 0,
        })

    assert GroundedImpactPlanner(
        {"expansion_city_target": 1}, ruleset_ir=ruleset).plan(
        snapshot) is None


def test_ruleset_defender_requires_counterfactual_treasury_runway():
    city = _city(
        size=4, shield_stock=0, surplus=(2, 10, 3, -10, 0, 2),
        production_kind=3, production_value=72)
    city["buildability"]["options"].extend([
        {"type": "unit", "id": 14, "name": "Sentinel"},
        {"type": "improvement", "id": 72, "name": "Coinage"},
    ])
    actions = [
        _production(10, "Sentinel", 6, 14),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ruleset = _ruleset_ir((
        ("Sentinel", "unit", 60),
        ("Coinage", "improvement", 999),
    ), founders=(), workers=(), capabilities={
        "Sentinel": {
            "class": "Land", "attack": 4, "defense": 6,
            "hitpoints": 20, "firepower": 1,
        },
    })
    settings = {
        "expansion_city_target": 1,
        "ruleset_driven_production_enabled": True,
        "modernization_enabled": True,
        "treasury_minimum_gold": 5,
        "treasury_reserve_turns": 2,
    }
    unfunded = _snapshot(
        [], actions, cities=[city],
        player={
            "gold": 30, "gold_per_turn": 0,
            "operating_gold_per_turn": -10,
            "capitalization_gold_per_turn": 10,
            "city_gold_surplus_per_turn": -10,
            "gold_upkeep_style": "Mixed",
            "unit_gold_upkeep": 0, "gold_upkeep_reserve": 0,
        })
    funded = _snapshot(
        [], actions, cities=[city], source_seq=2,
        player={
            "gold": 100, "gold_per_turn": 0,
            "operating_gold_per_turn": -10,
            "capitalization_gold_per_turn": 10,
            "city_gold_surplus_per_turn": -10,
            "gold_upkeep_style": "Mixed",
            "unit_gold_upkeep": 0, "gold_upkeep_reserve": 0,
        })

    assert GroundedImpactPlanner(settings, ruleset_ir=ruleset).plan(
        unfunded) is None
    decision = GroundedImpactPlanner(settings, ruleset_ir=ruleset).plan(funded)
    assert decision.candidate.category == "production_defense"
    assert decision.candidate.action["target"]["production_type"] == "Sentinel"
    assert decision.candidate.projection[
        "garrison_role_source"] == "ruleset_defense_not_less_than_attack"
    assert decision.candidate.projection["treasury_at_completion"] == 40


def test_funded_ruleset_defender_queue_survives_transient_treasury_pressure():
    city = _city(
        size=4, shield_stock=20, surplus=(2, 10, 3, -1, 0, 2),
        production_kind=6, production_value=14)
    city["buildability"]["options"].extend([
        {"type": "unit", "id": 14, "name": "Sentinel"},
        {"type": "improvement", "id": 72, "name": "Coinage"},
    ])
    actions = [
        _production(10, "Alpine Troops", 6, 11),
        _production(10, "Coinage", 3, 72),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ruleset = _ruleset_ir((
        ("Alpine Troops", "unit", 20),
        ("Sentinel", "unit", 60),
        ("Coinage", "improvement", 999),
    ), founders=(), workers=(), capabilities={
        "Alpine Troops": {
            "class": "Land", "attack": 5, "defense": 5,
            "hitpoints": 20, "firepower": 1,
        },
        "Sentinel": {
            "class": "Land", "attack": 4, "defense": 6,
            "hitpoints": 20, "firepower": 1,
        },
    })
    settings = {
        "expansion_city_target": 1,
        "ruleset_driven_production_enabled": True,
        "modernization_enabled": True,
        "treasury_minimum_gold": 5,
        "treasury_reserve_turns": 2,
    }
    funded = _snapshot(
        [], actions, cities=[city],
        player={
            "gold": 20, "gold_per_turn": -1,
            "operating_gold_per_turn": -1,
            "capitalization_gold_per_turn": 0,
            "city_gold_surplus_per_turn": -1,
            "gold_upkeep_style": "Mixed",
            "unit_gold_upkeep": 0, "gold_upkeep_reserve": 0,
        })
    crisis = _snapshot(
        [], actions, cities=[city], source_seq=2,
        player={
            "gold": 5, "gold_per_turn": -5,
            "operating_gold_per_turn": -5,
            "capitalization_gold_per_turn": 0,
            "city_gold_surplus_per_turn": -5,
            "gold_upkeep_style": "Mixed",
            "unit_gold_upkeep": 0, "gold_upkeep_reserve": 0,
        })

    assert GroundedImpactPlanner(settings, ruleset_ir=ruleset).plan(
        funded) is None
    emergency = GroundedImpactPlanner(settings, ruleset_ir=ruleset).plan(crisis)
    assert emergency.candidate.category == "production_treasury_stabilization"
    assert emergency.candidate.action["target"]["production_type"] == "Coinage"


def test_visible_pressure_blocks_rebuild_after_observed_founder_attrition():
    settler = _production(10, "Settlers", 6, 0)
    actions = [settler, {"action_type": "end_turn", "is_valid": True}]
    ruleset = _ruleset_ir((("Settlers", "unit", 20),))
    planner = GroundedImpactPlanner({
        "expansion_city_target": 2,
        "founder_attrition_rebuild_limit": 1,
    }, ruleset_ir=ruleset)
    founder_present = _snapshot(
        [_unit(1, "Settlers", x=1), _enemy(99, "Riflemen", 3, 0)],
        actions)
    under_pressure = _snapshot(
        [_enemy(99, "Riflemen", 3, 0)], actions, source_seq=2, turn=2)
    pressure_gone = _snapshot([], actions, source_seq=3, turn=3)

    planner.observe(founder_present)
    planner.observe(under_pressure)

    assert planner._founder_attrition_total(
        under_pressure, frozenset({"settlers"})) == 1
    assert planner.plan(under_pressure) is None
    assert planner.plan(
        pressure_gone).candidate.category == "production_expansion"


def test_founder_attrition_guard_expires_even_while_enemy_remains_visible():
    settler = _production(10, "Settlers", 6, 0)
    actions = [settler, {"action_type": "end_turn", "is_valid": True}]
    ruleset = _ruleset_ir((("Settlers", "unit", 20),))
    planner = GroundedImpactPlanner({
        "expansion_city_target": 2,
        "founder_attrition_rebuild_limit": 1,
        "founder_attrition_memory_turns": 5,
        "horizon_turn": 100,
    }, ruleset_ir=ruleset)
    founder_present = _snapshot(
        [_unit(1, "Settlers", x=2), _enemy(99, "Riflemen", 3, 0)],
        actions, turn=1)
    founder_lost = _snapshot(
        [_enemy(99, "Riflemen", 3, 0)],
        actions, source_seq=2, turn=2)
    memory_expired = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(12, "Alpine Troops"),
         _enemy(99, "Riflemen", 3, 0)],
        actions, source_seq=3, turn=8)

    planner.observe(founder_present)
    planner.observe(founder_lost)

    assert planner.plan(founder_lost) is None
    assert planner.plan(
        memory_expired).candidate.category == "production_expansion"


def test_founder_attrition_backoff_grows_after_repeated_recovery_losses():
    actions = [
        _production(10, "Settlers", 6, 0),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ruleset = _ruleset_ir((("Settlers", "unit", 20),))
    planner = GroundedImpactPlanner({
        "expansion_city_target": 2,
        "founder_attrition_rebuild_limit": 1,
        "founder_attrition_memory_turns": 5,
        "horizon_turn": 100,
    }, ruleset_ir=ruleset)
    enemy = _enemy(99, "Riflemen", 3, 0)

    planner.observe(_snapshot(
        [_unit(1, "Settlers", x=2), enemy], actions, turn=1))
    planner.observe(_snapshot(
        [enemy], actions, source_seq=2, turn=2))
    planner.observe(_snapshot(
        [_unit(2, "Settlers", x=2), enemy],
        actions, source_seq=3, turn=8))
    second_loss = _snapshot(
        [enemy], actions, source_seq=4, turn=9)
    planner.observe(second_loss)

    guard_turns, latest_turn, losses = planner._founder_attrition_backoff(
        second_loss, frozenset({"settlers"}))
    assert (guard_turns, latest_turn, losses) == (10, 9, 2)
    assert planner.plan(second_loss) is None

    expired = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(12, "Alpine Troops"), enemy],
        actions, source_seq=5, turn=20)
    assert planner.plan(
        expired).candidate.category == "production_expansion"


def test_owned_city_loss_reopens_recovery_after_older_founder_attrition():
    settler = _production(10, "Settlers", 6, 0)
    actions = [settler, {"action_type": "end_turn", "is_valid": True}]
    ruleset = _ruleset_ir((("Settlers", "unit", 20),))
    second_city = dict(_city())
    second_city.update({"id": 20, "name": "Antium", "x": 5, "tile": 5})
    planner = GroundedImpactPlanner({
        "expansion_city_target": 3,
        "founder_attrition_rebuild_limit": 1,
        "founder_attrition_memory_turns": 200,
        "horizon_turn": 200,
    }, ruleset_ir=ruleset)
    founder_present = _snapshot(
        [_unit(1, "Settlers", x=2), _enemy(99, "Riflemen", 3, 0)],
        actions, cities=[_city(), second_city], turn=1)
    founder_lost = _snapshot(
        [_enemy(99, "Riflemen", 3, 0)],
        actions, cities=[_city(), second_city], source_seq=2, turn=2)
    city_lost_unprotected = _snapshot(
        [], actions, cities=[_city()], source_seq=3, turn=100)
    city_lost = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(12, "Alpine Troops"),
         _enemy(99, "Riflemen", 3, 0)],
        actions, cities=[_city()], source_seq=4, turn=101)

    planner.observe(founder_present)
    planner.observe(founder_lost)
    assert planner.plan(founder_lost) is None

    planner.observe(city_lost_unprotected)
    assert planner.plan(city_lost_unprotected) is None

    planner.observe(city_lost)
    decision = planner.plan(city_lost)

    assert decision.candidate.category == "production_expansion"
    assert decision.candidate.projection["city_loss_recovery"] is True
    assert decision.candidate.projection["city_loss_recovery_target"] == 2
    assert decision.candidate.projection["lost_city_ids"] == (20,)


def test_city_loss_recovery_honors_route_attrition_without_local_enemy():
    settler = _production(10, "Settlers", 6, 0)
    actions = [settler, {"action_type": "end_turn", "is_valid": True}]
    ruleset = _ruleset_ir((("Settlers", "unit", 20),))
    second_city = dict(_city())
    second_city.update({"id": 20, "name": "Antium", "x": 5, "tile": 5})
    defenders = [
        _unit(11, "Alpine Troops"), _unit(12, "Alpine Troops")]
    planner = GroundedImpactPlanner({
        "expansion_city_target": 2,
        "founder_attrition_rebuild_limit": 1,
        "founder_attrition_memory_turns": 20,
        "horizon_turn": 100,
    }, ruleset_ir=ruleset)
    planner.observe(_snapshot(
        defenders, actions, cities=[_city(), second_city], turn=1))
    city_lost = _snapshot(
        defenders, actions, cities=[_city()], source_seq=2, turn=2)
    planner.observe(city_lost)
    assert planner.plan(
        city_lost).candidate.category == "production_expansion"

    planner.observe(_snapshot(
        defenders + [_unit(50, "Settlers", x=2)],
        actions, cities=[_city()], source_seq=3, turn=3))
    route_loss = _snapshot(
        defenders, actions, cities=[_city()], source_seq=4, turn=4)
    planner.observe(route_loss)

    assert route_loss.visible_enemy_units == ()
    assert planner.plan(route_loss) is None

    expired = _snapshot(
        defenders, actions, cities=[_city()], source_seq=5, turn=25)
    assert planner.plan(
        expired).candidate.category == "production_expansion"


def test_blocked_founder_does_not_reserve_research_recovery_production():
    actions = [
        _production(10, "Settlers", 6, 0),
        _production(10, "Library", 3, 17),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ruleset = _ruleset_ir((
        ("Settlers", "unit", 20),
        ("Library", "improvement", 40),
        ("Coinage", "improvement", 999),
    ))
    city = _city(
        size=4, production_kind=3, production_value=72,
        surplus=(1, 4, 2, 1, 0, 3))
    planner = GroundedImpactPlanner({
        "expansion_city_target": 2,
        "founder_attrition_rebuild_limit": 1,
        "founder_attrition_memory_turns": 20,
        "horizon_turn": 100,
        "ruleset_driven_production_enabled": True,
    }, ruleset_ir=ruleset)
    founder_present = _snapshot(
        [_unit(1, "Settlers", x=2), _unit(11, "Alpine Troops"),
         _enemy(99, "Riflemen", 3, 0)],
        actions, cities=[city], turn=1,
        research={
            "beakers_per_turn": -1,
            "gross_beakers_per_turn": 2,
            "tech_upkeep": 3,
        })
    founder_lost = _snapshot(
        [_unit(11, "Alpine Troops"), _enemy(99, "Riflemen", 3, 0)],
        actions, cities=[city], source_seq=2, turn=2,
        research={
            "beakers_per_turn": -1,
            "gross_beakers_per_turn": 2,
            "tech_upkeep": 3,
        })

    planner.observe(founder_present)
    planner.observe(founder_lost)
    decision = planner.plan(founder_lost)

    assert decision.candidate.category == "production_research_infrastructure"
    assert decision.candidate.action["target"]["production_type"] == "Library"


def test_founder_viability_removes_current_coinage_through_settlement():
    actions = [
        _production(10, "Settlers", 6, 0),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ruleset = _ruleset_ir((
        ("Settlers", "unit", 20),
        ("Coinage", "improvement", 999),
    ), upkeeps={"Settlers": {"uk_gold": 1}})
    city = _city(
        size=4, production_kind=3, production_value=72,
        surplus=(1, 9, 2, -8, 0, 3))
    city["buildability"]["options"].extend([
        {"type": "unit", "id": 0, "name": "Settlers"},
        {"type": "improvement", "id": 72, "name": "Coinage"},
    ])
    settings = {
        "expansion_city_target": 2,
        "horizon_turn": 100,
    }
    masked = _snapshot(
        [], actions, cities=[city], turn=1,
        player={
            "gold": 8, "gold_per_turn": 0,
            "operating_gold_per_turn": -9,
            "capitalization_gold_per_turn": 9,
            "city_gold_surplus_per_turn": -8,
            "gold_upkeep_style": "Mixed",
            "unit_gold_upkeep": 1, "gold_upkeep_reserve": 1,
        })
    funded = _snapshot(
        [], actions, cities=[city], source_seq=2, turn=1,
        player={
            "gold": 100, "gold_per_turn": 0,
            "operating_gold_per_turn": -9,
            "capitalization_gold_per_turn": 9,
            "city_gold_surplus_per_turn": -8,
            "gold_upkeep_style": "Mixed",
            "unit_gold_upkeep": 1, "gold_upkeep_reserve": 1,
        })

    assert GroundedImpactPlanner(
        settings, ruleset_ir=ruleset).plan(masked) is None
    decision = GroundedImpactPlanner(
        settings, ruleset_ir=ruleset).plan(funded)

    assert decision.candidate.category == "production_expansion"
    assert decision.candidate.projection[
        "founder_financing_coinage_removed"] == 9
    assert decision.candidate.projection[
        "founder_financing_construction_gold_per_turn"] == -9
    assert decision.candidate.projection[
        "founder_financing_gold_at_settlement"] >= (
            decision.candidate.projection[
                "founder_financing_reserve_required"])


def test_threatened_founder_build_requires_a_surplus_local_defender():
    actions = [
        _production(10, "Settlers", 6, 0),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ruleset = _ruleset_ir((("Settlers", "unit", 20),))
    enemy = _enemy(99, "Riflemen", 3, 0)
    settings = {"expansion_city_target": 2, "horizon_turn": 100}
    planner = GroundedImpactPlanner(settings, ruleset_ir=ruleset)
    city = _city()
    required = planner._required_garrison_count(
        _snapshot([], actions, cities=[city]).cities[0])
    exact_garrison = [
        _unit(10 + index, "Alpine Troops")
        for index in range(required)]
    surplus_garrison = exact_garrison + [
        _unit(10 + required, "Alpine Troops")]
    threatened = _snapshot(
        exact_garrison + [enemy], actions, cities=[city], turn=1)
    buffered = _snapshot(
        surplus_garrison + [enemy], actions, cities=[city],
        source_seq=2, turn=1)

    assert GroundedImpactPlanner(
        settings, ruleset_ir=ruleset).plan(threatened) is None
    decision = GroundedImpactPlanner(
        settings, ruleset_ir=ruleset).plan(buffered)

    assert decision.candidate.category == "production_expansion"
    assert decision.candidate.projection[
        "founder_local_visible_threat"] is True
    assert decision.candidate.projection[
        "founder_local_defenders"] == required + 1
    assert decision.candidate.projection[
        "founder_minimum_local_defenders"] == required + 1


def test_expired_coinage_bridge_materializes_productive_continuity():
    actions = [
        _production(10, "Mech. Inf.", 6, 16),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ruleset = _ruleset_ir((
        ("Alpine Troops", "unit", 20),
        ("Mech. Inf.", "unit", 40),
        ("Coinage", "improvement", 999),
    ), founders=(), workers=(), capabilities={
        "Alpine Troops": {
            "class": "Land", "attack": 5, "defense": 5,
            "hitpoints": 20, "firepower": 1,
        },
        "Mech. Inf.": {
            "class": "Land", "attack": 6, "defense": 12,
            "hitpoints": 30, "firepower": 1,
        },
    })
    city = _city(
        size=4, production_kind=3, production_value=72,
        surplus=(2, 8, 4, -4, 0, 3))
    city["buildability"]["options"].extend([
        {"type": "unit", "id": 16, "name": "Mech. Inf."},
        {"type": "improvement", "id": 72, "name": "Coinage"},
    ])
    settings = {
        "expansion_city_target": 1,
        "horizon_turn": 100,
        "coinage_bridge_max_turns": 10,
        "ruleset_driven_production_enabled": True,
        "modernization_enabled": True,
    }
    initial = _snapshot(
        [_unit(11, "Alpine Troops")], actions, cities=[city], turn=1,
        player={
            "gold": 100, "gold_per_turn": 1,
            "operating_gold_per_turn": -5,
            "capitalization_gold_per_turn": 8,
            "city_gold_surplus_per_turn": -4,
            "gold_upkeep_style": "Mixed",
            "unit_gold_upkeep": 0, "gold_upkeep_reserve": 0,
        })
    expired = _snapshot(
        [_unit(11, "Alpine Troops")], actions, cities=[city],
        source_seq=2, turn=12,
        player={
            "gold": 111, "gold_per_turn": 1,
            "operating_gold_per_turn": -5,
            "capitalization_gold_per_turn": 8,
            "city_gold_surplus_per_turn": -4,
            "gold_upkeep_style": "Mixed",
            "unit_gold_upkeep": 0, "gold_upkeep_reserve": 0,
        })
    planner = GroundedImpactPlanner(settings, ruleset_ir=ruleset)

    planner.observe(initial)
    planner.observe(expired)
    decision = planner.plan(expired)

    assert decision.candidate.category == "production_continuity"
    assert decision.candidate.projection[
        "continuity_original_category"] == "production_modernization"
    assert decision.candidate.projection["coinage_bridge_turns"] == 11


def test_recent_founder_loss_interrupts_unsafe_repeating_founder_queue():
    actions = [
        _production(10, "Coinage", 3, 72),
        {"action_type": "end_turn", "is_valid": True},
    ]
    ruleset = _ruleset_ir((
        ("Settlers", "unit", 20),
        ("Coinage", "improvement", 999),
    ))
    city = _city(
        size=4, production_kind=6, production_value=0,
        shield_stock=8, surplus=(1, 9, 2, 0, 0, 3))
    city["buildability"]["options"].append(
        {"type": "improvement", "id": 72, "name": "Coinage"})
    planner = GroundedImpactPlanner({
        "expansion_city_target": 2,
        "founder_attrition_rebuild_limit": 1,
        "founder_attrition_memory_turns": 20,
    }, ruleset_ir=ruleset)
    founder_present = _snapshot(
        [_unit(1, "Settlers", x=2), _enemy(99, "Riflemen", 3, 0)],
        actions, cities=[city], turn=1)
    founder_lost = _snapshot(
        [_enemy(99, "Riflemen", 3, 0)],
        actions, cities=[city], source_seq=2, turn=2)

    planner.observe(founder_present)
    planner.observe(founder_lost)
    decision = planner.plan(founder_lost)

    assert (
        decision.candidate.category
        == "production_founder_attrition_recovery")
    assert decision.candidate.action["target"][
        "production_type"] == "Coinage"
    assert decision.candidate.projection[
        "founder_attrition_backoff_turns"] == 20
    assert decision.candidate.projection[
        "founder_attrition_lifecycle_losses"] == 1
    assert decision.candidate.projection["discarded_shield_stock"] == 8


def test_masked_structural_and_research_deficits_remain_pressure_facts():
    city = _city(
        size=4, production_kind=3, production_value=72,
        surplus=(1, 9, 2, -8, 0, 3))
    city["buildability"]["options"].append(
        {"type": "improvement", "id": 72, "name": "Coinage"})
    settings = {
        "expansion_city_target": 1,
        "coinage_bridge_max_turns": 20,
    }
    player = {
        "gold": 8, "gold_per_turn": 0,
        "operating_gold_per_turn": -9,
        "capitalization_gold_per_turn": 9,
        "city_gold_surplus_per_turn": -8,
        "gold_upkeep_style": "Mixed",
        "unit_gold_upkeep": 1, "gold_upkeep_reserve": 1,
    }
    research = {
        "beakers_per_turn": 2,
        "gross_beakers_per_turn": 6,
        "tech_upkeep": 4,
    }
    planner = GroundedImpactPlanner(settings)
    planner.observe(_snapshot(
        [], [{"action_type": "end_turn", "is_valid": True}],
        cities=[city], turn=1, player=player, research=research))
    expired = _snapshot(
        [], [{"action_type": "end_turn", "is_valid": True}],
        cities=[city], source_seq=2, turn=22,
        player=player, research=research)
    planner.observe(expired)

    facts = planner._sustainability_facts(expired)

    assert facts["production_continuity_city_ids"] == (10,)
    assert facts["production_continuity_releasable_city_ids"] == ()
    assert facts["production_continuity_blocked_city_ids"] == (10,)
    assert facts["research_deficit"] is True
    assert facts["treasury_effective_deficit"] is False
    assert facts["treasury_structural_deficit"] is True
    assert facts["treasury_deficit"] is True


def test_required_city_defender_reaches_first_completion_before_food_recovery():
    city = _city(surplus=(1, 5, 2, 1, 0, 3))
    ruleset = _ruleset_ir((
        ("Alpine Troops", "unit", 20),
        ("Granary", "improvement", 40),
    ), founders=(), workers=(), upkeeps={
        "Alpine Troops": {"uk_food": 1},
    })
    snapshot = _snapshot(
        [], [_production(10, "Granary", 3, 14),
             {"action_type": "end_turn", "is_valid": True}],
        cities=[city])
    city_state = snapshot.cities[0]
    planner = GroundedImpactPlanner(
        {"expansion_city_target": 1}, ruleset_ir=ruleset)

    assert planner._production_upkeep_safe(
        snapshot, city_state, "alpine troops", food_surplus_floor=0) is True
    assert planner._production_upkeep_safe(
        snapshot, city_state, "alpine troops") is False
    assert planner._production_sustainability_route(
        snapshot, city_state, "alpine troops", "granary", frozenset()) is None

    starving_city = _city(surplus=(0, 5, 2, 1, 0, 3))
    starving = _snapshot(
        [], [_production(10, "Granary", 3, 14),
             {"action_type": "end_turn", "is_valid": True}],
        cities=[starving_city])
    assert planner._production_sustainability_route(
        starving, starving.cities[0], "alpine troops", "granary",
        frozenset()) is None

    repeated = _snapshot(
        [_unit(11, "Alpine Troops")],
        [_production(10, "Granary", 3, 14),
         {"action_type": "end_turn", "is_valid": True}],
        cities=[starving_city])
    assert planner._production_sustainability_route(
        repeated, repeated.cities[0], "alpine troops", "granary",
        frozenset())[0] == "production_food_stabilization"


def test_required_founder_reaches_first_completion_before_food_recovery():
    city = _city(
        size=3, food_stock=20, shield_stock=12,
        surplus=(0, 6, 3, 2, 0, 3),
        production_kind=6, production_value=0)
    coinage = _production(10, "Coinage", 3, 99)
    founder = _production(10, "Settlers", 6, 0)
    ruleset = _ruleset_ir((
        ("Settlers", "unit", 30),
        ("Coinage", "improvement", 999),
    ), founders=("Settlers",), workers=("Settlers",), upkeeps={
        "Settlers": {"uk_food": 1},
    }, pop_costs={"Settlers": 1})
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops")],
        [founder, coinage, {"action_type": "end_turn", "is_valid": True}],
        cities=[city], turn=100)
    planner = GroundedImpactPlanner({
        "expansion_city_target": 2, "horizon_turn": 480,
    }, ruleset_ir=ruleset)

    assert planner._production_sustainability_route(
        snapshot, snapshot.cities[0], "settlers", "coinage",
        frozenset(("settlers",)),
        current_is_required_founder=True) is None
    assert planner.plan(snapshot) is None


def test_food_recovery_prefers_output_building_and_finishes_before_garrison():
    city = _city(
        size=5, food_stock=8, shield_stock=12,
        surplus=(-1, 7, 5, 2, 0, 3),
        production_kind=6, production_value=10)
    city["buildability"]["options"].extend([
        {"type": "unit", "id": 10, "name": "Riflemen"},
        {"type": "improvement", "id": 39, "name": "Supermarket"},
        {"type": "improvement", "id": 72, "name": "Coinage"},
    ])
    supermarket = _production(10, "Supermarket", 3, 39)
    coinage = _production(10, "Coinage", 3, 72)
    defender = _production(10, "Riflemen", 6, 10)
    ruleset = _ruleset_ir((
        ("Riflemen", "unit", 30),
        ("Supermarket", "improvement", 80),
        ("Coinage", "improvement", 999),
    ), founders=(), workers=(), upkeeps={
        "Riflemen": {"uk_food": 1},
    })
    guarded = _snapshot(
        [],
        [supermarket, coinage, defender,
         {"action_type": "end_turn", "is_valid": True}],
        cities=[city], turn=100)
    planner = GroundedImpactPlanner({
        "expansion_city_target": 1, "horizon_turn": 480,
    }, ruleset_ir=ruleset)

    recovery = planner.plan(guarded)
    assert recovery.candidate.category == "production_food_stabilization"
    assert recovery.candidate.action["target"]["production_type"] == (
        "Supermarket")

    recovering_city = dict(
        city, production_kind=3, production_value=39, shield_stock=20)
    undefended = _snapshot(
        [], [supermarket, coinage, defender,
             {"action_type": "end_turn", "is_valid": True}],
        cities=[recovering_city], source_seq=2, turn=101)
    assert planner.plan(undefended) is None

    reserve_touched_city = dict(
        recovering_city, surplus=[1, 7, 5, 2, 0, 3])
    reserve_touched = _snapshot(
        [], [supermarket, coinage, defender,
             {"action_type": "end_turn", "is_valid": True}],
        cities=[reserve_touched_city], source_seq=3, turn=102)
    assert planner.plan(reserve_touched) is None


def test_missing_garrison_waits_for_full_build_treasury_runway():
    city = _city(
        size=4, shield_stock=12, surplus=(1, 4, 3, 1, 0, 2),
        production_kind=3, production_value=72)
    city["buildability"]["options"].extend([
        {"type": "unit", "id": 10, "name": "Riflemen"},
        {"type": "improvement", "id": 72, "name": "Coinage"},
    ])
    defender = _production(10, "Riflemen", 6, 10)
    ruleset = _ruleset_ir((
        ("Riflemen", "unit", 30),
        ("Coinage", "improvement", 999),
    ), founders=(), workers=())
    snapshot = _snapshot(
        [], [defender, {"action_type": "end_turn", "is_valid": True}],
        cities=[city],
        player={
            "gold": 10, "city_gold_surplus_per_turn": -1,
            "gold_per_turn": -1, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
        })

    assert GroundedImpactPlanner(
        {"expansion_city_target": 1}, ruleset_ir=ruleset).plan(
            snapshot) is None


def test_missing_local_garrison_interrupts_midbuild_even_at_zero_food_surplus():
    city = _city(
        size=4, shield_stock=80, surplus=(0, 7, 5, 2, 0, 3),
        production_kind=3, production_value=99)
    defender = _production(10, "Alpine Troops", 6, 11)
    ruleset = _ruleset_ir((
        ("Alpine Troops", "unit", 20),
        ("Coinage", "improvement", 999),
    ), founders=(), workers=(), upkeeps={
        "Alpine Troops": {"uk_food": 1, "uk_gold": 1},
    })
    snapshot = _snapshot(
        [], [defender, {"action_type": "end_turn", "is_valid": True}],
        cities=[city],
        player={
            "gold": 50, "city_gold_surplus_per_turn": 2,
            "gold_per_turn": 2, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
        })

    decision = GroundedImpactPlanner(
        {"expansion_city_target": 1}, ruleset_ir=ruleset).plan(snapshot)

    assert decision.candidate.category == "production_defense"
    assert decision.candidate.projection["mandatory_local_garrison"] is True
    assert decision.candidate.projection["discarded_shield_stock"] == 80
    assert decision.candidate.projection["completion_eta_turns"] == 3
    assert decision.candidate.projection["current_garrison"] == 0
    assert decision.candidate.projection["required_garrison"] == 1


def test_food_deficit_activates_exact_server_city_governor_once():
    city = _city(surplus=(-1, 5, 2, 1, 0, 3))
    city["governor"] = {
        "available": True, "enabled": False,
        "minimal_surplus": [0, 0, 0, 0, 0, 0],
        "require_happy": False, "allow_disorder": False,
        "max_growth": False, "allow_specialists": True,
        "factor": [0, 0, 0, 0, 0, 0], "happy_factor": 0,
    }
    action = {
        "type": "city_governor", "city_id": 10,
        "target": {"food_surplus_reserve": 1}, "is_valid": True,
    }
    before = _snapshot(
        [], [action, {"action_type": "end_turn", "is_valid": True}],
        cities=[city])
    planner = GroundedImpactPlanner({"expansion_city_target": 1})

    decision = planner.plan(before)

    assert decision.candidate.category == "city_food_governor"
    assert decision.candidate.scope == ("governor", 10)
    assert decision.candidate.action == {
        "action_type": "city_governor", "city_id": 10,
        "target": {"food_surplus_reserve": 1},
    }
    assert decision.candidate.projection["server_capability"] == (
        "PACKET_WEB_CMA_SET")

    recovered_city = dict(city, surplus=[1, 5, 2, 1, 0, 3])
    recovered_city["governor"] = {
        "available": True, "enabled": True,
        "minimal_surplus": [1, 0, 0, 0, 0, 0],
        "require_happy": False, "allow_disorder": False,
        "max_growth": False, "allow_specialists": True,
        "factor": [6, 2, 2, 1, 1, 2], "happy_factor": 0,
    }
    after = _snapshot(
        [], [action, {"action_type": "end_turn", "is_valid": True}],
        cities=[recovered_city], source_seq=2)
    assert planner.candidate_effect_observed(
        decision.candidate, before, after) is True
    assert planner._city_food_governor_candidate(
        after, decision.candidate.action) is None


def test_infeasible_city_governor_retries_only_after_topology_change():
    city = _city(
        size=4, shield_stock=10, surplus=(0, 7, 5, 2, 0, 3),
        production_kind=3, production_value=14)
    city["governor"] = {
        "available": True, "enabled": False,
        "minimal_surplus": [0, 0, 0, 0, 0, 0],
        "require_happy": False, "allow_disorder": False,
        "max_growth": False, "allow_specialists": False,
        "factor": [0, 0, 0, 0, 0, 0], "happy_factor": 0,
    }
    action = {
        "action_type": "city_governor", "city_id": 10,
        "target": {"food_surplus_reserve": 1}, "is_valid": True,
    }
    planner = GroundedImpactPlanner({
        "expansion_city_target": 1, "no_effect_retry_limit": 1,
    })
    before = _snapshot(
        [], [action, {"action_type": "end_turn", "is_valid": True}],
        cities=[city])
    attempted = planner.plan(before)
    assert attempted.candidate.category == "city_food_governor"
    planner.record_outcome(
        attempted.candidate, before, effect_observed=False,
        after_snapshot=before)

    accumulating = dict(city, shield_stock=17)
    unchanged_feasibility = _snapshot(
        [], [action, {"action_type": "end_turn", "is_valid": True}],
        cities=[accumulating], source_seq=2, turn=5)
    assert not any(
        candidate.category == "city_food_governor"
        for candidate in planner.candidates(unchanged_feasibility))
    assert planner.no_effect_retries_blocked == 1

    changed_output = dict(accumulating, surplus=[-1, 7, 5, 2, 0, 3])
    output_only = _snapshot(
        [], [action, {"action_type": "end_turn", "is_valid": True}],
        cities=[changed_output], source_seq=3, turn=6)
    assert not any(
        candidate.category == "city_food_governor"
        for candidate in planner.candidates(output_only))

    grown = dict(changed_output, size=5)
    topology_changed = _snapshot(
        [], [action, {"action_type": "end_turn", "is_valid": True}],
        cities=[grown], source_seq=4, turn=7)
    assert any(
        candidate.category == "city_food_governor"
        for candidate in planner.candidates(topology_changed))


def test_net_gold_does_not_double_subtract_city_style_unit_upkeep():
    snapshot = _snapshot(
        [_unit(
            20, "Explorer", homecity=10,
            upkeep=(0, 0, 0, 3, 0, 0))],
        [{"action_type": "end_turn", "is_valid": True}],
        city_surplus=(2, 5, 2, -2, 0, 3),
        player={
            "gold": 20, "city_gold_surplus_per_turn": -2,
            "gold_per_turn": -2, "unit_gold_upkeep": 3,
            "gold_upkeep_reserve": 3, "gold_upkeep_style": "City",
        })

    assert GroundedImpactPlanner()._net_gold_per_turn(snapshot) == -2


def test_food_support_can_be_rehomed_to_a_city_with_exact_reserve():
    home = _city(surplus=(0, 5, 2, 1, 0, 3))
    target = dict(
        _city(surplus=(3, 5, 2, 1, 0, 3)),
        id=20, name="Antium", x=2, y=0, tile=2)
    rehome = {
        "action_type": "unit_home_city", "actor_id": 20,
        "target": {"city_id": 20}, "is_valid": True,
    }
    snapshot = _snapshot(
        [_unit(
            20, "Explorer", x=2, y=0, homecity=10,
            upkeep=(1, 0, 0, 0, 0, 0))],
        [rehome, {"action_type": "end_turn", "is_valid": True}],
        cities=[home, target])

    decision = GroundedImpactPlanner(
        {"expansion_city_target": 2}).plan(snapshot)

    assert decision.candidate.category == "food_support_rehome"
    assert decision.candidate.projection["from_city_id"] == 10
    assert decision.candidate.projection["target_food_surplus_after"] == 2


def test_non_required_support_unit_can_be_disbanded_for_food_or_treasury():
    disband = {
        "action_type": "unit_disband", "actor_id": 20, "is_valid": True,
    }
    food_snapshot = _snapshot(
        [_unit(
            20, "Explorer", homecity=10,
            upkeep=(1, 0, 0, 0, 0, 0))],
        [disband, {"action_type": "end_turn", "is_valid": True}],
        city_surplus=(0, 5, 2, 1, 0, 3))
    food = GroundedImpactPlanner(
        {"expansion_city_target": 1}).plan(food_snapshot)
    assert food.candidate.category == "food_support_disband"
    assert food.candidate.terminal_on_accept

    treasury_snapshot = _snapshot(
        [_unit(
            20, "Explorer", homecity=10,
            upkeep=(0, 0, 0, 2, 0, 0))],
        [disband, {"action_type": "end_turn", "is_valid": True}],
        city_surplus=(2, 5, 2, 0, 0, 3),
        player={
            "gold": 0, "city_gold_surplus_per_turn": 0,
            "gold_per_turn": -2, "unit_gold_upkeep": 2,
            "gold_upkeep_reserve": 2,
        })
    treasury = GroundedImpactPlanner(
        {"expansion_city_target": 1}).plan(treasury_snapshot)
    assert treasury.candidate.category == "treasury_support_disband"
    assert treasury.candidate.projection["net_gold_per_turn_after"] == 0


def test_packet_legal_tax_shift_recovers_and_then_restores_science_rate():
    increase_tax = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 50, "science_rate": 50, "luxury_rate": 0,
        }, "is_valid": True,
    }
    unsafe = _snapshot(
        [], [increase_tax, {"action_type": "end_turn", "is_valid": True}],
        player={
            "gold": 0, "city_gold_surplus_per_turn": 1,
            "gold_per_turn": 1, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
        })
    recovery = GroundedImpactPlanner().plan(unsafe)
    assert recovery.candidate.category == "treasury_tax_shift"
    assert recovery.candidate.action["target"]["tax_rate"] == 50

    unsafe_luxury_sacrifice = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 50, "science_rate": 30, "luxury_rate": 20,
        }, "is_valid": True,
    }
    protected_luxury = _snapshot(
        [], [unsafe_luxury_sacrifice,
             {"action_type": "end_turn", "is_valid": True}],
        player={
            "gold": 0, "city_gold_surplus_per_turn": 1,
            "gold_per_turn": 1, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
            "tax": 40, "science": 30, "luxury": 30,
        })
    assert GroundedImpactPlanner().plan(protected_luxury) is None

    restore_science = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 40, "science_rate": 60, "luxury_rate": 0,
        }, "is_valid": True,
    }
    safe = _snapshot(
        [], [restore_science, {"action_type": "end_turn", "is_valid": True}],
        player={
            "gold": 20, "city_gold_surplus_per_turn": 1,
            "gold_per_turn": 1, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
            "tax": 50, "science": 50,
        })
    restored = GroundedImpactPlanner().plan(safe)
    assert restored.candidate.category == "treasury_tax_restore"
    assert restored.candidate.action["target"]["science_rate"] == 60


def test_tax_restore_requires_post_restore_structural_runway():
    restore_science = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 50, "science_rate": 50, "luxury_rate": 0,
        }, "is_valid": True,
    }
    snapshot = _snapshot(
        [], [restore_science, {"action_type": "end_turn", "is_valid": True}],
        player={
            "gold": 100, "gold_per_turn": 10,
            "operating_gold_per_turn": -20,
            "capitalization_gold_per_turn": 30,
            "city_gold_surplus_per_turn": -20,
            "unit_gold_upkeep": 30, "gold_upkeep_reserve": 30,
            "tax": 60, "science": 40, "luxury": 0,
        })
    planner = GroundedImpactPlanner()
    action = next(
        json.loads(row) for row in snapshot.legal_action_json
        if json.loads(row)["action_type"] == "player_rates")

    assert planner._project_operating_gold_for_tax_rate(
        snapshot, 50) == -22
    assert planner._rate_recovery_candidate(snapshot, action) is None


def test_tax_recovery_holds_learned_floor_until_economy_structure_changes():
    increase_tax = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 50, "science_rate": 50, "luxury_rate": 0,
        }, "is_valid": True,
    }
    restore_science = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 40, "science_rate": 60, "luxury_rate": 0,
        }, "is_valid": True,
    }
    city = _city()
    planner = GroundedImpactPlanner({"expansion_city_target": 1})
    unsafe = _snapshot(
        [], [increase_tax, {"action_type": "end_turn", "is_valid": True}],
        cities=[city],
        player={
            "gold": 0, "city_gold_surplus_per_turn": 1,
            "gold_per_turn": 1, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
            "tax": 40, "science": 60, "luxury": 0,
        })
    planner.observe(unsafe)
    assert planner._minimum_safe_tax_rate == 50
    assert planner.plan(unsafe).candidate.category == "treasury_tax_shift"

    stable = _snapshot(
        [], [restore_science, {"action_type": "end_turn", "is_valid": True}],
        cities=[city], source_seq=2,
        player={
            "gold": 20, "city_gold_surplus_per_turn": 1,
            "gold_per_turn": 1, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
            "tax": 50, "science": 50, "luxury": 0,
        })
    planner.observe(stable)
    rate_action = next(
        json.loads(row) for row in stable.legal_action_json
        if json.loads(row)["action_type"] == "player_rates")
    assert planner._rate_recovery_candidate(stable, rate_action) is None
    assert planner._minimum_safe_tax_rate == 50

    grown_city = dict(city, size=int(city["size"]) + 1)
    reprobe = _snapshot(
        [], [restore_science, {"action_type": "end_turn", "is_valid": True}],
        cities=[grown_city], source_seq=3,
        player={
            "gold": 20, "city_gold_surplus_per_turn": 1,
            "gold_per_turn": 1, "unit_gold_upkeep": 0,
            "gold_upkeep_reserve": 0,
            "tax": 50, "science": 50, "luxury": 0,
        })
    planner.observe(reprobe)
    candidate = planner._rate_recovery_candidate(reprobe, rate_action)
    assert candidate.category == "treasury_tax_restore"
    assert candidate.projection["minimum_safe_tax_rate"] == 40


def test_packet_legal_luxury_shift_breaks_disorder_without_rate_oscillation():
    city = _city()
    city.update({
        "ppl_happy": [0], "ppl_content": [0],
        "ppl_unhappy": [2], "ppl_angry": [0],
        "disorder": True,
    })
    city["surplus"][1] = 0
    city["buildability"]["options"].append(
        {"type": "improvement", "id": 40, "name": "Temple"})
    recover_from_tax = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 50, "science_rate": 40, "luxury_rate": 10,
        }, "is_valid": True,
    }
    recover_from_science = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 60, "science_rate": 30, "luxury_rate": 10,
        }, "is_valid": True,
    }
    units = [
        _unit(11, "Alpine Troops"),
        _unit(12, "Alpine Troops"),
        _unit(13, "Alpine Troops"),
    ]
    disorder = _snapshot(
        units,
        [recover_from_tax, recover_from_science,
         {"action_type": "end_turn", "is_valid": True}],
        cities=[city],
        player={
            "gold": 100, "gold_per_turn": 1,
            "city_gold_surplus_per_turn": 1,
            "tax": 60, "science": 40, "luxury": 0,
        })
    planner = GroundedImpactPlanner({
        "disorder_luxury_recovery_enabled": True,
        "disorder_luxury_trigger_turns": 1,
        "disorder_luxury_minimum_city_size": 1,
    })
    planner.observe(disorder)

    recovery = planner.plan(disorder)

    assert recovery.candidate.category == "disorder_luxury_shift"
    assert recovery.candidate.action["target"] == recover_from_tax["target"]
    assert recovery.candidate.projection["disorder_city_ids"] == (10,)

    clear_city = dict(city, disorder=False)
    restore_science = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 50, "science_rate": 50, "luxury_rate": 0,
        }, "is_valid": True,
    }
    same_grounding = _snapshot(
        units,
        [restore_science, {"action_type": "end_turn", "is_valid": True}],
        cities=[clear_city], source_seq=2,
        player={
            "gold": 100, "gold_per_turn": 1,
            "city_gold_surplus_per_turn": 1,
            "tax": 50, "science": 40, "luxury": 10,
        })
    planner.observe(same_grounding)
    assert planner.plan(same_grounding) is None

    grounded_garrison_change = _snapshot(
        units + [_unit(14, "Alpine Troops")],
        [restore_science, {"action_type": "end_turn", "is_valid": True}],
        cities=[clear_city], source_seq=3,
        player={
            "gold": 100, "gold_per_turn": 1,
            "city_gold_surplus_per_turn": 1,
            "tax": 50, "science": 40, "luxury": 10,
        })
    planner.observe(grounded_garrison_change)
    restored = planner.plan(grounded_garrison_change)
    assert restored.candidate.category == "disorder_luxury_restore"
    assert restored.candidate.action["target"] == restore_science["target"]


def test_luxury_bridge_builds_local_happiness_exit_and_reprobes_safe_rate():
    city = _city(
        size=14, shield_stock=5, surplus=(0, 0, 21, -9, 0, 0),
        production_kind=6, production_value=10)
    city.update({
        "ppl_happy": [0], "ppl_content": [9],
        "ppl_unhappy": [5], "ppl_angry": [0],
        "disorder": True,
        "buildability": {"available": True, "options": [
            {"type": "unit", "id": 10, "name": "Riflemen"},
            {"type": "improvement", "id": 40, "name": "Temple"},
        ]},
        "built_improvements": [{
            "id": 11, "name": "Amphitheater", "upkeep": 3,
        }],
    })
    raise_from_tax = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 50, "science_rate": 40, "luxury_rate": 10,
        }, "is_valid": True,
    }
    raise_from_science = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 60, "science_rate": 30, "luxury_rate": 10,
        }, "is_valid": True,
    }
    temple = _production(10, "Temple", 3, 40)
    planner = GroundedImpactPlanner({
        "expansion_city_target": 1,
        "disorder_luxury_recovery_enabled": True,
        "disorder_luxury_trigger_turns": 1,
        "disorder_luxury_minimum_city_size": 1,
    }, ruleset_ir=_ruleset_ir((
        ("Riflemen", "unit", 40),
        ("Temple", "improvement", 30),
    )))
    blocked = _snapshot(
        [], [raise_from_tax, raise_from_science, temple,
             {"action_type": "end_turn", "is_valid": True}],
        cities=[city], turn=5,
        player={
            "gold": 100, "gold_per_turn": -10,
            "operating_gold_per_turn": -10,
            "city_gold_surplus_per_turn": -10,
            "tax": 60, "science": 40, "luxury": 0,
        })
    planner.observe(blocked)

    bridge = planner.plan(blocked)

    assert bridge.candidate.category == "disorder_luxury_shift"
    assert bridge.candidate.action["target"] == raise_from_science["target"]
    assert bridge.candidate.projection["bridge_city_ids"] == (10,)

    recovered_city = dict(city, disorder=False, surplus=[0, 4, 21, -4, 2, 5])
    recovered_city["ppl_unhappy"] = [0]
    recovered = _snapshot(
        [], [temple, {"action_type": "end_turn", "is_valid": True}],
        cities=[recovered_city], source_seq=2, turn=6,
        player={
            "gold": 90, "gold_per_turn": -5,
            "operating_gold_per_turn": -5,
            "city_gold_surplus_per_turn": -5,
            "tax": 60, "science": 30, "luxury": 10,
        })
    planner.observe(recovered)

    local_exit = planner.plan(recovered)

    assert local_exit.candidate.category == "production_happiness_recovery"
    assert local_exit.candidate.action == {
        key: value for key, value in temple.items() if key != "is_valid"}
    assert local_exit.candidate.projection[
        "missing_happiness_improvements"] == ("Temple",)

    building_city = dict(
        recovered_city, production_kind=3, production_value=40,
        shield_stock=4)
    restore = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 60, "science_rate": 40, "luxury_rate": 0,
        }, "is_valid": True,
    }
    unrelated_disorder = dict(
        _city(size=2, surplus=(0, 0, 2, 0, 0, 0)),
        id=20, name="Small", tile=22, x=2, y=2, disorder=True,
        ppl_happy=[0], ppl_content=[1], ppl_unhappy=[1], ppl_angry=[0])
    probing = _snapshot(
        [], [restore, {"action_type": "end_turn", "is_valid": True}],
        cities=[building_city, unrelated_disorder], source_seq=3, turn=7,
        player={
            "gold": 85, "gold_per_turn": -5,
            "operating_gold_per_turn": -5,
            "city_gold_surplus_per_turn": -5,
            "tax": 60, "science": 30, "luxury": 10,
        })
    planner.observe(probing)

    probe = planner.plan(probing)

    assert probe.candidate.category == "disorder_luxury_unwind"
    assert probe.candidate.action["target"] == restore["target"]
    assert probe.candidate.utility >= 2650.0

    blocked_again = _snapshot(
        [], [raise_from_science, {"action_type": "end_turn", "is_valid": True}],
        cities=[dict(building_city, disorder=True, surplus=[0, 0, 21, -9, 0, 0])],
        source_seq=4, turn=8,
        player={
            "gold": 80, "gold_per_turn": -10,
            "operating_gold_per_turn": -10,
            "city_gold_surplus_per_turn": -10,
            "tax": 60, "science": 40, "luxury": 0,
        })
    planner.observe(blocked_again)
    assert planner.plan(
        blocked_again).candidate.category == "disorder_luxury_shift"

    stable = _snapshot(
        [], [restore, {"action_type": "end_turn", "is_valid": True}],
        cities=[building_city], source_seq=5, turn=9,
        player={
            "gold": 75, "gold_per_turn": -5,
            "operating_gold_per_turn": -5,
            "city_gold_surplus_per_turn": -5,
            "tax": 60, "science": 30, "luxury": 10,
        })
    planner.observe(stable)
    assert planner.plan(stable) is None

    # Completing the local remedy changes the grounded happiness signature.
    # The previously learned unsafe boundary belongs to the pre-Temple city
    # and must not strand the economy at the emergency luxury rate.
    completed_city = dict(
        building_city, production_kind=6, production_value=10,
        built_improvements=[
            {"id": 11, "name": "Amphitheater", "upkeep": 3},
            {"id": 40, "name": "Temple", "upkeep": 1},
        ])
    completed = _snapshot(
        [], [restore, {"action_type": "end_turn", "is_valid": True}],
        cities=[completed_city], source_seq=6, turn=10,
        player={
            "gold": 70, "gold_per_turn": -5,
            "operating_gold_per_turn": -5,
            "city_gold_surplus_per_turn": -5,
            "tax": 60, "science": 30, "luxury": 10,
        })
    planner.observe(completed)
    completion_probe = planner.plan(completed)
    assert completion_probe.candidate.category == "disorder_luxury_unwind"
    assert completion_probe.candidate.action["target"] == restore["target"]
    assert completion_probe.candidate.projection[
        "minimum_safe_luxury_rate"] == 0


def test_luxury_bridge_ignores_transient_disorder_until_turn_persistence():
    city = _city(surplus=(0, 0, 12, -4, 0, 0))
    city.update({
        "ppl_happy": [0], "ppl_content": [4],
        "ppl_unhappy": [2], "ppl_angry": [0],
        "disorder": True,
    })
    city["buildability"]["options"].append(
        {"type": "improvement", "id": 40, "name": "Temple"})
    raise_luxury = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 40, "science_rate": 50, "luxury_rate": 10,
        }, "is_valid": True,
    }
    actions = [raise_luxury, {"action_type": "end_turn", "is_valid": True}]
    planner = GroundedImpactPlanner({
        "expansion_city_target": 1,
        "disorder_luxury_recovery_enabled": True,
        "disorder_luxury_trigger_turns": 3,
        "disorder_luxury_minimum_city_size": 1,
    })

    for source_seq, turn in ((1, 5), (2, 6)):
        snapshot = _snapshot(
            [], actions, cities=[city], source_seq=source_seq, turn=turn)
        planner.observe(snapshot)
        assert planner.plan(snapshot) is None

    persistent = _snapshot(
        [], actions, cities=[city], source_seq=3, turn=7)
    planner.observe(persistent)

    assert planner.plan(
        persistent).candidate.category == "disorder_luxury_shift"


def test_luxury_bridge_expires_instead_of_permanently_starving_science():
    city = _city(
        size=14, surplus=(0, 0, 21, -9, 0, 0),
        production_kind=6, production_value=10)
    city.update({
        "ppl_happy": [0], "ppl_content": [9],
        "ppl_unhappy": [5], "ppl_angry": [0],
        "disorder": True,
        "buildability": {"available": True, "options": [
            {"type": "improvement", "id": 40, "name": "Temple"},
        ]},
    })
    planner = GroundedImpactPlanner({
        "expansion_city_target": 1,
        "disorder_luxury_recovery_enabled": True,
        "disorder_luxury_trigger_turns": 1,
        "disorder_luxury_minimum_city_size": 1,
        "disorder_luxury_bridge_max_turns": 1,
    }, ruleset_ir=_ruleset_ir((("Temple", "improvement", 30),)))
    start = _snapshot(
        [], [{"action_type": "end_turn", "is_valid": True}],
        cities=[city], turn=5)
    planner.observe(start)
    restore = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 50, "science_rate": 40, "luxury_rate": 10,
        }, "is_valid": True,
    }
    changed_signature_city = dict(
        city, size=15, production_kind=3, production_value=40)
    expired = _snapshot(
        [], [restore, {"action_type": "end_turn", "is_valid": True}],
        cities=[changed_signature_city], source_seq=2, turn=6,
        player={"tax": 40, "science": 40, "luxury": 20})
    planner.observe(expired)

    decision = planner.plan(expired)

    assert decision.candidate.category == "disorder_luxury_unwind"
    assert decision.candidate.projection["bridge_expired"] is True


def test_disordered_city_uses_local_happiness_governor_before_global_rates():
    city = _city(surplus=(0, 0, 0, 1, 0, 3))
    city.update({
        "ppl_happy": [0], "ppl_content": [0],
        "ppl_unhappy": [2], "ppl_angry": [0],
        "disorder": True,
        "governor": {
            "available": True, "enabled": False,
            "minimal_surplus": [0, 0, 0, 0, 0, 0],
            "require_happy": False, "allow_disorder": False,
            "max_growth": False, "allow_specialists": True,
            "factor": [0, 0, 0, 0, 0, 0], "happy_factor": 0,
        },
    })
    local = {
        "type": "city_governor", "city_id": 10,
        "target": {
            "food_surplus_reserve": 0,
            "require_happy": True,
        },
        "is_valid": True,
    }
    global_luxury = {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "tax_rate": 30, "science_rate": 60, "luxury_rate": 10,
        },
        "is_valid": True,
    }
    before = _snapshot(
        [], [local, global_luxury,
             {"action_type": "end_turn", "is_valid": True}],
        cities=[city])
    planner = GroundedImpactPlanner({
        "expansion_city_target": 1,
        "pressure_enabled": True,
        "city_happiness_governor_enabled": True,
    })

    decision = planner.plan(before)

    assert decision.candidate.category == "city_happiness_governor"
    assert decision.candidate.action == {
        "action_type": "city_governor", "city_id": 10,
        "target": {
            "food_surplus_reserve": 0,
            "require_happy": True,
        },
    }
    rate_action = next(
        json.loads(row) for row in before.legal_action_json
        if json.loads(row)["action_type"] == "player_rates")
    assert planner._rate_recovery_candidate(before, rate_action) is None

    recovered_city = dict(city, disorder=False)
    recovered_city["governor"] = {
        "available": True, "enabled": True,
        "minimal_surplus": [0, 0, 0, 0, 0, 0],
        "require_happy": True, "allow_disorder": False,
        "max_growth": False, "allow_specialists": True,
        "factor": [6, 2, 2, 1, 1, 2], "happy_factor": 0,
    }
    after = _snapshot(
        [], [local, {"action_type": "end_turn", "is_valid": True}],
        cities=[recovered_city], source_seq=2)
    assert planner.candidate_effect_observed(
        decision.candidate, before, after) is True
    assert planner.candidate_goal_relief(
        decision.candidate, before, after, effect_observed=True
    ).goal == "survival"
    assert planner._city_food_governor_candidate(
        after, decision.candidate.action) is None


def test_sole_city_garrison_cannot_attack_but_a_spare_can():
    attack = {
        "action_type": "unit_attack", "actor_id": 11,
        "target": {"x": 1, "y": 0}, "is_valid": True,
    }
    enemy = _enemy(99, "Warriors", 1, 0)
    sole = _snapshot(
        [_unit(11, "Alpine Troops"), enemy],
        [attack, {"action_type": "end_turn", "is_valid": True}])
    assert GroundedImpactPlanner().plan(sole) is None

    spare = _snapshot(
        [_unit(10, "Alpine Troops"), _unit(11, "Alpine Troops"), enemy],
        [attack, {"action_type": "end_turn", "is_valid": True}])
    assert GroundedImpactPlanner().plan(
        spare).candidate.category == "tactical_attack"


def test_spare_combat_unit_routes_toward_exact_uncovered_city():
    second = dict(_city(), id=20, name="Antium", tile=30, x=0, y=3)
    move = {
        "action_type": "unit_move", "actor_id": 12,
        "target": {"x": 0, "y": 1}, "is_valid": True,
    }
    snapshot = _snapshot(
        [_unit(11, "Alpine Troops"), _unit(12, "Alpine Troops")],
        [move, {"action_type": "end_turn", "is_valid": True}],
        cities=[_city(), second])

    decision = GroundedImpactPlanner(
        {"expansion_city_target": 2}).plan(snapshot)

    assert decision.candidate.category == "city_garrison_move"
    assert decision.candidate.projection["target_city_ids"] == (20,)
