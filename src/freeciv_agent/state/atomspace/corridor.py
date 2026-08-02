"""Bounded FDAS scopes for exact current native route corridors."""

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
    SymbolRef,
)
from .predicates import PredicateSpec, legacy_predicate_registry
from .scopes import ScopeSpec, snapshot_scopes


_CRISP = {"confidence": 1.0, "crisp": True, "strength": 1.0}
_CRISP_HASH = structural_hash(_CRISP)


def _spec(predicate, arguments):
    return PredicateSpec(
        predicate,
        len(arguments),
        tuple(tuple(value) for value in arguments),
        frozenset((AtomNamespace.DERIVED,)),
        "crisp",
        frozenset(("route-corridor",)),
        "explicit-witness",
        "parent-summary",
        "1.0",
    )


def route_corridor_predicate_registry():
    return legacy_predicate_registry().extended((
        _spec("route-corridor-for", (
            ("route-corridor",), ("unit",))),
        _spec("route-corridor-origin", (
            ("route-corridor",), ("tile",))),
        _spec("route-corridor-destination", (
            ("route-corridor",), ("tile",))),
        _spec("route-corridor-first-step", (
            ("route-corridor",), ("tile",))),
        _spec("route-corridor-reachable", (("route-corridor",),)),
        _spec("route-corridor-visibility", (
            ("route-corridor",), ("visibility-status",))),
        _spec("route-corridor-current-legal-step", (
            ("route-corridor",), ("action",))),
    ))


class RouteCorridorProjector(object):
    """Project no more than one exact scope per advertised reachable route."""

    projector_id = "fdas-route-corridor-projector"
    version = "1.0"
    incremental_dependency_roots = frozenset((
        "legal_actions", "map_tiles", "map_width", "movement_routes",
        "player_id", "source_seq", "turn", "units", "visible_tile_ids",
    ))
    incremental_dependency_kinds = frozenset()

    def __init__(self):
        self.predicate_registry = route_corridor_predicate_registry()

    @staticmethod
    def _corridors(snapshot):
        rows = []
        for route in snapshot.movement_routes:
            if not route.reachable:
                continue
            corridor = native_route_corridor(
                snapshot, route.unit_id, route.destination_tile)
            rows.append((route, corridor))
        return tuple(sorted(
            rows,
            key=lambda value: (
                value[0].unit_id, value[0].destination_tile)))

    def scopes(self, snapshot):
        world, empire = snapshot_scopes(snapshot)
        scopes = [world, empire]
        prefix = empire.scope_id.rsplit(":empire", 1)[0]
        predicates = tuple(sorted(
            value for value in self.predicate_registry.predicates
            if value.startswith("route-corridor-")))
        for _route, corridor in self._corridors(snapshot):
            corridor_ref = EntityRef(
                "route-corridor", corridor.corridor_digest)
            scopes.append(ScopeSpec(
                "{}:route-corridor:{}".format(
                    prefix, corridor.corridor_digest),
                "route-corridor",
                snapshot.player_id,
                (corridor_ref,),
                (empire.scope_id,),
                ("owns-unit", "unit-at"),
                predicates,
                frozenset((AtomNamespace.DERIVED,)),
                50,
                0,
                20,
                1,
                "snapshot-revision",
                empire.validity,
            ))
        return tuple(scopes)

    @staticmethod
    def extend_fingerprints(fingerprints):
        return dict(fingerprints)

    @staticmethod
    def _route_dependencies(snapshot, route, fingerprints):
        prefix = "movement_routes.{}:{}".format(
            route.unit_id, route.destination_tile)
        paths = (
            "source_seq",
            "units.{}.__exists__".format(route.unit_id),
            "units.{}.tile".format(route.unit_id),
            prefix + ".authority",
            prefix + ".destination_tile",
            prefix + ".estimated_turns",
            prefix + ".first_step_movement_cost",
            prefix + ".first_step_tile",
            prefix + ".origin_tile",
            prefix + ".path_directions",
            prefix + ".path_length",
            prefix + ".reachable",
            prefix + ".schema_version",
            prefix + ".source_seq",
            prefix + ".total_movement_cost",
            prefix + ".turn",
        )
        return tuple(
            snapshot_dependency_ref(snapshot, value, fingerprints)
            for value in paths)

    @staticmethod
    def _legal_steps(snapshot, fingerprints):
        """Index canonical move bindings once for all route corridors."""
        matches = {}
        for action_key in snapshot.legal_action_json:
            action = json.loads(action_key)
            target = action.get("target")
            if (action.get("action_type") == "unit_move"
                    and isinstance(target, dict)
                    and None not in (target.get("x"), target.get("y"))):
                identity = (
                    int(action.get("actor_id", -1)),
                    int(target["x"]), int(target["y"]))
                matches.setdefault(identity, []).append((
                    action_key,
                    snapshot_dependency_ref(
                        snapshot,
                        "legal_actions.{}".format(
                            structural_hash(action_key)),
                        fingerprints)))
        return dict(
            (key, values[0] if len(values) == 1 else None)
            for key, values in matches.items())

    def _record(self, scope, predicate, arguments, dependencies, witness,
                support=None):
        key = AtomKey(
            AtomNamespace.DERIVED, predicate, tuple(arguments), scope.scope_id)
        support = support or SupportRecord.create(
            self.projector_id, self.version, key.to_dict(), dependencies,
            witness, (self.projector_id, "freeciv-server-pathfinder"))
        return AtomRecord.create(
            key, AuthorityClass.DETERMINISTIC_DERIVED, _CRISP,
            scope.validity, (support,),
            (self.projector_id, "freeciv-server-pathfinder"),
            tags=(("domain", "route-corridor"),),
            truth_hash=_CRISP_HASH)

    def project(self, snapshot, scopes, fingerprints):
        scope_by_corridor = dict(
            (value.root_entities[0].entity_id, value)
            for value in scopes if value.scope_kind == "route-corridor")
        records = []
        legal_steps = self._legal_steps(snapshot, fingerprints)
        for route, corridor in self._corridors(snapshot):
            scope = scope_by_corridor[corridor.corridor_digest]
            corridor_ref = scope.root_entities[0]
            dependencies = self._route_dependencies(
                snapshot, route, fingerprints)
            witness = corridor.to_dict()
            route_support = SupportRecord.create(
                self.projector_id, self.version,
                {"corridor_digest": corridor.corridor_digest},
                dependencies, witness,
                (self.projector_id, "freeciv-server-pathfinder"))

            def add(predicate, argument=None, extra_dependencies=(),
                    shared=True):
                arguments = (
                    (corridor_ref,) if argument is None
                    else (corridor_ref, argument))
                records.append(self._record(
                    scope, predicate, arguments,
                    dependencies + tuple(extra_dependencies), witness,
                    route_support if shared and not extra_dependencies else None))

            add("route-corridor-for", EntityRef("unit", str(route.unit_id)))
            add("route-corridor-origin", EntityRef(
                "tile", str(route.origin_tile)))
            add("route-corridor-destination", EntityRef(
                "tile", str(route.destination_tile)))
            add("route-corridor-first-step", EntityRef(
                "tile", str(route.first_step_tile)))
            add("route-corridor-reachable")
            add("route-corridor-visibility", SymbolRef(
                "visibility-status", corridor.visibility))
            legal = None
            if snapshot.map_width > 0:
                legal = legal_steps.get((
                    route.unit_id,
                    route.first_step_tile % snapshot.map_width,
                    route.first_step_tile // snapshot.map_width))
            if legal is not None:
                add("route-corridor-current-legal-step", EntityRef(
                    "action", "legal-" + structural_hash(
                        legal[0])[:24]), (legal[1],), shared=False)
        return tuple(sorted(records, key=lambda value: value.atom_id))
