"""Atomic validation for Phase-1 full-build FDAS revisions."""

from ...events.schema import structural_hash
from .model import (
    AtomNamespace,
    AtomRecord,
    AuthorityClass,
    joined_identity_hash,
)
from .dependencies import DependencyIndex
from .derivations import ProjectionBatch
from .predicates import PredicateRegistry
from .scopes import ScopeSpec


_NAMESPACE_AUTHORITIES = {
    AtomNamespace.AUTHORITATIVE: frozenset((
        AuthorityClass.ENGINE_AUTHORITATIVE,
    )),
    AtomNamespace.OBSERVATION: frozenset((
        AuthorityClass.PACKET_OBSERVATION,
    )),
    AtomNamespace.RULESET: frozenset((
        AuthorityClass.RULESET_EXACT,
    )),
    AtomNamespace.DERIVED: frozenset((
        AuthorityClass.DETERMINISTIC_DERIVED,
    )),
    AtomNamespace.BELIEF: frozenset((
        AuthorityClass.UNCERTAIN_BELIEF,
    )),
    AtomNamespace.GOAL: frozenset((
        AuthorityClass.POLICY,
    )),
    AtomNamespace.OPERATION: frozenset((
        AuthorityClass.CONTROL_MODEL,
    )),
    AtomNamespace.EPISODE: frozenset((
        AuthorityClass.ENGINE_AUTHORITATIVE,
        AuthorityClass.CONTROL_MODEL,
    )),
    AtomNamespace.DIAGNOSTIC: frozenset(AuthorityClass),
}


class AtomSpaceTransaction(object):
    def __init__(self, snapshot_id, predicate_registry, scopes, records=()):
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise ValueError("transaction snapshot ID is required")
        if not isinstance(predicate_registry, PredicateRegistry):
            raise TypeError("transaction requires PredicateRegistry")
        scopes = tuple(scopes)
        if any(not isinstance(value, ScopeSpec) for value in scopes):
            raise TypeError("transaction scopes must be ScopeSpec values")
        if len({value.scope_id for value in scopes}) != len(scopes):
            raise ValueError("transaction scope IDs must be unique")
        self.snapshot_id = snapshot_id
        self.predicate_registry = predicate_registry
        self._scopes = dict((value.scope_id, value) for value in scopes)
        self._records = {}
        self._closed = False
        self._revision_id = None
        self._dependency_index = None
        for record in records:
            self.apply(record)

    def _require_open(self):
        if self._closed:
            raise RuntimeError("atomspace transaction is closed")

    def apply(self, record):
        self._require_open()
        if not isinstance(record, AtomRecord):
            raise TypeError("transaction accepts AtomRecord values")
        try:
            scope = self._scopes[record.key.scope_id]
        except KeyError:
            raise ValueError(
                "atom references unknown scope: {}".format(
                    record.key.scope_id))
        if record.key.namespace not in scope.namespaces:
            raise ValueError("atom namespace is not enabled in its scope")
        self.predicate_registry.validate(record.key, scope.scope_kind)
        if record.authority not in _NAMESPACE_AUTHORITIES[record.key.namespace]:
            raise ValueError("atom authority is invalid for its namespace")
        if (record.validity.snapshot_id is not None
                and record.validity.snapshot_id != self.snapshot_id):
            raise ValueError("atom validity references a different snapshot")
        current = self._records.get(record.atom_id)
        if current is not None and current != record:
            comparable_current = (
                current.key,
                current.authority,
                current.truth,
                current.validity,
                current.lifecycle,
                current.tags,
            )
            comparable_new = (
                record.key,
                record.authority,
                record.truth,
                record.validity,
                record.lifecycle,
                record.tags,
            )
            if comparable_current != comparable_new:
                raise ValueError("atom ID collision within transaction")
            supports = dict(
                (value.support_id, value)
                for value in current.supports + record.supports)
            record = AtomRecord.create(
                record.key,
                record.authority,
                record.truth,
                record.validity,
                tuple(supports[key] for key in sorted(supports)),
                current.provenance_ids + record.provenance_ids,
                record.lifecycle,
                record.tags,
            )
        self._records[record.atom_id] = record
        return record

    def retract_support(self, support_id):
        self._require_open()
        support_id = str(support_id)
        changed = []
        for atom_id, record in tuple(self._records.items()):
            supports = tuple(
                value for value in record.supports
                if value.support_id != support_id)
            if len(supports) == len(record.supports):
                continue
            changed.append(atom_id)
            if not supports:
                del self._records[atom_id]
                continue
            self._records[atom_id] = AtomRecord.create(
                record.key,
                record.authority,
                record.truth,
                record.validity,
                supports,
                record.provenance_ids,
                record.lifecycle,
                record.tags,
            )
        return tuple(sorted(changed))

    def apply_batch(self, batch):
        self._require_open()
        if not isinstance(batch, ProjectionBatch):
            raise TypeError("transaction requires ProjectionBatch")
        for record in batch.upserts:
            if record.key.scope_id != batch.scope_id:
                raise ValueError("projection batch crosses its declared scope")
        declared = set(batch.dependency_fingerprints)
        used = set(
            dependency
            for record in batch.upserts
            for support in record.supports
            for dependency in support.dependencies)
        if not used.issubset(declared):
            raise ValueError("projection batch used undeclared dependencies")
        for support_id in batch.retract_support_ids:
            self.retract_support(support_id)
        for record in batch.upserts:
            self.apply(record)
        return batch

    def invalidate(self, changed_keys):
        self._require_open()
        result = DependencyIndex.build(self._records.values()).invalidate(
            changed_keys)
        for support_id in result.invalid_support_ids:
            self.retract_support(support_id)
        return result

    def materialize(self, batches):
        self._require_open()
        for batch in batches:
            self.apply_batch(batch)

    def validate(self):
        self._require_open()
        counts = dict((scope_id, 0) for scope_id in self._scopes)
        for record in self._records.values():
            counts[record.key.scope_id] += 1
        for scope_id, count in counts.items():
            if count > self._scopes[scope_id].maximum_atoms:
                raise ValueError(
                    "scope atom budget exceeded: {}".format(scope_id))
        return True

    def commit(self):
        self.validate()
        self._dependency_index = DependencyIndex.build(
            self._records.values())
        identity_parts = [self.snapshot_id]
        for key in sorted(self._scopes):
            identity_parts.extend((
                key,
                structural_hash(self._scopes[key].to_dict()),
            ))
        for key in sorted(self._records):
            identity_parts.extend((
                key,
                self._records[key].materialization_key,
            ))
        self._revision_id = (
            "fdas-revision-"
            + joined_identity_hash(identity_parts)[:32])
        self._closed = True
        return self._revision_id

    def rollback(self):
        self._require_open()
        self._records.clear()
        self._closed = True

    @property
    def records(self):
        if not self._closed or self._revision_id is None:
            raise RuntimeError("transaction has not committed")
        return tuple(self._records[key] for key in sorted(self._records))

    @property
    def scopes(self):
        return tuple(self._scopes[key] for key in sorted(self._scopes))

    @property
    def dependency_index(self):
        if not self._closed or self._revision_id is None:
            raise RuntimeError("transaction has not committed")
        return self._dependency_index
