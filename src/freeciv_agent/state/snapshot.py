"""Immutable domain snapshot types derived from proxy packet state."""

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class SnapshotIdentity:
    game_id: str
    turn: int
    source_seq: int
    state_hash: str

    @property
    def snapshot_id(self):
        return "{}:{}:{}:{}".format(
            self.game_id, self.turn, self.source_seq, self.state_hash[:16])

    def to_dict(self):
        return {
            "game_id": self.game_id,
            "snapshot_id": self.snapshot_id,
            "source_seq": self.source_seq,
            "state_hash": self.state_hash,
            "turn": self.turn,
        }


@dataclass(frozen=True)
class ResearchState:
    known_techs: Tuple[str, ...]
    target_id: Optional[int]
    target_name: Optional[str]
    progress: Optional[int]
    cost: Optional[int]
    beakers_per_turn: Optional[int]
    available: bool
    diagnostic: Optional[str] = None

    def to_dict(self):
        return {
            "available": self.available,
            "beakers_per_turn": self.beakers_per_turn,
            "cost": self.cost,
            "diagnostic": self.diagnostic,
            "known_techs": list(self.known_techs),
            "progress": self.progress,
            "target_id": self.target_id,
            "target_name": self.target_name,
        }


@dataclass(frozen=True)
class EconomicState:
    gold: Optional[int]
    gold_per_turn: Optional[int]
    tax_rate: Optional[int]
    science_rate: Optional[int]
    luxury_rate: Optional[int]
    available: bool
    diagnostic: Optional[str] = None

    def to_dict(self):
        return {
            "available": self.available,
            "diagnostic": self.diagnostic,
            "gold": self.gold,
            "gold_per_turn": self.gold_per_turn,
            "luxury_rate": self.luxury_rate,
            "science_rate": self.science_rate,
            "tax_rate": self.tax_rate,
        }


@dataclass(frozen=True)
class GovernmentState:
    current_id: Optional[int] = None
    current_name: Optional[str] = None
    target_id: Optional[int] = None
    target_name: Optional[str] = None
    revolution_finishes: Optional[int] = None
    in_revolution: bool = False
    selection_required: bool = False
    available: bool = False
    diagnostic: Optional[str] = None

    def to_dict(self):
        return {
            "available": self.available,
            "current_id": self.current_id,
            "current_name": self.current_name,
            "diagnostic": self.diagnostic,
            "in_revolution": self.in_revolution,
            "revolution_finishes": self.revolution_finishes,
            "selection_required": self.selection_required,
            "target_id": self.target_id,
            "target_name": self.target_name,
        }


@dataclass(frozen=True)
class UnitState:
    unit_id: int
    owner: int
    unit_type: str
    type_id: Optional[int]
    tile: Optional[int]
    x: Optional[int]
    y: Optional[int]
    moves_left: Optional[int]
    hp: Optional[int]
    activity: Optional[str]
    upkeep: Tuple[int, ...] = field(default_factory=tuple)
    homecity: Optional[int] = None

    def to_dict(self):
        return {
            "activity": self.activity, "hp": self.hp, "moves_left": self.moves_left,
            "homecity": self.homecity,
            "owner": self.owner, "tile": self.tile, "type": self.unit_type,
            "type_id": self.type_id, "unit_id": self.unit_id,
            "upkeep": list(self.upkeep), "x": self.x, "y": self.y,
        }


@dataclass(frozen=True)
class CityState:
    city_id: int
    owner: int
    name: str
    tile: Optional[int]
    x: Optional[int]
    y: Optional[int]
    size: int
    production_kind: Optional[int]
    production_value: Optional[int]
    food_stock: Optional[int]
    shield_stock: Optional[int]
    surplus: Tuple[int, ...]
    production: Tuple[int, ...]
    buildability_available: bool
    buildable: Tuple[Tuple[str, int, str], ...]
    buildability_diagnostic: Optional[str] = None
    feeling_happy: Tuple[int, ...] = field(default_factory=tuple)
    feeling_content: Tuple[int, ...] = field(default_factory=tuple)
    feeling_unhappy: Tuple[int, ...] = field(default_factory=tuple)
    feeling_angry: Tuple[int, ...] = field(default_factory=tuple)
    disorder: Optional[bool] = None
    was_happy: Optional[bool] = None
    had_famine: Optional[bool] = None
    unhappy_penalty: Tuple[int, ...] = field(default_factory=tuple)
    usage: Tuple[int, ...] = field(default_factory=tuple)

    def to_dict(self):
        return {
            "buildability_available": self.buildability_available,
            "buildability_diagnostic": self.buildability_diagnostic,
            "buildable": [list(item) for item in self.buildable],
            "city_id": self.city_id, "food_stock": self.food_stock, "name": self.name,
            "owner": self.owner, "production": list(self.production),
            "production_kind": self.production_kind,
            "production_value": self.production_value, "shield_stock": self.shield_stock,
            "size": self.size, "surplus": list(self.surplus), "tile": self.tile,
            "citizen_mood": {
                "angry": list(self.feeling_angry),
                "content": list(self.feeling_content),
                "happy": list(self.feeling_happy),
                "unhappy": list(self.feeling_unhappy),
            },
            "disorder": self.disorder, "had_famine": self.had_famine,
            "unhappy_penalty": list(self.unhappy_penalty),
            "usage": list(self.usage), "was_happy": self.was_happy,
            "x": self.x, "y": self.y,
        }


@dataclass(frozen=True)
class AuthoritativeSnapshot:
    identity: SnapshotIdentity
    player_id: int
    player_alive: Optional[bool]
    phase: str
    ruleset_ready: bool
    ruleset_diagnostic: Optional[str]
    research: ResearchState
    economy: EconomicState
    cities: Tuple[CityState, ...]
    units: Tuple[UnitState, ...]
    visible_enemy_units: Tuple[UnitState, ...]
    visible_tile_ids: Tuple[int, ...]
    known_hut_tile_ids: Tuple[int, ...]
    map_width: int
    map_height: int
    map_tiles: Tuple[object, ...]
    legal_action_json: Tuple[str, ...]
    legal_actions_digest: str
    legal_action_kinds: Tuple[str, ...]
    government: GovernmentState = field(default_factory=GovernmentState)

    @property
    def snapshot_id(self):
        return self.identity.snapshot_id

    @property
    def turn(self):
        return self.identity.turn

    def city(self, city_id):
        city_id = int(city_id)
        return next((city for city in self.cities if city.city_id == city_id), None)

    def unit(self, unit_id):
        unit_id = int(unit_id)
        return next((unit for unit in self.units if unit.unit_id == unit_id), None)

    def visible_enemy_unit(self, unit_id):
        unit_id = int(unit_id)
        return next((unit for unit in self.visible_enemy_units
                     if unit.unit_id == unit_id), None)

    def own_state_dict(self):
        return {
            "cities": [city.to_dict() for city in self.cities],
            "economy": self.economy.to_dict(),
            "government": self.government.to_dict(),
            "legal_actions_digest": self.legal_actions_digest,
            "player_alive": self.player_alive,
            "research": self.research.to_dict(),
            "ruleset_diagnostic": self.ruleset_diagnostic,
            "ruleset_ready": self.ruleset_ready,
            "units": [unit.to_dict() for unit in self.units],
        }

    def map_dict(self):
        tile_count = self.map_width * self.map_height
        coverage = (
            "complete" if tile_count and len(self.map_tiles) == tile_count
            else "partial" if self.map_tiles or self.visible_tile_ids
            else "dimensions_only")
        return {
            "coverage": {
                "status": coverage,
                "tile_records": len(self.map_tiles),
                "visible_tiles": len(self.visible_tile_ids),
            },
            "height": self.map_height,
            "known_hut_tile_ids": list(self.known_hut_tile_ids),
            "tiles": list(self.map_tiles),
            "visible": [
                [tile_id % self.map_width, tile_id // self.map_width]
                for tile_id in self.visible_tile_ids
            ],
            "visible_enemy_units": [
                unit.to_dict() for unit in self.visible_enemy_units
            ],
            "visible_tile_ids": list(self.visible_tile_ids),
            "width": self.map_width,
        }

    def event_payload(self):
        return {
            "legal_actions_digest": self.legal_actions_digest,
            "map": self.map_dict(), "own_state": self.own_state_dict(),
            "player_id": self.player_id, "snapshot_id": self.snapshot_id,
            "source_seq": self.identity.source_seq,
            "state_hash": self.identity.state_hash, "uncertain_atoms": [],
        }
