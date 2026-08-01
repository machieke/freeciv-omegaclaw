"""Component-only unit capability and city-defense FDAS projection."""

import json
from dataclasses import dataclass

from ...events.schema import structural_hash
from .city import city_economy_predicate_registry, city_economy_scopes
from .delta import snapshot_dependency_ref
from .grounding import TypedGroundingRegistry
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


_CRISP = {"confidence": 1.0, "crisp": True, "strength": 1.0}
_CRISP_HASH = structural_hash(_CRISP)


@dataclass(frozen=True)
class CityDefensePolicy:
    maximum_garrison_per_city: int = 3
    visible_threat_radius: int = 3
    schema_version: str = "1.0"

    def __post_init__(self):
        for value, name, maximum in (
                (self.maximum_garrison_per_city, "garrison limit", 20),
                (self.visible_threat_radius, "visible threat radius", 20)):
            if (isinstance(value, bool) or not isinstance(value, int)
                    or not 1 <= value <= maximum):
                raise ValueError("{} must be in 1..{}".format(name, maximum))

    @property
    def policy_id(self):
        return "garrison:max{}:threat{}:v{}".format(
            self.maximum_garrison_per_city,
            self.visible_threat_radius,
            self.schema_version)

    def dependency_refs(self):
        owner = "fdas-city-defense-policy:{}".format(self.schema_version)
        values = {
            "maximum_garrison_per_city": self.maximum_garrison_per_city,
            "visible_threat_radius": self.visible_threat_radius,
        }
        return tuple(DependencyRef(
            DependencyKey("policy", owner, key), structural_hash(value))
            for key, value in sorted(values.items()))


def _spec(predicate, arguments, namespace, scopes, truth="crisp"):
    return PredicateSpec(
        predicate,
        len(arguments),
        tuple(tuple(value) for value in arguments),
        frozenset((namespace,)),
        truth,
        frozenset(scopes),
        "explicit-witness",
        "parent-summary",
        "1.0",
    )


def unit_defense_predicate_registry():
    derived = AtomNamespace.DERIVED
    observation = AtomNamespace.OBSERVATION
    return city_economy_predicate_registry().extended((
        _spec("visible-enemy-unit", (("unit",), ("player",)),
              observation, ("world",)),
        _spec("visible-enemy-at", (("unit",), ("tile",)),
              observation, ("world",)),
        _spec("unit-has-capability", (("unit",), ("capability",)),
              derived, ("unit-facts",)),
        _spec("unit-persistent-defender", (("unit",),),
              derived, ("unit-facts",)),
        _spec("unit-protects-city", (("unit",), ("city",)),
              derived, ("city-facts",)),
        _spec("unit-required-garrison", (("unit",), ("city",)),
              derived, ("city-facts",)),
        _spec("unit-fortification-opportunity", (("unit",), ("city",)),
              derived, ("city-facts",)),
        _spec("city-garrison-covered", (("city",), ("defense-policy",)),
              derived, ("city-facts",)),
        _spec("city-garrison-deficit", (("city",), ("defense-policy",)),
              derived, ("city-facts",)),
        _spec("city-visible-threat", (("city",), ("unit",)),
              derived, ("city-facts",)),
    ))


def unit_defense_scopes(snapshot):
    scopes = list(city_economy_scopes(snapshot))
    empire = next(value for value in scopes if value.scope_kind == "empire")
    predicates = unit_defense_predicate_registry().predicates
    for unit in sorted(snapshot.units, key=lambda value: value.unit_id):
        scopes.append(ScopeSpec(
            "{}:unit:{}:facts".format(
                empire.scope_id.rsplit(":empire", 1)[0], unit.unit_id),
            "unit-facts",
            snapshot.player_id,
            (EntityRef("unit", str(unit.unit_id)),),
            (empire.scope_id,),
            ("owns-unit", "unit-activity", "unit-at", "unit-type"),
            tuple(sorted(value for value in predicates
                         if value.startswith("unit-"))),
            frozenset((AtomNamespace.DERIVED,)),
            200,
            1000,
            500,
            2,
            "snapshot-revision",
            empire.validity,
        ))
    return tuple(scopes)


class UnitDefenseProjector(object):
    """Project exact unit capabilities and factual local defense conditions."""

    projector_id = "fdas-unit-defense-shadow"
    version = "1.0"

    def __init__(self, ruleset_ir, ruleset_digest, policy=None):
        self.ruleset_ir = ruleset_ir
        self.ruleset_digest = str(ruleset_digest)
        self.policy = policy or CityDefensePolicy()
        self.groundings = TypedGroundingRegistry(
            ruleset_ir, ruleset_digest=self.ruleset_digest)
        self.predicate_registry = unit_defense_predicate_registry()

    def scopes(self, snapshot):
        return unit_defense_scopes(snapshot)

    def extend_fingerprints(self, fingerprints):
        result = dict(fingerprints)
        for dependency in self.policy.dependency_refs():
            result[dependency.key] = dependency.fingerprint
        unit_types = set()
        # Per-type keys are also added lazily by ``project`` validation below;
        # add the complete compiled catalog here so any current unit is covered.
        unit_types.update(
            value.rule_name for value in self.ruleset_ir.rules
            if value.target_kind == "unit")
        unit_types.add("defender-catalog")
        for unit_type in sorted(unit_types):
            key = DependencyKey(
                "ruleset-digest", self.ruleset_digest,
                "target:unit:{}".format(unit_type))
            result[key] = structural_hash({
                "ruleset_digest": self.ruleset_digest,
                "target": unit_type,
                "target_kind": "unit",
            })
        return result

    @staticmethod
    def _support(derivation, key, dependencies, witness, provenance):
        return SupportRecord.create(
            derivation, "1.0", key.to_dict(), tuple(sorted(set(dependencies))),
            witness, (provenance,))

    def _record(self, scope, namespace, predicate, arguments, authority,
                dependencies, witness, provenance=None):
        provenance = provenance or self.projector_id
        key = AtomKey(namespace, predicate, tuple(arguments), scope.scope_id)
        support = self._support(
            "derive-{}".format(predicate), key, dependencies, witness,
            provenance)
        return AtomRecord.create(
            key, authority, _CRISP, scope.validity, (support,), (provenance,),
            tags=(("domain", "unit-defense-shadow"),),
            truth_hash=_CRISP_HASH)

    @staticmethod
    def _scope_maps(scopes):
        world = next(value for value in scopes if value.scope_kind == "world")
        cities = dict(
            (value.root_entities[0].entity_id, value)
            for value in scopes if value.scope_kind == "city-facts")
        units = dict(
            (value.root_entities[0].entity_id, value)
            for value in scopes if value.scope_kind == "unit-facts")
        return world, cities, units

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

    def project(self, snapshot, scopes, fingerprints):
        self.groundings.prime(snapshot, fingerprints)
        world, city_scopes, unit_scopes = self._scope_maps(scopes)
        policy_refs = self.policy.dependency_refs()
        player = EntityRef("player", str(snapshot.player_id))
        policy = SymbolRef("defense-policy", self.policy.policy_id)
        records = []

        for enemy in sorted(
                snapshot.visible_enemy_units, key=lambda value: value.unit_id):
            enemy_ref = EntityRef("unit", str(enemy.unit_id))
            exists = snapshot_dependency_ref(
                snapshot,
                "visible_enemy_units.{}.__exists__".format(enemy.unit_id),
                fingerprints)
            records.append(self._record(
                world, AtomNamespace.OBSERVATION, "visible-enemy-unit",
                (enemy_ref, player), AuthorityClass.PACKET_OBSERVATION,
                (exists,), enemy.grounded_dict()))
            if enemy.tile is not None:
                tile = snapshot_dependency_ref(
                    snapshot,
                    "visible_enemy_units.{}.tile".format(enemy.unit_id),
                    fingerprints)
                records.append(self._record(
                    world, AtomNamespace.OBSERVATION, "visible-enemy-at",
                    (enemy_ref, EntityRef("tile", str(enemy.tile))),
                    AuthorityClass.PACKET_OBSERVATION,
                    (exists, tile), enemy.grounded_dict()))

        defender_by_id = {}
        for unit in sorted(snapshot.units, key=lambda value: value.unit_id):
            unit_id = str(unit.unit_id)
            scope = unit_scopes[unit_id]
            defender = self.groundings.evaluate(
                "unit.persistent-defender", snapshot, unit.unit_id)
            profile = self.groundings.evaluate(
                "unit.combat-profile", snapshot, unit.unit_id)
            if profile.available and (profile.value["attack"] > 0
                                      or profile.value["defense"] > 0):
                records.append(self._record(
                    scope, AtomNamespace.DERIVED, "unit-has-capability",
                    (EntityRef("unit", unit_id),
                     SymbolRef("capability", "persistent-combat")),
                    AuthorityClass.DETERMINISTIC_DERIVED,
                    profile.dependencies, profile.witness))
            if defender.available and defender.value is True:
                defender_by_id[unit_id] = unit
                records.extend((
                    self._record(
                        scope, AtomNamespace.DERIVED,
                        "unit-has-capability",
                        (EntityRef("unit", unit_id), SymbolRef(
                            "capability", "persistent-land-defense")),
                        AuthorityClass.DETERMINISTIC_DERIVED,
                        defender.dependencies, defender.witness),
                    self._record(
                        scope, AtomNamespace.DERIVED,
                        "unit-persistent-defender",
                        (EntityRef("unit", unit_id),),
                        AuthorityClass.DETERMINISTIC_DERIVED,
                        defender.dependencies, defender.witness),
                ))

        legal_fortify = {}
        for action_json in snapshot.legal_action_json:
            action = json.loads(action_json)
            if action.get("action_type") == "unit_fortify":
                legal_fortify[str(action.get("actor_id"))] = (
                    action_json,
                    snapshot_dependency_ref(
                        snapshot,
                        "legal_actions.{}".format(structural_hash(action_json)),
                        fingerprints))

        for city in sorted(snapshot.cities, key=lambda value: value.city_id):
            city_id = str(city.city_id)
            scope = city_scopes[city_id]
            city_ref = EntityRef("city", city_id)
            required = self.groundings.evaluate(
                "city.required-garrison-count", snapshot, city.city_id,
                self.policy.maximum_garrison_per_city)
            current = self.groundings.evaluate(
                "city.local-garrison-count", snapshot, city.city_id)
            if not required.available or not current.available:
                continue
            predicate = (
                "city-garrison-covered"
                if int(current.value) >= int(required.value)
                else "city-garrison-deficit")
            records.append(self._record(
                scope, AtomNamespace.DERIVED, predicate, (city_ref, policy),
                AuthorityClass.DETERMINISTIC_DERIVED,
                required.dependencies + current.dependencies + policy_refs,
                {
                    "current": current.value,
                    "policy": self.policy.policy_id,
                    "required": required.value,
                }))
            local = tuple(
                unit for unit in defender_by_id.values()
                if unit.tile is not None and unit.tile == city.tile)
            for unit in sorted(local, key=lambda value: value.unit_id):
                unit_ref = EntityRef("unit", str(unit.unit_id))
                records.append(self._record(
                    scope, AtomNamespace.DERIVED, "unit-protects-city",
                    (unit_ref, city_ref), AuthorityClass.DETERMINISTIC_DERIVED,
                    current.dependencies, {
                        "city_id": city.city_id,
                        "unit_id": unit.unit_id,
                    }))
                if len(local) <= int(required.value):
                    records.append(self._record(
                        scope, AtomNamespace.DERIVED,
                        "unit-required-garrison", (unit_ref, city_ref),
                        AuthorityClass.DETERMINISTIC_DERIVED,
                        required.dependencies + current.dependencies
                        + policy_refs,
                        {
                            "current": len(local),
                            "required": required.value,
                            "unit_id": unit.unit_id,
                        }))
                fortify = legal_fortify.get(str(unit.unit_id))
                if (fortify is not None
                        and str(unit.activity or "").lower() not in (
                            "fortify", "fortified", "fortifying")):
                    records.append(self._record(
                        scope, AtomNamespace.DERIVED,
                        "unit-fortification-opportunity",
                        (unit_ref, city_ref),
                        AuthorityClass.DETERMINISTIC_DERIVED,
                        current.dependencies + (fortify[1],),
                        {
                            "action_key": fortify[0],
                            "factual_garrison_deficit": (
                                predicate == "city-garrison-deficit"),
                        }))

            for enemy in sorted(
                    snapshot.visible_enemy_units,
                    key=lambda value: value.unit_id):
                distance = self._distance(city, enemy, snapshot)
                if distance is None or distance > self.policy.visible_threat_radius:
                    continue
                paths = (
                    "cities.{}.x".format(city_id),
                    "cities.{}.y".format(city_id),
                    "visible_enemy_units.{}.x".format(enemy.unit_id),
                    "visible_enemy_units.{}.y".format(enemy.unit_id),
                    "map_width", "map_height", "map_wrap_x", "map_wrap_y",
                )
                dependencies = tuple(
                    snapshot_dependency_ref(snapshot, path, fingerprints)
                    for path in paths) + policy_refs
                records.append(self._record(
                    scope, AtomNamespace.DERIVED, "city-visible-threat",
                    (city_ref, EntityRef("unit", str(enemy.unit_id))),
                    AuthorityClass.DETERMINISTIC_DERIVED,
                    dependencies, {
                        "distance": distance,
                        "radius": self.policy.visible_threat_radius,
                    }))
        return tuple(sorted(records, key=lambda value: value.atom_id))
