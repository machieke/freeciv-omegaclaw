"""Composition helpers for independently gated FDAS domain projectors."""

from dataclasses import replace

from .predicates import PredicateRegistry


def merge_predicate_registries(*registries):
    """Merge registries while rejecting incompatible duplicate predicates."""
    by_name = {}
    for registry in registries:
        if not isinstance(registry, PredicateRegistry):
            raise TypeError("projector registry must be PredicateRegistry")
        for spec in registry.specs:
            existing = by_name.get(spec.predicate)
            if existing is not None and existing != spec:
                raise ValueError(
                    "incompatible predicate specification: {}".format(
                        spec.predicate))
            by_name[spec.predicate] = spec
    return PredicateRegistry(
        tuple(by_name[key] for key in sorted(by_name)))


class CompositeDomainProjector(object):
    """Present several pure projectors as one store projection boundary."""

    projector_id = "fdas-composite-domain-projector"
    version = "1.0"

    def __init__(self, projectors):
        self.projectors = tuple(projectors)
        if not self.projectors:
            raise ValueError("composite projector requires components")
        for projector in self.projectors:
            for attribute in (
                    "predicate_registry", "scopes",
                    "extend_fingerprints", "project"):
                if not hasattr(projector, attribute):
                    raise TypeError(
                        "domain projector lacks {}".format(attribute))
        self.predicate_registry = merge_predicate_registries(
            *(value.predicate_registry for value in self.projectors))

    def scopes(self, snapshot):
        by_id = {}
        for projector in self.projectors:
            for scope in projector.scopes(snapshot):
                existing = by_id.get(scope.scope_id)
                if existing is None:
                    by_id[scope.scope_id] = scope
                    continue
                fixed_fields = (
                    "scope_kind", "owner_player_id", "root_entities",
                    "parent_scope_ids", "retention_policy", "validity")
                if any(getattr(existing, name) != getattr(scope, name)
                       for name in fixed_fields):
                    raise ValueError(
                        "incompatible scope specification: {}".format(
                            scope.scope_id))
                by_id[scope.scope_id] = replace(
                    existing,
                    imported_predicates=tuple(sorted(set(
                        existing.imported_predicates
                    ).union(scope.imported_predicates))),
                    exported_predicates=tuple(sorted(set(
                        existing.exported_predicates
                    ).union(scope.exported_predicates))),
                    namespaces=frozenset(
                        existing.namespaces.union(scope.namespaces)),
                    maximum_atoms=max(
                        existing.maximum_atoms, scope.maximum_atoms),
                    maximum_rule_fires=max(
                        existing.maximum_rule_fires,
                        scope.maximum_rule_fires),
                    maximum_groundings=max(
                        existing.maximum_groundings,
                        scope.maximum_groundings),
                    maximum_expansion_depth=max(
                        existing.maximum_expansion_depth,
                        scope.maximum_expansion_depth),
                )
        return tuple(by_id[key] for key in sorted(by_id))

    def extend_fingerprints(self, fingerprints):
        result = dict(fingerprints)
        for projector in self.projectors:
            result = projector.extend_fingerprints(result)
        return result

    def project(self, snapshot, scopes, fingerprints):
        records = []
        for projector in self.projectors:
            records.extend(projector.project(snapshot, scopes, fingerprints))
        return tuple(sorted(records, key=lambda value: value.atom_id))
