"""Query-only LLM state summaries; raw proxy DTOs never cross this module."""

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryStateSummary:
    snapshot_id: str
    turn: int
    phase: str
    player_id: int
    known_techs: tuple
    research: dict
    economy: dict
    cities: tuple
    units: tuple
    visible_enemy_units: tuple
    map_summary: dict
    legal_action_kinds: tuple
    diagnostics: tuple

    def to_dict(self):
        return {
            "cities": [dict(item) for item in self.cities],
            "diagnostics": list(self.diagnostics), "economy": dict(self.economy),
            "known_techs": list(self.known_techs),
            "legal_action_kinds": list(self.legal_action_kinds),
            "map_summary": dict(self.map_summary), "phase": self.phase,
            "player_id": self.player_id, "research": dict(self.research),
            "snapshot_id": self.snapshot_id, "turn": self.turn,
            "units": [dict(item) for item in self.units],
            "visible_enemy_units": [dict(item) for item in self.visible_enemy_units],
        }


class StateSummaryService(object):
    def __init__(self, snapshot_store):
        self._store = snapshot_store

    def query(self, game_id, player_id):
        snapshot = self._store.current(game_id, player_id)
        if snapshot is None:
            raise KeyError("no current snapshot")
        diagnostics = [value for value in (
            snapshot.ruleset_diagnostic, snapshot.research.diagnostic,
            snapshot.economy.diagnostic) if value]
        diagnostics.extend(city.buildability_diagnostic for city in snapshot.cities
                           if city.buildability_diagnostic)
        return QueryStateSummary(
            snapshot_id=snapshot.snapshot_id, turn=snapshot.turn, phase=snapshot.phase,
            player_id=snapshot.player_id, known_techs=snapshot.research.known_techs,
            research={"target": snapshot.research.target_name,
                      "progress": snapshot.research.progress,
                      "cost": snapshot.research.cost,
                      "beakers_per_turn": snapshot.research.beakers_per_turn},
            economy={
                "gold": snapshot.economy.gold,
                "gold_per_turn": snapshot.economy.gold_per_turn,
                "city_gold_surplus_per_turn": (
                    snapshot.economy.city_gold_surplus_per_turn),
                "gold_upkeep_reserve": (
                    snapshot.economy.gold_upkeep_reserve),
                "gold_upkeep_style": snapshot.economy.gold_upkeep_style,
                "unit_gold_upkeep": snapshot.economy.unit_gold_upkeep,
            },
            cities=tuple({"id": city.city_id, "name": city.name, "size": city.size,
                          "food_surplus": (
                              city.surplus[0] if city.surplus else None),
                          "production_kind": city.production_kind,
                          "production_value": city.production_value}
                         for city in snapshot.cities),
            units=tuple({"id": unit.unit_id, "type": unit.unit_type,
                         "x": unit.x, "y": unit.y, "moves_left": unit.moves_left,
                         "activity": unit.activity,
                         "homecity": unit.homecity,
                         "upkeep": list(unit.upkeep)}
                        for unit in snapshot.units),
            visible_enemy_units=tuple({
                "id": unit.unit_id, "owner": unit.owner, "type": unit.unit_type,
                "x": unit.x, "y": unit.y,
            } for unit in snapshot.visible_enemy_units),
            map_summary={"width": snapshot.map_width, "height": snapshot.map_height,
                         "known_huts": len(snapshot.known_hut_tile_ids),
                         "visible_tiles": len(snapshot.visible_tile_ids)},
            # Legal action documents remain opaque here; only the kinds derived
            # while the DTO normalizes those documents cross this boundary.
            legal_action_kinds=snapshot.legal_action_kinds,
            diagnostics=tuple(sorted(set(diagnostics))))
