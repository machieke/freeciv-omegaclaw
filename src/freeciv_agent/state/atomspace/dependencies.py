"""Immutable reverse indexes and support-aware truth maintenance."""

from collections import deque
from dataclasses import dataclass
from types import MappingProxyType

from .model import AtomRecord, DependencyKey, EntityRef


def _frozen_mapping(values):
    return MappingProxyType(dict(values))


def _tuple_mapping(values):
    return _frozen_mapping(
        (key, tuple(sorted(set(items))))
        for key, items in values.items())


@dataclass(frozen=True)
class InvalidationResult:
    changed_dependency_keys: tuple
    invalid_support_ids: tuple
    affected_atom_ids: tuple
    unsupported_atom_ids: tuple
    surviving_atom_ids: tuple

    def to_dict(self):
        return {
            "affected_atom_ids": list(self.affected_atom_ids),
            "changed_dependency_keys": [
                value.to_dict() for value in self.changed_dependency_keys],
            "invalid_support_ids": list(self.invalid_support_ids),
            "surviving_atom_ids": list(self.surviving_atom_ids),
            "unsupported_atom_ids": list(self.unsupported_atom_ids),
        }


@dataclass(frozen=True)
class DependencyIndex:
    atom_by_id: object
    support_by_id: object
    atom_support_ids: object
    support_output_atom_ids: object
    support_dependency_keys: object
    dependency_support_ids: object
    derivation_support_ids: object
    scope_atom_ids: object
    entity_scope_ids: object
    operation_atom_ids: object
    belief_atom_ids: object
    dependent_keys_by_owner: object

    @classmethod
    def build(cls, records):
        records = tuple(records)
        atoms = {}
        supports = {}
        atom_supports = {}
        support_outputs = {}
        support_dependencies = {}
        dependency_supports = {}
        derivation_supports = {}
        scope_atoms = {}
        entity_scopes = {}
        operation_atoms = {}
        belief_atoms = {}
        dependent_keys_by_owner = {}
        for record in records:
            if not isinstance(record, AtomRecord):
                raise TypeError("dependency index requires AtomRecord values")
            current = atoms.get(record.atom_id)
            if current is not None and current != record:
                raise ValueError("duplicate atom identity has unequal records")
            atoms[record.atom_id] = record
            atom_supports.setdefault(record.atom_id, set())
            scope_atoms.setdefault(record.key.scope_id, set()).add(
                record.atom_id)
            for argument in record.key.arguments:
                if not isinstance(argument, EntityRef):
                    continue
                entity_key = "{}:{}".format(
                    argument.kind, argument.entity_id)
                entity_scopes.setdefault(entity_key, set()).add(
                    record.key.scope_id)
                if argument.kind == "operation":
                    operation_atoms.setdefault(
                        argument.entity_id, set()).add(record.atom_id)
                if argument.kind in ("belief", "hypothesis"):
                    belief_atoms.setdefault(
                        argument.entity_id, set()).add(record.atom_id)
            for support in record.supports:
                existing = supports.get(support.support_id)
                if existing is not None and existing != support:
                    raise ValueError("support ID collision in dependency index")
                new_support = existing is None
                if new_support:
                    supports[support.support_id] = support
                atom_supports[record.atom_id].add(support.support_id)
                support_outputs.setdefault(support.support_id, set()).add(
                    record.atom_id)
                # A shared support may justify hundreds of output atoms (for
                # example stable region topology). Its dependency and
                # derivation indexes are support-level data and must be
                # registered once, not rebuilt once per output atom.
                if new_support:
                    support_dependencies[support.support_id] = set()
                    derivation_supports.setdefault(
                        support.derivation_id, set()).add(support.support_id)
                    for dependency in support.dependencies:
                        key = dependency.key
                        support_dependencies[support.support_id].add(key)
                        dependency_supports.setdefault(key, set()).add(
                            support.support_id)
                        dependent_keys_by_owner.setdefault(
                            key.owner_id, set()).add(key)
        return cls(
            _frozen_mapping(atoms),
            _frozen_mapping(supports),
            _tuple_mapping(atom_supports),
            _tuple_mapping(support_outputs),
            _tuple_mapping(support_dependencies),
            _tuple_mapping(dependency_supports),
            _tuple_mapping(derivation_supports),
            _tuple_mapping(scope_atoms),
            _tuple_mapping(entity_scopes),
            _tuple_mapping(operation_atoms),
            _tuple_mapping(belief_atoms),
            _tuple_mapping(dependent_keys_by_owner),
        )

    def invalidate(self, changed_keys):
        """Return the transitive support/atom impact without mutating the index."""
        pending_keys = deque(sorted(set(changed_keys)))
        visited_keys = set()
        invalid_supports = set()
        affected_atoms = set()
        unsupported = set()
        while pending_keys:
            key = pending_keys.popleft()
            if key in visited_keys:
                continue
            visited_keys.add(key)
            for support_id in self.dependency_support_ids.get(key, ()):
                if support_id in invalid_supports:
                    continue
                invalid_supports.add(support_id)
                for atom_id in self.support_output_atom_ids.get(
                        support_id, ()):
                    affected_atoms.add(atom_id)
                    support_ids = set(self.atom_support_ids.get(atom_id, ()))
                    if (support_ids
                            and support_ids.issubset(invalid_supports)
                            and atom_id not in unsupported):
                        unsupported.add(atom_id)
                        for dependent_key in self.dependent_keys_by_owner.get(
                                atom_id, ()):
                            if dependent_key.kind.startswith("atom"):
                                pending_keys.append(dependent_key)
        surviving = affected_atoms.difference(unsupported)
        return InvalidationResult(
            tuple(sorted(visited_keys)),
            tuple(sorted(invalid_supports)),
            tuple(sorted(affected_atoms)),
            tuple(sorted(unsupported)),
            tuple(sorted(surviving)),
        )

    def stale_dependencies(self, fingerprints):
        """Report indexed dependency refs that disagree with current sources."""
        stale = []
        for support_id, support in self.support_by_id.items():
            for dependency in support.dependencies:
                if fingerprints.get(dependency.key) != dependency.fingerprint:
                    stale.append((support_id, dependency.key))
        return tuple(sorted(stale, key=lambda row: (row[0], row[1])))

    def to_dict(self):
        def rows(mapping, key=lambda value: value):
            return dict(
                (str(key(name)), list(values))
                for name, values in sorted(
                    mapping.items(), key=lambda row: str(key(row[0]))))

        return {
            "atom_ids": sorted(self.atom_by_id),
            "atom_support_ids": rows(self.atom_support_ids),
            "belief_atom_ids": rows(self.belief_atom_ids),
            "dependency_support_ids": [
                {
                    "dependency": dependency.to_dict(),
                    "support_ids": list(support_ids),
                }
                for dependency, support_ids in sorted(
                    self.dependency_support_ids.items())],
            "derivation_support_ids": rows(self.derivation_support_ids),
            "entity_scope_ids": rows(self.entity_scope_ids),
            "operation_atom_ids": rows(self.operation_atom_ids),
            "scope_atom_ids": rows(self.scope_atom_ids),
            "support_dependency_keys": [
                {
                    "dependency_keys": [value.to_dict() for value in values],
                    "support_id": support_id,
                }
                for support_id, values in sorted(
                    self.support_dependency_keys.items())],
            "support_ids": sorted(self.support_by_id),
            "support_output_atom_ids": rows(self.support_output_atom_ids),
        }
