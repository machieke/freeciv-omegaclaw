#!/usr/bin/env python3
"""Replay captured native joint-combat states through atomic GDO-5."""

import argparse
import copy
import hashlib
import json
import os
import statistics
import sys
import time


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(
    REPO, "scripts")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.state.snapshot import (  # noqa: E402
    AuthoritativeSnapshot,
    CombatActionProbabilityState,
    CombatProbabilityState,
    EconomicState,
    ResearchState,
    SnapshotIdentity,
    UnitState,
)
import run_gdo_combat_operation_replay as mechanism  # noqa: E402


DEFAULT_MANIFEST = os.path.join(
    REPO, "benchmarks", "gdo",
    "captured_snapshots",
    "combat_operations_native_160_manifest.json")
DEFAULT_OUTPUT = os.path.join(
    REPO, "benchmarks", "gdo",
    "gdo5_combat_operation_captured_diagnostic.json")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(
                lambda: stream.read(
                    1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unit(row):
    return UnitState(
        unit_id=int(
            row["unit_id"]),
        owner=int(
            row["owner"]),
        unit_type=str(
            row["type"]),
        type_id=row.get(
            "type_id"),
        tile=row.get("tile"),
        x=row.get("x"),
        y=row.get("y"),
        moves_left=row.get(
            "moves_left"),
        hp=row.get("hp"),
        activity=row.get(
            "activity"),
        upkeep=tuple(
            int(value)
            for value in row.get(
                "upkeep", ())),
        homecity=row.get(
            "homecity"),
        veteran=row.get(
            "veteran"),
        transported=row.get(
            "transported"),
        transported_by=row.get(
            "transported_by"),
        carrying=row.get(
            "carrying"),
        done_moving=row.get(
            "done_moving"))


def _combat_probability(row):
    return CombatProbabilityState(
        player_id=int(
            row["player_id"]),
        actor_unit_id=int(
            row["actor_unit_id"]),
        target_tile_id=int(
            row["target_tile_id"]),
        target_unit_id=int(
            row["target_unit_id"]),
        target_city_id=int(
            row["target_city_id"]),
        target_extra_id=int(
            row["target_extra_id"]),
        target_unit_ids=tuple(
            int(value)
            for value in row[
                "target_unit_ids"]),
        action_probabilities=tuple(
            CombatActionProbabilityState(
                action_id=int(
                    action["action_id"]),
                action_name=str(
                    action[
                        "action_name"]),
                minimum=int(
                    action["minimum"]),
                maximum=int(
                    action["maximum"]),
                status=str(
                    action["status"]))
            for action in row[
                "action_probabilities"]),
        actor_revision_digest=str(
            row[
                "actor_revision_digest"]),
        target_stack_revision_digest=str(
            row[
                "target_stack_revision_digest"]),
        turn=int(row["turn"]),
        request_source_seq=int(
            row[
                "request_source_seq"]),
        response_source_seq=int(
            row[
                "response_source_seq"]),
        authority=str(
            row["authority"]),
        schema_version=str(
            row["schema_version"]))


def _snapshot(fixture):
    event = fixture[
        "snapshot_event"]
    payload = event[
        "payload"]
    grounded = payload[
        "grounded_context"]
    map_payload = payload[
        "map"]
    legal_actions = tuple(sorted(
        json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"))
        for row in grounded[
            "legal_actions"]))
    topology = grounded.get(
        "map_topology", {})
    return AuthoritativeSnapshot(
        identity=SnapshotIdentity(
            game_id=str(
                event["game_id"]),
            turn=int(
                event["turn"]),
            source_seq=int(
                payload[
                    "source_seq"]),
            state_hash=str(
                payload[
                    "state_hash"])),
        player_id=int(
            payload["player_id"]),
        player_alive=True,
        phase="playing",
        ruleset_ready=True,
        ruleset_diagnostic=None,
        research=ResearchState(
            known_techs=(),
            target_id=None,
            target_name=None,
            progress=None,
            cost=None,
            beakers_per_turn=None,
            available=False,
            diagnostic=(
                "captured-combat-replay")),
        economy=EconomicState(
            gold=0,
            gold_per_turn=0,
            tax_rate=0,
            science_rate=0,
            luxury_rate=0,
            available=True),
        cities=(),
        units=tuple(
            _unit(row)
            for row in grounded[
                "own_units"]),
        visible_enemy_units=tuple(
            _unit(row)
            for row in grounded[
                "visible_enemy_units"]),
        visible_tile_ids=tuple(
            int(value)
            for value in map_payload.get(
                "visible_tile_ids", ())),
        known_hut_tile_ids=tuple(
            int(value)
            for value in map_payload.get(
                "known_hut_tile_ids", ())),
        map_width=int(
            map_payload["width"]),
        map_height=int(
            map_payload["height"]),
        map_tiles=tuple(
            map_payload.get(
                "tiles", ())),
        legal_action_json=(
            legal_actions),
        legal_actions_digest=str(
            payload[
                "legal_actions_digest"]),
        legal_action_kinds=tuple(sorted({
            str(row["action_type"])
            for row in grounded[
                "legal_actions"]
            if isinstance(
                row.get(
                    "action_type"),
                str)
        })),
        map_wrap_x=topology.get(
            "wrap_x"),
        map_wrap_y=topology.get(
            "wrap_y"),
        combat_probabilities=tuple(
            _combat_probability(row)
            for row in grounded[
                "combat_probabilities"]))


def _percentile(values, fraction):
    rows = sorted(
        float(value)
        for value in values)
    return rows[
        int(float(fraction)
            * (len(rows) - 1))]


def _summary(values):
    return {
        "maximum_ms": max(values),
        "mean_ms": statistics.mean(
            values),
        "p50_ms": statistics.median(
            values),
        "p95_ms": _percentile(
            values, 0.95),
        "sample_count": len(values),
    }


def _load_manifest(path):
    with open(
            path,
            encoding="utf-8") as stream:
        manifest = json.load(
            stream)
    hashable = copy.deepcopy(
        manifest)
    expected = hashable.pop(
        "manifest_hash")
    if structural_hash(
            hashable) != expected:
        raise ValueError(
            "captured combat manifest hash is invalid")
    fixtures = []
    for entry in manifest[
            "entries"]:
        fixture_path = os.path.join(
            REPO, entry["path"])
        if _sha256(
                fixture_path) != (
                entry["sha256"]):
            raise ValueError(
                "captured combat fixture checksum mismatch: {}".format(
                    entry["path"]))
        with open(
                fixture_path,
                encoding="utf-8") as stream:
            fixtures.append((
                entry,
                json.load(stream)))
    return manifest, fixtures


def _evaluate(fixture, action_budget):
    started = time.perf_counter()
    snapshot = _snapshot(
        fixture)
    scenario = {
        "action_budget":
            int(action_budget),
    }
    atomic = (
        mechanism
        ._atomic_readout(
            snapshot,
            scenario,
            ruleset_digest=(
                fixture[
                    "ruleset_digest"])))
    independent = (
        mechanism
        ._independent_readout(
            snapshot,
            int(action_budget)))
    expected = fixture[
        "expected_shadow_readout"]
    return {
        "atomic": atomic,
        "candidate_ids_match_source":
            atomic[
                "candidate_operation_ids"]
            == sorted(
                expected[
                    "candidate_operation_ids"]),
        "independent":
            independent,
        "latency_ms": (
            time.perf_counter()
            - started) * 1000.0,
        "reason_map_matches_source":
            atomic[
                "reason_by_operation_id"]
            == expected[
                "reason_by_operation_id"],
        "selected_ids_match_source":
            atomic[
                "selected_operation_ids"]
            == sorted(
                expected[
                    "selected_operation_ids"]),
        "snapshot_id":
            snapshot.snapshot_id,
    }


def run(manifest_path, iterations, action_budget):
    manifest, fixtures = (
        _load_manifest(
            manifest_path))
    first = [
        {
            **_evaluate(
                fixture,
                action_budget),
            "fixture_path":
                entry["path"],
            "turn": entry["turn"],
        }
        for entry, fixture
        in fixtures
    ]
    latency = [
        row["latency_ms"]
        for row in first
    ]
    decisions = {
        row["fixture_path"]: {
            row["atomic"][
                "decision_digest"]
        }
        for row in first
    }
    for _ in range(
            iterations - 1):
        for entry, fixture in fixtures:
            row = _evaluate(
                fixture,
                action_budget)
            latency.append(
                row["latency_ms"])
            decisions[
                entry["path"]].add(
                    row["atomic"][
                        "decision_digest"])
    independent_duplicates = sum(
        row["independent"][
            "duplicated_target_count"]
        for row in first)
    atomic_duplicates = sum(
        row["atomic"][
            "duplicated_target_count"]
        for row in first)
    gates = {
        "action_budget_never_exceeded":
            all(
                row["atomic"][
                    "action_budget_used"]
                <= action_budget
                for row in first),
        "atomic_duplicate_targeting_zero":
            atomic_duplicates == 0,
        "atomic_lower_duplicate_targeting_than_independent":
            atomic_duplicates
            < independent_duplicates,
        "atomic_reservations_complete":
            all(
                row["atomic"][
                    "reservations_complete"]
                for row in first),
        "candidate_ids_match_source":
            all(
                row[
                    "candidate_ids_match_source"]
                for row in first),
        "captured_authority_only":
            manifest[
                "authority"]
            == (
                "player-visible-engine-event"),
        "p95_compute_below_20_ms":
            _percentile(
                latency, 0.95)
            < 20.0,
        "reason_maps_match_source":
            all(
                row[
                    "reason_map_matches_source"]
                for row in first),
        "schedule_decisions_deterministic":
            all(
                len(values) == 1
                for values in
                decisions.values()),
        "selected_ids_match_source":
            all(
                row[
                    "selected_ids_match_source"]
                for row in first),
        "shadow_only_no_policy_authority":
            all(
                row["atomic"][
                    "shadow_only"]
                and not row["atomic"][
                    "policy_authority"]
                for row in first),
    }
    report = {
        "action_budget":
            int(action_budget),
        "authority":
            "captured-player-visible-engine-events",
        "claim_status":
            "mechanism-replay-no-outcome-or-score-claim",
        "fixture_count":
            len(first),
        "gates": gates,
        "independent_duplicate_target_count":
            independent_duplicates,
        "atomic_duplicate_target_count":
            atomic_duplicates,
        "iterations": int(
            iterations),
        "latency": _summary(
            latency),
        "manifest_hash":
            manifest[
                "manifest_hash"],
        "passed": all(
            gates.values()),
        "policy_authority": False,
        "replays": first,
        "schema_version": "1.0",
        "source_events_sha256":
            manifest[
                "source_events_sha256"],
    }
    report["report_hash"] = (
        structural_hash(report))
    return report


def main():
    parser = argparse.ArgumentParser(
        description=__doc__)
    parser.add_argument(
        "--action-budget",
        type=int,
        default=8)
    parser.add_argument(
        "--iterations",
        type=int,
        default=100)
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not 1 <= args.action_budget <= 32:
        parser.error(
            "--action-budget must be in 1..32")
    if not 1 <= args.iterations <= 10000:
        parser.error(
            "--iterations must be in 1..10000")
    report = run(
        args.manifest,
        args.iterations,
        args.action_budget)
    with open(
            args.output, "wb") as stream:
        stream.write(
            canonical_json_bytes(
                report))
        stream.write(b"\n")
    print(json.dumps({
        "output":
            os.path.abspath(
                args.output),
        "passed":
            report["passed"],
        "report_hash":
            report[
                "report_hash"],
    }, sort_keys=True))
    return 0 if report[
        "passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
