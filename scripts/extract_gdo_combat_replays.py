#!/usr/bin/env python3
"""Extract player-visible joint-combat fixtures from an engine event trace."""

import argparse
from collections import defaultdict
import hashlib
import json
import os
import sys


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)


DEFAULT_EVENT_PATH = os.path.join(
    REPO, "artifacts", "freeciv",
    "gdo5-joint-positive-replay-v1",
    "games", "main", "e_full_loop",
    "104743-00", "events.jsonl")
DEFAULT_RUN_MANIFEST = os.path.join(
    os.path.dirname(
        DEFAULT_EVENT_PATH),
    "manifest.json")
DEFAULT_OUTPUT_DIRECTORY = os.path.join(
    REPO, "benchmarks", "gdo",
    "captured_snapshots",
    "combat_operations_native_160")
DEFAULT_OUTPUT_MANIFEST = os.path.join(
    REPO, "benchmarks", "gdo",
    "captured_snapshots",
    "combat_operations_native_160_manifest.json")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(
                lambda: stream.read(
                    1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolved_target(row):
    selected = row.get(
        "target_unit_id")
    if (
        isinstance(selected, int)
        and not isinstance(selected, bool)
        and selected > 0
    ):
        return selected
    stack = row.get(
        "target_unit_ids")
    if (
        isinstance(stack, list)
        and len(stack) == 1
        and isinstance(stack[0], int)
        and not isinstance(stack[0], bool)
        and stack[0] > 0
    ):
        return stack[0]
    return None


def _joint_groups(event):
    grounded = event.get(
        "payload", {}).get(
            "grounded_context", {})
    rows = grounded.get(
        "combat_probabilities", ())
    grouped = defaultdict(set)
    for row in rows:
        if not isinstance(row, dict):
            continue
        attack = next((
            value
            for value in row.get(
                "action_probabilities",
                ())
            if (
                isinstance(value, dict)
                and value.get(
                    "action_name")
                    == "attack"
                and value.get(
                    "status")
                    == "bounded")
        ), None)
        target_id = (
            _resolved_target(row))
        actor_id = row.get(
            "actor_unit_id")
        if (
            attack is None
            or not isinstance(
                attack.get("maximum"),
                int)
            or attack["maximum"] <= 0
            or target_id is None
            or not isinstance(
                actor_id, int)
            or isinstance(actor_id, bool)
        ):
            continue
        grouped[(
            target_id,
            row.get(
                "target_tile_id"),
        )].add(actor_id)
    return tuple(
        {
            "actor_unit_ids":
                sorted(actor_ids),
            "target_tile_id":
                target_tile_id,
            "target_unit_id":
                target_unit_id,
        }
        for (
            target_unit_id,
            target_tile_id,
        ), actor_ids in sorted(
            grouped.items())
        if len(actor_ids) >= 2)


def extract(
        events_path, run_manifest_path,
        output_directory,
        output_manifest_path,
        ruleset_digest):
    events = []
    with open(
            events_path,
            encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                events.append(
                    json.loads(line))
    with open(
            run_manifest_path,
            encoding="utf-8") as stream:
        run_manifest = json.load(
            stream)
    proposals = defaultdict(list)
    for event in events:
        payload = event.get(
            "payload", {})
        if (
            event.get("type")
                == "operation_proposed"
            and payload.get(
                "operation_type")
                == "attack_then_conditional_attack"
        ):
            proposals[
                payload.get(
                    "snapshot_id")
            ].append(event)
    selected_events = []
    seen_state_hashes = set()
    for event in events:
        if event.get(
                "type") != (
                "state_snapshot"):
            continue
        groups = _joint_groups(
            event)
        state_hash = event.get(
            "payload", {}).get(
                "state_hash")
        if (
            not groups
            or state_hash
                in seen_state_hashes
        ):
            continue
        seen_state_hashes.add(
            state_hash)
        selected_events.append((
            event, groups))
    if not selected_events:
        raise ValueError(
            "event trace contains no exact joint-combat snapshots")
    os.makedirs(
        output_directory,
        exist_ok=True)
    event_sha = _sha256(
        events_path)
    run_manifest_sha = _sha256(
        run_manifest_path)
    entries = []
    for event, groups in selected_events:
        payload = event[
            "payload"]
        snapshot_id = payload[
            "snapshot_id"]
        operation_events = sorted(
            proposals.get(
                snapshot_id, ()),
            key=lambda row: (
                row["payload"][
                    "operation_id"]))
        fixture = {
            "authority":
                "player-visible-engine-event",
            "expected_shadow_readout": {
                "candidate_operation_ids": [
                    row["payload"][
                        "operation_id"]
                    for row in
                    operation_events],
                "reason_by_operation_id": {
                    row["payload"][
                        "operation_id"]:
                    row["payload"][
                        "reason_code"]
                    for row in
                    operation_events
                },
                "selected_operation_ids": [
                    row["payload"][
                        "operation_id"]
                    for row in
                    operation_events
                    if row["payload"].get(
                        "selected")
                ],
            },
            "joint_groups": list(
                groups),
            "ruleset_digest":
                str(ruleset_digest),
            "schema_version": "1.0",
            "snapshot_event": {
                "event_id":
                    event["event_id"],
                "game_id":
                    event["game_id"],
                "payload":
                    payload,
                "seq": event["seq"],
                "turn": event["turn"],
                "type":
                    event["type"],
            },
            "source": {
                "engine_commit":
                    run_manifest[
                        "engine"][
                        "freeciv_commit"],
                "events_path":
                    os.path.relpath(
                        events_path,
                        REPO),
                "events_sha256":
                    event_sha,
                "proxy_commit":
                    run_manifest[
                        "engine"][
                        "proxy_commit"],
                "run_manifest_path":
                    os.path.relpath(
                        run_manifest_path,
                        REPO),
                "run_manifest_sha256":
                    run_manifest_sha,
            },
        }
        filename = (
            "turn-{}-{}-{}.json"
            .format(
                event["turn"],
                payload[
                    "source_seq"],
                payload[
                    "state_hash"][:16]))
        path = os.path.join(
            output_directory,
            filename)
        with open(path, "wb") as stream:
            stream.write(
                canonical_json_bytes(
                    fixture))
            stream.write(b"\n")
        entries.append({
            "joint_group_count":
                len(groups),
            "path": os.path.relpath(
                path, REPO),
            "sha256": _sha256(path),
            "snapshot_id":
                snapshot_id,
            "source_event_id":
                event["event_id"],
            "turn": event["turn"],
        })
    manifest = {
        "authority":
            "player-visible-engine-event",
        "entries": entries,
        "ruleset_digest":
            str(ruleset_digest),
        "schema_version": "1.0",
        "source_events_sha256":
            event_sha,
        "source_manifest_sha256":
            run_manifest_sha,
    }
    manifest["manifest_hash"] = (
        structural_hash(manifest))
    with open(
            output_manifest_path,
            "wb") as stream:
        stream.write(
            canonical_json_bytes(
                manifest))
        stream.write(b"\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(
        description=__doc__)
    parser.add_argument(
        "--events",
        default=DEFAULT_EVENT_PATH)
    parser.add_argument(
        "--run-manifest",
        default=DEFAULT_RUN_MANIFEST)
    parser.add_argument(
        "--output-directory",
        default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument(
        "--output-manifest",
        default=DEFAULT_OUTPUT_MANIFEST)
    parser.add_argument(
        "--ruleset-digest",
        required=True)
    args = parser.parse_args()
    manifest = extract(
        args.events,
        args.run_manifest,
        args.output_directory,
        args.output_manifest,
        args.ruleset_digest)
    print(json.dumps({
        "fixtures":
            len(manifest["entries"]),
        "manifest_hash":
            manifest[
                "manifest_hash"],
        "output_manifest":
            os.path.abspath(
                args.output_manifest),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
