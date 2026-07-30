#!/usr/bin/env python3
"""Extract player-visible GDO-4 replay fixtures from an engine event trace."""

import argparse
import hashlib
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)


DEFAULT_EVENT_PATH = os.path.join(
    REPO, "artifacts", "freeciv",
    "pf-pln-960-turn-4543804-unified-flow-calibrated-20260730",
    "games", "main", "e_full_loop", "4543804-00", "events.jsonl")
DEFAULT_MANIFEST_PATH = os.path.join(
    os.path.dirname(
        DEFAULT_EVENT_PATH),
    "manifest.json")
DEFAULT_OUTPUT_DIRECTORY = os.path.join(
    REPO, "benchmarks", "gdo",
    "captured_snapshots",
    "city_defense")
DEFAULT_SNAPSHOT_IDS = (
    "m7-main-e_full_loop-4543804-00:46:11649:bf9fb77e2ccae3ba",
    "m7-main-e_full_loop-4543804-00:48:12071:c091728e59add329",
    "m7-main-e_full_loop-4543804-00:105:20389:dd4dc4a9b7576127",
    "m7-main-e_full_loop-4543804-00:107:20931:7c65d3b5807277fd",
    "m7-main-e_full_loop-4543804-00:115:22398:33cec663f917e714",
    "m7-main-e_full_loop-4543804-00:126:24355:b1b76772023a5e91",
    "m7-main-e_full_loop-4543804-00:132:25512:ddd08d621970ccb3",
    "m7-main-e_full_loop-4543804-00:133:25949:2b58af7c8f8344af",
    "m7-main-e_full_loop-4543804-00:134:26440:d32bd3350c7dd596",
)


def _candidate_rows(event):
    rows = []
    for score in event.get(
            "payload", {}).get(
                "scores", ()):
        operation = score.get(
            "operation")
        if not isinstance(
                operation, dict):
            continue
        payload = operation.get(
            "payload")
        if (not isinstance(
                payload, dict)
                or not isinstance(
                    payload.get("action"),
                    dict)
                or not isinstance(
                    payload.get("category"),
                    str)):
            continue
        rows.append({
            "action": payload["action"],
            "category":
                payload["category"],
            "operation_id":
                operation.get(
                    "operation_id"),
            "projection":
                payload.get(
                    "projection"),
            "rationale": str(
                payload.get(
                    "rationale")
                or "captured-operation-score"),
            "utility": float(
                payload.get(
                    "utility", 0.0)),
        })
    return sorted(
        rows,
        key=lambda row: (
            canonical_json_bytes(
                row["action"]),
            row["category"],
            row["operation_id"]
            or ""))


def _outcome_row(event):
    payload = event["payload"]
    own = payload.get(
        "own_state", {})
    visible = payload.get(
        "map", {}).get(
            "visible_enemy_units", ())
    return {
        "city_ids": sorted(
            int(row["city_id"])
            for row in own.get(
                "cities", ())),
        "snapshot_id":
            payload["snapshot_id"],
        "turn": int(
            event["turn"]),
        "units": sorted(
            ({
                "hp": row.get("hp"),
                "unit_id":
                    int(row["unit_id"]),
                "x": row.get("x"),
                "y": row.get("y"),
            }
             for row in own.get(
                 "units", ())),
            key=lambda row:
            row["unit_id"]),
        "visible_enemy_unit_ids":
            sorted(
                int(row["unit_id"])
                for row in visible),
    }


def _authority(snapshot_event):
    payload = snapshot_event[
        "payload"]
    grounded = payload.get(
        "grounded_context")
    grounded = (
        grounded
        if isinstance(
            grounded, dict)
        else {})
    legal = grounded.get(
        "legal_actions")
    full_legal = (
        isinstance(legal, list)
        and all(
            isinstance(
                row, dict)
            for row in legal))
    topology = grounded.get(
        "map_topology")
    topology = (
        topology
        if isinstance(
            topology, dict)
        else {})
    map_wrap = all(
        isinstance(
            topology.get(name),
            bool)
        for name in (
            "wrap_x", "wrap_y"))
    units = grounded.get(
        "own_units")
    movement_runtime = (
        isinstance(units, list)
        and all(
            isinstance(row, dict)
            and isinstance(
                row.get(
                    "transported"),
                bool)
            and isinstance(
                row.get(
                    "done_moving"),
                bool)
            for row in units))
    moves = (
        [
            row for row in legal
            if row.get(
                "action_type")
            == "unit_move"
        ]
        if full_legal
        else [])
    movement_action_metadata = bool(
        full_legal
        and all(
            not isinstance(
                row.get(
                    "movement_cost"),
                bool)
            and isinstance(
                row.get(
                    "movement_cost"),
                (int, float))
            and row[
                "movement_cost"] > 0
            and isinstance(
                row.get(
                    "transport_required"),
                bool)
            for row in moves))
    return {
        "full_legal_action_set_available":
            full_legal,
        "legal_action_source": (
            "snapshot-grounded-context"
            if full_legal
            else
            "planner-candidate-trace-subset"),
        "map_wrap_metadata_available":
            map_wrap,
        "movement_action_metadata_available":
            movement_action_metadata,
        "movement_runtime_fields_available":
            movement_runtime,
        "player_visible_only": True,
        # Completeness alone does not establish native parity,
        # counterfactual outcomes, or permission for live policy use.
        "policy_authority_eligible":
            False,
    }


def _load_trace(path):
    snapshots = {}
    last_snapshot = None
    scored = {}
    final_snapshot_by_turn = {}
    proposed_snapshot_ids = set()
    with open(
            path,
            encoding="utf-8") as stream:
        for line in stream:
            event = json.loads(
                line)
            event_type = event.get(
                "type")
            if event_type == (
                    "state_snapshot"):
                last_snapshot = event
                snapshot_id = event[
                    "payload"][
                        "snapshot_id"]
                snapshots[
                    snapshot_id] = event
                final_snapshot_by_turn[
                    int(event[
                        "turn"])] = event
                continue
            if (event_type
                    == "operation_scored"
                    and last_snapshot
                    is not None):
                snapshot_id = (
                    last_snapshot[
                        "payload"][
                            "snapshot_id"])
                if snapshot_id not in (
                        scored):
                    scored[
                        snapshot_id] = (
                            event)
                continue
            if event_type == (
                    "operation_proposed"):
                proposed_snapshot_id = (
                    event.get(
                        "payload", {})
                    .get(
                        "snapshot_id"))
                if isinstance(
                        proposed_snapshot_id,
                        str):
                    proposed_snapshot_ids.add(
                        proposed_snapshot_id)
    return (
        snapshots,
        scored,
        final_snapshot_by_turn,
        proposed_snapshot_ids)


def extract(
        event_path, manifest_path,
        output_directory,
        snapshot_ids,
        output_manifest_path=None):
    with open(
            manifest_path,
            encoding="utf-8") as stream:
        engine_manifest = json.load(
            stream)
    (
        snapshots,
        scored,
        final_snapshot_by_turn,
        _proposed_snapshot_ids,
    ) = _load_trace(
        event_path)
    os.makedirs(
        output_directory,
        exist_ok=True)
    fixture_rows = []
    for snapshot_id in snapshot_ids:
        if snapshot_id not in snapshots:
            raise ValueError(
                "snapshot not present in source trace: {}".format(
                    snapshot_id))
        if snapshot_id not in scored:
            raise ValueError(
                "snapshot has no associated operation score: {}".format(
                    snapshot_id))
        snapshot_event = snapshots[
            snapshot_id]
        score_event = scored[
            snapshot_id]
        candidates = _candidate_rows(
            score_event)
        if not candidates:
            raise ValueError(
                "snapshot has no captured candidates: {}".format(
                    snapshot_id))
        turn = int(
            snapshot_event["turn"])
        outcomes = [
            _outcome_row(
                final_snapshot_by_turn[
                    outcome_turn])
            for outcome_turn in range(
                turn + 1,
                turn + 7)
            if outcome_turn
            in final_snapshot_by_turn
        ]
        payload = {
            "authority": _authority(
                snapshot_event),
            "candidates": candidates,
            "outcome_observations":
                outcomes,
            "schema_version": "1.0",
            "source_control": {
                "decision_id":
                    score_event[
                        "payload"].get(
                            "decision_id"),
                "selected_operation_id":
                    score_event[
                        "payload"].get(
                            "selected_operation_id"),
                "solver_identity":
                    score_event[
                        "payload"].get(
                            "solver_identity"),
            },
            "snapshot_event": {
                "event_id":
                    snapshot_event[
                        "event_id"],
                "game_id":
                    snapshot_event[
                        "game_id"],
                "payload":
                    snapshot_event[
                        "payload"],
                "turn": turn,
            },
            "source": {
                "condition_id":
                    engine_manifest[
                        "condition_id"],
                "engine":
                    engine_manifest[
                        "engine"],
                "event_path":
                    os.path.relpath(
                        event_path,
                        REPO),
                "event_trace_sha256":
                    None,
                "manifest_identity":
                    engine_manifest[
                        "manifest_identity"],
                "operation_scored_event_id":
                    score_event[
                        "event_id"],
                "ruleset":
                    engine_manifest[
                        "ruleset"],
                "seed": int(
                    engine_manifest[
                        "seed"]),
            },
        }
        # The large source trace checksum is computed once below. Excluding it
        # here avoids hashing a multi-megabyte file for every fixture.
        filename = (
            "turn-{}-{}.json".format(
                turn,
                snapshot_id.split(":")[
                    -1]))
        path = os.path.join(
            output_directory,
            filename)
        fixture_rows.append((
            path, payload))
    digest = hashlib.sha256()
    with open(event_path, "rb") as stream:
        for block in iter(
                lambda:
                stream.read(
                    1024 * 1024),
                b""):
            digest.update(block)
    trace_sha256 = digest.hexdigest()
    manifest_fixtures = []
    for path, payload in fixture_rows:
        payload["source"][
            "event_trace_sha256"] = (
                trace_sha256)
        with open(
                path, "w",
                encoding="utf-8") as stream:
            json.dump(
                payload, stream,
                indent=2,
                sort_keys=True)
            stream.write("\n")
        manifest_fixtures.append({
            "candidate_count":
                len(
                    payload[
                        "candidates"]),
            "fixture_sha256":
                structural_hash(
                    payload),
            "path":
                os.path.relpath(
                    path, REPO),
            "snapshot_id":
                payload[
                    "snapshot_event"][
                        "payload"][
                            "snapshot_id"],
            "turn":
                payload[
                    "snapshot_event"][
                        "turn"],
        })
    manifest = {
        "authority": {
            "claim_status":
                "diagnostic-replay-only",
            "policy_authority_eligible":
                False,
        },
        "fixture_count": len(
            manifest_fixtures),
        "fixtures": sorted(
            manifest_fixtures,
            key=lambda row: (
                row["turn"],
                row["snapshot_id"])),
        "ruleset": engine_manifest[
            "ruleset"],
        "schema_version": "1.0",
        "source_event_trace_sha256":
            trace_sha256,
        "source_manifest_identity":
            engine_manifest[
                "manifest_identity"],
    }
    manifest["manifest_hash"] = (
        structural_hash(
            manifest))
    manifest_path = (
        os.path.abspath(
            output_manifest_path)
        if output_manifest_path
        else os.path.join(
            os.path.dirname(
                output_directory),
            "city_defense_replay_manifest.json"))
    with open(
            manifest_path, "w",
            encoding="utf-8") as stream:
        json.dump(
            manifest, stream,
            indent=2,
            sort_keys=True)
        stream.write("\n")
    return manifest_path, manifest


def main():
    parser = argparse.ArgumentParser(
        description=__doc__)
    parser.add_argument(
        "--events",
        default=DEFAULT_EVENT_PATH)
    parser.add_argument(
        "--engine-manifest",
        default=DEFAULT_MANIFEST_PATH)
    parser.add_argument(
        "--output-directory",
        default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument(
        "--output-manifest")
    parser.add_argument(
        "--all-proposed-defense-snapshots",
        action="store_true")
    parser.add_argument(
        "--snapshot-id",
        action="append",
        dest="snapshot_ids")
    arguments = parser.parse_args()
    snapshot_ids = (
        tuple(arguments.snapshot_ids)
        if arguments.snapshot_ids
        else None)
    if (arguments
            .all_proposed_defense_snapshots):
        if snapshot_ids:
            parser.error(
                "--all-proposed-defense-snapshots cannot be combined with --snapshot-id")
        (
            snapshots,
            scored,
            _outcomes,
            proposed_snapshot_ids,
        ) = _load_trace(
            os.path.abspath(
                arguments.events))
        snapshot_ids = tuple(sorted(
            (
                snapshot_id
                for snapshot_id
                in proposed_snapshot_ids
                if snapshot_id
                in snapshots
                and snapshot_id
                in scored),
            key=lambda snapshot_id: (
                int(
                    snapshots[
                        snapshot_id][
                            "turn"]),
                snapshot_id)))
        if not snapshot_ids:
            parser.error(
                "source trace contains no replayable proposed defence snapshots")
    path, manifest = extract(
        os.path.abspath(
            arguments.events),
        os.path.abspath(
            arguments.engine_manifest),
        os.path.abspath(
            arguments.output_directory),
        tuple(
            snapshot_ids
            or DEFAULT_SNAPSHOT_IDS),
        output_manifest_path=(
            arguments.output_manifest))
    print(json.dumps({
        "fixture_count":
            manifest[
                "fixture_count"],
        "manifest":
            path,
        "manifest_hash":
            manifest[
                "manifest_hash"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
