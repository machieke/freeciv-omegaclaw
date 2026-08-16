"""Decision-safe amplification of captured FDAS record and index shapes."""

from dataclasses import dataclass

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.state.atomspace.model import (
    AtomKey,
    AtomNamespace,
    AtomRecord,
    AuthorityClass,
    DependencyKey,
    DependencyRef,
    EntityRef,
    SupportRecord,
    SymbolRef,
    joined_identity_hash,
)
from freeciv_agent.state.atomspace.dependencies import DependencyIndex
from freeciv_agent.state.atomspace.predicates import (
    PredicateRegistry,
    PredicateSpec,
)
from freeciv_agent.state.atomspace.scopes import ScopeSpec
from freeciv_agent.state.atomspace.transaction import AtomSpaceTransaction


@dataclass(frozen=True)
class CapturedAmplification:
    records: tuple
    scopes: tuple
    revision_id: str
    dependency_index: object
    original_record_count: int
    amplified_record_count: int
    replication_factor: int
    original_hash_before: str
    original_hash_after: str
    historical_validity_record_count: int = 0
    validation_mode: str = "same-snapshot-transaction"

    @property
    def original_subgraph_invariant(self):
        return self.original_hash_before == self.original_hash_after

    @property
    def clone_records(self):
        return tuple(
            row for row in self.records
            if row.key.scope_id.startswith("benchmark-amplified-"))


def _benchmark_registry(registry):
    if not isinstance(registry, PredicateRegistry):
        raise TypeError("captured amplification requires PredicateRegistry")
    return PredicateRegistry(tuple(PredicateSpec(
        predicate=spec.predicate,
        arity=spec.arity,
        argument_kinds=spec.argument_kinds,
        namespaces=spec.namespaces.union((AtomNamespace.DIAGNOSTIC,)),
        truth_kind=spec.truth_kind,
        allowed_scope_kinds=spec.allowed_scope_kinds,
        completeness_policy=spec.completeness_policy,
        export_policy=spec.export_policy,
        schema_version=spec.schema_version,
    ) for spec in registry.specs))


def _entity(term, replica):
    if isinstance(term, SymbolRef):
        return term
    if not isinstance(term, EntityRef):
        raise TypeError("captured terms must be typed")
    return EntityRef(
        term.kind,
        "benchmark-amplified-{:04d}:{}".format(replica, term.entity_id))


def amplify_captured_records(
        snapshot_id, records, scopes, predicate_registry,
        replication_factor):
    """Clone record motifs without cloning their epistemic/action authority."""
    records = tuple(records)
    scopes = tuple(scopes)
    if (isinstance(replication_factor, bool)
            or not isinstance(replication_factor, int)
            or replication_factor < 1):
        raise ValueError("replication factor must be positive")
    if any(not isinstance(row, AtomRecord) for row in records):
        raise TypeError("captured amplification requires AtomRecord values")
    if any(not isinstance(row, ScopeSpec) for row in scopes):
        raise TypeError("captured amplification requires ScopeSpec values")
    original_hash = structural_hash([row.to_dict() for row in records])
    all_scopes = list(scopes)
    all_records = list(records)
    scope_by_id = dict((row.scope_id, row) for row in scopes)
    for replica in range(replication_factor):
        scope_ids = dict(
            (scope.scope_id,
             "benchmark-amplified-{:04d}:{}".format(replica, scope.scope_id))
            for scope in scopes)
        cloned_scopes = []
        for scope in scopes:
            cloned_scopes.append(ScopeSpec(
                scope_id=scope_ids[scope.scope_id],
                scope_kind=scope.scope_kind,
                owner_player_id=scope.owner_player_id,
                root_entities=tuple(
                    _entity(term, replica) for term in scope.root_entities),
                parent_scope_ids=tuple(
                    scope_ids[value] for value in scope.parent_scope_ids),
                imported_predicates=scope.imported_predicates,
                exported_predicates=scope.exported_predicates,
                namespaces=frozenset((AtomNamespace.DIAGNOSTIC,)),
                maximum_atoms=scope.maximum_atoms,
                maximum_rule_fires=scope.maximum_rule_fires,
                maximum_groundings=scope.maximum_groundings,
                maximum_expansion_depth=scope.maximum_expansion_depth,
                retention_policy="benchmark-amplified",
                validity=scope.validity,
            ))
        all_scopes.extend(cloned_scopes)
        cloned_keys = {}
        for record in records:
            if record.key.scope_id not in scope_by_id:
                raise ValueError("captured record references an omitted scope")
            key = AtomKey(
                AtomNamespace.DIAGNOSTIC,
                record.key.predicate,
                tuple(_entity(term, replica) for term in record.key.arguments),
                scope_ids[record.key.scope_id],
            )
            cloned_keys[record.atom_id] = key
        for record in records:
            supports = []
            for support in record.supports:
                dependencies = []
                for dependency in support.dependencies:
                    key = dependency.key
                    if (key.kind.startswith("atom")
                            and key.owner_id in cloned_keys):
                        owner = cloned_keys[key.owner_id].atom_id
                        kind = key.kind
                    else:
                        owner = "benchmark-amplified-{:04d}:{}".format(
                            replica, key.owner_id)
                        kind = "benchmark-amplified:" + key.kind
                    dependencies.append(DependencyRef(
                        DependencyKey(kind, owner, key.path),
                        "benchmark-amplified-{:04d}:{}".format(
                            replica, dependency.fingerprint),
                    ))
                supports.append(SupportRecord.from_hashes(
                    "benchmark-amplified:{}".format(support.derivation_id),
                    support.derivation_version,
                    support.binding_hash,
                    tuple(dependencies),
                    support.witness_hash,
                    ("benchmark-amplifier",) + support.provenance_ids,
                    support.confidence_cap,
                ))
            all_records.append(AtomRecord.create(
                key=cloned_keys[record.atom_id],
                authority=AuthorityClass.CONTROL_MODEL,
                truth=record.truth,
                validity=record.validity,
                supports=tuple(supports),
                provenance_ids=("benchmark-amplifier",) + record.provenance_ids,
                lifecycle=record.lifecycle,
                tags=record.tags + (("benchmark", "captured-amplification"),),
            ))
    combined_registry = _benchmark_registry(predicate_registry)
    historical = tuple(
        row for row in all_records
        if (row.validity.snapshot_id is not None
            and row.validity.snapshot_id != str(snapshot_id)))
    if not historical:
        transaction = AtomSpaceTransaction(
            str(snapshot_id), combined_registry,
            tuple(all_scopes), maximum_atoms=len(all_records))
        for record in all_records:
            transaction.apply(record)
        revision_id = transaction.commit()
        committed_records = transaction.records
        committed_scopes = transaction.scopes
        dependency_index = transaction.dependency_index
        validation_mode = "same-snapshot-transaction"
    else:
        # Retained live revisions intentionally contain records whose validity
        # interval refers to the source snapshot that originally justified
        # them. Replaying those records through a new-snapshot transaction
        # would erase that temporal distinction or fail validation. Keep the
        # production transaction strict and validate every other structural
        # contract before building the immutable production dependency index.
        scope_by_id = dict((row.scope_id, row) for row in all_scopes)
        counts = dict((row.scope_id, 0) for row in all_scopes)
        for record in all_records:
            try:
                scope = scope_by_id[record.key.scope_id]
            except KeyError:
                raise ValueError("amplified atom references unknown scope")
            if record.key.namespace not in scope.namespaces:
                raise ValueError("amplified atom namespace is not in scope")
            combined_registry.validate(record.key, scope.scope_kind)
            counts[scope.scope_id] += 1
        for scope_id, count in counts.items():
            if count > scope_by_id[scope_id].maximum_atoms:
                raise ValueError(
                    "amplified scope atom budget exceeded: {}".format(
                        scope_id))
        committed_records = tuple(sorted(
            all_records, key=lambda value: value.atom_id))
        committed_scopes = tuple(sorted(
            all_scopes, key=lambda value: value.scope_id))
        dependency_index = DependencyIndex.build(committed_records)
        identity_parts = [str(snapshot_id)]
        for scope in committed_scopes:
            identity_parts.extend((
                scope.scope_id, structural_hash(scope.to_dict())))
        for record in committed_records:
            identity_parts.extend((
                record.atom_id, record.materialization_key))
        revision_id = (
            "fdas-revision-" + joined_identity_hash(identity_parts)[:32])
        validation_mode = "retained-historical-dependency-index"
    original_after = tuple(
        dependency_index.atom_by_id[row.atom_id] for row in records)
    after_hash = structural_hash([row.to_dict() for row in original_after])
    return CapturedAmplification(
        records=committed_records,
        scopes=committed_scopes,
        revision_id=revision_id,
        dependency_index=dependency_index,
        original_record_count=len(records),
        amplified_record_count=len(records) * replication_factor,
        replication_factor=replication_factor,
        original_hash_before=original_hash,
        original_hash_after=after_hash,
        historical_validity_record_count=len(historical),
        validation_mode=validation_mode,
    )
