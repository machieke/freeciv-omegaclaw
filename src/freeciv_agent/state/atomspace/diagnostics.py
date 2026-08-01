"""Deterministic read-only operator diagnostics for FDAS revisions."""

from collections import Counter

from ...events.schema import structural_hash
from .model import DependencyKey
from .query import AtomQuery, RevisionQueryContext
from .store import DependentAtomSpaceRevision, DependentAtomSpaceStore


class AtomSpaceDiagnostics(object):
    """Report revision state without acquiring decision or mutation authority."""

    DIAGNOSTIC_IDENTITY = "fdas-operator-diagnostics/1.0"

    def __init__(self, revision, shadow_decisions=()):
        if not isinstance(revision, DependentAtomSpaceRevision):
            raise TypeError("operator diagnostics require an FDAS revision")
        rows = tuple(dict(value) for value in shadow_decisions)
        turns = [int(value["turn"]) for value in rows]
        if len(turns) != len(set(turns)):
            raise ValueError("shadow decision turns must be unique")
        self.revision = revision
        self.query = RevisionQueryContext(revision)
        self._shadow_decisions = dict(zip(turns, rows))

    @staticmethod
    def _counts(values):
        return dict(sorted(Counter(values).items()))

    def stats(self):
        records = self.revision.records
        semantic = {
            "atom_count": len(records),
            "atoms_by_authority": self._counts(
                value.authority.value for value in records),
            "atoms_by_namespace": self._counts(
                value.key.namespace.value for value in records),
            "atoms_by_predicate": self._counts(
                value.key.predicate for value in records),
            "atoms_by_scope_kind": self._counts(
                next(scope.scope_kind for scope in self.revision.scopes
                     if scope.scope_id == value.key.scope_id)
                for value in records),
            "build_hash": self.revision.build_hash,
            "diagnostic_identity": self.DIAGNOSTIC_IDENTITY,
            "metrics": (
                None if self.revision.metrics is None
                else self.revision.metrics.to_dict()),
            "revision_id": self.revision.revision_id,
            "scope_count": len(self.revision.scopes),
            "snapshot_id": self.revision.snapshot_id,
            "support_count": len(
                self.revision.dependency_index.support_by_id),
        }
        semantic["structural_hash"] = structural_hash(semantic)
        return semantic

    def scopes(self, active_only=True):
        rows = []
        for scope in self.revision.scopes:
            atom_ids = self.revision.dependency_index.scope_atom_ids.get(
                scope.scope_id, ())
            if active_only and not atom_ids:
                continue
            rows.append({
                "atom_count": len(atom_ids),
                "atom_ids": list(atom_ids),
                "maximum_atoms": scope.maximum_atoms,
                "maximum_expansion_depth": scope.maximum_expansion_depth,
                "maximum_groundings": scope.maximum_groundings,
                "maximum_rule_fires": scope.maximum_rule_fires,
                "parent_scope_ids": list(scope.parent_scope_ids),
                "retention_policy": scope.retention_policy,
                "root_entities": [value.to_dict()
                                  for value in scope.root_entities],
                "scope_id": scope.scope_id,
                "scope_kind": scope.scope_kind,
                "validity": scope.validity.to_dict(),
            })
        return tuple(rows)

    def explain(self, atom_id, support_limit=None):
        return self.query.explain(atom_id, support_limit=support_limit)

    def why_not(self, query):
        if not isinstance(query, AtomQuery):
            raise TypeError("operator why-not requires AtomQuery")
        return self.query.why_not(query)

    def dependencies(self, atom_id):
        record = self.query.require_record(atom_id)
        rows = []
        for support in record.supports:
            rows.append({
                "dependencies": [value.to_dict()
                                 for value in support.dependencies],
                "derivation_id": support.derivation_id,
                "provenance_ids": list(support.provenance_ids),
                "support_id": support.support_id,
            })
        return tuple(rows)

    def dependents(self, dependency):
        if isinstance(dependency, str):
            keys = self.revision.dependency_index.dependent_keys_by_owner.get(
                dependency, ())
        elif isinstance(dependency, DependencyKey):
            keys = (dependency,)
        else:
            raise TypeError("dependents require an atom ID or DependencyKey")
        rows = []
        for key in keys:
            support_ids = self.revision.dependency_index.dependency_support_ids.get(
                key, ())
            output_ids = sorted(set(
                atom_id for support_id in support_ids
                for atom_id in self.revision.dependency_index.
                support_output_atom_ids.get(support_id, ())))
            rows.append({
                "dependency": key.to_dict(),
                "output_atom_ids": output_ids,
                "support_ids": list(support_ids),
            })
        return tuple(rows)

    def diff(self, other):
        if not isinstance(other, DependentAtomSpaceRevision):
            raise TypeError("FDAS diff requires another revision")
        before = dict((value.atom_id, value) for value in self.revision.records)
        after = dict((value.atom_id, value) for value in other.records)
        common = set(before).intersection(after)
        changed = sorted(
            atom_id for atom_id in common
            if before[atom_id] != after[atom_id])
        semantic = {
            "added_atom_ids": sorted(set(after).difference(before)),
            "after_revision_id": other.revision_id,
            "before_revision_id": self.revision.revision_id,
            "changed_atom_ids": changed,
            "removed_atom_ids": sorted(set(before).difference(after)),
        }
        semantic["structural_hash"] = structural_hash(semantic)
        return semantic

    def shadow_decision(self, turn):
        turn = int(turn)
        try:
            return dict(self._shadow_decisions[turn])
        except KeyError:
            raise KeyError("no FDAS shadow decision for turn {}".format(turn))

    @staticmethod
    def cold_verify(store, snapshot, prior_snapshot, prior_revision):
        if not isinstance(store, DependentAtomSpaceStore):
            raise TypeError("cold verification requires FDAS store")
        return store.verify_incremental(
            snapshot, prior_snapshot, prior_revision).to_dict()
