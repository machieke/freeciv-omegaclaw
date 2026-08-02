"""Bounded, exact-topology city regions for FDAS defense reasoning."""

from dataclasses import dataclass

from ...events.schema import structural_hash
from .delta import snapshot_dependency_ref
from .model import (
    AtomKey,
    AtomNamespace,
    AtomRecord,
    AuthorityClass,
    DependencyKey,
    DependencyRef,
    EntityRef,
    SupportRecord,
    SymbolRef,
)
from .predicates import PredicateSpec
from .scopes import ScopeSpec
from .unit import unit_defense_predicate_registry, unit_defense_scopes


_CRISP = {"confidence": 1.0, "crisp": True, "strength": 1.0}
_CRISP_HASH = structural_hash(_CRISP)


@dataclass(frozen=True)
class CityRegionPolicy:
    radius: int = 3
    maximum_active_regions: int = 8
    maximum_atoms_per_region: int = 3000
    schema_version: str = "1.0"

    def __post_init__(self):
        for value, name, minimum, maximum in (
                (self.radius, "region radius", 1, 8),
                (self.maximum_active_regions, "active region limit", 1, 64),
                (self.maximum_atoms_per_region, "region atom limit", 100, 10000)):
            if (isinstance(value, bool) or not isinstance(value, int)
                    or not minimum <= value <= maximum):
                raise ValueError(
                    "{} must be in {}..{}".format(name, minimum, maximum))

    @property
    def policy_id(self):
        return "city-region:r{}:max{}:v{}".format(
            self.radius, self.maximum_active_regions, self.schema_version)

    def dependency_refs(self):
        owner = "fdas-city-region-policy:{}".format(self.schema_version)
        values = {
            "maximum_active_regions": self.maximum_active_regions,
            "maximum_atoms_per_region": self.maximum_atoms_per_region,
            "radius": self.radius,
        }
        return tuple(DependencyRef(
            DependencyKey("policy", owner, key), structural_hash(value))
            for key, value in sorted(values.items()))


def _spec(predicate, arguments, namespace, truth="crisp"):
    return PredicateSpec(
        predicate,
        len(arguments),
        tuple(tuple(value) for value in arguments),
        frozenset((namespace,)),
        truth,
        frozenset(("region",)),
        "explicit-witness",
        "parent-summary",
        "1.0",
    )


def region_predicate_registry():
    derived = AtomNamespace.DERIVED
    return unit_defense_predicate_registry().extended((
        _spec("region-centered-on", (("region",), ("city",)), derived),
        _spec("tile-in-region", (("tile",), ("region",)), derived),
        _spec("tile-adjacent", (("tile",), ("tile",)), derived),
        _spec("terrain-kind", (("tile",), ("terrain",)),
              AtomNamespace.AUTHORITATIVE),
        _spec("visible-threat-near", (
            ("unit",), ("city",), ("radius-policy",)), derived),
        _spec("region-activation-reason", (
            ("region",), ("activation-reason",)),
            AtomNamespace.DIAGNOSTIC, truth="structural"),
    ))


class CityRegionProjector(object):
    """Materialize at most a policy-bounded set of focused city regions."""

    projector_id = "fdas-city-region-shadow"
    version = "1.0"
    incremental_dependency_roots = frozenset((
        "cities", "map_height", "map_tiles", "map_width", "map_wrap_x",
        "map_wrap_y", "player_id", "visible_enemy_units",
    ))
    incremental_dependency_kinds = frozenset(("policy",))

    def __init__(self, policy=None):
        self.policy = policy or CityRegionPolicy()
        self.predicate_registry = region_predicate_registry()

    @staticmethod
    def _distance(city, enemy, snapshot):
        if (None in (city.x, city.y, enemy.x, enemy.y,
                     snapshot.map_wrap_x, snapshot.map_wrap_y)
                or snapshot.map_width <= 0 or snapshot.map_height <= 0):
            return None
        dx = abs(int(city.x) - int(enemy.x))
        dy = abs(int(city.y) - int(enemy.y))
        if snapshot.map_wrap_x:
            dx = min(dx, snapshot.map_width - dx)
        if snapshot.map_wrap_y:
            dy = min(dy, snapshot.map_height - dy)
        return max(dx, dy)

    def _activations(self, snapshot):
        if (snapshot.map_wrap_x is None or snapshot.map_wrap_y is None
                or snapshot.map_width <= 0 or snapshot.map_height <= 0):
            return ()
        rows = []
        for city in sorted(snapshot.cities, key=lambda value: value.city_id):
            if None in (city.tile, city.x, city.y):
                continue
            threats = []
            for enemy in snapshot.visible_enemy_units:
                distance = self._distance(city, enemy, snapshot)
                if distance is not None and distance <= self.policy.radius:
                    threats.append(enemy)
            threats = tuple(threats)
            reasons = []
            if threats:
                reasons.append("visible-threat")
            if reasons:
                rows.append((city, tuple(reasons), threats))
        rows.sort(key=lambda value: (
            0 if "visible-threat" in value[1] else 1,
            value[0].city_id))
        return tuple(rows[:self.policy.maximum_active_regions])

    def scopes(self, snapshot):
        scopes = list(unit_defense_scopes(snapshot))
        empire = next(value for value in scopes if value.scope_kind == "empire")
        predicates = region_predicate_registry().predicates
        for city, _reasons, _threats in self._activations(snapshot):
            region_id = "city-{}:r{}:v{}".format(
                city.city_id, self.policy.radius, self.policy.schema_version)
            city_scope_id = "{}:city:{}:facts".format(
                empire.scope_id.rsplit(":empire", 1)[0], city.city_id)
            scopes.append(ScopeSpec(
                "{}:region:{}".format(
                    empire.scope_id.rsplit(":empire", 1)[0], region_id),
                "region",
                snapshot.player_id,
                (EntityRef("region", region_id),),
                (empire.scope_id, city_scope_id),
                ("city-at", "tile-visible", "visible-enemy-at"),
                tuple(sorted(value for value in predicates
                             if value in (
                                 "region-centered-on", "tile-in-region",
                                 "visible-threat-near"))),
                frozenset((
                    AtomNamespace.AUTHORITATIVE,
                    AtomNamespace.DERIVED,
                    AtomNamespace.DIAGNOSTIC,
                )),
                self.policy.maximum_atoms_per_region,
                500,
                250,
                2,
                "focused-snapshot-revision",
                empire.validity,
            ))
        return tuple(scopes)

    def extend_fingerprints(self, fingerprints):
        result = dict(fingerprints)
        for dependency in self.policy.dependency_refs():
            result[dependency.key] = dependency.fingerprint
        return result

    @staticmethod
    def _record(scope, namespace, predicate, arguments, authority,
                dependencies, witness, truth=None, support=None):
        truth = truth or _CRISP
        key = AtomKey(namespace, predicate, tuple(arguments), scope.scope_id)
        support = support or SupportRecord.create(
            "fdas-city-region-shadow", "1.0", key.to_dict(),
            tuple(sorted(set(dependencies))), witness,
            ("fdas-city-region-shadow",))
        return AtomRecord.create(
            key, authority, truth, scope.validity, (support,),
            ("fdas-city-region-shadow",),
            tags=(("domain", "city-region-shadow"),),
            truth_hash=structural_hash(truth))

    @staticmethod
    def _region_tiles(city, snapshot, radius):
        tiles = set()
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                x = int(city.x) + dx
                y = int(city.y) + dy
                if snapshot.map_wrap_x:
                    x %= snapshot.map_width
                elif not 0 <= x < snapshot.map_width:
                    continue
                if snapshot.map_wrap_y:
                    y %= snapshot.map_height
                elif not 0 <= y < snapshot.map_height:
                    continue
                tiles.add(y * snapshot.map_width + x)
        return tuple(sorted(tiles))

    @staticmethod
    def _adjacent(tile, snapshot):
        x = tile % snapshot.map_width
        y = tile // snapshot.map_width
        values = set()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if snapshot.map_wrap_x:
                    nx %= snapshot.map_width
                elif not 0 <= nx < snapshot.map_width:
                    continue
                if snapshot.map_wrap_y:
                    ny %= snapshot.map_height
                elif not 0 <= ny < snapshot.map_height:
                    continue
                values.add(ny * snapshot.map_width + nx)
        return tuple(sorted(values))

    def project(self, snapshot, scopes, fingerprints):
        scope_by_city = {}
        for scope in scopes:
            if scope.scope_kind != "region":
                continue
            region_id = scope.root_entities[0].entity_id
            city_id = region_id.split(":", 1)[0].split("-", 1)[1]
            scope_by_city[city_id] = scope
        policy_refs = self.policy.dependency_refs()
        policy_ref = SymbolRef("radius-policy", self.policy.policy_id)
        terrain_by_tile = dict(
            (int(value["index"]), value)
            for value in snapshot.map_tiles
            if isinstance(value, dict) and value.get("index") is not None)
        records = []
        for city, reasons, threats in self._activations(snapshot):
            city_id = str(city.city_id)
            scope = scope_by_city[city_id]
            region_ref = scope.root_entities[0]
            city_ref = EntityRef("city", city_id)
            base_paths = (
                "cities.{}.tile".format(city_id),
                "cities.{}.x".format(city_id),
                "cities.{}.y".format(city_id),
                "map_width", "map_height", "map_wrap_x", "map_wrap_y",
            )
            base_dependencies = tuple(
                snapshot_dependency_ref(snapshot, path, fingerprints)
                for path in base_paths) + policy_refs
            activation_dependencies = list(base_dependencies)
            for enemy in threats:
                for field in ("x", "y"):
                    activation_dependencies.append(snapshot_dependency_ref(
                        snapshot,
                        "visible_enemy_units.{}.{}".format(
                            enemy.unit_id, field), fingerprints))
            activation_dependencies = tuple(sorted(set(
                activation_dependencies)))
            geometry_dependencies = tuple(sorted(set(base_dependencies)))
            geometry_support = SupportRecord.create(
                "fdas-city-region-geometry", self.version,
                {
                    "city_id": city.city_id,
                    "region_id": region_ref.entity_id,
                }, geometry_dependencies, {
                    "city_id": city.city_id,
                    "policy": self.policy.policy_id,
                    "radius": self.policy.radius,
                }, (self.projector_id,))
            records.append(self._record(
                scope, AtomNamespace.DERIVED, "region-centered-on",
                (region_ref, city_ref), AuthorityClass.DETERMINISTIC_DERIVED,
                activation_dependencies, {
                    "city_id": city.city_id,
                    "policy": self.policy.policy_id,
                }))
            for reason in reasons:
                records.append(self._record(
                    scope, AtomNamespace.DIAGNOSTIC,
                    "region-activation-reason",
                    (region_ref, SymbolRef("activation-reason", reason)),
                    AuthorityClass.POLICY,
                    activation_dependencies, {
                        "policy": self.policy.policy_id,
                        "reason": reason,
                    }, truth={"structural": True}))
            tiles = self._region_tiles(city, snapshot, self.policy.radius)
            tile_set = frozenset(tiles)
            for tile in tiles:
                tile_ref = EntityRef("tile", str(tile))
                records.append(self._record(
                    scope, AtomNamespace.DERIVED, "tile-in-region",
                    (tile_ref, region_ref),
                    AuthorityClass.DETERMINISTIC_DERIVED,
                    geometry_dependencies, {
                        "radius": self.policy.radius,
                        "tile": tile,
                    }, support=geometry_support))
                terrain = terrain_by_tile.get(tile)
                if terrain is not None and terrain.get("terrain") is not None:
                    terrain_dependency = snapshot_dependency_ref(
                        snapshot,
                        "map_tiles.{}.terrain".format(tile), fingerprints)
                    records.append(self._record(
                        scope, AtomNamespace.AUTHORITATIVE, "terrain-kind",
                        (tile_ref, SymbolRef(
                            "terrain", str(terrain["terrain"]))),
                        AuthorityClass.ENGINE_AUTHORITATIVE,
                        geometry_dependencies + (terrain_dependency,),
                        terrain))
                for neighbor in self._adjacent(tile, snapshot):
                    if neighbor not in tile_set:
                        continue
                    records.append(self._record(
                        scope, AtomNamespace.DERIVED, "tile-adjacent",
                        (tile_ref, EntityRef("tile", str(neighbor))),
                        AuthorityClass.DETERMINISTIC_DERIVED,
                        geometry_dependencies, {
                            "from": tile,
                            "to": neighbor,
                        }, support=geometry_support))
            for enemy in threats:
                enemy_paths = (
                    "visible_enemy_units.{}.x".format(enemy.unit_id),
                    "visible_enemy_units.{}.y".format(enemy.unit_id),
                )
                dependencies = activation_dependencies + tuple(
                    snapshot_dependency_ref(snapshot, path, fingerprints)
                    for path in enemy_paths)
                records.append(self._record(
                    scope, AtomNamespace.DERIVED, "visible-threat-near",
                    (EntityRef("unit", str(enemy.unit_id)), city_ref,
                     policy_ref),
                    AuthorityClass.DETERMINISTIC_DERIVED,
                    dependencies, {
                        "distance": self._distance(city, enemy, snapshot),
                        "radius": self.policy.radius,
                    }))
        return tuple(sorted(records, key=lambda value: value.atom_id))
