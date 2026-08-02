"""Deterministic extraction of authoritative current-turn game capacities."""

import math
import re
from dataclasses import dataclass
from functools import cached_property

from ..events.schema import structural_hash
from .resource_claims import (
    GameResourceKind,
    ResourceCapacity,
    ResourceRef,
    TurnWindow,
)


def _normalized(value):
    return re.sub(
        r"[^a-z0-9]+", "",
        str(value or "").lower())


def _transport_capacity(ruleset_ir, unit_type):
    target = _normalized(
        unit_type)
    matches = []
    for rule in getattr(
            ruleset_ir, "rules", ()):
        if getattr(
                rule, "target_kind", None) != "unit":
            continue
        labels = {
            _normalized(getattr(
                rule, "display_name", "")),
            _normalized(getattr(
                rule, "rule_name", "")),
        }
        if target not in labels:
            continue
        quantitative = getattr(
            rule, "quantitative", {})
        # ``transport_cap`` is the canonical compiler projection of the
        # Freeciv ruleset field.  Retain the longer legacy spelling only for
        # compatibility with pre-compiler synthetic fixtures.
        value = quantitative.get(
            "transport_cap")
        if value is None:
            value = quantitative.get(
                "transport_capacity")
        if isinstance(value, dict):
            value = value.get("value")
        if (isinstance(value, bool)
                or not isinstance(
                    value, (int, float))
                or not math.isfinite(
                    float(value))
                or int(value) != value
                or int(value) < 0):
            return None
        matches.append(
            int(value))
    if len(matches) != 1:
        return None
    return matches[0]


@dataclass(frozen=True)
class ResourceCapacitySnapshot:
    snapshot_id: str
    turn: int
    capacities: tuple
    omissions: tuple
    extractor_identity: str

    def __post_init__(self):
        if not isinstance(
                self.snapshot_id, str
                ) or not self.snapshot_id:
            raise ValueError(
                "capacity snapshot requires snapshot ID")
        if (isinstance(self.turn, bool)
                or not isinstance(self.turn, int)
                or self.turn < 0):
            raise ValueError(
                "capacity snapshot turn must be non-negative")
        if any(not isinstance(
                row, ResourceCapacity)
               for row in self.capacities):
            raise TypeError(
                "capacity snapshot rows must be ResourceCapacity")
        if tuple(sorted(
                self.capacities,
                key=lambda row: row.sort_key)
                ) != self.capacities:
            raise ValueError(
                "capacity snapshot rows must be stably sorted")
        capacity_ids = [
            row.capacity_id
            for row in self.capacities]
        if len(capacity_ids) != len(
                set(capacity_ids)):
            raise ValueError(
                "capacity snapshot rows must be unique")
        if (tuple(sorted(set(
                self.omissions)))
                != self.omissions
                or any(
                    not isinstance(value, str)
                    or not value
                    for value in self.omissions)):
            raise ValueError(
                "capacity omissions must be unique sorted strings")
        if (not isinstance(
                self.extractor_identity, str)
                or not self.extractor_identity):
            raise ValueError(
                "capacity extractor identity is required")

    @cached_property
    def capacity_digest(self):
        return structural_hash({
            "capacities": [
                row.to_dict()
                for row in self.capacities],
            "extractor_identity":
                self.extractor_identity,
            "omissions": list(
                self.omissions),
            "snapshot_id": self.snapshot_id,
            "turn": self.turn,
        })

    def to_dict(self):
        return {
            "capacities": [
                row.to_dict()
                for row in self.capacities],
            "capacity_digest":
                self.capacity_digest,
            "extractor_identity":
                self.extractor_identity,
            "omissions": list(
                self.omissions),
            "snapshot_id": self.snapshot_id,
            "turn": self.turn,
        }


class ResourceCapacityExtractor:
    """Expose only capacities justified by the current immutable snapshot."""

    EXTRACTOR_IDENTITY = (
        "freeciv-resource-capacity-extractor/1.0")

    def extract(
            self, snapshot, ruleset_ir=None,
            action_budget=None, cpu_budget=None):
        snapshot_id = str(getattr(
            snapshot, "snapshot_id", ""))
        turn = getattr(
            snapshot, "turn", None)
        player_id = getattr(
            snapshot, "player_id", None)
        if not snapshot_id:
            raise ValueError(
                "capacity extraction requires snapshot identity")
        if (isinstance(turn, bool)
                or not isinstance(turn, int)
                or turn < 0):
            raise ValueError(
                "capacity extraction requires a valid turn")
        if (isinstance(player_id, bool)
                or not isinstance(player_id, int)
                or player_id < 0):
            raise ValueError(
                "capacity extraction requires a player ID")
        for value, name in (
                (action_budget, "action budget"),
                (cpu_budget, "CPU budget")):
            if (value is not None
                    and (isinstance(value, bool)
                         or not isinstance(value, int)
                         or value < 0)):
                raise ValueError(
                    "{} must be a non-negative integer or absent".format(
                        name))
        scope = "player:{}".format(
            player_id)
        window = TurnWindow(
            turn, turn + 1)
        capacities = []
        omissions = {
            "tile-occupancy-rules-unavailable",
            "diplomatic-capacity-unavailable",
        }

        def add(kind, owner_id, subresource, quantity, authority):
            capacities.append(
                ResourceCapacity(
                    resource=ResourceRef(
                        kind=kind,
                        owner_id=owner_id,
                        subresource=subresource,
                        scope=scope),
                    quantity=int(quantity),
                    window=window,
                    snapshot_id=snapshot_id,
                    authority=authority))

        for unit in sorted(
                getattr(snapshot, "units", ()),
                key=lambda row: row.unit_id):
            unit_id = "unit:{}".format(
                unit.unit_id)
            add(
                GameResourceKind.ACTOR,
                unit_id, "whole_actor", 1,
                "authoritative-own-unit")
            if unit.moves_left is None:
                omissions.add(
                    "move-points-missing:{}".format(
                        unit_id))
            elif unit.moves_left < 0:
                omissions.add(
                    "move-points-invalid:{}".format(
                        unit_id))
            else:
                add(
                    GameResourceKind.MOVE_POINTS,
                    unit_id, "current_turn",
                    unit.moves_left,
                    "authoritative-unit-state")
            transport_capacity = (
                None
                if ruleset_ir is None else
                _transport_capacity(
                    ruleset_ir,
                    unit.unit_type))
            if transport_capacity is None:
                if unit.cargo_count is not None:
                    omissions.add(
                        "transport-rules-missing:{}".format(
                            unit_id))
            elif transport_capacity > 0:
                if (unit.cargo_count is None
                        or unit.cargo_count < 0):
                    omissions.add(
                        "transport-load-missing:{}".format(
                            unit_id))
                else:
                    add(
                        GameResourceKind.TRANSPORT_SEAT,
                        unit_id, "cargo",
                        max(
                            0,
                            transport_capacity
                            - unit.cargo_count),
                        "derived-ruleset-and-transport-relations")

        for city in sorted(
                getattr(snapshot, "cities", ()),
                key=lambda row: row.city_id):
            add(
                GameResourceKind.CITY_PRODUCTION_SLOT,
                "city:{}".format(
                    city.city_id),
                "production", 1,
                "authoritative-own-city")
            if getattr(
                    city,
                    "governor_available",
                    False) is True:
                add(
                    GameResourceKind.CITY_WORKER_ASSIGNMENT,
                    "city:{}".format(city.city_id),
                    "citizen_manager", 1,
                    "authoritative-city-governor-capability")

        economy = getattr(
            snapshot, "economy", None)
        gold = getattr(
            economy, "gold", None)
        if gold is None or gold < 0:
            omissions.add(
                "treasury-stockpile-unavailable")
        else:
            add(
                GameResourceKind.TREASURY,
                scope, "gold", gold,
                "authoritative-economy")

        research = getattr(
            snapshot, "research", None)
        if getattr(
                research, "available", False):
            add(
                GameResourceKind.RESEARCH_SLOT,
                scope, "current_target", 1,
                "authoritative-research-state")
        else:
            omissions.add(
                "research-slot-unavailable")

        if action_budget is not None:
            add(
                GameResourceKind.ACTION_BUDGET,
                scope, "controller", action_budget,
                "declared-controller-budget")
        if cpu_budget is not None:
            add(
                GameResourceKind.CPU,
                scope, "controller", cpu_budget,
                "declared-controller-budget")

        return ResourceCapacitySnapshot(
            snapshot_id=snapshot_id,
            turn=turn,
            capacities=tuple(sorted(
                capacities,
                key=lambda row: row.sort_key)),
            omissions=tuple(sorted(
                omissions)),
            extractor_identity=(
                self.EXTRACTOR_IDENTITY))
