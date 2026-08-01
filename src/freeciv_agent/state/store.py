"""Thread-safe transactional replacement store for authoritative snapshots."""

import threading

from .atomspace.compatibility import legacy_view_from_revision
from .atomspace.store import DependentAtomSpaceStore


class SnapshotConflict(RuntimeError):
    pass


class SnapshotStore(object):
    def __init__(self, dependent_atomspace_store=None,
                 atomspace_mode="dependent"):
        if atomspace_mode not in ("dependent", "legacy"):
            raise ValueError("atomspace mode must be dependent or legacy")
        self.atomspace_mode = atomspace_mode
        self._lock = threading.RLock()
        self._snapshots = {}
        self._atomspaces = {}
        self._dependent_revisions = {}
        self._dependent_store = (
            dependent_atomspace_store
            or DependentAtomSpaceStore(lock=self._lock))
        self._dependent_store.bind_coordinator_lock(self._lock)

    @staticmethod
    def _key(snapshot):
        return snapshot.identity.game_id, snapshot.player_id

    def replace(self, snapshot):
        """Atomically replace snapshot and every authoritative atom for its key."""
        key = self._key(snapshot)
        with self._lock:
            prior = self._snapshots.get(key)
            if prior is not None:
                if snapshot.turn < prior.turn:
                    raise SnapshotConflict("turn regression")
                if snapshot.turn == prior.turn and snapshot.identity.source_seq <= prior.identity.source_seq:
                    if snapshot.snapshot_id == prior.snapshot_id:
                        return prior
                    raise SnapshotConflict("source_seq must increase within a turn")
            prior_revision = self._dependent_revisions.get(key)
            if self.atomspace_mode == "legacy":
                from .atoms import _build_legacy_atomspaces

                revision = None
                projected = _build_legacy_atomspaces(snapshot)
            else:
                try:
                    revision = self._dependent_store.prepare(
                        snapshot, prior, prior_revision, cold=False)
                except ValueError as error:
                    raise SnapshotConflict(
                        "dependent projection rejected snapshot: {}".format(
                            error))
                projected = legacy_view_from_revision(revision)
                self._dependent_store.publish(snapshot, revision)
            self._snapshots[key] = snapshot
            self._atomspaces[key] = projected
            if revision is None:
                self._dependent_revisions.pop(key, None)
            else:
                self._dependent_revisions[key] = revision
        return snapshot

    def current(self, game_id, player_id):
        with self._lock:
            return self._snapshots.get((str(game_id), int(player_id)))

    def current_atomspaces(self, game_id, player_id):
        with self._lock:
            return self._atomspaces.get((str(game_id), int(player_id)))

    def current_dependent_revision(self, game_id, player_id):
        with self._lock:
            return self._dependent_revisions.get(
                (str(game_id), int(player_id)))

    def current_pair(self, game_id, player_id):
        """Return an atomically consistent snapshot/FDAS revision pair."""
        key = (str(game_id), int(player_id))
        with self._lock:
            return self._snapshots.get(key), self._dependent_revisions.get(key)

    def lease_dependent_revision(self, game_id, player_id):
        with self._lock:
            revision = self._dependent_revisions.get(
                (str(game_id), int(player_id)))
            if revision is None:
                raise SnapshotConflict("no current dependent revision")
            return self._dependent_store.lease(revision.revision_id)

    def require_snapshot(self, snapshot_id):
        with self._lock:
            matches = [item for item in self._snapshots.values()
                       if item.snapshot_id == snapshot_id]
        if not matches:
            raise SnapshotConflict("snapshot is not current: {}".format(snapshot_id))
        return matches[0]

    def emit_replace(self, snapshot, writer, caused_by=None):
        self.replace(snapshot)
        return writer.emit("state_snapshot", snapshot.turn, snapshot.event_payload(),
                           caused_by=caused_by)
