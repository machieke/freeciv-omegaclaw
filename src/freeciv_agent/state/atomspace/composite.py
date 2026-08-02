"""Composition helpers for independently gated FDAS domain projectors."""

from dataclasses import dataclass, replace
from functools import lru_cache

from ...events.schema import structural_hash
from .model import AtomRecord, joined_identity_hash
from .predicates import PredicateRegistry


@dataclass(frozen=True)
class ProjectionShardSpec:
    """Conservative input and output boundary for incremental projection."""

    shard_id: str
    snapshot_prefixes: tuple
    dependency_kinds: frozenset
    scope_ids: tuple

    def __post_init__(self):
        if not isinstance(self.shard_id, str) or not self.shard_id:
            raise ValueError("projection shard ID is required")
        prefixes = tuple(sorted(set(
            str(value).strip(".") for value in self.snapshot_prefixes
            if str(value).strip("."))))
        if not prefixes and not self.dependency_kinds:
            raise ValueError(
                "projection shard requires snapshot prefixes or dependency "
                "kinds")
        scopes = tuple(sorted(set(str(value) for value in self.scope_ids)))
        if not scopes:
            raise ValueError("projection shard requires output scopes")
        object.__setattr__(self, "snapshot_prefixes", prefixes)
        object.__setattr__(self, "dependency_kinds", frozenset(
            str(value) for value in self.dependency_kinds))
        object.__setattr__(self, "scope_ids", scopes)


class _SnapshotIdentityAccessRecorder(object):
    _ALIASES = {
        "game_id": (),
        "snapshot_id": ("source_seq", "turn"),
        "source_seq": ("source_seq",),
        "state_hash": ("source_seq", "turn"),
        "turn": ("turn",),
    }

    def __init__(self, identity, accessed_roots):
        object.__setattr__(self, "_identity", identity)
        object.__setattr__(self, "_accessed_roots", accessed_roots)

    def __getattr__(self, name):
        roots = self._ALIASES.get(str(name), (str(name),))
        self._accessed_roots.update(roots)
        return getattr(self._identity, name)

    def __setattr__(self, name, _value):
        raise AttributeError(
            "projectors cannot mutate snapshot identity {}".format(name))


class _SnapshotAccessRecorder(object):
    """Record semantic top-level reads without changing snapshot behavior."""

    _ALIASES = {
        "city": ("cities",),
        "legal_action_json": ("legal_actions",),
        "movement_route": ("movement_routes",),
        # Direct snapshot_id reads are transaction/cache plumbing. Projectors
        # whose output semantically embeds it must declare turn/source_seq;
        # nested identity reads below remain audited.
        "snapshot_id": (),
        "unit": ("units",),
        "visible_enemy_unit": ("visible_enemy_units",),
    }

    def __init__(self, snapshot):
        object.__setattr__(self, "_snapshot", snapshot)
        object.__setattr__(self, "accessed_roots", set())

    def __getattr__(self, name):
        if name == "identity":
            return _SnapshotIdentityAccessRecorder(
                self._snapshot.identity, self.accessed_roots)
        roots = self._ALIASES.get(str(name), (str(name),))
        self.accessed_roots.update(roots)
        return getattr(self._snapshot, name)

    def __setattr__(self, name, _value):
        raise AttributeError(
            "projectors cannot mutate snapshot attribute {}".format(name))


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
            shard_methods = tuple(hasattr(projector, name) for name in (
                "projection_shards", "project_shard"))
            if any(shard_methods) and not all(shard_methods):
                raise TypeError(
                    "incremental shard projector requires projection_shards "
                    "and project_shard")
        self.predicate_registry = merge_predicate_registries(
            *(value.predicate_registry for value in self.projectors))
        projector_ids = [value.projector_id for value in self.projectors]
        if len(projector_ids) != len(set(projector_ids)):
            raise ValueError("composite projector IDs must be unique")
        self._component_scopes = {}
        self._projections = {}
        self._incremental_metrics = {}
        self._fingerprint_index_cache = None
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
        # This digest is private cache identity over already canonical scalar
        # dependency fields. Avoid JSON-encoding thousands of tiny key
        # objects on every turn.
        return joined_identity_hash(tuple(
            value
            for key, fingerprint in rows
            for value in (
                key.kind, key.owner_id, key.path, fingerprint)))

    @classmethod
    def _fingerprint_index(
            cls, fingerprints, wanted_roots, wanted_kinds,
            wanted_prefixes=()):
        roots = {}
        kinds = {}
        prefix_trie = {}
        for prefix in sorted(set(str(value) for value in wanted_prefixes)):
            node = prefix_trie
            for part in prefix.split("."):
                node = node.setdefault(part, {})
            node[None] = prefix
        prefix_rows = {}
        for key, fingerprint in fingerprints.items():
            root = cls._root(key.path)
            if key.kind == "snapshot-field" and root in wanted_roots:
                row = (key, fingerprint)
                roots.setdefault(root, []).append(row)
                node = prefix_trie
                for part in str(key.path).split("."):
                    node = node.get(part)
                    if node is None:
                        break
                    prefix = node.get(None)
                    if prefix is not None:
                        prefix_rows.setdefault(prefix, []).append(row)
            elif key.kind in wanted_kinds:
                kinds.setdefault(key.kind, []).append((key, fingerprint))
        root_rows = dict(
            (root, tuple(sorted(rows))) for root, rows in roots.items())
        return {
            "kinds": dict(
                (kind, cls._semantic_fingerprint(tuple(sorted(rows))))
                for kind, rows in kinds.items()),
            "roots": dict(
                (root, cls._semantic_fingerprint(tuple(sorted(rows))))
                for root, rows in roots.items()),
            "prefix_rows": dict(
                (prefix, tuple(sorted(rows)))
                for prefix, rows in prefix_rows.items()),
        }

    def _cached_fingerprint_index(self, fingerprints, wanted_prefixes):
        """Reuse one immutable preparation index across parity projections."""
        prefixes = tuple(wanted_prefixes)
        cached = self._fingerprint_index_cache
        if (cached is not None and cached[0] is fingerprints
                and cached[1] == prefixes):
            return cached[2]
        index = self._fingerprint_index(
            fingerprints, self._incremental_roots,
            self._incremental_kinds, prefixes)
        # Retaining the mapping itself makes an object-ID reuse impossible;
        # the next different preparation replaces this single bounded entry.
        self._fingerprint_index_cache = (fingerprints, prefixes, index)
        return index

    @staticmethod
    def _matches_prefix(path, prefix):
        return str(path) == str(prefix) or str(path).startswith(
            str(prefix) + ".")

    @classmethod
    def _shard_fingerprint(cls, spec, fingerprint_index):
        semantic = [
            ("kind", kind, fingerprint_index["kinds"].get(kind))
            for kind in sorted(spec.dependency_kinds)]
        for prefix in spec.snapshot_prefixes:
            rows = fingerprint_index["prefix_rows"].get(prefix, ())
            semantic.append((
                "snapshot-prefix", prefix, rows))
        semantic.append(("output-scopes", spec.scope_ids))
        # This signature is private in-memory cache state. Exact immutable
        # dependency rows are both cheaper and stronger than hashing each of
        # hundreds of small entity shards independently.
        return tuple(semantic)

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
        identity_parts = []
        for kind in sorted(kinds):
            identity_parts.extend((
                "kind", kind, fingerprint_index["kinds"].get(kind)))
        for root in sorted(roots):
            identity_parts.extend((
                "root", root, fingerprint_index["roots"].get(root)))
        for key in sorted(set(dependency_keys)):
            if (key.kind in kinds
                    or (key.kind == "snapshot-field"
                        and cls._root(key.path) in roots)):
                continue
            identity_parts.extend((
                "dependency", key.kind, key.owner_id, key.path,
                fingerprints.get(key)))
        return joined_identity_hash(tuple(identity_parts))

    @staticmethod
    def _refresh(records, scopes, scope_by_id=None):
        scope_by_id = scope_by_id or dict(
            (value.scope_id, value) for value in scopes)
        refreshed = []
        truth_hashes = {}
        for record in records:
            scope = scope_by_id.get(record.key.scope_id)
            if scope is None:
                raise ValueError(
                    "incremental projector record scope disappeared")
            truth_identity = id(record.truth)
            truth_hash = truth_hashes.get(truth_identity)
            if truth_hash is None:
                truth_hash = structural_hash(record.truth)
                truth_hashes[truth_identity] = truth_hash
            refreshed.append(AtomRecord.create(
                record.key, record.authority, record.truth, scope.validity,
                record.supports, record.provenance_ids, record.lifecycle,
                record.tags, truth_hash=truth_hash))
        return tuple(refreshed)

    @staticmethod
    def _project_checked(projector, snapshot, scopes, fingerprints):
        tracked = _SnapshotAccessRecorder(snapshot)
        records = tuple(projector.project(tracked, scopes, fingerprints))
        declared = frozenset(getattr(
            projector, "incremental_dependency_roots", ()))
        undeclared = sorted(tracked.accessed_roots.difference(declared))
        if undeclared:
            raise ValueError(
                "projector {} read undeclared snapshot roots: {}".format(
                    projector.projector_id, ", ".join(undeclared)))
        return records

    @classmethod
    def _project_shard_checked(
            cls, projector, spec, shard_owners, snapshot, scopes,
            fingerprints):
        tracked = _SnapshotAccessRecorder(snapshot)
        records = tuple(projector.project_shard(
            spec.shard_id, tracked, scopes, fingerprints))
        declared_roots = frozenset(
            cls._root(value) for value in spec.snapshot_prefixes)
        undeclared = sorted(
            tracked.accessed_roots.difference(declared_roots))
        if undeclared:
            raise ValueError(
                "projector {} shard {} read undeclared snapshot roots: {}"
                .format(projector.projector_id, spec.shard_id,
                        ", ".join(undeclared)))
        invalid_scopes = sorted(set(
            record.key.scope_id for record in records).difference(
                spec.scope_ids))
        if invalid_scopes:
            raise ValueError(
                "projector {} shard {} wrote undeclared scopes: {}".format(
                    projector.projector_id, spec.shard_id,
                    ", ".join(invalid_scopes)))
        misowned = tuple(
            record for record in records
            if cls._record_shard_id(projector, shard_owners, record)
            != spec.shard_id)
        if misowned:
            raise ValueError(
                "projector {} shard {} wrote records owned by another "
                "shard".format(projector.projector_id, spec.shard_id))
        cls._validate_shard_dependencies(projector, spec, records)
        return records

    @staticmethod
    def _dependency_keys(records):
        return tuple(sorted(set(
            dependency.key
            for record in records for support in record.supports
            for dependency in support.dependencies)))

    @classmethod
    def _validate_shard_dependencies(cls, projector, spec, records):
        undeclared = []
        for key in cls._dependency_keys(records):
            covered = key.kind in spec.dependency_kinds
            if key.kind == "snapshot-field":
                covered = any(
                    cls._matches_prefix(key.path, prefix)
                    for prefix in spec.snapshot_prefixes)
            if not covered:
                undeclared.append(key)
        if undeclared:
            raise ValueError(
                "projector {} shard {} emitted undeclared dependencies: {}"
                .format(
                    projector.projector_id, spec.shard_id,
                    ", ".join("{}:{}".format(value.kind, value.path)
                              for value in undeclared)))

    @classmethod
    def _shard_specs(cls, projector, snapshot, scopes):
        if not hasattr(projector, "projection_shards"):
            return ()
        specs = tuple(projector.projection_shards(snapshot, scopes))
        if not all(isinstance(value, ProjectionShardSpec) for value in specs):
            raise TypeError(
                "projection_shards must return ProjectionShardSpec values")
        ids = tuple(value.shard_id for value in specs)
        if len(ids) != len(set(ids)):
            raise ValueError("projection shard IDs must be unique")
        component_roots = frozenset(getattr(
            projector, "incremental_dependency_roots", ()))
        component_kinds = frozenset(getattr(
            projector, "incremental_dependency_kinds", ()))
        known_scope_ids = frozenset(value.scope_id for value in scopes)
        scope_owners = {}
        for spec in specs:
            extra_roots = frozenset(
                cls._root(value)
                for value in spec.snapshot_prefixes).difference(
                    component_roots)
            extra_kinds = spec.dependency_kinds.difference(component_kinds)
            if extra_roots or extra_kinds:
                raise ValueError(
                    "projection shard dependencies exceed projector "
                    "declaration: {}".format(spec.shard_id))
            missing_scopes = frozenset(spec.scope_ids).difference(
                known_scope_ids)
            if missing_scopes:
                raise ValueError(
                    "projection shard references unknown output scopes: {}"
                    .format(spec.shard_id))
            for scope_id in spec.scope_ids:
                scope_owners.setdefault(scope_id, []).append(spec.shard_id)
        overlapping = tuple(sorted(
            scope_id for scope_id, owners in scope_owners.items()
            if len(owners) > 1))
        if (overlapping
                and not hasattr(projector, "projection_shard_for_record")):
            raise ValueError(
                "overlapping projection shard scopes require explicit "
                "record ownership: {}".format(", ".join(overlapping)))
        return specs

    @staticmethod
    def _shard_owners(specs):
        owners = {}
        for spec in specs:
            for scope_id in spec.scope_ids:
                owners.setdefault(scope_id, []).append(spec.shard_id)
        return dict(
            (scope_id, frozenset(shard_ids))
            for scope_id, shard_ids in owners.items())

    @staticmethod
    def _record_shard_id(projector, shard_owners, record):
        candidates = shard_owners.get(record.key.scope_id, frozenset())
        if not candidates:
            return None
        if len(candidates) == 1:
            return next(iter(candidates))
        owner = projector.projection_shard_for_record(record)
        if owner not in candidates:
            raise ValueError(
                "projector {} returned invalid shard owner {} for {}"
                .format(projector.projector_id, owner, record.atom_id))
        return owner

    @classmethod
    def _partition_records(cls, projector, specs, records):
        shard_owners = cls._shard_owners(specs)
        partitions = dict((spec.shard_id, []) for spec in specs)
        unassigned = []
        for record in records:
            shard_id = cls._record_shard_id(
                projector, shard_owners, record)
            if shard_id is None:
                unassigned.append(record.key.scope_id)
            else:
                partitions[shard_id].append(record)
        if unassigned:
            raise ValueError(
                "projector {} emitted records outside shard scopes: {}".format(
                    projector.projector_id,
                    ", ".join(sorted(set(unassigned)))))
        result = {}
        for spec in specs:
            projected = tuple(partitions[spec.shard_id])
            cls._validate_shard_dependencies(projector, spec, projected)
            result[spec.shard_id] = projected
        return result

    @classmethod
    def _component_state(
            cls, projector, projected, scopes, fingerprints,
            fingerprint_index, component_scope_ids, specs=(),
            shard_fingerprints=None, shard_partitions=None):
        # Sharded components are invalidated exclusively through each checked
        # shard signature. Rebuilding a redundant component-wide dependency
        # union adds a full scan of every output record on every turn.
        dependency_keys = (
            () if specs else cls._dependency_keys(projected))
        state = {
            "dependency_keys": dependency_keys,
            "fingerprint": (
                None if specs else cls._component_fingerprint(
                    projector, fingerprints, fingerprint_index,
                    dependency_keys)),
            "records": projected,
            "scope_ids": component_scope_ids,
        }
        if specs:
            shard_fingerprints = shard_fingerprints or dict(
                (spec.shard_id, cls._shard_fingerprint(
                    spec, fingerprint_index)) for spec in specs)
            partitions = (
                shard_partitions if shard_partitions is not None else
                cls._partition_records(projector, specs, projected))
            state["shards"] = dict(
                (spec.shard_id, {
                    "fingerprint": shard_fingerprints[spec.shard_id],
                    "records": partitions[spec.shard_id],
                    "spec": spec,
                }) for spec in specs)
        return state

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
        specs_by_projector = dict(
            (projector.projector_id,
             self._shard_specs(projector, snapshot, scopes))
            for projector in self.projectors)
        fingerprint_index = self._cached_fingerprint_index(
            fingerprints,
            tuple(
                prefix for specs in specs_by_projector.values()
                for spec in specs for prefix in spec.snapshot_prefixes))
        for projector in self.projectors:
            specs = specs_by_projector[projector.projector_id]
            projected = self._project_checked(
                projector, snapshot, scopes, fingerprints)
            components[projector.projector_id] = self._component_state(
                projector, projected, scopes, fingerprints,
                fingerprint_index,
                self._component_scopes.get(snapshot.snapshot_id, {}).get(
                    projector.projector_id, ()), specs)
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
        scope_by_id = dict((value.scope_id, value) for value in scopes)
        specs_by_projector = dict(
            (projector.projector_id,
             self._shard_specs(projector, snapshot, scopes))
            for projector in self.projectors)
        fingerprint_index = self._cached_fingerprint_index(
            fingerprints,
            tuple(
                prefix for specs in specs_by_projector.values()
                for spec in specs for prefix in spec.snapshot_prefixes))
        records = []
        components = {}
        reused = []
        recomputed = []
        reused_shards = []
        recomputed_shards = []
        reused_shard_records = []
        recomputed_shard_records = []
        reused_record_count = 0
        recomputed_record_count = 0
        for projector in self.projectors:
            projector_id = projector.projector_id
            cached = prior.get(projector_id)
            current_scope_ids = current_scopes.get(projector_id, ())
            specs = specs_by_projector[projector_id]
            if specs:
                shard_owners = self._shard_owners(specs)
                shard_fingerprints = dict(
                    (spec.shard_id, self._shard_fingerprint(
                        spec, fingerprint_index)) for spec in specs)
                cached_shards = (
                    {} if cached is None else cached.get("shards", {}))
                shard_records = []
                shard_partitions = {}
                projector_recomputed = False
                projector_reused = False
                for spec in specs:
                    prior_shard = cached_shards.get(spec.shard_id)
                    fingerprint = shard_fingerprints[spec.shard_id]
                    can_reuse_shard = bool(
                        prior_shard is not None
                        and prior_shard["spec"] == spec
                        and prior_shard["fingerprint"] == fingerprint)
                    metric_id = "{}/{}".format(
                        projector_id, spec.shard_id)
                    if can_reuse_shard:
                        values = self._refresh(
                            prior_shard["records"], scopes, scope_by_id)
                        reused_shards.append(metric_id)
                        reused_shard_records.append((metric_id, len(values)))
                        reused_record_count += len(values)
                        projector_reused = True
                    else:
                        values = self._project_shard_checked(
                            projector, spec, shard_owners, snapshot, scopes,
                            fingerprints)
                        recomputed_shards.append(metric_id)
                        recomputed_shard_records.append(
                            (metric_id, len(values)))
                        recomputed_record_count += len(values)
                        projector_recomputed = True
                    shard_partitions[spec.shard_id] = values
                    shard_records.extend(values)
                projected = tuple(sorted(
                    shard_records, key=lambda value: value.atom_id))
                components[projector_id] = self._component_state(
                    projector, projected, scopes, fingerprints,
                    fingerprint_index, current_scope_ids, specs,
                    shard_fingerprints, shard_partitions)
                if projector_recomputed:
                    recomputed.append(projector_id)
                if projector_reused:
                    reused.append(projector_id)
                records.extend(projected)
                continue
            fingerprint = self._component_fingerprint(
                projector, fingerprints, fingerprint_index,
                () if cached is None else cached["dependency_keys"])
            can_reuse = bool(
                cached is not None
                and fingerprint is not None
                and fingerprint == cached["fingerprint"]
                and current_scope_ids == cached["scope_ids"])
            if can_reuse:
                projected = self._refresh(
                    cached["records"], scopes, scope_by_id)
                dependency_keys = cached["dependency_keys"]
                reused.append(projector_id)
                reused_record_count += len(projected)
            else:
                projected = self._project_checked(
                    projector, snapshot, scopes, fingerprints)
                dependency_keys = self._dependency_keys(projected)
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
            "recomputed_shard_ids": tuple(recomputed_shards),
            "recomputed_shard_records": tuple(recomputed_shard_records),
            "reused_shard_ids": tuple(reused_shards),
            "reused_shard_records": tuple(reused_shard_records),
        }
        self._trim(self._incremental_metrics)
        return tuple(sorted(records, key=lambda value: value.atom_id))

    def incremental_metrics(self, snapshot_id):
        return dict(self._incremental_metrics.get(str(snapshot_id), {
            "recomputed_projector_ids": (),
            "recomputed_record_count": 0,
            "reused_projector_ids": (),
            "reused_record_count": 0,
            "recomputed_shard_ids": (),
            "recomputed_shard_records": (),
            "reused_shard_ids": (),
            "reused_shard_records": (),
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
            "recomputed_shard_ids": (),
            "recomputed_shard_records": (),
            "reused_shard_ids": (),
            "reused_shard_records": (),
        }
