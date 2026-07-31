"""Grounded city-threat analysis and exact defender assignment."""

import itertools
import os
import sys
import tempfile
from dataclasses import replace
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import ImpactCandidate  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.execution import ActionOutcome  # noqa: E402
from freeciv_agent.planning import ControlEventEmitter  # noqa: E402
from freeciv_agent.planning.domain_models import (  # noqa: E402
    CityDefenseAnalysis,
    CityDefenseAnalyzer,
    CityDefenseOperation,
    CityDefenseRequirement,
    DefenseOperationType,
    ExactCityDefenseAssignmentSolver,
    build_city_defense_assignment_artifact,
    grounded_operation_result,
    grounded_threat_result,
)
from freeciv_agent.state import MovementRouteState  # noqa: E402
from freeciv_agent.pressure.resource_claims import (  # noqa: E402
    ClaimHardness,
    GameResourceKind,
    ResourceClaim,
    ResourceRef,
    TurnWindow,
)


def _rule(
        name, attack, defense, hp=10,
        unit_class="Land", flags=()):
    return SimpleNamespace(
        target_kind="unit",
        display_name=name,
        rule_name=name,
        rule_id="unit:{}".format(name),
        quantitative={
            "attack": {"value": attack},
            "defense": {"value": defense},
            "hitpoints": {"value": hp},
            "build_cost": {"value": 10},
            "move_rate": {"value": 3},
        },
        traits={
            "class": {
                "values": [unit_class],
            },
            "flags": {
                "values": list(flags),
            },
            "roles": {
                "values": [],
            },
        })


def _unit(
        unit_id, unit_type, x, y,
        owner=1, hp=10):
    return SimpleNamespace(
        unit_id=unit_id,
        unit_type=unit_type,
        x=x, y=y, owner=owner,
        hp=hp)


def _city(city_id, x, y, size=3):
    return SimpleNamespace(
        city_id=city_id, tile=x + y * 12,
        x=x, y=y, size=size)


def _candidate(
        action, category,
        projection=None,
        utility=900.0):
    return ImpactCandidate(
        action=dict(action),
        category=category,
        utility=utility,
        rationale="test",
        projection=projection)


def _scenario(
        candidates,
        rules=True,
        include_actions=True):
    own = (
        _unit(1, "Guard", 0, 0),
        _unit(2, "Guard", 2, 0),
        _unit(3, "Guard", 2, 1),
    )
    enemy = (
        _unit(
            90, "Raider", 4, 3,
            owner=2),)
    legal = (
        tuple(
            candidate.action_key
            for candidate in candidates)
        if include_actions else ())
    snapshot = SimpleNamespace(
        snapshot_id="defence-snapshot",
        player_id=1,
        turn=10,
        map_width=12,
        map_height=12,
        map_wrap_x=False,
        map_wrap_y=False,
        map_topology_id=0,
        map_tiles=tuple(
            {
                "index":
                    x + y * 12,
                "x": x,
                "y": y,
                "terrain_class":
                    "land",
                "terrain_name":
                    "Test land",
                "native_unit_classes": [
                    "Land",
                ],
            }
            for y in range(12)
            for x in range(12)),
        cities=(
            _city(10, 0, 0),
            _city(20, 4, 0)),
        units=own,
        visible_enemy_units=enemy,
        movement_routes=(),
        legal_action_json=legal,
        legal_actions_digest="legal")
    ruleset = SimpleNamespace(
        rules=(
            _rule("Guard", 4, 6),
            _rule("Raider", 8, 3),
        ) if rules else ())
    return snapshot, ruleset


def _candidates():
    return (
        _candidate({
            "action_type": "unit_fortify",
            "actor_id": 1,
            "is_valid": True,
        }, "city_defense"),
        _candidate({
            "action_type": "unit_move",
            "actor_id": 1,
            "target": {"x": 1, "y": 0},
            "is_valid": True,
        }, "city_garrison_move", {
            "target_city_ids": (20,),
        }),
        _candidate({
            "action_type": "unit_move",
            "actor_id": 2,
            "target": {"x": 4, "y": 0},
            "movement_cost": 1,
            "is_valid": True,
        }, "city_garrison_move", {
            "target_city_ids": (20,),
        }),
        _candidate({
            "action_type": "unit_move",
            "actor_id": 3,
            "target": {"x": 4, "y": 0},
            "movement_cost": 1,
            "is_valid": True,
        }, "city_garrison_move", {
            "target_city_ids": (20,),
        }),
    )


def _requirement(city_id):
    return CityDefenseRequirement(
        city_id=city_id,
        city_position=(city_id, 0),
        current_defenders=0,
        required_defenders=1,
        response_slots=1,
        deadline_turn=2,
        threat_ids=(
            "threat-{}".format(city_id),),
        threat_priority=100.0,
        confidence=1.0)


def _operation(
        operation_id, requirement,
        actor_id, bid):
    claim = ResourceClaim(
        resource=ResourceRef(
            kind=GameResourceKind.ACTOR,
            owner_id="unit:{}".format(
                actor_id),
            subresource="whole_actor",
            scope="player:1"),
        quantity=1,
        window=TurnWindow(1, 2),
        hardness=ClaimHardness.HARD_CURRENT,
        exclusive=True,
        source_operation_id=operation_id,
        source_step_id="move")
    return CityDefenseOperation(
        operation_id=operation_id,
        operation_type=(
            DefenseOperationType
            .MOVE_DEFENDER_TO_CITY),
        requirement_id=(
            requirement.requirement_id),
        city_id=requirement.city_id,
        actor_id=actor_id,
        next_action={
            "action_type": "unit_move",
            "actor_id": actor_id,
            "is_valid": True,
        },
        arrival_turn=1,
        deadline_turn=2,
        expected_prevented_loss=bid,
        opportunity_cost=0.0,
        bid=bid,
        claims=(claim,),
        support_reason=None,
        provenance=("exhaustive-test",))


def _analysis(requirements, operations):
    return CityDefenseAnalysis(
        snapshot_id="assignment-test",
        threats=(),
        requirements=tuple(requirements),
        defenders=(),
        operations=tuple(operations),
        omissions=(),
        analyzer_identity="assignment-test")


def test_grounded_operation_result_separates_negative_facts_from_unknowns():
    requirement = _requirement(
        10)
    supported = _operation(
        "supported", requirement,
        1, 10.0)
    late = replace(
        supported,
        operation_id="late",
        support_reason=(
            "arrival-after-threat-deadline"),
        claims=tuple(
            replace(
                claim,
                source_operation_id="late")
            for claim in
            supported.claims))
    unknown = replace(
        supported,
        operation_id="unknown",
        support_reason=(
            "defender-route-eta-unavailable"),
        claims=tuple(
            replace(
                claim,
                source_operation_id="unknown")
            for claim in
            supported.claims))

    assert grounded_operation_result(
        supported)
    assert grounded_operation_result(
        late)
    assert not grounded_operation_result(
        unknown)


def _brute_force_optimum(requirements, operations):
    capacity = {
        row.requirement_id:
        row.response_slots
        for row in requirements}
    best = (-1, -1.0, ())
    for size in range(
            len(operations) + 1):
        for selected in itertools.combinations(
                operations, size):
            actors = [
                row.actor_id
                for row in selected]
            if len(actors) != len(
                    set(actors)):
                continue
            requirement_counts = {}
            for row in selected:
                requirement_counts[
                    row.requirement_id] = (
                        requirement_counts.get(
                            row.requirement_id,
                            0) + 1)
            if any(
                    count > capacity.get(
                        requirement_id, 0)
                    for requirement_id, count
                    in requirement_counts.items()):
                continue
            ids = tuple(sorted(
                row.operation_id
                for row in selected))
            candidate = (
                len(selected),
                sum(
                    row.bid
                    for row in selected),
                ids)
            if (candidate[0] > best[0]
                    or (
                        candidate[0] == best[0]
                        and candidate[1]
                        > best[1] + 1e-12)
                    or (
                        candidate[0] == best[0]
                        and abs(
                            candidate[1]
                            - best[1])
                        <= 1e-12
                        and (
                            not best[2]
                            or candidate[2]
                            < best[2]))):
                best = candidate
    return best


def test_visible_threats_have_explicit_unknown_mass_and_deadlines():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)

    assert len(analysis.threats) == 2
    assert {
        row.city_id
        for row in analysis.threats
    } == {10, 20}
    assert all(
        row.confidence == 0.45
        and row.unknown_mass == 0.55
        and row.supported
        and row.movement_rate == 3.0
        and row.eta_basis
        == "ruleset-move-rate-geometric-lower-bound"
        and row.reachability_status
        == "reachable"
        and row.reachability_basis
        == "player-known-native-terrain-corridor"
        for row in analysis.threats)
    assert {
        row.city_id:
        row.deadline_turn
        for row in analysis.requirements
    } == {
        10: 11,
        20: 11,
    }


def test_missing_enemy_move_rate_cannot_authorize_a_threat_deadline():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)
    enemy_rule = next(
        row for row in ruleset.rules
        if row.display_name
        == "Raider")
    enemy_rule.quantitative[
        "move_rate"] = {
            "value": None,
        }

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)

    assert analysis.threats
    assert all(
        row.movement_rate is None
        and row.eta_basis
        == "unsupported-unit-step-fallback"
        and row.support_reason
        == "enemy-move-rate-unavailable"
        and not row.supported
        for row in analysis.threats)
    assert analysis.requirements == ()


def test_unknown_native_terrain_corridor_abstains_from_threat_reachability():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)
    snapshot.map_tiles = ()

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)

    assert analysis.threats
    assert all(
        row.reachability_status
        == "unknown"
        and row.support_reason
        == "source-terrain-semantics-unavailable"
        and not row.supported
        for row in analysis.threats)
    assert analysis.requirements == ()


def test_complete_native_terrain_barrier_proves_threat_unreachable():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)
    blocked = {
        (3, 2), (4, 2), (5, 2),
        (3, 3), (5, 3),
        (3, 4), (4, 4), (5, 4),
    }
    snapshot.map_tiles = tuple(
        {
            **tile,
            "native_unit_classes": (
                []
                if (
                    tile["x"],
                    tile["y"])
                in blocked
                else ["Land"]),
        }
        for tile in
        snapshot.map_tiles)

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)

    assert analysis.threats
    assert all(
        row.reachability_status
        == "unreachable"
        and row.support_reason
        == "known-native-corridor-unreachable"
        and not row.supported
        for row in analysis.threats)
    assert analysis.requirements == ()


def test_locally_known_non_native_city_approach_proves_unreachable():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)
    snapshot.cities = (
        _city(20, 4, 0),)
    snapshot.visible_enemy_units = (
        _unit(
            90, "Raider", 4, 3,
            owner=2),)
    approaches = {
        (3, 0), (3, 1),
        (4, 1), (5, 0), (5, 1),
    }
    snapshot.map_tiles = tuple(
        {
            "index": x + y * 12,
            "x": x,
            "y": y,
            "terrain_class":
                "ocean"
                if (x, y) in approaches
                else "land",
            "terrain_name":
                "Test terrain",
            "native_unit_classes": (
                []
                if (x, y) in approaches
                else ["Land"]),
        }
        for x, y in (
            {(4, 3)}
            | approaches))

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)

    assert len(analysis.threats) == 1
    threat = analysis.threats[0]
    assert threat.reachability_status == (
        "unreachable")
    assert threat.reachability_basis == (
        "known-native-city-approach-unreachable")
    assert grounded_threat_result(
        threat)
    assert analysis.requirements == ()


def test_unknown_city_approach_keeps_reachability_unknown():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)
    snapshot.cities = (
        _city(20, 4, 0),)
    snapshot.visible_enemy_units = (
        _unit(
            90, "Raider", 4, 3,
            owner=2),)
    snapshot.map_tiles = ({
        "index": 4 + 3 * 12,
        "x": 4,
        "y": 3,
        "terrain_class": "land",
        "terrain_name": "Test land",
        "native_unit_classes": [
            "Land",
        ],
    },)

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)

    assert len(analysis.threats) == 1
    threat = analysis.threats[0]
    assert threat.reachability_status == (
        "unknown")
    assert threat.reachability_basis == (
        "city-approach-semantics-unavailable")
    assert not grounded_threat_result(
        threat)
    assert analysis.requirements == ()


def test_hex_topology_uses_freeciv_native_coordinate_adjacency():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)
    snapshot.map_topology_id = 3
    snapshot.cities = (
        _city(10, 0, 0),)
    snapshot.visible_enemy_units = (
        _unit(
            500, "Raider",
            0, 2, owner=2),)
    snapshot.map_tiles = tuple(
        {
            **tile,
            "native_unit_classes": [
                "Land",
            ],
        }
        for tile in
        snapshot.map_tiles)

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)

    assert len(analysis.threats) == 1
    assert analysis.threats[
        0].reachability_status == (
            "reachable")
    assert analysis.threats[
        0].reachability_basis == (
            "visible-adjacent-threat")


def test_sole_defender_is_a_protected_constraint_not_a_movable_asset():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)
    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)

    defender = next(
        row for row in analysis.defenders
        if row.unit_id == 1)
    protected_move = next(
        row for row in analysis.operations
        if row.actor_id == 1
        and row.operation_type
        == DefenseOperationType
        .MOVE_DEFENDER_TO_CITY)
    hold = next(
        row for row in analysis.operations
        if row.actor_id == 1
        and row.operation_type
        == DefenseOperationType
        .HOLD_SOLE_DEFENDER)

    assert defender.protected_sole_defender
    assert not protected_move.supported
    assert protected_move.support_reason == (
        "protected-sole-defender")
    assert hold.supported
    assert hold.next_action is None


def test_exact_assignment_covers_threat_slots_without_actor_conflicts():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)
    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)

    assignment = (
        ExactCityDefenseAssignmentSolver()
        .schedule(analysis))
    selected = [
        row for row in analysis.operations
        if row.operation_id
        in assignment
        .selected_operation_ids]

    assert assignment.status == "exact"
    assert assignment.covered_slots == 3
    assert assignment.uncovered_slots == 0
    assert len({
        row.actor_id
        for row in selected
        if row.actor_id is not None
    }) == len(selected)
    assert {
        row.actor_id
        for row in selected
    } == {1, 2, 3}
    assert all(
        row.next_action is not None
        for row in selected)
    assert not any(
        row.actor_id == 1
        and row.city_id == 20
        for row in selected)


def test_operation_claims_use_stable_operation_identity_and_typed_movement():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)
    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)
    movement = next(
        row for row in analysis.operations
        if row.actor_id == 2)

    assert all(
        claim.source_operation_id
        == movement.operation_id
        for claim in movement.claims)
    assert {
        claim.resource.kind.value
        for claim in movement.claims
    } == {"actor", "move_points"}
    assert next(
        claim for claim in movement.claims
        if claim.resource.kind.value
        == "move_points"
    ).hardness.value == "hard_current"


def test_unknown_ruleset_support_abstains_from_assignment():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates, rules=False)

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)
    assignment = (
        ExactCityDefenseAssignmentSolver()
        .schedule(analysis))

    assert analysis.threats
    assert all(
        not row.supported
        and row.unknown_mass == 1.0
        for row in analysis.threats)
    assert analysis.requirements == ()
    assert assignment.selected_operation_ids == ()
    assert assignment.uncovered_slots == 0


def test_non_military_visible_unit_does_not_create_defense_requirement():
    candidates = _candidates()
    snapshot, _ = _scenario(
        candidates)
    snapshot.visible_enemy_units = (
        _unit(
            90, "Ferry", 4, 3,
            owner=2),)
    ruleset = SimpleNamespace(
        rules=(
            _rule("Guard", 4, 6),
            _rule(
                "Ferry", 0, 1,
                unit_class="Sea",
                flags=("NonMil",)),
        ))

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)

    assert analysis.threats == ()
    assert analysis.requirements == ()
    assert analysis.omissions == (
        "enemy:90:not-combat-capable",)


def test_existing_garrison_surplus_is_not_an_uncovered_response_slot():
    candidates = _candidates() + (
        _candidate({
            "action_type":
                "unit_attack",
            "actor_id": 1,
            "target": {
                "x": 4,
                "y": 3,
            },
            "is_valid": True,
        }, "tactical_attack"),)
    snapshot, ruleset = _scenario(
        candidates)
    snapshot.units = (
        snapshot.units
        + (
            _unit(
                4, "Guard", 0, 0),
            _unit(
                5, "Guard", 4, 0),
            _unit(
                6, "Guard", 4, 0),
        ))

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)

    assert analysis.threats
    assert analysis.requirements == ()
    assert analysis.operations == ()


def test_category_independent_direct_city_move_forms_supported_edge():
    move = _candidate({
        "action_type": "unit_move",
        "actor_id": 2,
        "target": {"x": 4, "y": 0},
        "movement_cost": 1,
        "is_valid": True,
    }, "tactical_move")
    snapshot, ruleset = _scenario(
        (move,))

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        (move,))
    operation = next(
        row for row
        in analysis.operations
        if row.actor_id == 2)

    assert operation.supported
    assert operation.operation_type == (
        DefenseOperationType
        .MOVE_DEFENDER_TO_CITY)
    assert operation.arrival_turn == (
        snapshot.turn)


def test_complete_legal_set_forms_protected_defense_candidate_union():
    move = _candidate({
        "action_type": "unit_move",
        "actor_id": 2,
        "target": {"x": 4, "y": 0},
        "movement_cost": 1,
        "is_valid": True,
    }, "tactical_move")
    snapshot, ruleset = _scenario(
        ())
    snapshot.legal_action_json = (
        move.action_key,)

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        ())
    operation = next(
        row for row
        in analysis.operations
        if row.actor_id == 2)

    assert analysis.input_candidate_count == 0
    assert (
        analysis
        .protected_union_added_count
    ) == 1
    assert operation.supported
    assert (
        "protected-legal-action-union"
        in operation.provenance)


def test_multi_turn_defender_route_abstains_without_grounded_eta():
    move = _candidate({
        "action_type": "unit_move",
        "actor_id": 2,
        "target": {"x": 3, "y": 0},
        "movement_cost": 1,
        "is_valid": True,
    }, "tactical_move")
    snapshot, ruleset = _scenario(
        (move,))

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        (move,))
    operation = next(
        row for row
        in analysis.operations
        if row.actor_id == 2
        and row.city_id == 20)

    assert not operation.supported
    assert operation.support_reason == (
        "defender-route-eta-unavailable")


def test_native_route_eta_supports_multi_turn_defender_operation():
    move = _candidate({
        "action_type": "unit_move",
        "actor_id": 2,
        "target": {"x": 3, "y": 0},
        "movement_cost": 1,
        "transport_required": False,
        "is_valid": True,
    }, "tactical_move")
    snapshot, ruleset = _scenario(
        (move,))
    snapshot.movement_routes = (
        MovementRouteState(
            unit_id=2,
            origin_tile=2,
            destination_tile=4,
            reachable=True,
            first_step_tile=3,
            first_step_movement_cost=1,
            path_length=2,
            path_directions=(4, 4),
            estimated_turns=1,
            total_movement_cost=4,
            movement_points_remaining=2,
            moves_left_at_request=3,
            transported_at_request=False,
            initially_transported=False,
            turn=10,
            source_seq=10),)

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        (move,))
    operation = next(
        row for row
        in analysis.operations
        if row.actor_id == 2
        and row.city_id == 20)

    assert operation.supported
    assert operation.arrival_turn == 11
    assert "native-server-route-eta" in (
        operation.provenance)


def test_native_late_route_bounds_an_alternate_first_step():
    move = _candidate({
        "action_type": "unit_move",
        "actor_id": 2,
        "target": {"x": 3, "y": 0},
        "movement_cost": 1,
        "transport_required": False,
        "is_valid": True,
    }, "tactical_move")
    snapshot, ruleset = _scenario(
        (move,))
    snapshot.movement_routes = (
        MovementRouteState(
            unit_id=2,
            origin_tile=2,
            destination_tile=4,
            reachable=True,
            first_step_tile=14,
            first_step_movement_cost=1,
            path_length=3,
            path_directions=(6, 1, 1),
            estimated_turns=2,
            total_movement_cost=7,
            movement_points_remaining=2,
            moves_left_at_request=3,
            transported_at_request=False,
            initially_transported=False,
            turn=10,
            source_seq=10),)

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        (move,))
    operation = next(
        row for row
        in analysis.operations
        if row.actor_id == 2
        and row.city_id == 20)

    assert not operation.supported
    assert operation.arrival_turn == 12
    assert operation.support_reason == (
        "native-route-misses-threat-deadline")
    assert (
        "native-server-route-deadline-bound"
        in operation.provenance)


def test_native_selected_route_excludes_an_early_alternate_step():
    alternate = _candidate({
        "action_type": "unit_move",
        "actor_id": 2,
        "target": {"x": 3, "y": 0},
        "movement_cost": 1,
        "transport_required": False,
        "is_valid": True,
    }, "tactical_move")
    selected = _candidate({
        "action_type": "unit_move",
        "actor_id": 2,
        "target": {"x": 3, "y": 1},
        "movement_cost": 1,
        "transport_required": False,
        "is_valid": True,
    }, "tactical_move")
    snapshot, ruleset = _scenario(
        (alternate, selected))
    snapshot.movement_routes = (
        MovementRouteState(
            unit_id=2,
            origin_tile=2,
            destination_tile=4,
            reachable=True,
            first_step_tile=15,
            first_step_movement_cost=1,
            path_length=2,
            path_directions=(6, 1),
            estimated_turns=1,
            total_movement_cost=3,
            movement_points_remaining=0,
            moves_left_at_request=3,
            transported_at_request=False,
            initially_transported=False,
            turn=10,
            source_seq=10),)

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        (alternate, selected))
    alternate_operation = next(
        row for row
        in analysis.operations
        if row.actor_id == 2
        and row.city_id == 20
        and row.next_action
        == alternate.action)
    selected_operation = next(
        row for row
        in analysis.operations
        if row.actor_id == 2
        and row.city_id == 20
        and row.next_action
        == selected.action)

    assert not alternate_operation.supported
    assert alternate_operation.support_reason == (
        "alternate-step-not-native-selected-route")
    assert (
        "native-server-selected-route-dominates-alternate"
        in alternate_operation.provenance)
    assert selected_operation.supported


def test_native_unreachable_route_rejects_geometric_progress():
    move = _candidate({
        "action_type": "unit_move",
        "actor_id": 2,
        "target": {"x": 3, "y": 0},
        "movement_cost": 1,
        "transport_required": False,
        "is_valid": True,
    }, "tactical_move")
    snapshot, ruleset = _scenario(
        (move,))
    snapshot.movement_routes = (
        MovementRouteState(
            unit_id=2,
            origin_tile=2,
            destination_tile=4,
            reachable=False,
            first_step_tile=None,
            first_step_movement_cost=None,
            path_length=0,
            path_directions=(),
            estimated_turns=None,
            total_movement_cost=None,
            movement_points_remaining=None,
            moves_left_at_request=3,
            transported_at_request=False,
            initially_transported=False,
            turn=10,
            source_seq=10),)

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        (move,))
    operation = next(
        row for row
        in analysis.operations
        if row.actor_id == 2
        and row.city_id == 20)

    assert not operation.supported
    assert operation.support_reason == (
        "defender-native-route-unreachable")
    assert (
        "native-server-route-unreachable"
        in operation.provenance)


def test_unadvertised_candidate_cannot_form_an_operation():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates,
        include_actions=False)

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)

    assert not any(
        row.next_action is not None
        for row in analysis.operations)
    assert sum(
        value.startswith(
            "candidate-not-in-legal-set:")
        for value in analysis.omissions
    ) == len(candidates)
    assert all(
        not row.interception_legal
        for row in analysis.threats)


def test_late_emergency_build_is_not_counted_as_present_defense():
    build = _candidate({
        "action_type": "city_production",
        "city_id": 20,
        "production_kind": 1,
        "production_value": 5,
        "is_valid": True,
    }, "production_defense", {
        "completion_eta_turns": 5,
    })
    candidates = _candidates() + (
        build,)
    snapshot, ruleset = _scenario(
        candidates)
    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)
    production = next(
        row for row in analysis.operations
        if row.operation_type
        == DefenseOperationType
        .EMERGENCY_BUILD_DEFENDER)
    assignment = (
        ExactCityDefenseAssignmentSolver()
        .schedule(analysis))

    assert not production.supported
    assert production.support_reason == (
        "arrival-after-threat-deadline")
    assert production.operation_id not in (
        assignment
        .selected_operation_ids)


def test_unknown_emergency_build_eta_remains_epistemically_unresolved():
    build = _candidate({
        "action_type": "city_production",
        "city_id": 20,
        "production_kind": 1,
        "production_value": 5,
        "is_valid": True,
    }, "production_defense")
    candidates = _candidates() + (
        build,)
    snapshot, ruleset = _scenario(
        candidates)

    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)
    production = next(
        row for row in analysis.operations
        if row.operation_type
        == DefenseOperationType
        .EMERGENCY_BUILD_DEFENDER)

    assert not production.supported
    assert production.support_reason == (
        "production-completion-eta-unavailable")


def test_analysis_and_assignment_are_input_permutation_invariant():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)
    analyzer = CityDefenseAnalyzer()
    first = analyzer.analyze(
        snapshot, ruleset,
        candidates)
    second = analyzer.analyze(
        snapshot, ruleset,
        tuple(reversed(
            candidates)))

    first_assignment = (
        ExactCityDefenseAssignmentSolver()
        .schedule(first))
    second_assignment = (
        ExactCityDefenseAssignmentSolver()
        .schedule(second))

    assert first.analysis_digest == (
        second.analysis_digest)
    assert first_assignment.decision_digest == (
        second_assignment
        .decision_digest)


def test_node_budget_fallback_is_deterministic_and_attributable():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)
    analysis = CityDefenseAnalyzer().analyze(
        snapshot, ruleset,
        candidates)
    scheduler = (
        ExactCityDefenseAssignmentSolver(
            node_budget=1))

    first = scheduler.schedule(
        analysis)
    second = scheduler.schedule(
        analysis)

    assert first.status == (
        "greedy_fallback")
    assert first.fallback_reason == (
        "node-budget-exhausted")
    assert first.decision_digest == (
        second.decision_digest)
    assert all(
        row["reason"] is None
        if row["selected"]
        else bool(row["reason"])
        for row in first.entries)


def test_exact_assignment_avoids_known_greedy_coverage_failure():
    city_a = _requirement(10)
    city_b = _requirement(20)
    operations = (
        _operation(
            "actor-1-city-a",
            city_a, 1, 10.0),
        _operation(
            "actor-1-city-b",
            city_b, 1, 9.0),
        _operation(
            "actor-2-city-a",
            city_a, 2, 8.0),
    )
    analysis = _analysis(
        (city_a, city_b),
        operations)

    exact = (
        ExactCityDefenseAssignmentSolver()
        .schedule(analysis))
    greedy = (
        ExactCityDefenseAssignmentSolver(
            node_budget=1)
        .schedule(analysis))

    assert exact.status == "exact"
    assert exact.covered_slots == 2
    assert exact.objective_value == 17.0
    assert exact.selected_operation_ids == (
        "actor-1-city-b",
        "actor-2-city-a",
    )
    assert greedy.status == (
        "greedy_fallback")
    assert greedy.covered_slots == 1
    assert greedy.objective_value == 10.0


def test_exact_assignment_matches_brute_force_on_every_small_graph():
    requirements = (
        _requirement(10),
        _requirement(20),
    )
    all_edges = tuple(
        _operation(
            "actor-{}-city-{}".format(
                actor_id,
                requirement.city_id),
            requirement,
            actor_id,
            float(
                actor_id * 10
                + requirement.city_id))
        for actor_id in (1, 2, 3)
        for requirement in requirements)
    scheduler = (
        ExactCityDefenseAssignmentSolver())

    for edge_mask in range(
            1 << len(all_edges)):
        operations = tuple(
            operation
            for index, operation
            in enumerate(all_edges)
            if edge_mask & (1 << index))
        expected = _brute_force_optimum(
            requirements,
            operations)
        actual = scheduler.schedule(
            _analysis(
                requirements,
                operations))

        assert actual.status == "exact"
        assert (
            actual.covered_slots,
            actual.objective_value,
            actual.selected_operation_ids,
        ) == expected


def test_city_defense_artifact_exposes_only_an_exact_decision_safe_readout():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)

    exact = (
        build_city_defense_assignment_artifact(
            snapshot, ruleset,
            candidates,
            threat_radius=6,
            node_budget=5000,
            ruleset_digest=(
                "ruleset-proof")))
    bounded_out = (
        build_city_defense_assignment_artifact(
            snapshot, ruleset,
            candidates,
            threat_radius=6,
            node_budget=1,
            ruleset_digest=(
                "ruleset-proof")))

    assert exact[
        "decision_safe_candidate_readout"]
    assert exact[
        "selected_action_key"] in (
            snapshot.legal_action_json)
    assert exact["assignment"][
        "status"] == "exact"
    assert bounded_out["assignment"][
        "status"] == "greedy_fallback"
    assert not bounded_out[
        "decision_safe_candidate_readout"]
    assert bounded_out[
        "selected_action_key"] is None


def test_city_defense_authority_keeps_interception_shadow_only():
    intercept = _candidate({
        "action_type": "unit_attack",
        "actor_id": 2,
        "target": {
            "target_unit_id": 90,
            "x": 4,
            "y": 3,
        },
        "is_valid": True,
    }, "tactical_attack")
    snapshot, ruleset = _scenario(
        (intercept,))

    artifact = (
        build_city_defense_assignment_artifact(
            snapshot, ruleset,
            (intercept,),
            threat_radius=6,
            node_budget=5000,
            ruleset_digest=(
                "ruleset-proof")))

    assert any(
        row["selected"]
        and row["operation_type"]
        == "intercept_immediate_threat"
        for row in artifact[
            "assignment"]["entries"])
    assert not artifact[
        "decision_safe_candidate_readout"]
    assert artifact[
        "selected_action_key"] is None


def test_city_defense_authority_allows_grounded_approach_before_deadline():
    move = _candidate({
        "action_type": "unit_move",
        "actor_id": 2,
        "target": {"x": 3, "y": 0},
        "movement_cost": 1,
        "transport_required": False,
        "is_valid": True,
    }, "tactical_move")
    snapshot, ruleset = _scenario(
        (move,))
    snapshot.cities = (
        _city(20, 4, 0),)
    snapshot.movement_routes = (
        MovementRouteState(
            unit_id=2,
            origin_tile=2,
            destination_tile=4,
            reachable=True,
            first_step_tile=3,
            first_step_movement_cost=1,
            path_length=2,
            path_directions=(4, 4),
            estimated_turns=1,
            total_movement_cost=4,
            movement_points_remaining=2,
            moves_left_at_request=3,
            transported_at_request=False,
            initially_transported=False,
            turn=10,
            source_seq=10),)

    artifact = (
        build_city_defense_assignment_artifact(
            snapshot, ruleset,
            (move,),
            threat_radius=6,
            node_budget=5000,
            ruleset_digest=(
                "ruleset-proof")))

    assert any(
        row["selected"]
        and row["operation_type"]
        == "move_defender_to_city"
        for row in artifact[
            "assignment"]["entries"])
    assert artifact[
        "decision_safe_candidate_readout"]
    assert artifact[
        "selected_action_key"] == (
            move.action_key)


def test_current_snapshot_city_defense_authority_is_prepared_once():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory,
            "events.jsonl")
        writer = EventWriter(
            path,
            "city-defense-authority",
            durable=False)
        emitter = ControlEventEmitter()
        artifact, events, readout = (
            emitter
            .prepare_city_defense_authority(
                writer,
                snapshot,
                ruleset,
                candidates,
                threat_radius=6,
                node_budget=5000,
                ruleset_digest=(
                    "ruleset-proof")))
        (
            repeated_artifact,
            repeated_events,
            repeated_readout,
        ) = (
            emitter
            .prepare_city_defense_authority(
                writer,
                snapshot,
                ruleset,
                candidates,
                threat_radius=6,
                node_budget=5000,
                ruleset_digest=(
                    "ruleset-proof")))
        report = validate_file(
            path)

    assert artifact[
        "decision_safe_candidate_readout"]
    assert readout is not None
    assert readout.authority_kind.value == (
        "city_defense")
    assert readout.snapshot_id == (
        snapshot.snapshot_id)
    assert readout.legal_actions_digest == (
        snapshot.legal_actions_digest)
    assert readout.action_key in (
        snapshot.legal_action_json)
    assert any(
        row["type"]
        == "operation_reserved"
        for row in events)
    assert repeated_artifact is None
    assert repeated_events == ()
    assert repeated_readout == readout
    assert report.valid, [
        row.to_dict()
        for row in report.errors]


def test_unused_city_defense_authority_is_abandoned_immediately():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory,
            "events.jsonl")
        writer = EventWriter(
            path,
            "city-defense-abandonment",
            durable=False)
        emitter = ControlEventEmitter()
        _, events, readout = (
            emitter
            .prepare_city_defense_authority(
                writer,
                snapshot,
                ruleset,
                candidates,
                threat_radius=6,
                node_budget=5000,
                ruleset_digest=(
                    "ruleset-proof")))
        abandoned = (
            emitter
            .abandon_city_defense_authority(
                writer,
                snapshot.turn,
                readout,
                snapshot.snapshot_id,
                "current-planner-produced-no-decision",
                caused_by=(
                    events[-1][
                        "event_id"],)))
        remaining = (
            emitter
            .operation_authority_readout(
                writer,
                snapshot,
                city_defense_enabled=True))
        report = validate_file(
            path)

    assert [
        row["type"]
        for row in abandoned
    ] == [
        "operation_abandoned",
    ]
    assert abandoned[0]["payload"][
        "reason_code"] == (
            "current-planner-produced-no-decision")
    assert remaining is None
    assert report.valid, [
        row.to_dict()
        for row in report.errors]


def test_async_city_defense_shadow_cannot_reregister_live_reservation():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory,
            "events.jsonl")
        writer = EventWriter(
            path,
            "city-defense-shadow-suppression",
            durable=False)
        emitter = ControlEventEmitter()
        artifact, _, _ = (
            emitter
            .prepare_city_defense_authority(
                writer,
                snapshot,
                ruleset,
                candidates,
                threat_radius=6,
                node_budget=5000,
                ruleset_digest=(
                    "ruleset-proof")))
        delayed = dict(
            artifact)
        delayed.pop(
            "synchronous_authority_preparation")
        events = (
            emitter
            .emit_city_defense_operations(
                writer,
                snapshot.turn,
                delayed))
        report = validate_file(
            path)

    assert not any(
        row["type"]
        in (
            "operation_reserved",
            "operation_step_selected",
            "operation_blocked",
        )
        for row in events)
    assert any(
        row["payload"][
            "reason_code"]
        == "asynchronous-shadow-superseded-by-current-authority"
        for row in events
        if row["type"]
        == "operation_proposed")
    assert report.valid, [
        row.to_dict()
        for row in report.errors]


def test_city_defense_shadow_operations_emit_valid_attributable_events():
    candidates = _candidates()
    snapshot, ruleset = _scenario(
        candidates)
    analysis = (
        CityDefenseAnalyzer()
        .analyze(
            snapshot, ruleset,
            candidates))
    assignment = (
        ExactCityDefenseAssignmentSolver()
        .schedule(analysis))
    selected_action = next(
        row.next_action
        for row in analysis.operations
        if row.operation_id
        in assignment
        .selected_operation_ids
        and row.operation_type
        == DefenseOperationType
        .MOVE_DEFENDER_TO_CITY
        and row.next_action
        is not None)

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory,
            "events.jsonl")
        writer = EventWriter(
            path,
            "city-defense-events",
            durable=False)
        emitter = ControlEventEmitter()
        events = (
            emitter.emit_city_defense_operations(
                writer,
                snapshot.turn, {
                    "analysis":
                        analysis.to_dict(),
                    "assignment":
                        assignment.to_dict(),
                    "ruleset_digest":
                        "ruleset-proof",
                    "selected_action_key":
                        ImpactCandidate(
                            action=selected_action,
                            category="test",
                            utility=0.0,
                            rationale="test")
                        .action_key,
                    "source_turn":
                        snapshot.turn,
                }))
        selection = next(
            row for row in events
            if row["type"]
            == "operation_step_selected")
        action_events = (
            emitter
            .emit_city_defense_action_outcome(
                writer,
                snapshot.turn,
                snapshot,
                selected_action,
                ActionOutcome(
                    action_id=(
                        "action-proof"),
                    status="accepted",
                    reason=None,
                    submitted=True),
                caused_by=(
                    selection[
                        "event_id"],)))
        target = selected_action[
            "target"]
        actor_id = selected_action[
            "actor_id"]
        next_units = tuple(
            SimpleNamespace(
                **{
                    **unit.__dict__,
                    "x": (
                        target["x"]
                        if unit.unit_id
                        == actor_id
                        else unit.x),
                    "y": (
                        target["y"]
                        if unit.unit_id
                        == actor_id
                        else unit.y),
                    "activity":
                        getattr(
                            unit,
                            "activity",
                            None),
                })
            for unit in
            snapshot.units)
        next_snapshot = (
            SimpleNamespace(
                snapshot_id=(
                    "defence-snapshot-next"),
                turn=(
                    snapshot.turn + 1),
                city=lambda city_id: next(
                    (
                        city for city
                        in snapshot.cities
                        if city.city_id
                        == city_id),
                    None),
                unit=lambda unit_id: next(
                    (
                        unit for unit
                        in next_units
                        if unit.unit_id
                        == unit_id),
                    None)))
        resolution_events = (
            emitter
            .resolve_city_defense_operations(
                writer,
                next_snapshot,
                caused_by=(
                    action_events[
                        -1]["event_id"],)))
        report = validate_file(
            path)

    proposals = [
        row for row in events
        if row["type"]
        == "operation_proposed"]
    selections = [
        row for row in events
        if row["type"]
        == "operation_step_selected"]
    assert len(proposals) == len(
        analysis.operations)
    assert len(selections) == 1
    assert [
        row["type"]
        for row in action_events
    ] == [
        "operation_activated",
        "operation_step_revalidated",
        "operation_step_committed",
    ]
    assert [
        row["type"]
        for row in resolution_events
    ] == [
        "operation_completed",
    ]
    assert resolution_events[0][
        "payload"][
            "resolution_status"
    ] == "resolved_success"
    assert {
        row["payload"]["operation_id"]
        for row in selections
    } <= set(
        assignment
        .selected_operation_ids)
    assert all(
        row["payload"][
            "assignment_digest"]
        == assignment
        .decision_digest
        for row in events)
    assert all(
        row["payload"][
            "reason_code"]
        for row in proposals
        if not row["payload"][
            "selected"])
    assert all(
        row["payload"][
            "shadow_only"]
        and not row["payload"][
            "policy_authority"]
        for row in events)
    assert report.valid, [
        row.to_dict()
        for row in report.errors]


def test_city_defense_move_rebinds_current_steps_until_city_occupancy():
    first_action = {
        "action_type": "unit_move",
        "actor_id": 2,
        "movement_cost": 1,
        "target": {"x": 1, "y": 0},
        "transport_required": False,
    }
    second_action = {
        "action_type": "unit_move",
        "actor_id": 2,
        "movement_cost": 1,
        "target": {"x": 2, "y": 0},
        "transport_required": False,
    }

    def artifact(
            operation_id, action,
            snapshot_id, turn):
        operation = {
            "actor_id": 2,
            "arrival_turn": turn + 1,
            "bid": 50.0,
            "city_id": 20,
            "claims": [],
            "deadline_turn": 12,
            "expected_prevented_loss":
                50.0,
            "next_action": dict(action),
            "operation_id": operation_id,
            "operation_type":
                "move_defender_to_city",
            "opportunity_cost": 0.0,
            "provenance": [
                "server-advertised-legal-action",
                "native-server-route-eta",
            ],
            "requirement_id":
                "city-defense-requirement",
            "support_reason": None,
        }
        return {
            "analysis": {
                "operations": [operation],
                "snapshot_id": snapshot_id,
            },
            "assignment": {
                "decision_digest":
                    structural_hash({
                        "snapshot_id":
                            snapshot_id,
                    }),
                "entries": [{
                    "operation_id":
                        operation_id,
                    "reason": None,
                    "selected": True,
                }],
            },
            "ruleset_digest":
                "ruleset-proof",
            "selected_action_key":
                ImpactCandidate(
                    action=action,
                    category="test",
                    utility=0.0,
                    rationale="test")
                .action_key,
            "source_turn": turn,
            "synchronous_authority_preparation":
                True,
        }

    def snapshot(
            snapshot_id, turn,
            unit_x, legal_action):
        city = SimpleNamespace(
            city_id=20,
            x=2, y=0)
        unit = SimpleNamespace(
            unit_id=2,
            x=unit_x, y=0,
            activity=None)
        legal_key = (
            None
            if legal_action is None
            else ImpactCandidate(
                action=legal_action,
                category="test",
                utility=0.0,
                rationale="test")
            .action_key)
        return SimpleNamespace(
            snapshot_id=snapshot_id,
            legal_actions_digest=(
                "legal-{}".format(
                    snapshot_id)),
            legal_action_json=(
                (legal_key,)
                if legal_action is not None
                else ()),
            turn=turn,
            city=lambda city_id: (
                city if city_id == 20
                else None),
            unit=lambda unit_id: (
                unit if unit_id == 2
                else None))

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory,
            "events.jsonl")
        writer = EventWriter(
            path,
            "city-defense-persistence",
            durable=False)
        emitter = ControlEventEmitter()
        first_snapshot = snapshot(
            "route-step-1", 10, 0,
            first_action)
        first_events = (
            emitter
            .emit_city_defense_operations(
                writer, 10,
                artifact(
                    "volatile-operation-1",
                    first_action,
                    "route-step-1", 10)))
        first_readout = (
            emitter
            .operation_authority_readout(
                writer,
                first_snapshot,
                city_defense_enabled=True))
        first_outcome = (
            emitter
            .emit_city_defense_action_outcome(
                writer, 10,
                first_snapshot,
                first_action,
                ActionOutcome(
                    action_id="route-action-1",
                    status="accepted",
                    reason=None,
                    submitted=True)))

        second_snapshot = snapshot(
            "route-step-2", 11, 1,
            second_action)
        assert (
            emitter
            .resolve_city_defense_operations(
                writer,
                second_snapshot)
        ) == ()
        second_events = (
            emitter
            .emit_city_defense_operations(
                writer, 11,
                artifact(
                    "volatile-operation-2",
                    second_action,
                    "route-step-2", 11)))
        second_readout = (
            emitter
            .operation_authority_readout(
                writer,
                second_snapshot,
                city_defense_enabled=True))
        second_outcome = (
            emitter
            .emit_city_defense_action_outcome(
                writer, 11,
                second_snapshot,
                second_action,
                ActionOutcome(
                    action_id="route-action-2",
                    status="accepted",
                    reason=None,
                    submitted=True)))
        completed_snapshot = snapshot(
            "route-complete", 12, 2,
            None)
        completed = (
            emitter
            .resolve_city_defense_operations(
                writer,
                completed_snapshot))
        report = validate_file(path)

    assert first_readout is not None
    assert second_readout is not None
    assert (
        second_readout.operation_id
        == first_readout.operation_id
        == "volatile-operation-1")
    assert [
        row["type"]
        for row in first_outcome
    ] == [
        "operation_activated",
        "operation_step_revalidated",
        "operation_step_committed",
    ]
    assert [
        row["type"]
        for row in second_outcome
    ] == [
        "operation_step_revalidated",
        "operation_step_committed",
    ]
    assert not any(
        row["type"]
        == "operation_reserved"
        for row in second_events)
    assert any(
        row["type"]
        == "operation_step_selected"
        and row["payload"][
            "operation_id"]
        == "volatile-operation-1"
        for row in second_events)
    assert [
        row["type"]
        for row in completed
    ] == [
        "operation_completed",
    ]
    assert all(
        row["payload"][
            "operation_id"]
        == "volatile-operation-1"
        for row in completed)
    assert first_events
    assert report.valid, [
        row.to_dict()
        for row in report.errors]
