"""Crisp atomspace projection with explicit authoritative/visible/belief namespaces."""

from dataclasses import dataclass


QUANTITATIVE_PREDICATES = frozenset({
    "beakers-per-turn", "build-cost", "city-size", "gold-stockpile",
    "research-cost", "shield-stockpile", "shields-per-turn",
})


# Phase-0 FDAS migration inventory.  These constants describe the existing
# compatibility projection; they do not expand it or grant new authority.
LEGACY_AUTHORITATIVE_PREDICATES = frozenset({
    "buildable",
    "city-at",
    "city-producing",
    "has-tech",
    "owns-city",
    "owns-unit",
    "unit-activity",
    "unit-at",
    "unit-type",
})
LEGACY_VISIBLE_PREDICATES = frozenset({
    "tile-visible",
})
LEGACY_PROJECTED_PREDICATES = frozenset(
    LEGACY_AUTHORITATIVE_PREDICATES
    | LEGACY_VISIBLE_PREDICATES)


@dataclass(frozen=True, order=True)
class Atom:
    predicate: str
    args: tuple

    def __post_init__(self):
        if self.predicate in QUANTITATIVE_PREDICATES:
            raise ValueError("quantitative values must be grounded, not stored as atoms")

    def to_dict(self):
        return {"args": list(self.args), "predicate": self.predicate}


@dataclass(frozen=True)
class SnapshotAtomspaces:
    snapshot_id: str
    authoritative: frozenset
    visible: frozenset
    uncertain: frozenset


def build_atomspaces(snapshot):
    own = set()
    player = str(snapshot.player_id)
    for tech in snapshot.research.known_techs:
        own.add(Atom("has-tech", (player, tech)))
    for city in snapshot.cities:
        cid = str(city.city_id)
        own.add(Atom("owns-city", (player, cid)))
        if city.tile is not None:
            own.add(Atom("city-at", (cid, str(city.tile))))
        if city.production_kind is not None and city.production_value is not None:
            own.add(Atom("city-producing", (
                cid, str(city.production_kind), str(city.production_value))))
        if city.buildability_available:
            for kind, target_id, _ in city.buildable:
                own.add(Atom("buildable", (cid, kind, str(target_id))))
    for unit in snapshot.units:
        uid = str(unit.unit_id)
        own.add(Atom("owns-unit", (player, uid)))
        own.add(Atom("unit-type", (uid, unit.unit_type)))
        if unit.tile is not None:
            own.add(Atom("unit-at", (uid, str(unit.tile))))
        if unit.activity:
            own.add(Atom("unit-activity", (uid, unit.activity)))
    visible = frozenset(Atom("tile-visible", (str(tile_id),))
                        for tile_id in snapshot.visible_tile_ids)
    return SnapshotAtomspaces(snapshot.snapshot_id, frozenset(own), visible, frozenset())
