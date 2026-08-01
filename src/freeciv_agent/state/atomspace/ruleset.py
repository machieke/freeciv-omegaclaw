"""Ruleset-exact static FDAS projection cached by compiled digest."""

import threading

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
    ValidityInterval,
)
from .predicates import PredicateRegistry, PredicateSpec
from .scopes import ScopeSpec
from .store import DependentAtomSpaceRevision
from .transaction import AtomSpaceTransaction


_ENTITY_KINDS = (
    "building-type",
    "government",
    "tech-type",
    "terrain",
    "unit-type",
)


def _spec(predicate, argument_kinds):
    return PredicateSpec(
        predicate=predicate,
        arity=len(argument_kinds),
        argument_kinds=tuple(tuple(value) for value in argument_kinds),
        namespaces=frozenset((AtomNamespace.RULESET,)),
        truth_kind="structural",
        allowed_scope_kinds=frozenset(("ruleset",)),
        completeness_policy="explicit-witness",
        export_policy="global",
        schema_version="1.0",
    )


def ruleset_predicate_registry():
    subject_kinds = _ENTITY_KINDS + (
        "action-schema", "effect", "requirement")
    return PredicateRegistry((
        _spec("action-schema", (("action-schema",), ("action-type",))),
        _spec("effect-kind", (("effect",), ("effect-kind",))),
        _spec("effect-status", (("effect",), ("effect-status",))),
        _spec("entity-kind", (_ENTITY_KINDS, ("entity-kind",))),
        _spec("grants-capability", (_ENTITY_KINDS, ("capability",))),
        _spec("grounding-authority", (
            ("grounding",), ("grounding-authority",))),
        _spec("has-role", (("unit-type",), ("role",))),
        _spec("requirement-kind", (
            ("requirement",), ("requirement-kind",))),
        _spec("requires", (subject_kinds, ("requirement",))),
        _spec("schema-actor-kind", (
            ("action-schema",), ("entity-kind",))),
        _spec("schema-claims", (
            ("action-schema",), ("resource-kind",))),
        _spec("schema-predicts", (
            ("action-schema",), ("effect",))),
        _spec("schema-requires", (
            ("action-schema",), ("requirement",))),
        _spec("schema-target-kind", (
            ("action-schema",), ("entity-kind",))),
    ))


def ruleset_digest(ir):
    return structural_hash({
        "compiler_version": ir.compiler_version,
        "ruleset": ir.ruleset,
        "semantics": ir.to_dict(),
        "source_hashes": ir.source_hashes,
    })


def ruleset_scope(ir, digest=None):
    digest = digest or ruleset_digest(ir)
    return ScopeSpec(
        scope_id="scope:ruleset:{}:{}".format(ir.ruleset, digest[:24]),
        scope_kind="ruleset",
        owner_player_id=0,
        root_entities=(EntityRef("ruleset", ir.ruleset),),
        parent_scope_ids=(),
        imported_predicates=(),
        exported_predicates=ruleset_predicate_registry().predicates,
        namespaces=frozenset((AtomNamespace.RULESET,)),
        maximum_atoms=25000,
        maximum_rule_fires=0,
        maximum_groundings=0,
        maximum_expansion_depth=0,
        retention_policy="persistent-ruleset-digest",
        validity=ValidityInterval(ruleset_digest=digest),
    )


def _dependency(digest, provenance):
    return DependencyRef(
        DependencyKey("ruleset-source", digest, str(provenance)),
        structural_hash({"provenance": provenance, "ruleset": digest}),
    )


def _record(scope, digest, predicate, arguments, provenance):
    key = AtomKey(
        AtomNamespace.RULESET,
        predicate,
        tuple(arguments),
        scope.scope_id,
    )
    dependency = _dependency(digest, provenance)
    support = SupportRecord.create(
        "ruleset-ir-projection",
        "1.0",
        key.to_dict(),
        (dependency,),
        {"atom": key.to_dict(), "provenance": provenance},
        (str(provenance),),
    )
    return AtomRecord.create(
        key,
        AuthorityClass.RULESET_EXACT,
        {"confidence": 1.0, "crisp": True, "strength": 1.0},
        scope.validity,
        (support,),
        (str(provenance),),
        tags=(("ruleset", digest),),
    )


def _entity_kind(rule_kind):
    return {
        "building": "building-type",
        "tech": "tech-type",
        "unit": "unit-type",
    }[rule_kind]


def project_ruleset_records(ir, scope=None, digest=None):
    digest = digest or ruleset_digest(ir)
    scope = scope or ruleset_scope(ir, digest)
    records = []
    for rule in ir.rules:
        kind = _entity_kind(rule.target_kind)
        entity = EntityRef(kind, rule.rule_name)
        provenance = "{}:{}".format(rule.rule_id, rule.source["line"])
        records.append(_record(
            scope, digest, "entity-kind",
            (entity, SymbolRef("entity-kind", kind)), provenance))
        root = next((
            value.expression_id for value in ir.requirement_expressions
            if value.expression_id in {
                capability.requirements for capability in ir.capabilities
                if (capability.source_entity_id == rule.rule_name
                    and capability.entity_kind == kind)
            }
        ), None)
        if root:
            records.append(_record(
                scope, digest, "requires",
                (entity, EntityRef("requirement", root)), provenance))
    for capability in ir.capabilities:
        entity = EntityRef(
            capability.entity_kind, capability.source_entity_id)
        provenance = capability.provenance[0]
        records.append(_record(
            scope, digest, "entity-kind",
            (entity, SymbolRef("entity-kind", capability.entity_kind)),
            provenance))
        records.append(_record(
            scope, digest, "grants-capability",
            (entity, EntityRef("capability", capability.capability_id)),
            provenance))
        traits = dict(capability.traits)
        if traits.get("trait-kind") == "roles":
            records.append(_record(
                scope, digest, "has-role",
                (entity, SymbolRef("role", str(traits["trait-value"]))),
                provenance))
    for expression in ir.requirement_expressions:
        requirement = EntityRef("requirement", expression.expression_id)
        provenance = "{}:requirement-expression".format(ir.compiler_version)
        records.append(_record(
            scope, digest, "requirement-kind",
            (requirement, SymbolRef("requirement-kind", expression.kind)),
            provenance))
        for child in expression.children:
            records.append(_record(
                scope, digest, "requires",
                (requirement, EntityRef("requirement", child)), provenance))
    for effect in ir.effects:
        effect_ref = EntityRef("effect", effect.effect_id)
        provenance = effect.provenance[0]
        records.append(_record(
            scope, digest, "effect-kind",
            (effect_ref, SymbolRef("effect-kind", effect.effect_kind)),
            provenance))
        records.append(_record(
            scope, digest, "effect-status",
            (effect_ref, SymbolRef(
                "effect-status", "known" if effect.known else "unknown")),
            provenance))
        if effect.requirements:
            records.append(_record(
                scope, digest, "requires",
                (effect_ref, EntityRef("requirement", effect.requirements)),
                provenance))
    for schema in ir.action_schemas:
        schema_ref = EntityRef("action-schema", schema.schema_id)
        provenance = schema.provenance[0]
        records.extend((
            _record(
                scope, digest, "action-schema",
                (schema_ref, SymbolRef("action-type", schema.action_type)),
                provenance),
            _record(
                scope, digest, "schema-actor-kind",
                (schema_ref, SymbolRef("entity-kind", schema.actor_kind)),
                provenance),
            _record(
                scope, digest, "schema-requires",
                (schema_ref, EntityRef("requirement", schema.requirements)),
                provenance),
        ))
        if schema.target_kind:
            records.append(_record(
                scope, digest, "schema-target-kind",
                (schema_ref, SymbolRef("entity-kind", schema.target_kind)),
                provenance))
        for effect_id in schema.effects:
            records.append(_record(
                scope, digest, "schema-predicts",
                (schema_ref, EntityRef("effect", effect_id)), provenance))
        for claim in schema.resource_claim_templates:
            records.append(_record(
                scope, digest, "schema-claims",
                (schema_ref, SymbolRef("resource-kind", claim["kind"])),
                provenance))
    for grounding in ir.grounding_specs:
        records.append(_record(
            scope, digest, "grounding-authority",
            (EntityRef("grounding", grounding.name), SymbolRef(
                "grounding-authority", grounding.authority)),
            "{}:grounding:1.0".format(ir.compiler_version)))
    return tuple(sorted(records, key=lambda value: (
        value.atom_id, value.materialization_key)))


class RulesetAtomSpaceStore(object):
    def __init__(self):
        self._lock = threading.RLock()
        self._revisions = {}

    def build(self, ir):
        digest = ruleset_digest(ir)
        with self._lock:
            existing = self._revisions.get(digest)
            if existing is not None:
                return existing
        scope = ruleset_scope(ir, digest)
        transaction = AtomSpaceTransaction(
            "ruleset:{}".format(digest),
            ruleset_predicate_registry(),
            (scope,),
        )
        for record in project_ruleset_records(ir, scope, digest):
            transaction.apply(record)
        revision_id = transaction.commit()
        revision = DependentAtomSpaceRevision(
            revision_id,
            "ruleset:{}".format(digest),
            transaction.records,
            transaction.scopes,
            revision_id[len("fdas-revision-"):],
            transaction.dependency_index,
        )
        with self._lock:
            current = self._revisions.get(digest)
            if current is not None and current != revision:
                raise ValueError("ruleset FDAS digest collision")
            self._revisions[digest] = revision
        return revision

    def revision(self, digest):
        with self._lock:
            return self._revisions.get(str(digest))
