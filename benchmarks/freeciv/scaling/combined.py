"""Combined-load evaluation with all large working sets simultaneously live."""

import time

from freeciv_agent.events.schema import structural_hash

from .atomspace_generator import apply_atomspace_churn, build_atomspace_case
from .bridge_generator import (
    build_bridge_case,
    evaluate_bridge_case,
    evaluate_protected_readout,
)
from .fluid_generator import build_fluid_case, run_fluid_case
from .proof_generator import build_proof_dag_case, evaluate_proof_case


def evaluate_combined_case(parameters, seed=1729):
    """Run the frozen stage order while retaining every prior stage result."""
    atom_parameters = dict(parameters["atomspace"])
    proof_parameters = dict(parameters["proof"])
    bridge_parameters = dict(parameters["bridge"])
    fluid_parameters = (
        None if parameters.get("fluid") is None
        else dict(parameters["fluid"]))
    stage_ms = {}
    started = time.perf_counter()

    stage_started = time.perf_counter()
    atom_case = build_atomspace_case(
        int(atom_parameters["atom_count"]),
        int(atom_parameters["scope_count"]),
        int(atom_parameters.get("support_multiplicity", 1)),
        atom_parameters.get("topology", "local"),
        seed=seed)
    atom_churn = apply_atomspace_churn(
        atom_case, float(atom_parameters.get("churn_fraction", 0.01)))
    atom_hash_before = structural_hash([
        row.to_dict() for row in atom_case.records])
    stage_ms["atomspace_stage_ms"] = (
        time.perf_counter() - stage_started) * 1000.0

    stage_started = time.perf_counter()
    proof_case = build_proof_dag_case(
        int(proof_parameters["depth"]),
        int(proof_parameters["relevant_nodes"]),
        proof_parameters.get("shape", "shared_dag"),
        int(proof_parameters.get("distractor_count", 0)))
    proof = evaluate_proof_case(proof_case)
    stage_ms["proof_stage_ms"] = (
        time.perf_counter() - stage_started) * 1000.0

    stage_started = time.perf_counter()
    bridge_case = build_bridge_case(
        int(bridge_parameters["node_count"]),
        int(bridge_parameters["edge_count"]),
        int(bridge_parameters["candidate_count"]),
        int(bridge_parameters["goal_count"]),
        seed=seed,
        topology=bridge_parameters.get(
            "topology", "disconnected_distractors"))
    bridge = evaluate_bridge_case(bridge_case)
    readout = evaluate_protected_readout(bridge_case, bridge)
    stage_ms["bridge_stage_ms"] = (
        time.perf_counter() - stage_started) * 1000.0

    fluid_case = None
    fluid = None
    if fluid_parameters is not None:
        stage_started = time.perf_counter()
        fluid_case = build_fluid_case(
            int(fluid_parameters["length"]),
            int(fluid_parameters["microsteps"]),
            float(fluid_parameters.get("velocity", 0.25)))
        fluid = run_fluid_case(fluid_case, aggregate=True)
        stage_ms["fluid_stage_ms"] = (
            time.perf_counter() - stage_started) * 1000.0

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    # Read hashes after every control stage so accidental mutation is visible.
    atom_hash_after = structural_hash([
        row.to_dict() for row in atom_case.records])
    fluid_healthy = fluid is None or fluid.healthy
    fluid_mass_healthy = (
        fluid is None or fluid.maximum_normalized_mass_error <= 1e-9)
    actual = {
        "bridge_candidates": bridge_case.candidate_count,
        "bridge_edges": bridge_case.edge_count,
        "bridge_estimates": bridge.estimate_count,
        "bridge_goals": len(bridge_case.goal_ids),
        "bridge_nodes": bridge_case.node_count,
        "dependency_edges": sum(
            len(support.dependencies) for record in atom_case.records
            for support in record.supports),
        "fluid_edge_updates": 0 if fluid is None else fluid.edge_updates,
        "fluid_edges": 0 if fluid_case is None else len(fluid_case.view.edges),
        "live_revision_atoms": atom_case.atom_count,
        "proof_records": proof.proof_record_count,
        "relevant_rules": proof_case.expected_rule_count,
        "scopes": atom_case.scope_count,
        "supports": atom_case.support_count,
    }
    actual.update(dict(
        ("proof_" + key, value) for key, value in proof.work_counters))
    correctness = {
        "bridge_candidate_safe": (
            readout.scalar_winner_recalled
            and readout.scalar_order_preserved
            and readout.expected_bridge_recalled),
        "cold_incremental_equivalent": atom_churn.equivalent,
        "fluid_healthy": fluid_healthy,
        "fluid_mass_within_1e_9": fluid_mass_healthy,
        "proof_matches_reference": proof.matches_reference,
        "semantic_hash": structural_hash({
            "atomspace": atom_case.artifact_hash,
            "bridge": bridge_case.artifact_hash,
            "fluid": None if fluid_case is None else fluid_case.artifact_hash,
            "proof": proof_case.artifact_hash,
            "readout": readout.artifact_hash,
        }),
        "truth_hash_unchanged": atom_hash_after == atom_hash_before,
    }
    metrics = dict(stage_ms)
    metrics["combined_elapsed_ms"] = elapsed_ms
    metrics["measured_stage_sum_ms"] = sum(stage_ms.values())
    return actual, metrics, correctness
