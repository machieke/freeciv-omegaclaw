"""Thread-safe transactional replacement store for authoritative snapshots."""

import threading

from .atoms import build_atomspaces


class SnapshotConflict(RuntimeError):
    pass


class SnapshotStore(object):
    def __init__(self):
        self._lock = threading.RLock()
        self._snapshots = {}
        self._atomspaces = {}

    @staticmethod
    def _key(snapshot):
        return snapshot.identity.game_id, snapshot.player_id

    def replace(self, snapshot):
        """Atomically replace snapshot and every authoritative atom for its key."""
        key = self._key(snapshot)
        projected = build_atomspaces(snapshot)
        with self._lock:
            prior = self._snapshots.get(key)
            if prior is not None:
                if snapshot.turn < prior.turn:
                    raise SnapshotConflict("turn regression")
                if snapshot.turn == prior.turn and snapshot.identity.source_seq <= prior.identity.source_seq:
                    if snapshot.snapshot_id == prior.snapshot_id:
                        return prior
                    raise SnapshotConflict("source_seq must increase within a turn")
            self._snapshots[key] = snapshot
            self._atomspaces[key] = projected
        return snapshot

    def current(self, game_id, player_id):
        with self._lock:
            return self._snapshots.get((str(game_id), int(player_id)))

    def current_atomspaces(self, game_id, player_id):
        with self._lock:
            return self._atomspaces.get((str(game_id), int(player_id)))

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
