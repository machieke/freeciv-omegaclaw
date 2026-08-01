"""Ruleset-exact FDAS founder population-recovery scopes."""

import json
from dataclasses import replace

from ...events.schema import structural_hash
from ..ruleset_profiles import population_recovery_profile
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
)
from .predicates import PredicateSpec, legacy_predicate_registry
from .scopes import ScopeSpec, snapshot_scopes


_CRISP = {"confidence": 1.0, "crisp": True, "strength": 1.0}
_CRISP_HASH = structural_hash(_CRISP)


def _spec(predicate, arguments):
    return PredicateSpec(
        predicate, len(arguments), tuple(tuple(value) for value in arguments),
        frozenset((AtomNamespace.DERIVED,)), "crisp",
        frozenset(("population-recovery",)), "explicit-witness",
        "parent-summary", "1.0")


def population_recovery_predicate_registry():
    return legacy_predicate_registry().extended((
        _spec("population-recovery-founder", (
            ("population-recovery",), ("unit",))),
        _spec("population-recovery-target-city", (
            ("population-recovery",), ("city",))),
        _spec("founder-population-recovery-capable", (
            ("unit",), ("city",))),
        _spec("founder-population-recovery-colocated", (
            ("unit",), ("city",))),
        _spec("population-recovery-current-legal-action", (
            ("population-recovery",), ("action",))),
        _spec("population-recovery-expected-city-gain", (
            ("population-recovery",), ("city",))),
    ))


class PopulationRecoveryProjector(object):
    """Project only legal join-city actions with exact founder semantics."""

    projector_id = "fdas-population-recovery-projector"
    version = "1.0"

    def __init__(self, ruleset_ir, ruleset_digest):
        if ruleset_ir is None:
            raise ValueError("population recovery requires ruleset IR")
        if not isinstance(ruleset_digest, str) or not ruleset_digest:
            raise ValueError("population recovery requires ruleset digest")
        self.ruleset_ir = ruleset_ir
        self.ruleset_digest = ruleset_digest
        self.predicate_registry = population_recovery_predicate_registry()

    def _dependency(self, unit_type):
        key = DependencyKey(
            "ruleset-digest", self.ruleset_digest,
            "target:unit:{}".format(unit_type))
        return DependencyRef(key, structural_hash({
            "ruleset_digest": self.ruleset_digest,
            "target": unit_type,
            "target_kind": "unit",
        }))

    def extend_fingerprints(self, fingerprints):
        result = dict(fingerprints)
        for rule in getattr(self.ruleset_ir, "rules", ()):
            if getattr(rule, "target_kind", None) != "unit":
                continue
            for label in {
                    getattr(rule, "display_name", None),
                    getattr(rule, "rule_name", None)}:
                if label:
                    dependency = self._dependency(label)
                    result[dependency.key] = dependency.fingerprint
        return result

    def _rows(self, snapshot):
        rows = []
        for action_key in snapshot.legal_action_json:
            action = json.loads(action_key)
            target = action.get("target")
            if (action.get("action_type") != "unit_join_city"
                    or not isinstance(target, dict)
                    or not isinstance(target.get("city_id"), int)):
                continue
            founder = snapshot.unit(action.get("actor_id"))
            city = snapshot.city(target["city_id"])
            if (founder is None or city is None or founder.tile is None
                    or city.tile is None or founder.tile != city.tile):
                continue
            profile = population_recovery_profile(
                self.ruleset_ir, founder.unit_type)
            if profile is None:
                continue
            rows.append((founder, city, profile, action, action_key))
        return tuple(sorted(rows, key=lambda value: (
            value[0].unit_id, value[1].city_id, value[4])))

    def scopes(self, snapshot):
        world, empire = snapshot_scopes(snapshot)
        scopes = [world, empire]
        prefix = empire.scope_id.rsplit(":empire", 1)[0]
        validity = replace(
            empire.validity, ruleset_digest=self.ruleset_digest)
        predicates = tuple(sorted(
            value for value in self.predicate_registry.predicates
            if value.startswith(("population-recovery-",
                                 "founder-population-recovery-"))))
        for founder, city, _profile, _action, _action_key in self._rows(snapshot):
            recovery_id = "unit:{}:city:{}".format(
                founder.unit_id, city.city_id)
            scopes.append(ScopeSpec(
                "{}:population-recovery:{}".format(prefix, recovery_id),
                "population-recovery", snapshot.player_id,
                (EntityRef("population-recovery", recovery_id),),
                (empire.scope_id,), ("owns-unit", "owns-city", "unit-at"),
                predicates, frozenset((AtomNamespace.DERIVED,)),
                50, 10, 10, 1, "snapshot-and-ruleset-revision", validity))
        return tuple(scopes)

    def _record(self, scope, predicate, arguments, dependencies, witness):
        key = AtomKey(
            AtomNamespace.DERIVED, predicate, tuple(arguments), scope.scope_id)
        dependencies = tuple(sorted(set(dependencies)))
        support = SupportRecord.create(
            self.projector_id, self.version, key.to_dict(), dependencies,
            witness, (self.projector_id, "compiled-ruleset-profile",
                      "server-advertised-action"))
        return AtomRecord.create(
            key, AuthorityClass.DETERMINISTIC_DERIVED, _CRISP,
            scope.validity, (support,),
            (self.projector_id, "compiled-ruleset-profile",
             "server-advertised-action"),
            tags=(("domain", "population-recovery"),),
            truth_hash=_CRISP_HASH)

    def project(self, snapshot, scopes, fingerprints):
        scope_by_id = dict(
            (value.root_entities[0].entity_id, value)
            for value in scopes if value.scope_kind == "population-recovery")
        records = []
        for founder, city, profile, action, action_key in self._rows(snapshot):
            recovery_id = "unit:{}:city:{}".format(
                founder.unit_id, city.city_id)
            scope = scope_by_id[recovery_id]
            recovery = scope.root_entities[0]
            founder_ref = EntityRef("unit", str(founder.unit_id))
            city_ref = EntityRef("city", str(city.city_id))
            dependencies = (
                snapshot_dependency_ref(
                    snapshot, "units.{}.__exists__".format(founder.unit_id),
                    fingerprints),
                snapshot_dependency_ref(
                    snapshot, "units.{}.tile".format(founder.unit_id),
                    fingerprints),
                snapshot_dependency_ref(
                    snapshot, "units.{}.type".format(founder.unit_id),
                    fingerprints),
                snapshot_dependency_ref(
                    snapshot, "cities.{}.__exists__".format(city.city_id),
                    fingerprints),
                snapshot_dependency_ref(
                    snapshot, "cities.{}.tile".format(city.city_id),
                    fingerprints),
                snapshot_dependency_ref(
                    snapshot, "cities.{}.size".format(city.city_id),
                    fingerprints),
                snapshot_dependency_ref(
                    snapshot, "legal_actions.{}".format(
                        structural_hash(action_key)), fingerprints),
                self._dependency(founder.unit_type),
            )
            witness = {
                "action": action,
                "action_key": action_key,
                "city_size_before": city.size,
                "profile": profile,
            }
            for predicate, arguments in (
                    ("population-recovery-founder", (recovery, founder_ref)),
                    ("population-recovery-target-city", (recovery, city_ref)),
                    ("founder-population-recovery-capable",
                     (founder_ref, city_ref)),
                    ("founder-population-recovery-colocated",
                     (founder_ref, city_ref)),
                    ("population-recovery-current-legal-action",
                     (recovery, EntityRef(
                         "action", "legal-" +
                         structural_hash(action_key)[:24]))),
                    ("population-recovery-expected-city-gain",
                     (recovery, city_ref))):
                records.append(self._record(
                    scope, predicate, arguments, dependencies, witness))
        return tuple(sorted(records, key=lambda value: value.atom_id))
