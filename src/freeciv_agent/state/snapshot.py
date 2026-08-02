"""Immutable domain snapshot types derived from proxy packet state."""

from dataclasses import dataclass, field
import json
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
    gross_beakers_per_turn: Optional[int] = None
    tech_upkeep: Optional[int] = None

    def to_dict(self):
        return {
            "available": self.available,
            "beakers_per_turn": self.beakers_per_turn,
            "cost": self.cost,
            "diagnostic": self.diagnostic,
            "gross_beakers_per_turn": self.gross_beakers_per_turn,
            "known_techs": list(self.known_techs),
            "progress": self.progress,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "tech_upkeep": self.tech_upkeep,
        }


@dataclass(frozen=True)
class ResearchOptionState:
    """One currently advertised research selection and its grounded cost."""

    tech_name: str
    tech_id: Optional[int]
    tech_cost: Optional[int]
    action_json: str
    diagnostic: Optional[str] = None

    def to_dict(self):
        return {
            "action_json": self.action_json,
            "diagnostic": self.diagnostic,
            "tech_cost": self.tech_cost,
            "tech_id": self.tech_id,
            "tech_name": self.tech_name,
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
    city_gold_surplus_per_turn: Optional[int] = None
    unit_gold_upkeep: Optional[int] = None
    gold_upkeep_reserve: Optional[int] = None
    gold_upkeep_style: Optional[str] = None
    operating_gold_per_turn: Optional[int] = None
    capitalization_gold_per_turn: Optional[int] = None

    def to_dict(self):
        return {
            "available": self.available,
            "capitalization_gold_per_turn": self.capitalization_gold_per_turn,
            "diagnostic": self.diagnostic,
            "gold": self.gold,
            "gold_per_turn": self.gold_per_turn,
            "gold_upkeep_reserve": self.gold_upkeep_reserve,
            "gold_upkeep_style": self.gold_upkeep_style,
            "city_gold_surplus_per_turn": self.city_gold_surplus_per_turn,
            "luxury_rate": self.luxury_rate,
            "operating_gold_per_turn": self.operating_gold_per_turn,
            "science_rate": self.science_rate,
            "tax_rate": self.tax_rate,
            "unit_gold_upkeep": self.unit_gold_upkeep,
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
    veteran: Optional[int] = None
    transported: Optional[bool] = None
    transported_by: Optional[int] = None
    carrying: Optional[int] = None
    done_moving: Optional[bool] = None

    def to_dict(self):
        # This is the version-1 public/event representation. Grounded-domain
        # fields above remain available on the immutable object but are not
        # injected into the frozen v1 snapshot bytes.
        return {
            "activity": self.activity, "hp": self.hp, "moves_left": self.moves_left,
            "homecity": self.homecity,
            "owner": self.owner, "tile": self.tile, "type": self.unit_type,
            "type_id": self.type_id, "unit_id": self.unit_id,
            "upkeep": list(self.upkeep), "x": self.x, "y": self.y,
        }

    def grounded_dict(self):
        """Lossless domain-state extension for replay and parity artifacts."""
        return {
            **self.to_dict(),
            "carrying": self.carrying,
            "done_moving": self.done_moving,
            "transported": self.transported,
            "transported_by":
                self.transported_by,
            "veteran": self.veteran,
        }


@dataclass(frozen=True)
class BuildingState:
    improvement_id: int
    name: str
    upkeep: Optional[int] = None

    def to_dict(self):
        return {
            "improvement_id": self.improvement_id,
            "name": self.name,
            "upkeep": self.upkeep,
        }


@dataclass(frozen=True)
class PlayerScoreState:
    player_id: int
    name: str
    score: Optional[int]
    is_alive: Optional[bool] = None

    def to_dict(self):
        return {
            "is_alive": self.is_alive,
            "name": self.name,
            "player_id": self.player_id,
            "score": self.score,
        }


@dataclass(frozen=True)
class MovementRouteState:
    """One exact-turn path result returned by the native FreeCiv server."""

    unit_id: int
    origin_tile: int
    destination_tile: int
    reachable: bool
    first_step_tile: int
    first_step_movement_cost: int
    path_length: int
    path_directions: Tuple[int, ...]
    estimated_turns: int
    total_movement_cost: int
    movement_points_remaining: int
    moves_left_at_request: int
    transported_at_request: bool
    initially_transported: bool
    turn: int
    source_seq: int
    authority: str = "freeciv-server-pathfinder"
    schema_version: str = "1.0"

    def to_dict(self):
        return {
            "authority": self.authority,
            "destination_tile": self.destination_tile,
            "estimated_turns": self.estimated_turns,
            "first_step_movement_cost": self.first_step_movement_cost,
            "first_step_tile": self.first_step_tile,
            "initially_transported": self.initially_transported,
            "movement_points_remaining": self.movement_points_remaining,
            "moves_left_at_request": self.moves_left_at_request,
            "origin_tile": self.origin_tile,
            "path_directions": list(self.path_directions),
            "path_length": self.path_length,
            "reachable": self.reachable,
            "schema_version": self.schema_version,
            "source_seq": self.source_seq,
            "total_movement_cost": self.total_movement_cost,
            "transported_at_request": self.transported_at_request,
            "turn": self.turn,
            "unit_id": self.unit_id,
        }


@dataclass(frozen=True)
class CombatActionProbabilityState:
    """One uninterpreted native action-probability interval."""

    action_id: int
    action_name: str
    minimum: int
    maximum: int
    status: str

    @property
    def lower_probability(self):
        return (
            float(self.minimum) / 200.0
            if self.status == "bounded"
            else None)

    @property
    def upper_probability(self):
        return (
            float(self.maximum) / 200.0
            if self.status == "bounded"
            else None)

    def to_dict(self):
        return {
            "action_id": self.action_id,
            "action_name": self.action_name,
            "maximum": self.maximum,
            "minimum": self.minimum,
            "status": self.status,
        }


@dataclass(frozen=True)
class CombatProbabilityState:
    """Exact-revision combat odds returned by Freeciv's action subsystem."""

    player_id: int
    actor_unit_id: int
    target_tile_id: int
    target_unit_id: int
    target_city_id: int
    target_extra_id: int
    target_unit_ids: Tuple[int, ...]
    action_probabilities: Tuple[CombatActionProbabilityState, ...]
    actor_revision_digest: str
    target_stack_revision_digest: str
    turn: int
    request_source_seq: int
    response_source_seq: int
    authority: str = "freeciv-server-action-probability"
    schema_version: str = "1.0"

    def action_probability(self, action_name):
        action_name = str(action_name)
        return next((
            row for row in self.action_probabilities
            if row.action_name == action_name
        ), None)

    def to_dict(self):
        return {
            "action_probabilities": [
                row.to_dict()
                for row in self.action_probabilities],
            "actor_revision_digest":
                self.actor_revision_digest,
            "actor_unit_id": self.actor_unit_id,
            "authority": self.authority,
            "player_id": self.player_id,
            "request_source_seq":
                self.request_source_seq,
            "response_source_seq":
                self.response_source_seq,
            "schema_version": self.schema_version,
            "target_city_id": self.target_city_id,
            "target_extra_id": self.target_extra_id,
            "target_stack_revision_digest":
                self.target_stack_revision_digest,
            "target_tile_id": self.target_tile_id,
            "target_unit_id": self.target_unit_id,
            "target_unit_ids": list(
                self.target_unit_ids),
            "turn": self.turn,
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
    governor_available: bool = False
    governor_enabled: Optional[bool] = None
    governor_minimal_surplus: Tuple[int, ...] = field(default_factory=tuple)
    governor_factor: Tuple[int, ...] = field(default_factory=tuple)
    governor_require_happy: Optional[bool] = None
    governor_allow_disorder: Optional[bool] = None
    governor_max_growth: Optional[bool] = None
    governor_allow_specialists: Optional[bool] = None
    governor_happy_factor: Optional[int] = None
    buildings: Tuple[BuildingState, ...] = field(default_factory=tuple)

    def to_dict(self):
        return {
            "buildability_available": self.buildability_available,
            "buildability_diagnostic": self.buildability_diagnostic,
            "buildable": [list(item) for item in self.buildable],
            "buildings": [item.to_dict() for item in self.buildings],
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
            "governor": {
                "allow_disorder": self.governor_allow_disorder,
                "allow_specialists": self.governor_allow_specialists,
                "available": self.governor_available,
                "enabled": self.governor_enabled,
                "factor": list(self.governor_factor),
                "happy_factor": self.governor_happy_factor,
                "max_growth": self.governor_max_growth,
                "minimal_surplus": list(self.governor_minimal_surplus),
                "require_happy": self.governor_require_happy,
            },
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
    game_over: bool = False
    own_score: Optional[int] = None
    opponent_scores: Tuple[PlayerScoreState, ...] = field(default_factory=tuple)
    map_wrap_x: Optional[bool] = None
    map_wrap_y: Optional[bool] = None
    map_topology_id: Optional[int] = None
    movement_routes: Tuple[MovementRouteState, ...] = field(
        default_factory=tuple)
    combat_probabilities: Tuple[CombatProbabilityState, ...] = field(
        default_factory=tuple)
    research_options: Tuple[ResearchOptionState, ...] = field(
        default_factory=tuple)

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

    def movement_route(self, unit_id, destination_tile):
        unit_id = int(unit_id)
        destination_tile = int(destination_tile)
        return next((
            route for route in self.movement_routes
            if (
                route.unit_id == unit_id
                and route.destination_tile
                    == destination_tile)
        ), None)

    def combat_probability(self, unit_id, target_tile):
        unit_id = int(unit_id)
        target_tile = int(target_tile)
        return next((
            result for result in self.combat_probabilities
            if (
                result.actor_unit_id == unit_id
                and result.target_tile_id
                    == target_tile)
        ), None)

    def research_option(self, tech_name):
        tech_name = str(tech_name)
        return next((
            option for option in self.research_options
            if option.tech_name == tech_name
        ), None)

    def own_state_dict(self):
        value = {
            "cities": [city.to_dict() for city in self.cities],
            "economy": self.economy.to_dict(),
            "game_over": self.game_over,
            "government": self.government.to_dict(),
            "legal_actions_digest": self.legal_actions_digest,
            "player_alive": self.player_alive,
            "score": {
                "opponents": [row.to_dict() for row in self.opponent_scores],
                "own": self.own_score,
            },
            "research": self.research.to_dict(),
            "ruleset_diagnostic": self.ruleset_diagnostic,
            "ruleset_ready": self.ruleset_ready,
            "units": [unit.to_dict() for unit in self.units],
        }
        if self.research_options:
            value["research_options"] = [
                option.to_dict()
                for option in self.research_options
            ]
        return value

    def map_dict(self):
        tile_count = self.map_width * self.map_height
        coverage = (
            "complete" if tile_count and len(self.map_tiles) == tile_count
            else "partial" if self.map_tiles or self.visible_tile_ids
            else "dimensions_only")
        value = {
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
        if self.map_wrap_x is not None:
            value["wrap_x"] = (
                self.map_wrap_x)
        if self.map_wrap_y is not None:
            value["wrap_y"] = (
                self.map_wrap_y)
        if self.map_topology_id is not None:
            value["topology_id"] = (
                self.map_topology_id)
        return value

    def event_payload(self):
        map_topology = {
            "wrap_x":
                self.map_wrap_x,
            "wrap_y":
                self.map_wrap_y,
        }
        if self.map_topology_id is not None:
            map_topology[
                "topology_id"] = (
                    self.map_topology_id)
        if self.research_options:
            grounded_schema_version = "1.4"
        elif self.combat_probabilities:
            grounded_schema_version = "1.3"
        elif (
            self.map_topology_id
            is not None
            or any(
                isinstance(tile, dict)
                and (
                    "terrain_class"
                    in tile
                    or
                    "native_unit_classes"
                    in tile)
                for tile in
                self.map_tiles)
        ):
            grounded_schema_version = "1.2"
        else:
            grounded_schema_version = "1.1"
        payload = {
            "grounded_context": {
                "combat_probabilities": [
                    result.to_dict()
                    for result in
                    self.combat_probabilities
                ],
                "legal_actions": [
                    json.loads(value)
                    for value
                    in self.legal_action_json
                ],
                "map_topology":
                    map_topology,
                "phase": self.phase,
                "own_units": [
                    unit.grounded_dict()
                    for unit in
                    self.units
                ],
                "movement_routes": [
                    route.to_dict()
                    for route in
                    self.movement_routes
                ],
                "schema_version":
                    grounded_schema_version,
                "visible_enemy_units": [
                    unit.grounded_dict()
                    for unit in
                    self.visible_enemy_units
                ],
            },
            "legal_actions_digest": self.legal_actions_digest,
            "map": self.map_dict(), "own_state": self.own_state_dict(),
            "player_id": self.player_id, "snapshot_id": self.snapshot_id,
            "source_seq": self.identity.source_seq,
            "state_hash": self.identity.state_hash, "uncertain_atoms": [],
        }
        if self.research_options:
            payload["grounded_context"][
                "research_options"] = [
                    option.to_dict()
                    for option in
                    self.research_options
                ]
        return payload
