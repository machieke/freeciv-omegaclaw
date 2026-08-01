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


class ActivatedDomainProjector(object):
    """Apply explicit focused-scope funding around any pure projector."""

    projector_id = "fdas-activated-domain-projector"
    version = "1.0"

    def __init__(self, projector, activator, signal_source):
        from .scopes import ScopeActivator

        if not isinstance(activator, ScopeActivator):
            raise TypeError("activated projector requires ScopeActivator")
        if not callable(signal_source):
            raise TypeError("activated projector requires signal source")
        self.projector = projector
        self.activator = activator
        self.signal_source = signal_source
        self.predicate_registry = projector.predicate_registry
        self._builds = {}

    def scopes(self, snapshot):
        all_scopes = tuple(self.projector.scopes(snapshot))
        signals = tuple(self.signal_source(snapshot, all_scopes))
        state = self.activator.activate(all_scopes, signals, snapshot.turn)
        active = frozenset(state.active_scope_ids)
        selected = tuple(value for value in all_scopes
                         if value.scope_id in active)
        if not any(value.scope_kind == "world" for value in selected):
            raise ValueError("focused projection cannot omit world scope")
        if not any(value.scope_kind == "empire" for value in selected):
            raise ValueError("focused projection cannot omit empire scope")
        self._builds[snapshot.snapshot_id] = (all_scopes, state)
        return selected

    def activation(self, snapshot_id):
        try:
            return self._builds[str(snapshot_id)][1]
        except KeyError:
            raise KeyError("snapshot has no scope activation state")

    def extend_fingerprints(self, fingerprints):
        return self.projector.extend_fingerprints(fingerprints)

    def project(self, snapshot, scopes, fingerprints):
        try:
            all_scopes, state = self._builds[snapshot.snapshot_id]
        except KeyError:
            self.scopes(snapshot)
            all_scopes, state = self._builds[snapshot.snapshot_id]
        supplied = frozenset(value.scope_id for value in scopes)
        if supplied != frozenset(state.active_scope_ids):
            raise ValueError("focused projection scope set changed during build")
        records = self.projector.project(
            snapshot, all_scopes, fingerprints)
        return tuple(value for value in records
                     if value.key.scope_id in supplied)
