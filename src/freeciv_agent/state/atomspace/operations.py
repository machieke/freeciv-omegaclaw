"""Lossless structural projection of durable operation lifecycles."""

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
        _spec("operation-current-action", (
            ("operation",), ("action",))),
        _spec("operation-current-action-legal", (
            ("operation",), ("action",))),
        _spec("operation-action-binding", (
            ("operation",), ("action-binding",))),
        _spec("operation-deadline", (
            ("operation",), ("deadline-turn",))),
        _spec("operation-requirement-set", (
            ("operation",), ("requirement-set",))),
        _spec("requirement-set-premise", (
            ("requirement-set",), ("requirement-premise",))),
        _spec("requirement-premise-role", (
            ("requirement-set",), ("requirement-premise",),
            ("premise-role",))),
        _spec("requirement-premise-blocked", (
            ("requirement-set",), ("requirement-premise",),
            ("operation-blocker",))),
        _spec("operation-resource-claim", (
            ("operation",), ("resource-claim",))),
        _spec("resource-claim-resource", (
            ("resource-claim",), ("game-resource",))),
        _spec("resource-claim-window", (
            ("resource-claim",), ("turn-window",))),
        _spec("resource-claim-hardness", (
            ("resource-claim",), ("claim-hardness",))),
        _spec("resource-claim-quantity", (
            ("resource-claim",), ("resource-quantity",))),
        _spec("resource-claim-exclusive", (
            ("resource-claim",), ("claim-exclusivity",))),
        _spec("resource-claim-window-start", (
            ("resource-claim",), ("turn",))),
        _spec("resource-claim-window-end", (
            ("resource-claim",), ("turn",))),
        _spec("game-resource-kind", (
            ("game-resource",), ("resource-kind",))),
        _spec("game-resource-owner", (
            ("game-resource",), ("resource-owner",))),
        _spec("game-resource-scope", (
            ("game-resource",), ("resource-scope",))),
        _spec("game-resource-subresource", (
            ("game-resource",), ("resource-subresource",))),
    ))


@dataclass(frozen=True)
class OperationProjectionSnapshot:
    records: tuple
    projection_hash: str
    bindings: tuple = ()
    requirement_contexts: tuple = ()


class OperationProjector(object):
    """Project an immutable observation of an OperationStore or record set."""

    projector_id = "fdas-operation-projector"
    version = "1.0"

    def __init__(self, records_source, bindings_source=None,
                 requirement_contexts_source=None):
        self.records_source = records_source
        self.bindings_source = bindings_source
        self.requirement_contexts_source = requirement_contexts_source
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
        bindings = self._bindings(records)
        contexts = self._requirement_contexts(records)
        projection_value = (
            [value.to_dict() for value in records]
            if not bindings and not contexts else {
                "bindings": [value.to_dict() for value in bindings],
                "records": [value.to_dict() for value in records],
                "requirement_contexts": [
                    value.to_dict() for value in contexts],
            })
        return OperationProjectionSnapshot(
            records,
            structural_hash(projection_value),
            bindings,
            contexts,
        )

    def _bindings(self, records=None):
        source = self.bindings_source
        if source is None:
            return ()
        if callable(source):
            source = source()
        if isinstance(source, dict):
            source = source.values()
        bindings = tuple(source)
        required = (
            "action", "action_key", "binding_hash", "legal_actions_digest",
            "legal_bound", "operation_id", "snapshot_id", "to_dict")
        if any(any(not hasattr(value, name) for name in required)
               for value in bindings):
            raise TypeError("operation projection binding is invalid")
        operation_ids = {
            value.spec.operation_id for value in (records or self._records())}
        if any(value.operation_id not in operation_ids for value in bindings):
            raise ValueError("operation binding names an unknown operation")
        if len({value.operation_id for value in bindings}) != len(bindings):
            raise ValueError("operation projection bindings must be unique")
        return tuple(sorted(bindings, key=lambda value: value.operation_id))

    def _requirement_contexts(self, records=None):
        source = self.requirement_contexts_source
        if source is None:
            return ()
        if callable(source):
            source = source()
        if isinstance(source, dict):
            source = source.values()
        contexts = tuple(source)
        required = (
            "blocked_premises", "context_hash", "operation_id",
            "requirement_set", "resource_claims", "snapshot_id", "to_dict")
        if any(any(not hasattr(value, name) for name in required)
               for value in contexts):
            raise TypeError("operation requirement context is invalid")
        operation_ids = {
            value.spec.operation_id for value in (records or self._records())}
        if any(value.operation_id not in operation_ids for value in contexts):
            raise ValueError(
                "operation requirement context names an unknown operation")
        if len({value.operation_id for value in contexts}) != len(contexts):
            raise ValueError(
                "operation requirement contexts must be unique")
        for context in contexts:
            material = {
                "blocked_premises": dict(context.blocked_premises),
                "operation_id": context.operation_id,
                "requirement_set": context.requirement_set.to_dict(),
                "resource_claims": [
                    value.to_dict() for value in context.resource_claims],
                "snapshot_id": context.snapshot_id,
            }
            if structural_hash(material) != context.context_hash:
                raise ValueError(
                    "operation requirement context hash is invalid")
        return tuple(sorted(contexts, key=lambda value: value.operation_id))

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
                    if value.startswith((
                        "game-resource-", "operation-", "requirement-",
                        "resource-")))),
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
        records = self._records()
        for record in records:
            for path in ("spec", "progress"):
                dependency = self._dependency(record, path)
                result[dependency.key] = dependency.fingerprint
        for binding in self._bindings(records):
            key = DependencyKey(
                "operation-binding", binding.operation_id, "current")
            result[key] = structural_hash(binding.to_dict())
        for context in self._requirement_contexts(records):
            key = DependencyKey(
                "operation-requirements", context.operation_id, "current")
            result[key] = structural_hash(context.to_dict())
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
        records = self._records()
        bindings = dict(
            (value.operation_id, value)
            for value in self._bindings(records))
        contexts = dict(
            (value.operation_id, value)
            for value in self._requirement_contexts(records))
        scope_by_operation = dict(
            (value.root_entities[0].entity_id, value)
            for value in scopes if value.scope_kind == "operation")
        result = []
        for record in records:
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
            add("operation-deadline", (
                operation,
                SymbolRef("deadline-turn", str(spec.expiry_turn))),
                (spec_dependency,), {"expiry_turn": spec.expiry_turn})
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
            context = contexts.get(spec.operation_id)
            if context is not None:
                context_dependency = DependencyRef(
                    DependencyKey(
                        "operation-requirements", spec.operation_id,
                        "current"),
                    structural_hash(context.to_dict()))
                if fingerprints.get(context_dependency.key) != (
                        context_dependency.fingerprint):
                    raise ValueError(
                        "operation requirements changed during revision")
                # Requirement evaluations and current claims are scoped to the
                # exact snapshot in which they were grounded. A stale context
                # is omitted, never converted into a negative fact.
                if context.snapshot_id == snapshot.snapshot_id:
                    requirement_set = context.requirement_set
                    requirement_ref = EntityRef(
                        "requirement-set",
                        requirement_set.requirement_set_id)
                    add("operation-requirement-set", (
                        operation, requirement_ref),
                        (context_dependency,), requirement_set.to_dict(),
                        lifecycle=progress.state.value)
                    blocked = dict(context.blocked_premises)
                    for premise_id, role_id in zip(
                            requirement_set.premise_ids,
                            requirement_set.role_ids):
                        premise_ref = EntityRef(
                            "requirement-premise", premise_id)
                        add("requirement-set-premise", (
                            requirement_ref, premise_ref),
                            (context_dependency,), requirement_set.to_dict(),
                            lifecycle=progress.state.value)
                        add("requirement-premise-role", (
                            requirement_ref, premise_ref,
                            SymbolRef("premise-role", role_id)),
                            (context_dependency,), requirement_set.to_dict(),
                            lifecycle=progress.state.value)
                        if premise_id in blocked:
                            add("requirement-premise-blocked", (
                                requirement_ref, premise_ref,
                                SymbolRef(
                                    "operation-blocker",
                                    blocked[premise_id])),
                                (context_dependency,), {
                                    "blocker": blocked[premise_id],
                                    "premise_id": premise_id,
                                }, lifecycle="blocked")
                    for claim in sorted(
                            context.resource_claims,
                            key=lambda value: value.sort_key):
                        claim_ref = EntityRef(
                            "resource-claim", claim.claim_id)
                        resource_ref = EntityRef(
                            "game-resource", claim.resource.resource_id)
                        window_ref = EntityRef(
                            "turn-window", structural_hash(
                                claim.window.to_dict()))
                        witness = claim.to_dict()
                        add("operation-resource-claim", (
                            operation, claim_ref),
                            (context_dependency,), witness,
                            lifecycle=progress.state.value)
                        add("resource-claim-resource", (
                            claim_ref, resource_ref),
                            (context_dependency,), witness,
                            lifecycle=progress.state.value)
                        add("resource-claim-window", (
                            claim_ref, window_ref),
                            (context_dependency,), witness,
                            lifecycle=progress.state.value)
                        add("resource-claim-hardness", (
                            claim_ref,
                            SymbolRef(
                                "claim-hardness", claim.hardness.value)),
                            (context_dependency,), witness,
                            lifecycle=progress.state.value)
                        add("resource-claim-quantity", (
                            claim_ref,
                            SymbolRef(
                                "resource-quantity", str(claim.quantity))),
                            (context_dependency,), witness,
                            lifecycle=progress.state.value)
                        add("resource-claim-exclusive", (
                            claim_ref,
                            SymbolRef(
                                "claim-exclusivity",
                                "exclusive" if claim.exclusive else "shared")),
                            (context_dependency,), witness,
                            lifecycle=progress.state.value)
                        add("resource-claim-window-start", (
                            claim_ref,
                            SymbolRef(
                                "turn", str(claim.window.start_turn))),
                            (context_dependency,), witness,
                            lifecycle=progress.state.value)
                        add("resource-claim-window-end", (
                            claim_ref,
                            SymbolRef(
                                "turn", str(
                                    claim.window.end_turn_exclusive))),
                            (context_dependency,), witness,
                            lifecycle=progress.state.value)
                        add("game-resource-kind", (
                            resource_ref,
                            SymbolRef(
                                "resource-kind", claim.resource.kind.value)),
                            (context_dependency,), witness,
                            lifecycle=progress.state.value)
                        add("game-resource-owner", (
                            resource_ref,
                            SymbolRef(
                                "resource-owner", claim.resource.owner_id)),
                            (context_dependency,), witness,
                            lifecycle=progress.state.value)
                        add("game-resource-scope", (
                            resource_ref,
                            SymbolRef(
                                "resource-scope", claim.resource.scope)),
                            (context_dependency,), witness,
                            lifecycle=progress.state.value)
                        if claim.resource.subresource is not None:
                            add("game-resource-subresource", (
                                resource_ref,
                                SymbolRef(
                                    "resource-subresource",
                                    claim.resource.subresource)),
                                (context_dependency,), witness,
                                lifecycle=progress.state.value)
            binding = bindings.get(spec.operation_id)
            if binding is None:
                continue
            binding_dependency = DependencyRef(
                DependencyKey(
                    "operation-binding", spec.operation_id, "current"),
                structural_hash(binding.to_dict()))
            if fingerprints.get(binding_dependency.key) != (
                    binding_dependency.fingerprint):
                raise ValueError(
                    "operation action binding changed during revision")
            # A stale/blocked binding is a control input, never a current legal
            # relation. Fail closed without converting it into a negative fact.
            if (not binding.legal_bound
                    or binding.snapshot_id != snapshot.snapshot_id
                    or binding.legal_actions_digest
                    != snapshot.legal_actions_digest
                    or binding.action_key not in snapshot.legal_action_json):
                continue
            action_ref = EntityRef(
                "action", "legal-" + structural_hash(
                    binding.action_key)[:24])
            legal_dependency = snapshot_dependency_ref(
                snapshot,
                "legal_actions.{}".format(structural_hash(
                    binding.action_key)), fingerprints)
            add("operation-current-action", (
                operation, action_ref),
                (binding_dependency,), binding.to_dict(),
                lifecycle=progress.state.value)
            add("operation-current-action-legal", (
                operation, action_ref),
                (binding_dependency, legal_dependency), binding.to_dict(),
                lifecycle=progress.state.value)
            add("operation-action-binding", (
                operation,
                SymbolRef("action-binding", binding.binding_hash)),
                (binding_dependency, legal_dependency), binding.to_dict(),
                lifecycle=progress.state.value)
        return tuple(sorted(result, key=lambda value: value.atom_id))
