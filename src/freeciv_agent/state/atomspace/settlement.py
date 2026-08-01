"""Exact, fog-safe FDAS settlement-site microspaces."""

import json

from ...events.schema import structural_hash
from ...planning.path_corridors import native_route_corridor
from .delta import snapshot_dependency_ref
from .model import (
    AtomKey,
    AtomNamespace,
    AtomRecord,
    AuthorityClass,
    EntityRef,
    SupportRecord,
)
from .predicates import PredicateSpec, legacy_predicate_registry
from .scopes import ScopeSpec, snapshot_scopes


_CRISP = {"confidence": 1.0, "crisp": True, "strength": 1.0}
_CRISP_HASH = structural_hash(_CRISP)


def _spec(predicate, arguments):
    return PredicateSpec(
        predicate, len(arguments), tuple(tuple(value) for value in arguments),
        frozenset((AtomNamespace.DERIVED,)), "crisp",
        frozenset(("settlement-site",)), "explicit-witness",
        "parent-summary", "1.0")


def settlement_predicate_registry():
    return legacy_predicate_registry().extended((
        _spec("settlement-site-at", (
            ("settlement-site",), ("tile",))),
        _spec("settlement-site-eligible-for", (
            ("settlement-site",), ("unit",))),
        _spec("founder-current-settlement-capability", (("unit",),)),
        _spec("founder-can-settle-now", (
            ("unit",), ("settlement-site",))),
        _spec("founder-legal-site-step", (
            ("unit",), ("settlement-site",), ("action",))),
        _spec("settlement-site-route-corridor", (
            ("settlement-site",), ("route-corridor",))),
        _spec("settlement-site-currently-uncontested", (
            ("settlement-site",),)),
        _spec("settlement-site-contested-by", (
            ("settlement-site",), ("unit",))),
        _spec("settlement-escort-required", (
            ("unit",), ("settlement-site",), ("unit",))),
    ))


class SettlementSiteProjector(object):
    """Project only packet-proven current settlement sites."""

    projector_id = "fdas-settlement-site-projector"
    version = "1.0"

    def __init__(self):
        self.predicate_registry = settlement_predicate_registry()

    @staticmethod
    def extend_fingerprints(fingerprints):
        return dict(fingerprints)

    @staticmethod
    def _sites(snapshot):
        sites = {}
        if snapshot.map_width <= 0:
            return ()
        for action_key in snapshot.legal_action_json:
            action = json.loads(action_key)
            actor_id = action.get("actor_id")
            actor = snapshot.unit(actor_id)
            if actor is None:
                continue
            if (action.get("action_type") == "unit_build_city"
                    and actor.tile is not None):
                tile = int(actor.tile)
                kind = "settle-now"
            elif (action.get("action_type") == "unit_move"
                    and action.get("settlement_site_eligible") is True
                    and isinstance(action.get("target"), dict)
                    and None not in (
                        action["target"].get("x"),
                        action["target"].get("y"))):
                tile = (
                    int(action["target"]["x"])
                    + int(action["target"]["y"]) * snapshot.map_width)
                kind = "eligible-move"
            else:
                continue
            sites.setdefault(tile, []).append((
                str(actor_id), kind, action, action_key))
        return tuple(
            (tile, tuple(sorted(rows, key=lambda value: (value[0], value[3]))))
            for tile, rows in sorted(sites.items()))

    def scopes(self, snapshot):
        world, empire = snapshot_scopes(snapshot)
        scopes = [world, empire]
        prefix = empire.scope_id.rsplit(":empire", 1)[0]
        predicates = tuple(sorted(
            value for value in self.predicate_registry.predicates
            if (value.startswith("settlement-")
                or value.startswith("founder-"))))
        for tile, _rows in self._sites(snapshot):
            site = EntityRef("settlement-site", "tile:{}".format(tile))
            scopes.append(ScopeSpec(
                "{}:settlement-site:{}".format(prefix, tile),
                "settlement-site", snapshot.player_id, (site,),
                (empire.scope_id,),
                ("owns-unit", "tile-visible", "visible-enemy-at"),
                predicates, frozenset((AtomNamespace.DERIVED,)),
                100, 50, 50, 2, "snapshot-revision", empire.validity))
        return tuple(scopes)

    def _record(self, scope, predicate, arguments, dependencies, witness,
                provenance=()):
        key = AtomKey(
            AtomNamespace.DERIVED, predicate, tuple(arguments), scope.scope_id)
        support = SupportRecord.create(
            self.projector_id, self.version, key.to_dict(), dependencies,
            witness, (self.projector_id,) + tuple(provenance))
        return AtomRecord.create(
            key, AuthorityClass.DETERMINISTIC_DERIVED, _CRISP,
            scope.validity, (support,),
            (self.projector_id,) + tuple(provenance),
            tags=(("domain", "settlement-site"),), truth_hash=_CRISP_HASH)

    def project(self, snapshot, scopes, fingerprints):
        scope_by_tile = dict(
            (int(value.root_entities[0].entity_id.split(":", 1)[1]), value)
            for value in scopes if value.scope_kind == "settlement-site")
        visible = set(snapshot.visible_tile_ids)
        records = []
        for tile, rows in self._sites(snapshot):
            scope = scope_by_tile[tile]
            site = scope.root_entities[0]
            action_dependencies = []
            records.append(self._record(
                scope, "settlement-site-at",
                (site, EntityRef("tile", str(tile))),
                tuple(snapshot_dependency_ref(
                    snapshot,
                    "legal_actions.{}".format(structural_hash(value[3])),
                    fingerprints) for value in rows),
                {"tile": tile, "witness": "current-legal-settlement-route"}))
            for actor_id, kind, action, action_key in rows:
                legal_dependency = snapshot_dependency_ref(
                    snapshot,
                    "legal_actions.{}".format(structural_hash(action_key)),
                    fingerprints)
                actor_dependency = snapshot_dependency_ref(
                    snapshot, "units.{}.__exists__".format(actor_id),
                    fingerprints)
                dependencies = (actor_dependency, legal_dependency)
                action_dependencies.append(legal_dependency)
                actor = EntityRef("unit", actor_id)
                witness = {
                    "action": action,
                    "action_key": action_key,
                    "evidence_kind": kind,
                    "tile": tile,
                }
                records.append(self._record(
                    scope, "founder-current-settlement-capability",
                    (actor,), dependencies, witness,
                    ("server-advertised-settlement-action",)))
                records.append(self._record(
                    scope, "settlement-site-eligible-for",
                    (site, actor), dependencies, witness,
                    ("server-advertised-settlement-action",)))
                action_ref = EntityRef(
                    "action", "legal-" + structural_hash(action_key)[:24])
                if kind == "settle-now":
                    records.append(self._record(
                        scope, "founder-can-settle-now", (actor, site),
                        dependencies, witness,
                        ("server-advertised-settlement-action",)))
                else:
                    records.append(self._record(
                        scope, "founder-legal-site-step",
                        (actor, site, action_ref), dependencies, witness,
                        ("packet-ruleset-found-city-preconditions",)))
                route = snapshot.movement_route(actor_id, tile)
                if route is not None and route.reachable:
                    corridor = native_route_corridor(snapshot, actor_id, tile)
                    route_dependency = snapshot_dependency_ref(
                        snapshot,
                        "movement_routes.{}:{}.__exists__".format(
                            actor_id, tile), fingerprints)
                    records.append(self._record(
                        scope, "settlement-site-route-corridor",
                        (site, EntityRef(
                            "route-corridor", corridor.corridor_digest)),
                        dependencies + (route_dependency,),
                        corridor.to_dict(),
                        ("freeciv-server-pathfinder",)))

            enemies = tuple(sorted(
                (value for value in snapshot.visible_enemy_units
                 if value.tile == tile), key=lambda value: value.unit_id))
            if enemies:
                for enemy in enemies:
                    enemy_dependencies = (
                        snapshot_dependency_ref(
                            snapshot,
                            "visible_enemy_units.{}.__exists__".format(
                                enemy.unit_id), fingerprints),
                        snapshot_dependency_ref(
                            snapshot,
                            "visible_enemy_units.{}.tile".format(
                                enemy.unit_id), fingerprints),
                    )
                    enemy_ref = EntityRef("unit", str(enemy.unit_id))
                    records.append(self._record(
                        scope, "settlement-site-contested-by",
                        (site, enemy_ref), enemy_dependencies,
                        enemy.grounded_dict(), ("packet-visible-enemy",)))
                    for actor_id, _kind, _action, _action_key in rows:
                        records.append(self._record(
                            scope, "settlement-escort-required",
                            (EntityRef("unit", actor_id), site, enemy_ref),
                            tuple(action_dependencies) + enemy_dependencies,
                            {
                                "enemy_unit_id": enemy.unit_id,
                                "site_tile": tile,
                                "requirement":
                                    "visible-enemy-occupies-settlement-site",
                            }, ("packet-visible-enemy",)))
            elif tile in visible:
                records.append(self._record(
                    scope, "settlement-site-currently-uncontested",
                    (site,),
                    (
                        snapshot_dependency_ref(
                            snapshot, "visible_tile_ids.{}".format(tile),
                            fingerprints),
                        snapshot_dependency_ref(
                            snapshot, "visible_enemy_units.__members__",
                            fingerprints),
                    ),
                    {
                        "completeness": "current-packet-visible-enemy-set",
                        "future_safety": "unknown",
                        "site_tile": tile,
                    }, ("explicit-current-visibility-completeness",)))
        return tuple(sorted(records, key=lambda value: value.atom_id))
