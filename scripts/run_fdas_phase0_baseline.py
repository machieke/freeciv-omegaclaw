#!/usr/bin/env python3
"""Freeze the behavior-invariant FDAS Phase-0 migration baseline."""

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    KNOWN_EVENT_TYPES,
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.oracle import (  # noqa: E402
    CrispStateView,
    DependencyOracle,
    Goal,
)
from freeciv_agent.planning import (  # noqa: E402
    ImpactCandidate,
    OperationAuthorityKind,
    OperationState,
)
from freeciv_agent.planning.city_worker_macro import (  # noqa: E402
    CityWorkerMacroIntent,
)
from freeciv_agent.planning.combat_operations import (  # noqa: E402
    CombatOperationAssembler,
)
from freeciv_agent.planning.domain_models.defense import (  # noqa: E402
    DefenseOperationType,
)
from freeciv_agent.planning.transport_operations import (  # noqa: E402
    FounderTransportOperationAssembler,
)
from freeciv_agent.pressure import ImpactPressureRanker  # noqa: E402
from freeciv_agent.pressure.packets import ResourceKind  # noqa: E402
from freeciv_agent.pressure.resource_claims import (  # noqa: E402
    GameResourceKind,
)
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.state.atoms import (  # noqa: E402
    LEGACY_AUTHORITATIVE_PREDICATES,
    LEGACY_PROJECTED_PREDICATES,
    LEGACY_VISIBLE_PREDICATES,
    build_atomspaces,
)
from freeciv_agent.state.grounded import GroundedRegistry  # noqa: E402


DEFAULT_MANIFEST = (
    "benchmarks/gdo/captured_snapshots/"
    "city_defense_grounded_160_manifest.json")
DEFAULT_RULESET_ROOT = "build/freeciv/ruleset-source"
DEFAULT_OUTPUT = "benchmarks/fdas/phase0-baseline.json"


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--ruleset-root", default=DEFAULT_RULESET_ROOT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument(
        "--check", action="store_true",
        help="compare regenerated semantic hash with the existing output")
    return parser.parse_args()


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _unit(row):
    return SimpleNamespace(
        unit_id=int(row["unit_id"]),
        unit_type=str(row.get("type", "")),
        tile=row.get("tile"),
        activity=row.get("activity"),
        x=row.get("x"),
        y=row.get("y"),
    )


def _city(row):
    return SimpleNamespace(
        city_id=int(row["city_id"]),
        tile=row.get("tile"),
        production_kind=row.get("production_kind"),
        production_value=row.get("production_value"),
        buildability_available=bool(
            row.get("buildability_available", False)),
        buildable=tuple(
            tuple(value) for value in row.get("buildable", ())),
        x=row.get("x"),
        y=row.get("y"),
    )


def _snapshot_view(event):
    payload = event["payload"]
    own = payload["own_state"]
    map_row = payload.get("map") or {}
    units = tuple(_unit(row) for row in own.get("units", ()))
    unit_by_id = dict((unit.unit_id, unit) for unit in units)
    return SimpleNamespace(
        player_id=int(payload["player_id"]),
        turn=int(event["turn"]),
        snapshot_id=str(payload["snapshot_id"]),
        research=SimpleNamespace(
            known_techs=tuple(
                own.get("research", {}).get("known_techs", ()))),
        cities=tuple(_city(row) for row in own.get("cities", ())),
        units=units,
        visible_enemy_units=tuple(
            _unit(row) for row in map_row.get("visible_enemy_units", ())),
        visible_tile_ids=tuple(map_row.get("visible_tile_ids", ())),
        map_width=int(map_row.get("width", 0)),
        map_height=int(map_row.get("height", 0)),
        unit=lambda unit_id: unit_by_id.get(unit_id),
    )


def _atom_rows(values):
    return [
        value.to_dict()
        for value in sorted(values)
    ]


def _projection(snapshot, iterations):
    latencies = []
    projected = None
    for _ in range(iterations):
        started = time.perf_counter()
        projected = build_atomspaces(snapshot)
        latencies.append((time.perf_counter() - started) * 1000.0)
    authoritative = _atom_rows(projected.authoritative)
    visible = _atom_rows(projected.visible)
    uncertain = _atom_rows(projected.uncertain)
    semantic = {
        "authoritative": authoritative,
        "counts": {
            "authoritative": len(authoritative),
            "total": len(authoritative) + len(visible) + len(uncertain),
            "uncertain": len(uncertain),
            "visible": len(visible),
        },
        "snapshot_id": projected.snapshot_id,
        "uncertain": uncertain,
        "visible": visible,
    }
    return semantic, latencies


def _candidate(row):
    return ImpactCandidate(
        action=dict(row["action"]),
        category=str(row["category"]),
        utility=float(row["utility"]),
        rationale=str(row["rationale"]),
        projection=row.get("projection"),
    )


def _adapter_baseline(snapshot, candidate_rows):
    candidates = tuple(_candidate(row) for row in candidate_rows)
    diagnostics = {}
    ordered, artifact = ImpactPressureRanker().rank(
        snapshot,
        candidates,
        expansion_city_target=5,
        horizon_turn=160,
        diagnostics=diagnostics,
    )
    pressure = artifact["pressure"]
    pressure_atom_ids = sorted(set(
        atom_id
        for rows in pressure["pressure"].values()
        for atom_id in rows))
    schedule = artifact["schedule"]
    selected_operation_id = schedule["selected_operation_id"]
    selected = next((
        row for row in schedule["scores"]
        if row["operation"]["operation_id"] == selected_operation_id
    ), None)
    semantic = {
        "graph_hash": pressure["graph_hash"],
        "pressure_atom_count": len(pressure_atom_ids),
        "pressure_goal_count": len(pressure["goals"]),
        "pressure_trace_count": len(pressure["traces"]),
        "schedule_operation_count": len(schedule["scores"]),
        "selected_action_key": (
            ordered[0].action_key if ordered else None),
        "selected_operation_id": selected_operation_id,
        "selected_score": selected,
    }
    return semantic, dict(
        (key, float(value))
        for key, value in sorted(diagnostics.items()))


def _technology_proof(oracle, snapshot):
    target = None
    # The projection view intentionally contains only known technologies.  The
    # target remains a captured authoritative field used by this baseline.
    if hasattr(snapshot, "research_target"):
        target = snapshot.research_target
    if not target:
        return None
    state = CrispStateView(
        snapshot.snapshot_id,
        known_techs=snapshot.research.known_techs,
        player=str(snapshot.player_id),
    )
    result = oracle.deps(
        Goal.researchable(snapshot.player_id, target),
        state,
        query_id="fdas-phase0:{}".format(snapshot.snapshot_id),
    )
    return {
        "chain_depth": result.chain_depth,
        "frontier": result.frontier,
        "prerequisite_names": list(result.prerequisite_names),
        "proof_hash": result.proof["structural_hash"],
        "proof_node_count": len(result.proof["nodes"]),
        "status": result.status,
        "target": target,
    }


def _inventory():
    operation_types = set(
        value.value for value in DefenseOperationType)
    operation_types.update((
        CombatOperationAssembler.OPERATION_TYPE,
        FounderTransportOperationAssembler.OPERATION_TYPE,
        CityWorkerMacroIntent.__dataclass_fields__["operation_type"].default,
        "BUILD_ENABLING_PRODUCT",
        "RESEARCH_ENABLER",
    ))
    return {
        "event_types": list(KNOWN_EVENT_TYPES),
        "grounded_predicates": sorted(GroundedRegistry.IMPLEMENTED),
        "legacy_projection": {
            "authoritative_predicates": sorted(
                LEGACY_AUTHORITATIVE_PREDICATES),
            "all_predicates": sorted(LEGACY_PROJECTED_PREDICATES),
            "visible_predicates": sorted(LEGACY_VISIBLE_PREDICATES),
        },
        "operation_authority_kinds": sorted(
            value.value for value in OperationAuthorityKind),
        "operation_states": sorted(value.value for value in OperationState),
        "operation_types": sorted(operation_types),
        "packet_resource_kinds": sorted(value.value for value in ResourceKind),
        "resource_kinds": sorted(value.value for value in GameResourceKind),
    }


def build_report(manifest_path, ruleset_root, iterations=1):
    if iterations < 1:
        raise ValueError("iterations must be positive")
    with open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    ruleset = compile_ruleset(ruleset_root, manifest["ruleset"])
    oracle = DependencyOracle(ruleset)
    fixtures = []
    latency_rows = []
    adapter_latency_rows = []
    try:
        for fixture in manifest["fixtures"]:
            fixture_path = os.path.join(REPO, fixture["path"])
            with open(fixture_path, encoding="utf-8") as stream:
                captured = json.load(stream)
            if structural_hash(captured) != fixture["fixture_sha256"]:
                raise ValueError(
                    "fixture semantic hash mismatch: {}".format(
                        fixture["path"]))
            event = captured["snapshot_event"]
            snapshot = _snapshot_view(event)
            snapshot.research_target = event["payload"]["own_state"][
                "research"].get("target_name")
            projection, latencies = _projection(snapshot, iterations)
            adapter, adapter_latencies = _adapter_baseline(
                snapshot, captured.get("candidates", ()))
            latency_rows.extend(latencies)
            adapter_latency_rows.append(adapter_latencies)
            candidate_rows = tuple(captured.get("candidates", ()))
            source_selection = captured.get("source_control") or {}
            source_operation_id = source_selection.get(
                "selected_operation_id")
            source_candidate = next((
                row for row in candidate_rows
                if row.get("operation_id") == source_operation_id
            ), None)
            fixtures.append({
                "adapter": adapter,
                "candidate_count": len(candidate_rows),
                "candidates": list(candidate_rows),
                "fixture_path": fixture["path"],
                "fixture_file_sha256": _sha256(fixture_path),
                "fixture_sha256": fixture["fixture_sha256"],
                "projection": projection,
                "source_selection": {
                    "decision_id": source_selection.get("decision_id"),
                    "selected_action": (
                        source_candidate.get("action")
                        if source_candidate is not None else None),
                    "selected_operation_id": source_operation_id,
                    "solver_identity": source_selection.get(
                        "solver_identity"),
                },
                "technology_proof": _technology_proof(oracle, snapshot),
                "turn": int(event["turn"]),
            })
    finally:
        oracle.close()
    semantic = {
        "authority": "diagnostic-replay-only",
        "capability_status": "not-built",
        "design": {
            "adapter": "ImpactPressureRanker/default-scalar-v1",
            "expansion_city_target": 5,
            "horizon_turn": 160,
            "projection": "build_atomspaces",
            "ruleset": manifest["ruleset"],
        },
        "fixtures": fixtures,
        "inventory": _inventory(),
        "manifest": {
            "fixture_count": manifest["fixture_count"],
            "manifest_hash": manifest["manifest_hash"],
            "path": os.path.relpath(manifest_path, REPO),
            "sha256": _sha256(manifest_path),
        },
        "schema_version": "1.0",
    }
    measurements = {
        "adapter_stage_latency_ms": {
            key: {
                "maximum": max(row.get(key, 0.0) for row in adapter_latency_rows),
                "mean": statistics.mean(
                    row.get(key, 0.0) for row in adapter_latency_rows),
            }
            for key in sorted(set(
                key for row in adapter_latency_rows for key in row))
        },
        "iterations_per_fixture": iterations,
        "projection_latency_ms": {
            "maximum": max(latency_rows),
            "mean": statistics.mean(latency_rows),
            "median": statistics.median(latency_rows),
        },
    }
    return {
        "measurements": measurements,
        "report_hash": structural_hash(semantic),
        "semantic": semantic,
    }


def main():
    args = _arguments()
    manifest_path = os.path.join(REPO, args.manifest)
    ruleset_root = os.path.join(REPO, args.ruleset_root)
    report = build_report(manifest_path, ruleset_root, args.iterations)
    output_path = os.path.join(REPO, args.output)
    if args.check:
        with open(output_path, encoding="utf-8") as stream:
            existing = json.load(stream)
        if existing.get("report_hash") != report["report_hash"]:
            raise SystemExit(
                "FDAS Phase-0 semantic baseline mismatch: {} != {}".format(
                    existing.get("report_hash"), report["report_hash"]))
        print(report["report_hash"])
        return
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as stream:
        stream.write(canonical_json_bytes(report))
        stream.write(b"\n")
    print(report["report_hash"])


if __name__ == "__main__":
    main()
