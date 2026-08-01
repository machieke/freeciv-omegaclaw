"""Lossless structural projection of durable operation lifecycles."""

from dataclasses import dataclass

from ...events.schema import structural_hash
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


_STRUCTURAL = {"structural": True}
_STRUCTURAL_HASH = structural_hash(_STRUCTURAL)
_ACTOR_KINDS = (
    "city", "player", "research_slot", "task-force", "transport", "unit")


def _spec(predicate, arguments):
    return PredicateSpec(
        predicate,
        len(arguments),
        tuple(tuple(value) for value in arguments),
        frozenset((AtomNamespace.OPERATION,)),
        "structural",
        frozenset(("operation",)),
        "explicit-witness",
        "parent-summary",
        "1.0",
    )


def operation_predicate_registry():
    actor = _ACTOR_KINDS
    return legacy_predicate_registry().extended((
        _spec("operation-type", (("operation",), ("operation-type",))),
        _spec("operation-serves-goal", (("operation",), ("goal",))),
        _spec("operation-participant", (("operation",), actor)),
        _spec("operation-participant-role", (
            ("operation",), actor, ("operation-role",))),
        _spec("operation-target", (
            ("operation",), ("operation-target",))),
        _spec("operation-step", (
            ("operation",), ("operation-step",))),
        _spec("operation-current-step", (
            ("operation",), ("operation-step",))),
        _spec("operation-step-action", (
            ("operation-step",), ("action-type",))),
        _spec("operation-step-requires", (
            ("operation-step",), ("requirement-set",))),
        _spec("operation-step-completes", (
            ("operation-step",), ("completion-predicate",))),
        _spec("operation-state", (
            ("operation",), ("operation-state",))),
        _spec("operation-blocked-reason", (
            ("operation",), ("operation-blocker",))),
        _spec("operation-terminal-reason", (
            ("operation",), ("operation-terminal-reason",))),
        _spec("operation-ruleset", (
            ("operation",), ("ruleset-digest",))),
        _spec("operation-specification", (
            ("operation",), ("operation-spec-digest",))),
    ))


@dataclass(frozen=True)
class OperationProjectionSnapshot:
    records: tuple
    projection_hash: str


class OperationProjector(object):
    """Project an immutable observation of an OperationStore or record set."""

    projector_id = "fdas-operation-projector"
    version = "1.0"

    def __init__(self, records_source):
        self.records_source = records_source
        self.predicate_registry = operation_predicate_registry()

    def _records(self):
        # Import lazily: planning's public facade also exports FDAS helpers.
        # Keeping this edge out of module initialization prevents a package
        # import cycle without weakening the concrete record validation.
        from ...planning.operation_store import OperationRecord, OperationStore

        source = self.records_source
        if callable(source):
            source = source()
        if isinstance(source, OperationStore):
            if source.quarantined:
                raise ValueError("quarantined operation store cannot project")
            source = source.records()
        records = tuple(source)
        if any(not isinstance(value, OperationRecord) for value in records):
            raise TypeError("operation projection requires OperationRecord values")
        operation_ids = [value.spec.operation_id for value in records]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("operation projection IDs must be unique")
        return tuple(sorted(records, key=lambda value: value.spec.operation_id))

    def projection_snapshot(self):
        records = self._records()
        return OperationProjectionSnapshot(
            records,
            structural_hash([value.to_dict() for value in records]),
        )

    def scopes(self, snapshot):
        world, empire = snapshot_scopes(snapshot)
        result = [world, empire]
        for record in self._records():
            operation = EntityRef("operation", record.spec.operation_id)
            result.append(ScopeSpec(
                "{}:operation:{}".format(
                    empire.scope_id.rsplit(":empire", 1)[0],
                    record.spec.operation_id),
                "operation",
                snapshot.player_id,
                (operation,),
                (empire.scope_id,),
                (),
                tuple(sorted(
                    value for value in self.predicate_registry.predicates
                    if value.startswith("operation-"))),
                frozenset((AtomNamespace.OPERATION,)),
                250,
                250,
                100,
                2,
                "operation-lifecycle",
                empire.validity,
            ))
        return tuple(result)

    @staticmethod
    def _dependency(record, path):
        value = (
            record.spec.to_dict()
            if path == "spec" else record.progress.to_dict())
        return DependencyRef(
            DependencyKey(
                "operation-revision", record.spec.operation_id, path),
            structural_hash(value),
        )

    def extend_fingerprints(self, fingerprints):
        result = dict(fingerprints)
        for record in self._records():
            for path in ("spec", "progress"):
                dependency = self._dependency(record, path)
                result[dependency.key] = dependency.fingerprint
        return result

    def _record(self, scope, predicate, arguments, dependencies, witness,
                lifecycle="projected", provenance=()):
        key = AtomKey(
            AtomNamespace.OPERATION, predicate, tuple(arguments),
            scope.scope_id)
        support = SupportRecord.create(
            self.projector_id,
            self.version,
            key.to_dict(),
            tuple(dependencies),
            witness,
            (self.projector_id,) + tuple(provenance),
        )
        return AtomRecord.create(
            key,
            AuthorityClass.CONTROL_MODEL,
            _STRUCTURAL,
            scope.validity,
            (support,),
            (self.projector_id,) + tuple(provenance),
            lifecycle=lifecycle,
            tags=(("domain", "operation-lifecycle"),),
            truth_hash=_STRUCTURAL_HASH,
        )

    def project(self, snapshot, scopes, fingerprints):
        scope_by_operation = dict(
            (value.root_entities[0].entity_id, value)
            for value in scopes if value.scope_kind == "operation")
        result = []
        for record in self._records():
            spec = record.spec
            progress = record.progress
            scope = scope_by_operation[spec.operation_id]
            operation = EntityRef("operation", spec.operation_id)
            spec_dependency = self._dependency(record, "spec")
            progress_dependency = self._dependency(record, "progress")
            expected = {
                spec_dependency.key: spec_dependency.fingerprint,
                progress_dependency.key: progress_dependency.fingerprint,
            }
            for key, fingerprint in expected.items():
                if fingerprints.get(key) != fingerprint:
                    raise ValueError(
                        "operation projection source changed during revision")

            def add(predicate, arguments, dependencies, witness,
                    lifecycle="projected"):
                result.append(self._record(
                    scope, predicate, arguments, dependencies, witness,
                    lifecycle=lifecycle, provenance=spec.provenance))

            add("operation-type", (
                operation,
                SymbolRef("operation-type", spec.operation_type)),
                (spec_dependency,), {"operation_type": spec.operation_type})
            add("operation-specification", (
                operation,
                SymbolRef("operation-spec-digest", spec.spec_digest)),
                (spec_dependency,), {"spec_digest": spec.spec_digest})
            add("operation-ruleset", (
                operation,
                SymbolRef("ruleset-digest", spec.ruleset_digest)),
                (spec_dependency,), {"ruleset_digest": spec.ruleset_digest})
            if spec.target_ref is not None:
                add("operation-target", (
                    operation,
                    SymbolRef("operation-target", spec.target_ref)),
                    (spec_dependency,), {"target_ref": spec.target_ref})
            for goal_id in sorted(spec.goal_ids):
                add("operation-serves-goal", (
                    operation, EntityRef("goal", goal_id)),
                    (spec_dependency,), {"goal_id": goal_id})
            actors = {}
            for participant in sorted(
                    spec.participants,
                    key=lambda value: (value.role, value.actor_id)):
                actor = EntityRef(
                    participant.actor_class, participant.actor_id)
                actors[participant.role] = actor
                add("operation-participant", (operation, actor),
                    (spec_dependency,), participant.to_dict())
                add("operation-participant-role", (
                    operation, actor,
                    SymbolRef("operation-role", participant.role)),
                    (spec_dependency,), participant.to_dict())
            step_refs = []
            for step in spec.steps:
                step_ref = EntityRef("operation-step", step.step_id)
                step_refs.append(step_ref)
                add("operation-step", (operation, step_ref),
                    (spec_dependency,), step.to_dict())
                add("operation-step-action", (
                    step_ref, SymbolRef("action-type", step.action_type)),
                    (spec_dependency,), step.to_dict())
                add("operation-step-requires", (
                    step_ref,
                    SymbolRef("requirement-set", step.requirement_set_id)),
                    (spec_dependency,), step.to_dict())
                add("operation-step-completes", (
                    step_ref,
                    SymbolRef(
                        "completion-predicate",
                        step.completion_predicate_id)),
                    (spec_dependency,), step.to_dict())
            add("operation-state", (
                operation,
                SymbolRef("operation-state", progress.state.value)),
                (progress_dependency,), progress.to_dict(),
                lifecycle=progress.state.value)
            if progress.current_step_index < len(step_refs):
                add("operation-current-step", (
                    operation, step_refs[progress.current_step_index]),
                    (spec_dependency, progress_dependency),
                    progress.to_dict(), lifecycle=progress.state.value)
            if progress.blocked_reason:
                add("operation-blocked-reason", (
                    operation,
                    SymbolRef(
                        "operation-blocker", progress.blocked_reason)),
                    (progress_dependency,), progress.to_dict(),
                    lifecycle="blocked")
            if progress.terminal_reason:
                add("operation-terminal-reason", (
                    operation,
                    SymbolRef(
                        "operation-terminal-reason",
                        progress.terminal_reason)),
                    (progress_dependency,), progress.to_dict(),
                    lifecycle=progress.state.value)
        return tuple(sorted(result, key=lambda value: value.atom_id))
