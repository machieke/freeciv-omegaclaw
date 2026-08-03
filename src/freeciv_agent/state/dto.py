"""Strict normalization of freeciv-llm state into an authoritative snapshot."""

import copy
import hashlib
from dataclasses import dataclass, replace

from ..events.schema import canonical_json_bytes
from .snapshot import (AuthoritativeSnapshot, BuildingState, CityState,
                       CombatActionProbabilityState, CombatProbabilityState,
                       EconomicState, GovernmentState, MovementRouteState,
                       PlayerScoreState, ResearchOptionState, ResearchState,
                       SnapshotIdentity, UnitState)


class ContractError(ValueError):
    pass


def _integer(value, field, required=False):
    if value is None:
        if required:
            raise ContractError("missing required integer {}".format(field))
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise ContractError("{} must be an integer".format(field))
    return int(value)


def _boolean(value, field, required=False):
    if value is None:
        if required:
            raise ContractError("missing required boolean {}".format(field))
        return None
    if not isinstance(value, bool):
        raise ContractError("{} must be a boolean".format(field))
    return value


def _collection(value, field):
    if value is None:
        return []
    if isinstance(value, dict):
        rows = list(value.values())
    elif isinstance(value, list):
        rows = value
    else:
        raise ContractError("{} must be an object or array".format(field))
    if not all(isinstance(row, dict) for row in rows):
        raise ContractError("{} entries must be objects".format(field))
    return rows


def _numbers(value, field):
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ContractError("{} must be an array".format(field))
    return tuple(_integer(item, field + "[]", required=True) for item in value)


def _action_rows(actions):
    if actions is None:
        raise ContractError("legal_actions is required for an executable snapshot")
    if isinstance(actions, list):
        rows = actions
    elif isinstance(actions, dict):
        rows = []
        for key in sorted(actions, key=str):
            value = actions[key]
            if isinstance(value, list):
                rows.extend(value)
            elif isinstance(value, dict):
                rows.append(value)
            else:
                raise ContractError("legal_actions.{} must be an object or array".format(key))
    else:
        raise ContractError("legal_actions must be an object or array")
    return rows


def _action_target_within_map(action, width, height):
    """Reject proxy-advertised spatial actions outside engine coordinates.

    The proxy's adjacent-action projection can briefly expose negative or
    over-bound coordinates at a non-wrapping map edge while still marking the
    row valid.  Civserver does not accept those coordinates, so they cannot be
    admitted to the trusted canonical legal-action set.  This deliberately
    validates the executable coordinate representation even on wrapping maps;
    an advertised wrapped action must already use canonical in-map coordinates
    before it can authorize execution.
    """
    target = action.get("target")
    if not isinstance(target, dict):
        return True
    x = target.get("x")
    y = target.get("y")
    if x is None and y is None:
        return True
    return bool(
        isinstance(x, int) and not isinstance(x, bool)
        and isinstance(y, int) and not isinstance(y, bool)
        and 0 <= x < width and 0 <= y < height)


def _canonical_actions(actions, player_id=None, map_width=None,
                       map_height=None):
    rows = _action_rows(actions)
    valid = []
    kinds = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ContractError("legal action entries must be objects")
        if row.get("is_valid") is False:
            continue
        normalized = _executable_action(row, player_id=player_id)
        if (map_width is not None and map_height is not None
                and not _action_target_within_map(
                    normalized, map_width, map_height)):
            continue
        kind = normalized.get("action_type")
        if kind is not None:
            kinds.add(str(kind))
        valid.append(canonical_json_bytes(normalized).decode("utf-8"))
    return tuple(sorted(set(valid))), tuple(sorted(kinds))


def _research_options(actions, player_id=None):
    """Retain advertised research metadata outside executable action bytes."""
    options = {}
    for row in _action_rows(actions):
        if not isinstance(row, dict):
            raise ContractError("legal action entries must be objects")
        if row.get("is_valid") is False:
            continue
        normalized = _executable_action(
            row, player_id=player_id)
        if normalized.get("action_type") != "tech_research":
            continue
        target = normalized.get("target")
        if not isinstance(target, dict) or not target.get("tech_name"):
            raise ContractError(
                "tech_research action is missing tech_name")
        tech_name = str(target["tech_name"])
        raw_target = row.get("target")
        raw_target = raw_target if isinstance(raw_target, dict) else {}
        # Historical snapshots already contain canonical execution commands
        # without proxy metadata.  They are legal actions, not authoritative
        # research-option records.  Preserve their frozen v1 identity and
        # fail closed on cost grounding.
        if (
                row.get("type") != "tech_research"
                and not any(
                    name in row or name in raw_target
                    for name in ("tech_id", "tech_cost"))
        ):
            continue
        tech_id = _integer(
            row.get("tech_id", raw_target.get("tech_id")),
            "legal_actions.tech_research.tech_id")
        tech_cost = _integer(
            row.get("tech_cost", raw_target.get("tech_cost")),
            "legal_actions.tech_research.tech_cost")
        if tech_id is not None and tech_id < 0:
            raise ContractError(
                "legal_actions.tech_research.tech_id must be non-negative")
        if tech_cost is not None and tech_cost < 0:
            raise ContractError(
                "legal_actions.tech_research.tech_cost must be non-negative")
        option = ResearchOptionState(
            tech_name=tech_name,
            tech_id=tech_id,
            tech_cost=tech_cost,
            action_json=canonical_json_bytes(
                normalized).decode("utf-8"),
            diagnostic=(
                None if tech_cost is not None
                else "advertised research option omitted tech_cost"))
        previous = options.get(tech_name)
        if previous is not None and previous != option:
            raise ContractError(
                "conflicting advertised research options for {}".format(
                    tech_name))
        options[tech_name] = option
    return tuple(sorted(
        options.values(),
        key=lambda option: (
            option.tech_name,
            -1 if option.tech_id is None else option.tech_id)))


def _city_governor_action(city_id, target):
    if not isinstance(target, dict):
        raise ContractError(
            "city_governor action is missing its bounded target")
    reserve = _integer(
        target.get("food_surplus_reserve"),
        "legal_actions.city_governor.target.food_surplus_reserve",
        required=True)
    if reserve < 0 or reserve > 10:
        raise ContractError(
            "city_governor food_surplus_reserve must be in 0..10")
    action_target = {"food_surplus_reserve": reserve}
    if "require_happy" in target:
        action_target["require_happy"] = _boolean(
            target.get("require_happy"),
            "legal_actions.city_governor.target.require_happy",
            required=True)
    return {
        "action_type": "city_governor",
        "city_id": _integer(
            city_id, "legal_actions.city_governor.city_id", required=True),
        "target": action_target,
    }


def _executable_action(row, player_id=None):
    """Translate proxy validator actions to its public action-message dialect."""
    if row.get("action_type"):
        normalized = copy.deepcopy(row)
        normalized.pop("reason", None)
        normalized.pop("is_valid", None)
        if (normalized.get("action_type") == "unit_move"
                and "settlement_site_eligible" in normalized):
            normalized["settlement_site_eligible"] = _boolean(
                normalized["settlement_site_eligible"],
                "legal_actions.unit_move.settlement_site_eligible",
                required=True)
        if normalized.get("action_type") == "unit_join_city":
            target = normalized.get("target")
            if not isinstance(target, dict):
                raise ContractError("unit_join_city action is missing target city")
            target["city_id"] = _integer(
                target.get("city_id"),
                "legal_actions.unit_join_city.target.city_id", required=True)
        if normalized.get("action_type") == "city_governor":
            return _city_governor_action(
                normalized.get("city_id", normalized.get("actor_id")),
                normalized.get("target"))
        return normalized
    kind = row.get("type")
    if kind == "city_governor":
        return _city_governor_action(
            row.get("city_id", row.get("actor_id")), row.get("target"))
    if kind == "tech_research":
        tech_name = row.get("tech_name")
        if not tech_name:
            raise ContractError("tech_research action is missing tech_name")
        normalized = {
            "action_type": "tech_research",
            "target": {"tech_name": str(tech_name)},
        }
        actor_id = row.get("actor_id", row.get("player_id", player_id))
        if actor_id is not None:
            normalized["actor_id"] = _integer(
                actor_id, "legal_actions.tech_research.actor_id", required=True)
        return normalized
    if kind == "government_change":
        target = row.get("target")
        if not isinstance(target, dict):
            target = {
                "government_id": row.get("government_id"),
                "government_name": row.get("government_name"),
            }
        government_id = _integer(
            target.get("government_id", row.get("government_id")),
            "legal_actions.government_change.target.government_id",
            required=True)
        government_name = target.get(
            "government_name", row.get("government_name"))
        if not government_name:
            raise ContractError(
                "government_change action is missing government_name")
        normalized = {
            "action_type": "government_change",
            "target": {
                "government_id": government_id,
                "government_name": str(government_name),
            },
        }
        actor_id = row.get("actor_id", row.get("player_id", player_id))
        if actor_id is not None:
            normalized["actor_id"] = _integer(
                actor_id,
                "legal_actions.government_change.actor_id", required=True)
        return normalized
    if kind == "player_rates":
        target = row.get("target")
        if not isinstance(target, dict):
            target = {
                "tax_rate": row.get("tax_rate"),
                "science_rate": row.get("science_rate"),
                "luxury_rate": row.get("luxury_rate"),
            }
        normalized = {
            "action_type": "player_rates",
            "target": {
                name: _integer(
                    target.get(name), "legal_actions.player_rates.target.{}".format(
                        name), required=True)
                for name in ("tax_rate", "science_rate", "luxury_rate")
            },
        }
        if sum(normalized["target"].values()) != 100:
            raise ContractError(
                "legal_actions.player_rates target rates must sum to 100")
        if any(
                value < 0 or value > 100 or value % 10
                for value in normalized["target"].values()):
            raise ContractError(
                "legal_actions.player_rates target rates must be 0..100 "
                "in increments of 10")
        actor_id = row.get("actor_id", row.get("player_id", player_id))
        if actor_id is not None:
            normalized["actor_id"] = _integer(
                actor_id, "legal_actions.player_rates.actor_id",
                required=True)
        return normalized
    if kind == "unit_move":
        target = row.get("target")
        params = row.get("params")
        if not isinstance(target, dict) and isinstance(params, dict):
            target = params.get("target")
        if not isinstance(target, dict) and row.get("dest_x") is not None:
            target = {"x": row.get("dest_x"), "y": row.get("dest_y")}
        if not isinstance(target, dict) or target.get("x") is None or target.get("y") is None:
            raise ContractError("unit_move action is missing target coordinates")
        normalized = {
            "action_type": "unit_move",
            "actor_id": _integer(
                row.get("unit_id", row.get("actor_id")),
                "legal_actions.unit_move.actor_id", required=True),
            "target": {
                "x": _integer(target.get("x"), "legal_actions.unit_move.target.x", True),
                "y": _integer(target.get("y"), "legal_actions.unit_move.target.y", True),
            },
        }
        site_eligible = row.get("settlement_site_eligible")
        if site_eligible is None and isinstance(params, dict):
            site_eligible = params.get("settlement_site_eligible")
        if site_eligible is not None:
            normalized["settlement_site_eligible"] = _boolean(
                site_eligible,
                "legal_actions.unit_move.settlement_site_eligible",
                required=True)
        movement_cost = row.get("movement_cost")
        if movement_cost is not None:
            normalized["movement_cost"] = _integer(
                movement_cost,
                "legal_actions.unit_move.movement_cost",
                required=True)
            if normalized["movement_cost"] <= 0:
                raise ContractError(
                    "unit_move movement_cost must be positive")
        transport_required = row.get(
            "transport_required")
        if transport_required is not None:
            normalized["transport_required"] = _boolean(
                transport_required,
                "legal_actions.unit_move.transport_required",
                required=True)
        return normalized
    if kind == "unit_build_city":
        return {
            "action_type": "unit_build_city",
            "actor_id": _integer(
                row.get("unit_id", row.get("actor_id")),
                "legal_actions.unit_build_city.actor_id", required=True),
        }
    if kind == "unit_action":
        action = str(row.get("action", ""))
        action_type = action if action.startswith("unit_") else "unit_" + action
        normalized = {
            "action_type": action_type,
            "actor_id": _integer(
                row.get("unit_id", row.get("actor_id")),
                "legal_actions.{}.actor_id".format(action_type), required=True),
        }
        params = row.get("params")
        if isinstance(params, dict) and params:
            # StateExtractor wraps positional action parameters as
            # ``params.target``.  The public LLM action handler expects those
            # coordinates directly under ``target``; retaining the wrapper
            # makes a proxy-advertised attack fail its own E235 validation.
            positional = params.get("target")
            if action_type == "unit_join_city":
                target = {}
                if params.get("city") is not None:
                    target["city"] = str(params["city"])
                target["city_id"] = _integer(
                    params.get("city_id"),
                    "legal_actions.unit_join_city.target.city_id", required=True)
                normalized["target"] = target
            elif (action_type in (
                    "unit_attack", "unit_suicide_attack", "unit_bombard",
                    "unit_capture", "unit_wipe", "unit_conquer_city",
                    "unit_nuke", "unit_nuke_city", "unit_nuke_units")
                    and isinstance(positional, dict)):
                target = copy.deepcopy(positional)
                for field in ("target_unit_id", "target_city_id"):
                    if field in params:
                        target[field] = copy.deepcopy(params[field])
                normalized["target"] = target
            else:
                normalized["target"] = copy.deepcopy(params)
        return normalized
    normalized = {"action_type": kind}
    if row.get("unit_id") is not None:
        normalized["actor_id"] = row["unit_id"]
    elif row.get("actor_id") is not None:
        normalized["actor_id"] = row["actor_id"]
    elif row.get("city_id") is not None:
        normalized["city_id"] = row["city_id"]
    for field in ("target", "production_kind", "production_value", "tech_id"):
        if field in row:
            normalized[field] = copy.deepcopy(row[field])
    return normalized


def _visibility(payload, map_data):
    explicit = payload.get("visible_tiles")
    if isinstance(explicit, list):
        result = []
        for item in explicit:
            if isinstance(item, dict):
                item = item.get("index", item.get("tile"))
            if item is None:
                raise ContractError(
                    "visible_tiles[] requires an exact tile index")
            result.append(_integer(item, "visible_tiles[]", required=True))
        return tuple(sorted(set(result)))
    if explicit is not None:
        raise ContractError("visible_tiles must be an array")
    visibility = map_data.get("visibility", {})
    if isinstance(visibility, dict):
        result = []
        for key, value in visibility.items():
            if not isinstance(value, bool):
                raise ContractError("map.visibility values must be booleans")
            if value:
                if (isinstance(key, str)
                        and key.isdigit()):
                    key = int(key)
                result.append(_integer(
                    key, "map.visibility tile index", required=True))
        return tuple(sorted(set(result)))
    if isinstance(visibility, list):
        if not all(isinstance(value, bool) for value in visibility):
            raise ContractError("map.visibility values must be booleans")
        return tuple(index for index, value in enumerate(visibility) if value)
    if visibility is not None:
        raise ContractError("map.visibility must be an object or array")
    return ()


def _map_tiles(value, width, height):
    if not isinstance(value, list):
        raise ContractError("map.tiles must be an array")
    tile_count = width * height
    normalized = []
    seen = set()
    for position, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (dict, int, float)):
            raise ContractError("map.tiles[] must be an object or tile index")
        row = {"index": item} if not isinstance(item, dict) else copy.deepcopy(item)
        index = _integer(
            row.get("index", row.get("tile")),
            "map.tiles[{}].index".format(position))
        x = _integer(row.get("x"), "map.tiles[{}].x".format(position))
        y = _integer(row.get("y"), "map.tiles[{}].y".format(position))
        if index is None:
            if x is None or y is None:
                raise ContractError(
                    "map.tiles[] requires index or exact x/y coordinates")
            index = y * width + x
        if index < 0 or index >= tile_count:
            raise ContractError("map.tiles[] index must be within the map")
        expected_x = index % width
        expected_y = index // width
        if ((x is not None and x != expected_x)
                or (y is not None and y != expected_y)):
            raise ContractError("map.tiles[] coordinates must match its index")
        if index in seen:
            raise ContractError("map.tiles[] contains a duplicate index")
        seen.add(index)
        row["index"] = index
        row["x"] = expected_x
        row["y"] = expected_y
        terrain_name = row.get(
            "terrain_name")
        if (terrain_name is not None
                and (
                    not isinstance(
                        terrain_name, str)
                    or not terrain_name)):
            raise ContractError(
                "map.tiles[].terrain_name must be non-empty or absent")
        terrain_class = row.get(
            "terrain_class")
        if (terrain_class is not None
                and terrain_class
                not in ("land", "ocean")):
            raise ContractError(
                "map.tiles[].terrain_class must be land, ocean, or absent")
        native_classes = row.get(
            "native_unit_classes")
        if native_classes is not None:
            if (not isinstance(
                    native_classes, list)
                    or any(
                        not isinstance(
                            value, str)
                        or not value
                        for value in
                        native_classes)
                    or native_classes
                    != sorted(set(
                        native_classes))):
                raise ContractError(
                    "map.tiles[].native_unit_classes must be unique sorted names")
        normalized.append(row)
    return tuple(sorted(normalized, key=lambda row: row["index"]))


@dataclass(frozen=True)
class ProxyStateDTO:
    """Validated transport DTO. Raw proxy data is not retained after conversion."""

    snapshot: AuthoritativeSnapshot

    @classmethod
    def parse(cls, game_id, source_seq, payload, legal_actions=None):
        if not isinstance(payload, dict):
            raise ContractError("proxy state must be an object")
        player_id = _integer(payload.get("player_id", payload.get("player_perspective")),
                             "player_id", required=True)
        turn = _integer(payload.get("turn", payload.get("game", {}).get("turn")),
                        "turn", required=True)
        phase = str(payload.get("phase", payload.get("game", {}).get("phase", "unknown")))
        game_packet = payload.get("game")
        game_packet = game_packet if isinstance(game_packet, dict) else {}
        game_over = _boolean(game_packet.get("is_over"), "game.is_over")
        game_over = game_over is True
        source_seq = _integer(source_seq, "source_seq", required=True)

        authoritative = payload.get("authoritative")
        authoritative = authoritative if isinstance(authoritative, dict) else {}
        player = authoritative.get("player") if isinstance(authoritative.get("player"), dict) else {}
        player_alive = _boolean(player.get("is_alive"), "player.is_alive")
        research_packet = (authoritative.get("research")
                           if isinstance(authoritative.get("research"), dict) else {})
        ruleset = authoritative.get("ruleset") if isinstance(authoritative.get("ruleset"), dict) else {}
        government_packet = (
            authoritative.get("government")
            if isinstance(authoritative.get("government"), dict) else {})
        economic = payload.get("economic") if isinstance(payload.get("economic"), dict) else {}

        techs = payload.get("techs", {})
        known = techs.get("player{}".format(player_id), []) if isinstance(techs, dict) else []
        if not isinstance(known, list) or not all(isinstance(item, str) for item in known):
            raise ContractError("techs.player{} must be an array of names".format(player_id))

        target_id = _integer(research_packet.get("researching"), "research.researching")
        target_name = research_packet.get("researching_name", economic.get("research_target"))
        if target_name == "":
            target_name = None
        progress = _integer(research_packet.get("bulbs_researched", economic.get("research")),
                            "research.bulbs_researched")
        research_cost = _integer(research_packet.get("researching_cost"),
                                 "research.researching_cost")
        beakers = _integer(research_packet.get("beakers_per_turn"),
                           "research.beakers_per_turn")
        gross_beakers = _integer(
            research_packet.get("gross_beakers_per_turn"),
            "research.gross_beakers_per_turn")
        tech_upkeep = _integer(
            research_packet.get("tech_upkeep"), "research.tech_upkeep")
        research_available = all(value is not None for value in (progress, beakers))
        research_diagnostic = None if research_available else (
            "proxy omitted authoritative research progress or beakers_per_turn")

        gold = _integer(player.get("gold", economic.get("gold")), "economy.gold")
        gold_per_turn = _integer(player.get("gold_per_turn", economic.get("gold_per_turn")),
                                 "economy.gold_per_turn")
        operating_gold_per_turn = _integer(
            player.get("operating_gold_per_turn"),
            "economy.operating_gold_per_turn")
        capitalization_gold_per_turn = _integer(
            player.get("capitalization_gold_per_turn"),
            "economy.capitalization_gold_per_turn")
        city_gold_surplus_per_turn = _integer(
            player.get(
                "city_gold_surplus_per_turn",
                player.get("gross_gold_per_turn", player.get("gold_income_per_turn"))),
            "economy.city_gold_surplus_per_turn")
        unit_gold_upkeep = _integer(
            player.get("unit_gold_upkeep"), "economy.unit_gold_upkeep")
        gold_upkeep_reserve = _integer(
            player.get("gold_upkeep_reserve", unit_gold_upkeep),
            "economy.gold_upkeep_reserve")
        gold_upkeep_style = player.get("gold_upkeep_style")
        if gold_upkeep_style is not None:
            gold_upkeep_style = str(gold_upkeep_style)
            if gold_upkeep_style not in ("City", "Mixed", "Nation"):
                raise ContractError(
                    "economy.gold_upkeep_style must be City, Mixed, or Nation")
        tax = _integer(player.get("tax"), "economy.tax")
        science = _integer(player.get("science"), "economy.science")
        luxury = _integer(player.get("luxury"), "economy.luxury")
        economy_available = (bool(authoritative) and "gold" in player
                             and "gold_per_turn" in player
                             and gold is not None and gold_per_turn is not None)
        economy_diagnostic = None if economy_available else (
            "proxy omitted authoritative gold stockpile or per-turn income")

        government_available = government_packet.get("available") is True
        government = GovernmentState(
            current_id=_integer(
                government_packet.get("current_id"),
                "government.current_id"),
            current_name=(
                str(government_packet["current_name"])
                if government_packet.get("current_name") else None),
            target_id=_integer(
                government_packet.get("target_id"),
                "government.target_id"),
            target_name=(
                str(government_packet["target_name"])
                if government_packet.get("target_name") else None),
            revolution_finishes=_integer(
                government_packet.get("revolution_finishes"),
                "government.revolution_finishes"),
            in_revolution=bool(_boolean(
                government_packet.get("in_revolution", False),
                "government.in_revolution", required=True)),
            selection_required=bool(_boolean(
                government_packet.get("selection_required", False),
                "government.selection_required", required=True)),
            available=government_available,
            diagnostic=(
                None if government_available else str(
                    government_packet.get("diagnostic")
                    or "proxy omitted authoritative government state")),
        )

        unit_rows = _collection(payload.get("units"), "units")
        units = []
        visible_enemy_units = []
        for row in unit_rows:
            owner = _integer(row.get("owner"), "unit.owner", required=True)
            parsed = UnitState(
                unit_id=_integer(row.get("id"), "unit.id", required=True), owner=owner,
                unit_type=str(row.get("type", row.get("utype", "unknown"))),
                type_id=_integer(row.get("type_id"), "unit.type_id"),
                tile=_integer(row.get("tile"), "unit.tile"),
                x=_integer(row.get("x"), "unit.x"), y=_integer(row.get("y"), "unit.y"),
                moves_left=_integer(row.get("moves_left", row.get("movesleft")), "unit.moves_left"),
                hp=_integer(row.get("hp"), "unit.hp"),
                activity=None if row.get("activity") is None else str(row.get("activity")),
                upkeep=_numbers(row.get("upkeep"), "unit.upkeep"),
                homecity=_integer(row.get("homecity"), "unit.homecity"),
                veteran=_integer(
                    row.get("veteran"), "unit.veteran"),
                transported=_boolean(
                    row.get("transported"), "unit.transported"),
                transported_by=_integer(
                    row.get("transported_by"),
                    "unit.transported_by"),
                carrying=_integer(
                    row.get("carrying"), "unit.carrying"),
                cargo_count=_integer(
                    row.get("cargo_count"), "unit.cargo_count"),
                done_moving=_boolean(
                    row.get("done_moving"),
                    "unit.done_moving"))
            if parsed.cargo_count is not None and parsed.cargo_count < 0:
                raise ContractError("unit.cargo_count must be non-negative")
            if owner == player_id:
                units.append(parsed)
            else:
                # CivCom contains only packet-visible foreign units for a player
                # connection. Preserve them as observations, never as own-state facts.
                visible_enemy_units.append(parsed)

        # PACKET_UNIT_INFO.carrying is the carried trade-goods type, not a
        # transport load.  The exact load of each own carrier is instead the
        # number of authoritative own units whose transported_by relation
        # names it.  Only derive zeroes when every own relation is complete;
        # otherwise absence would be mistaken for proof of a free seat.
        transport_relations_complete = all(
            unit.transported is not None
            and (unit.transported is not True
                 or (isinstance(unit.transported_by, int)
                     and not isinstance(unit.transported_by, bool)
                     and unit.transported_by > 0))
            for unit in units)
        if transport_relations_complete:
            cargo_counts = {}
            for unit in units:
                if unit.transported is True:
                    cargo_counts[unit.transported_by] = (
                        cargo_counts.get(unit.transported_by, 0) + 1)
            reconciled_units = []
            for unit in units:
                derived_count = cargo_counts.get(unit.unit_id, 0)
                if (unit.cargo_count is not None
                        and unit.cargo_count != derived_count):
                    raise ContractError(
                        "unit.cargo_count contradicts transported_by relations "
                        "for unit {}: {} != {}".format(
                            unit.unit_id, unit.cargo_count, derived_count))
                reconciled_units.append(replace(
                    unit, cargo_count=derived_count))
            units = reconciled_units

        city_rows = _collection(payload.get("cities"), "cities")
        cities = []
        for row in city_rows:
            owner = _integer(row.get("owner"), "city.owner", required=True)
            if owner != player_id:
                continue
            build_data = row.get("buildability")
            legacy_build = row.get("can_build")
            if isinstance(build_data, dict):
                build_available = build_data.get("available") is True
                build_rows = build_data.get("options", legacy_build or [])
                build_diag = build_data.get("diagnostic")
            else:
                build_available = isinstance(legacy_build, list)
                build_rows = legacy_build or []
                build_diag = None if build_available else "server buildability bitvector missing"
            if not isinstance(build_rows, list):
                raise ContractError("city buildability options must be an array")
            buildable = []
            for option in build_rows:
                if not isinstance(option, dict):
                    raise ContractError("city buildability option must be an object")
                kind = str(option.get("type", option.get("kind", "unknown")))
                item_id = _integer(option.get("id"), "city.buildable.id", required=True)
                buildable.append((kind, item_id, str(option.get("name", item_id))))
            buildings = []
            for improvement in _collection(
                    row.get("built_improvements"), "city.built_improvements"):
                improvement_id = _integer(
                    improvement.get("id", improvement.get("improvement_id")),
                    "city.built_improvements.id", required=True)
                buildings.append(BuildingState(
                    improvement_id=improvement_id,
                    name=str(improvement.get("name", improvement_id)),
                    upkeep=_integer(
                        improvement.get("upkeep"),
                        "city.built_improvements.upkeep")))
            governor = row.get("governor")
            governor_available = False
            governor_enabled = None
            governor_minimal_surplus = ()
            governor_factor = ()
            governor_require_happy = None
            governor_allow_disorder = None
            governor_max_growth = None
            governor_allow_specialists = None
            governor_happy_factor = None
            if governor is not None:
                if not isinstance(governor, dict):
                    raise ContractError("city.governor must be an object")
                governor_available = _boolean(
                    governor.get("available"),
                    "city.governor.available", required=True)
                governor_enabled = _boolean(
                    governor.get("enabled"), "city.governor.enabled")
                governor_minimal_surplus = _numbers(
                    governor.get("minimal_surplus"),
                    "city.governor.minimal_surplus")
                governor_factor = _numbers(
                    governor.get("factor"), "city.governor.factor")
                if governor_available and (
                        len(governor_minimal_surplus) != 6
                        or len(governor_factor) != 6):
                    raise ContractError(
                        "available city governor requires six-output arrays")
                governor_require_happy = _boolean(
                    governor.get("require_happy"),
                    "city.governor.require_happy")
                governor_allow_disorder = _boolean(
                    governor.get("allow_disorder"),
                    "city.governor.allow_disorder")
                governor_max_growth = _boolean(
                    governor.get("max_growth"),
                    "city.governor.max_growth")
                governor_allow_specialists = _boolean(
                    governor.get("allow_specialists"),
                    "city.governor.allow_specialists")
                governor_happy_factor = _integer(
                    governor.get("happy_factor"),
                    "city.governor.happy_factor")
            cities.append(CityState(
                city_id=_integer(row.get("id"), "city.id", required=True), owner=owner,
                name=str(row.get("name", "City")), tile=_integer(row.get("tile"), "city.tile"),
                x=_integer(row.get("x"), "city.x"), y=_integer(row.get("y"), "city.y"),
                size=_integer(row.get("size", row.get("population", 1)), "city.size", required=True),
                production_kind=_integer(row.get("production_kind"), "city.production_kind"),
                production_value=_integer(row.get("production_value"), "city.production_value"),
                food_stock=_integer(row.get("food_stock"), "city.food_stock"),
                shield_stock=_integer(row.get("shield_stock"), "city.shield_stock"),
                surplus=_numbers(row.get("surplus"), "city.surplus"),
                production=_numbers(row.get("prod", row.get("production")), "city.prod"),
                buildability_available=build_available,
                buildable=tuple(sorted(buildable)), buildability_diagnostic=build_diag,
                feeling_happy=_numbers(row.get("ppl_happy"), "city.ppl_happy"),
                feeling_content=_numbers(row.get("ppl_content"), "city.ppl_content"),
                feeling_unhappy=_numbers(row.get("ppl_unhappy"), "city.ppl_unhappy"),
                feeling_angry=_numbers(row.get("ppl_angry"), "city.ppl_angry"),
                disorder=_boolean(row.get("disorder"), "city.disorder"),
                was_happy=_boolean(row.get("was_happy"), "city.was_happy"),
                had_famine=_boolean(row.get("had_famine"), "city.had_famine"),
                unhappy_penalty=_numbers(
                    row.get("unhappy_penalty"), "city.unhappy_penalty"),
                usage=_numbers(row.get("usage"), "city.usage"),
                governor_available=governor_available,
                governor_enabled=governor_enabled,
                governor_minimal_surplus=governor_minimal_surplus,
                governor_factor=governor_factor,
                governor_require_happy=governor_require_happy,
                governor_allow_disorder=governor_allow_disorder,
                governor_max_growth=governor_max_growth,
                governor_allow_specialists=governor_allow_specialists,
                governor_happy_factor=governor_happy_factor,
                buildings=tuple(sorted(
                    buildings, key=lambda item: item.improvement_id))))

        score_packet = (
            authoritative.get("score")
            if isinstance(authoritative.get("score"), dict) else {})
        own_score = _integer(score_packet.get("own"), "score.own")
        if own_score is not None and own_score < 0:
            own_score = None
        opponent_scores = []
        for row in _collection(score_packet.get("opponents"), "score.opponents"):
            opponent_score = _integer(
                row.get("score"), "score.opponents.score")
            if opponent_score is not None and opponent_score < 0:
                opponent_score = None
            opponent_scores.append(PlayerScoreState(
                player_id=_integer(
                    row.get("player_id"), "score.opponents.player_id",
                    required=True),
                name=str(row.get("name", row.get("player_id", "Player"))),
                score=opponent_score,
                is_alive=_boolean(
                    row.get("is_alive"), "score.opponents.is_alive")))

        map_data = payload.get("map") if isinstance(payload.get("map"), dict) else {}
        width = _integer(map_data.get("width", 0), "map.width", required=True)
        height = _integer(map_data.get("height", 0), "map.height", required=True)
        wrap_x = _boolean(
            map_data.get("wrap_x"), "map.wrap_x")
        wrap_y = _boolean(
            map_data.get("wrap_y"), "map.wrap_y")
        topology_id = _integer(
            map_data.get("topology_id"),
            "map.topology_id")
        if topology_id is not None and topology_id < 0:
            raise ContractError(
                "map.topology_id must be non-negative")
        if width <= 0 or height <= 0:
            raise ContractError("map dimensions must be positive")
        tiles = _map_tiles(map_data.get("tiles", []), width, height)
        visible = _visibility(payload, map_data)
        known_hut_tiles = tuple(sorted(set(_numbers(
            authoritative.get("known_hut_tiles"),
            "authoritative.known_hut_tiles"))))
        tile_count = width * height
        if any(tile < 0 or tile >= tile_count for tile in visible):
            raise ContractError(
                "visible_tiles entries must be within the map")
        if any(tile < 0 or tile >= tile_count for tile in known_hut_tiles):
            raise ContractError(
                "authoritative.known_hut_tiles entries must be within the map")
        own_units_by_id = {
            unit.unit_id: unit for unit in units}
        movement_routes = []
        for row in _collection(
                authoritative.get("movement_routes"),
                "authoritative.movement_routes"):
            if row.get("schema_version") != "1.0":
                raise ContractError(
                    "movement route schema_version must be 1.0")
            if row.get("authority") != (
                    "freeciv-server-pathfinder"):
                raise ContractError(
                    "movement route authority must be the native server pathfinder")
            unit_id = _integer(
                row.get("unit_id"),
                "movement_route.unit_id",
                required=True)
            unit = own_units_by_id.get(unit_id)
            if unit is None:
                raise ContractError(
                    "movement route unit must be a current own unit")
            origin_tile = _integer(
                row.get("origin_tile"),
                "movement_route.origin_tile",
                required=True)
            destination_tile = _integer(
                row.get("destination_tile"),
                "movement_route.destination_tile",
                required=True)
            first_step_tile = _integer(
                row.get("first_step_tile"),
                "movement_route.first_step_tile",
                required=True)
            if any(
                    tile < 0 or tile >= tile_count
                    for tile in (
                        origin_tile,
                        destination_tile,
                        first_step_tile)):
                raise ContractError(
                    "movement route tiles must be within the map")
            route_turn = _integer(
                row.get("turn"),
                "movement_route.turn",
                required=True)
            route_source_seq = _integer(
                row.get("source_seq"),
                "movement_route.source_seq",
                required=True)
            moves_left_at_request = _integer(
                row.get("moves_left_at_request"),
                "movement_route.moves_left_at_request",
                required=True)
            transported_at_request = _boolean(
                row.get("transported_at_request"),
                "movement_route.transported_at_request",
                required=True)
            initially_transported = _boolean(
                row.get("initially_transported"),
                "movement_route.initially_transported",
                required=True)
            if (
                route_turn != turn
                or route_source_seq > source_seq
                or unit.tile != origin_tile
                or unit.moves_left != moves_left_at_request
                or unit.transported
                    is not transported_at_request
                or initially_transported
                    is not transported_at_request
            ):
                raise ContractError(
                    "movement route does not match the current unit revision")
            reachable = _boolean(
                row.get("reachable"),
                "movement_route.reachable",
                required=True)
            path_length = _integer(
                row.get("path_length"),
                "movement_route.path_length",
                required=True)
            path_directions = _numbers(
                row.get("path_directions"),
                "movement_route.path_directions")
            first_step_cost = _integer(
                row.get("first_step_movement_cost"),
                "movement_route.first_step_movement_cost",
                required=True)
            estimated_turns = _integer(
                row.get("estimated_turns"),
                "movement_route.estimated_turns",
                required=True)
            total_cost = _integer(
                row.get("total_movement_cost"),
                "movement_route.total_movement_cost",
                required=True)
            remaining = _integer(
                row.get("movement_points_remaining"),
                "movement_route.movement_points_remaining",
                required=True)
            if (
                path_length < 0
                or path_length != len(path_directions)
                or any(direction < -1 or direction > 7
                       for direction in path_directions)
                or min(
                    first_step_cost,
                    estimated_turns,
                    total_cost,
                    remaining,
                    moves_left_at_request) < 0
            ):
                raise ContractError(
                    "movement route numeric fields are inconsistent")
            if reachable:
                if (
                    path_length < 1
                    or first_step_cost < 1
                    or total_cost < first_step_cost
                ):
                    raise ContractError(
                        "reachable movement route requires a positive path and cost")
            elif (
                path_length != 0
                or path_directions
                or first_step_tile != origin_tile
                or first_step_cost != 0
                or estimated_turns != 0
                or total_cost != 0
            ):
                raise ContractError(
                    "unreachable movement route must carry an empty path")
            movement_routes.append(
                MovementRouteState(
                    unit_id=unit_id,
                    origin_tile=origin_tile,
                    destination_tile=destination_tile,
                    reachable=bool(reachable),
                    first_step_tile=first_step_tile,
                    first_step_movement_cost=first_step_cost,
                    path_length=path_length,
                    path_directions=path_directions,
                    estimated_turns=estimated_turns,
                    total_movement_cost=total_cost,
                    movement_points_remaining=remaining,
                    moves_left_at_request=moves_left_at_request,
                    transported_at_request=bool(
                        transported_at_request),
                    initially_transported=bool(
                        initially_transported),
                    turn=route_turn,
                    source_seq=route_source_seq))
        all_visible_units = tuple(units) + tuple(
            visible_enemy_units)

        def combat_revision(unit):
            return {
                "activity": unit.activity,
                "hp": unit.hp,
                "id": unit.unit_id,
                "moves_left": unit.moves_left,
                "owner": unit.owner,
                "tile": unit.tile,
                "transported": unit.transported,
                "transported_by":
                    unit.transported_by,
                "type_id": unit.type_id,
                "veteran": unit.veteran,
            }

        combat_probabilities = []
        combat_action_names = {
            24: "capture_units",
            45: "attack",
            46: "suicide_attack",
            49: "conquer_city",
            53: "bombard",
        }
        for row in _collection(
                authoritative.get(
                    "combat_probabilities"),
                "authoritative.combat_probabilities"):
            if row.get("schema_version") != "1.0":
                raise ContractError(
                    "combat probability schema_version must be 1.0")
            if row.get("authority") != (
                    "freeciv-server-action-probability"):
                raise ContractError(
                    "combat probability authority must be the native action subsystem")
            combat_player_id = _integer(
                row.get("player_id"),
                "combat_probability.player_id",
                required=True)
            if combat_player_id != player_id:
                raise ContractError(
                    "combat probability player must match the snapshot")
            actor_id = _integer(
                row.get("actor_unit_id"),
                "combat_probability.actor_unit_id",
                required=True)
            actor = own_units_by_id.get(
                actor_id)
            if actor is None:
                raise ContractError(
                    "combat probability actor must be a current own unit")
            actor_revision = row.get(
                "actor_revision")
            if (
                not isinstance(
                    actor_revision, dict)
                or actor_revision
                    != combat_revision(actor)
            ):
                raise ContractError(
                    "combat probability actor revision is stale")
            target_tile = _integer(
                row.get("target_tile_id"),
                "combat_probability.target_tile_id",
                required=True)
            if (
                target_tile < 0
                or target_tile >= tile_count):
                raise ContractError(
                    "combat probability target tile must be within the map")
            target_stack = _collection(
                row.get(
                    "target_stack_revision"),
                "combat_probability.target_stack_revision")
            target_unit_ids = tuple(
                _integer(
                    unit.get("id"),
                    "combat_probability.target_stack_revision.id",
                    required=True)
                for unit in target_stack)
            if (
                len(set(target_unit_ids))
                    != len(target_unit_ids)
                or tuple(sorted(
                    target_unit_ids))
                    != target_unit_ids
            ):
                raise ContractError(
                    "combat probability target stack must have sorted unique unit IDs")
            expected_stack = [
                combat_revision(unit)
                for unit in sorted(
                    all_visible_units,
                    key=lambda item:
                        item.unit_id)
                if unit.tile == target_tile
            ]
            if target_stack != expected_stack:
                raise ContractError(
                    "combat probability target stack revision is stale")
            selected_target_id = _integer(
                row.get("target_unit_id"),
                "combat_probability.target_unit_id",
                required=True)
            if (
                selected_target_id != 0
                and selected_target_id
                    not in target_unit_ids):
                raise ContractError(
                    "combat probability selected target must be visible on its target tile")
            action_probabilities = []
            seen_action_ids = set()
            for probability in _collection(
                    row.get(
                        "action_probabilities"),
                    "combat_probability.action_probabilities"):
                action_id = _integer(
                    probability.get(
                        "action_id"),
                    "combat_probability.action_probability.action_id",
                    required=True)
                action_name = str(
                    probability.get(
                        "action_name") or "")
                if (
                    action_id not in combat_action_names
                    or action_name
                        != combat_action_names[
                            action_id]
                    or action_id in
                        seen_action_ids
                ):
                    raise ContractError(
                        "combat action probability identity is invalid")
                seen_action_ids.add(
                    action_id)
                minimum = _integer(
                    probability.get("minimum"),
                    "combat_probability.action_probability.minimum",
                    required=True)
                maximum = _integer(
                    probability.get("maximum"),
                    "combat_probability.action_probability.maximum",
                    required=True)
                status = str(
                    probability.get("status")
                    or "")
                if status == "bounded":
                    if not (
                            0 <= minimum
                            <= maximum <= 200):
                        raise ContractError(
                            "bounded combat probability must be in 0..200")
                elif status == (
                        "not_applicable"):
                    if (minimum, maximum) != (
                            253, 0):
                        raise ContractError(
                            "not-applicable combat probability sentinel is invalid")
                elif status == (
                        "not_implemented"):
                    if (minimum, maximum) != (
                            254, 0):
                        raise ContractError(
                            "not-implemented combat probability sentinel is invalid")
                else:
                    raise ContractError(
                        "combat probability status is invalid")
                action_probabilities.append(
                    CombatActionProbabilityState(
                        action_id=action_id,
                        action_name=action_name,
                        minimum=minimum,
                        maximum=maximum,
                        status=status))
            if seen_action_ids != set(
                    combat_action_names):
                raise ContractError(
                    "combat probability must include the complete supported action subset")
            combat_turn = _integer(
                row.get("turn"),
                "combat_probability.turn",
                required=True)
            request_source_seq = _integer(
                row.get("request_source_seq"),
                "combat_probability.request_source_seq",
                required=True)
            response_source_seq = _integer(
                row.get("response_source_seq"),
                "combat_probability.response_source_seq",
                required=True)
            if (
                combat_turn != turn
                or not 0 <= request_source_seq
                    < response_source_seq
                    <= source_seq
            ):
                raise ContractError(
                    "combat probability source revision is inconsistent")
            if row.get(
                    "request_kind") != (
                    "background_refresh"):
                raise ContractError(
                    "combat probability request kind is invalid")
            combat_probabilities.append(
                CombatProbabilityState(
                    player_id=combat_player_id,
                    actor_unit_id=actor_id,
                    target_tile_id=target_tile,
                    target_unit_id=selected_target_id,
                    target_city_id=_integer(
                        row.get(
                            "target_city_id"),
                        "combat_probability.target_city_id",
                        required=True),
                    target_extra_id=_integer(
                        row.get(
                            "target_extra_id"),
                        "combat_probability.target_extra_id",
                        required=True),
                    target_unit_ids=(
                        target_unit_ids),
                    action_probabilities=tuple(
                        sorted(
                            action_probabilities,
                            key=lambda item:
                                item.action_id)),
                    actor_revision_digest=hashlib.sha256(
                        canonical_json_bytes(
                            actor_revision)
                    ).hexdigest(),
                    target_stack_revision_digest=hashlib.sha256(
                        canonical_json_bytes(
                            target_stack)
                    ).hexdigest(),
                    turn=combat_turn,
                    request_source_seq=(
                        request_source_seq),
                    response_source_seq=(
                        response_source_seq)))
        action_source = (
            payload.get("legal_actions")
            if legal_actions is None else legal_actions)
        legal_json, legal_action_kinds = _canonical_actions(
            action_source,
            player_id=player_id,
            map_width=width,
            map_height=height)
        research_options = _research_options(
            action_source, player_id=player_id)
        legal_digest = hashlib.sha256("\n".join(legal_json).encode("utf-8")).hexdigest()

        ruleset_ready = ruleset.get("ready") is True
        if not ruleset_ready:
            ruleset_diagnostic = str(ruleset.get(
                "diagnostic", "proxy omitted authoritative ruleset-ready packet state"))
        else:
            ruleset_diagnostic = None

        body = {
            "cities": [city.to_dict() for city in sorted(cities, key=lambda item: item.city_id)],
            "economy": EconomicState(
                gold, gold_per_turn, tax, science, luxury,
                economy_available, economy_diagnostic,
                city_gold_surplus_per_turn=city_gold_surplus_per_turn,
                unit_gold_upkeep=unit_gold_upkeep,
                gold_upkeep_reserve=gold_upkeep_reserve,
                gold_upkeep_style=gold_upkeep_style,
                operating_gold_per_turn=operating_gold_per_turn,
                capitalization_gold_per_turn=(
                    capitalization_gold_per_turn)).to_dict(),
            "government": government.to_dict(),
            "game_id": str(game_id), "legal_action_json": list(legal_json),
            "map": {"height": height,
                    "known_hut_tile_ids": list(known_hut_tiles),
                    "tiles": list(tiles), "visible_tile_ids": list(visible),
                    "width": width},
            "game_over": game_over, "phase": phase,
            "player_alive": player_alive, "player_id": player_id,
            "research": ResearchState(tuple(sorted(set(known))), target_id, target_name,
                                      progress, research_cost, beakers,
                                      research_available, research_diagnostic,
                                      gross_beakers_per_turn=gross_beakers,
                                      tech_upkeep=tech_upkeep).to_dict(),
            "score": {
                "opponents": [
                    row.to_dict() for row in sorted(
                        opponent_scores, key=lambda item: item.player_id)
                ],
                "own": own_score,
            },
            "ruleset_ready": ruleset_ready, "turn": turn,
            "units": [unit.to_dict() for unit in sorted(units, key=lambda item: item.unit_id)],
            "visible_enemy_units": [unit.to_dict() for unit in sorted(
                visible_enemy_units, key=lambda item: item.unit_id)],
        }
        if wrap_x is not None:
            body["map"][
                "wrap_x"] = wrap_x
        if wrap_y is not None:
            body["map"][
                "wrap_y"] = wrap_y
        if topology_id is not None:
            body["map"][
                "topology_id"] = (
                    topology_id)
        # Preserve the frozen snapshot identity for every pre-route and
        # route-disabled input. Exact route bytes join the identity only when
        # the optional collection is actually present.
        if movement_routes:
            body["movement_routes"] = [
                route.to_dict()
                for route in sorted(
                    movement_routes,
                    key=lambda item: (
                        item.unit_id,
                        item.destination_tile))
            ]
        if combat_probabilities:
            body["combat_probabilities"] = [
                result.to_dict()
                for result in sorted(
                    combat_probabilities,
                    key=lambda item: (
                        item.actor_unit_id,
                        item.target_tile_id))
            ]
        if research_options:
            body["research_options"] = [
                option.to_dict()
                for option in research_options
            ]
        state_hash = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
        identity = SnapshotIdentity(str(game_id), turn, source_seq, state_hash)
        return cls(AuthoritativeSnapshot(
            identity=identity, player_id=player_id, player_alive=player_alive, phase=phase,
            ruleset_ready=ruleset_ready, ruleset_diagnostic=ruleset_diagnostic,
            research=ResearchState(tuple(sorted(set(known))), target_id, target_name,
                                   progress, research_cost, beakers,
                                   research_available, research_diagnostic,
                                   gross_beakers_per_turn=gross_beakers,
                                   tech_upkeep=tech_upkeep),
            economy=EconomicState(
                gold, gold_per_turn, tax, science, luxury,
                economy_available, economy_diagnostic,
                city_gold_surplus_per_turn=city_gold_surplus_per_turn,
                unit_gold_upkeep=unit_gold_upkeep,
                gold_upkeep_reserve=gold_upkeep_reserve,
                gold_upkeep_style=gold_upkeep_style,
                operating_gold_per_turn=operating_gold_per_turn,
                capitalization_gold_per_turn=capitalization_gold_per_turn),
            cities=tuple(sorted(cities, key=lambda item: item.city_id)),
            units=tuple(sorted(units, key=lambda item: item.unit_id)),
            visible_enemy_units=tuple(sorted(
                visible_enemy_units, key=lambda item: item.unit_id)),
            visible_tile_ids=visible, known_hut_tile_ids=known_hut_tiles,
            map_width=width, map_height=height, game_over=game_over,
            map_wrap_x=wrap_x, map_wrap_y=wrap_y,
            map_topology_id=topology_id,
            movement_routes=tuple(sorted(
                movement_routes,
                key=lambda item: (
                    item.unit_id,
                    item.destination_tile))),
            combat_probabilities=tuple(
                sorted(
                    combat_probabilities,
                    key=lambda item: (
                        item.actor_unit_id,
                        item.target_tile_id))),
            research_options=research_options,
            map_tiles=tuple(copy.deepcopy(tiles)), legal_action_json=legal_json,
            legal_actions_digest=legal_digest,
            legal_action_kinds=legal_action_kinds,
            government=government,
            own_score=own_score,
            opponent_scores=tuple(sorted(
                opponent_scores, key=lambda item: item.player_id))))

    def to_snapshot(self):
        return self.snapshot
