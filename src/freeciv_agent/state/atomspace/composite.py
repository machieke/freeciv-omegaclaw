"""Composition helpers for independently gated FDAS domain projectors."""

from dataclasses import replace
from functools import lru_cache

from ...events.schema import structural_hash
from .model import AtomRecord
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
        projector_ids = [value.projector_id for value in self.projectors]
        if len(projector_ids) != len(set(projector_ids)):
            raise ValueError("composite projector IDs must be unique")
        self._component_scopes = {}
        self._projections = {}
        self._incremental_metrics = {}
        self._incremental_roots = frozenset(
            root for projector in self.projectors
            for root in getattr(
                projector, "incremental_dependency_roots", ()))
        self._incremental_kinds = frozenset(
            kind for projector in self.projectors
            for kind in getattr(
                projector, "incremental_dependency_kinds", ()))

    @property
    def component_projector_ids(self):
        return tuple(value.projector_id for value in self.projectors)

    @staticmethod
    def _trim(cache):
        while len(cache) > 8:
            cache.pop(next(iter(cache)))

    @staticmethod
    def _root(path):
        return str(path).split(".", 1)[0]

    @staticmethod
    @lru_cache(maxsize=512)
    def _semantic_fingerprint(rows):
        return structural_hash(tuple(
            (key.to_dict(), fingerprint) for key, fingerprint in rows))

    @classmethod
    def _fingerprint_index(cls, fingerprints, wanted_roots, wanted_kinds):
        roots = {}
        kinds = {}
        for key, fingerprint in fingerprints.items():
            root = cls._root(key.path)
            if key.kind == "snapshot-field" and root in wanted_roots:
                roots.setdefault(root, []).append((key, fingerprint))
            elif key.kind in wanted_kinds:
                kinds.setdefault(key.kind, []).append((key, fingerprint))
        return {
            "kinds": dict(
                (kind, cls._semantic_fingerprint(tuple(sorted(rows))))
                for kind, rows in kinds.items()),
            "roots": dict(
                (root, cls._semantic_fingerprint(tuple(sorted(rows))))
                for root, rows in roots.items()),
        }

    @classmethod
    def _component_fingerprint(
            cls, projector, fingerprints, fingerprint_index,
            dependency_keys=()):
        roots = frozenset(getattr(
            projector, "incremental_dependency_roots", ()))
        kinds = frozenset(getattr(
            projector, "incremental_dependency_kinds", ()))
        if not roots and not kinds:
            return None
        semantic = [
            ("kind", kind, fingerprint_index["kinds"].get(kind))
            for kind in sorted(kinds)]
        semantic.extend(
            ("root", root, fingerprint_index["roots"].get(root))
            for root in sorted(roots))
        semantic.extend(
            ("dependency", key.to_dict(), fingerprints.get(key))
            for key in sorted(set(dependency_keys))
            if (key.kind not in kinds
                and not (key.kind == "snapshot-field"
                         and cls._root(key.path) in roots)))
        return structural_hash(semantic)

    @staticmethod
    def _refresh(records, scopes):
        scope_by_id = dict((value.scope_id, value) for value in scopes)
        refreshed = []
        for record in records:
            scope = scope_by_id.get(record.key.scope_id)
            if scope is None:
                raise ValueError(
                    "incremental projector record scope disappeared")
            refreshed.append(AtomRecord.create(
                record.key, record.authority, record.truth, scope.validity,
                record.supports, record.provenance_ids, record.lifecycle,
                record.tags))
        return tuple(refreshed)

    def scopes(self, snapshot):
        by_id = {}
        component_scopes = {}
        for projector in self.projectors:
            projected_scopes = tuple(projector.scopes(snapshot))
            component_scopes[projector.projector_id] = tuple(sorted(
                value.scope_id for value in projected_scopes))
            for scope in projected_scopes:
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
        self._component_scopes[snapshot.snapshot_id] = component_scopes
        self._trim(self._component_scopes)
        return tuple(by_id[key] for key in sorted(by_id))

    def extend_fingerprints(self, fingerprints):
        result = dict(fingerprints)
        for projector in self.projectors:
            result = projector.extend_fingerprints(result)
        return result

    def project(self, snapshot, scopes, fingerprints):
        records = []
        components = {}
        fingerprint_index = self._fingerprint_index(
            fingerprints, self._incremental_roots, self._incremental_kinds)
        for projector in self.projectors:
            projected = tuple(projector.project(
                snapshot, scopes, fingerprints))
            dependency_keys = tuple(sorted(set(
                dependency.key
                for record in projected for support in record.supports
                for dependency in support.dependencies)))
            components[projector.projector_id] = {
                "dependency_keys": dependency_keys,
                "fingerprint": self._component_fingerprint(
                    projector, fingerprints, fingerprint_index,
                    dependency_keys),
                "records": projected,
                "scope_ids": self._component_scopes.get(
                    snapshot.snapshot_id, {}).get(
                        projector.projector_id, ()),
            }
            records.extend(projected)
        self._projections[snapshot.snapshot_id] = components
        self._trim(self._projections)
        return tuple(sorted(records, key=lambda value: value.atom_id))

    def project_incremental(
            self, snapshot, scopes, fingerprints, prior_snapshot,
            _prior_revision):
        prior = self._projections.get(prior_snapshot.snapshot_id, {})
        current_scopes = self._component_scopes.get(
            snapshot.snapshot_id, {})
        fingerprint_index = self._fingerprint_index(
            fingerprints, self._incremental_roots, self._incremental_kinds)
        records = []
        components = {}
        reused = []
        recomputed = []
        reused_record_count = 0
        recomputed_record_count = 0
        for projector in self.projectors:
            projector_id = projector.projector_id
            cached = prior.get(projector_id)
            current_scope_ids = current_scopes.get(projector_id, ())
            fingerprint = self._component_fingerprint(
                projector, fingerprints, fingerprint_index,
                () if cached is None else cached["dependency_keys"])
            can_reuse = bool(
                cached is not None
                and fingerprint is not None
                and fingerprint == cached["fingerprint"]
                and current_scope_ids == cached["scope_ids"])
            if can_reuse:
                projected = self._refresh(cached["records"], scopes)
                dependency_keys = cached["dependency_keys"]
                reused.append(projector_id)
                reused_record_count += len(projected)
            else:
                projected = tuple(projector.project(
                    snapshot, scopes, fingerprints))
                dependency_keys = tuple(sorted(set(
                    dependency.key
                    for record in projected for support in record.supports
                    for dependency in support.dependencies)))
                fingerprint = self._component_fingerprint(
                    projector, fingerprints, fingerprint_index,
                    dependency_keys)
                recomputed.append(projector_id)
                recomputed_record_count += len(projected)
            components[projector_id] = {
                "dependency_keys": dependency_keys,
                "fingerprint": fingerprint,
                "records": projected,
                "scope_ids": current_scope_ids,
            }
            records.extend(projected)
        self._projections[snapshot.snapshot_id] = components
        self._trim(self._projections)
        self._incremental_metrics[snapshot.snapshot_id] = {
            "recomputed_projector_ids": tuple(recomputed),
            "recomputed_record_count": recomputed_record_count,
            "reused_projector_ids": tuple(reused),
            "reused_record_count": reused_record_count,
        }
        self._trim(self._incremental_metrics)
        return tuple(sorted(records, key=lambda value: value.atom_id))

    def incremental_metrics(self, snapshot_id):
        return dict(self._incremental_metrics.get(str(snapshot_id), {
            "recomputed_projector_ids": (),
            "recomputed_record_count": 0,
            "reused_projector_ids": (),
            "reused_record_count": 0,
        }))


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
        if len(self._builds) > 8:
            for snapshot_id in tuple(self._builds)[:-8]:
                self._builds.pop(snapshot_id, None)
        return selected

    def activation(self, snapshot_id):
        try:
            return self._builds[str(snapshot_id)][1]
        except KeyError:
            raise KeyError("snapshot has no scope activation state")

    @property
    def component_projector_ids(self):
        return tuple(getattr(
            self.projector, "component_projector_ids", ()))

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

    def project_incremental(
            self, snapshot, scopes, fingerprints, prior_snapshot,
            prior_revision):
        try:
            all_scopes, state = self._builds[snapshot.snapshot_id]
        except KeyError:
            self.scopes(snapshot)
            all_scopes, state = self._builds[snapshot.snapshot_id]
        supplied = frozenset(value.scope_id for value in scopes)
        if supplied != frozenset(state.active_scope_ids):
            raise ValueError("focused projection scope set changed during build")
        if hasattr(self.projector, "project_incremental"):
            records = self.projector.project_incremental(
                snapshot, all_scopes, fingerprints, prior_snapshot,
                prior_revision)
        else:
            records = self.projector.project(
                snapshot, all_scopes, fingerprints)
        return tuple(value for value in records
                     if value.key.scope_id in supplied)

    def incremental_metrics(self, snapshot_id):
        if hasattr(self.projector, "incremental_metrics"):
            return self.projector.incremental_metrics(snapshot_id)
        return {
            "recomputed_projector_ids": (),
            "recomputed_record_count": 0,
            "reused_projector_ids": (),
            "reused_record_count": 0,
        }
