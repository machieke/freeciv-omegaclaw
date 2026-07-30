"""Deterministic generation and replay of the scalar-v1 golden corpus."""

import copy
import hashlib
import json
import os
import platform
import tempfile
import time
from types import SimpleNamespace

from freeciv.pf_pressure_benchmark import (
    run_pressure_concentration_benchmark,
)
from freeciv.pf_pressure_replay import replay_snapshot_paths
from freeciv_agent.events.schema import canonical_json_bytes, structural_hash
from freeciv_agent.events.validator import validate_file
from freeciv_agent.events.writer import EventWriter
from freeciv_agent.paths import REPO_ROOT
from freeciv_agent.pf_runtime import (
    build_runtime_activation,
    canonical_declaration,
    emit_runtime_activation,
)
from freeciv_agent.pressure import (
    AtomState,
    ConductanceState,
    CostVector,
    GoalState,
    Operation,
    PressureEngine,
    PressureGraph,
    PressureRule,
    PressureScheduler,
    ProofPressureAdapter,
    Resolvability,
    ScalarRouteBid,
    SmoothedScalarController,
    TruthState,
)

from .baseline import baseline_identity, load_baseline_manifest


GOLDEN_NAMES = (
    "capital-pressure.json",
    "concentration-256.json",
    "proof-dag.json",
    "observation-action.json",
    "impact-snapshot-replay.json",
    "conductance-replay.json",
    "runtime-matrix.json",
    "event-contract.json",
    "smoothed-scalar.json",
)


def _atom(atom_id, strength=0.0, confidence=1.0, resolvability=None):
    return (
        AtomState(
            atom_id,
            TruthState(strength, confidence, crisp=True)),
        resolvability or Resolvability(infer=1.0),
    )


def _capital_graph():
    graph = PressureGraph()
    rows = (
        _atom(
            "survives", 0.42, 0.65,
            Resolvability(infer=0.5, retain=0.5)),
        _atom(
            "no-attack", 0.25, 0.8,
            Resolvability(observe=0.8, act=0.2)),
        _atom(
            "defense", 0.25, 0.9,
            Resolvability(infer=0.3, act=0.8)),
        _atom(
            "treasury", 0.70, 0.70,
            Resolvability(observe=1.0, infer=0.2)),
        _atom(
            "archer-available", 0.95, 0.90,
            Resolvability(observe=0.1, infer=0.2)),
        _atom("buy-archer", 0.0, 1.0, Resolvability(act=1.0)),
    )
    for atom, resolvability in rows:
        graph.add_atom(atom, resolvability)
    graph.add_rule(PressureRule(
        "survival-routes", ("defense", "no-attack"), "survives",
        kind="or", causal_kind="procedural",
        premise_weights=(0.69, 0.31)))
    graph.add_rule(PressureRule(
        "buy-route", ("treasury", "archer-available", "buy-archer"),
        "defense", kind="and", causal_kind="procedural"))
    return graph


def _proof_query():
    leaf_atom = {
        "args": ["player", "Alphabet"],
        "atom_id": "leaf-atom",
        "crisp": True,
        "predicate": "has-tech",
        "provenance_ids": [],
        "tv": {"confidence": 0.99, "strength": 1.0},
    }
    goal_atom = {
        "args": ["player", "Writing"],
        "atom_id": "goal-atom",
        "crisp": True,
        "predicate": "researchable",
        "provenance_ids": [],
        "tv": {"confidence": 0.99, "strength": 1.0},
    }
    nodes = [
        {
            "atom": goal_atom,
            "crisp": True,
            "kind": "goal",
            "node_id": "root",
            "premise_node_refs": ["leaf"],
            "rule_applied": "compiled-writing",
            "satisfied": False,
            "subtree_hash": "1" * 64,
            "tv": {"confidence": 0.99, "strength": 0.0},
        },
        {
            "atom": leaf_atom,
            "crisp": True,
            "kind": "premise",
            "node_id": "leaf",
            "premise_node_refs": [],
            "rule_applied": None,
            "satisfied": False,
            "subtree_hash": "2" * 64,
            "tv": {"confidence": 0.99, "strength": 0.0},
        },
    ]
    return SimpleNamespace(
        goal=SimpleNamespace(goal_id="research-writing"),
        proof={
            "nodes": nodes,
            "root_node_id": "root",
            "structural_hash": structural_hash(nodes),
        },
    )


def _wrap(manifest, name, payload, config, fixture,
          artifact_type="semantic"):
    value = {
        "artifact_type": artifact_type,
        "baseline_id": manifest["baseline_id"],
        "baseline_identity": baseline_identity(manifest),
        "config_hash": structural_hash(config),
        "fixture_hash": structural_hash(fixture),
        "name": name,
        "payload": payload,
        "payload_hash": structural_hash(payload),
        "random_seed": copy.deepcopy(manifest["random_seed"]),
        "schema_version": "1.0",
        "source_commit": manifest["source"]["commit"],
    }
    value["artifact_hash"] = structural_hash(value)
    return value


def capital_pressure_artifact(manifest):
    graph = _capital_graph()
    before = [atom.to_dict() for atom in graph.atoms]
    goal = GoalState(
        "defend-capital", "survives", 0.90, utility=100.0)
    engine = PressureEngine()
    result = engine.propagate(graph, (goal,))
    payload = {
        "graph_hash": graph.artifact_hash,
        "pressure": result.to_dict(),
        "truth_after": [atom.to_dict() for atom in graph.atoms],
        "truth_before": before,
        "truth_unchanged": before == [
            atom.to_dict() for atom in graph.atoms],
    }
    return _wrap(
        manifest, "capital-pressure", payload,
        result.config.to_dict(),
        {"graph_hash": graph.artifact_hash, "goal": goal.to_dict()})


def concentration_artifact(manifest):
    result = run_pressure_concentration_benchmark()
    return _wrap(
        manifest, "concentration-256", result.to_dict(), result.config,
        {"branch_depth": result.branch_depth,
         "graph_hash": result.graph_hash,
         "irrelevant_branches": result.irrelevant_branches})


def proof_dag_artifact(manifest):
    query = _proof_query()
    before = copy.deepcopy(query.proof)
    decision = ProofPressureAdapter().decision_artifact(query, utility=4.0)
    payload = {
        "decision": decision,
        "proof_after": query.proof,
        "proof_before": before,
        "truth_unchanged": before == query.proof,
    }
    return _wrap(
        manifest, "proof-dag", payload, {"utility": 4.0}, before)


def observation_action_artifact(manifest):
    graph = PressureGraph()
    atom, resolvability = _atom(
        "uncertain-threat", strength=0.2,
        resolvability=Resolvability(observe=1.0, act=1.0))
    graph.add_atom(atom, resolvability)
    before = [row.to_dict() for row in graph.atoms]
    result = PressureEngine().propagate(
        graph,
        (GoalState(
            "survive", "uncertain-threat", utility=10.0),))
    operations = (
        Operation(
            "act", "uncertain-threat", "act",
            CostVector(resource=20),
            causal_kind="procedural"),
        Operation(
            "observe", "uncertain-threat", "observe",
            CostVector(compute=1),
            causal_kind="diagnostic", information_gain=0.8),
    )
    decision = PressureScheduler().decision_artifact(operations, result)
    payload = {
        "pressure": result.to_dict(),
        "schedule": decision,
        "truth_unchanged": before == [
            row.to_dict() for row in graph.atoms],
    }
    return _wrap(
        manifest, "observation-action", payload,
        result.config.to_dict(),
        {"graph_hash": graph.artifact_hash,
         "operations": [row.to_dict() for row in operations]})


def snapshot_replay_artifact(manifest):
    relative = (
        "benchmarks/freeciv/samples/real_state_turn0.json",
        "benchmarks/freeciv/samples/real_state_turn1.json",
    )
    paths = tuple(os.path.join(REPO_ROOT, path) for path in relative)
    replay = replay_snapshot_paths(
        paths,
        relative_to=REPO_ROOT,
        planner_identity=manifest[
            "solvers"]["live_adapter"])
    fixture = [
        row for row in manifest["fixtures"]["files"]
        if row["path"] in relative
    ]
    return _wrap(
        manifest, "impact-snapshot-replay", replay,
        {"policy": {}, "replay_schema_version": "1.0"}, fixture)


def conductance_replay_artifact(manifest):
    state = ConductanceState(
        identity="pf-unified-golden",
        learning_rate=0.10,
        no_progress_rate=0.10,
        initial_conductance=0.50)
    updates = (
        state.feedback(
            "production_economy", True, "feedback-success",
            realized_relief=0.75,
            relief_source="golden-authoritative-goal"),
        state.feedback(
            "production_economy", True, "feedback-success",
            realized_relief=0.75,
            relief_source="golden-authoritative-goal"),
        state.feedback(
            "production_economy", False, "feedback-no-progress",
            realized_relief=0.0,
            relief_source="golden-authoritative-goal"),
    )
    payload = {
        "duplicate_was_idempotent": not updates[1].applied,
        "snapshot": state.snapshot(),
        "updates": [row.to_dict() for row in updates],
    }
    return _wrap(
        manifest, "conductance-replay", payload,
        state.snapshot()["configuration"],
        {"feedback_ids": [
            "feedback-success", "feedback-success",
            "feedback-no-progress"]})


def _runtime_cases():
    full_policy = {
        "pressure_enabled": True,
        "pressure_learning_enabled": True,
    }
    return (
        ("engine-full", "engine-live", {"scheduler": True}, full_policy),
        ("engine-pressure-off", "engine-live", {"scheduler": True}, {
            "pressure_enabled": False,
            "pressure_learning_enabled": True,
        }),
        ("engine-no-scheduler", "engine-live", {"scheduler": False},
         full_policy),
        ("representative", "representative", {"scheduler": True},
         full_policy),
    )


def runtime_matrix_artifact(manifest):
    adapter = manifest[
        "solvers"]["live_adapter"]
    declaration = canonical_declaration(
        adapter=adapter)
    rows = []
    for case, backend, capabilities, policy in _runtime_cases():
        rows.append({
            "case": case,
            "report": build_runtime_activation(
                declaration, backend, capabilities, policy,
                expected_adapter=adapter),
        })
    return _wrap(
        manifest, "runtime-matrix", {"cases": rows},
        {"runtime_schema": declaration["schema_version"]},
        {"declaration": declaration,
         "cases": [row[0] for row in _runtime_cases()]})


def event_contract_artifact(manifest):
    identifiers = iter(
        "event-{:03d}".format(index) for index in range(20))
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(
            path, "pf-unified-golden",
            clock=lambda: "2026-07-29T00:00:00Z",
            id_factory=lambda: next(identifiers),
            durable=False)
        root = writer.emit("run_started", 0, {
            "condition_id": "engine-full",
            "manifest_identity": baseline_identity(manifest),
        })
        case = _runtime_cases()[0]
        adapter = manifest[
            "solvers"]["live_adapter"]
        report = build_runtime_activation(
            canonical_declaration(
                adapter=adapter),
            case[1], case[2], case[3],
            expected_adapter=adapter)
        parent, activation_events = emit_runtime_activation(
            writer, 0, root["event_id"], report,
            "engine-full", "golden")
        validation = validate_file(path)
        with open(path, "rb") as stream:
            raw = stream.read()
    events = [
        json.loads(line.decode("utf-8"))
        for line in raw.splitlines() if line.strip()
    ]
    payload = {
        "event_bytes_sha256": hashlib.sha256(raw).hexdigest(),
        "events": events,
        "final_parent": parent,
        "phase_event_count": len(activation_events),
        "validation": validation.to_dict(),
    }
    return _wrap(
        manifest, "event-contract", payload,
        {"event_schema_version": writer.schema_version},
        {"runtime_activation_hash": report["activation_hash"]})


def smoothed_scalar_artifact(manifest):
    controller = SmoothedScalarController()
    frames = (
        (
            ScalarRouteBid("economy", 1.0, pf_advantage=0.10),
            ScalarRouteBid("defense", 0.8, bridge_estimate=0.05),
        ),
        (
            ScalarRouteBid("economy", 0.7, pf_advantage=0.10),
            ScalarRouteBid("defense", 1.15, bridge_estimate=0.05),
        ),
        (
            ScalarRouteBid("economy", 0.6, pf_advantage=0.05),
            ScalarRouteBid("defense", 1.25, bridge_estimate=0.10),
        ),
        (
            ScalarRouteBid("economy", 0.9, pf_advantage=0.05),
            ScalarRouteBid("defense", 0.0, admissible=False),
        ),
    )
    decisions = [
        controller.rank(frame, step).to_dict()
        for step, frame in enumerate(frames)
    ]
    payload = {
        "decisions": decisions,
        "solver_identity": controller.SOLVER_IDENTITY,
    }
    fixture = [
        [bid.to_dict() for bid in frame] for frame in frames]
    return _wrap(
        manifest, "smoothed-scalar", payload,
        controller.config.to_dict(), fixture)


_GENERATORS = (
    ("capital-pressure.json", capital_pressure_artifact),
    ("concentration-256.json", concentration_artifact),
    ("proof-dag.json", proof_dag_artifact),
    ("observation-action.json", observation_action_artifact),
    ("impact-snapshot-replay.json", snapshot_replay_artifact),
    ("conductance-replay.json", conductance_replay_artifact),
    ("runtime-matrix.json", runtime_matrix_artifact),
    ("event-contract.json", event_contract_artifact),
    ("smoothed-scalar.json", smoothed_scalar_artifact),
)


def generate_artifacts(manifest=None):
    manifest = load_baseline_manifest() if manifest is None else manifest
    return tuple(
        (name, generator(manifest)) for name, generator in _GENERATORS)


def capture_golden(directory=None, manifest=None):
    manifest = load_baseline_manifest() if manifest is None else manifest
    directory = os.path.abspath(
        directory or os.path.join(
            REPO_ROOT, manifest["golden"]["directory"]))
    os.makedirs(directory, exist_ok=True)
    rows = []
    for name, artifact in generate_artifacts(manifest):
        path = os.path.join(directory, name)
        temporary = path + ".tmp"
        with open(temporary, "wb") as stream:
            stream.write(canonical_json_bytes(artifact))
            stream.write(b"\n")
        os.replace(temporary, path)
        rows.append({
            "path": os.path.relpath(path, REPO_ROOT).replace(os.sep, "/"),
            "sha256": hashlib.sha256(
                canonical_json_bytes(artifact) + b"\n").hexdigest(),
        })
    return rows


def reproduce_golden(manifest=None):
    manifest = load_baseline_manifest() if manifest is None else manifest
    expected = dict(
        (os.path.basename(row["path"]), row["sha256"])
        for row in manifest["golden"]["artifacts"])
    actual = dict(
        (name, hashlib.sha256(
            canonical_json_bytes(artifact) + b"\n").hexdigest())
        for name, artifact in generate_artifacts(manifest))
    mismatches = [
        {"actual": actual.get(name), "expected": expected.get(name),
         "name": name}
        for name in sorted(set(actual) | set(expected))
        if actual.get(name) != expected.get(name)
    ]
    report = {
        "actual": actual,
        "baseline_id": manifest["baseline_id"],
        "byte_exact": not mismatches,
        "expected": expected,
        "mismatches": mismatches,
        "schema_version": "1.0",
    }
    report["replay_hash"] = structural_hash(report)
    return report


def controller_timings(repetitions=20):
    """Measure end-to-end controller calls, including guards and artifacts."""
    repetitions = max(1, int(repetitions))
    graph = _capital_graph()
    goal = GoalState(
        "defend-capital", "survives", 0.90, utility=100.0)
    started = time.perf_counter()
    for _ in range(repetitions):
        PressureEngine().propagate(graph, (goal,)).to_dict()
    capital_seconds = time.perf_counter() - started

    bids = (
        ScalarRouteBid("economy", 1.0, pf_advantage=0.1),
        ScalarRouteBid("defense", 0.9, bridge_estimate=0.1),
    )
    started = time.perf_counter()
    for _ in range(repetitions):
        controller = SmoothedScalarController()
        for step in range(10):
            controller.rank(bids, step).to_dict()
    scalar_seconds = time.perf_counter() - started

    started = time.perf_counter()
    for _ in range(max(1, repetitions // 10)):
        run_pressure_concentration_benchmark().to_dict()
    concentration_repetitions = max(1, repetitions // 10)
    concentration_seconds = time.perf_counter() - started

    snapshot_paths = (
        os.path.join(
            REPO_ROOT,
            "benchmarks/freeciv/samples/real_state_turn0.json"),
        os.path.join(
            REPO_ROOT,
            "benchmarks/freeciv/samples/real_state_turn1.json"),
    )
    replay_repetitions = max(1, repetitions // 10)
    started = time.perf_counter()
    for _ in range(replay_repetitions):
        replay_snapshot_paths(
            snapshot_paths, relative_to=REPO_ROOT)
    replay_seconds = time.perf_counter() - started
    value = {
        "capital_pressure": {
            "mean_ms": capital_seconds * 1000.0 / repetitions,
            "repetitions": repetitions,
            "total_seconds": capital_seconds,
        },
        "concentration_256": {
            "mean_ms": (
                concentration_seconds * 1000.0
                / concentration_repetitions),
            "repetitions": concentration_repetitions,
            "total_seconds": concentration_seconds,
        },
        "measurement_scope": (
            "controller-inclusive Python wall time including validation, "
            "ranking, allocation, and artifact serialization"),
        "platform": {
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "system": platform.system(),
        },
        "snapshot_replay_2_states": {
            "mean_ms": replay_seconds * 1000.0 / replay_repetitions,
            "repetitions": replay_repetitions,
            "total_seconds": replay_seconds,
        },
        "schema_version": "1.0",
        "smoothed_scalar_10_steps": {
            "mean_ms": scalar_seconds * 1000.0 / repetitions,
            "repetitions": repetitions,
            "total_seconds": scalar_seconds,
        },
    }
    value["timing_hash"] = structural_hash(value)
    return value
