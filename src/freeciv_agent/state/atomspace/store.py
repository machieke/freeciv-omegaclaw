"""In-memory full-build FDAS component store."""

import threading
from dataclasses import dataclass
from .predicates import legacy_predicate_registry
from .scopes import snapshot_scopes
from .transaction import AtomSpaceTransaction


@dataclass(frozen=True)
class DependentAtomSpaceRevision:
    revision_id: str
    snapshot_id: str
    records: tuple
    scopes: tuple
    build_hash: str

    def __post_init__(self):
        for value, name in (
                (self.revision_id, "revision ID"),
                (self.snapshot_id, "revision snapshot ID"),
                (self.build_hash, "revision build hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("{} is required".format(name))
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "scopes", tuple(self.scopes))

    def record(self, atom_id):
        return next((
            value for value in self.records
            if value.atom_id == atom_id
        ), None)

    def to_dict(self):
        return {
            "build_hash": self.build_hash,
            "records": [value.to_dict() for value in self.records],
            "revision_id": self.revision_id,
            "scopes": [value.to_dict() for value in self.scopes],
            "snapshot_id": self.snapshot_id,
        }


class DependentAtomSpaceStore(object):
    """Build complete immutable revisions; incrementality starts in Phase 2."""

    def __init__(self, predicate_registry=None):
        self.predicate_registry = (
            predicate_registry or legacy_predicate_registry())
        self._lock = threading.RLock()
        self._revisions = {}
        self._current = {}

    @staticmethod
    def _snapshot_key(snapshot):
        return str(snapshot.identity.game_id), int(snapshot.player_id)

    def build(self, snapshot):
        from .compatibility import project_legacy_records

        scopes = snapshot_scopes(snapshot)
        transaction = AtomSpaceTransaction(
            snapshot.snapshot_id, self.predicate_registry, scopes)
        for record in project_legacy_records(snapshot, scopes):
            transaction.apply(record)
        revision_id = transaction.commit()
        records = transaction.records
        scopes = transaction.scopes
        # AtomSpaceTransaction already hashes the complete canonical record and
        # scope material. Reuse that digest rather than serializing a potentially
        # large full-build revision a second time.
        build_hash = revision_id[len("fdas-revision-"):]
        revision = DependentAtomSpaceRevision(
            revision_id, snapshot.snapshot_id, records, scopes, build_hash)
        with self._lock:
            existing = self._revisions.get(revision_id)
            if existing is not None and existing != revision:
                raise ValueError("FDAS revision ID collision")
            self._revisions[revision_id] = revision
            self._current[self._snapshot_key(snapshot)] = revision_id
        return revision

    def current(self, game_id, player_id):
        with self._lock:
            revision_id = self._current.get((str(game_id), int(player_id)))
            return self._revisions.get(revision_id)

    def revision(self, revision_id):
        with self._lock:
            return self._revisions.get(str(revision_id))
