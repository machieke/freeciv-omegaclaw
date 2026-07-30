"""Identity- and time-bearing game resource contracts."""

from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from typing import Optional

from ..events.schema import structural_hash


class GameResourceKind(str, Enum):
    ACTOR = "actor"
    MOVE_POINTS = "move_points"
    CITY_PRODUCTION_SLOT = "city_production_slot"
    TILE_OCCUPANCY = "tile_occupancy"
    TRANSPORT_SEAT = "transport_seat"
    TREASURY = "treasury"
    RESEARCH_SLOT = "research_slot"
    DIPLOMATIC_COMMITMENT = "diplomatic_commitment"
    ACTION_BUDGET = "action_budget"
    CPU = "cpu"


class ClaimHardness(str, Enum):
    HARD_CURRENT = "hard_current"
    CONDITIONAL_FUTURE = "conditional_future"
    ADVISORY = "advisory"


@dataclass(frozen=True)
class ResourceRef:
    kind: GameResourceKind
    owner_id: str
    subresource: Optional[str]
    scope: str

    def __post_init__(self):
        if not isinstance(
                self.kind, GameResourceKind):
            raise TypeError(
                "game resource kind has the wrong type")
        for value, name in (
                (self.owner_id, "resource owner ID"),
                (self.scope, "resource scope")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "{} must be a non-empty string".format(name))
        if (self.subresource is not None
                and (not isinstance(
                    self.subresource, str)
                     or not self.subresource)):
            raise ValueError(
                "resource subresource must be non-empty or absent")

    @cached_property
    def resource_id(self):
        return structural_hash(
            self.to_dict())

    @property
    def sort_key(self):
        return (
            self.kind.value,
            self.scope,
            self.owner_id,
            self.subresource or "",
        )

    def to_dict(self):
        return {
            "kind": self.kind.value,
            "owner_id": self.owner_id,
            "scope": self.scope,
            "subresource": self.subresource,
        }


@dataclass(frozen=True)
class TurnWindow:
    start_turn: int
    end_turn_exclusive: int

    def __post_init__(self):
        for value, name in (
                (self.start_turn, "window start"),
                (self.end_turn_exclusive,
                 "window exclusive end")):
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0):
                raise ValueError(
                    "{} must be a non-negative integer".format(name))
        if self.end_turn_exclusive <= self.start_turn:
            raise ValueError(
                "turn window must contain at least one turn")

    def overlaps(self, other):
        if not isinstance(other, TurnWindow):
            raise TypeError(
                "turn-window overlap requires TurnWindow")
        return bool(
            self.start_turn
            < other.end_turn_exclusive
            and other.start_turn
            < self.end_turn_exclusive)

    def covers(self, other):
        if not isinstance(other, TurnWindow):
            raise TypeError(
                "turn-window coverage requires TurnWindow")
        return bool(
            self.start_turn <= other.start_turn
            and self.end_turn_exclusive
            >= other.end_turn_exclusive)

    @property
    def duration(self):
        return (
            self.end_turn_exclusive
            - self.start_turn)

    def to_dict(self):
        return {
            "end_turn_exclusive":
                self.end_turn_exclusive,
            "start_turn": self.start_turn,
        }


@dataclass(frozen=True)
class ResourceClaim:
    resource: ResourceRef
    quantity: int
    window: TurnWindow
    hardness: ClaimHardness
    exclusive: bool
    source_operation_id: str
    source_step_id: str

    def __post_init__(self):
        if not isinstance(
                self.resource, ResourceRef):
            raise TypeError(
                "resource claim requires ResourceRef")
        if (isinstance(self.quantity, bool)
                or not isinstance(self.quantity, int)
                or self.quantity <= 0):
            raise ValueError(
                "resource claim quantity must be positive")
        if not isinstance(self.window, TurnWindow):
            raise TypeError(
                "resource claim requires TurnWindow")
        if not isinstance(
                self.hardness, ClaimHardness):
            raise TypeError(
                "resource claim hardness has the wrong type")
        if not isinstance(self.exclusive, bool):
            raise TypeError(
                "resource claim exclusivity must be boolean")
        for value, name in (
                (self.source_operation_id,
                 "source operation ID"),
                (self.source_step_id,
                 "source step ID")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "{} must be a non-empty string".format(name))

    @cached_property
    def claim_id(self):
        return structural_hash(
            self.to_dict())

    @property
    def sort_key(self):
        return (
            self.resource.sort_key,
            self.window.start_turn,
            self.window.end_turn_exclusive,
            self.hardness.value,
            not self.exclusive,
            self.source_operation_id,
            self.source_step_id,
            self.quantity,
        )

    def to_dict(self):
        return {
            "exclusive": self.exclusive,
            "hardness": self.hardness.value,
            "quantity": self.quantity,
            "resource": self.resource.to_dict(),
            "source_operation_id":
                self.source_operation_id,
            "source_step_id":
                self.source_step_id,
            "window": self.window.to_dict(),
        }


@dataclass(frozen=True)
class ResourceCapacity:
    resource: ResourceRef
    quantity: int
    window: TurnWindow
    snapshot_id: str
    authority: str

    def __post_init__(self):
        if not isinstance(
                self.resource, ResourceRef):
            raise TypeError(
                "resource capacity requires ResourceRef")
        if (isinstance(self.quantity, bool)
                or not isinstance(self.quantity, int)
                or self.quantity < 0):
            raise ValueError(
                "resource capacity quantity must be non-negative")
        if not isinstance(self.window, TurnWindow):
            raise TypeError(
                "resource capacity requires TurnWindow")
        for value, name in (
                (self.snapshot_id, "capacity snapshot ID"),
                (self.authority, "capacity authority")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "{} must be a non-empty string".format(name))

    @cached_property
    def capacity_id(self):
        return structural_hash(
            self.to_dict())

    @property
    def sort_key(self):
        return (
            self.resource.sort_key,
            self.window.start_turn,
            self.window.end_turn_exclusive,
            self.snapshot_id,
            self.authority,
            self.quantity,
        )

    def to_dict(self):
        return {
            "authority": self.authority,
            "quantity": self.quantity,
            "resource": self.resource.to_dict(),
            "snapshot_id": self.snapshot_id,
            "window": self.window.to_dict(),
        }


def legacy_packet_resource_ref(resource):
    """Return an anonymous v2 identity without changing v1 packet semantics."""
    from .packets import ResourceKind

    if not isinstance(resource, ResourceKind):
        raise TypeError(
            "legacy resource adapter requires ResourceKind")
    kind = (
        GameResourceKind.ACTION_BUDGET
        if resource == ResourceKind.ACTION
        else GameResourceKind.CPU)
    return ResourceRef(
        kind=kind,
        owner_id="legacy-packet:{}".format(
            resource.value),
        subresource=(
            None
            if resource in (
                ResourceKind.ACTION,
                ResourceKind.CPU)
            else resource.value),
        scope="legacy-controller")


def claims_from_packet_costs(
        operation_id, step_id, packet_costs,
        turn, hardness=ClaimHardness.HARD_CURRENT):
    """Adapt v1 packet costs to anonymous identity-bearing current claims."""
    from .packets import PacketCost

    if (not isinstance(operation_id, str)
            or not operation_id
            or not isinstance(step_id, str)
            or not step_id):
        raise ValueError(
            "legacy claims require operation and step IDs")
    packet_costs = tuple(packet_costs)
    if any(not isinstance(
            row, PacketCost)
            for row in packet_costs):
        raise TypeError(
            "legacy claims require PacketCost rows")
    window = TurnWindow(
        turn, turn + 1)
    return tuple(sorted(
        (
            ResourceClaim(
                resource=legacy_packet_resource_ref(
                    row.resource),
                quantity=row.quanta,
                window=window,
                hardness=hardness,
                exclusive=False,
                source_operation_id=(
                    operation_id),
                source_step_id=(
                    step_id))
            for row in packet_costs
        ),
        key=lambda row: row.sort_key))


def capacities_from_packet_budgets(
        packet_budgets, turn, snapshot_id):
    """Adapt v1 packet budgets without mutating the packet scheduler."""
    from .packets import PacketBudget

    if (not isinstance(snapshot_id, str)
            or not snapshot_id):
        raise ValueError(
            "legacy capacities require snapshot ID")
    packet_budgets = tuple(
        packet_budgets)
    if any(not isinstance(
            row, PacketBudget)
            for row in packet_budgets):
        raise TypeError(
            "legacy capacities require PacketBudget rows")
    window = TurnWindow(
        turn, turn + 1)
    return tuple(sorted(
        (
            ResourceCapacity(
                resource=legacy_packet_resource_ref(
                    row.resource),
                quantity=row.available,
                window=window,
                snapshot_id=snapshot_id,
                authority=(
                    "legacy-packet-budget"))
            for row in packet_budgets
        ),
        key=lambda row: row.sort_key))
