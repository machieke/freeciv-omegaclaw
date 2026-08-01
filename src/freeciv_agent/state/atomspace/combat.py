"""Conservative current-revision FDAS combat and task-force scopes."""

import json
from dataclasses import replace

from ...events.schema import structural_hash
from ...planning.combat_operations import CombatOperationAssembler
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


def _spec(predicate, arguments, scopes):
    return PredicateSpec(
        predicate, len(arguments), tuple(tuple(value) for value in arguments),
        frozenset((AtomNamespace.DERIVED,)), "crisp", frozenset(scopes),
        "explicit-witness", "parent-summary", "1.0")


def combat_predicate_registry():
    engagement = ("combat-engagement",)
    task_force = ("task-force",)
    return legacy_predicate_registry().extended((
        _spec("combat-engagement-actor", (
            ("combat-engagement",), ("unit",)), engagement),
        _spec("combat-engagement-target-tile", (
            ("combat-engagement",), ("tile",)), engagement),
        _spec("combat-engagement-visible-target", (
            ("combat-engagement",), ("unit",)), engagement),
        _spec("combat-action-probability-bounded", (
            ("combat-engagement",), ("action-type",)), engagement),
        _spec("combat-action-probability-unknown", (
            ("combat-engagement",), ("action-type",)), engagement),
        _spec("combat-outcome-partition", (
            ("combat-engagement",), ("action-type",)), engagement),
        _spec("combat-interval-unknown-mass-retained", (
            ("combat-engagement",), ("action-type",)), engagement),
        _spec("combat-current-legal-action", (
            ("combat-engagement",), ("action",)), engagement),
        _spec("task-force-participant", (
            ("task-force",), ("unit",)), task_force),
        _spec("task-force-primary-attacker", (
            ("task-force",), ("unit",)), task_force),
        _spec("task-force-conditional-attacker", (
            ("task-force",), ("unit",)), task_force),
        _spec("task-force-target-unit", (
            ("task-force",), ("unit",)), task_force),
        _spec("task-force-target-tile", (
            ("task-force",), ("tile",)), task_force),
        _spec("task-force-current-operation", (
            ("task-force",), ("operation",)), task_force),
        _spec("task-force-outcome-partition", (
            ("task-force",),), task_force),
    ))


class CombatTaskForceProjector(object):
    """Project native intervals and already-grounded conditional pairs."""

    projector_id = "fdas-combat-task-force-projector"
    version = "1.0"

    def __init__(self, ruleset_ir, ruleset_digest):
        if ruleset_ir is None:
            raise ValueError("combat projection requires ruleset IR")
        if not isinstance(ruleset_digest, str) or not ruleset_digest:
            raise ValueError("combat projection requires ruleset digest")
        self.ruleset_ir = ruleset_ir
        self.ruleset_digest = ruleset_digest
        self.predicate_registry = combat_predicate_registry()

    @property
    def _ruleset_dependency(self):
        key = DependencyKey(
            "ruleset-digest", self.ruleset_digest,
            "combat-material-model")
        return DependencyRef(key, structural_hash({
            "model": "grounded-terminal-material/1.0",
            "ruleset_digest": self.ruleset_digest,
        }))

    def extend_fingerprints(self, fingerprints):
        result = dict(fingerprints)
        dependency = self._ruleset_dependency
        result[dependency.key] = dependency.fingerprint
        return result

    @staticmethod
    def _engagement_id(probability):
        return "actor:{}:tile:{}".format(
            probability.actor_unit_id, probability.target_tile_id)

    def _assemblies(self, snapshot):
        return CombatOperationAssembler().assemble(
            snapshot, self.ruleset_digest, ruleset_ir=self.ruleset_ir)

    def scopes(self, snapshot):
        world, empire = snapshot_scopes(snapshot)
        scopes = [world, empire]
        prefix = empire.scope_id.rsplit(":empire", 1)[0]
        engagement_predicates = tuple(sorted(
            value for value in self.predicate_registry.predicates
            if value.startswith("combat-")))
        for probability in snapshot.combat_probabilities:
            engagement_id = self._engagement_id(probability)
            scopes.append(ScopeSpec(
                "{}:combat-engagement:{}".format(prefix, engagement_id),
                "combat-engagement", snapshot.player_id,
                (EntityRef("combat-engagement", engagement_id),),
                (empire.scope_id,),
                ("owns-unit", "visible-enemy-at"), engagement_predicates,
                frozenset((AtomNamespace.DERIVED,)), 100, 25, 25, 1,
                "snapshot-revision", empire.validity))
        task_predicates = tuple(sorted(
            value for value in self.predicate_registry.predicates
            if value.startswith("task-force-")))
        task_validity = replace(
            empire.validity, ruleset_digest=self.ruleset_digest)
        for assembly in self._assemblies(snapshot):
            scopes.append(ScopeSpec(
                "{}:task-force:{}".format(
                    prefix, assembly.spec.operation_id),
                "task-force", snapshot.player_id,
                (EntityRef("task-force", assembly.spec.operation_id),),
                (empire.scope_id,),
                ("owns-unit", "visible-enemy-at"), task_predicates,
                frozenset((AtomNamespace.DERIVED,)), 100, 25, 25, 2,
                "snapshot-and-ruleset-revision", task_validity))
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
            tags=(("domain", "combat"),), truth_hash=_CRISP_HASH)

    @staticmethod
    def _probability_dependencies(probability, fingerprints):
        prefix = "combat_probabilities.{}:{}".format(
            probability.actor_unit_id, probability.target_tile_id)
        return tuple(DependencyRef(key, value)
                     for key, value in sorted(fingerprints.items())
                     if key.path == prefix + ".__exists__"
                     or key.path.startswith(prefix + "."))

    @staticmethod
    def _target(probability, snapshot):
        target_id = probability.target_unit_id
        if target_id == 0 and len(probability.target_unit_ids) == 1:
            target_id = probability.target_unit_ids[0]
        target = snapshot.visible_enemy_unit(target_id)
        if target is None or target.tile != probability.target_tile_id:
            return None
        return target

    @staticmethod
    def _legal_attack(probability, snapshot, fingerprints):
        rows = []
        for action_key in snapshot.legal_action_json:
            action = json.loads(action_key)
            target = action.get("target")
            if (action.get("action_type") == "unit_attack"
                    and action.get("actor_id") == probability.actor_unit_id
                    and isinstance(target, dict)
                    and snapshot.map_width > 0
                    and target.get("x") is not None
                    and target.get("y") is not None
                    and target["x"] + target["y"] * snapshot.map_width
                    == probability.target_tile_id):
                rows.append((action, action_key))
        if len(rows) != 1:
            return None
        return rows[0] + (snapshot_dependency_ref(
            snapshot, "legal_actions.{}".format(
                structural_hash(rows[0][1])), fingerprints),)

    @staticmethod
    def _partition(row):
        lower = row.lower_probability
        upper = row.upper_probability
        return {
            "failure_lower_probability": 1.0 - upper,
            "native_interval": row.to_dict(),
            "residual_unknown_mass": upper - lower,
            "success_lower_probability": lower,
            "total_probability": 1.0,
        }

    def project(self, snapshot, scopes, fingerprints):
        engagement_scopes = dict(
            (value.root_entities[0].entity_id, value)
            for value in scopes if value.scope_kind == "combat-engagement")
        task_scopes = dict(
            (value.root_entities[0].entity_id, value)
            for value in scopes if value.scope_kind == "task-force")
        records = []
        for probability in snapshot.combat_probabilities:
            engagement_id = self._engagement_id(probability)
            scope = engagement_scopes[engagement_id]
            engagement = scope.root_entities[0]
            actor = EntityRef("unit", str(probability.actor_unit_id))
            dependencies = self._probability_dependencies(
                probability, fingerprints)
            actor_dependencies = dependencies + (
                snapshot_dependency_ref(
                    snapshot, "units.{}.__exists__".format(
                        probability.actor_unit_id), fingerprints),)
            records.append(self._record(
                scope, "combat-engagement-actor", (engagement, actor),
                actor_dependencies, probability.to_dict(),
                ("freeciv-server-action-probability",)))
            records.append(self._record(
                scope, "combat-engagement-target-tile",
                (engagement, EntityRef(
                    "tile", str(probability.target_tile_id))),
                dependencies, probability.to_dict(),
                ("freeciv-server-action-probability",)))
            target = self._target(probability, snapshot)
            if target is not None:
                target_dependencies = dependencies + (
                    snapshot_dependency_ref(
                        snapshot,
                        "visible_enemy_units.{}.__exists__".format(
                            target.unit_id), fingerprints),
                    snapshot_dependency_ref(
                        snapshot,
                        "visible_enemy_units.{}.tile".format(target.unit_id),
                        fingerprints),
                )
                records.append(self._record(
                    scope, "combat-engagement-visible-target",
                    (engagement, EntityRef("unit", str(target.unit_id))),
                    target_dependencies, target.grounded_dict(),
                    ("packet-visible-enemy",)))
                legal = self._legal_attack(
                    probability, snapshot, fingerprints)
                if legal is not None:
                    records.append(self._record(
                        scope, "combat-current-legal-action",
                        (engagement, EntityRef(
                            "action", "legal-" +
                            structural_hash(legal[1])[:24])),
                        target_dependencies + (legal[2],),
                        {"action": legal[0], "action_key": legal[1]},
                        ("server-advertised-action",)))
            for row in probability.action_probabilities:
                action_type = SymbolRef("action-type", row.action_name)
                if row.status != "bounded":
                    records.append(self._record(
                        scope, "combat-action-probability-unknown",
                        (engagement, action_type), dependencies,
                        row.to_dict(),
                        ("freeciv-server-action-probability",)))
                    continue
                partition = self._partition(row)
                records.append(self._record(
                    scope, "combat-action-probability-bounded",
                    (engagement, action_type), dependencies, row.to_dict(),
                    ("freeciv-server-action-probability",)))
                records.append(self._record(
                    scope, "combat-outcome-partition",
                    (engagement, action_type), dependencies, partition,
                    ("interval-residual-preserved",)))
                if partition["residual_unknown_mass"] > 0.0:
                    records.append(self._record(
                        scope, "combat-interval-unknown-mass-retained",
                        (engagement, action_type), dependencies, partition,
                        ("interval-residual-preserved",)))

        probability_by_actor = dict(
            (value.actor_unit_id, value)
            for value in snapshot.combat_probabilities)
        for assembly in self._assemblies(snapshot):
            scope = task_scopes[assembly.spec.operation_id]
            task_force = scope.root_entities[0]
            operation = EntityRef("operation", assembly.spec.operation_id)
            dependencies = [self._ruleset_dependency]
            for participant in assembly.spec.participants:
                actor_id = int(participant.actor_id.split(":", 1)[1])
                probability = probability_by_actor[actor_id]
                dependencies.extend(self._probability_dependencies(
                    probability, fingerprints))
                dependencies.append(snapshot_dependency_ref(
                    snapshot, "units.{}.__exists__".format(actor_id),
                    fingerprints))
                action_key = assembly.action_json_by_step[
                    0 if participant.role == "primary_attacker" else 1]
                dependencies.append(snapshot_dependency_ref(
                    snapshot, "legal_actions.{}".format(
                        structural_hash(action_key)), fingerprints))
                actor = EntityRef("unit", str(actor_id))
                records.append(self._record(
                    scope, "task-force-participant",
                    (task_force, actor), tuple(dependencies),
                    participant.to_dict(), ("grounded-combat-assembly",)))
                records.append(self._record(
                    scope, "task-force-{}".format(participant.role.replace(
                        "primary_attacker", "primary-attacker").replace(
                            "conditional_attacker", "conditional-attacker")),
                    (task_force, actor), tuple(dependencies),
                    participant.to_dict(), ("grounded-combat-assembly",)))
            target = snapshot.visible_enemy_unit(assembly.target_unit_id)
            dependencies.extend((
                snapshot_dependency_ref(
                    snapshot,
                    "visible_enemy_units.{}.__exists__".format(
                        assembly.target_unit_id), fingerprints),
                snapshot_dependency_ref(
                    snapshot,
                    "visible_enemy_units.{}.tile".format(
                        assembly.target_unit_id), fingerprints),
            ))
            dependencies = tuple(sorted(set(dependencies)))
            records.append(self._record(
                scope, "task-force-target-unit",
                (task_force, EntityRef("unit", str(assembly.target_unit_id))),
                dependencies, target.grounded_dict(),
                ("grounded-combat-assembly",)))
            records.append(self._record(
                scope, "task-force-target-tile",
                (task_force, EntityRef("tile", str(assembly.target_tile_id))),
                dependencies, {"target_tile_id": assembly.target_tile_id},
                ("grounded-combat-assembly",)))
            records.append(self._record(
                scope, "task-force-current-operation",
                (task_force, operation), dependencies, assembly.to_dict(),
                ("grounded-combat-assembly",)))
            interval = assembly.operation_probability_interval
            partition = {
                "failure_lower_probability": 1.0 - interval.upper,
                "interval": interval.to_dict(),
                "residual_unknown_mass": interval.upper - interval.lower,
                "success_lower_probability": interval.lower,
                "total_probability": 1.0,
            }
            records.append(self._record(
                scope, "task-force-outcome-partition", (task_force,),
                dependencies, partition,
                ("explicit-conditional-branch",
                 "interval-residual-preserved")))
        return tuple(sorted(records, key=lambda value: value.atom_id))
