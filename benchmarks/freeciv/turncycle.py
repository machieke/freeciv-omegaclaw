"""Shared turn-cycle helpers for the live freeciv runners (Issue #25).

Centralizes the pieces that used to be duplicated (and divergent) across ``llm_play.py`` /
``live_play.py``: typed message waiting, ``llm_optimized`` state polling, and — the point of
Issue #25 — **turn-advance detection**. The action envelope itself lives in
``client.action_message`` (the single wire-dialect source). Async + stdlib only; the live
``websockets`` dependency belongs to the caller.

Why this exists: the game got stuck on turn 1 because end_turn was sent with the wrong
envelope (dropped by the proxy) AND the runners never checked that the turn actually
incremented (blind ``sleep`` + fixed cycle count). :func:`await_turn_advance` closes the
second half: it drives the loop by *observed* turns, not by attempts.
"""

import asyncio
import json
import math
import time

from . import client

# Re-export so callers have one import for the whole turn-cycle surface.
action_message = client.action_message
end_turn_message = client.end_turn_message

_STATE_TYPES = {"state_response", "state_update", "state_unchanged"}
# Server pushes that announce a new turn/phase (best-effort; polling is the reliable path).
TURN_PUSH_TYPES = {"begin_turn", "turn_begin", "new_turn", "phase_change"}


async def recv_until(ws, types, timeout=20, drain=500, diagnostics=None):
    """Return the first received message whose ``type`` is in ``types`` (or None on timeout)."""
    if diagnostics is not None and not isinstance(diagnostics, dict):
        raise ValueError("diagnostics must be a dictionary")
    for _ in range(drain):
        try:
            raw_message = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        decode_started = time.perf_counter()
        m = json.loads(raw_message)
        decode_ms = (time.perf_counter() - decode_started) * 1000.0
        if diagnostics is not None:
            diagnostics["json_decode_ms"] = (
                diagnostics.get("json_decode_ms", 0.0) + decode_ms)
            wire_bytes = (
                len(raw_message)
                if isinstance(raw_message, bytes)
                else len(raw_message.encode("utf-8")))
            diagnostics["wire_bytes"] = (
                diagnostics.get("wire_bytes", 0.0) + wire_bytes)
        if isinstance(m, dict) and m.get("type") in types:
            return m
    return None


def state_body(m):
    """Unwrap a state message: prefer ``data`` when it carries the ``turn`` field."""
    if not m:
        return None
    d = m.get("data")
    return d if isinstance(d, dict) and "turn" in d else m


async def get_state(ws, fmt="llm_optimized", after_source_seq=None,
                    wait_timeout_ms=None, accept_unchanged=False,
                    settle_quiet_ms=None, diagnostics=None,
                    include_movement_routes=False):
    """Query current state, optionally waiting for a newer packet revision.

    ``after_source_seq`` and ``wait_timeout_ms`` are a bounded long-poll hint
    supported by the pinned authoritative-state proxy patch. ``settle_quiet_ms``
    additionally requests an exact-revision settled full response. A timeout
    still returns the current state, so callers retain normal query semantics.
    """
    query = {"type": "state_query", "format": fmt}
    if not isinstance(include_movement_routes, bool):
        raise ValueError("include_movement_routes must be boolean")
    if include_movement_routes:
        if fmt != "pln_authoritative":
            raise ValueError(
                "include_movement_routes requires pln_authoritative format")
        query["include_movement_routes"] = True
    if after_source_seq is not None:
        if (isinstance(after_source_seq, bool)
                or not isinstance(after_source_seq, int)
                or after_source_seq < 0):
            raise ValueError("after_source_seq must be a non-negative integer")
        query["after_source_seq"] = after_source_seq
    if wait_timeout_ms is not None:
        if (isinstance(wait_timeout_ms, bool)
                or not isinstance(wait_timeout_ms, int)
                or not 1 <= wait_timeout_ms <= 5000):
            raise ValueError("wait_timeout_ms must be in 1..5000")
        if after_source_seq is None:
            raise ValueError("wait_timeout_ms requires after_source_seq")
        query["wait_timeout_ms"] = wait_timeout_ms
    if not isinstance(accept_unchanged, bool):
        raise ValueError("accept_unchanged must be boolean")
    if accept_unchanged:
        if (fmt != "pln_authoritative" or after_source_seq is None
                or wait_timeout_ms is None):
            raise ValueError(
                "accept_unchanged requires an authoritative bounded source wait")
        query["accept_unchanged"] = True
    if settle_quiet_ms is not None:
        if (isinstance(settle_quiet_ms, bool)
                or not isinstance(settle_quiet_ms, int)
                or not 1 <= settle_quiet_ms <= 1000):
            raise ValueError("settle_quiet_ms must be in 1..1000")
        if (fmt != "pln_authoritative" or after_source_seq is None
                or wait_timeout_ms is None
                or settle_quiet_ms > wait_timeout_ms):
            raise ValueError(
                "settle_quiet_ms requires a sufficient authoritative bounded "
                "source wait")
        query["settle_quiet_ms"] = settle_quiet_ms
    if diagnostics is not None and not isinstance(diagnostics, dict):
        raise ValueError("diagnostics must be a dictionary")
    await ws.send(json.dumps(query))
    message = await recv_until(
        ws, _STATE_TYPES, timeout=15, diagnostics=diagnostics)
    timing = message.get("server_timing") if isinstance(message, dict) else None
    if diagnostics is not None and isinstance(timing, dict):
        for name in (
                "source_wait_ms", "projection_ms", "quiet_wait_ms",
                "movement_route_wait_ms", "movement_route_responses",
                "elapsed_before_serialize_ms", "projection_attempts"):
            value = timing.get(name)
            if (isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(value) and value >= 0):
                diagnostics[name] = diagnostics.get(name, 0.0) + float(value)
    return state_body(message)


def turn_of(state):
    """Integer turn from a state dict, or None if absent/unparseable."""
    if not state or state.get("turn") is None:
        return None
    try:
        return int(state.get("turn"))
    except (TypeError, ValueError):
        return None


async def send_end_turn(ws):
    """Send the correctly-shaped end_turn action (advances the phase via pid 52)."""
    await ws.send(json.dumps(end_turn_message()))


async def await_turn_advance(ws, prev_turn, timeout=40, poll=1.0):
    """Poll state until the turn strictly advances past ``prev_turn``.

    Returns the new (larger) turn number, or None if it did not advance within ``timeout``
    seconds. ``prev_turn`` None means "accept the first integer turn observed" (used once to
    latch the starting turn). This is the detection the old runners lacked — the loop should
    count *observed* advances, not attempts, so re-deciding over a held turn never counts.
    """
    attempts = max(1, int(timeout / poll))
    for _ in range(attempts):
        st = await get_state(ws)
        t = turn_of(st)
        if t is not None and (prev_turn is None or t > prev_turn):
            return t
        await asyncio.sleep(poll)
    return None
