"""Revision-bound typed FDAS queries with decision-staleness guards."""

from dataclasses import dataclass

from .model import AtomNamespace, EntityRef, SymbolRef


class StaleAtomSpaceRevision(RuntimeError):
    pass


@dataclass(frozen=True)
class AtomQuery:
    predicate: object = None
    namespace: object = None
    arguments: object = None
    scope_id: object = None

    def __post_init__(self):
        if self.predicate is not None and (
                not isinstance(self.predicate, str) or not self.predicate):
            raise ValueError("query predicate must be non-empty or absent")
        if self.namespace is not None:
            object.__setattr__(
                self, "namespace", AtomNamespace(self.namespace))
        if self.arguments is not None:
            arguments = tuple(self.arguments)
            if any(not isinstance(value, (EntityRef, SymbolRef))
                   for value in arguments):
                raise TypeError("query arguments must be typed terms")
            object.__setattr__(self, "arguments", arguments)
        if self.scope_id is not None and (
                not isinstance(self.scope_id, str) or not self.scope_id):
            raise ValueError("query scope ID must be non-empty or absent")


class RevisionQueryContext(object):
    def __init__(self, revision, expected_snapshot_id=None,
                 decision_safe=False):
        self.revision = revision
        self.expected_snapshot_id = expected_snapshot_id
        self.decision_safe = bool(decision_safe)
        if self.decision_safe:
            if not isinstance(expected_snapshot_id, str) or not expected_snapshot_id:
                raise ValueError(
                    "decision-safe query requires expected snapshot ID")
            if revision.snapshot_id != expected_snapshot_id:
                raise StaleAtomSpaceRevision(
                    "FDAS revision {} is stale for snapshot {}".format(
                        revision.snapshot_id, expected_snapshot_id))

    def records(self, query=None):
        query = query or AtomQuery()
        if not isinstance(query, AtomQuery):
            raise TypeError("FDAS records require AtomQuery")
        result = []
        for record in self.revision.records:
            if (query.predicate is not None
                    and record.key.predicate != query.predicate):
                continue
            if (query.namespace is not None
                    and record.key.namespace != query.namespace):
                continue
            if (query.arguments is not None
                    and record.key.arguments != query.arguments):
                continue
            if (query.scope_id is not None
                    and record.key.scope_id != query.scope_id):
                continue
            result.append(record)
        return tuple(result)

    def require_record(self, atom_id):
        record = self.revision.record(str(atom_id))
        if record is None:
            raise KeyError("unknown atom in revision: {}".format(atom_id))
        return record
