"""Strict reconstruction of immutable snapshots from state-snapshot events."""

import copy
import hashlib

from ..events.schema import canonical_json_bytes
from .snapshot import (
    AuthoritativeSnapshot,
    BuildingState,
    CityState,
    CombatActionProbabilityState,
    CombatProbabilityState,
    EconomicState,
    GovernmentState,
    MovementRouteState,
    PlayerScoreState,
    ResearchOptionState,
    ResearchState,
    SnapshotIdentity,
    UnitState,
)


class SnapshotReplayError(ValueError):
    """A recorded state event is incomplete or internally inconsistent."""


def _object(value, name):
    if not isinstance(value, dict):
        raise SnapshotReplayError("{} must be an object".format(name))
    return value


def _rows(value, name):
    if not isinstance(value, list) or any(
            not isinstance(row, dict) for row in value):
        raise SnapshotReplayError("{} must be an array of objects".format(name))
    return value


def _unit(row):
    return UnitState(
        unit_id=int(row["unit_id"]),
        owner=int(row["owner"]),
        unit_type=str(row["type"]),
        type_id=row.get("type_id"),
        tile=row.get("tile"),
        x=row.get("x"),
        y=row.get("y"),
        moves_left=row.get("moves_left"),
        hp=row.get("hp"),
        activity=row.get("activity"),
        upkeep=tuple(row.get("upkeep") or ()),
        homecity=row.get("homecity"),
        veteran=row.get("veteran"),
        transported=row.get("transported"),
        transported_by=row.get("transported_by"),
        carrying=row.get("carrying"),
        cargo_count=row.get("cargo_count"),
        done_moving=row.get("done_moving"),
    )


def _city(row):
    mood = _object(row.get("citizen_mood", {}), "city.citizen_mood")
    governor = _object(row.get("governor", {}), "city.governor")
    return CityState(
        city_id=int(row["city_id"]),
        owner=int(row["owner"]),
        name=str(row["name"]),
        tile=row.get("tile"),
        x=row.get("x"),
        y=row.get("y"),
        size=int(row["size"]),
        production_kind=row.get("production_kind"),
        production_value=row.get("production_value"),
        food_stock=row.get("food_stock"),
        shield_stock=row.get("shield_stock"),
        surplus=tuple(row.get("surplus") or ()),
        production=tuple(row.get("production") or ()),
        buildability_available=bool(row.get("buildability_available", False)),
        buildable=tuple(tuple(value) for value in row.get("buildable") or ()),
        buildability_diagnostic=row.get("buildability_diagnostic"),
        feeling_happy=tuple(mood.get("happy") or ()),
        feeling_content=tuple(mood.get("content") or ()),
        feeling_unhappy=tuple(mood.get("unhappy") or ()),
        feeling_angry=tuple(mood.get("angry") or ()),
        disorder=row.get("disorder"),
        was_happy=row.get("was_happy"),
        had_famine=row.get("had_famine"),
        unhappy_penalty=tuple(row.get("unhappy_penalty") or ()),
        usage=tuple(row.get("usage") or ()),
        governor_available=bool(governor.get("available", False)),
        governor_enabled=governor.get("enabled"),
        governor_minimal_surplus=tuple(
            governor.get("minimal_surplus") or ()),
        governor_factor=tuple(governor.get("factor") or ()),
        governor_require_happy=governor.get("require_happy"),
        governor_allow_disorder=governor.get("allow_disorder"),
        governor_max_growth=governor.get("max_growth"),
        governor_allow_specialists=governor.get("allow_specialists"),
        governor_happy_factor=governor.get("happy_factor"),
        buildings=tuple(BuildingState(
            int(value["improvement_id"]), str(value["name"]),
            value.get("upkeep"))
            for value in _rows(row.get("buildings", []), "city.buildings")),
    )


def _movement_route(row):
    values = dict(row)
    values["path_directions"] = tuple(values.get("path_directions") or ())
    return MovementRouteState(**values)


def _combat_probability(row):
    values = dict(row)
    values["target_unit_ids"] = tuple(values.get("target_unit_ids") or ())
    values["action_probabilities"] = tuple(
        CombatActionProbabilityState(**value)
        for value in _rows(
            values.get("action_probabilities", []),
            "grounded_context.combat_probabilities.action_probabilities"))
    return CombatProbabilityState(**values)


def snapshot_from_event(event):
    """Reconstruct the exact public snapshot represented by one event.

    Older captured events did not include ``grounded_context.phase``. They are
    accepted with the explicit non-authorizing ``captured-replay`` phase; every
    state field used by FDAS projectors still comes from the recorded payload.
    """
    event = _object(event, "state snapshot event")
    payload = _object(event.get("payload"), "state snapshot event.payload")
    own = _object(payload.get("own_state"), "state snapshot own_state")
    map_row = _object(payload.get("map"), "state snapshot map")
    grounded = _object(
        payload.get("grounded_context", {}),
        "state snapshot grounded_context")
    game_id = str(event.get("game_id", ""))
    if not game_id:
        raise SnapshotReplayError("state snapshot game_id is required")
    try:
        turn = int(event["turn"])
        source_seq = int(payload["source_seq"])
        player_id = int(payload["player_id"])
    except (KeyError, TypeError, ValueError):
        raise SnapshotReplayError(
            "state snapshot turn, source_seq, and player_id are required")
    state_hash = str(payload.get("state_hash", ""))
    if len(state_hash) != 64 or any(
            value not in "0123456789abcdef" for value in state_hash):
        raise SnapshotReplayError("state snapshot state_hash is invalid")
    identity = SnapshotIdentity(game_id, turn, source_seq, state_hash)
    if payload.get("snapshot_id") != identity.snapshot_id:
        raise SnapshotReplayError("state snapshot identity mismatch")

    research_row = _object(own.get("research"), "own_state.research")
    research = ResearchState(
        known_techs=tuple(research_row.get("known_techs") or ()),
        target_id=research_row.get("target_id"),
        target_name=research_row.get("target_name"),
        progress=research_row.get("progress"),
        cost=research_row.get("cost"),
        beakers_per_turn=research_row.get("beakers_per_turn"),
        available=bool(research_row.get("available", False)),
        diagnostic=research_row.get("diagnostic"),
        gross_beakers_per_turn=research_row.get("gross_beakers_per_turn"),
        tech_upkeep=research_row.get("tech_upkeep"),
    )
    economy_row = _object(own.get("economy"), "own_state.economy")
    economy = EconomicState(
        gold=economy_row.get("gold"),
        gold_per_turn=economy_row.get("gold_per_turn"),
        tax_rate=economy_row.get("tax_rate"),
        science_rate=economy_row.get("science_rate"),
        luxury_rate=economy_row.get("luxury_rate"),
        available=bool(economy_row.get("available", False)),
        diagnostic=economy_row.get("diagnostic"),
        city_gold_surplus_per_turn=economy_row.get(
            "city_gold_surplus_per_turn"),
        unit_gold_upkeep=economy_row.get("unit_gold_upkeep"),
        gold_upkeep_reserve=economy_row.get("gold_upkeep_reserve"),
        gold_upkeep_style=economy_row.get("gold_upkeep_style"),
        operating_gold_per_turn=economy_row.get("operating_gold_per_turn"),
        capitalization_gold_per_turn=economy_row.get(
            "capitalization_gold_per_turn"),
    )
    government_row = _object(
        own.get("government", {}), "own_state.government")
    government = GovernmentState(**dict(
        (name, government_row.get(name)) for name in (
            "current_id", "current_name", "target_id", "target_name",
            "revolution_finishes", "in_revolution", "selection_required",
            "available", "diagnostic")))

    if ("legal_actions" not in grounded
            and payload.get("legal_actions_digest") != hashlib.sha256(
                b"").hexdigest()):
        raise SnapshotReplayError(
            "state snapshot lacks replayable grounded legal actions")
    legal_actions = _rows(
        grounded.get("legal_actions", []),
        "grounded_context.legal_actions")
    legal_json = tuple(sorted(set(
        canonical_json_bytes(value).decode("utf-8")
        for value in legal_actions)))
    legal_digest = hashlib.sha256(
        "\n".join(legal_json).encode("utf-8")).hexdigest()
    claimed_legal_digest = str(payload.get("legal_actions_digest", ""))
    if claimed_legal_digest != legal_digest:
        raise SnapshotReplayError("state snapshot legal action digest mismatch")

    grounded_own_units = grounded.get("own_units")
    unit_rows = (
        _rows(grounded_own_units, "grounded_context.own_units")
        if grounded_own_units is not None else
        _rows(own.get("units", []), "own_state.units"))
    grounded_enemy_units = grounded.get("visible_enemy_units")
    enemy_rows = (
        _rows(
            grounded_enemy_units,
            "grounded_context.visible_enemy_units")
        if grounded_enemy_units is not None else
        _rows(
            map_row.get("visible_enemy_units", []),
            "map.visible_enemy_units"))
    topology = _object(
        grounded.get("map_topology", {}),
        "grounded_context.map_topology")
    scores = _object(own.get("score", {}), "own_state.score")
    opponents = tuple(PlayerScoreState(
        int(value["player_id"]), str(value.get("name", "")),
        value.get("score"), value.get("is_alive"))
        for value in _rows(scores.get("opponents", []), "score.opponents"))
    research_options = tuple(ResearchOptionState(
        tech_name=str(value["tech_name"]),
        tech_id=value.get("tech_id"),
        tech_cost=value.get("tech_cost"),
        action_json=str(value["action_json"]),
        diagnostic=value.get("diagnostic"))
        for value in _rows(
            grounded.get("research_options", []),
            "grounded_context.research_options"))
    snapshot = AuthoritativeSnapshot(
        identity=identity,
        player_id=player_id,
        player_alive=own.get("player_alive"),
        phase=str(grounded.get("phase", "captured-replay")),
        ruleset_ready=bool(own.get("ruleset_ready", False)),
        ruleset_diagnostic=own.get("ruleset_diagnostic"),
        research=research,
        economy=economy,
        cities=tuple(sorted(
            (_city(value) for value in _rows(
                own.get("cities", []), "own_state.cities")),
            key=lambda value: value.city_id)),
        units=tuple(sorted(
            (_unit(value) for value in unit_rows),
            key=lambda value: value.unit_id)),
        visible_enemy_units=tuple(sorted(
            (_unit(value) for value in enemy_rows),
            key=lambda value: value.unit_id)),
        visible_tile_ids=tuple(map_row.get("visible_tile_ids") or ()),
        known_hut_tile_ids=tuple(map_row.get("known_hut_tile_ids") or ()),
        map_width=int(map_row.get("width", 0)),
        map_height=int(map_row.get("height", 0)),
        map_tiles=tuple(copy.deepcopy(map_row.get("tiles") or ())),
        legal_action_json=legal_json,
        legal_actions_digest=legal_digest,
        legal_action_kinds=tuple(sorted(set(
            str(value.get("action_type", ""))
            for value in legal_actions if value.get("action_type")))),
        government=government,
        game_over=bool(own.get("game_over", False)),
        own_score=scores.get("own"),
        opponent_scores=tuple(sorted(
            opponents, key=lambda value: value.player_id)),
        map_wrap_x=topology.get("wrap_x"),
        map_wrap_y=topology.get("wrap_y"),
        map_topology_id=topology.get("topology_id"),
        movement_routes=tuple(sorted(
            (_movement_route(value) for value in _rows(
                grounded.get("movement_routes", []),
                "grounded_context.movement_routes")),
            key=lambda value: (value.unit_id, value.destination_tile))),
        combat_probabilities=tuple(sorted(
            (_combat_probability(value) for value in _rows(
                grounded.get("combat_probabilities", []),
                "grounded_context.combat_probabilities")),
            key=lambda value: (
                value.actor_unit_id, value.target_tile_id))),
        research_options=research_options,
    )
    return snapshot
