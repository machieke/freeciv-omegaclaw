"""In-memory dependency-aware FDAS revision store."""

import gc
import threading
from dataclasses import dataclass, field

from ...events.schema import structural_hash
from .delta import (
    SnapshotDelta,
    snapshot_dependency_fingerprints,
    snapshot_document,
)
from .dependencies import DependencyIndex
from .predicates import legacy_predicate_registry
from .scopes import snapshot_scopes
from .transaction import AtomSpaceTransaction


_FDAS_BUILD_LOCK = threading.RLock()


def _without_cyclic_gc(function):
    """Keep cyclic-GC scans out of the bounded immutable build transaction."""
    def guarded(*args, **kwargs):
        with _FDAS_BUILD_LOCK:
            enabled = gc.isenabled()
            if enabled:
                gc.disable()
            try:
                return function(*args, **kwargs)
            finally:
                if enabled:
                    gc.enable()
    return guarded


@dataclass(frozen=True)
class MaterializationMetrics:
    cold_build: bool
    total_records: int
    recomputed_records: int
    refreshed_records: int
    removed_records: int
    invalidated_supports: int
    affected_atoms: int
    unsupported_atoms: int
    delta_hash: str
    recomputed_projector_ids: tuple = ()
    reused_projector_ids: tuple = ()
    rich_recomputed_records: int = 0
    rich_reused_records: int = 0

    @property
    def incremental_recomputation_ratio(self):
        if self.total_records <= 0:
            return 0.0
        return float(self.recomputed_records) / float(self.total_records)

    def to_dict(self):
        return {
            "affected_atoms": self.affected_atoms,
            "cold_build": self.cold_build,
            "delta_hash": self.delta_hash,
            "invalidated_supports": self.invalidated_supports,
            "incremental_recomputation_ratio": (
                self.incremental_recomputation_ratio),
            "recomputed_records": self.recomputed_records,
            "recomputed_projector_ids": list(
                self.recomputed_projector_ids),
            "refreshed_records": self.refreshed_records,
            "removed_records": self.removed_records,
            "reused_projector_ids": list(self.reused_projector_ids),
            "rich_recomputed_records": self.rich_recomputed_records,
            "rich_reused_records": self.rich_reused_records,
            "total_records": self.total_records,
            "unsupported_atoms": self.unsupported_atoms,
        }


@dataclass(frozen=True)
class DependentAtomSpaceRevision:
    revision_id: str
    snapshot_id: str
    records: tuple
    scopes: tuple
    build_hash: str
    dependency_index: DependencyIndex
    delta: object = field(default=None, compare=False)
    metrics: object = field(default=None, compare=False)

    def __post_init__(self):
        for value, name in (
                (self.revision_id, "revision ID"),
                (self.snapshot_id, "revision snapshot ID"),
                (self.build_hash, "revision build hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("{} is required".format(name))
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "scopes", tuple(self.scopes))
        if not isinstance(self.dependency_index, DependencyIndex):
            raise TypeError("revision requires DependencyIndex")

    def record(self, atom_id):
        return self.dependency_index.atom_by_id.get(str(atom_id))

    def to_dict(self):
        return {
            "build_hash": self.build_hash,
            "delta": self.delta.to_dict() if self.delta is not None else None,
            "metrics": (
                self.metrics.to_dict() if self.metrics is not None else None),
            "records": [value.to_dict() for value in self.records],
            "revision_id": self.revision_id,
            "scopes": [value.to_dict() for value in self.scopes],
            "snapshot_id": self.snapshot_id,
        }


@dataclass(frozen=True)
class DifferentialVerification:
    equivalent: bool
    incremental_revision_id: str
    cold_revision_id: str
    mismatch_categories: tuple
    verification_hash: str

    def to_dict(self):
        return {
            "cold_revision_id": self.cold_revision_id,
            "equivalent": self.equivalent,
            "incremental_revision_id": self.incremental_revision_id,
            "mismatch_categories": list(self.mismatch_categories),
            "verification_hash": self.verification_hash,
        }


class RevisionLease(object):
    def __init__(self, store, revision_id):
        self._store = store
        self.revision_id = str(revision_id)
        self._released = False

    @property
    def revision(self):
        revision = self._store.revision(self.revision_id)
        if revision is None:
            raise RuntimeError("leased FDAS revision is unavailable")
        return revision

    def release(self):
        if not self._released:
            self._store._release_lease(self.revision_id)
            self._released = True

    def __enter__(self):
        return self.revision

    def __exit__(self, _type, _value, _traceback):
        self.release()


class DependentAtomSpaceStore(object):
    """Prepare, publish, retain, and verify immutable dependent revisions."""

    def __init__(self, predicate_registry=None, revision_retention=4,
                 lock=None, domain_projector=None, maximum_atoms=None):
        if (isinstance(revision_retention, bool)
                or not isinstance(revision_retention, int)
                or revision_retention < 1):
            raise ValueError("revision retention must be positive")
        if domain_projector is not None and predicate_registry is not None:
            raise ValueError(
                "domain projector owns the combined predicate registry")
        if (maximum_atoms is not None
                and (isinstance(maximum_atoms, bool)
                     or not isinstance(maximum_atoms, int)
                     or maximum_atoms < 1)):
            raise ValueError("global atom budget must be positive")
        self.domain_projector = domain_projector
        self.predicate_registry = (
            domain_projector.predicate_registry
            if domain_projector is not None else
            predicate_registry or legacy_predicate_registry())
        self.revision_retention = revision_retention
        self.maximum_atoms = maximum_atoms
        self._lock = lock or threading.RLock()
        self._revisions = {}
        self._current = {}
        self._snapshots = {}
        self._revision_order = {}
        self._lease_counts = {}

    def bind_coordinator_lock(self, lock):
        """Bind an unused store to its snapshot coordinator's atomic lock."""
        if lock is None:
            raise ValueError("coordinator lock is required")
        with self._lock:
            if self._revisions or self._current or self._snapshots:
                if self._lock is not lock:
                    raise RuntimeError(
                        "cannot rebind a populated FDAS store")
                return self
            self._lock = lock
        return self

    @staticmethod
    def _snapshot_key(snapshot):
        return str(snapshot.identity.game_id), int(snapshot.player_id)

    @staticmethod
    def _validate_order(prior, snapshot):
        if prior is None:
            return
        if snapshot.turn < prior.turn:
            raise ValueError("FDAS snapshot turn regression")
        if (snapshot.turn == prior.turn
                and snapshot.identity.source_seq <= prior.identity.source_seq
                and snapshot.snapshot_id != prior.snapshot_id):
            raise ValueError("FDAS source sequence must increase within turn")

    @_without_cyclic_gc
    def prepare(self, snapshot, prior_snapshot=None, prior_revision=None,
                cold=False):
        """Build a revision without changing the store's visible current pair."""
        from .compatibility import (
            project_legacy_records,
            project_legacy_records_incremental,
        )

        self._validate_order(prior_snapshot, snapshot)
        scopes = (
            self.domain_projector.scopes(snapshot)
            if self.domain_projector is not None else snapshot_scopes(snapshot))
        current_document = snapshot_document(snapshot)
        prior_document = (
            snapshot_document(prior_snapshot)
            if prior_snapshot is not None else {})
        delta = SnapshotDelta.between(
            prior_snapshot,
            snapshot,
            prior_document=prior_document,
            current_document=current_document,
        )
        fingerprints = snapshot_dependency_fingerprints(
            snapshot, current_document)
        if self.domain_projector is not None:
            fingerprints = self.domain_projector.extend_fingerprints(
                fingerprints)
        if cold or prior_revision is None:
            records = project_legacy_records(
                snapshot, scopes, fingerprints)
            projection_metrics = {
                "recomputed_records": len(records),
                "refreshed_records": 0,
                "removed_records": 0,
            }
        else:
            records, projection_metrics = project_legacy_records_incremental(
                snapshot, scopes, prior_revision, fingerprints)
        if self.domain_projector is not None:
            used_incremental_domain = bool(
                not cold and prior_snapshot is not None
                and prior_revision is not None
                and hasattr(self.domain_projector, "project_incremental"))
            if used_incremental_domain:
                domain_records = self.domain_projector.project_incremental(
                    snapshot, scopes, fingerprints, prior_snapshot,
                    prior_revision)
            else:
                domain_records = self.domain_projector.project(
                    snapshot, scopes, fingerprints)
            records = tuple(records) + tuple(domain_records)
            component_metrics = (
                self.domain_projector.incremental_metrics(
                    snapshot.snapshot_id)
                if used_incremental_domain and hasattr(
                    self.domain_projector, "incremental_metrics") else {
                        "recomputed_projector_ids": tuple(getattr(
                            self.domain_projector,
                            "component_projector_ids", ())),
                        "recomputed_record_count": len(domain_records),
                        "reused_projector_ids": (),
                        "reused_record_count": 0,
                    })
            projection_metrics["recomputed_records"] += component_metrics[
                "recomputed_record_count"]
            projection_metrics["refreshed_records"] += component_metrics[
                "reused_record_count"]
        else:
            component_metrics = {
                "recomputed_projector_ids": (),
                "recomputed_record_count": 0,
                "reused_projector_ids": (),
                "reused_record_count": 0,
            }
        transaction = AtomSpaceTransaction(
            snapshot.snapshot_id, self.predicate_registry, scopes,
            maximum_atoms=self.maximum_atoms)
        for record in records:
            transaction.apply(record)
        revision_id = transaction.commit()
        dependency_index = transaction.dependency_index
        stale = dependency_index.stale_dependencies(
            fingerprints)
        if stale:
            raise ValueError(
                "FDAS commit contains stale dependencies: {}".format(stale))
        if prior_revision is None:
            invalidation = None
        else:
            prior_fingerprints = {}
            for support in prior_revision.dependency_index.support_by_id.values():
                for dependency in support.dependencies:
                    existing = prior_fingerprints.get(dependency.key)
                    if (existing is not None
                            and existing != dependency.fingerprint):
                        raise ValueError(
                            "prior revision has inconsistent dependency "
                            "fingerprints")
                    prior_fingerprints[dependency.key] = dependency.fingerprint
            changed_keys = set(delta.changed_dependency_keys)
            changed_keys.update(
                key for key, fingerprint in prior_fingerprints.items()
                if fingerprints.get(key) != fingerprint)
            invalidation = prior_revision.dependency_index.invalidate(
                changed_keys)
        metrics = MaterializationMetrics(
            bool(cold or prior_revision is None),
            len(transaction.records),
            projection_metrics["recomputed_records"],
            projection_metrics["refreshed_records"],
            projection_metrics["removed_records"],
            len(invalidation.invalid_support_ids) if invalidation else 0,
            len(invalidation.affected_atom_ids) if invalidation else 0,
            len(invalidation.unsupported_atom_ids) if invalidation else 0,
            delta.delta_hash,
            tuple(component_metrics["recomputed_projector_ids"]),
            tuple(component_metrics["reused_projector_ids"]),
            int(component_metrics["recomputed_record_count"]),
            int(component_metrics["reused_record_count"]),
        )
        build_hash = revision_id[len("fdas-revision-"):]
        return DependentAtomSpaceRevision(
            revision_id,
            snapshot.snapshot_id,
            transaction.records,
            transaction.scopes,
            build_hash,
            dependency_index,
            delta,
            metrics,
        )

    def _collect_key(self, key):
        order = self._revision_order.get(key, [])
        current_id = self._current.get(key)
        kept = []
        unleased_seen = 0
        for revision_id in reversed(order):
            protected = (
                revision_id == current_id
                or self._lease_counts.get(revision_id, 0) > 0)
            if protected or unleased_seen < self.revision_retention - 1:
                kept.append(revision_id)
                if not protected:
                    unleased_seen += 1
            else:
                self._revisions.pop(revision_id, None)
        self._revision_order[key] = list(reversed(kept))

    def publish(self, snapshot, revision):
        if revision.snapshot_id != snapshot.snapshot_id:
            raise ValueError("FDAS revision does not match snapshot")
        key = self._snapshot_key(snapshot)
        with self._lock:
            prior = self._snapshots.get(key)
            self._validate_order(prior, snapshot)
            existing = self._revisions.get(revision.revision_id)
            if existing is not None and existing != revision:
                raise ValueError("FDAS revision ID collision")
            self._revisions[revision.revision_id] = revision
            order = self._revision_order.setdefault(key, [])
            if revision.revision_id not in order:
                order.append(revision.revision_id)
            self._snapshots[key] = snapshot
            self._current[key] = revision.revision_id
            self._collect_key(key)
        return revision

    def build(self, snapshot):
        """Cold-build and publish a complete revision."""
        revision = self.prepare(snapshot, cold=True)
        return self.publish(snapshot, revision)

    def update(self, snapshot):
        """Incrementally prepare and publish the next complete revision."""
        key = self._snapshot_key(snapshot)
        with self._lock:
            prior_snapshot = self._snapshots.get(key)
            prior_revision = self.current(*key)
            if (prior_snapshot is not None
                    and prior_snapshot.snapshot_id == snapshot.snapshot_id):
                return prior_revision
        revision = self.prepare(
            snapshot, prior_snapshot, prior_revision, cold=False)
        return self.publish(snapshot, revision)

    def rematerialize(self, snapshot):
        """Refresh non-snapshot sources against the same snapshot identity.

        Operation and belief stores can advance while the authoritative game
        snapshot remains unchanged.  This explicit method avoids making the
        ordinary idempotent ``update`` path surprising while still committing
        a coherent new FDAS revision for those source revisions.
        """
        key = self._snapshot_key(snapshot)
        with self._lock:
            prior_snapshot = self._snapshots.get(key)
            prior_revision = self.current(*key)
        if prior_snapshot is None or prior_revision is None:
            return self.build(snapshot)
        if prior_snapshot.snapshot_id != snapshot.snapshot_id:
            raise ValueError(
                "rematerialization requires the current snapshot identity")
        revision = self.prepare(
            snapshot, prior_snapshot, prior_revision, cold=False)
        return self.publish(snapshot, revision)

    def prepare_verified_incremental(
            self, snapshot, prior_snapshot, prior_revision):
        """Return the already-built incremental revision and parity proof."""
        incremental = self.prepare(
            snapshot, prior_snapshot, prior_revision, cold=False)
        cold = self.prepare(
            snapshot, prior_snapshot, prior_revision, cold=True)
        mismatches = []
        for name in (
                "revision_id", "build_hash", "records", "scopes",
                "dependency_index"):
            if getattr(incremental, name) != getattr(cold, name):
                mismatches.append(name)
        semantic = {
            "cold_revision_id": cold.revision_id,
            "incremental_revision_id": incremental.revision_id,
            "mismatch_categories": mismatches,
        }
        verification = DifferentialVerification(
            not mismatches,
            incremental.revision_id,
            cold.revision_id,
            tuple(mismatches),
            structural_hash(semantic),
        )
        return incremental, verification

    def verify_incremental(self, snapshot, prior_snapshot, prior_revision):
        _incremental, verification = self.prepare_verified_incremental(
            snapshot, prior_snapshot, prior_revision)
        return verification

    def current(self, game_id, player_id):
        with self._lock:
            revision_id = self._current.get((str(game_id), int(player_id)))
            return self._revisions.get(revision_id)

    def revision(self, revision_id):
        with self._lock:
            return self._revisions.get(str(revision_id))

    def query_current(self, game_id, player_id):
        from .query import RevisionQueryContext
        revision = self.current(game_id, player_id)
        if revision is None:
            raise KeyError("no current FDAS revision")
        return RevisionQueryContext(
            revision,
            expected_snapshot_id=revision.snapshot_id,
            decision_safe=True,
        )

    def query_revision(self, revision_id, expected_snapshot_id=None,
                       decision_safe=False):
        from .query import RevisionQueryContext
        revision = self.revision(revision_id)
        if revision is None:
            raise KeyError("unknown FDAS revision: {}".format(revision_id))
        return RevisionQueryContext(
            revision,
            expected_snapshot_id=expected_snapshot_id,
            decision_safe=decision_safe,
        )

    def lease(self, revision_id):
        revision_id = str(revision_id)
        with self._lock:
            if revision_id not in self._revisions:
                raise KeyError("unknown FDAS revision: {}".format(revision_id))
            self._lease_counts[revision_id] = (
                self._lease_counts.get(revision_id, 0) + 1)
        return RevisionLease(self, revision_id)

    def _release_lease(self, revision_id):
        with self._lock:
            count = self._lease_counts.get(revision_id, 0)
            if count < 1:
                raise RuntimeError("FDAS revision lease is not active")
            if count == 1:
                del self._lease_counts[revision_id]
            else:
                self._lease_counts[revision_id] = count - 1
            for key in tuple(self._revision_order):
                self._collect_key(key)
