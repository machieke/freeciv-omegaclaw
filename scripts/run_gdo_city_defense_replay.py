#!/usr/bin/env python3
"""Replay captured GDO-4 city-defence states through B1/B2/B3/B4."""

import argparse
from collections import Counter
import hashlib
import json
import os
import statistics
import sys
import time


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import ImpactCandidate  # noqa: E402
from freeciv_agent.planning.domain_models import (  # noqa: E402
    CityDefenseAnalyzer,
    DefenseOperationType,
    ExactCityDefenseAssignmentSolver,
    grounded_operation_result,
)
from freeciv_agent.pressure import ImpactPressureRankerV2  # noqa: E402
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.state.snapshot import (  # noqa: E402
    AuthoritativeSnapshot,
    BuildingState,
    CityState,
    EconomicState,
    GovernmentState,
    MovementRouteState,
    PlayerScoreState,
    ResearchState,
    SnapshotIdentity,
    UnitState,
)


DEFAULT_MANIFEST = os.path.join(
    REPO, "benchmarks", "gdo",
    "captured_snapshots",
    "city_defense_replay_manifest.json")
DEFAULT_RULESET_ROOT = os.path.join(
    REPO, "build", "freeciv",
    "ruleset-source")
DEFAULT_OUTPUT = os.path.join(
    REPO, "benchmarks", "gdo",
    "gdo4_city_defense_replay_diagnostic.local.json")

def _percentile(rows, fraction):
    ordered = sorted(
        float(value)
        for value in rows)
    return ordered[
        int(float(fraction)
            * (len(ordered) - 1))]


def _summary(rows):
    return {
        "maximum_ms": max(rows),
        "mean_ms": statistics.mean(
            rows),
        "p50_ms": statistics.median(
            rows),
        "p95_ms": _percentile(
            rows, 0.95),
        "p99_ms": _percentile(
            rows, 0.99),
        "sample_count": len(rows),
    }


def _numbers(value):
    return tuple(
        int(row)
        for row in (
            value or ()))


def _unit(row):
    return UnitState(
        unit_id=int(
            row["unit_id"]),
        owner=int(
            row["owner"]),
        unit_type=str(
            row["type"]),
        type_id=row.get(
            "type_id"),
        tile=row.get("tile"),
        x=row.get("x"),
        y=row.get("y"),
        moves_left=row.get(
            "moves_left"),
        hp=row.get("hp"),
        activity=row.get(
            "activity"),
        upkeep=_numbers(
            row.get("upkeep")),
        homecity=row.get(
            "homecity"),
        veteran=row.get(
            "veteran"),
        transported=row.get(
            "transported"),
        transported_by=row.get(
            "transported_by"),
        carrying=row.get(
            "carrying"),
        done_moving=row.get(
            "done_moving"))


def _city(row):
    mood = row.get(
        "citizen_mood", {})
    governor = row.get(
        "governor", {})
    buildings = tuple(
        BuildingState(
            improvement_id=int(
                value[
                    "improvement_id"]),
            name=str(
                value["name"]),
            upkeep=value.get(
                "upkeep"))
        for value in row.get(
            "buildings", ()))
    return CityState(
        city_id=int(
            row["city_id"]),
        owner=int(
            row["owner"]),
        name=str(
            row["name"]),
        tile=row.get("tile"),
        x=row.get("x"),
        y=row.get("y"),
        size=int(
            row["size"]),
        production_kind=row.get(
            "production_kind"),
        production_value=row.get(
            "production_value"),
        food_stock=row.get(
            "food_stock"),
        shield_stock=row.get(
            "shield_stock"),
        surplus=_numbers(
            row.get("surplus")),
        production=_numbers(
            row.get("production")),
        buildability_available=bool(
            row.get(
                "buildability_available",
                False)),
        buildable=tuple(
            tuple(value)
            for value in row.get(
                "buildable", ())),
        buildability_diagnostic=(
            row.get(
                "buildability_diagnostic")),
        feeling_happy=_numbers(
            mood.get("happy")),
        feeling_content=_numbers(
            mood.get("content")),
        feeling_unhappy=_numbers(
            mood.get("unhappy")),
        feeling_angry=_numbers(
            mood.get("angry")),
        disorder=row.get(
            "disorder"),
        was_happy=row.get(
            "was_happy"),
        had_famine=row.get(
            "had_famine"),
        unhappy_penalty=_numbers(
            row.get(
                "unhappy_penalty")),
        usage=_numbers(
            row.get("usage")),
        governor_available=bool(
            governor.get(
                "available", False)),
        governor_enabled=governor.get(
            "enabled"),
        governor_minimal_surplus=_numbers(
            governor.get(
                "minimal_surplus")),
        governor_factor=_numbers(
            governor.get(
                "factor")),
        governor_require_happy=(
            governor.get(
                "require_happy")),
        governor_allow_disorder=(
            governor.get(
                "allow_disorder")),
        governor_max_growth=(
            governor.get(
                "max_growth")),
        governor_allow_specialists=(
            governor.get(
                "allow_specialists")),
        governor_happy_factor=(
            governor.get(
                "happy_factor")),
        buildings=buildings)


def _movement_route(row):
    if not isinstance(
            row, dict):
        raise ValueError(
            "captured movement route must be an object")
    if row.get(
            "schema_version") != "1.0":
        raise ValueError(
            "captured movement route schema must be 1.0")
    if row.get(
            "authority") != (
                "freeciv-server-pathfinder"):
        raise ValueError(
            "captured movement route must use native server authority")
    integer_names = (
        "unit_id",
        "origin_tile",
        "destination_tile",
        "first_step_tile",
        "first_step_movement_cost",
        "path_length",
        "estimated_turns",
        "total_movement_cost",
        "movement_points_remaining",
        "moves_left_at_request",
        "turn",
        "source_seq",
    )
    if any(
            isinstance(
                row.get(name),
                bool)
            or not isinstance(
                row.get(name),
                int)
            for name in
            integer_names):
        raise ValueError(
            "captured movement route numeric fields must be integers")
    boolean_names = (
        "reachable",
        "transported_at_request",
        "initially_transported",
    )
    if any(
            not isinstance(
                row.get(name),
                bool)
            for name in
            boolean_names):
        raise ValueError(
            "captured movement route boolean fields must be booleans")
    directions = row.get(
        "path_directions")
    if (
        not isinstance(
            directions, list)
        or any(
            isinstance(
                value, bool)
            or not isinstance(
                value, int)
            or value < -1
            or value > 7
            for value in
            directions)
        or row[
            "path_length"]
        != len(
            directions)
    ):
        raise ValueError(
            "captured movement route directions are inconsistent")
    if (
        row[
            "transported_at_request"]
        is not row[
            "initially_transported"]
    ):
        raise ValueError(
            "captured movement route transport state is inconsistent")
    if any(
            row[name] < 0
            for name in (
                "unit_id",
                "origin_tile",
                "destination_tile",
                "first_step_tile",
                "first_step_movement_cost",
                "path_length",
                "estimated_turns",
                "total_movement_cost",
                "movement_points_remaining",
                "moves_left_at_request",
                "turn",
                "source_seq",
            )):
        raise ValueError(
            "captured movement route numeric fields must be non-negative")
    if row[
            "reachable"]:
        if (
            row[
                "path_length"] < 1
            or row[
                "first_step_movement_cost"] < 1
            or row[
                "total_movement_cost"]
            < row[
                "first_step_movement_cost"]
            or row[
                "estimated_turns"] < 0
        ):
            raise ValueError(
                "captured reachable movement route is inconsistent")
    elif any((
            row["path_length"],
            row[
                "first_step_movement_cost"],
            row[
                "estimated_turns"],
            row[
                "total_movement_cost"],
            len(
                directions))):
        raise ValueError(
            "captured unreachable movement route must have an empty path")
    elif row[
            "first_step_tile"] != row[
                "origin_tile"]:
        raise ValueError(
            "captured unreachable route must remain at its origin")
    return MovementRouteState(
        unit_id=int(
            row["unit_id"]),
        origin_tile=int(
            row["origin_tile"]),
        destination_tile=int(
            row["destination_tile"]),
        reachable=bool(
            row["reachable"]),
        first_step_tile=int(
            row["first_step_tile"]),
        first_step_movement_cost=int(
            row[
                "first_step_movement_cost"]),
        path_length=int(
            row["path_length"]),
        path_directions=tuple(
            directions),
        estimated_turns=int(
            row["estimated_turns"]),
        total_movement_cost=int(
            row[
                "total_movement_cost"]),
        movement_points_remaining=int(
            row[
                "movement_points_remaining"]),
        moves_left_at_request=int(
            row[
                "moves_left_at_request"]),
        transported_at_request=bool(
            row[
                "transported_at_request"]),
        initially_transported=bool(
            row[
                "initially_transported"]),
        turn=int(
            row["turn"]),
        source_seq=int(
            row["source_seq"]))


def _snapshot(fixture, candidates):
    event = fixture[
        "snapshot_event"]
    payload = event[
        "payload"]
    own = payload[
        "own_state"]
    map_payload = payload[
        "map"]
    research = own[
        "research"]
    economy = own[
        "economy"]
    government = own[
        "government"]
    score = own.get(
        "score", {})
    grounded = payload.get(
        "grounded_context")
    grounded = (
        grounded
        if isinstance(
            grounded, dict)
        else {})
    legal_actions = grounded.get(
        "legal_actions")
    if (not isinstance(
            legal_actions, list)
            or not all(
                isinstance(
                    row, dict)
                for row in
                legal_actions)):
        legal_actions = [
            candidate.action
            for candidate
            in candidates]
    legal_json = tuple(sorted(
        canonical_json_bytes(
            action).decode(
                "utf-8")
        for action in
        legal_actions))
    grounded_own_units = grounded.get(
        "own_units")
    if not isinstance(
            grounded_own_units, list):
        grounded_own_units = own.get(
            "units", ())
    grounded_enemy_units = (
        grounded.get(
            "visible_enemy_units"))
    if not isinstance(
            grounded_enemy_units, list):
        grounded_enemy_units = (
            map_payload.get(
                "visible_enemy_units",
                ()))
    topology = grounded.get(
        "map_topology")
    topology = (
        topology
        if isinstance(
            topology, dict)
        else {})
    movement_routes = grounded.get(
        "movement_routes")
    movement_routes = (
        movement_routes
        if isinstance(
            movement_routes, list)
        else ())
    identity = SnapshotIdentity(
        game_id=str(
            event["game_id"]),
        turn=int(
            event["turn"]),
        source_seq=int(
            payload["source_seq"]),
        state_hash=str(
            payload["state_hash"]))
    snapshot_units = tuple(
        _unit(row)
        for row in
        grounded_own_units)
    parsed_routes = tuple(
        sorted(
            (
                _movement_route(row)
                for row in
                movement_routes
            ),
            key=lambda row: (
                row.unit_id,
                row.destination_tile)))
    units_by_id = {
        unit.unit_id: unit
        for unit in
        snapshot_units}
    for route in parsed_routes:
        unit = units_by_id.get(
            route.unit_id)
        if (
            unit is None
            or route.turn
            != identity.turn
            or route.source_seq
            > identity.source_seq
            or route.origin_tile
            != unit.tile
            or route.moves_left_at_request
            != unit.moves_left
            or route.transported_at_request
            is not unit.transported
        ):
            raise ValueError(
                "captured movement route does not match replay snapshot")
    return AuthoritativeSnapshot(
        identity=identity,
        player_id=int(
            payload["player_id"]),
        player_alive=own.get(
            "player_alive"),
        phase="captured-event-replay",
        ruleset_ready=bool(
            own.get(
                "ruleset_ready",
                False)),
        ruleset_diagnostic=own.get(
            "ruleset_diagnostic"),
        research=ResearchState(
            known_techs=tuple(
                sorted(
                    research.get(
                        "known_techs",
                        ()))),
            target_id=research.get(
                "target_id"),
            target_name=research.get(
                "target_name"),
            progress=research.get(
                "progress"),
            cost=research.get(
                "cost"),
            beakers_per_turn=(
                research.get(
                    "beakers_per_turn")),
            available=bool(
                research.get(
                    "available",
                    False)),
            diagnostic=research.get(
                "diagnostic"),
            gross_beakers_per_turn=(
                research.get(
                    "gross_beakers_per_turn")),
            tech_upkeep=research.get(
                "tech_upkeep")),
        economy=EconomicState(
            gold=economy.get(
                "gold"),
            gold_per_turn=economy.get(
                "gold_per_turn"),
            tax_rate=economy.get(
                "tax_rate"),
            science_rate=economy.get(
                "science_rate"),
            luxury_rate=economy.get(
                "luxury_rate"),
            available=bool(
                economy.get(
                    "available",
                    False)),
            diagnostic=economy.get(
                "diagnostic"),
            city_gold_surplus_per_turn=(
                economy.get(
                    "city_gold_surplus_per_turn")),
            unit_gold_upkeep=economy.get(
                "unit_gold_upkeep"),
            gold_upkeep_reserve=(
                economy.get(
                    "gold_upkeep_reserve")),
            gold_upkeep_style=economy.get(
                "gold_upkeep_style"),
            operating_gold_per_turn=(
                economy.get(
                    "operating_gold_per_turn")),
            capitalization_gold_per_turn=(
                economy.get(
                    "capitalization_gold_per_turn"))),
        government=GovernmentState(
            current_id=government.get(
                "current_id"),
            current_name=government.get(
                "current_name"),
            target_id=government.get(
                "target_id"),
            target_name=government.get(
                "target_name"),
            revolution_finishes=(
                government.get(
                    "revolution_finishes")),
            in_revolution=bool(
                government.get(
                    "in_revolution",
                    False)),
            selection_required=bool(
                government.get(
                    "selection_required",
                    False)),
            available=bool(
                government.get(
                    "available",
                    False)),
            diagnostic=government.get(
                "diagnostic")),
        cities=tuple(
            _city(row)
            for row in own.get(
                "cities", ())),
        units=snapshot_units,
        visible_enemy_units=tuple(
            _unit(row)
            for row in
            grounded_enemy_units),
        visible_tile_ids=tuple(
            int(value)
            for value in map_payload.get(
                "visible_tile_ids", ())),
        known_hut_tile_ids=tuple(
            int(value)
            for value in map_payload.get(
                "known_hut_tile_ids",
                ())),
        map_width=int(
            map_payload["width"]),
        map_height=int(
            map_payload["height"]),
        map_tiles=tuple(
            map_payload.get(
                "tiles", ())),
        legal_action_json=legal_json,
        legal_actions_digest=str(
            payload[
                "legal_actions_digest"]),
        legal_action_kinds=tuple(
            sorted(set(
                str(
                    candidate.action.get(
                        "action_type",
                        "unknown"))
                for candidate
                in candidates))),
        game_over=bool(
            own.get(
                "game_over", False)),
        own_score=score.get(
            "own"),
        opponent_scores=tuple(
            PlayerScoreState(
                player_id=int(
                    row["player_id"]),
                name=str(
                    row["name"]),
                score=row.get(
                    "score"),
                is_alive=row.get(
                    "is_alive"))
            for row in score.get(
                "opponents", ())),
        map_wrap_x=topology.get(
            "wrap_x"),
        map_wrap_y=topology.get(
            "wrap_y"),
        movement_routes=parsed_routes)


def _load_fixture(path, expected_hash):
    with open(
            path,
            encoding="utf-8") as stream:
        fixture = json.load(
            stream)
    if structural_hash(
            fixture) != expected_hash:
        raise ValueError(
            "fixture checksum mismatch: {}".format(
                path))
    candidates = tuple(
        ImpactCandidate(
            action=row["action"],
            category=row[
                "category"],
            utility=float(
                row["utility"]),
            rationale=row[
                "rationale"],
            projection=row.get(
                "projection"))
        for row in fixture[
            "candidates"])
    return (
        fixture,
        _snapshot(
            fixture,
            candidates),
        candidates)


def _selected_for_action(
        analysis, action_key):
    rows = [
        row for row
        in analysis.operations
        if row.supported
        and row.next_action
        is not None
        and ImpactCandidate(
            action=row.next_action,
            category="replay",
            utility=0.0,
            rationale="replay"
        ).action_key
        == action_key]
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                -float(row.bid),
                row.operation_id))[:1])


def _single_action_readout(selected):
    return tuple(sorted(
        (
            row for row in selected
            if row.next_action
            is not None
        ),
        key=lambda row: (
            -float(row.bid),
            row.operation_id))[:1])


def _metrics(
        requirements, selected,
        analysis):
    selected = tuple(
        selected)
    by_requirement = {}
    for row in selected:
        by_requirement[
            row.requirement_id] = (
                by_requirement.get(
                    row.requirement_id,
                    0) + 1)
    uncovered = sum(
        max(
            0,
            row.response_slots
            - by_requirement.get(
                row.requirement_id,
                0))
        for row in requirements)
    prevented_loss_proxy = 0.0
    remaining_loss_proxy = 0.0
    for row in requirements:
        covered = min(
            row.response_slots,
            by_requirement.get(
                row.requirement_id,
                0))
        value_per_slot = (
            float(
                row.threat_priority)
            / float(
                row.response_slots))
        prevented_loss_proxy += (
            covered
            * value_per_slot)
        remaining_loss_proxy += (
            (
                row.response_slots
                - covered)
            * value_per_slot)
    defenders = {
        row.unit_id: row
        for row in analysis.defenders}
    sole_violations = sum(
        bool(
            operation.actor_id
            is not None
            and defenders.get(
                operation.actor_id)
            is not None
            and defenders[
                operation.actor_id]
            .protected_sole_defender
            and defenders[
                operation.actor_id]
            .current_city_id
            != operation.city_id)
        for operation in selected)
    actors = [
        row.actor_id
        for row in selected
        if row.actor_id
        is not None]
    city_production = [
        row.city_id
        for row in selected
        if row.actor_id
        is None]
    return {
        "actor_conflicts": (
            len(actors)
            - len(set(actors))),
        "city_production_conflicts": (
            len(city_production)
            - len(set(
                city_production))),
        "covered_threat_slots": (
            sum(
                row.response_slots
                for row
                in requirements)
            - uncovered),
        "late_assignments": sum(
            row.arrival_turn
            > row.deadline_turn
            for row in selected),
        "objective_value": sum(
            row.bid
            for row in selected),
        "prevented_loss_proxy":
            prevented_loss_proxy,
        "remaining_loss_proxy":
            remaining_loss_proxy,
        "selected_operation_count":
            len(selected),
        "sole_defender_violations":
            sole_violations,
        "uncovered_threat_slots":
            uncovered,
    }


def _add(target, values):
    for key, value in (
            values.items()):
        target[key] = (
            target.get(
                key, 0)
            + value)


def _resolved_city_losses(
        fixture, analysis):
    outcomes = {
        int(row["turn"]): row
        for row in fixture.get(
            "outcome_observations",
            ())}
    losses = 0
    unresolved = 0
    for requirement in (
            analysis.requirements):
        turns = sorted(
            turn
            for turn in outcomes
            if turn
            >= requirement
            .deadline_turn)
        if not turns:
            unresolved += 1
            continue
        city_ids = set(
            outcomes[
                turns[0]][
                    "city_ids"])
        losses += (
            requirement.city_id
            not in city_ids)
    return losses, unresolved


def run(
        manifest_path,
        ruleset_root,
        timing_iterations):
    with open(
            manifest_path,
            encoding="utf-8") as stream:
        manifest = json.load(
            stream)
    hash_value = manifest.get(
        "manifest_hash")
    hash_material = dict(
        manifest)
    hash_material.pop(
        "manifest_hash", None)
    if structural_hash(
            hash_material) != hash_value:
        raise ValueError(
            "city-defence replay manifest checksum mismatch")
    ruleset_ir = compile_ruleset(
        ruleset_root,
        manifest[
            "ruleset"])
    fixtures = []
    for row in manifest[
            "fixtures"]:
        path = os.path.join(
            REPO, row["path"])
        fixtures.append(
            _load_fixture(
                path,
                row[
                    "fixture_sha256"]))
    for fixture, snapshot, _candidates in fixtures:
        if fixture[
                "authority"].get(
                    "full_legal_action_set_available"):
            digest = hashlib.sha256(
                "\n".join(
                    snapshot
                    .legal_action_json)
                .encode("utf-8")
            ).hexdigest()
            if digest != (
                    snapshot
                    .legal_actions_digest):
                raise ValueError(
                    "grounded legal-action digest mismatch: {}".format(
                        snapshot
                        .snapshot_id))
    analyzer = CityDefenseAnalyzer(
        threat_radius=3)
    solver = (
        ExactCityDefenseAssignmentSolver())
    ranker = (
        ImpactPressureRankerV2())
    totals = {
        name: {}
        for name in (
            "B1", "B2",
            "B3", "B4")}
    assignment_totals = {
        name: {}
        for name in (
            "B3", "B4")}
    scenarios = []
    exact_never_worse = True
    exact_status = True
    factual_city_losses = 0
    unresolved_city_outcomes = 0
    replay_latency = []
    operation_support_reasons = Counter()
    operation_types = Counter()
    threat_support_reasons = Counter()
    threat_eta_bases = Counter()
    threat_eta_advance_turns = Counter()
    threat_unit_classes = Counter()
    threat_unit_types = Counter()
    try:
        for (
                fixture,
                snapshot,
                candidates) in fixtures:
            ordered, _ = ranker.rank(
                snapshot,
                candidates,
                expansion_city_target=5,
                horizon_turn=960,
                survival_threat_radius=3)
            b1_key = (
                ordered[0].action_key
                if ordered else None)
            analysis = analyzer.analyze(
                snapshot,
                ruleset_ir,
                candidates)
            supported = tuple(
                row
                for row in analysis.operations
                if row.supported
                and row.operation_type
                != DefenseOperationType
                .HOLD_SOLE_DEFENDER)
            b1_selected = (
                ()
                if b1_key is None
                else _selected_for_action(
                    analysis,
                    b1_key))
            b2_selected = tuple(
                sorted(
                    supported,
                    key=lambda row: (
                        -float(row.bid),
                        row.operation_id))[:1])
            b3_selected = solver._greedy(
                analysis.requirements,
                analysis.operations)
            b4 = solver.schedule(
                analysis)
            b4_ids = frozenset(
                b4.selected_operation_ids)
            b4_selected = tuple(
                row
                for row in
                analysis.operations
                if row.operation_id
                in b4_ids)
            b3_readout = (
                _single_action_readout(
                    b3_selected))
            b4_readout = (
                _single_action_readout(
                    b4_selected))
            arms = {
                "B1": b1_selected,
                "B2": b2_selected,
                "B3": b3_readout,
                "B4": b4_readout,
            }
            assignment_arms = {
                "B3": b3_selected,
                "B4": b4_selected,
            }
            arm_metrics = {}
            for name, selected in (
                    arms.items()):
                arm_metrics[name] = (
                    _metrics(
                        analysis.requirements,
                        selected,
                        analysis))
                _add(
                    totals[name],
                    arm_metrics[name])
            assignment_arm_metrics = {}
            for name, selected in (
                    assignment_arms
                    .items()):
                assignment_arm_metrics[
                    name] = _metrics(
                        analysis.requirements,
                        selected,
                        analysis)
                _add(
                    assignment_totals[
                        name],
                    assignment_arm_metrics[
                        name])
            exact_never_worse = bool(
                exact_never_worse
                and assignment_arm_metrics[
                    "B4"][
                    "covered_threat_slots"]
                >= assignment_arm_metrics[
                    "B3"][
                    "covered_threat_slots"])
            exact_status = bool(
                exact_status
                and b4.status == "exact")
            losses, unresolved = (
                _resolved_city_losses(
                    fixture,
                    analysis))
            factual_city_losses += (
                losses)
            unresolved_city_outcomes += (
                unresolved)
            supported_threats = sum(
                row.supported
                for row in
                analysis.threats)
            for threat in analysis.threats:
                threat_support_reasons[
                    threat.support_reason
                    or "supported"] += 1
                threat_eta_bases[
                    threat.eta_basis] += 1
                threat_eta_advance_turns[
                    max(
                        0,
                        int(snapshot.turn)
                        + max(
                            0,
                            threat.distance_tiles
                            - 1)
                        - threat
                        .earliest_attack_turn)
                ] += 1
                threat_unit_classes[
                    threat.enemy_unit_class
                    or "unknown"] += 1
                threat_unit_types[
                    threat.enemy_unit_type] += 1
            for operation in analysis.operations:
                operation_support_reasons[
                    operation.support_reason
                    or "supported"] += 1
                operation_types[
                    operation.operation_type
                    .value] += 1
            candidate_edge_requirements = sum(
                any(
                    operation.next_action
                    is not None
                    and operation
                    .requirement_id
                    == requirement
                    .requirement_id
                    for operation
                    in analysis.operations)
                for requirement
                in analysis.requirements)
            supported_requirements = sum(
                any(
                    operation.supported
                    and operation
                    .requirement_id
                    == requirement
                    .requirement_id
                    and operation
                    .operation_type
                    != DefenseOperationType
                    .HOLD_SOLE_DEFENDER
                    for operation
                    in analysis.operations)
                for requirement
                in analysis.requirements)
            grounded_operation_count = sum(
                grounded_operation_result(
                    operation)
                for operation in
                analysis.operations)
            decision_resolved_requirements = sum(
                bool(
                    requirement_operations)
                and all(
                    grounded_operation_result(
                        operation)
                    for operation in
                    requirement_operations)
                for requirement
                in analysis.requirements
                for requirement_operations
                in (tuple(
                    operation
                    for operation in
                    analysis.operations
                    if operation
                    .requirement_id
                    == requirement
                    .requirement_id),))
            scenarios.append({
                "arms":
                    arm_metrics,
                "assignment_arms":
                    assignment_arm_metrics,
                "candidate_count":
                    len(candidates),
                "candidate_edge_requirement_count":
                    candidate_edge_requirements,
                "operation_count":
                    len(
                        analysis.operations),
                "input_candidate_count":
                    analysis
                    .input_candidate_count,
                "grounded_operation_count":
                    grounded_operation_count,
                "protected_union_added_count":
                    analysis
                    .protected_union_added_count,
                "requirement_count":
                    len(
                        analysis.requirements),
                "decision_resolved_requirement_count":
                    decision_resolved_requirements,
                "snapshot_id":
                    snapshot.snapshot_id,
                "supported_operation_count":
                    len(supported),
                "supported_requirement_count":
                    supported_requirements,
                "supported_threat_count":
                    supported_threats,
                "threat_support_reasons":
                    dict(sorted(
                        Counter(
                            row.support_reason
                            or "supported"
                            for row in
                            analysis.threats)
                        .items())),
                "threat_eta_bases":
                    dict(sorted(
                        Counter(
                            row.eta_basis
                            for row in
                            analysis.threats)
                        .items())),
                "threat_eta_advance_turns":
                    {
                        str(turns): count
                        for turns, count
                        in sorted(
                            Counter(
                            max(
                                0,
                                int(snapshot.turn)
                                + max(
                                    0,
                                    row.distance_tiles
                                    - 1)
                                - row
                                .earliest_attack_turn)
                            for row in
                            analysis.threats)
                            .items())
                    },
                "threat_unit_classes":
                    dict(sorted(
                        Counter(
                            row.enemy_unit_class
                            or "unknown"
                            for row in
                            analysis.threats)
                        .items())),
                "threat_unit_types":
                    dict(sorted(
                        Counter(
                            row.enemy_unit_type
                            for row in
                            analysis.threats)
                        .items())),
                "threat_count":
                    len(
                        analysis.threats),
                "turn": snapshot.turn,
            })

        for _ in range(
                int(timing_iterations)):
            for (
                    _fixture,
                    snapshot,
                    candidates) in fixtures:
                started = (
                    time.perf_counter())
                analysis = (
                    analyzer.analyze(
                        snapshot,
                        ruleset_ir,
                        candidates))
                solver.schedule(
                    analysis)
                replay_latency.append(
                    (
                        time.perf_counter()
                        - started) * 1000.0)
    finally:
        ranker.close_domain_estimates()

    total_threats = sum(
        row["threat_count"]
        for row in scenarios)
    supported_threats = sum(
        row[
            "supported_threat_count"]
        for row in scenarios)
    total_requirements = sum(
        row["requirement_count"]
        for row in scenarios)
    supported_requirements = sum(
        row[
            "supported_requirement_count"]
        for row in scenarios)
    candidate_edge_requirements = sum(
        row[
            "candidate_edge_requirement_count"]
        for row in scenarios)
    total_operations = sum(
        row["operation_count"]
        for row in scenarios)
    grounded_operations = sum(
        row["grounded_operation_count"]
        for row in scenarios)
    decision_resolved_requirements = sum(
        row[
            "decision_resolved_requirement_count"]
        for row in scenarios)
    threat_coverage = (
        float(supported_threats)
        / max(1, total_threats))
    operation_edge_coverage = (
        float(supported_requirements)
        / max(
            1,
            total_requirements))
    candidate_edge_coverage = (
        float(
            candidate_edge_requirements)
        / max(
            1,
            total_requirements))
    grounded_operation_coverage = (
        float(
            grounded_operations)
        / max(
            1,
            total_operations))
    decision_resolution_coverage = (
        float(
            decision_resolved_requirements)
        / max(
            1,
            total_requirements))
    timing = _summary(
        replay_latency)
    safety_metrics = (
        "actor_conflicts",
        "city_production_conflicts",
        "late_assignments",
        "sole_defender_violations",
    )
    mechanism_gates = {
        "b4_lower_uncovered_threats_than_b1":
            totals["B4"][
                "uncovered_threat_slots"]
            < totals["B1"][
                "uncovered_threat_slots"],
        "b4_lower_uncovered_threats_than_b3":
            totals["B4"][
                "uncovered_threat_slots"]
            < totals["B3"][
                "uncovered_threat_slots"],
        "exact_never_worse_than_greedy":
            exact_never_worse,
        "exact_status_for_all_fixtures":
            exact_status,
        "no_assignment_safety_violations":
            all(
                totals["B4"][name]
                == 0
                for name
                in safety_metrics),
        "typed_operation_evaluation_at_least_90_percent":
            grounded_operation_coverage
            >= 0.90,
        "decision_resolved_requirements_at_least_90_percent":
            decision_resolution_coverage
            >= 0.90,
        "p95_replay_compute_below_50_ms":
            timing["p95_ms"]
            <= 50.0,
        "threat_value_coverage_at_least_90_percent":
            threat_coverage
            >= 0.90,
    }
    result = {
        "arms": {
            "B1": {
                "description":
                    "frozen scalar PF-v2 plus packet readout over captured candidates",
                **totals["B1"],
            },
            "B2": {
                "description":
                    "best typed supported defence edge with one-action capacity",
                **totals["B2"],
            },
            "B3": {
                "description":
                    "typed identity-aware greedy assignment with one-action readout",
                **totals["B3"],
            },
            "B4": {
                "description":
                    "typed bounded-exact assignment with one-action readout",
                **totals["B4"],
            },
        },
        "assignment_arms": {
            "B3": {
                "description":
                    "typed identity-aware greedy intent assignment before one-action readout",
                **assignment_totals[
                    "B3"],
            },
            "B4": {
                "description":
                    "typed bounded-exact intent assignment before one-action readout",
                **assignment_totals[
                    "B4"],
            },
            "warning":
                "Intent assignments are not credited as executed operations; headline arm metrics include only one current-action readout per fixture.",
        },
        "claim_status":
            "captured-replay-diagnostic-only",
        "coverage": {
            "actionable_requirement_fraction":
                operation_edge_coverage,
            "candidate_edge_fraction":
                candidate_edge_coverage,
            "candidate_edge_requirement_count":
                candidate_edge_requirements,
            "decision_resolved_requirement_count":
                decision_resolved_requirements,
            "decision_resolved_requirement_fraction":
                decision_resolution_coverage,
            "grounded_operation_count":
                grounded_operations,
            "grounded_operation_evaluation_fraction":
                grounded_operation_coverage,
            "operation_edge_fraction":
                operation_edge_coverage,
            "operation_support_reasons":
                dict(sorted(
                    operation_support_reasons
                    .items())),
            "operation_types":
                dict(sorted(
                    operation_types
                    .items())),
            "protected_union_added_count":
                sum(
                    row[
                        "protected_union_added_count"]
                    for row in
                    scenarios),
            "supported_requirement_count":
                supported_requirements,
            "supported_threat_count":
                supported_threats,
            "threat_support_reasons":
                dict(sorted(
                    threat_support_reasons
                    .items())),
            "threat_eta_bases":
                dict(sorted(
                    threat_eta_bases
                    .items())),
            "threat_eta_advance_turns":
                {
                    str(turns): count
                    for turns, count
                    in sorted(
                        threat_eta_advance_turns
                        .items())
                },
            "threat_unit_classes":
                dict(sorted(
                    threat_unit_classes
                    .items())),
            "threat_unit_types":
                dict(sorted(
                    threat_unit_types
                    .items())),
            "threat_value_fraction":
                threat_coverage,
            "total_requirement_count":
                total_requirements,
            "total_operation_count":
                total_operations,
            "total_threat_count":
                total_threats,
        },
        "factual_outcomes": {
            "observed_city_losses_at_threat_deadline":
                factual_city_losses,
            "unresolved_city_outcomes":
                unresolved_city_outcomes,
            "warning":
                "Factual outcomes resolve source-run observations only; they are not counterfactual B2/B3/B4 outcomes.",
        },
        "fixture_count":
            len(fixtures),
        "fixture_manifest_hash":
            hash_value,
        "gdo4_exit_gate_passed":
            all(
                mechanism_gates.values())
            and all(
                fixture[
                    "authority"][
                        "policy_authority_eligible"]
                for fixture, _snapshot_value,
                _candidates in fixtures),
        "mechanism_gates":
            mechanism_gates,
        "policy_authority": False,
        "policy_authority_blockers": [
            message
            for available, message in (
                (
                    all(
                        fixture[
                            "authority"].get(
                                "full_legal_action_set_available",
                                False)
                        for fixture,
                        _snapshot_value,
                        _candidates
                        in fixtures),
                    "captured event snapshots omit the complete legal-action set",
                ),
                (
                    all(
                        fixture[
                            "authority"].get(
                                "map_wrap_metadata_available",
                                False)
                        for fixture,
                        _snapshot_value,
                        _candidates
                        in fixtures),
                    "captured event snapshots omit map-wrap metadata",
                ),
                (
                    all(
                        fixture[
                            "authority"].get(
                                "movement_runtime_fields_available",
                                False)
                        for fixture,
                        _snapshot_value,
                        _candidates
                        in fixtures),
                    "captured event units omit movement transport/done state",
                ),
                (
                    all(
                        fixture[
                            "authority"].get(
                                "movement_action_metadata_available",
                                False)
                        for fixture,
                        _snapshot_value,
                        _candidates
                        in fixtures),
                    "captured legal moves omit movement cost or transport metadata",
                ),
                (
                    all(
                        fixture[
                            "authority"].get(
                                "native_movement_routes_available",
                                False)
                        for fixture,
                        _snapshot_value,
                        _candidates
                        in fixtures),
                    "captured snapshots omit exact native movement routes",
                ),
                (
                    False,
                    "threat ETA lacks native gameplay parity",
                ),
                (
                    False,
                    "counterfactual operation outcomes are unavailable",
                ),
            )
            if not available
        ],
        "replay_compute":
            timing,
        "ruleset": {
            "compiler_version":
                ruleset_ir
                .compiler_version,
            "ir_sha256":
                structural_hash(
                    ruleset_ir
                    .to_dict()),
            "ruleset":
                ruleset_ir.ruleset,
            "source_sha256":
                structural_hash(
                    ruleset_ir
                    .source_hashes),
        },
        "scenarios":
            scenarios,
        "schema_version": "1.0",
        "timing_iterations":
            int(timing_iterations),
        "validation_passed": all((
            manifest[
                "fixture_count"]
            == len(fixtures),
            exact_status,
            exact_never_worse,
            totals["B4"][
                "actor_conflicts"] == 0,
            totals["B4"][
                "city_production_conflicts"] == 0,
            totals["B4"][
                "late_assignments"] == 0,
            totals["B4"][
                "sole_defender_violations"]
            == 0,
        )),
    }
    result["report_hash"] = (
        structural_hash(
            result))
    return result


def main():
    parser = argparse.ArgumentParser(
        description=__doc__)
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--ruleset-root",
        default=DEFAULT_RULESET_ROOT)
    parser.add_argument(
        "--timing-iterations",
        type=int, default=100)
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    if arguments.timing_iterations < 1:
        parser.error(
            "timing iterations must be positive")
    result = run(
        os.path.abspath(
            arguments.manifest),
        os.path.abspath(
            arguments.ruleset_root),
        arguments.timing_iterations)
    output = os.path.abspath(
        arguments.output)
    os.makedirs(
        os.path.dirname(output),
        exist_ok=True)
    with open(
            output, "w",
            encoding="utf-8") as stream:
        json.dump(
            result, stream,
            indent=2,
            sort_keys=True)
        stream.write("\n")
    print(json.dumps({
        "gdo4_exit_gate_passed":
            result[
                "gdo4_exit_gate_passed"],
        "output": output,
        "report_hash":
            result[
                "report_hash"],
        "validation_passed":
            result[
                "validation_passed"],
    }, sort_keys=True))
    return (
        0
        if result[
            "validation_passed"]
        else 1)


if __name__ == "__main__":
    sys.exit(main())
