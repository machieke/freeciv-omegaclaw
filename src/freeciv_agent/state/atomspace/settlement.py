"""Exact, fog-safe FDAS settlement-site microspaces."""

import json
from dataclasses import dataclass

from ...events.schema import structural_hash
from ...planning.path_corridors import native_route_corridor
from .delta import snapshot_dependency_ref
from .grounding import persistent_defender_type
from .model import (
    AtomKey,
    AtomNamespace,
    AtomRecord,
    AuthorityClass,
    DependencyKey,
    DependencyRef,
    EntityRef,
    SupportRecord,
)
from .predicates import PredicateSpec, legacy_predicate_registry
from .scopes import ScopeSpec, snapshot_scopes


_CRISP = {"confidence": 1.0, "crisp": True, "strength": 1.0}
_CRISP_HASH = structural_hash(_CRISP)


@dataclass(frozen=True)
class SettlementEscortPolicy:
    visible_threat_radius: int = 2
    catch_budget_turns: int = 1
    schema_version: str = "1.0"

    def __post_init__(self):
        for value, name in (
                (self.visible_threat_radius, "visible threat radius"),
                (self.catch_budget_turns, "escort catch budget")):
            if (isinstance(value, bool) or not isinstance(value, int)
                    or not 0 <= value <= 20):
                raise ValueError("{} must be in 0..20".format(name))

    def dependency_refs(self):
        owner = "fdas-settlement-escort-policy:{}".format(
            self.schema_version)
        return tuple(DependencyRef(
            DependencyKey("policy", owner, name), structural_hash(value))
            for name, value in (
                ("catch_budget_turns", self.catch_budget_turns),
                ("visible_threat_radius", self.visible_threat_radius),
            ))


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
        _spec("settlement-visible-threat-near", (
            ("settlement-site",), ("unit",))),
        _spec("escort-can-catch-founder", (
            ("unit",), ("unit",), ("settlement-site",))),
        _spec("settlement-actionable-escort", (
            ("unit",), ("settlement-site",), ("unit",))),
        _spec("settlement-site-blocked-by-threat", (
            ("settlement-site",), ("unit",))),
    ))


class SettlementSiteProjector(object):
    """Project only packet-proven current settlement sites."""

    projector_id = "fdas-settlement-site-projector"
    version = "1.0"

    def __init__(self, ruleset_ir=None, ruleset_digest=None, policy=None):
        if ruleset_ir is not None and not ruleset_digest:
            raise ValueError(
                "settlement ruleset projection requires ruleset digest")
        self.ruleset_ir = ruleset_ir
        self.ruleset_digest = ruleset_digest
        self.policy = policy or SettlementEscortPolicy()
        self.predicate_registry = settlement_predicate_registry()

    def extend_fingerprints(self, fingerprints):
        result = dict(fingerprints)
        for dependency in self.policy.dependency_refs():
            result[dependency.key] = dependency.fingerprint
        if self.ruleset_digest:
            for rule in getattr(self.ruleset_ir, "rules", ()):
                if getattr(rule, "target_kind", None) != "unit":
                    continue
                for unit_type in {
                        getattr(rule, "rule_name", None),
                        getattr(rule, "display_name", None)}:
                    if not unit_type:
                        continue
                    dependency = self._ruleset_dependency(unit_type)
                    result[dependency.key] = dependency.fingerprint
        return result

    def _ruleset_dependency(self, unit_type):
        key = DependencyKey(
            "ruleset-digest", self.ruleset_digest,
            "target:unit:{}".format(unit_type))
        return DependencyRef(key, structural_hash({
            "ruleset_digest": self.ruleset_digest,
            "target": unit_type,
            "target_kind": "unit",
        }))

    @staticmethod
    def _sites(snapshot):
        sites = {}
        if snapshot.map_width <= 0:
            return ()
        for action_key in snapshot.legal_action_json:
            action = json.loads(action_key)
            actor_id = action.get("actor_id")
            if isinstance(actor_id, bool) or not isinstance(actor_id, int):
                continue
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

    @staticmethod
    def _distance_to_tile(snapshot, tile, enemy):
        if enemy.tile == tile:
            return 0
        if (snapshot.map_width <= 0 or snapshot.map_height <= 0
                or snapshot.map_wrap_x is None
                or snapshot.map_wrap_y is None
                or enemy.x is None or enemy.y is None):
            return None
        x = tile % snapshot.map_width
        y = tile // snapshot.map_width
        dx = abs(x - int(enemy.x))
        dy = abs(y - int(enemy.y))
        if snapshot.map_wrap_x:
            dx = min(dx, snapshot.map_width - dx)
        if snapshot.map_wrap_y:
            dy = min(dy, snapshot.map_height - dy)
        return max(dx, dy)

    @staticmethod
    def _legal_route_step(snapshot, actor_id, destination_tile, fingerprints):
        actor = snapshot.unit(actor_id)
        route = snapshot.movement_route(actor_id, destination_tile)
        if (actor is None or actor.tile is None or route is None
                or not route.reachable
                or route.authority != "freeciv-server-pathfinder"
                or route.schema_version != "1.0"
                or route.origin_tile != actor.tile
                or route.turn != snapshot.turn
                or route.source_seq > snapshot.identity.source_seq
                or snapshot.map_width <= 0):
            return None
        x = route.first_step_tile % snapshot.map_width
        y = route.first_step_tile // snapshot.map_width
        matches = []
        for action_key in snapshot.legal_action_json:
            action = json.loads(action_key)
            target = action.get("target")
            if (action.get("action_type") == "unit_move"
                    and int(action.get("actor_id", -1)) == int(actor_id)
                    and isinstance(target, dict)
                    and target.get("x") == x and target.get("y") == y):
                matches.append((action, action_key))
        if len(matches) != 1:
            return None
        prefix = "movement_routes.{}:{}".format(actor_id, destination_tile)
        paths = (
            "units.{}.__exists__".format(actor_id),
            "units.{}.tile".format(actor_id),
            prefix + ".__exists__",
            prefix + ".authority",
            prefix + ".estimated_turns",
            prefix + ".first_step_tile",
            prefix + ".origin_tile",
            prefix + ".reachable",
            prefix + ".schema_version",
            prefix + ".source_seq",
            prefix + ".turn",
            "legal_actions.{}".format(structural_hash(matches[0][1])),
        )
        dependencies = tuple(snapshot_dependency_ref(
            snapshot, value, fingerprints) for value in paths)
        return route, matches[0][0], matches[0][1], dependencies

    def _escort_rows(self, snapshot, founder_id, site, fingerprints):
        founder = snapshot.unit(founder_id)
        if founder is None or founder.tile is None:
            return ()
        defenders = tuple(
            value for value in snapshot.units
            if (value.unit_id != int(founder_id)
                and persistent_defender_type(
                    self.ruleset_ir, value.unit_type)))
        results = []
        policy_dependencies = self.policy.dependency_refs()
        population_dependencies = [
            snapshot_dependency_ref(
                snapshot, "cities.__members__", fingerprints),
            snapshot_dependency_ref(
                snapshot, "units.__members__", fingerprints),
            snapshot_dependency_ref(
                snapshot, "units.{}.__exists__".format(founder_id),
                fingerprints),
            snapshot_dependency_ref(
                snapshot, "units.{}.tile".format(founder_id), fingerprints),
        ]
        for city in snapshot.cities:
            population_dependencies.append(snapshot_dependency_ref(
                snapshot, "cities.{}.tile".format(city.city_id),
                fingerprints))
        for unit in snapshot.units:
            population_dependencies.extend((
                snapshot_dependency_ref(
                    snapshot, "units.{}.tile".format(unit.unit_id),
                    fingerprints),
                snapshot_dependency_ref(
                    snapshot, "units.{}.type".format(unit.unit_id),
                    fingerprints),
            ))
            if self.ruleset_digest:
                population_dependencies.append(
                    self._ruleset_dependency(unit.unit_type))
        population_dependencies = tuple(sorted(set(population_dependencies)))
        for escort in sorted(defenders, key=lambda value: value.unit_id):
            source_city = next((
                value for value in snapshot.cities
                if value.tile == escort.tile), None)
            source_defenders = tuple(
                value for value in defenders
                if value.tile == escort.tile)
            # Moving the only durable defender out of an owned city is not an
            # actionable escort route.
            if source_city is not None and len(source_defenders) <= 1:
                continue
            unit_dependencies = (
                snapshot_dependency_ref(
                    snapshot, "units.{}.__exists__".format(escort.unit_id),
                    fingerprints),
                snapshot_dependency_ref(
                    snapshot, "units.{}.tile".format(escort.unit_id),
                    fingerprints),
                snapshot_dependency_ref(
                    snapshot, "units.{}.type".format(escort.unit_id),
                    fingerprints),
            )
            if self.ruleset_digest:
                unit_dependencies += (
                    self._ruleset_dependency(escort.unit_type),)
            if escort.tile == founder.tile:
                eta = 0
                action = None
                action_key = None
                dependencies = unit_dependencies + (
                    snapshot_dependency_ref(
                        snapshot, "units.{}.tile".format(founder_id),
                        fingerprints),) + policy_dependencies
            else:
                routed = self._legal_route_step(
                    snapshot, escort.unit_id, founder.tile, fingerprints)
                if routed is None:
                    continue
                route, action, action_key, route_dependencies = routed
                eta = int(route.estimated_turns)
                dependencies = (
                    unit_dependencies + route_dependencies
                    + policy_dependencies)
            if eta > self.policy.catch_budget_turns:
                continue
            results.append((escort, eta, action, action_key,
                            tuple(sorted(set(
                                dependencies + population_dependencies)))))
        return tuple(results)

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

            occupying_enemies = tuple(sorted(
                (value for value in snapshot.visible_enemy_units
                 if value.tile == tile), key=lambda value: value.unit_id))
            threat_rows = []
            for enemy in sorted(
                    snapshot.visible_enemy_units,
                    key=lambda value: value.unit_id):
                distance = self._distance_to_tile(snapshot, tile, enemy)
                if (distance is None
                        or distance > self.policy.visible_threat_radius):
                    continue
                enemy_dependencies = (
                    snapshot_dependency_ref(
                        snapshot,
                        "visible_enemy_units.{}.__exists__".format(
                            enemy.unit_id), fingerprints),
                    snapshot_dependency_ref(
                        snapshot,
                        "visible_enemy_units.{}.x".format(enemy.unit_id),
                        fingerprints),
                    snapshot_dependency_ref(
                        snapshot,
                        "visible_enemy_units.{}.y".format(enemy.unit_id),
                        fingerprints),
                    snapshot_dependency_ref(
                        snapshot,
                        "visible_enemy_units.{}.tile".format(enemy.unit_id),
                        fingerprints),
                ) + tuple(snapshot_dependency_ref(
                    snapshot, value, fingerprints) for value in (
                        "map_width", "map_height",
                        "map_wrap_x", "map_wrap_y"))
                enemy_dependencies += self.policy.dependency_refs()
                threat_rows.append((enemy, distance, enemy_dependencies))
                records.append(self._record(
                    scope, "settlement-visible-threat-near",
                    (site, EntityRef("unit", str(enemy.unit_id))),
                    tuple(action_dependencies) + enemy_dependencies,
                    {
                        "distance": distance,
                        "site_tile": tile,
                        "visible_threat_radius":
                            self.policy.visible_threat_radius,
                    }, ("packet-visible-enemy", "exact-map-topology")))

            if occupying_enemies:
                for enemy in occupying_enemies:
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
            if not occupying_enemies and tile in visible:
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

            for actor_id, _kind, _action, _action_key in rows:
                escorts = self._escort_rows(
                    snapshot, actor_id, site, fingerprints)
                actor_ref = EntityRef("unit", actor_id)
                for escort, eta, escort_action, escort_action_key, deps in escorts:
                    escort_ref = EntityRef("unit", str(escort.unit_id))
                    witness = {
                        "action": escort_action,
                        "action_key": escort_action_key,
                        "catch_budget_turns": self.policy.catch_budget_turns,
                        "estimated_turns": eta,
                        "founder_unit_id": int(actor_id),
                        "site_tile": tile,
                    }
                    records.append(self._record(
                        scope, "escort-can-catch-founder",
                        (escort_ref, actor_ref, site), deps, witness,
                        ("freeciv-server-pathfinder",)))
                for enemy, distance, enemy_dependencies in threat_rows:
                    enemy_ref = EntityRef("unit", str(enemy.unit_id))
                    requirement_dependencies = (
                        tuple(action_dependencies) + enemy_dependencies)
                    records.append(self._record(
                        scope, "settlement-escort-required",
                        (actor_ref, site, enemy_ref),
                        requirement_dependencies,
                        {
                            "distance": distance,
                            "enemy_unit_id": enemy.unit_id,
                            "requirement": "visible-threat-within-policy",
                            "site_tile": tile,
                        }, ("packet-visible-enemy", "escort-policy")))
                    if escorts:
                        for escort, eta, escort_action, escort_action_key, deps in escorts:
                            records.append(self._record(
                                scope, "settlement-actionable-escort",
                                (actor_ref, site, EntityRef(
                                    "unit", str(escort.unit_id))),
                                requirement_dependencies + deps,
                                {
                                    "action": escort_action,
                                    "action_key": escort_action_key,
                                    "enemy_unit_id": enemy.unit_id,
                                    "estimated_turns": eta,
                                    "site_tile": tile,
                                }, ("freeciv-server-pathfinder",
                                    "packet-visible-enemy")))
                    else:
                        records.append(self._record(
                            scope, "settlement-site-blocked-by-threat",
                            (site, enemy_ref), requirement_dependencies,
                            {
                                "blocker": "no-actionable-escort-route",
                                "distance": distance,
                                "enemy_unit_id": enemy.unit_id,
                                "site_tile": tile,
                            }, ("packet-visible-enemy", "escort-policy")))
        return tuple(sorted(records, key=lambda value: value.atom_id))
