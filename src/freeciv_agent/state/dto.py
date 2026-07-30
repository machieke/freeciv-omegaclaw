"""Strict normalization of freeciv-llm state into an authoritative snapshot."""

import copy
import hashlib
from dataclasses import dataclass

from ..events.schema import canonical_json_bytes
from .snapshot import (AuthoritativeSnapshot, BuildingState, CityState,
                       EconomicState, GovernmentState, PlayerScoreState,
                       ResearchState, SnapshotIdentity, UnitState)


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


def _canonical_actions(actions, player_id=None):
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
    valid = []
    kinds = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ContractError("legal action entries must be objects")
        if row.get("is_valid") is False:
            continue
        normalized = _executable_action(row, player_id=player_id)
        kind = normalized.get("action_type")
        if kind is not None:
            kinds.add(str(kind))
        valid.append(canonical_json_bytes(normalized).decode("utf-8"))
    return tuple(sorted(set(valid))), tuple(sorted(kinds))


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
                done_moving=_boolean(
                    row.get("done_moving"),
                    "unit.done_moving"))
            if owner == player_id:
                units.append(parsed)
            else:
                # CivCom contains only packet-visible foreign units for a player
                # connection. Preserve them as observations, never as own-state facts.
                visible_enemy_units.append(parsed)

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
        legal_json, legal_action_kinds = _canonical_actions(
            payload.get("legal_actions") if legal_actions is None else legal_actions,
            player_id=player_id)
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
            map_tiles=tuple(copy.deepcopy(tiles)), legal_action_json=legal_json,
            legal_actions_digest=legal_digest,
            legal_action_kinds=legal_action_kinds,
            government=government,
            own_score=own_score,
            opponent_scores=tuple(sorted(
                opponent_scores, key=lambda item: item.player_id))))

    def to_snapshot(self):
        return self.snapshot
