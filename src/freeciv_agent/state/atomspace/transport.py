"""Ruleset-exact, current-snapshot FDAS transport capability scopes."""

import json
from dataclasses import replace

from ...events.schema import structural_hash
from ...planning.domain_models.transport import transport_unit_profile
from ...pressure.resource_capacity import ResourceCapacityExtractor
from ...pressure.resource_claims import GameResourceKind
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
from .predicates import PredicateSpec, legacy_predicate_registry
from .scopes import ScopeSpec, snapshot_scopes


_CRISP = {"confidence": 1.0, "crisp": True, "strength": 1.0}
_CRISP_HASH = structural_hash(_CRISP)


def _spec(predicate, arguments):
    return PredicateSpec(
        predicate, len(arguments), tuple(tuple(value) for value in arguments),
        frozenset((AtomNamespace.DERIVED,)), "crisp",
        frozenset(("transport",)), "explicit-witness", "parent-summary",
        "1.0")


def transport_predicate_registry():
    return legacy_predicate_registry().extended((
        _spec("transport-backed-by-unit", (
            ("transport",), ("unit",))),
        _spec("transport-accepts-unit-class", (
            ("transport",), ("unit-class",))),
        _spec("transport-seat-resource", (
            ("transport",), ("game-resource",))),
        _spec("transport-seat-available", (("transport",),)),
        _spec("transport-at-capacity", (("transport",),)),
        _spec("unit-ruleset-founder-capable", (("unit",),)),
        _spec("transport-cargo-compatible", (
            ("transport",), ("unit",))),
        _spec("transport-compatible-founder", (
            ("transport",), ("unit",))),
        _spec("unit-carried-by", (
            ("unit",), ("transport",))),
        _spec("transport-current-embark-action", (
            ("transport",), ("unit",), ("action",))),
        _spec("transport-current-disembark-action", (
            ("transport",), ("unit",), ("action",))),
    ))


class TransportCapabilityProjector(object):
    """Project exact carrier profiles, load, cargo, and legal edge bindings."""

    projector_id = "fdas-transport-capability-projector"
    version = "1.0"

    def __init__(self, ruleset_ir, ruleset_digest):
        if ruleset_ir is None:
            raise ValueError("transport projection requires ruleset IR")
        if not isinstance(ruleset_digest, str) or not ruleset_digest:
            raise ValueError("transport projection requires ruleset digest")
        self.ruleset_ir = ruleset_ir
        self.ruleset_digest = ruleset_digest
        self.predicate_registry = transport_predicate_registry()

    def _profile(self, unit):
        return transport_unit_profile(self.ruleset_ir, unit.unit_type)

    def _ruleset_dependency(self, unit_type):
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
        labels = set()
        for rule in getattr(self.ruleset_ir, "rules", ()):
            if getattr(rule, "target_kind", None) != "unit":
                continue
            for label in (
                    getattr(rule, "rule_name", None),
                    getattr(rule, "display_name", None)):
                if isinstance(label, str) and label:
                    labels.add(label)
        for label in sorted(labels):
            dependency = self._ruleset_dependency(label)
            result[dependency.key] = dependency.fingerprint
        return result

    def _carriers(self, snapshot):
        rows = []
        for unit in sorted(snapshot.units, key=lambda value: value.unit_id):
            profile = self._profile(unit)
            if profile is not None and profile.transport_capacity > 0:
                rows.append((unit, profile))
        return tuple(rows)

    def scopes(self, snapshot):
        world, empire = snapshot_scopes(snapshot)
        scopes = [world, empire]
        prefix = empire.scope_id.rsplit(":empire", 1)[0]
        validity = replace(
            empire.validity, ruleset_digest=self.ruleset_digest)
        predicates = tuple(sorted(
            value for value in self.predicate_registry.predicates
            if value.startswith(("transport-", "unit-carried-",
                                 "unit-ruleset-founder-"))))
        for unit, _profile in self._carriers(snapshot):
            transport = EntityRef("transport", "unit:{}".format(unit.unit_id))
            scopes.append(ScopeSpec(
                "{}:transport:{}".format(prefix, unit.unit_id),
                "transport", snapshot.player_id, (transport,),
                (empire.scope_id,), ("owns-unit", "unit-at"), predicates,
                frozenset((AtomNamespace.DERIVED,)), 200, 50, 50, 2,
                "snapshot-and-ruleset-revision", validity))
        return tuple(scopes)

    def _record(self, scope, predicate, arguments, dependencies, witness,
                provenance=()):
        key = AtomKey(
            AtomNamespace.DERIVED, predicate, tuple(arguments), scope.scope_id)
        dependencies = tuple(sorted(set(dependencies)))
        support = SupportRecord.create(
            self.projector_id, self.version, key.to_dict(), dependencies,
            witness, (self.projector_id,) + tuple(provenance))
        return AtomRecord.create(
            key, AuthorityClass.DETERMINISTIC_DERIVED, _CRISP,
            scope.validity, (support,),
            (self.projector_id,) + tuple(provenance),
            tags=(("domain", "transport"),), truth_hash=_CRISP_HASH)

    @staticmethod
    def _unit_dependencies(snapshot, unit, fingerprints, fields=()):
        paths = ["units.{}.__exists__".format(unit.unit_id)]
        paths.extend(
            "units.{}.{}".format(unit.unit_id, value) for value in fields)
        return tuple(snapshot_dependency_ref(
            snapshot, value, fingerprints) for value in paths)

    @staticmethod
    def _target_tile(snapshot, action, default=None):
        target = action.get("target")
        if (isinstance(target, dict)
                and isinstance(target.get("x"), int)
                and not isinstance(target.get("x"), bool)
                and isinstance(target.get("y"), int)
                and not isinstance(target.get("y"), bool)
                and snapshot.map_width > 0):
            return target["x"] + target["y"] * snapshot.map_width
        return default

    @staticmethod
    def _explicit_carrier_id(action):
        target = action.get("target")
        values = [
            action.get("transport_id"), action.get("carrier_id"),
            action.get("target_unit_id")]
        if isinstance(target, dict):
            values.extend((
                target.get("transport_id"), target.get("carrier_id"),
                target.get("target_unit_id"), target.get("unit_id")))
        integers = tuple(sorted(set(
            int(value) for value in values
            if isinstance(value, int) and not isinstance(value, bool))))
        return integers[0] if len(integers) == 1 else None

    def _legal_edges(self, snapshot, carriers, profiles, fingerprints):
        by_id = dict((value.unit_id, value) for value, _profile in carriers)
        carrier_profile = dict(
            (value.unit_id, profile) for value, profile in carriers)
        edges = []
        for action_key in snapshot.legal_action_json:
            action = json.loads(action_key)
            actor_id = action.get("actor_id")
            if isinstance(actor_id, bool) or not isinstance(actor_id, int):
                continue
            cargo = snapshot.unit(actor_id)
            cargo_profile = profiles.get(actor_id)
            if cargo is None or cargo_profile is None:
                continue
            action_type = action.get("action_type")
            mode = None
            candidates = []
            if (action_type in ("unit_board", "unit_embark")
                    or (action_type == "unit_move"
                        and action.get("transport_required") is True)):
                if cargo.transported is True:
                    continue
                mode = "embark"
                tile = self._target_tile(snapshot, action, cargo.tile)
                for carrier, profile in carriers:
                    if (carrier.tile == tile
                            and carrier.carrying is not None
                            and 0 <= carrier.carrying
                            < profile.transport_capacity
                            and cargo_profile.unit_class
                            in profile.cargo_classes):
                        candidates.append(carrier.unit_id)
            elif (action_type in ("unit_deboard", "unit_disembark")
                    or (action_type == "unit_move"
                        and action.get("transport_required") is False)):
                if (cargo.transported is not True
                        or cargo.transported_by not in by_id):
                    continue
                mode = "disembark"
                candidates = [cargo.transported_by]
            if mode is None:
                continue
            explicit = self._explicit_carrier_id(action)
            if explicit is not None:
                candidates = [value for value in candidates
                              if value == explicit]
            candidates = tuple(sorted(set(candidates)))
            if len(candidates) != 1:
                continue
            carrier_id = candidates[0]
            carrier = by_id[carrier_id]
            dependencies = self._unit_dependencies(
                snapshot, cargo, fingerprints,
                ("tile", "transported", "transported_by", "type"))
            dependencies += self._unit_dependencies(
                snapshot, carrier, fingerprints,
                ("carrying", "tile", "type"))
            dependencies += (
                self._ruleset_dependency(cargo.unit_type),
                self._ruleset_dependency(carrier.unit_type),
                snapshot_dependency_ref(
                    snapshot, "legal_actions.{}".format(
                        structural_hash(action_key)), fingerprints),
            )
            edges.append((
                carrier_id, cargo.unit_id, mode, action, action_key,
                tuple(sorted(set(dependencies))),
                carrier_profile[carrier_id]))
        return tuple(edges)

    def project(self, snapshot, scopes, fingerprints):
        carriers = self._carriers(snapshot)
        scope_by_id = dict(
            (int(value.scope_id.rsplit(":", 1)[1]), value)
            for value in scopes if value.scope_kind == "transport")
        profiles = dict(
            (unit.unit_id, self._profile(unit)) for unit in snapshot.units)
        capacity_rows = ResourceCapacityExtractor().extract(
            snapshot, ruleset_ir=self.ruleset_ir).capacities
        capacity_by_owner = dict(
            (value.resource.owner_id, value) for value in capacity_rows
            if value.resource.kind == GameResourceKind.TRANSPORT_SEAT)
        records = []
        for carrier, profile in carriers:
            scope = scope_by_id[carrier.unit_id]
            transport = scope.root_entities[0]
            carrier_ref = EntityRef("unit", str(carrier.unit_id))
            carrier_dependencies = self._unit_dependencies(
                snapshot, carrier, fingerprints, ("carrying", "type"))
            carrier_dependencies += (
                self._ruleset_dependency(carrier.unit_type),)
            profile_witness = profile.to_dict()
            records.append(self._record(
                scope, "transport-backed-by-unit",
                (transport, carrier_ref), carrier_dependencies,
                profile_witness, ("compiled-ruleset-profile",)))
            for cargo_class in profile.cargo_classes:
                records.append(self._record(
                    scope, "transport-accepts-unit-class",
                    (transport, SymbolRef("unit-class", cargo_class)),
                    carrier_dependencies, profile_witness,
                    ("compiled-ruleset-profile",)))

            capacity = capacity_by_owner.get(
                "unit:{}".format(carrier.unit_id))
            if capacity is not None:
                resource = EntityRef(
                    "game-resource", capacity.resource.resource_id)
                records.append(self._record(
                    scope, "transport-seat-resource",
                    (transport, resource), carrier_dependencies,
                    capacity.to_dict(), ("exact-resource-capacity",)))
                records.append(self._record(
                    scope,
                    "transport-seat-available"
                    if capacity.quantity > 0 else "transport-at-capacity",
                    (transport,), carrier_dependencies, capacity.to_dict(),
                    ("exact-resource-capacity",)))

            for cargo in sorted(snapshot.units, key=lambda value: value.unit_id):
                cargo_profile = profiles[cargo.unit_id]
                if (cargo_profile is None
                        or cargo_profile.unit_class not in profile.cargo_classes):
                    continue
                cargo_dependencies = self._unit_dependencies(
                    snapshot, cargo, fingerprints, ("type",))
                cargo_dependencies += (
                    self._ruleset_dependency(cargo.unit_type),)
                witness = {
                    "cargo_profile": cargo_profile.to_dict(),
                    "carrier_profile": profile_witness,
                }
                records.append(self._record(
                    scope, "transport-cargo-compatible",
                    (transport, EntityRef("unit", str(cargo.unit_id))),
                    carrier_dependencies + cargo_dependencies, witness,
                    ("compiled-ruleset-profile",)))
                if cargo_profile.founder_capable:
                    records.append(self._record(
                        scope, "unit-ruleset-founder-capable",
                        (EntityRef("unit", str(cargo.unit_id)),),
                        cargo_dependencies, cargo_profile.to_dict(),
                        ("compiled-ruleset-profile",)))
                    records.append(self._record(
                        scope, "transport-compatible-founder",
                        (transport, EntityRef("unit", str(cargo.unit_id))),
                        carrier_dependencies + cargo_dependencies, witness,
                        ("compiled-ruleset-profile",)))

            for cargo in sorted(snapshot.units, key=lambda value: value.unit_id):
                if (cargo.transported is True
                        and cargo.transported_by == carrier.unit_id):
                    dependencies = carrier_dependencies + (
                        *self._unit_dependencies(
                            snapshot, cargo, fingerprints,
                            ("transported", "transported_by")),)
                    records.append(self._record(
                        scope, "unit-carried-by",
                        (EntityRef("unit", str(cargo.unit_id)), transport),
                        dependencies, cargo.grounded_dict(),
                        ("authoritative-own-unit-state",)))

        for (carrier_id, cargo_id, mode, action, action_key,
             dependencies, _profile) in self._legal_edges(
                 snapshot, carriers, profiles, fingerprints):
            scope = scope_by_id[carrier_id]
            action_ref = EntityRef(
                "action", "legal-" + structural_hash(action_key)[:24])
            records.append(self._record(
                scope, "transport-current-{}-action".format(mode),
                (scope.root_entities[0], EntityRef("unit", str(cargo_id)),
                 action_ref), dependencies,
                {"action": action, "action_key": action_key,
                 "carrier_unit_id": carrier_id, "mode": mode},
                ("server-advertised-action",)))
        return tuple(sorted(records, key=lambda value: value.atom_id))
