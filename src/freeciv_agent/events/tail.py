"""Persisted-first, read-only WebSocket tail for canonical event logs.

The event file is the source of truth.  The service never accepts events and never
broadcasts bytes that have not first appeared as a complete, schema-valid JSONL
record on disk.
"""

import asyncio
import bisect
import json
import os
from dataclasses import dataclass

from websockets.exceptions import ConnectionClosed

from .schema import SCHEMA_VERSION, validate_event_schema


class TailProtocolError(RuntimeError):
    """A typed subscription or persisted-log protocol failure."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True, order=True)
class EventCursor:
    turn: int
    seq: int

    @classmethod
    def from_value(cls, value):
        if value is None:
            return cls(-1, -1)
        if not isinstance(value, dict):
            raise TailProtocolError("E_SUBSCRIBE_CURSOR", "after must be an object")
        turn, seq = value.get("turn"), value.get("seq")
        if isinstance(turn, bool) or not isinstance(turn, int):
            raise TailProtocolError("E_SUBSCRIBE_CURSOR", "after.turn must be an integer")
        if isinstance(seq, bool) or not isinstance(seq, int):
            raise TailProtocolError("E_SUBSCRIBE_CURSOR", "after.seq must be an integer")
        return cls(turn, seq)

    def to_dict(self):
        return {"turn": self.turn, "seq": self.seq}


def _wire_message(message_type, **values):
    return json.dumps(
        {"protocol_version": "1", "type": message_type, **values},
        sort_keys=True, separators=(",", ":"), allow_nan=False)


class PersistedEventTail(object):
    """Serve one append-only JSONL log with resume and bounded batches."""

    def __init__(self, path, game_id, schema_version=SCHEMA_VERSION,
                 poll_interval=0.05, max_batch=256):
        self.path = os.path.abspath(path)
        self.game_id = str(game_id)
        self.schema_version = str(schema_version)
        self.poll_interval = float(poll_interval)
        self.max_batch = int(max_batch)
        if self.poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        if self.max_batch < 1:
            raise ValueError("max_batch must be positive")
        self._file_identity = None
        self._offset = 0
        self._line_count = 0
        self._events = []
        self._cursors = []
        self._seen_event_ids = set()

    def _parse_subscription(self, raw):
        try:
            value = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise TailProtocolError("E_SUBSCRIBE_JSON", "invalid subscription JSON: {}".format(exc))
        if not isinstance(value, dict) or value.get("type") != "subscribe":
            raise TailProtocolError("E_SUBSCRIBE_TYPE", "first message must be subscribe")
        if value.get("game_id") != self.game_id:
            raise TailProtocolError("E_SUBSCRIBE_GAME", "game_id does not match this tail")
        if value.get("schema_version") != self.schema_version:
            raise TailProtocolError("E_SUBSCRIBE_SCHEMA", "schema_version is incompatible")
        return EventCursor.from_value(value.get("after"))

    def _reset_index(self):
        self._file_identity = None
        self._offset = 0
        self._line_count = 0
        self._events = []
        self._cursors = []
        self._seen_event_ids = set()

    def _sync_index(self):
        """Validate only bytes appended since the last persisted scan.

        The cache is an index over bytes already present on disk, never an
        acknowledgement buffer. File replacement or truncation resets it and
        deterministically validates the new file from byte zero.
        """
        if not os.path.exists(self.path):
            self._reset_index()
            return
        stat = os.stat(self.path)
        identity = (stat.st_dev, stat.st_ino)
        if (self._file_identity != identity or stat.st_size < self._offset):
            self._reset_index()
            self._file_identity = identity
        if stat.st_size == self._offset:
            return
        with open(self.path, "rb") as stream:
            stream.seek(self._offset)
            content = stream.read()
        if content and not content.endswith(b"\n"):
            raise TailProtocolError(
                "E_TAIL_TRUNCATED",
                "persisted log ends in a partial JSONL record")
        prior = (
            self._cursors[-1] if self._cursors else EventCursor(-1, -1))
        parsed = []
        parsed_cursors = []
        parsed_ids = set()
        for line_number, raw in enumerate(
                content.splitlines(), self._line_count + 1):
            if not raw.strip():
                continue
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise TailProtocolError(
                    "E_TAIL_JSON", "invalid persisted record at line {}: {}".format(line_number, exc))
            errors = validate_event_schema(event)
            if errors:
                raise TailProtocolError(
                    "E_TAIL_SCHEMA", "invalid persisted record at line {}: {}".format(
                        line_number, errors[0]["message"]))
            if event["game_id"] != self.game_id:
                raise TailProtocolError("E_TAIL_GAME", "persisted log contains another game_id")
            if event["schema_version"] != self.schema_version:
                raise TailProtocolError("E_TAIL_SCHEMA", "persisted log schema changed")
            cursor = EventCursor(event["turn"], event["seq"])
            if cursor <= prior:
                raise TailProtocolError("E_TAIL_ORDER", "persisted event cursor is not increasing")
            if (event["event_id"] in self._seen_event_ids
                    or event["event_id"] in parsed_ids):
                raise TailProtocolError("E_TAIL_DUPLICATE", "persisted event_id is duplicated")
            prior = cursor
            parsed.append(event)
            parsed_cursors.append(cursor)
            parsed_ids.add(event["event_id"])
        self._events.extend(parsed)
        self._cursors.extend(parsed_cursors)
        self._seen_event_ids.update(parsed_ids)
        self._offset += len(content)
        self._line_count += len(content.splitlines())

    def _read_after(self, after):
        """Return one bounded batch from the validated persisted-file index."""
        self._sync_index()
        start = bisect.bisect_right(self._cursors, after)
        return self._events[start:start + self.max_batch]

    async def handler(self, websocket, _legacy_path=None):
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            after = self._parse_subscription(raw)
            await websocket.send(_wire_message(
                "subscribed", game_id=self.game_id, schema_version=self.schema_version,
                after=after.to_dict(), persisted_first=True, max_batch=self.max_batch))
            while True:
                batch = self._read_after(after)
                if not batch:
                    await asyncio.sleep(self.poll_interval)
                    if websocket.close_code is not None:
                        return
                    continue
                for event in batch:
                    await websocket.send(json.dumps(
                        event, sort_keys=True, separators=(",", ":"), allow_nan=False))
                    after = EventCursor(event["turn"], event["seq"])
        except TailProtocolError as exc:
            try:
                await websocket.send(_wire_message("tail_error", code=exc.code, message=str(exc)))
                await websocket.close(code=1008, reason=exc.code)
            except ConnectionClosed:
                return
        except (asyncio.TimeoutError, json.JSONDecodeError):
            try:
                await websocket.send(_wire_message(
                    "tail_error", code="E_SUBSCRIBE_TIMEOUT", message="subscription timed out"))
                await websocket.close(code=1008, reason="E_SUBSCRIBE_TIMEOUT")
            except ConnectionClosed:
                return
        except ConnectionClosed:
            return
