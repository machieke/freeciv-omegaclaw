"""Component-only unit capability and city-defense FDAS projection."""

import json
from dataclasses import dataclass, replace

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
        _spec("unit-critical-garrison", (("unit",), ("city",)),
              derived, ("city-facts",)),
        _spec("unit-fortification-opportunity", (("unit",), ("city",)),
              derived, ("city-facts",)),
        _spec("unit-reinforcement-route", (("unit",), ("city",)),
              derived, ("city-facts",)),
        _spec("city-replacement-defender-available", (
            ("city",), ("unit",)), derived, ("city-facts",)),
        _spec("unit-coordinated-replacement-for", (
            ("unit",), ("unit",), ("city",)),
            derived, ("city-facts",)),
        _spec("city-garrison-covered", (("city",), ("defense-policy",)),
              derived, ("city-facts",)),
        _spec("city-garrison-deficit", (("city",), ("defense-policy",)),
              derived, ("city-facts",)),
        _spec("city-visible-threat", (("city",), ("unit",)),
              derived, ("city-facts",)),
        _spec("city-threat-arrival-estimate", (
            ("city",), ("unit",), ("threat-model",)),
            AtomNamespace.BELIEF, ("city-facts",), truth="uncertain"),
        _spec("city-threat-arrives-before-defense", (
            ("city",), ("unit",), ("unit",)),
            AtomNamespace.BELIEF, ("city-facts",), truth="uncertain"),
    ))


def unit_defense_scopes(snapshot):
    scopes = list(city_economy_scopes(snapshot))
    scopes = [
        replace(value, namespaces=frozenset(
            set(value.namespaces).union((AtomNamespace.BELIEF,))))
        if value.scope_kind == "city-facts" else value
        for value in scopes]
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
    incremental_dependency_roots = frozenset((
        "cities", "legal_actions", "map_height", "map_width", "map_wrap_x",
        "map_wrap_y", "movement_routes", "player_id", "source_seq", "turn",
        "units", "visible_enemy_units",
    ))
    incremental_dependency_kinds = frozenset(("policy", "ruleset-digest"))

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
            label
            for value in self.ruleset_ir.rules
            if value.target_kind == "unit"
            for label in {
                value.rule_name, getattr(value, "display_name", None)}
            if label)
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

    def _uncertain_record(self, scope, predicate, arguments, grounding):
        truth = {
            "confidence": float(grounding.value["confidence"]),
            "strength": 1.0,
            "uncertain": True,
            "unknown_mass": float(grounding.value["unknown_mass"]),
        }
        key = AtomKey(
            AtomNamespace.BELIEF, predicate, tuple(arguments), scope.scope_id)
        support = SupportRecord.create(
            "model-visible-threat-eta", "1.0", key.to_dict(),
            grounding.dependencies, grounding.witness,
            (self.projector_id, "ruleset-move-rate-geometric-lower-bound"),
            confidence_cap=grounding.confidence_cap)
        return AtomRecord.create(
            key, AuthorityClass.UNCERTAIN_BELIEF, truth, scope.validity,
            (support,),
            (self.projector_id, "ruleset-move-rate-geometric-lower-bound"),
            tags=(("domain", "unit-defense-shadow"),
                  ("epistemic", "control-model")),
            truth_hash=structural_hash(truth))

    def _deadline_record(self, scope, city_ref, enemy, defender_id,
                         threat_eta, defense_eta):
        truth = {
            "confidence": float(threat_eta.value["confidence"]),
            "strength": 1.0,
            "uncertain": True,
            "unknown_mass": float(threat_eta.value["unknown_mass"]),
        }
        key = AtomKey(
            AtomNamespace.BELIEF,
            "city-threat-arrives-before-defense",
            (city_ref, EntityRef("unit", str(enemy.unit_id)),
             EntityRef("unit", str(defender_id))),
            scope.scope_id)
        witness = {
            "defender_arrival_turn": (
                int(scope.validity.valid_from_turn) + int(defense_eta.value)),
            "defender_eta_turns": defense_eta.value,
            "enemy_earliest_attack_turn":
                threat_eta.value["earliest_attack_turn"],
            "threat_basis": threat_eta.value["basis"],
        }
        support = SupportRecord.create(
            "compare-threat-defense-deadline", "1.0", key.to_dict(),
            tuple(sorted(set(
                threat_eta.dependencies + defense_eta.dependencies))), witness,
            (self.projector_id, "mixed-exact-and-control-deadline"),
            confidence_cap=threat_eta.confidence_cap)
        return AtomRecord.create(
            key, AuthorityClass.UNCERTAIN_BELIEF, truth, scope.validity,
            (support,),
            (self.projector_id, "mixed-exact-and-control-deadline"),
            tags=(("domain", "unit-defense-shadow"),
                  ("epistemic", "control-model")),
            truth_hash=structural_hash(truth))

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
        legal_moves = {}
        for action_json in snapshot.legal_action_json:
            action = json.loads(action_json)
            if action.get("action_type") == "unit_fortify":
                legal_fortify[str(action.get("actor_id"))] = (
                    action_json,
                    snapshot_dependency_ref(
                        snapshot,
                        "legal_actions.{}".format(structural_hash(action_json)),
                        fingerprints))
            elif action.get("action_type") == "unit_move":
                target = action.get("target")
                if (isinstance(target, dict)
                        and None not in (target.get("x"), target.get("y"))):
                    legal_moves[(
                        str(action.get("actor_id")),
                        int(target["x"]), int(target["y"]),
                    )] = (
                        action_json,
                        snapshot_dependency_ref(
                            snapshot,
                            "legal_actions.{}".format(
                                structural_hash(action_json)),
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
            reinforcement_etas = []
            if predicate == "city-garrison-deficit" and city.tile is not None:
                for unit_id, unit in sorted(defender_by_id.items()):
                    if unit.tile is None or unit.tile == city.tile:
                        continue
                    route = self.groundings.evaluate(
                        "movement.shortest-route", snapshot, unit_id, city.tile)
                    eta = self.groundings.evaluate(
                        "movement.arrival-eta", snapshot, unit_id, city.tile)
                    if not route.available or not eta.available:
                        continue
                    reinforcement_etas.append((unit_id, eta))
                    records.append(self._record(
                        scope, AtomNamespace.DERIVED,
                        "unit-reinforcement-route",
                        (EntityRef("unit", unit_id), city_ref),
                        AuthorityClass.DETERMINISTIC_DERIVED,
                        route.dependencies + eta.dependencies,
                        {
                            "destination_tile": city.tile,
                            "estimated_turns": eta.value,
                            "first_step_tile": route.value["first_step_tile"],
                            "path_length": route.value["path_length"],
                            "route_authority": route.value["authority"],
                        }))
            local = tuple(
                unit for unit in defender_by_id.values()
                if unit.tile is not None and unit.tile == city.tile)
            critical = []
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
                    removal = self.groundings.evaluate(
                        "defense.removal-deficit", snapshot, unit.unit_id,
                        self.policy.maximum_garrison_per_city)
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
                    if (removal.available
                            and removal.value["creates_deficit"] is True):
                        critical.append((unit, removal))
                        records.append(self._record(
                            scope, AtomNamespace.DERIVED,
                            "unit-critical-garrison", (unit_ref, city_ref),
                            AuthorityClass.DETERMINISTIC_DERIVED,
                            removal.dependencies + policy_refs,
                            removal.value))
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

            # Replacement is a coordinated causal route, not a waiver of the
            # protected-garrison invariant. Materialize it only when another
            # persistent defender can legally take the critical unit's place
            # through the current native server-selected route, and moving
            # that replacement creates no deficit at its own source.
            if critical and city.tile is not None and snapshot.map_width > 0:
                for replacement_id, replacement in sorted(
                        defender_by_id.items()):
                    if any(
                            replacement.unit_id == value[0].unit_id
                            for value in critical):
                        continue
                    removal = self.groundings.evaluate(
                        "defense.removal-deficit", snapshot,
                        replacement.unit_id,
                        self.policy.maximum_garrison_per_city)
                    route = self.groundings.evaluate(
                        "movement.shortest-route", snapshot,
                        replacement.unit_id, city.tile)
                    eta = self.groundings.evaluate(
                        "movement.arrival-eta", snapshot,
                        replacement.unit_id, city.tile)
                    if (not removal.available
                            or removal.value["creates_deficit"] is True
                            or not route.available or not eta.available):
                        continue
                    first_step = int(route.value["first_step_tile"])
                    legal = legal_moves.get((
                        replacement_id,
                        first_step % snapshot.map_width,
                        first_step // snapshot.map_width,
                    ))
                    if legal is None:
                        continue
                    dependencies = tuple(sorted(set(
                        removal.dependencies + route.dependencies
                        + eta.dependencies + required.dependencies
                        + current.dependencies + policy_refs
                        + (legal[1],))))
                    witness = {
                        "action_key": legal[0],
                        "destination_tile": city.tile,
                        "estimated_turns": eta.value,
                        "first_step_tile": first_step,
                        "removal_deficit": removal.value,
                        "route_authority": route.value["authority"],
                    }
                    records.append(self._record(
                        scope, AtomNamespace.DERIVED,
                        "city-replacement-defender-available",
                        (city_ref, EntityRef("unit", replacement_id)),
                        AuthorityClass.DETERMINISTIC_DERIVED,
                        dependencies, witness))
                    for protected, protected_removal in critical:
                        coordinated_witness = dict(witness)
                        coordinated_witness["protected_defender_id"] = (
                            protected.unit_id)
                        coordinated_witness["protected_removal_deficit"] = (
                            protected_removal.value)
                        records.append(self._record(
                            scope, AtomNamespace.DERIVED,
                            "unit-coordinated-replacement-for",
                            (EntityRef("unit", replacement_id),
                             EntityRef("unit", str(protected.unit_id)),
                             city_ref),
                            AuthorityClass.DETERMINISTIC_DERIVED,
                            dependencies + protected_removal.dependencies,
                            coordinated_witness))

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
                eta = self.groundings.evaluate(
                    "defense.visible-threat-eta", snapshot,
                    city.city_id, enemy.unit_id)
                if eta.available:
                    records.append(self._uncertain_record(
                        scope, "city-threat-arrival-estimate",
                        (city_ref, EntityRef("unit", str(enemy.unit_id)),
                         SymbolRef(
                             "threat-model",
                             "ruleset-geometric-lower-bound:v1.0")),
                        eta))
                    for defender_id, defense_eta in reinforcement_etas:
                        defender_arrival = (
                            int(snapshot.turn) + int(defense_eta.value))
                        if (int(eta.value["earliest_attack_turn"])
                                < defender_arrival):
                            records.append(self._deadline_record(
                                scope, city_ref, enemy, defender_id,
                                eta, defense_eta))
        return tuple(sorted(records, key=lambda value: value.atom_id))
