"""Stable, candidate-invariant identities for grounded movement corridors."""

from dataclasses import dataclass

from ..events.schema import structural_hash


def _position(value, name):
    value = tuple(value)
    if (len(value) != 2
            or any(isinstance(item, bool)
                   or not isinstance(item, int)
                   for item in value)):
        raise ValueError(
            "{} must be an integer x/y pair".format(name))
    return value


@dataclass(frozen=True)
class PathCorridor:
    schema_version: int
    actor_id: str
    source_position: tuple
    destination_position: tuple
    tile_path: tuple
    candidate_next_hops: tuple
    visibility: str

    def __post_init__(self):
        if self.schema_version != 1:
            raise ValueError(
                "unsupported path corridor schema")
        if not isinstance(self.actor_id, str) or not self.actor_id:
            raise ValueError(
                "path corridor requires an actor ID")
        _position(
            self.source_position,
            "corridor source")
        _position(
            self.destination_position,
            "corridor destination")
        if (not self.tile_path
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                    for value in self.tile_path)):
            raise ValueError(
                "path corridor tile IDs must be non-negative integers")
        hops = tuple(
            _position(row, "candidate next hop")
            for row in self.candidate_next_hops)
        if tuple(sorted(set(hops))) != hops:
            raise ValueError(
                "candidate next hops must be unique and sorted")
        if self.visibility not in (
                "visible", "known-not-visible",
                "unknown"):
            raise ValueError(
                "unknown path visibility status")

    @property
    def corridor_digest(self):
        return structural_hash({
            "actor_id": self.actor_id,
            "candidate_next_hops": [
                list(value)
                for value in self.candidate_next_hops],
            "destination_position": list(
                self.destination_position),
            "schema_version":
                self.schema_version,
            "source_position": list(
                self.source_position),
            "tile_path": list(
                self.tile_path),
            "visibility": self.visibility,
        })

    def to_dict(self):
        return {
            "actor_id": self.actor_id,
            "candidate_next_hops": [
                list(value)
                for value in self.candidate_next_hops],
            "corridor_digest":
                self.corridor_digest,
            "destination_position": list(
                self.destination_position),
            "schema_version":
                self.schema_version,
            "source_position": list(
                self.source_position),
            "tile_path": list(
                self.tile_path),
            "visibility": self.visibility,
        }

def adjacent_action_corridor(snapshot, legal_action):
    """Build the exact one-edge corridor declared by a legal move action."""
    if not isinstance(legal_action, dict):
        raise TypeError(
            "movement corridor requires a legal action")
    actor_id = legal_action.get(
        "actor_id", legal_action.get("unit_id"))
    unit = (
        snapshot.unit(actor_id)
        if actor_id is not None
        and callable(getattr(
            snapshot, "unit", None))
        else None)
    target = legal_action.get("target")
    if (unit is None
            or unit.x is None
            or unit.y is None
            or not isinstance(target, dict)
            or isinstance(target.get("x"), bool)
            or not isinstance(target.get("x"), int)
            or isinstance(target.get("y"), bool)
            or not isinstance(target.get("y"), int)):
        raise ValueError(
            "movement corridor requires exact actor and target positions")
    width = int(getattr(
        snapshot, "map_width"))
    height = int(getattr(
        snapshot, "map_height"))
    if width <= 0 or height <= 0:
        raise ValueError(
            "movement corridor requires positive map dimensions")
    x = int(target["x"])
    y = int(target["y"])
    if not 0 <= x < width or not 0 <= y < height:
        raise ValueError(
            "movement target is outside the authoritative map")
    delta_x = abs(x - int(unit.x))
    delta_y = abs(y - int(unit.y))
    if getattr(snapshot, "map_wrap_x", None) is True:
        delta_x = min(delta_x, width - delta_x)
    if getattr(snapshot, "map_wrap_y", None) is True:
        delta_y = min(delta_y, height - delta_y)
    if (delta_x == 0 and delta_y == 0) or max(
            delta_x, delta_y) != 1:
        raise ValueError(
            "movement corridor supports one adjacent edge only")
    source_tile = (
        int(unit.tile)
        if unit.tile is not None else
        int(unit.y) * width + int(unit.x))
    target_tile = y * width + x
    visible = set(getattr(
        snapshot, "visible_tile_ids", ()))
    known = {
        int(row["index"])
        for row in getattr(
            snapshot, "map_tiles", ())
        if isinstance(row, dict)
        and row.get("index") is not None
    }
    visibility = (
        "visible"
        if target_tile in visible else
        "known-not-visible"
        if target_tile in known else
        "unknown")
    return PathCorridor(
        schema_version=1,
        actor_id=str(actor_id),
        source_position=(
            int(unit.x), int(unit.y)),
        destination_position=(x, y),
        tile_path=(
            source_tile, target_tile),
        candidate_next_hops=((x, y),),
        visibility=visibility)


@dataclass(frozen=True)
class NativeRouteCorridor:
    """Stable summary of one exact-revision native pathfinder result."""

    schema_version: int
    actor_id: str
    origin_tile: int
    destination_tile: int
    first_step_tile: int
    path_directions: tuple
    path_length: int
    estimated_turns: int
    total_movement_cost: int
    snapshot_id: str
    visibility: str

    def __post_init__(self):
        if self.schema_version != 1:
            raise ValueError(
                "unsupported native route corridor schema")
        if not isinstance(
                self.actor_id, str
                ) or not self.actor_id:
            raise ValueError(
                "native route corridor requires an actor ID")
        for value, name in (
                (self.origin_tile, "origin tile"),
                (self.destination_tile,
                 "destination tile"),
                (self.first_step_tile,
                 "first-step tile"),
                (self.path_length,
                 "path length"),
                (self.estimated_turns,
                 "estimated turns"),
                (self.total_movement_cost,
                 "total movement cost")):
            if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
            ):
                raise ValueError(
                    "native route corridor {} must be non-negative"
                    .format(name))
        directions = tuple(
            self.path_directions)
        if (
                any(
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                    for value in directions)
                or len(directions)
                    != self.path_length
        ):
            raise ValueError(
                "native route directions must match path length")
        object.__setattr__(
            self, "path_directions",
            directions)
        if not isinstance(
                self.snapshot_id, str
                ) or not self.snapshot_id:
            raise ValueError(
                "native route corridor requires snapshot identity")
        if self.visibility not in (
                "visible", "known-not-visible",
                "unknown"):
            raise ValueError(
                "unknown native route visibility status")

    @property
    def corridor_digest(self):
        return structural_hash({
            "actor_id": self.actor_id,
            "destination_tile":
                self.destination_tile,
            "estimated_turns":
                self.estimated_turns,
            "first_step_tile":
                self.first_step_tile,
            "origin_tile": self.origin_tile,
            "path_directions": list(
                self.path_directions),
            "path_length": self.path_length,
            "schema_version":
                self.schema_version,
            "total_movement_cost":
                self.total_movement_cost,
            "visibility": self.visibility,
        })

    def to_dict(self):
        return {
            "actor_id": self.actor_id,
            "corridor_digest":
                self.corridor_digest,
            "destination_tile":
                self.destination_tile,
            "estimated_turns":
                self.estimated_turns,
            "first_step_tile":
                self.first_step_tile,
            "origin_tile": self.origin_tile,
            "path_directions": list(
                self.path_directions),
            "path_length": self.path_length,
            "schema_version":
                self.schema_version,
            "snapshot_id": self.snapshot_id,
            "total_movement_cost":
                self.total_movement_cost,
            "visibility": self.visibility,
        }

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise TypeError("native route corridor must be an object")
        try:
            corridor = cls(
                schema_version=value["schema_version"],
                actor_id=value["actor_id"],
                origin_tile=value["origin_tile"],
                destination_tile=value["destination_tile"],
                first_step_tile=value["first_step_tile"],
                path_directions=tuple(value["path_directions"]),
                path_length=value["path_length"],
                estimated_turns=value["estimated_turns"],
                total_movement_cost=value["total_movement_cost"],
                snapshot_id=value["snapshot_id"],
                visibility=value["visibility"],
            )
        except KeyError as error:
            raise ValueError(
                "native route corridor field is missing: {}".format(
                    error.args[0]))
        digest = value.get("corridor_digest")
        if not isinstance(digest, str) or digest != corridor.corridor_digest:
            raise ValueError("native route corridor digest mismatch")
        return corridor


def native_route_corridor(
        snapshot, actor_id,
        destination_tile):
    """Return a validated exact-turn corridor or raise ``ValueError``."""
    route = snapshot.movement_route(
        actor_id, destination_tile)
    if route is None:
        raise ValueError(
            "native route is unavailable")
    if (
            route.authority
                != "freeciv-server-pathfinder"
            or route.schema_version != "1.0"
            or not route.reachable
    ):
        raise ValueError(
            "native route is not an authoritative reachable path")
    actor = snapshot.unit(
        actor_id)
    if (
            actor is None
            or actor.tile
                != route.origin_tile
            or route.turn
                != snapshot.turn
            or route.source_seq
                > snapshot.identity.source_seq
    ):
        raise ValueError(
            "native route does not match current actor revision")
    visible = set(getattr(
        snapshot, "visible_tile_ids", ()))
    known = {
        int(row["index"])
        for row in getattr(
            snapshot, "map_tiles", ())
        if isinstance(row, dict)
        and row.get("index") is not None
    }
    visibility = (
        "visible"
        if route.destination_tile in visible
        else "known-not-visible"
        if route.destination_tile in known
        else "unknown")
    return NativeRouteCorridor(
        schema_version=1,
        actor_id="unit:{}".format(
            actor_id),
        origin_tile=int(
            route.origin_tile),
        destination_tile=int(
            route.destination_tile),
        first_step_tile=int(
            route.first_step_tile),
        path_directions=tuple(
            route.path_directions),
        path_length=int(
            route.path_length),
        estimated_turns=int(
            route.estimated_turns),
        total_movement_cost=int(
            route.total_movement_cost),
        snapshot_id=(
            snapshot.snapshot_id),
        visibility=visibility)
