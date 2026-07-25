"""Append-only, turn-sequenced V0 event writer."""

import datetime
import json
import os
import threading
import uuid

from .schema import SCHEMA_VERSION, assert_event_schema, canonical_json_bytes


class EventWriteError(RuntimeError):
    pass


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


class EventWriter(object):
    """Emit validated events with one monotonic sequence per turn.

    A single ``os.write`` under ``O_APPEND`` persists each complete JSONL record.
    Parents must already have been emitted by this writer, which makes causal cycles
    impossible at the source boundary.
    """

    def __init__(self, path, game_id, schema_version=SCHEMA_VERSION,
                 clock=None, id_factory=None, resume=False, durable=True,
                 sync_mode="event"):
        self.path = os.path.abspath(path)
        self.game_id = str(game_id)
        self.schema_version = schema_version
        self.clock = clock or utc_now
        self.id_factory = id_factory or (lambda: uuid.uuid4().hex)
        self.durable = bool(durable)
        if sync_mode not in ("event", "turn"):
            raise ValueError("sync_mode must be event or turn")
        self.sync_mode = sync_mode
        self._lock = threading.Lock()
        self._next_seq = {}
        self._emitted_ids = set()
        self._last_turn = None
        self._dirty = False
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if os.path.exists(self.path) and os.path.getsize(self.path):
            if not resume:
                raise EventWriteError("event log already exists: {}".format(self.path))
            self._resume_existing()

    def _resume_existing(self):
        from .validator import validate_file
        report = validate_file(self.path)
        if not report.valid:
            raise EventWriteError("cannot resume invalid event log: {}".format(report.errors[0].code))
        with open(self.path, encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                event = json.loads(line)
                if event["game_id"] != self.game_id:
                    raise EventWriteError("resume game_id mismatch")
                self._emitted_ids.add(event["event_id"])
                self._next_seq[event["turn"]] = event["seq"] + 1
                self._last_turn = event["turn"]

    def emit(self, event_type, turn, payload, caused_by=None, event_id=None, ts=None):
        turn = int(turn)
        with self._lock:
            if self._last_turn is not None and turn < self._last_turn:
                raise EventWriteError(
                    "turn regression: {} after {}".format(turn, self._last_turn))
            parents = list(caused_by or [])
            missing = [parent for parent in parents if parent not in self._emitted_ids]
            if missing:
                raise EventWriteError("causal parents have not been emitted: {}".format(missing))
            eid = str(event_id or self.id_factory())
            if eid in self._emitted_ids:
                raise EventWriteError("duplicate event_id: {}".format(eid))
            seq = self._next_seq.get(turn, 0)
            event = {
                "schema_version": self.schema_version,
                "event_id": eid,
                "game_id": self.game_id,
                "turn": turn,
                "seq": seq,
                "ts": ts or self.clock(),
                "type": str(event_type),
                "caused_by": parents,
                "payload": payload,
            }
            assert_event_schema(event)
            line = canonical_json_bytes(event) + b"\n"
            # In turn mode, make the completed prior turn durable before any
            # record from its successor becomes visible. Each individual line
            # remains one atomic O_APPEND write.
            if (self.durable and self.sync_mode == "turn"
                    and self._dirty and self._last_turn is not None
                    and turn > self._last_turn):
                self._sync_path()
                self._dirty = False
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            fd = os.open(self.path, flags, 0o600)
            try:
                written = os.write(fd, line)
                if written != len(line):
                    raise EventWriteError("short event-log write: {} of {}".format(written, len(line)))
                self._dirty = True
                if (self.durable and (
                        self.sync_mode == "event"
                        or event["type"] == "run_completed")):
                    os.fsync(fd)
                    self._dirty = False
            finally:
                os.close(fd)
            self._next_seq[turn] = seq + 1
            self._emitted_ids.add(eid)
            self._last_turn = turn
            return event

    def _sync_path(self):
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def sync(self):
        """Force all records emitted so far to stable storage."""
        if not self.durable or not self._dirty or not os.path.exists(self.path):
            return
        with self._lock:
            if self._dirty:
                self._sync_path()
                self._dirty = False
