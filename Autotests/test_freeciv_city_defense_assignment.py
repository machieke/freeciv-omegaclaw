"""Grounded city-threat analysis and exact defender assignment."""

import itertools
import os
import sys
import tempfile
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import ImpactCandidate  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.planning import ControlEventEmitter  # noqa: E402
from freeciv_agent.planning.domain_models import (  # noqa: E402
    CityDefenseAnalysis,
    CityDefenseAnalyzer,
    CityDefenseOperation,
    CityDefenseRequirement,
    DefenseOperationType,
    ExactCityDefenseAssignmentSolver,
)
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
        city_id=city_id,
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
        cities=(
            _city(10, 0, 0),
            _city(20, 4, 0)),
        units=own,
        visible_enemy_units=enemy,
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
        for row in analysis.threats)
    assert {
        row.city_id:
        row.deadline_turn
        for row in analysis.requirements
    } == {
        10: 13,
        20: 12,
    }


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

    assert analysis.threats
    assert all(
        row.support_reason
        == "enemy-unit-not-combat-capable"
        for row in analysis.threats)
    assert analysis.requirements == ()


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

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory,
            "events.jsonl")
        writer = EventWriter(
            path,
            "city-defense-events",
            durable=False)
        events = (
            ControlEventEmitter
            .emit_city_defense_operations(
                writer,
                snapshot.turn, {
                    "analysis":
                        analysis.to_dict(),
                    "assignment":
                        assignment.to_dict(),
                }))
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
    assert {
        row["payload"]["operation_id"]
        for row in selections
    } == set(
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
