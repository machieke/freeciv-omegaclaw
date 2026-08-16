"""Isolated trial execution and artifact emission for the scalability campaign."""

import gc
import hashlib
import json
import math
import os
import platform
import resource
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from freeciv_agent.events.schema import structural_hash

from .atomspace_generator import apply_atomspace_churn, build_atomspace_case
from .baseline import load_frozen_baseline, verify_frozen_baseline
from .bridge_generator import (
    build_bridge_case,
    apply_bridge_edge_failure,
    evaluate_bridge_case,
    evaluate_corrected_probe_readout,
    evaluate_path_persistence,
    evaluate_protected_readout,
    evaluate_scalar_readout,
    evaluate_source_sink_flow_readout,
)
from .fluid_generator import (
    apply_fluid_edge_failures,
    build_fluid_case,
    build_fluid_graph_case,
    run_fluid_case,
)
from .combined import evaluate_combined_case
from .captured_amplifier import amplify_captured_records
from .captured_loader import load_captured_revisions
from .model import ScaleCell, TrialResult, TrialSpec
from .proof_generator import (
    build_proof_case,
    build_proof_dag_case,
    evaluate_proof_case,
)
from .retention import run_retention_cycles


GENERATOR_VERSION = "freeciv-scaling-generators/1.0"
DEFAULT_WALL_SECONDS = 120
DEFAULT_RSS_BYTES = 16 * 1024 * 1024 * 1024

ATOMSPACE_TIERS = {
    "A0": {"atom_count": 2500, "scope_count": 25,
           "churn_fraction": 0.01, "support_multiplicity": 1,
           "topology": "local"},
    "A1": {"atom_count": 10000, "scope_count": 100,
           "churn_fraction": 0.01, "support_multiplicity": 1,
           "topology": "local"},
    "A2": {"atom_count": 25000, "scope_count": 250,
           "churn_fraction": 0.01, "support_multiplicity": 1,
           "topology": "local"},
    "A3": {"atom_count": 50000, "scope_count": 500,
           "churn_fraction": 0.01, "support_multiplicity": 1,
           "topology": "local"},
    "A4": {"atom_count": 100000, "scope_count": 1000,
           "churn_fraction": 0.01, "support_multiplicity": 1,
           "topology": "local"},
    "A5": {"atom_count": 250000, "scope_count": 2500,
           "churn_fraction": 0.01, "support_multiplicity": 1,
           "topology": "local"},
}
PROOF_TIERS = {
    "P0": {"depth": 12, "relevant_nodes": 132, "distractor_count": 0},
    "P1": {"depth": 24, "relevant_nodes": 1000, "distractor_count": 10000},
    "P2": {"depth": 48, "relevant_nodes": 10000, "distractor_count": 25000},
    "P3": {"depth": 96, "relevant_nodes": 100000, "distractor_count": 100000},
    "P4": {"depth": 128, "relevant_nodes": 250000, "distractor_count": 250000},
}
BRIDGE_TIERS = {
    "B0": {"node_count": 354, "edge_count": 855,
           "candidate_count": 34, "goal_count": 2},
    "B1": {"node_count": 1000, "edge_count": 4000,
           "candidate_count": 128, "goal_count": 4},
    "B2": {"node_count": 5000, "edge_count": 20000,
           "candidate_count": 512, "goal_count": 8},
    "B3": {"node_count": 10000, "edge_count": 40000,
           "candidate_count": 2048, "goal_count": 16},
    "B4": {"node_count": 50000, "edge_count": 200000,
           "candidate_count": 8192, "goal_count": 32},
    "B5": {"node_count": 100000, "edge_count": 400000,
           "candidate_count": 16384, "goal_count": 64},
}
FLUID_TIERS = {
    "F0": {"edge_update_budget": 10000, "length": 101, "microsteps": 50},
    "F1": {"edge_update_budget": 100000, "length": 1001, "microsteps": 50},
    "F2": {"edge_update_budget": 1000000, "length": 10001, "microsteps": 50},
    "F3": {"edge_update_budget": 10000000, "length": 100001, "microsteps": 50},
    "F4": {"edge_update_budget": 50000000, "length": 100001, "microsteps": 250},
}
CAPTURED_TIERS = {
    "CA2": {"target_atom_count": 25000, "synthetic_tier": "A2"},
    "CA4": {"target_atom_count": 100000, "synthetic_tier": "A4"},
}
COMBINED_TIERS = {}
for _index in range(16):
    _atom_high = bool(_index & 1)
    _proof_high = bool(_index & 2)
    _bridge_high = bool(_index & 4)
    _flow_high = bool(_index & 8)
    COMBINED_TIERS["C{:02d}".format(_index)] = {
        "atom_tier": "A4" if _atom_high else "A2",
        "atomspace": dict(ATOMSPACE_TIERS["A4" if _atom_high else "A2"]),
        "bridge": dict(BRIDGE_TIERS["B3" if _bridge_high else "B1"]),
        "bridge_tier": "B3" if _bridge_high else "B1",
        "fluid": (
            dict(FLUID_TIERS["F2"]) if _flow_high else None),
        "fluid_tier": "F2" if _flow_high else "none",
        "proof": dict(PROOF_TIERS["P2" if _proof_high else "P1"],
                      shape="shared_dag"),
        "proof_tier": "P2" if _proof_high else "P1",
    }
COMBINED_TIERS["C16-center"] = {
    "atom_tier": "A3",
    "atomspace": dict(ATOMSPACE_TIERS["A3"]),
    "bridge": dict(BRIDGE_TIERS["B2"]),
    "bridge_tier": "B2",
    "fluid": dict(FLUID_TIERS["F1"]),
    "fluid_tier": "F1",
    "proof": {
        "depth": 36,
        "relevant_nodes": 5000,
        "distractor_count": 17500,
        "shape": "shared_dag",
    },
    "proof_tier": "center",
}
TIER_TABLES = {
    "atomspace": ATOMSPACE_TIERS,
    "proof": PROOF_TIERS,
    "bridge": BRIDGE_TIERS,
    "fluid": FLUID_TIERS,
    "combined": COMBINED_TIERS,
    "captured": CAPTURED_TIERS,
}


def _source_digest(repo_root):
    roots = (
        "benchmarks/freeciv/scaling",
        "scripts/freeciv/run_scalability_campaign.py",
        "scripts/freeciv/audit_scalability_campaign.py",
        "profile/dependent_atomspace_scaling_shadow.yaml",
        "profile/freeciv_scalability_experiment.yaml",
        "schemas/freeciv-scaling",
        "src/freeciv_agent/beliefs/rule_engine.py",
        "src/freeciv_agent/flow_control/advection.py",
        "src/freeciv_agent/flow_control/candidate_selector.py",
        "src/freeciv_agent/flow_control/model.py",
        "src/freeciv_agent/flow_control/potentials.py",
        "src/freeciv_agent/flow_control/probes.py",
        "src/freeciv_agent/flow_control/projection.py",
        "src/freeciv_agent/state/atomspace/store.py",
        "src/freeciv_agent/state/atomspace/transaction.py",
    )
    files = []
    for relative in roots:
        path = os.path.join(repo_root, relative)
        if os.path.isdir(path):
            for directory, _names, filenames in os.walk(path):
                for filename in filenames:
                    if filename.endswith((".py", ".json", ".yaml")):
                        files.append(os.path.join(directory, filename))
        elif os.path.isfile(path):
            files.append(path)
    digest = hashlib.sha256()
    for path in sorted(files):
        relative = os.path.relpath(path, repo_root)
        digest.update(relative.encode("utf-8") + b"\0")
        with open(path, "rb") as handle:
            while True:
                block = handle.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
    return digest.hexdigest()


def environment_identity(repo_root=None):
    repo_root = repo_root or os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    commit = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=repo_root,
        universal_newlines=True).strip()
    dirty = bool(subprocess.check_output(
        ("git", "status", "--porcelain"), cwd=repo_root,
        universal_newlines=True).strip())
    load = os.getloadavg() if hasattr(os, "getloadavg") else ()
    contract = {
        "code_digest": _source_digest(repo_root),
        "cpu_count": os.cpu_count(),
        "generator_version": GENERATOR_VERSION,
        "git_commit": commit,
        "git_dirty": dirty,
        "machine": platform.machine(),
        "memory_limit_bytes": DEFAULT_RSS_BYTES,
        "os": platform.platform(),
        "python": platform.python_version(),
        "wall_limit_seconds": DEFAULT_WALL_SECONDS,
    }
    material = dict(contract)
    material.update({
        "load_average": list(load),
        "measurement_contract_hash": structural_hash(contract),
        "schema_version": "1.0",
    })
    material["environment_hash"] = structural_hash(material)
    return material


def tier_payload(surface, tier, seed=1729, overrides=None):
    try:
        parameters = dict(TIER_TABLES[surface][tier])
    except KeyError:
        raise ValueError("unknown surface/tier: {}/{}".format(surface, tier))
    parameters.update(overrides or {})
    return {
        "parameters": parameters,
        "seed": int(seed),
        "surface": surface,
        "tier": tier,
    }


def _peak_rss_bytes():
    # Linux reports ru_maxrss in KiB; macOS reports bytes.
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def _execute(payload):
    surface = payload["surface"]
    tier = payload["tier"]
    seed = int(payload["seed"])
    parameters = dict(payload["parameters"])
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    gc_before = gc.get_count()
    correctness = {}
    actual = {}
    detail = {}
    if surface == "atomspace":
        generator_started = time.perf_counter()
        case = build_atomspace_case(
            atom_count=int(parameters["atom_count"]),
            scope_count=int(parameters["scope_count"]),
            support_multiplicity=int(parameters.get("support_multiplicity", 1)),
            topology=parameters.get("topology", "mixed"),
            seed=seed,
            insertion_order=parameters.get("insertion_order", "canonical"),
        )
        detail["generator_ms"] = (
            time.perf_counter() - generator_started) * 1000.0
        churn = apply_atomspace_churn(
            case, float(parameters.get("churn_fraction", 0.01)))
        actual = {
            "affected_atoms": churn.affected_atom_count,
            "changed_dependencies": churn.changed_dependency_count,
            "dependency_edges": sum(
                len(row.dependencies) for record in case.records
                for row in record.supports),
            "live_revision_atoms": case.atom_count,
            "scopes": case.scope_count,
            "supports": case.support_count,
            "invalidated_supports": churn.invalidated_support_count,
            "unsupported_atoms": churn.unsupported_atom_count,
        }
        correctness = {
            "cold_incremental_equivalent": churn.equivalent,
            "count_exact": case.atom_count == int(parameters["atom_count"]),
            "revision_id": case.revision_id,
            "semantic_hash": case.artifact_hash,
            "synthetic_namespace_only": all(
                row.key.namespace.value == "diagnostic" for row in case.records),
        }
        detail["cold_rebuild_ms"] = churn.cold_ms
        detail["incremental_ms"] = churn.incremental_ms
        if int(parameters.get("retention_cycles", 0)) > 0:
            retention = run_retention_cycles(
                int(parameters["atom_count"]),
                int(parameters["scope_count"]),
                cycles=int(parameters["retention_cycles"]),
                retention=int(parameters.get("revision_retention", 4)),
                seed=seed,
                topology=parameters.get("topology", "local"))
            actual["retention_cycles"] = retention.cycles
            actual["maximum_retained_revisions"] = (
                retention.maximum_retained_revisions)
            actual["maximum_retained_scopes"] = (
                retention.maximum_retained_scopes)
            correctness["revision_retention_no_leak"] = (
                not retention.revision_leak)
            correctness["scope_retention_no_leak"] = (
                not retention.scope_leak)
            correctness["rss_plateau_within_5_percent"] = (
                retention.rss_plateau_within_5_percent)
            detail["rss_plateau_drift_fraction"] = (
                retention.plateau_rss_drift_fraction)
    elif surface == "proof":
        generator_started = time.perf_counter()
        if "relevant_nodes" in parameters:
            case = build_proof_dag_case(
                int(parameters["depth"]),
                int(parameters["relevant_nodes"]),
                parameters.get("shape", "and_tree"),
                int(parameters.get("distractor_count", 0)))
        else:
            case = build_proof_case(
                int(parameters["depth"]), parameters.get("shape", "chain"))
        detail["generator_ms"] = (
            time.perf_counter() - generator_started) * 1000.0
        evaluation = evaluate_proof_case(case)
        actual = {
            "blockers": evaluation.prerequisite_count,
            "proof_depth_requested": case.depth,
            "proof_records": evaluation.proof_record_count,
            "relevant_rules": case.expected_rule_count,
            "indexed_distractor_rules": int(
                parameters.get("distractor_count", 0)),
        }
        actual.update(dict(evaluation.work_counters))
        correctness = {
            "expected_status": case.expected_status,
            "matches_reference": evaluation.matches_reference,
            "outcome_hash": evaluation.artifact_hash,
            "status": evaluation.status,
            "truncated": evaluation.truncated,
        }
        detail["kernel_elapsed_ms"] = evaluation.elapsed_ms
    elif surface == "bridge":
        generator_started = time.perf_counter()
        case = build_bridge_case(
            int(parameters["node_count"]),
            int(parameters["edge_count"]),
            int(parameters["candidate_count"]),
            int(parameters["goal_count"]),
            seed,
            parameters.get("topology", "disconnected_distractors"),
        )
        if parameters.get("topology") == "dynamic_failure":
            case = apply_bridge_edge_failure(case)
        detail["generator_ms"] = (
            time.perf_counter() - generator_started) * 1000.0
        controller_started = time.perf_counter()
        arm = parameters.get("arm", "protected_message")
        evaluation = None
        if arm in ("scalar_pf_v2", "source_sink_flow"):
            readout = evaluate_scalar_readout(
                case, scalar_top_k=int(parameters.get("scalar_top_k", 3)))
        else:
            evaluation = evaluate_bridge_case(
                case, int(parameters.get("max_iterations", 64)))
            readout = evaluate_protected_readout(
                case, evaluation,
                scalar_top_k=int(parameters.get("scalar_top_k", 3)),
                bridge_top_k=int(parameters.get("bridge_top_k", 8)),
                maximum_nodes=parameters.get("readout_maximum_nodes"),
                maximum_edges=parameters.get("readout_maximum_edges"),
                readout_policy=parameters.get(
                    "readout_policy", "protected-message-union"))
        probe_readout = None
        if arm == "corrected_probe" and not case.failed_edge_ids:
            probe_readout = evaluate_corrected_probe_readout(
                case,
                path_count=int(parameters.get("probe_path_count", 128)),
                max_steps=int(parameters.get("probe_max_steps", 16)),
                maximum_regions=int(parameters.get("bridge_top_k", 8)),
                seed=seed)
            readout = probe_readout.protected_readout
        persistence = None
        if arm == "path_persistence" and not case.failed_edge_ids:
            persistence = evaluate_path_persistence(
                case,
                iterations=int(parameters.get("persistence_iterations", 8)),
                momentum=float(parameters.get("persistence_momentum", 0.8)),
                dwell_threshold=int(parameters.get("dwell_threshold", 3)),
                maximum_regions=int(parameters.get("bridge_top_k", 8)))
            readout = persistence.protected_readout
        source_sink = None
        if arm == "source_sink_flow":
            source_sink = evaluate_source_sink_flow_readout(
                case,
                microsteps=int(parameters.get("flow_microsteps", 1)),
                velocity=float(parameters.get("flow_velocity", 0.25)),
                maximum_regions=int(parameters.get("bridge_top_k", 8)))
            readout = source_sink.protected_readout
        actual = {
            "candidates": case.candidate_count,
            "edges": case.edge_count,
            "estimates": evaluation.estimate_count if evaluation else 0,
            "goals": len(case.goal_ids),
            "nodes": case.node_count,
            "failed_edges": len(case.failed_edge_ids),
            "protected_candidates": len(readout.protected_operation_ids),
            "bridge_additions": len(readout.bridge_added_operation_ids),
        }
        correctness = {
            "bridge_recall_applicable": arm != "scalar_pf_v2",
            "bridge_separated": (
                evaluation.bridge_separated if evaluation else None),
            "deterministic_hash": (
                evaluation.deterministic_hash
                if evaluation else readout.artifact_hash),
            "semantic_hash": case.artifact_hash,
            "expected_bridge_recalled": readout.expected_bridge_recalled,
            "fallback_reason": readout.fallback_reason,
            "fallback_required": readout.fallback_required,
            "protected_readout_hash": readout.artifact_hash,
            "scalar_order_preserved": readout.scalar_order_preserved,
            "scalar_winner_recalled": readout.scalar_winner_recalled,
            "signal_ledger_hash": readout.signal_ledger_hash,
            "truth_hash_unchanged": (
                case.view.probe_semantic_hash
                == case.view.probe_semantic_hash),
        }
        detail["kernel_elapsed_ms"] = (
            evaluation.elapsed_ms if evaluation else 0.0)
        if probe_readout is not None:
            actual["probe_paths"] = probe_readout.path_count
            correctness["probe_healthy"] = probe_readout.probe_healthy
            correctness["probe_fallback_to_messages"] = (
                probe_readout.fallback_to_messages)
            detail["minimum_effective_sample_fraction"] = (
                probe_readout.minimum_effective_sample_fraction)
            detail["minimum_path_diversity"] = (
                probe_readout.minimum_path_diversity)
        if persistence is not None:
            actual["persistence_iterations"] = persistence.iterations
            actual["persistence_state_entries"] = (
                persistence.maximum_state_entries)
            actual["persisted_candidates"] = len(
                persistence.persisted_operation_ids)
            correctness["persistence_hash"] = persistence.artifact_hash
        if source_sink is not None:
            actual["flow_edge_updates"] = source_sink.edge_updates
            actual["flow_microsteps"] = source_sink.microsteps
            correctness["flow_healthy"] = source_sink.healthy
            correctness["flow_mass_within_1e_9"] = (
                source_sink.maximum_normalized_mass_error <= 1e-9)
            correctness["flow_no_positivity_corrections"] = (
                source_sink.positivity_corrections == 0)
            correctness["flow_fallback_to_messages"] = (
                source_sink.fallback_to_messages)
            detail["flow_maximum_normalized_mass_error"] = (
                source_sink.maximum_normalized_mass_error)
            detail["kernel_elapsed_ms"] = source_sink.wall_ms
        detail["controller_inclusive_ms"] = (
            time.perf_counter() - controller_started) * 1000.0
    elif surface == "fluid":
        generator_started = time.perf_counter()
        if parameters.get("topology", "corridor") == "sparse_dag":
            case = build_fluid_graph_case(
                int(parameters["edge_update_budget"]),
                int(parameters["microsteps"]),
                int(parameters.get("average_degree", 4)),
                float(parameters.get("velocity", 0.25)))
        else:
            case = build_fluid_case(
                int(parameters["length"]), int(parameters["microsteps"]),
                float(parameters.get("velocity", 0.25)))
        if float(parameters.get("failure_fraction", 0.0)) > 0.0:
            case = apply_fluid_edge_failures(
                case, float(parameters["failure_fraction"]), seed)
        detail["generator_ms"] = (
            time.perf_counter() - generator_started) * 1000.0
        run = run_fluid_case(case, aggregate=True)
        mass_before = case.initial_state.accounted_total
        mass_after = run.final_state.accounted_total
        normalized_error = abs(mass_after - mass_before) / max(1.0, mass_before)
        actual = {
            "edges": len(case.view.edges),
            "edge_updates": run.edge_updates,
            "microsteps": run.microsteps,
            "nodes": len(case.view.nodes),
            "failed_edges": len(case.failed_edge_ids),
            "realized_average_degree": case.average_degree,
            "topology": case.topology,
        }
        correctness = {
            "edge_updates_exact": run.edge_updates == case.expected_edge_updates,
            "healthy": run.healthy,
            "mass_error_normalized": normalized_error,
            "mass_error_within_1e_9": normalized_error <= 1e-9,
            "maximum_step_mass_error_normalized": (
                run.maximum_normalized_mass_error),
            "positivity_corrections": run.positivity_corrections,
            "failed_edges_carried_no_current": all(
                case.forward_field.get(edge_id, 0.0) == 0.0
                and case.backward_field.get(edge_id, 0.0) == 0.0
                for edge_id in case.failed_edge_ids),
            "semantic_hash": case.artifact_hash,
        }
        detail["kernel_elapsed_ms"] = run.wall_ms
        detail["microseconds_per_edge_update"] = (
            run.microseconds_per_edge_update)
    elif surface == "combined":
        actual, combined_metrics, correctness = evaluate_combined_case(
            parameters, seed=seed)
        detail.update(combined_metrics)
    elif surface == "captured":
        load_started = time.perf_counter()
        captured = load_captured_revisions(
            str(parameters["events_path"]),
            (int(parameters["turn"]),),
            expected_sha256=str(parameters["events_sha256"]))[0]
        detail["captured_load_ms"] = (
            time.perf_counter() - load_started) * 1000.0
        target = int(parameters["target_atom_count"])
        replication_factor = max(
            1, int(math.ceil(
                max(0, target - len(captured.records))
                / float(len(captured.records)))))
        amplification_started = time.perf_counter()
        amplification = amplify_captured_records(
            captured.snapshot_id,
            captured.records,
            captured.scopes,
            captured.predicate_registry,
            replication_factor=replication_factor)
        detail["amplification_ms"] = (
            time.perf_counter() - amplification_started) * 1000.0
        support_ids = {
            support.support_id for record in amplification.records
            for support in record.supports}
        actual = {
            "amplified_atoms": len(amplification.records),
            "amplified_clone_atoms": amplification.amplified_record_count,
            "base_atoms": len(captured.records),
            "historical_validity_records": (
                amplification.historical_validity_record_count),
            "replication_factor": replication_factor,
            "scopes": len(amplification.scopes),
            "supports": len(support_ids),
            "target_atoms": target,
            "turn": captured.turn,
        }
        correctness = {
            "at_least_target_atoms": len(amplification.records) >= target,
            "clone_authority_quarantined": all(
                record.key.namespace.value == "diagnostic"
                and record.authority.value == "control_model"
                for record in amplification.clone_records),
            "original_subgraph_invariant": (
                amplification.original_subgraph_invariant),
            "source_hash_verified": (
                captured.source_sha256 == str(parameters["events_sha256"])),
            "validation_mode": amplification.validation_mode,
            "semantic_hash": structural_hash({
                "amplified_revision_id": amplification.revision_id,
                "captured_revision_hash": captured.artifact_hash,
                "source_sha256": captured.source_sha256,
            }),
        }
    else:
        raise ValueError("unknown scaling surface")
    wall_ms = (time.perf_counter() - started_wall) * 1000.0
    cpu_ms = (time.process_time() - started_cpu) * 1000.0
    return {
        "actual_work": actual,
        "correctness": correctness,
        "metrics": dict(detail, **{
            "cpu_ms": cpu_ms,
            "gc_count_after": list(gc.get_count()),
            "gc_count_before": list(gc_before),
            "peak_rss_bytes": _peak_rss_bytes(),
            "wall_ms": wall_ms,
        }),
        "parameters": parameters,
        "seed": seed,
        "surface": surface,
        "tier": tier,
    }


def _worker_main():
    payload = json.load(sys.stdin)
    rss_bytes = int(payload.pop("_rss_limit_bytes", DEFAULT_RSS_BYTES))
    if hasattr(resource, "RLIMIT_AS"):
        resource.setrlimit(resource.RLIMIT_AS, (rss_bytes, rss_bytes))
    result = _execute(payload)
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _trial_spec(payload, source_identity, phase="discovery", arm="kernel",
                telemetry_mode="aggregate", wall_seconds=DEFAULT_WALL_SECONDS,
                rss_bytes=DEFAULT_RSS_BYTES):
    payload = dict(payload)
    parameters = dict(payload["parameters"])
    cell = ScaleCell(
        surface=payload["surface"],
        tier=payload["tier"],
        seed=int(payload["seed"]),
        parameters=tuple(parameters.items()),
        budgets=(("rss_bytes", int(rss_bytes)),
                 ("wall_seconds", int(wall_seconds))),
    )
    return TrialSpec(
        experiment_id="freeciv-scalability-v1",
        phase=phase,
        cell=cell,
        arm=arm,
        telemetry_mode=telemetry_mode,
        source_identity=source_identity,
    )


def run_isolated(payload, source_identity, phase="discovery", arm="kernel",
                 telemetry_mode="aggregate", wall_seconds=DEFAULT_WALL_SECONDS,
                 rss_bytes=DEFAULT_RSS_BYTES):
    payload = dict(payload)
    trial = _trial_spec(
        payload, source_identity, phase=phase, arm=arm,
        telemetry_mode=telemetry_mode, wall_seconds=wall_seconds,
        rss_bytes=rss_bytes)
    payload["_rss_limit_bytes"] = int(rss_bytes)
    command = (sys.executable, "-m", "benchmarks.freeciv.scaling.runner", "worker")
    repo_root = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", ".."))
    worker_environment = os.environ.copy()
    import_roots = (repo_root, os.path.join(repo_root, "src"))
    inherited_pythonpath = worker_environment.get("PYTHONPATH")
    worker_environment["PYTHONPATH"] = os.pathsep.join(
        import_roots + ((inherited_pythonpath,) if inherited_pythonpath else ()))
    try:
        process = subprocess.run(
            command,
            cwd=repo_root,
            env=worker_environment,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=wall_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return TrialResult(
            trial, "stopped", (), (),
            (("stop_rule", "wall-time"),),
            ("wall limit exceeded",))
    if process.returncode != 0:
        disposition = (
            "resource-or-signal" if process.returncode < 0 else "worker-error")
        return TrialResult(
            trial, "failed", (),
            (("returncode", process.returncode),),
            (("disposition", disposition),),
            (process.stderr.strip() or disposition,))
    result = json.loads(process.stdout)
    return TrialResult(
        trial=trial,
        status="completed",
        actual_work=tuple(result["actual_work"].items()),
        metrics=tuple(result["metrics"].items()),
        correctness=tuple(result["correctness"].items()),
    )


def write_json(path, material):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(material, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)


def payload_identity(payload):
    """Hash the complete requested workload independently of trial phase."""
    material = {
        "parameters": dict(payload["parameters"]),
        "seed": int(payload["seed"]),
        "surface": str(payload["surface"]),
        "tier": str(payload["tier"]),
    }
    # ScaleCell supplies the same strict JSON validation used by a trial.
    cell = ScaleCell(
        material["surface"], material["tier"], material["seed"],
        tuple(material["parameters"].items()),
        (("rss_bytes", DEFAULT_RSS_BYTES),
         ("wall_seconds", DEFAULT_WALL_SECONDS)),
    )
    return cell.cell_id


def _resource_termination_key(material):
    """Return the seed-independent cell key for a bounded resource stop."""
    correctness = material.get("correctness", {})
    bounded = (
        material.get("status") == "stopped"
        and correctness.get("stop_rule") == "wall-time")
    bounded = bounded or (
        material.get("status") == "failed"
        and correctness.get("disposition") == "resource-or-signal")
    if not bounded:
        return None
    cell = material["trial"]["cell"]
    parameters = dict(cell["parameters"])
    # These fields describe replicate scheduling, not the workload cell.
    parameters.pop("timing_block", None)
    parameters.pop("timing_sample", None)
    return structural_hash({
        "parameters": parameters,
        "surface": cell["surface"],
        "tier": cell["tier"],
    })


def _tier_key_from_result(material):
    cell = material["trial"]["cell"]
    return (cell["surface"], cell["tier"])


def _tier_key_from_payload(payload):
    return (str(payload["surface"]), str(payload["tier"]))


def _tier_stop_result(trial, trigger_trial_ids):
    return TrialResult(
        trial=trial,
        status="stopped",
        actual_work=(),
        metrics=(),
        correctness=(
            ("stop_rule", "repeated-resource-termination"),
            ("trigger_trial_ids", list(sorted(trigger_trial_ids))),
            ("workload_not_entered", True),
        ),
        errors=(
            "tier stopped after two repeated resource terminations",
        ),
    )


def freeze_campaign(out_root, payloads):
    """Freeze exact held-out inputs and the executable source identity."""
    preregistration_path = os.path.join(out_root, "preregistration.json")
    if not os.path.isfile(preregistration_path):
        raise ValueError("baseline/preregistration is missing")
    with open(preregistration_path, "r", encoding="utf-8") as handle:
        preregistration = json.load(handle)
    payload_rows = [dict(
        parameters=dict(row["parameters"]),
        seed=int(row["seed"]),
        surface=str(row["surface"]),
        tier=str(row["tier"]),
    ) for row in payloads]
    if not payload_rows:
        raise ValueError("frozen campaign requires at least one payload")
    by_id = dict((payload_identity(row), row) for row in payload_rows)
    if len(by_id) != len(payload_rows):
        raise ValueError("frozen payload selection contains duplicate cells")
    environment = environment_identity()
    source_identity = "{}:{}:{}".format(
        environment["git_commit"], environment["code_digest"],
        environment["measurement_contract_hash"])
    material = {
        "artifact_type": "freeciv-scalability-frozen-preregistration",
        "base_preregistration_hash": preregistration[
            "preregistration_hash"],
        "environment_hash": environment["environment_hash"],
        "frozen": True,
        "payload_count": len(by_id),
        "payloads": [dict({"payload_id": key}, **by_id[key])
                     for key in sorted(by_id)],
        "schema_version": "1.0",
        "source_identity": source_identity,
    }
    material["freeze_hash"] = structural_hash(material)
    write_json(
        os.path.join(out_root, "frozen-preregistration.json"), material)
    return material


def validate_frozen_campaign(out_root, payloads, source_identity=None):
    """Reject unfrozen, changed-source, or unregistered held-out work."""
    path = os.path.join(out_root, "frozen-preregistration.json")
    if not os.path.isfile(path):
        raise ValueError("held-out execution requires a frozen preregistration")
    with open(path, "r", encoding="utf-8") as handle:
        frozen = json.load(handle)
    material = dict(frozen)
    claimed_hash = material.pop("freeze_hash", None)
    if claimed_hash != structural_hash(material):
        raise ValueError("frozen preregistration hash mismatch")
    if frozen.get("artifact_type") != (
            "freeciv-scalability-frozen-preregistration"):
        raise ValueError("wrong frozen preregistration artifact type")
    if source_identity is None:
        environment = environment_identity()
        source_identity = "{}:{}:{}".format(
            environment["git_commit"], environment["code_digest"],
            environment["measurement_contract_hash"])
    if frozen.get("source_identity") != source_identity:
        raise ValueError("held-out source identity differs from frozen source")
    allowed = {row["payload_id"] for row in frozen.get("payloads", ())}
    requested = {payload_identity(row) for row in payloads}
    missing = sorted(requested.difference(allowed))
    if missing:
        raise ValueError(
            "held-out payload was not preregistered: {}".format(missing[0]))
    return frozen


def initialize_campaign(out_root):
    environment = environment_identity()
    baseline = verify_frozen_baseline()
    manifest = load_frozen_baseline()
    write_json(os.path.join(out_root, "environment.json"), environment)
    write_json(os.path.join(out_root, "baseline", "verification.json"),
               baseline.to_dict())
    preregistration = {
        "artifact_type": "freeciv-scalability-preregistration",
        "baseline_commit": manifest["baseline_commit"],
        "claim_boundary": manifest["claim_boundary"],
        "environment_hash": environment["environment_hash"],
        "generator_version": GENERATOR_VERSION,
        "primary_tiers": {
            "atomspace": ["A0", "A1", "A2", "A3", "A4"],
            "bridge": ["B0", "B1", "B2", "B3"],
            "fluid": ["F0", "F1", "F2", "F3"],
            "proof": ["P0", "P1", "P2", "P3"],
            "combined": sorted(COMBINED_TIERS),
            "captured": ["CA2", "CA4"],
        },
        "schema_version": "1.0",
        "stretch_tiers": ["A5", "P4", "B5", "F4"],
        "stop_rules": {
            "edge_updates": 50000000,
            "live_atoms": 250000,
            "peak_rss_bytes": DEFAULT_RSS_BYTES,
            "relevant_proof_nodes": 250000,
            "wall_seconds": DEFAULT_WALL_SECONDS,
        },
    }
    preregistration["preregistration_hash"] = structural_hash(preregistration)
    write_json(os.path.join(out_root, "preregistration.json"), preregistration)
    return {
        "baseline": baseline.to_dict(),
        "environment": environment,
        "preregistration": preregistration,
    }


def run_cells(out_root, payloads, phase="discovery", workers=1):
    payloads = tuple(payloads)
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError("workers must be a positive integer")
    if phase == "heldout" and workers != 1:
        raise ValueError("held-out timing execution requires exactly one worker")
    environment = environment_identity()
    source_identity = "{}:{}:{}".format(
        environment["git_commit"], environment["code_digest"],
        environment["measurement_contract_hash"])
    if phase == "heldout":
        validate_frozen_campaign(
            out_root, payloads, source_identity=source_identity)
        payloads = tuple(sorted(payloads, key=lambda payload: (
            int(payload.get("parameters", {}).get("timing_block", 3)),
            structural_hash({
                "payload_id": payload_identity(payload),
                "randomization": "heldout-block-order-v1",
            }),
        )))
    path = os.path.join(out_root, phase, "trials.json")
    existing = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            existing = json.load(handle).get("results", [])
    by_id = dict((row["trial_id"], row) for row in existing)
    telemetry_mode = (
        "semantic-screening" if phase == "discovery" and workers > 1
        else "aggregate")
    planned_rows = []
    for payload in payloads:
        arm = str(payload.get("parameters", {}).get("arm", "kernel"))
        planned = _trial_spec(
            payload, source_identity, phase=phase, arm=arm,
            telemetry_mode=telemetry_mode)
        planned_rows.append((payload, arm, planned.trial_id))
    trial_ids = [row[2] for row in planned_rows]
    if len(trial_ids) != len(set(trial_ids)):
        raise ValueError("selected campaign contains duplicate trial identities")

    def checkpoint():
        write_json(path, {
            "artifact_type": "freeciv-scalability-trials",
            "execution_order_hash": structural_hash([
                payload_identity(row) for row in payloads]),
            "randomization": (
                "heldout-block-order-v1" if phase == "heldout" else
                "discovery-concurrent-screening-v1" if workers > 1 else
                "discovery-declared-order"),
            "results": [by_id[key] for key in sorted(by_id)],
            "schema_version": "1.0",
            "worker_count": workers,
        })

    resource_hits = defaultdict(list)
    stopped_tiers = {}
    for material in by_id.values():
        trial = material.get("trial", {})
        if (trial.get("phase") != phase
                or trial.get("source_identity") != source_identity
                or trial.get("telemetry_mode") != telemetry_mode):
            continue
        resource_key = _resource_termination_key(material)
        if resource_key is None:
            continue
        resource_hits[resource_key].append(material["trial_id"])
        if len(resource_hits[resource_key]) >= 2:
            stopped_tiers[_tier_key_from_result(material)] = tuple(
                resource_hits[resource_key][:2])

    def record(material):
        by_id[material["trial_id"]] = material
        resource_key = _resource_termination_key(material)
        if resource_key is not None:
            resource_hits[resource_key].append(material["trial_id"])
            if len(resource_hits[resource_key]) >= 2:
                stopped_tiers[_tier_key_from_result(material)] = tuple(
                    resource_hits[resource_key][:2])
        checkpoint()

    pending = [row for row in planned_rows if row[2] not in by_id]

    def next_runnable():
        while pending:
            payload, arm, trial_id = pending.pop(0)
            triggers = stopped_tiers.get(_tier_key_from_payload(payload))
            if triggers is not None:
                planned = _trial_spec(
                    payload, source_identity, phase=phase, arm=arm,
                    telemetry_mode=telemetry_mode)
                record(_tier_stop_result(planned, triggers).to_dict())
                continue
            return payload, arm, trial_id
        return None

    if workers == 1:
        while True:
            row = next_runnable()
            if row is None:
                break
            payload, arm, _trial_id = row
            material = run_isolated(
                payload, source_identity, phase=phase, arm=arm,
                telemetry_mode=telemetry_mode).to_dict()
            record(material)
    elif pending:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            while pending or futures:
                while len(futures) < workers:
                    row = next_runnable()
                    if row is None:
                        break
                    payload, arm, trial_id = row
                    future = pool.submit(
                        run_isolated, payload, source_identity,
                        phase=phase, arm=arm,
                        telemetry_mode=telemetry_mode)
                    futures[future] = trial_id
                if not futures:
                    break
                completed, _remaining = wait(
                    tuple(futures), return_when=FIRST_COMPLETED)
                for future in sorted(
                        completed, key=lambda item: futures[item]):
                    expected_trial_id = futures.pop(future)
                    material = future.result().to_dict()
                    if material["trial_id"] != expected_trial_id:
                        raise RuntimeError(
                            "worker returned an unexpected trial identity")
                    record(material)
    else:
        checkpoint()
    return [by_id[trial_id] for trial_id in trial_ids]


def smoke_payloads(seed=1729):
    return (
        {"surface": "atomspace", "tier": "smoke", "seed": seed,
         "parameters": {"atom_count": 100, "scope_count": 5}},
        {"surface": "proof", "tier": "smoke", "seed": seed,
         "parameters": {"depth": 8, "shape": "chain"}},
        {"surface": "bridge", "tier": "smoke", "seed": seed,
         "parameters": {"node_count": 40, "edge_count": 80,
                        "candidate_count": 8, "goal_count": 2}},
        {"surface": "fluid", "tier": "smoke", "seed": seed,
         "parameters": {"length": 32, "microsteps": 8}},
    )


def _main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "worker":
        return _worker_main()
    raise SystemExit("use scripts/freeciv/run_scalability_campaign.py")


if __name__ == "__main__":
    raise SystemExit(_main())
