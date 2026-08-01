"""Atomic validation for Phase-1 full-build FDAS revisions."""

from ...events.schema import structural_hash
from .model import (
    AtomNamespace,
    AtomRecord,
    AuthorityClass,
    joined_identity_hash,
)
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
    def __init__(self, snapshot_id, predicate_registry, scopes):
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
            raise ValueError("atom ID collision within transaction")
        self._records[record.atom_id] = record
        return record

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
