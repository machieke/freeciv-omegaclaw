"""Controller-inclusive scalar-v2 correctness and timing benchmark."""

import hashlib
import json
import os
import platform
import time

from freeciv.pf_unified.golden import reproduce_golden
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.paths import REPO_ROOT
from freeciv_agent.planning import GroundedImpactPlanner
from freeciv_agent.pressure import (
    AtomState,
    CostVector,
    GoalState,
    ImpactPressureRanker,
    ImpactPressureRankerV2,
    Operation,
    PacketBudget,
    PacketCost,
    PacketScheduler,
    PressureEngine,
    PressureEngineV2,
    PressureGraph,
    PressureRule,
    PressureScheduler,
    Resolvability,
    ResourceKind,
    TruthState,
    validate_packet_schedule,
    validate_pressure_artifact,
)
from freeciv_agent.state import ProxyStateDTO


def _graph(arity=8):
    graph = PressureGraph()
    graph.add_atom(
        AtomState("goal", TruthState(0.1, 0.6)),
        Resolvability(infer=0.5, observe=0.5))
    premises = tuple(
        "premise-{}".format(index) for index in range(arity))
    for index, premise_id in enumerate(premises):
        graph.add_atom(
            AtomState(
                premise_id,
                TruthState(0.2 + 0.05 * index, 0.4 + 0.05 * index)),
            Resolvability(infer=0.2, observe=0.4, act=1.0))
    graph.add_rule(PressureRule(
        "all-prerequisites", premises, "goal",
        kind="and", causal_kind="procedural"))
    return graph, premises


def _file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _packet_schedule(v2_result, premises):
    operations = tuple(
        Operation(
            "operation-{}".format(index), premise_id, "act",
            CostVector(compute=0.1), causal_kind="procedural",
            packet_costs=(
                PacketCost(ResourceKind.ACTION, 1),
                PacketCost(ResourceKind.CPU, 1),
            ))
        for index, premise_id in enumerate(premises))
    scores = PressureScheduler().score_all(operations, v2_result)
    schedule = PacketScheduler().schedule(
        operations, scores, (
            PacketBudget(ResourceKind.ACTION, 4),
            PacketBudget(ResourceKind.CPU, 4),
        ))
    return schedule


def _snapshot_replay():
    rows = []
    for relative in (
            "benchmarks/freeciv/samples/real_state_turn0.json",
            "benchmarks/freeciv/samples/real_state_turn1.json"):
        path = os.path.join(REPO_ROOT, relative)
        before = _file_sha256(path)
        with open(path, encoding="utf-8") as stream:
            raw = json.load(stream)
        if (raw.get("turn") == 0 and raw.get("map") == {}
                and not raw.get("cities") and not raw.get("units")):
            raw = dict(raw)
            raw["map"] = {
                "height": 1, "tiles": [],
                "visibility": [], "width": 1}
        snapshot = ProxyStateDTO.parse(
            "pf-v2-snapshot-replay", 1, raw).to_snapshot()
        state_before = snapshot.event_payload()
        candidates = GroundedImpactPlanner({
            "pressure_enabled": False}).candidates(snapshot)
        if not candidates:
            rows.append({
                "candidate_count": 0,
                "path": relative,
                "source_unchanged": (
                    before == _file_sha256(path)),
                "state_unchanged": (
                    state_before == snapshot.event_payload()),
                "v1_selected": None,
                "v2_selected": None,
                "v2_selection_legal": True,
            })
            continue
        arguments = {
            "expansion_city_target": 5,
            "horizon_turn": max(1, int(snapshot.turn) + 2000),
        }
        v1_ordered, _ = ImpactPressureRanker().rank(
            snapshot, candidates, **arguments)
        v2_ordered, v2_artifact = ImpactPressureRankerV2().rank(
            snapshot, candidates, **arguments)
        selected_id = v2_artifact["schedule"][
            "selected_operation_id"]
        selected_score = next(
            row for row in v2_artifact["schedule"]["scores"]
            if row["operation"]["operation_id"] == selected_id)
        candidate_keys = frozenset(
            candidate.action_key for candidate in candidates)
        rows.append({
            "candidate_count": len(candidates),
            "path": relative,
            "source_unchanged": (
                before == _file_sha256(path)),
            "state_unchanged": (
                state_before == snapshot.event_payload()),
            "v1_selected": v1_ordered[0].to_dict(),
            "v2_pressure_valid": validate_pressure_artifact(
                v2_artifact["pressure"])["valid"],
            "v2_selected": v2_ordered[0].to_dict(),
            "v2_selection_legal": (
                v2_ordered[0].action_key in candidate_keys
                and selected_score["admissible"]
                and selected_score["operation"]["payload"]
                == v2_ordered[0].to_dict()),
        })
    return rows


def run_v2_verification():
    graph, premises = _graph()
    goal = GoalState("benchmark", "goal", utility=10.0, safety=True)
    before = tuple(atom.to_dict() for atom in graph.atoms)
    first = PressureEngineV2().propagate(graph, (goal,))
    second = PressureEngineV2().propagate(graph, (goal,))
    schedule = _packet_schedule(first, premises)
    legacy = reproduce_golden()
    snapshot_rows = _snapshot_replay()
    report = {
        "packet_validation": validate_packet_schedule(
            schedule.to_dict()),
        "pressure_validation": validate_pressure_artifact(
            first.to_dict()),
        "schema_version": "1.0",
        "snapshot_replay": snapshot_rows,
        "snapshot_replay_safe_and_legal": all(
            row["source_unchanged"]
            and row["state_unchanged"]
            and row["v2_selection_legal"]
            and row.get("v2_pressure_valid", True)
            for row in snapshot_rows),
        "truth_unchanged": before == tuple(
            atom.to_dict() for atom in graph.atoms),
        "v1_byte_exact": legacy["byte_exact"],
        "v1_replay_hash": legacy["replay_hash"],
        "v2_deterministic": (
            first.artifact_hash == second.artifact_hash),
        "v2_pressure_hash": first.artifact_hash,
    }
    report["valid"] = all((
        report["packet_validation"]["valid"],
        report["pressure_validation"]["valid"],
        report["truth_unchanged"],
        report["v1_byte_exact"],
        report["v2_deterministic"],
        report["snapshot_replay_safe_and_legal"],
    ))
    report["verification_hash"] = structural_hash(report)
    return report


def run_v2_timing(repetitions=500):
    repetitions = max(1, int(repetitions))
    graph, premises = _graph()
    goal = GoalState("benchmark", "goal", utility=10.0)

    started = time.perf_counter()
    for _ in range(repetitions):
        PressureEngine().propagate(graph, (goal,)).to_dict()
    v1_seconds = time.perf_counter() - started

    started = time.perf_counter()
    v2_result = None
    for _ in range(repetitions):
        v2_result = PressureEngineV2().propagate(
            graph, (goal,))
        v2_result.to_dict()
    v2_seconds = time.perf_counter() - started

    started = time.perf_counter()
    for _ in range(repetitions):
        _packet_schedule(v2_result, premises).to_dict()
    packet_seconds = time.perf_counter() - started

    v1_mean = v1_seconds * 1000.0 / repetitions
    v2_mean = v2_seconds * 1000.0 / repetitions
    packet_mean = packet_seconds * 1000.0 / repetitions
    value = {
        "measurement_scope": (
            "controller-inclusive Python wall time including semantic "
            "transport, validation-ready serialization, scoring, packet "
            "reservation, and accounting"),
        "packet_schedule_8_operations": {
            "mean_ms": packet_mean,
            "repetitions": repetitions,
            "total_seconds": packet_seconds,
        },
        "platform": {
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "system": platform.system(),
        },
        "scalar_v1_8_premise": {
            "mean_ms": v1_mean,
            "repetitions": repetitions,
            "total_seconds": v1_seconds,
        },
        "scalar_v2_8_premise": {
            "mean_ms": v2_mean,
            "repetitions": repetitions,
            "total_seconds": v2_seconds,
        },
        "schema_version": "1.0",
        "v2_over_v1_ratio": v2_mean / v1_mean,
        "v2_plus_packets_over_v1_ratio": (
            (v2_mean + packet_mean) / v1_mean),
    }
    value["timing_hash"] = structural_hash(value)
    return value
