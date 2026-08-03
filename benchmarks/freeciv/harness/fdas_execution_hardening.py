"""Mechanical trace audit for FDAS execution-hardening replays."""

from __future__ import annotations

import glob
import hashlib
import json
import os
from typing import Any, Iterable

from freeciv_agent.events.schema import structural_hash


AUDIT_IDENTITY = "fdas-execution-hardening-trace-audit/1.0"


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object in {}".format(path))
    return value


def _events(path: str) -> Iterable[dict[str, Any]]:
    with open(path, encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(
                    "expected event object at {}:{}".format(path, line_number))
            yield value


def _action_key(action: Any) -> str:
    return json.dumps(action, sort_keys=True, separators=(",", ":"))


def _is_unit_action(action: Any) -> bool:
    return (
        isinstance(action, dict)
        and str(action.get("action_type", "")).startswith("unit_"))


def _find_game_dir(run_dir: str, seed: int) -> str:
    matches = glob.glob(os.path.join(
        os.path.abspath(run_dir), "games", "*", "*", "{}-*".format(seed)))
    matches = sorted(path for path in matches if os.path.isdir(path))
    if len(matches) != 1:
        raise ValueError(
            "expected one game directory for seed {}, found {}".format(
                seed, len(matches)))
    return matches[0]


def _audit_game(
        game_dir: str,
        *,
        historical_turn: int | None = None) -> dict[str, Any]:
    events_path = os.path.join(game_dir, "events.jsonl")
    status_path = os.path.join(game_dir, "status.json")
    manifest_path = os.path.join(game_dir, "manifest.json")
    status = _load_json(status_path)
    manifest = _load_json(manifest_path)

    sent_by_id: dict[str, tuple[str, str, bool, int, int]] = {}
    accepted_pairs: set[tuple[str, str]] = set()
    accepted_unit_snapshots: set[str] = set()
    duplicate_after_acceptance: list[dict[str, Any]] = []
    stale_unit_scope_followups: list[dict[str, Any]] = []
    spatial_violations: list[dict[str, Any]] = []
    spatial_actions_checked = 0
    snapshots_checked = 0
    historical_snapshots_checked = 0
    historical_spatial_actions_checked = 0
    actions_sent = 0
    accepted_actions = 0

    for event in _events(events_path):
        event_type = event.get("type")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        if event_type == "state_snapshot":
            snapshots_checked += 1
            turn = int(event.get("turn", 0))
            map_value = payload.get("map")
            grounded = payload.get("grounded_context")
            if not isinstance(map_value, dict) or not isinstance(grounded, dict):
                spatial_violations.append({
                    "reason": "snapshot-missing-map-or-grounded-context",
                    "seq": event.get("seq"),
                    "turn": turn,
                })
                continue
            width = map_value.get("width")
            height = map_value.get("height")
            actions = grounded.get("legal_actions")
            if not isinstance(width, int) or not isinstance(height, int):
                spatial_violations.append({
                    "reason": "snapshot-invalid-map-dimensions",
                    "seq": event.get("seq"),
                    "turn": turn,
                })
                continue
            if not isinstance(actions, list):
                spatial_violations.append({
                    "reason": "snapshot-missing-legal-actions",
                    "seq": event.get("seq"),
                    "turn": turn,
                })
                continue
            if historical_turn is not None and turn == historical_turn:
                historical_snapshots_checked += 1
            for action in actions:
                if not isinstance(action, dict):
                    continue
                target = action.get("target")
                if not isinstance(target, dict):
                    continue
                has_x = "x" in target
                has_y = "y" in target
                if not has_x and not has_y:
                    continue
                spatial_actions_checked += 1
                if historical_turn is not None and turn == historical_turn:
                    historical_spatial_actions_checked += 1
                x = target.get("x")
                y = target.get("y")
                valid = (
                    isinstance(x, int) and not isinstance(x, bool)
                    and isinstance(y, int) and not isinstance(y, bool)
                    and 0 <= x < width and 0 <= y < height)
                if not valid:
                    spatial_violations.append({
                        "action": action,
                        "height": height,
                        "reason": "spatial-action-outside-canonical-map",
                        "seq": event.get("seq"),
                        "snapshot_id": payload.get("snapshot_id"),
                        "turn": turn,
                        "width": width,
                    })
        elif event_type == "action_sent":
            actions_sent += 1
            action_id = payload.get("action_id")
            snapshot_id = payload.get("snapshot_id")
            action = payload.get("action")
            if not isinstance(action_id, str) or not isinstance(snapshot_id, str):
                continue
            action_key = _action_key(action)
            is_unit = _is_unit_action(action)
            pair = (snapshot_id, action_key)
            row = {
                "action": action,
                "action_id": action_id,
                "seq": event.get("seq"),
                "snapshot_id": snapshot_id,
                "turn": event.get("turn"),
            }
            if pair in accepted_pairs:
                duplicate_after_acceptance.append(row)
            if is_unit and snapshot_id in accepted_unit_snapshots:
                stale_unit_scope_followups.append(row)
            sent_by_id[action_id] = (
                snapshot_id,
                action_key,
                is_unit,
                int(event.get("turn", 0)),
                int(event.get("seq", 0)),
            )
        elif event_type == "action_result":
            action_id = payload.get("action_id")
            accepted = (
                payload.get("status") == "accepted"
                or bool((payload.get("engine_response") or {}).get("accepted")))
            sent = sent_by_id.get(action_id)
            if accepted and sent is not None:
                accepted_actions += 1
                snapshot_id, action_key, is_unit, _turn, _seq = sent
                accepted_pairs.add((snapshot_id, action_key))
                if is_unit:
                    accepted_unit_snapshots.add(snapshot_id)

    guard_count = status.get("decision_stale_unit_scope_followups_blocked", 0)
    gates = {
        "completed_without_infrastructure_failure": (
            status.get("completed") is True
            and status.get("infrastructure_failure") is False),
        "historical_boundary_observed": (
            historical_turn is None
            or (historical_snapshots_checked > 0
                and historical_spatial_actions_checked > 0)),
        "no_accepted_snapshot_action_pair_replayed": (
            not duplicate_after_acceptance),
        "no_spatial_action_outside_canonical_map": not spatial_violations,
        "no_unit_action_after_accepted_unit_on_same_snapshot": (
            not stale_unit_scope_followups),
        "stale_unit_guard_counter_is_valid": (
            isinstance(guard_count, int) and guard_count >= 0),
        "zero_rejected_engine_actions": status.get("rejected_actions") == 0,
    }
    return {
        "accepted_actions": accepted_actions,
        "actions_sent": actions_sent,
        "artifacts": {
            "events_sha256": _sha256(events_path),
            "manifest_sha256": _sha256(manifest_path),
            "status_sha256": _sha256(status_path),
        },
        "duplicate_after_acceptance": duplicate_after_acceptance,
        "game_id": manifest.get("game_id"),
        "gates": gates,
        "historical_spatial_actions_checked": historical_spatial_actions_checked,
        "historical_snapshots_checked": historical_snapshots_checked,
        "passed": all(gates.values()),
        "seed": manifest.get("seed"),
        "source": manifest.get("source"),
        "spatial_actions_checked": spatial_actions_checked,
        "spatial_violations": spatial_violations,
        "snapshots_checked": snapshots_checked,
        "stale_unit_scope_followups": stale_unit_scope_followups,
        "stale_unit_scope_followups_blocked": guard_count,
    }


def audit_execution_hardening(
        run_dir: str,
        randomized_audit_path: str,
        *,
        expected_seeds: Iterable[int],
        historical_seed: int,
        historical_turn: int) -> dict[str, Any]:
    seeds = tuple(int(seed) for seed in expected_seeds)
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("expected seeds must be non-empty and unique")
    if historical_seed not in seeds:
        raise ValueError("historical seed must be in expected seeds")
    randomized = _load_json(randomized_audit_path)
    randomized_seeds = tuple(sorted(
        int(row["seed"]) for row in randomized.get("games", [])))
    games = tuple(
        _audit_game(
            _find_game_dir(run_dir, seed),
            historical_turn=(historical_turn
                             if seed == historical_seed else None))
        for seed in seeds)
    source_identities = {
        json.dumps(game.get("source"), sort_keys=True, separators=(",", ":"))
        for game in games
    }
    gates = {
        "all_game_trace_gates_pass": all(game["passed"] for game in games),
        "exact_randomized_audit_seeds": randomized_seeds == tuple(sorted(seeds)),
        "randomized_ledger_audit_passed": randomized.get("passed") is True,
        "source_identity_is_identical": len(source_identities) == 1,
    }
    report: dict[str, Any] = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "known-seed execution mechanics only; no candidate-value, gameplay, "
            "score, or win-rate claim"),
        "games": list(games),
        "gates": gates,
        "historical_boundary": {
            "seed": historical_seed,
            "turn": historical_turn,
        },
        "passed": all(gates.values()),
        "randomized_audit": {
            "audit_identity": randomized.get("audit_identity"),
            "report_hash": randomized.get("report_hash"),
            "sha256": _sha256(randomized_audit_path),
        },
    }
    report["report_hash"] = structural_hash(report)
    return report
