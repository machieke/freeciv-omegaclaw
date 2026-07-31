"""Grounded, shadow-only city-defence analysis and assignment."""

import math
import json
import re
from collections import deque
from dataclasses import dataclass
from enum import Enum
from functools import cached_property

from ...events.schema import (
    canonical_json_bytes,
    structural_hash,
)
from ...pressure.resource_claims import (
    ClaimHardness,
    GameResourceKind,
    ResourceClaim,
    ResourceRef,
    TurnWindow,
)


_ACTION_TYPE_JSON_PATTERN = re.compile(
    r'"action_type"\s*:\s*"([^"]+)"')
_ATTACK_ACTION_TYPES = frozenset((
    "unit_attack",
    "unit_bombard",
    "unit_capture",
    "unit_conquer_city",
    "unit_suicide_attack",
    "unit_wipe",
))


def _normalized(value):
    return re.sub(
        r"[^a-z0-9]+", "",
        str(value or "").lower())


def _quantity(rule, name):
    value = getattr(
        rule, "quantitative", {}).get(
            name)
    if isinstance(value, dict):
        value = value.get("value")
    if (isinstance(value, bool)
            or not isinstance(
                value, (int, float))):
        return None
    value = float(value)
    return value if math.isfinite(
        value) else None


def _unit_spec(ruleset_ir, unit_type):
    target = _normalized(
        unit_type)
    matches = []
    for rule in getattr(
            ruleset_ir, "rules", ()):
        if getattr(
                rule, "target_kind",
                None) != "unit":
            continue
        labels = {
            _normalized(getattr(
                rule, "display_name", "")),
            _normalized(getattr(
                rule, "rule_name", "")),
        }
        if target in labels:
            matches.append(rule)
    if len(matches) != 1:
        return None
    rule = matches[0]
    values = {
        name: _quantity(rule, name)
        for name in (
            "attack", "defense",
            "hitpoints", "move_rate",
            "build_cost")
    }
    if any(
            values[name] is None
            for name in (
                "attack", "defense",
                "hitpoints")):
        return None
    values["rule_id"] = str(
        getattr(
            rule, "rule_id",
            "unknown"))
    traits = getattr(
        rule, "traits", {})
    for name in (
            "class", "flags", "roles"):
        value = traits.get(
            name, {})
        if isinstance(value, dict):
            value = value.get(
                "values", ())
        if not isinstance(
                value, (list, tuple)):
            value = ()
        values[name] = tuple(sorted(
            str(row)
            for row in value
            if isinstance(row, str)
            and row))
    return values


def _combat_capable(spec):
    return bool(
        spec is not None
        and float(spec["attack"]) > 0.0
        and "NonMil" not in set(
            spec.get("flags", ())))


def _defense_capable(spec):
    return bool(
        spec is not None
        and float(spec["defense"]) > 0.0
        and "NonMil" not in set(
            spec.get("flags", ())))


def _axis_distance(
        source, target, size, wraps):
    direct = abs(
        int(source) - int(target))
    if not wraps or int(size) <= 0:
        return direct
    return min(
        direct,
        int(size) - direct)


def _distance(snapshot, source, target):
    if (not isinstance(source, tuple)
            or not isinstance(
                target, tuple)
            or len(source) != 2
            or len(target) != 2
            or None in source
            or None in target):
        return None
    return max(
        _axis_distance(
            source[0], target[0],
            getattr(
                snapshot,
                "map_width", 0),
            getattr(
                snapshot,
                "map_wrap_x", None)
            is True),
        _axis_distance(
            source[1], target[1],
            getattr(
                snapshot,
                "map_height", 0),
            getattr(
                snapshot,
                "map_wrap_y", None)
            is True))


def _neighbor_positions(
        snapshot, position):
    width = int(
        getattr(
            snapshot,
            "map_width", 0))
    height = int(
        getattr(
            snapshot,
            "map_height", 0))
    if width <= 0 or height <= 0:
        return ()
    x, y = position
    topology_id = int(
        getattr(
            snapshot,
            "map_topology_id", 0)
        or 0)
    is_isometric = bool(
        topology_id & 3)
    is_hex = bool(
        topology_id & 2)
    iso_hex = bool(
        is_hex
        and topology_id & 1)
    rows = set()
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            # These exclusions reproduce Freeciv's
            # is_valid_dir_calculate(): ordinary hex maps exclude NW/SE,
            # while iso-hex maps exclude NE/SW.
            if (
                    is_hex
                    and (
                        (
                            not iso_hex
                            and (
                                (dx, dy)
                                in (
                                    (-1, -1),
                                    (1, 1))))
                        or (
                            iso_hex
                            and (
                                (dx, dy)
                                in (
                                    (1, -1),
                                    (-1, 1)))))):
                continue
            if is_isometric:
                # Snapshot tile x/y values are Freeciv native coordinates
                # (tile index modulo/divided by native width). mapstep()
                # applies directions in map coordinates, so reproduce the
                # public NATIVE_TO_MAP_POS/MAP_TO_NATIVE_POS transforms.
                map_x = (
                    (y + (y & 1))
                    // 2 + x)
                map_y = (
                    y - map_x
                    + width)
                target_map_x = (
                    map_x + dx)
                target_map_y = (
                    map_y + dy)
                target_y = (
                    target_map_x
                    + target_map_y
                    - width)
                target_x = (
                    2 * target_map_x
                    - target_y
                    - (target_y & 1)
                ) // 2
            else:
                target_x = x + dx
                target_y = y + dy
            if getattr(
                    snapshot,
                    "map_wrap_x",
                    None) is True:
                target_x %= width
            if getattr(
                    snapshot,
                    "map_wrap_y",
                    None) is True:
                target_y %= height
            if (0 <= target_x < width
                    and 0 <= target_y
                    < height):
                rows.add((
                    target_x,
                    target_y))
    return tuple(sorted(
        rows))


def _known_native_terrain_context(
        snapshot, unit_class):
    """Project immutable known/native tile sets once per snapshot/class."""
    known_positions = set()
    native_tiles = set()
    complete_semantics = True
    tile_count = (
        int(getattr(
            snapshot,
            "map_width", 0))
        * int(getattr(
            snapshot,
            "map_height", 0)))
    map_tiles = tuple(
        getattr(
            snapshot,
            "map_tiles", ()))
    for tile in map_tiles:
        if not isinstance(
                tile, dict):
            complete_semantics = False
            continue
        x = tile.get("x")
        y = tile.get("y")
        classes = tile.get(
            "native_unit_classes")
        if (isinstance(x, bool)
                or not isinstance(x, int)
                or isinstance(y, bool)
                or not isinstance(y, int)
                or not isinstance(
                    classes, list)):
            complete_semantics = False
            continue
        known_positions.add((
            x, y))
        if unit_class in classes:
            native_tiles.add((
                x, y))
    complete_semantics = bool(
        complete_semantics
        and tile_count > 0
        and len(known_positions)
        == tile_count)
    return (
        frozenset(
            known_positions),
        frozenset(
            native_tiles),
        complete_semantics)


def _known_native_corridor(
        snapshot, source, city_position,
        unit_class,
        terrain_context=None):
    """Find a path using only player-known native terrain semantics."""
    distance = _distance(
        snapshot, source,
        city_position)
    if distance is None:
        return (
            "unknown",
            "threat-position-unavailable",
            (),
            None)
    topology_id = getattr(
        snapshot,
        "map_topology_id", None)
    if topology_id is None:
        return (
            "unknown",
            "map-topology-unavailable",
            (),
            None)
    if source in _neighbor_positions(
            snapshot,
            city_position):
        return (
            "reachable",
            "visible-adjacent-threat",
            (source,),
            0)
    if terrain_context is None:
        terrain_context = (
            _known_native_terrain_context(
                snapshot,
                unit_class))
    (
        known_positions,
        native_tiles,
        complete_semantics,
    ) = terrain_context
    if source not in native_tiles:
        return (
            "unreachable"
            if source
            in known_positions
            else "unknown",
            "known-native-source-unreachable"
            if source
            in known_positions
            else
            "source-terrain-semantics-unavailable",
            (),
            None)
    city_approaches = frozenset(
        _neighbor_positions(
            snapshot,
            city_position))
    targets = frozenset(
        position
        for position in city_approaches
        if position in native_tiles)
    if not targets:
        approaches_known = bool(
            city_approaches
            and city_approaches
            <= known_positions)
        return (
            "unreachable"
            if approaches_known
            else "unknown",
            "known-native-city-approach-unreachable"
            if approaches_known
            else
            "city-approach-semantics-unavailable",
            (),
            None)
    queue = deque((source,))
    parent = {
        source: None,
    }
    selected = None
    while queue:
        current = queue.popleft()
        if current in targets:
            selected = current
            break
        for neighbor in _neighbor_positions(
                snapshot, current):
            if (neighbor
                    not in native_tiles
                    or neighbor in parent):
                continue
            parent[neighbor] = (
                current)
            queue.append(neighbor)
    if selected is None:
        closed_known_component = all(
            neighbor
            in known_positions
            for current in parent
            for neighbor in
            _neighbor_positions(
                snapshot, current))
        return (
            "unreachable"
            if (
                complete_semantics
                or closed_known_component)
            else "unknown",
            "known-native-corridor-unreachable"
            if (
                complete_semantics
                or closed_known_component)
            else
            "known-native-corridor-not-proven",
            (),
            None)
    reversed_path = []
    current = selected
    while current is not None:
        reversed_path.append(
            current)
        current = parent[
            current]
    corridor = tuple(reversed(
        reversed_path))
    return (
        "reachable",
        "player-known-native-terrain-corridor",
        corridor,
        len(corridor) - 1)


class DefenseOperationType(str, Enum):
    FORTIFY_EXISTING_DEFENDER = (
        "fortify_existing_defender")
    MOVE_DEFENDER_TO_CITY = (
        "move_defender_to_city")
    INTERCEPT_IMMEDIATE_THREAT = (
        "intercept_immediate_threat")
    BLOCK_APPROACH_TILE = (
        "block_approach_tile")
    EMERGENCY_BUILD_DEFENDER = (
        "emergency_build_defender")
    RETREAT_EXPOSED_UNIT = (
        "retreat_exposed_unit")
    HOLD_SOLE_DEFENDER = (
        "hold_sole_defender")


CITY_DEFENSE_LIVE_OPERATION_TYPES = frozenset({
    DefenseOperationType
    .FORTIFY_EXISTING_DEFENDER,
    DefenseOperationType
    .MOVE_DEFENDER_TO_CITY,
})


@dataclass(frozen=True)
class _DefenseActionView:
    action: dict
    category: str
    projection: object
    readout_source: str

    @cached_property
    def action_key(self):
        return canonical_json_bytes(
            self.action).decode(
                "utf-8")


@dataclass(frozen=True)
class VisibleCityThreat:
    enemy_unit_id: int
    enemy_unit_type: str
    enemy_unit_class: object
    city_id: int
    distance_tiles: int
    earliest_attack_turn: int
    movement_rate: object
    eta_basis: str
    reachability_status: str
    reachability_basis: str
    threat_priority: float
    confidence: float
    unknown_mass: float
    path_corridor: tuple
    interception_legal: bool
    support_reason: object
    ruleset_rule_id: object

    def __post_init__(self):
        for value, name in (
                (self.enemy_unit_id,
                 "enemy unit ID"),
                (self.city_id, "city ID"),
                (self.distance_tiles,
                 "threat distance"),
                (self.earliest_attack_turn,
                 "earliest attack turn")):
            if (isinstance(value, bool)
                    or not isinstance(
                        value, int)
                    or value < 0):
                raise ValueError(
                    "{} must be non-negative".format(name))
        if (not isinstance(
                self.enemy_unit_type, str)
                or not self.enemy_unit_type):
            raise ValueError(
                "enemy unit type is required")
        if (self.enemy_unit_class is not None
                and (not isinstance(
                    self.enemy_unit_class, str)
                     or not self.enemy_unit_class)):
            raise ValueError(
                "enemy unit class must be non-empty or absent")
        if (self.movement_rate is not None
                and (
                    isinstance(
                        self.movement_rate,
                        bool)
                    or not isinstance(
                        self.movement_rate,
                        (int, float))
                    or not math.isfinite(
                        float(
                            self.movement_rate))
                    or float(
                        self.movement_rate)
                    <= 0.0)):
            raise ValueError(
                "threat movement rate must be positive or absent")
        if (not isinstance(
                self.eta_basis, str)
                or not self.eta_basis):
            raise ValueError(
                "threat ETA basis is required")
        if self.reachability_status not in (
                "reachable",
                "unreachable",
                "unknown"):
            raise ValueError(
                "threat reachability status is invalid")
        if (not isinstance(
                self.reachability_basis,
                str)
                or not
                self.reachability_basis):
            raise ValueError(
                "threat reachability basis is required")
        for value, name in (
                (self.threat_priority,
                 "threat priority"),
                (self.confidence,
                 "threat confidence"),
                (self.unknown_mass,
                 "threat unknown mass")):
            value = float(value)
            if (not math.isfinite(value)
                    or value < 0.0):
                raise ValueError(
                    "{} must be finite and non-negative".format(name))
        if self.confidence > 1.0 or self.unknown_mass > 1.0:
            raise ValueError(
                "threat confidence and unknown mass must be at most one")
        if abs(
                self.confidence
                + self.unknown_mass
                - 1.0) > 1e-9:
            raise ValueError(
                "threat confidence and unknown mass must conserve mass")
        if any(
                not isinstance(row, tuple)
                or len(row) != 2
                or any(
                    isinstance(value, bool)
                    or not isinstance(
                        value, int)
                    for value in row)
                for row in self.path_corridor):
            raise ValueError(
                "threat corridor must contain integer positions")
        if not isinstance(
                self.interception_legal, bool):
            raise TypeError(
                "interception legality must be boolean")
        if (self.support_reason is not None
                and (not isinstance(
                    self.support_reason, str)
                     or not self.support_reason)):
            raise ValueError(
                "threat support reason must be non-empty or absent")

    @cached_property
    def threat_id(self):
        return structural_hash(
            self.to_dict())

    @property
    def supported(self):
        return self.support_reason is None

    def to_dict(self):
        return {
            "city_id": self.city_id,
            "confidence": float(
                self.confidence),
            "distance_tiles":
                self.distance_tiles,
            "earliest_attack_turn":
                self.earliest_attack_turn,
            "eta_basis":
                self.eta_basis,
            "enemy_unit_id":
                self.enemy_unit_id,
            "enemy_unit_class":
                self.enemy_unit_class,
            "enemy_unit_type":
                self.enemy_unit_type,
            "interception_legal":
                self.interception_legal,
            "movement_rate": (
                None
                if self.movement_rate
                is None
                else float(
                    self.movement_rate)),
            "path_corridor": [
                list(row)
                for row in
                self.path_corridor],
            "reachability_basis":
                self.reachability_basis,
            "reachability_status":
                self.reachability_status,
            "ruleset_rule_id":
                self.ruleset_rule_id,
            "support_reason":
                self.support_reason,
            "threat_priority":
                float(
                    self.threat_priority),
            "unknown_mass":
                float(
                    self.unknown_mass),
        }


@dataclass(frozen=True)
class CityDefenseRequirement:
    city_id: int
    city_position: tuple
    current_defenders: int
    required_defenders: int
    response_slots: int
    deadline_turn: int
    threat_ids: tuple
    threat_priority: float
    confidence: float

    def __post_init__(self):
        for value, name in (
                (self.city_id, "city ID"),
                (self.current_defenders,
                 "current defenders"),
                (self.required_defenders,
                 "required defenders"),
                (self.response_slots,
                 "response slots"),
                (self.deadline_turn,
                 "defence deadline")):
            if (isinstance(value, bool)
                    or not isinstance(
                        value, int)
                    or value < 0):
                raise ValueError(
                    "{} must be non-negative".format(name))
        if self.required_defenders < 1:
            raise ValueError(
                "city defence requires at least one defender")
        if self.response_slots < 1:
            raise ValueError(
                "threatened city requires at least one response")
        if (not isinstance(
                self.city_position, tuple)
                or len(
                    self.city_position) != 2
                or any(
                    isinstance(value, bool)
                    or not isinstance(
                        value, int)
                    for value
                    in self.city_position)):
            raise ValueError(
                "city position requires integer coordinates")
        if (tuple(sorted(set(
                self.threat_ids)))
                != self.threat_ids
                or any(
                    not isinstance(value, str)
                    or not value
                    for value
                    in self.threat_ids)):
            raise ValueError(
                "requirement threat IDs must be unique and sorted")
        if (not math.isfinite(
                float(
                    self.threat_priority))
                or self.threat_priority < 0.0):
            raise ValueError(
                "requirement priority must be non-negative")
        if (not math.isfinite(
                float(self.confidence))
                or not 0.0
                <= self.confidence
                <= 1.0):
            raise ValueError(
                "requirement confidence must be in [0,1]")

    @cached_property
    def requirement_id(self):
        return structural_hash(
            self.to_dict())

    def to_dict(self):
        return {
            "city_id": self.city_id,
            "city_position": list(
                self.city_position),
            "confidence": float(
                self.confidence),
            "current_defenders":
                self.current_defenders,
            "deadline_turn":
                self.deadline_turn,
            "required_defenders":
                self.required_defenders,
            "response_slots":
                self.response_slots,
            "threat_ids": list(
                self.threat_ids),
            "threat_priority":
                float(
                    self.threat_priority),
        }


@dataclass(frozen=True)
class DefenderProfile:
    unit_id: int
    unit_type: str
    position: tuple
    current_city_id: object
    defense_power: object
    hitpoint_fraction: object
    protected_sole_defender: bool
    ruleset_rule_id: object
    support_reason: object

    def __post_init__(self):
        if (isinstance(self.unit_id, bool)
                or not isinstance(
                    self.unit_id, int)
                or self.unit_id < 0):
            raise ValueError(
                "defender unit ID must be non-negative")
        if not isinstance(
                self.unit_type, str
                ) or not self.unit_type:
            raise ValueError(
                "defender unit type is required")
        if (not isinstance(
                self.position, tuple)
                or len(self.position) != 2
                or any(
                    isinstance(value, bool)
                    or not isinstance(
                        value, int)
                    for value
                    in self.position)):
            raise ValueError(
                "defender position requires integer coordinates")
        if (self.current_city_id is not None
                and (isinstance(
                    self.current_city_id, bool)
                     or not isinstance(
                        self.current_city_id, int)
                     or self.current_city_id < 0)):
            raise ValueError(
                "current city ID must be non-negative or absent")
        for value, name in (
                (self.defense_power,
                 "defender power"),
                (self.hitpoint_fraction,
                 "hitpoint fraction")):
            if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(
                        value, (int, float))
                    or not math.isfinite(
                        float(value))
                    or float(value) < 0.0):
                raise ValueError(
                    "{} must be non-negative or absent".format(name))
        if (self.hitpoint_fraction is not None
                and self.hitpoint_fraction > 1.0):
            raise ValueError(
                "hitpoint fraction must not exceed one")
        if not isinstance(
                self.protected_sole_defender,
                bool):
            raise TypeError(
                "sole-defender protection must be boolean")

    @property
    def supported(self):
        return self.support_reason is None

    @property
    def effective_defense(self):
        if not self.supported:
            return None
        return (
            float(self.defense_power)
            * float(
                self.hitpoint_fraction))

    def to_dict(self):
        return {
            "current_city_id":
                self.current_city_id,
            "defense_power":
                self.defense_power,
            "effective_defense":
                self.effective_defense,
            "hitpoint_fraction":
                self.hitpoint_fraction,
            "position": list(
                self.position),
            "protected_sole_defender":
                self.protected_sole_defender,
            "ruleset_rule_id":
                self.ruleset_rule_id,
            "support_reason":
                self.support_reason,
            "unit_id": self.unit_id,
            "unit_type": self.unit_type,
        }


@dataclass(frozen=True)
class CityDefenseOperation:
    operation_id: str
    operation_type: DefenseOperationType
    requirement_id: str
    city_id: int
    actor_id: object
    next_action: object
    arrival_turn: int
    deadline_turn: int
    expected_prevented_loss: float
    opportunity_cost: float
    bid: float
    claims: tuple
    support_reason: object
    provenance: tuple

    def __post_init__(self):
        if (not isinstance(
                self.operation_id, str)
                or not self.operation_id):
            raise ValueError(
                "defence operation requires operation ID")
        if not isinstance(
                self.operation_type,
                DefenseOperationType):
            raise TypeError(
                "defence operation type is invalid")
        if (not isinstance(
                self.requirement_id, str)
                or not self.requirement_id):
            raise ValueError(
                "defence operation requires requirement ID")
        for value, name in (
                (self.city_id, "city ID"),
                (self.arrival_turn,
                 "arrival turn"),
                (self.deadline_turn,
                 "deadline turn")):
            if (isinstance(value, bool)
                    or not isinstance(
                        value, int)
                    or value < 0):
                raise ValueError(
                    "{} must be non-negative".format(name))
        if (self.actor_id is not None
                and (isinstance(
                    self.actor_id, bool)
                     or not isinstance(
                        self.actor_id, int)
                     or self.actor_id < 0)):
            raise ValueError(
                "operation actor ID must be non-negative or absent")
        if (self.next_action is not None
                and not isinstance(
                    self.next_action, dict)):
            raise TypeError(
                "next defence action must be a dictionary or absent")
        for value, name in (
                (self.expected_prevented_loss,
                 "expected prevented loss"),
                (self.opportunity_cost,
                 "opportunity cost"),
                (self.bid, "operation bid")):
            if (not math.isfinite(
                    float(value))
                    or float(value) < 0.0):
                raise ValueError(
                    "{} must be finite and non-negative".format(name))
        if any(not isinstance(
                claim, ResourceClaim)
               for claim in self.claims):
            raise TypeError(
                "defence claims must be ResourceClaim")
        if not self.claims:
            raise ValueError(
                "defence operation requires at least one resource claim")
        if any(
                claim.source_operation_id
                != self.operation_id
                for claim in self.claims):
            raise ValueError(
                "defence claims must name their operation")
        if (self.support_reason is not None
                and (not isinstance(
                    self.support_reason, str)
                     or not self.support_reason)):
            raise ValueError(
                "operation support reason must be non-empty or absent")
        if (not self.provenance
                or any(
                    not isinstance(value, str)
                    or not value
                    for value
                    in self.provenance)):
            raise ValueError(
                "defence operation requires provenance")

    @property
    def supported(self):
        return (
            self.support_reason is None
            and self.arrival_turn
            <= self.deadline_turn)

    def to_dict(self):
        return {
            "actor_id": self.actor_id,
            "arrival_turn":
                self.arrival_turn,
            "bid": float(self.bid),
            "city_id": self.city_id,
            "claims": [
                row.to_dict()
                for row in self.claims],
            "deadline_turn":
                self.deadline_turn,
            "expected_prevented_loss":
                float(
                    self.expected_prevented_loss),
            "next_action":
                self.next_action,
            "operation_id":
                self.operation_id,
            "operation_type":
                self.operation_type.value,
            "opportunity_cost":
                float(
                    self.opportunity_cost),
            "provenance": list(
                self.provenance),
            "requirement_id":
                self.requirement_id,
            "support_reason":
                self.support_reason,
        }


GROUNDED_OPERATION_RESULT_REASONS = frozenset({
    "alternate-step-not-native-selected-route",
    "arrival-after-threat-deadline",
    "defender-native-route-unreachable",
    "immediate-interception-available",
    "native-route-misses-threat-deadline",
    "protected-sole-defender",
})

GROUNDED_THREAT_RESULT_BASES = frozenset({
    "known-native-city-approach-unreachable",
    "known-native-corridor-unreachable",
    "known-native-source-unreachable",
})


def grounded_threat_result(threat):
    """Whether a threat has a decision-usable positive or negative result."""
    if not isinstance(
            threat,
            VisibleCityThreat):
        raise TypeError(
            "grounded threat result requires a visible city threat")
    return bool(
        threat.supported
        or (
            threat.reachability_status
            == "unreachable"
            and threat.reachability_basis
            in
            GROUNDED_THREAT_RESULT_BASES))


def grounded_operation_result(operation):
    """Whether an operation has a decision-usable positive or negative result."""
    if not isinstance(
            operation,
            CityDefenseOperation):
        raise TypeError(
            "grounded operation result requires a city-defence operation")
    return bool(
        operation.supported
        or operation.support_reason
        in
        GROUNDED_OPERATION_RESULT_REASONS)


@dataclass(frozen=True)
class CityDefenseAnalysis:
    snapshot_id: str
    threats: tuple
    requirements: tuple
    defenders: tuple
    operations: tuple
    omissions: tuple
    analyzer_identity: str
    input_candidate_count: int = 0
    analyzed_candidate_count: int = 0
    protected_union_added_count: int = 0

    def __post_init__(self):
        if (not isinstance(
                self.snapshot_id, str)
                or not self.snapshot_id):
            raise ValueError(
                "defence analysis requires snapshot ID")
        for rows, expected, name in (
                (self.threats,
                 VisibleCityThreat,
                 "threats"),
                (self.requirements,
                 CityDefenseRequirement,
                 "requirements"),
                (self.defenders,
                 DefenderProfile,
                 "defenders"),
                (self.operations,
                 CityDefenseOperation,
                 "operations")):
            if any(
                    not isinstance(
                        row, expected)
                    for row in rows):
                raise TypeError(
                    "defence {} have the wrong type".format(name))
        for identities, name in (
                (tuple(
                    row.threat_id
                    for row in self.threats),
                 "threat"),
                (tuple(
                    row.requirement_id
                    for row
                    in self.requirements),
                 "requirement"),
                (tuple(
                    row.unit_id
                    for row in self.defenders),
                 "defender"),
                (tuple(
                    row.operation_id
                    for row
                    in self.operations),
                 "operation")):
            if len(identities) != len(
                    set(identities)):
                raise ValueError(
                    "defence {} identities must be unique".format(name))
        requirement_ids = frozenset(
            row.requirement_id
            for row in self.requirements)
        if any(
                row.requirement_id
                not in requirement_ids
                for row in self.operations):
            raise ValueError(
                "defence operation references an unknown requirement")
        if (tuple(sorted(set(
                self.omissions)))
                != self.omissions
                or any(
                    not isinstance(value, str)
                    or not value
                    for value
                    in self.omissions)):
            raise ValueError(
                "defence omissions must be unique sorted strings")
        if (not isinstance(
                self.analyzer_identity, str)
                or not self.analyzer_identity):
            raise ValueError(
                "defence analyzer identity is required")
        for value, name in (
                (self.input_candidate_count,
                 "input candidate count"),
                (self.analyzed_candidate_count,
                 "analyzed candidate count"),
                (self.protected_union_added_count,
                 "protected-union added count")):
            if (isinstance(value, bool)
                    or not isinstance(
                        value, int)
                    or value < 0):
                raise ValueError(
                    "{} must be non-negative".format(name))

    @cached_property
    def analysis_digest(self):
        return structural_hash(
            self.to_dict(
                include_digest=False))

    def to_dict(
            self, include_digest=True):
        payload = {
            "analyzed_candidate_count":
                self.analyzed_candidate_count,
            "analyzer_identity":
                self.analyzer_identity,
            "input_candidate_count":
                self.input_candidate_count,
            "defenders": [
                row.to_dict()
                for row in self.defenders],
            "omissions": list(
                self.omissions),
            "operations": [
                {
                    "operation_id":
                        row.operation_id,
                    **row.to_dict(),
                }
                for row in self.operations],
            "requirements": [
                {
                    "requirement_id":
                        row.requirement_id,
                    **row.to_dict(),
                }
                for row in self.requirements],
            "protected_union_added_count":
                self.protected_union_added_count,
            "snapshot_id":
                self.snapshot_id,
            "threats": [
                {
                    "threat_id":
                        row.threat_id,
                    **row.to_dict(),
                }
                for row in self.threats],
        }
        if include_digest:
            payload["analysis_digest"] = (
                self.analysis_digest)
        return payload


class CityDefenseAnalyzer:
    """Build a conservative city-threat/defender operation graph."""

    ANALYZER_IDENTITY = (
        "freeciv-city-defense-analyzer/1.3")

    def __init__(
            self, threat_radius=6,
            required_garrison=1):
        for value, name in (
                (threat_radius,
                 "threat radius"),
                (required_garrison,
                 "required garrison")):
            if (isinstance(value, bool)
                    or not isinstance(
                        value, int)
                    or value < 1):
                raise ValueError(
                    "{} must be a positive integer".format(name))
        self.threat_radius = threat_radius
        self.required_garrison = (
            required_garrison)

    @staticmethod
    def _actor_claim(
            snapshot, operation_id,
            actor_id, step_id):
        scope = "player:{}".format(
            snapshot.player_id)
        return ResourceClaim(
            resource=ResourceRef(
                GameResourceKind.ACTOR,
                "unit:{}".format(
                    actor_id),
                "whole_actor", scope),
            quantity=1,
            window=TurnWindow(
                int(snapshot.turn),
                int(snapshot.turn) + 1),
            hardness=(
                ClaimHardness
                .HARD_CURRENT),
            exclusive=True,
            source_operation_id=(
                operation_id),
            source_step_id=step_id)

    @staticmethod
    def _operation_id_seed(
            operation_type,
            requirement_id,
            city_id, actor_id,
            action):
        return structural_hash({
            "actor_id": actor_id,
            "city_id": city_id,
            "next_action": action,
            "operation_type":
                operation_type.value,
            "requirement_id":
                requirement_id,
            "schema_version": "1.0",
        })

    def _defenders(
            self, snapshot, ruleset_ir,
            city_counts,
            unit_specs=None):
        cities_by_position = {
            (city.x, city.y): city
            for city in snapshot.cities
            if None not in (
                city.x, city.y)}
        rows = []
        for unit in sorted(
                snapshot.units,
                key=lambda row:
                row.unit_id):
            if None in (
                    unit.x, unit.y):
                continue
            spec = (
                unit_specs.get(
                    unit.unit_id)
                if unit_specs is not None
                else _unit_spec(
                    ruleset_ir,
                    unit.unit_type))
            if (spec is not None
                    and not _defense_capable(
                        spec)):
                continue
            city = cities_by_position.get(
                (unit.x, unit.y))
            current_city_id = (
                None if city is None
                else city.city_id)
            hp = getattr(
                unit, "hp", None)
            maximum_hp = (
                None if spec is None
                else spec["hitpoints"])
            hitpoint_fraction = (
                None
                if (isinstance(hp, bool)
                    or not isinstance(
                        hp, (int, float))
                    or maximum_hp is None
                    or maximum_hp <= 0.0)
                else min(
                    1.0,
                    max(
                        0.0,
                        float(hp)
                        / maximum_hp)))
            support_reason = (
                "ruleset-unit-spec-unavailable"
                if spec is None
                else
                "unit-hitpoints-unavailable"
                if hitpoint_fraction is None
                else None)
            rows.append(
                DefenderProfile(
                    unit_id=unit.unit_id,
                    unit_type=unit.unit_type,
                    position=(
                        int(unit.x),
                        int(unit.y)),
                    current_city_id=(
                        current_city_id),
                    defense_power=(
                        None
                        if spec is None
                        else spec[
                            "defense"]),
                    hitpoint_fraction=(
                        hitpoint_fraction),
                    protected_sole_defender=bool(
                        current_city_id
                        is not None
                        and city_counts.get(
                            current_city_id,
                            0)
                        <= self
                        .required_garrison),
                    ruleset_rule_id=(
                        None
                        if spec is None
                        else spec[
                            "rule_id"]),
                    support_reason=(
                        support_reason)))
        return tuple(rows)

    def _threats(
            self, snapshot, ruleset_ir,
            legal_actions):
        attack_target_ids = set()
        attack_target_positions = set()
        for action in legal_actions:
            if not str(action.get(
                    "action_type", "")
                    ).startswith(
                        "unit_"):
                continue
            if action.get(
                    "action_type") not in (
                    "unit_attack",
                    "unit_bombard",
                    "unit_capture",
                    "unit_conquer_city",
                    "unit_suicide_attack",
                    "unit_wipe"):
                continue
            target = action.get(
                "target")
            if isinstance(target, dict):
                target_id = target.get(
                    "target_unit_id")
                if target_id is not None:
                    attack_target_ids.add(
                        int(target_id))
                if None not in (
                        target.get("x"),
                        target.get("y")):
                    attack_target_positions.add((
                        int(target["x"]),
                        int(target["y"])))
        threats = []
        omissions = []
        terrain_contexts = {}
        for enemy in sorted(
                snapshot.visible_enemy_units,
                key=lambda row:
                row.unit_id):
            if None in (
                    enemy.x, enemy.y):
                omissions.append(
                    "enemy:{}:position-unavailable".format(
                        enemy.unit_id))
                continue
            spec = _unit_spec(
                ruleset_ir,
                enemy.unit_type)
            attack_supported = (
                _combat_capable(spec))
            unit_classes = (
                ()
                if spec is None
                else spec.get(
                    "class", ()))
            unit_class = (
                unit_classes[0]
                if len(unit_classes) == 1
                else None)
            if (
                    unit_class is not None
                    and unit_class
                    not in terrain_contexts):
                terrain_contexts[
                    unit_class] = (
                        _known_native_terrain_context(
                            snapshot,
                            unit_class))
            if spec is None:
                support_reason = (
                    "enemy-ruleset-spec-unavailable")
            elif not attack_supported:
                omissions.append(
                    "enemy:{}:not-combat-capable".format(
                        enemy.unit_id))
                continue
            elif unit_class is None:
                support_reason = (
                    "enemy-unit-class-unavailable")
            else:
                support_reason = None
            movement_rate = (
                None if spec is None
                else spec.get(
                    "move_rate"))
            movement_rate_supported = (
                not isinstance(
                    movement_rate, bool)
                and isinstance(
                    movement_rate,
                    (int, float))
                and math.isfinite(
                    float(
                        movement_rate))
                and float(
                    movement_rate) > 0.0)
            if (support_reason is None
                    and not
                    movement_rate_supported):
                support_reason = (
                    "enemy-move-rate-unavailable")
            for city in sorted(
                    snapshot.cities,
                    key=lambda row:
                    row.city_id):
                distance = _distance(
                    snapshot,
                    (enemy.x, enemy.y),
                    (city.x, city.y))
                if (distance is None
                        or distance
                        > self.threat_radius):
                    continue
                attack_power = (
                    0.0
                    if spec is None
                    else max(
                        0.0,
                        spec["attack"]))
                priority = (
                    (1.0
                     + max(
                         1,
                         int(city.size)))
                    * max(
                        1.0,
                        attack_power)
                    / max(
                        1,
                        distance))
                (
                    reachability_status,
                    reachability_basis,
                    known_corridor,
                    known_approach_tiles,
                ) = _known_native_corridor(
                    snapshot,
                    (
                        int(enemy.x),
                        int(enemy.y)),
                    (
                        int(city.x),
                        int(city.y)),
                    unit_class,
                    terrain_context=(
                        terrain_contexts.get(
                            unit_class)))
                threat_support_reason = (
                    support_reason)
                if (threat_support_reason
                        is None
                        and reachability_status
                        != "reachable"):
                    threat_support_reason = (
                        reachability_basis)
                approach_tiles = (
                    int(
                        known_approach_tiles)
                    if known_approach_tiles
                    is not None
                    else max(
                        0,
                        distance - 1))
                if movement_rate_supported:
                    eta_turns = int(
                        math.ceil(
                            float(
                                approach_tiles)
                            / float(
                                movement_rate)))
                    eta_basis = (
                        "ruleset-move-rate-geometric-lower-bound")
                else:
                    # Retain an attributable diagnostic for unsupported
                    # threats, but never form a requirement from this
                    # fallback because support_reason is non-null.
                    eta_turns = (
                        approach_tiles)
                    eta_basis = (
                        "unsupported-unit-step-fallback")
                threats.append(
                    VisibleCityThreat(
                        enemy_unit_id=(
                            enemy.unit_id),
                        enemy_unit_type=(
                            enemy.unit_type),
                        enemy_unit_class=(
                            unit_class),
                        city_id=city.city_id,
                        distance_tiles=(
                            distance),
                        earliest_attack_turn=(
                            int(snapshot.turn)
                            + eta_turns),
                        movement_rate=(
                            float(
                                movement_rate)
                            if
                            movement_rate_supported
                            else None),
                        eta_basis=(
                            eta_basis),
                        threat_priority=(
                            priority),
                        confidence=(
                            0.45
                            if threat_support_reason
                            is None
                            else 0.0),
                        unknown_mass=(
                            0.55
                            if threat_support_reason
                            is None
                            else 1.0),
                        path_corridor=(
                            known_corridor
                            if known_corridor
                            else (
                                (
                                    int(
                                        enemy.x),
                                    int(
                                        enemy.y)),
                                (
                                    int(
                                        city.x),
                                    int(
                                        city.y)))),
                        reachability_status=(
                            reachability_status),
                        reachability_basis=(
                            reachability_basis),
                        interception_legal=bool(
                            enemy.unit_id
                            in attack_target_ids
                            or (
                                int(enemy.x),
                                int(enemy.y))
                            in attack_target_positions),
                        support_reason=(
                            threat_support_reason),
                        ruleset_rule_id=(
                            None
                            if spec is None
                            else spec[
                                "rule_id"])))
        return (
            tuple(sorted(
                threats,
                key=lambda row: (
                    row.city_id,
                    row.earliest_attack_turn,
                    row.enemy_unit_id))),
            tuple(sorted(set(
                omissions))))

    def analyze(
            self, snapshot, ruleset_ir,
            candidates,
            operation_types=None):
        candidates = tuple(
            candidates)
        if operation_types is None:
            allowed_operation_types = (
                frozenset(
                    DefenseOperationType))
        else:
            try:
                allowed_operation_types = (
                    frozenset(
                        DefenseOperationType(
                            value)
                        for value in
                        operation_types))
            except (TypeError, ValueError):
                raise ValueError(
                    "city defence operation types are invalid")
        # Protected holds are constraints, not policy candidates.  Keep them
        # visible in every narrowed analysis so a low-latency live slice
        # cannot accidentally remove the sole-defender invariant.
        allowed_operation_types = (
            allowed_operation_types
            | {
                DefenseOperationType
                .HOLD_SOLE_DEFENDER,
            })
        input_candidate_count = len(
            candidates)
        narrow_fortify_only = bool(
            operation_types is not None
            and allowed_operation_types
            == {
                DefenseOperationType
                .FORTIFY_EXISTING_DEFENDER,
                DefenseOperationType
                .HOLD_SOLE_DEFENDER,
            })
        # The bounded live slice reacts only to player-visible city threats.
        # With no visible enemy there can be no requirement, fortification
        # operation, protected hold, or winner-changing authority. Avoid
        # decoding and canonicalizing the otherwise very large legal-action
        # set in this exact no-authority state.
        if (
                narrow_fortify_only
                and not snapshot
                .visible_enemy_units):
            return CityDefenseAnalysis(
                snapshot_id=str(
                    snapshot.snapshot_id),
                threats=(),
                requirements=(),
                defenders=(),
                operations=(),
                omissions=(),
                analyzer_identity=(
                    self.ANALYZER_IDENTITY),
                input_candidate_count=(
                    input_candidate_count),
                analyzed_candidate_count=0,
                protected_union_added_count=0)
        protected_types = set()
        if (
                DefenseOperationType
                .FORTIFY_EXISTING_DEFENDER
                in allowed_operation_types):
            protected_types.add(
                "unit_fortify")
        if (
                DefenseOperationType
                .MOVE_DEFENDER_TO_CITY
                in allowed_operation_types):
            protected_types.add(
                "unit_move")
        if (
                DefenseOperationType
                .INTERCEPT_IMMEDIATE_THREAT
                in allowed_operation_types):
            protected_types.update(
                _ATTACK_ACTION_TYPES)
        relevant_action_types = set(
            protected_types)
        if (
                DefenseOperationType
                .EMERGENCY_BUILD_DEFENDER
                in allowed_operation_types):
            relevant_action_types.add(
                "city_production")
        legal_relevant_action_types = set(
            relevant_action_types)
        # Legal immediate attacks are context for the conservative
        # fortification guard: if a supported threat can be intercepted,
        # fortification yields to exact B1. They are not fortification
        # operation candidates and must not enter candidate canonicalization
        # or assembly unless interception operations are explicitly enabled.
        if (
                DefenseOperationType
                .FORTIFY_EXISTING_DEFENDER
                in allowed_operation_types):
            legal_relevant_action_types.update(
                _ATTACK_ACTION_TYPES)
        if operation_types is not None:
            candidates = tuple(
                candidate
                for candidate in
                candidates
                if str(
                    candidate.action.get(
                        "action_type", ""))
                in relevant_action_types)
        declared_legal = getattr(
            snapshot,
            "legal_action_json", None)
        if declared_legal is None:
            legal_keys = frozenset(
                canonical_json_bytes(
                    candidate.action)
                .decode("utf-8")
                for candidate in
                candidates)
            legal = tuple(
                candidate.action
                for candidate
                in candidates)
        else:
            legal_keys = frozenset(
                declared_legal)
            legal = []
            for value in sorted(
                    legal_keys):
                if operation_types is not None:
                    match = (
                        _ACTION_TYPE_JSON_PATTERN
                        .search(value)
                        if isinstance(
                            value, str)
                        else None)
                    if (
                            match is not None
                            and match.group(1)
                            not in
                            legal_relevant_action_types):
                        continue
                try:
                    action = json.loads(
                        value)
                except (
                        TypeError,
                        ValueError):
                    continue
                if (
                        isinstance(action, dict)
                        and (
                            operation_types
                            is None
                            or str(
                                action.get(
                                    "action_type",
                                    ""))
                            in
                            legal_relevant_action_types)):
                    legal.append(action)
            legal = tuple(legal)
        candidate_keys = {
            candidate.action_key
            for candidate in
            candidates}
        protected_union = []
        for action in legal:
            action_type = str(
                action.get(
                    "action_type", ""))
            action_key = (
                canonical_json_bytes(
                    action).decode(
                        "utf-8"))
            if (action_type
                    not in protected_types
                    or action_key
                    in candidate_keys):
                continue
            category = (
                "city_defense"
                if action_type
                == "unit_fortify"
                else
                "tactical_attack"
                if action_type
                in (
                    protected_types
                    - {
                        "unit_fortify",
                        "unit_move",
                    })
                else
                "grounded_defense_move")
            protected_union.append(
                _DefenseActionView(
                    action=dict(action),
                    category=category,
                    projection=None,
                    readout_source=(
                        "protected-legal-action-union")))
            candidate_keys.add(
                action_key)
        candidates = (
            candidates
            + tuple(
                protected_union))
        analyzed_candidate_count = len(
            candidates)
        threats, threat_omissions = (
            self._threats(
                snapshot, ruleset_ir,
                legal))
        provisional_specs = {
            unit.unit_id: _unit_spec(
                ruleset_ir,
                unit.unit_type)
            for unit in snapshot.units}
        city_counts = {}
        for city in snapshot.cities:
            city_counts[city.city_id] = sum(
                None not in (
                    unit.x, unit.y)
                and (unit.x, unit.y)
                == (city.x, city.y)
                and provisional_specs.get(
                    unit.unit_id)
                is not None
                and _defense_capable(
                    provisional_specs[
                        unit.unit_id])
                for unit in
                snapshot.units)
        defenders = self._defenders(
            snapshot, ruleset_ir,
            city_counts,
            unit_specs=(
                provisional_specs))
        by_city = {}
        for threat in threats:
            by_city.setdefault(
                threat.city_id, []).append(
                    threat)
        city_by_id = {
            city.city_id: city
            for city in snapshot.cities}
        requirements = []
        for city_id, rows in sorted(
                by_city.items()):
            city = city_by_id[
                city_id]
            supported = [
                row for row in rows
                if row.supported]
            if not supported:
                continue
            # One visible threat raises the local response requirement by one
            # bounded slot. Additional visible units increase priority and
            # uncertainty, but do not create an unbounded defender fiction.
            required = (
                self.required_garrison
                + min(
                    1,
                    len(supported)))
            current = city_counts.get(
                city_id, 0)
            deficit = max(
                0,
                required - current)
            # A requirement represents missing defence capacity. Existing
            # surplus garrison is not an uncovered operation merely because
            # no redundant fortify action happened to be advertised.
            if deficit == 0:
                continue
            requirements.append(
                CityDefenseRequirement(
                    city_id=city_id,
                    city_position=(
                        int(city.x),
                        int(city.y)),
                    current_defenders=(
                        current),
                    required_defenders=(
                        required),
                    response_slots=(
                        deficit),
                    deadline_turn=min(
                        row
                        .earliest_attack_turn
                        for row in
                        supported),
                    threat_ids=tuple(sorted(
                        row.threat_id
                        for row in
                        supported)),
                    threat_priority=sum(
                        row.threat_priority
                        for row in
                        supported),
                    confidence=(
                        min(
                            row.confidence
                            for row
                            in supported))))
        requirements = tuple(
            requirements)
        requirements_by_city = {
            row.city_id: row
            for row in requirements}
        defender_by_id = {
            row.unit_id: row
            for row in defenders}
        threat_by_enemy = {}
        for threat in threats:
            threat_by_enemy.setdefault(
                threat.enemy_unit_id,
                []).append(threat)
        immediate_interceptions = set()
        for action in legal:
            action_type = str(
                action.get(
                    "action_type", ""))
            if (
                    action_type
                    not in
                    _ATTACK_ACTION_TYPES):
                continue
            actor_id = action.get(
                "actor_id")
            if actor_id not in defender_by_id:
                continue
            target = action.get(
                "target", {})
            if not isinstance(target, dict):
                target = {}
            enemy_ids = set()
            target_id = target.get(
                "target_unit_id")
            if target_id is not None:
                try:
                    enemy_ids.add(
                        int(target_id))
                except (TypeError, ValueError):
                    pass
            if None not in (
                    target.get("x"),
                    target.get("y")):
                enemy_ids.update(
                    enemy.unit_id
                    for enemy in
                    snapshot.visible_enemy_units
                    if (
                        enemy.x,
                        enemy.y)
                    == (
                        target.get("x"),
                        target.get("y")))
            for enemy_id in enemy_ids:
                for threat in (
                        threat_by_enemy.get(
                            enemy_id, ())):
                    if threat.supported:
                        immediate_interceptions.add((
                            actor_id,
                            threat.city_id))
        operations = []
        omissions = list(
            threat_omissions)

        def add_operation(
                operation_id,
                operation_type,
                requirement,
                actor_id, action,
                arrival_turn,
                prevented_loss,
                opportunity_cost,
                support_reason,
                claims,
                provenance):
            bid = max(
                0.0,
                float(prevented_loss)
                - float(
                    opportunity_cost))
            operations.append(
                CityDefenseOperation(
                    operation_id=(
                        operation_id),
                    operation_type=(
                        operation_type),
                    requirement_id=(
                        requirement
                        .requirement_id),
                    city_id=(
                        requirement.city_id),
                    actor_id=actor_id,
                    next_action=(
                        None
                        if action is None
                        else dict(action)),
                    arrival_turn=int(
                        arrival_turn),
                    deadline_turn=(
                        requirement
                        .deadline_turn),
                    expected_prevented_loss=(
                        float(
                            prevented_loss)),
                    opportunity_cost=(
                        float(
                            opportunity_cost)),
                    bid=bid,
                    claims=tuple(claims),
                    support_reason=(
                        support_reason),
                    provenance=tuple(
                        provenance)))

        # Protected holds make the safety invariant visible even though they
        # are constraints rather than candidates for current action.
        for defender in defenders:
            if (not defender
                    .protected_sole_defender
                    or defender
                    .current_city_id
                    not in
                    requirements_by_city):
                continue
            requirement = (
                requirements_by_city[
                    defender
                    .current_city_id])
            operation_seed = (
                self._operation_id_seed(
                    DefenseOperationType
                    .HOLD_SOLE_DEFENDER,
                    requirement
                    .requirement_id,
                    requirement.city_id,
                    defender.unit_id,
                    None))
            claim = self._actor_claim(
                snapshot, operation_seed,
                defender.unit_id,
                "hold-current-city")
            add_operation(
                operation_seed,
                DefenseOperationType
                .HOLD_SOLE_DEFENDER,
                requirement,
                defender.unit_id,
                None,
                int(snapshot.turn),
                requirement.threat_priority,
                0.0,
                None,
                (claim,),
                (
                    "authoritative-current-city-occupancy",
                    "protected-sole-defender-constraint",
                ))

        for candidate in sorted(
                candidates,
                key=lambda row:
                row.action_key):
            action = candidate.action
            action_key = (
                canonical_json_bytes(
                    action).decode(
                        "utf-8"))
            if action_key not in legal_keys:
                omissions.append(
                    "candidate-not-in-legal-set:{}".format(
                        structural_hash(
                            action)))
                continue
            action_type = str(
                action.get(
                    "action_type", ""))
            actor_id = action.get(
                "actor_id")
            defender = defender_by_id.get(
                actor_id)
            target_requirements = []
            operation_type = None
            arrival_by_requirement = {}
            native_route_requirements = set()
            native_route_alternates = set()
            native_route_deadline_misses = set()
            native_route_unreachable = set()
            production_eta_unavailable = set()
            if (candidate.category
                    == "city_defense"
                    and action_type
                    == "unit_fortify"
                    and DefenseOperationType
                    .FORTIFY_EXISTING_DEFENDER
                    in allowed_operation_types
                    and defender is not None
                    and defender
                    .current_city_id
                    in requirements_by_city):
                requirement = (
                    requirements_by_city[
                        defender
                        .current_city_id])
                target_requirements = [
                    requirement]
                operation_type = (
                    DefenseOperationType
                    .FORTIFY_EXISTING_DEFENDER)
                arrival_by_requirement[
                    requirement
                    .requirement_id] = int(
                        snapshot.turn)
            elif (action_type
                    == "unit_move"
                    and DefenseOperationType
                    .MOVE_DEFENDER_TO_CITY
                    in allowed_operation_types
                    and defender is not None):
                operation_type = (
                    DefenseOperationType
                    .MOVE_DEFENDER_TO_CITY)
                projected_ids = set(
                    (candidate.projection
                     or {}).get(
                        "target_city_ids",
                        ()))
                target = action.get(
                    "target", {})
                if not isinstance(
                        target, dict):
                    target = {}
                target_position = (
                    target.get("x"),
                    target.get("y"))
                for requirement in requirements:
                    if (projected_ids
                            and requirement
                            .city_id
                            not in
                            projected_ids):
                        continue
                    target_distance = (
                        _distance(
                            snapshot,
                            target_position,
                            requirement
                            .city_position))
                    current_distance = (
                        _distance(
                            snapshot,
                            defender.position,
                            requirement
                            .city_position))
                    if (target_distance
                            is None
                            or current_distance
                            is None
                            or target_distance
                            >= current_distance):
                        continue
                    target_requirements.append(
                        requirement)
                    arrival = (
                        int(snapshot.turn)
                        if target_distance == 0
                        else int(snapshot.turn)
                        + target_distance)
                    if target_distance > 0:
                        city = city_by_id.get(
                            requirement.city_id)
                        destination_tile = (
                            getattr(
                                city, "tile", None)
                            if city is not None
                            else None)
                        if (
                            destination_tile
                                is None
                            and city is not None
                            and None not in (
                                city.x, city.y)
                        ):
                            destination_tile = (
                                int(city.x)
                                + int(city.y)
                                * int(
                                    snapshot
                                    .map_width))
                        target_tile = (
                            int(target_position[0])
                            + int(target_position[1])
                            * int(
                                snapshot
                                .map_width))
                        route = next((
                            row for row in getattr(
                                snapshot,
                                "movement_routes",
                                ())
                            if (
                                row.unit_id
                                    == actor_id
                                and row
                                    .destination_tile
                                    == destination_tile)
                        ), None)
                        if (route is not None
                                and not route
                                .initially_transported):
                            if not route.reachable:
                                native_route_unreachable.add(
                                    requirement
                                    .requirement_id)
                            else:
                                native_arrival = (
                                    int(
                                        snapshot.turn)
                                    + int(
                                        route
                                        .estimated_turns))
                                if (native_arrival
                                        > requirement
                                        .deadline_turn):
                                    native_route_deadline_misses.add(
                                        requirement
                                        .requirement_id)
                                    # The native pathfinder's selected route
                                    # is the lower-cost route for this exact
                                    # unit/city state. A different advertised
                                    # first step cannot be credited with the
                                    # older geometric ETA when that route
                                    # already misses the deadline.
                                    arrival = (
                                        native_arrival)
                                if (route
                                        .first_step_tile
                                        == target_tile):
                                    arrival = (
                                        native_arrival)
                                    native_route_requirements.add(
                                        requirement
                                        .requirement_id)
                                elif any(
                                        str(
                                            legal_action
                                            .get(
                                                "action_type",
                                                ""))
                                        == "unit_move"
                                        and legal_action
                                        .get(
                                            "actor_id")
                                        == actor_id
                                        and isinstance(
                                            legal_action
                                            .get("target"),
                                            dict)
                                        and None not in (
                                            legal_action[
                                                "target"]
                                            .get("x"),
                                            legal_action[
                                                "target"]
                                            .get("y"))
                                        and (
                                            int(
                                                legal_action[
                                                    "target"][
                                                        "x"])
                                            + int(
                                                legal_action[
                                                    "target"][
                                                        "y"])
                                            * int(
                                                snapshot
                                                .map_width))
                                        == route
                                        .first_step_tile
                                        for legal_action
                                        in legal):
                                    arrival = (
                                        native_arrival)
                                    native_route_alternates.add(
                                        requirement
                                        .requirement_id)
                    arrival_by_requirement[
                        requirement
                        .requirement_id] = (
                            arrival)
            elif (candidate.category
                    == "tactical_attack"
                    and DefenseOperationType
                    .INTERCEPT_IMMEDIATE_THREAT
                    in allowed_operation_types
                    and action_type
                    in _ATTACK_ACTION_TYPES
                    and defender is not None):
                operation_type = (
                    DefenseOperationType
                    .INTERCEPT_IMMEDIATE_THREAT)
                target = action.get(
                    "target", {})
                enemy_ids = set()
                if isinstance(target, dict):
                    target_id = target.get(
                        "target_unit_id")
                    if target_id is not None:
                        enemy_ids.add(
                            int(target_id))
                    if None not in (
                            target.get("x"),
                            target.get("y")):
                        enemy_ids.update(
                            enemy.unit_id
                            for enemy in
                            snapshot
                            .visible_enemy_units
                            if (
                                enemy.x,
                                enemy.y)
                            == (
                                target.get("x"),
                                target.get("y")))
                for enemy_id in sorted(
                        enemy_ids):
                    for threat in (
                            threat_by_enemy.get(
                                enemy_id, ())):
                        requirement = (
                            requirements_by_city
                            .get(
                                threat.city_id))
                        if requirement is None:
                            continue
                        if requirement not in (
                                target_requirements):
                            target_requirements.append(
                                requirement)
                            arrival_by_requirement[
                                requirement
                                .requirement_id] = (
                                    int(
                                        snapshot.turn))
            elif (candidate.category
                    == "production_defense"
                    and action_type
                    == "city_production"
                    and DefenseOperationType
                    .EMERGENCY_BUILD_DEFENDER
                    in allowed_operation_types):
                city_id = action.get(
                    "city_id")
                if city_id in (
                        requirements_by_city):
                    requirement = (
                        requirements_by_city[
                            city_id])
                    target_requirements = [
                        requirement]
                    operation_type = (
                        DefenseOperationType
                        .EMERGENCY_BUILD_DEFENDER)
                    eta = (
                        candidate.projection
                        or {}).get(
                            "completion_eta_turns")
                    if (isinstance(eta, bool)
                            or not isinstance(
                                eta,
                                (int, float))
                            or not math.isfinite(
                                float(eta))
                            or eta < 0.0):
                        arrival_by_requirement[
                            requirement
                            .requirement_id] = (
                                requirement
                                .deadline_turn + 1)
                        production_eta_unavailable.add(
                            requirement
                            .requirement_id)
                    else:
                        arrival_by_requirement[
                            requirement
                            .requirement_id] = (
                                int(snapshot.turn)
                                + int(math.ceil(
                                    float(eta))))
            if operation_type is None:
                continue
            for requirement in sorted(
                    target_requirements,
                    key=lambda row:
                    row.requirement_id):
                operation_seed = (
                    self._operation_id_seed(
                        operation_type,
                        requirement
                        .requirement_id,
                        requirement.city_id,
                        actor_id, action))
                support_reason = None
                if requirement.confidence <= 0.0:
                    support_reason = (
                        "threat-value-support-incomplete")
                elif (
                        operation_type
                        == DefenseOperationType
                        .FORTIFY_EXISTING_DEFENDER
                        and (
                            actor_id,
                            requirement.city_id)
                        in immediate_interceptions):
                    support_reason = (
                        "immediate-interception-available")
                elif (defender is not None
                        and not defender.supported):
                    support_reason = (
                        defender.support_reason)
                elif (defender is not None
                        and defender
                        .protected_sole_defender
                        and defender
                        .current_city_id
                        != requirement
                        .city_id):
                    support_reason = (
                        "protected-sole-defender")
                elif (requirement
                        .requirement_id
                        in
                        production_eta_unavailable):
                    support_reason = (
                        "production-completion-eta-unavailable")
                arrival = (
                    arrival_by_requirement[
                        requirement
                        .requirement_id])
                if (support_reason is None
                        and operation_type
                        == DefenseOperationType
                        .MOVE_DEFENDER_TO_CITY
                        and requirement
                        .requirement_id
                        not in
                        native_route_requirements
                        and (
                            arrival
                            > int(
                                snapshot.turn)
                            or requirement
                            .requirement_id
                            in
                            native_route_unreachable
                            or requirement
                            .requirement_id
                            in
                            native_route_deadline_misses
                            or requirement
                            .requirement_id
                            in
                            native_route_alternates)):
                    if (requirement
                            .requirement_id
                            in
                            native_route_unreachable):
                        support_reason = (
                            "defender-native-route-unreachable")
                    elif (requirement
                            .requirement_id
                            in
                            native_route_deadline_misses):
                        support_reason = (
                            "native-route-misses-threat-deadline")
                    elif (requirement
                            .requirement_id
                            in
                            native_route_alternates):
                        support_reason = (
                            "alternate-step-not-native-selected-route")
                    else:
                        support_reason = (
                            "defender-route-eta-unavailable")
                if (support_reason is None
                        and arrival
                        > requirement
                        .deadline_turn):
                    support_reason = (
                        "arrival-after-threat-deadline")
                claims = []
                if actor_id is not None:
                    claims.append(
                        self._actor_claim(
                            snapshot,
                            operation_seed,
                            actor_id,
                            "current-defence-action"))
                    if action_type == (
                            "unit_move"):
                        movement_cost = (
                            action.get(
                                "movement_cost"))
                        known_cost = (
                            not isinstance(
                                movement_cost,
                                bool)
                            and isinstance(
                                movement_cost,
                                (int, float))
                            and math.isfinite(
                                float(
                                    movement_cost))
                            and movement_cost > 0
                            and int(
                                movement_cost)
                            == movement_cost)
                        claims.append(
                            ResourceClaim(
                                resource=(
                                    ResourceRef(
                                        GameResourceKind
                                        .MOVE_POINTS,
                                        "unit:{}".format(
                                            actor_id),
                                        "current_turn",
                                        "player:{}".format(
                                            snapshot
                                            .player_id))),
                                quantity=(
                                    int(movement_cost)
                                    if known_cost
                                    else 1),
                                window=TurnWindow(
                                    int(
                                        snapshot.turn),
                                    int(
                                        snapshot.turn)
                                    + 1),
                                hardness=(
                                    ClaimHardness
                                    .HARD_CURRENT
                                    if known_cost
                                    else
                                    ClaimHardness
                                    .ADVISORY),
                                exclusive=False,
                                source_operation_id=(
                                    operation_seed),
                                source_step_id=(
                                    "current-movement")))
                else:
                    claims.append(
                        ResourceClaim(
                            resource=ResourceRef(
                                GameResourceKind
                                .CITY_PRODUCTION_SLOT,
                                "city:{}".format(
                                    requirement
                                    .city_id),
                                "production",
                                "player:{}".format(
                                    snapshot
                                    .player_id)),
                            quantity=1,
                            window=TurnWindow(
                                int(snapshot.turn),
                                int(snapshot.turn)
                                + 1),
                            hardness=(
                                ClaimHardness
                                .HARD_CURRENT),
                            exclusive=True,
                            source_operation_id=(
                                operation_seed),
                            source_step_id=(
                                "emergency-production")))
                contribution = (
                    defender
                    .effective_defense
                    if defender is not None
                    and defender
                    .effective_defense
                    is not None
                    else 1.0)
                prevented = (
                    requirement
                    .threat_priority
                    * max(
                        0.1,
                        contribution)
                    * requirement
                    .confidence)
                opportunity = (
                    max(
                        0.0,
                        float(
                            defender
                            .effective_defense))
                    * 0.1
                    if (defender
                        is not None
                        and defender
                        .effective_defense
                        is not None
                        and defender
                        .current_city_id
                        is not None
                        and operation_type
                        in (
                            DefenseOperationType
                            .MOVE_DEFENDER_TO_CITY,
                            DefenseOperationType
                            .INTERCEPT_IMMEDIATE_THREAT))
                    else 0.0)
                add_operation(
                    operation_seed,
                    operation_type,
                    requirement,
                    actor_id, action,
                    arrival,
                    prevented,
                    opportunity,
                    support_reason,
                    claims,
                    (
                        "server-advertised-legal-action",
                        getattr(
                            candidate,
                            "readout_source",
                            "legacy-candidate-readout"),
                        "visible-city-threat",
                        "native-server-route-eta"
                        if requirement
                        .requirement_id
                        in
                        native_route_requirements
                        else
                        "native-server-route-deadline-bound"
                        if requirement
                        .requirement_id
                        in
                        native_route_deadline_misses
                        else
                        "native-server-selected-route-dominates-alternate"
                        if requirement
                        .requirement_id
                        in
                        native_route_alternates
                        else
                        "native-server-route-unreachable"
                        if requirement
                        .requirement_id
                        in
                        native_route_unreachable
                        else
                        "route-eta-not-grounded",
                        "ruleset-unit-stat"
                        if support_reason
                        not in (
                            "threat-value-support-incomplete",
                            "ruleset-unit-spec-unavailable")
                        else
                        "incomplete-ruleset-support",
                    ))
        return CityDefenseAnalysis(
            snapshot_id=str(
                snapshot.snapshot_id),
            threats=threats,
            requirements=requirements,
            defenders=defenders,
            operations=tuple(sorted(
                operations,
                key=lambda row: (
                    row.operation_id))),
            omissions=tuple(sorted(set(
                omissions))),
            analyzer_identity=(
                self.ANALYZER_IDENTITY),
            input_candidate_count=(
                input_candidate_count),
            analyzed_candidate_count=(
                analyzed_candidate_count),
            protected_union_added_count=(
                len(protected_union)))


@dataclass(frozen=True)
class CityDefenseAssignment:
    selected_operation_ids: tuple
    entries: tuple
    covered_slots: int
    uncovered_slots: int
    objective_value: float
    status: str
    explored_nodes: int
    node_budget: int
    fallback_reason: object
    solver_identity: str

    def __post_init__(self):
        if (tuple(sorted(set(
                self.selected_operation_ids)))
                != self.selected_operation_ids
                or any(
                    not isinstance(value, str)
                    or not value
                    for value in
                    self.selected_operation_ids)):
            raise ValueError(
                "selected defence operations must be unique and sorted")
        if any(
                not isinstance(row, dict)
                for row in self.entries):
            raise TypeError(
                "defence assignment entries must be dictionaries")
        for value, name in (
                (self.covered_slots,
                 "covered slots"),
                (self.uncovered_slots,
                 "uncovered slots"),
                (self.explored_nodes,
                 "explored nodes"),
                (self.node_budget,
                 "node budget")):
            if (isinstance(value, bool)
                    or not isinstance(
                        value, int)
                    or value < 0):
                raise ValueError(
                    "{} must be non-negative".format(name))
        if self.node_budget < 1:
            raise ValueError(
                "defence assignment node budget must be positive")
        if (not math.isfinite(
                float(
                    self.objective_value))
                or self.objective_value < 0.0):
            raise ValueError(
                "defence objective must be non-negative")
        if self.status not in (
                "exact",
                "greedy_fallback"):
            raise ValueError(
                "unknown defence assignment status")
        if (self.status == "exact"
                and self.fallback_reason
                is not None):
            raise ValueError(
                "exact defence assignment has no fallback reason")
        if (self.status
                == "greedy_fallback"
                and (not isinstance(
                    self.fallback_reason,
                    str)
                     or not self
                     .fallback_reason)):
            raise ValueError(
                "fallback defence assignment requires a reason")
        if (not isinstance(
                self.solver_identity, str)
                or not self.solver_identity):
            raise ValueError(
                "defence solver identity is required")

    @cached_property
    def decision_digest(self):
        return structural_hash(
            self.to_dict(
                include_digest=False))

    def to_dict(
            self, include_digest=True):
        payload = {
            "covered_slots":
                self.covered_slots,
            "entries": [
                dict(row)
                for row in self.entries],
            "explored_nodes":
                self.explored_nodes,
            "fallback_reason":
                self.fallback_reason,
            "node_budget":
                self.node_budget,
            "objective_value":
                float(
                    self.objective_value),
            "policy_authority": False,
            "selected_operation_ids":
                list(
                    self.selected_operation_ids),
            "shadow_only": True,
            "solver_identity":
                self.solver_identity,
            "status": self.status,
            "uncovered_slots":
                self.uncovered_slots,
        }
        if include_digest:
            payload["decision_digest"] = (
                self.decision_digest)
        return payload


class ExactCityDefenseAssignmentSolver:
    """Deterministic bounded exact matching with coverage-first objective."""

    SOLVER_IDENTITY = (
        "freeciv-exact-city-defense-assignment/1.0")

    def __init__(self, node_budget=100000):
        if (isinstance(node_budget, bool)
                or not isinstance(
                    node_budget, int)
                or node_budget < 1):
            raise ValueError(
                "defence assignment node budget must be positive")
        self.node_budget = node_budget

    @staticmethod
    def _greedy(
            requirements, operations):
        remaining = {
            row.requirement_id:
                row.response_slots
            for row in requirements}
        actors = set()
        cities = set()
        selected = []
        for operation in sorted(
                operations,
                key=lambda row: (
                    -float(row.bid),
                    row.operation_id)):
            if (not operation.supported
                    or operation
                    .operation_type
                    == DefenseOperationType
                    .HOLD_SOLE_DEFENDER
                    or remaining.get(
                        operation
                        .requirement_id,
                        0) <= 0
                    or (
                        operation.actor_id
                        is not None
                        and operation.actor_id
                        in actors)
                    or (
                        operation.actor_id
                        is None
                        and operation.city_id
                        in cities)):
                continue
            selected.append(
                operation)
            remaining[
                operation.requirement_id] -= 1
            if operation.actor_id is None:
                cities.add(
                    operation.city_id)
            else:
                actors.add(
                    operation.actor_id)
        return tuple(
            selected)

    def schedule(self, analysis):
        if not isinstance(
                analysis,
                CityDefenseAnalysis):
            raise TypeError(
                "defence assignment requires CityDefenseAnalysis")
        requirements = analysis.requirements
        operations = tuple(
            row for row in analysis.operations
            if row.operation_type
            != DefenseOperationType
            .HOLD_SOLE_DEFENDER)
        operations = tuple(sorted(
            operations,
            key=lambda row: (
                -float(row.bid),
                row.operation_id)))
        total_slots = sum(
            row.response_slots
            for row in requirements)
        slots = {
            row.requirement_id:
                row.response_slots
            for row in requirements}
        explored = [0]
        exhausted = [False]
        best_covered = [-1]
        best_value = [-1.0]
        best_ids = [()]

        def visit(
                index, selected,
                actors, cities,
                used_slots, value):
            if exhausted[0]:
                return
            if explored[0] >= (
                    self.node_budget):
                exhausted[0] = True
                return
            explored[0] += 1
            if index == len(operations):
                ids = tuple(sorted(
                    row.operation_id
                    for row in selected))
                covered = len(
                    selected)
                if (covered
                        > best_covered[0]
                        or (
                            covered
                            == best_covered[0]
                            and float(value)
                            > best_value[0]
                            + 1e-12)
                        or (
                            covered
                            == best_covered[0]
                            and abs(
                                float(value)
                                - best_value[0])
                            <= 1e-12
                            and (
                                not best_ids[0]
                                or ids
                                < best_ids[0]))):
                    best_covered[0] = (
                        covered)
                    best_value[0] = (
                        float(value))
                    best_ids[0] = ids
                return
            operation = operations[index]
            can_select = bool(
                operation.supported
                and used_slots.get(
                    operation
                    .requirement_id,
                    0)
                < slots.get(
                    operation
                    .requirement_id,
                    0)
                and (
                    operation.actor_id
                    is None
                    and operation.city_id
                    not in cities
                    or operation.actor_id
                    is not None
                    and operation.actor_id
                    not in actors))
            if can_select:
                next_slots = dict(
                    used_slots)
                next_slots[
                    operation
                    .requirement_id] = (
                        next_slots.get(
                            operation
                            .requirement_id,
                            0) + 1)
                visit(
                    index + 1,
                    selected
                    + (operation,),
                    actors
                    | ({
                        operation.actor_id}
                       if operation
                       .actor_id
                       is not None
                       else set()),
                    cities
                    | ({
                        operation.city_id}
                       if operation
                       .actor_id
                       is None
                       else set()),
                    next_slots,
                    value
                    + operation.bid)
            visit(
                index + 1,
                selected, actors,
                cities, used_slots,
                value)

        visit(
            0, (), set(), set(),
            {}, 0.0)
        fallback_reason = None
        if exhausted[0]:
            selected = self._greedy(
                requirements,
                operations)
            selected_ids = tuple(sorted(
                row.operation_id
                for row in selected))
            status = "greedy_fallback"
            fallback_reason = (
                "node-budget-exhausted")
        else:
            selected_ids = (
                best_ids[0])
            selected_set = frozenset(
                selected_ids)
            selected = tuple(
                row for row in operations
                if row.operation_id
                in selected_set)
            status = "exact"
        selected_set = frozenset(
            selected_ids)
        selected_by_requirement = {}
        for operation in selected:
            selected_by_requirement[
                operation.requirement_id] = (
                    selected_by_requirement.get(
                        operation
                        .requirement_id, 0)
                    + 1)
        entries = []
        for operation in sorted(
                analysis.operations,
                key=lambda row:
                row.operation_id):
            selected_row = (
                operation.operation_id
                in selected_set)
            if selected_row:
                reason = None
            elif not operation.supported:
                reason = (
                    operation.support_reason
                    or "arrival-after-threat-deadline")
            elif (operation.operation_type
                    == DefenseOperationType
                    .HOLD_SOLE_DEFENDER):
                reason = (
                    "protected-constraint")
            elif (selected_by_requirement.get(
                    operation
                    .requirement_id, 0)
                  >= slots.get(
                      operation
                      .requirement_id, 0)):
                reason = (
                    "requirement-covered")
            elif (operation.actor_id
                    is not None
                    and any(
                        row.actor_id
                        == operation.actor_id
                        for row
                        in selected)):
                reason = (
                    "actor-already-assigned")
            elif (operation.actor_id
                    is None
                    and any(
                        row.actor_id
                        is None
                        and row.city_id
                        == operation.city_id
                        for row
                        in selected)):
                reason = (
                    "city-production-already-assigned")
            else:
                reason = (
                    "lower-objective")
            entries.append({
                "actor_id":
                    operation.actor_id,
                "city_id":
                    operation.city_id,
                "operation_id":
                    operation
                    .operation_id,
                "operation_type":
                    operation
                    .operation_type.value,
                "reason": reason,
                "requirement_id":
                    operation
                    .requirement_id,
                "selected":
                    selected_row,
            })
        covered = len(
            selected)
        return CityDefenseAssignment(
            selected_operation_ids=(
                selected_ids),
            entries=tuple(entries),
            covered_slots=covered,
            uncovered_slots=max(
                0,
                total_slots - covered),
            objective_value=sum(
                row.bid
                for row in selected),
            status=status,
            explored_nodes=(
                explored[0]),
            node_budget=(
                self.node_budget),
            fallback_reason=(
                fallback_reason),
            solver_identity=(
                self.SOLVER_IDENTITY))


def build_city_defense_assignment_artifact(
        snapshot, ruleset_ir, candidates,
        threat_radius, node_budget,
        ruleset_digest,
        baseline_action_key=None,
        analysis_operation_types=None,
        live_operation_types=None,
        maximum_authority_lead_turns=None):
    """Build one decision-safe exact-assignment readout for a snapshot.

    This shared boundary keeps the asynchronous GDO-4 shadow path and the
    default-off synchronous pilot path on byte-identical threat, coverage, and
    fallback semantics.  The artifact itself never grants policy authority.
    """
    analysis = CityDefenseAnalyzer(
        threat_radius=threat_radius).analyze(
            snapshot, ruleset_ir,
            tuple(candidates),
            operation_types=(
                analysis_operation_types))
    assignment = ExactCityDefenseAssignmentSolver(
        node_budget=node_budget).schedule(
            analysis)
    selected_ids = frozenset(
        assignment.selected_operation_ids)
    live_types = (
        CITY_DEFENSE_LIVE_OPERATION_TYPES
        if live_operation_types is None
        else frozenset(
            DefenseOperationType(
                value)
            for value in
            live_operation_types))
    non_displacing_local_readout = bool(
        live_types
        and live_types <= {
            DefenseOperationType
            .FORTIFY_EXISTING_DEFENDER,
        })
    selected_operations = tuple(
        row for row in analysis.operations
        if row.operation_id in selected_ids
        and row.next_action is not None)
    authority_operations = tuple(
        row for row in selected_operations
        if row.operation_type
        in live_types
        and (
            maximum_authority_lead_turns
            is None
            or row.deadline_turn
            <= (
                int(snapshot.turn)
                + int(
                    maximum_authority_lead_turns)))
        and (
            row.operation_type
            != DefenseOperationType
            .MOVE_DEFENDER_TO_CITY
            # A move command can advance only part of the native route.  Do
            # not authorize one on the deadline turn because no later exact
            # snapshot remains in which to prove that it reached the city.
            or row.deadline_turn
            > int(snapshot.turn)))
    readout = (
        sorted(
            authority_operations,
            key=lambda row: (
                -float(row.bid),
                row.operation_id))[0]
        if authority_operations
        else None)
    supported_threats = sum(
        row.supported
        for row in analysis.threats)
    threat_count = len(
        analysis.threats)
    threat_coverage = (
        1.0
        if threat_count == 0
        else float(supported_threats)
        / threat_count)
    requirement_count = len(
        analysis.requirements)
    supported_requirements = sum(
        any(
            operation.supported
            and operation.next_action
            is not None
            and operation.requirement_id
            == requirement.requirement_id
            for operation in
            analysis.operations)
        for requirement in
        analysis.requirements)
    operation_edge_coverage = (
        1.0
        if requirement_count == 0
        else float(supported_requirements)
        / requirement_count)
    operation_count = len(
        analysis.operations)
    grounded_operation_count = sum(
        grounded_operation_result(operation)
        for operation in
        analysis.operations)
    grounded_operation_coverage = (
        1.0
        if operation_count == 0
        else float(grounded_operation_count)
        / operation_count)
    decision_resolved_requirements = sum(
        bool(requirement_operations)
        and all(
            grounded_operation_result(
                operation)
            for operation in
            requirement_operations)
        for requirement in
        analysis.requirements
        for requirement_operations
        in (tuple(
            operation
            for operation in
            analysis.operations
            if operation.requirement_id
            == requirement.requirement_id),))
    decision_resolution_coverage = (
        1.0
        if requirement_count == 0
        else float(
            decision_resolved_requirements)
        / requirement_count)
    decision_safe_readout = bool(
        readout is not None
        and readout.supported
        and assignment.status == "exact"
        and threat_coverage >= 0.90
        and grounded_operation_coverage >= 0.90
        and (
            non_displacing_local_readout
            or decision_resolution_coverage
            >= 0.90))
    payload = {
        "analysis": analysis.to_dict(),
        "assignment":
            assignment.to_dict(),
        "authority_active": False,
        "b1_action_key":
            baseline_action_key,
        "actionable_requirement_coverage":
            operation_edge_coverage,
        "decision_resolved_requirement_coverage":
            decision_resolution_coverage,
        "decision_safe_candidate_readout":
            decision_safe_readout,
        "fallback_reason": (
            "no-city-defense-requirement"
            if not analysis.requirements
            else
            "typed-defense-coverage-below-90-percent"
            if threat_coverage < 0.90
            else
            "typed-defense-operation-evaluation-coverage-below-90-percent"
            if grounded_operation_coverage < 0.90
            else
            "typed-defense-decision-resolution-below-90-percent"
            if (
                decision_resolution_coverage
                < 0.90
                and not
                non_displacing_local_readout)
            else
            "typed-defense-assignment-not-exact"
            if assignment.status != "exact"
            else
            "no-supported-current-defense-action"
            if readout is None
            else
            "shadow-only-gdo4"),
        "fallback_to_b1": True,
        "live_ordering_unchanged": True,
        "live_readout_scope": (
            "non-displacing-local"
            if non_displacing_local_readout
            else "globally-resolved"),
        "policy_authority": False,
        "protected_union_added_count":
            analysis.protected_union_added_count,
        "schema_version": "1.0",
        "ruleset_digest":
            str(ruleset_digest),
        "typed_grounded_operation_coverage":
            grounded_operation_coverage,
        "selected_action_key": (
            None
            if (
                readout is None
                or not
                decision_safe_readout)
            else canonical_json_bytes(
                readout.next_action)
            .decode("utf-8")),
        "shadow_only": True,
        "source_turn": int(
            snapshot.turn),
        "typed_threat_coverage":
            threat_coverage,
        "typed_operation_edge_coverage":
            operation_edge_coverage,
    }
    payload["artifact_hash"] = (
        structural_hash(payload))
    return payload
