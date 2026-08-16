"""G0/G1 contracts for larger AtomSpace, proof, bridge, and fluid trials."""

import os
import random
import sys
import hashlib
import json

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
for candidate in (REPO, SRC):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from benchmarks.freeciv.scaling import (  # noqa: E402
    ScaleCell,
    TrialSpec,
    apply_atomspace_churn,
    apply_bridge_edge_failure,
    apply_fluid_edge_failures,
    amplify_captured_records,
    build_atomspace_case,
    build_bridge_case,
    build_fluid_case,
    build_fluid_graph_case,
    build_proof_case,
    build_proof_dag_case,
    evaluate_bridge_case,
    evaluate_corrected_probe_readout,
    evaluate_path_persistence,
    evaluate_protected_readout,
    evaluate_scalar_readout,
    evaluate_source_sink_flow_readout,
    evaluate_proof_case,
    run_fluid_case,
    run_retention_cycles,
    load_captured_revisions,
    verify_frozen_baseline,
)
from benchmarks.freeciv.scaling.combined import evaluate_combined_case  # noqa: E402
from benchmarks.freeciv.scaling.design import design_variants  # noqa: E402
from benchmarks.freeciv.scaling.runner import run_isolated  # noqa: E402
from benchmarks.freeciv.scaling.audit import audit_results  # noqa: E402


def test_g0_frozen_evidence_and_defaults_match_while_source_drift_is_reported():
    result = verify_frozen_baseline()
    assert result.valid, result.errors
    assert all(dict(result.checks).values())
    # Intentional benchmark hardening is versioned separately and reported as
    # source drift; frozen evidence and production defaults must still match.
    assert all(" current " in row for row in result.source_drift)


def test_trial_identity_is_canonical_and_seed_sensitive():
    left = ScaleCell("proof", "P0", 1, (("depth", 12),), (("wall", 120),))
    right = ScaleCell("proof", "P0", 1, (("depth", 12),), (("wall", 120),))
    changed = ScaleCell("proof", "P0", 2, (("depth", 12),), (("wall", 120),))
    assert left.cell_id == right.cell_id
    assert left.cell_id != changed.cell_id
    trial = TrialSpec("experiment", "discovery", left, "kernel", "aggregate", "source")
    assert trial.trial_id.startswith("scale-trial-")


def test_atomspace_exact_counts_for_100_deterministic_small_cases():
    rng = random.Random(104743)
    for index in range(100):
        atoms = rng.randint(1, 40)
        scopes = rng.randint(1, 8)
        supports = rng.choice((1, 2, 4))
        topology = rng.choice((
            "local", "chain", "hub", "balanced_tree", "shared_dag",
            "distractor_shards", "mixed"))
        case = build_atomspace_case(
            atoms, scopes, supports, topology, seed=index)
        assert case.atom_count == atoms
        assert case.scope_count == scopes
        assert case.support_count == atoms * supports
        assert len(case.dependency_index.atom_by_id) == atoms
        assert all(row.key.namespace.value == "diagnostic" for row in case.records)


def test_atomspace_hash_is_insertion_order_invariant():
    cases = [build_atomspace_case(
        40, 7, 2, "mixed", seed=19, insertion_order=order)
        for order in ("canonical", "reverse", "shuffled")]
    assert len({row.revision_id for row in cases}) == 1
    assert len({row.artifact_hash for row in cases}) == 1


def test_chain_invalidation_transitively_fails_closed():
    case = build_atomspace_case(20, 1, 1, "chain")
    result = case.dependency_index.invalidate((case.source_dependency_keys[0],))
    assert result.unsupported_atom_ids
    assert set(result.unsupported_atom_ids).issubset(case.dependency_index.atom_by_id)


@pytest.mark.parametrize("topology", (
    "local", "chain", "hub", "balanced_tree", "shared_dag",
    "distractor_shards", "mixed"))
def test_cold_and_incremental_churn_are_semantically_identical(topology):
    case = build_atomspace_case(80, 8, 2, topology, seed=44)
    result = apply_atomspace_churn(case, 0.05)
    assert result.changed_dependency_count == 4
    assert result.equivalent
    assert result.cold_revision_id == result.incremental_revision_id
    assert result.cold_hash == result.incremental_hash


@pytest.mark.parametrize("shape,status", (("chain", "BLOCKED"), ("cycle", "UNREACHABLE")))
def test_proof_reference_and_engine_agree(shape, status):
    case = build_proof_case(12, shape)
    result = evaluate_proof_case(case)
    assert result.status == status
    assert result.matches_reference
    assert result.proof_record_count == 13
    counters = dict(result.work_counters)
    assert counters["rules_visited"] == 13
    assert counters["maximum_depth_attempted"] == (
        13 if shape == "cycle" else 12)


def test_proof_depth_exhaustion_is_explicit_unknown():
    result = evaluate_proof_case(build_proof_case(12), maximum_depth=3)
    assert result.status == "UNKNOWN"
    assert result.truncated
    assert not result.matches_reference
    assert dict(result.work_counters)["maximum_depth_attempted"] == 4


@pytest.mark.parametrize("shape,status", (
    ("and_tree", "BLOCKED"),
    ("shared_dag", "BLOCKED"),
    ("diamond_50", "BLOCKED"),
    ("diamond_90", "BLOCKED"),
    ("or_one_success", "BLOCKED"),
    ("or_several_success", "BLOCKED"),
    ("or_unreachable", "UNREACHABLE"),
    ("cycle_alternate", "BLOCKED"),
    ("cycle_only", "UNREACHABLE"),
    ("grounded_blocker", "UNREACHABLE"),
    ("binding_heavy", "BLOCKED"),
))
def test_proof_dag_families_match_independent_reference(shape, status):
    case = build_proof_dag_case(
        depth=8, relevant_nodes=80, shape=shape, distractor_count=100)
    result = evaluate_proof_case(
        case, maximum_bindings=500, maximum_rule_fires=500)
    assert case.expected_status == status
    assert result.status == status
    assert result.matches_reference
    # Unreachable indexed distractors never enter the proof artifact.
    assert result.proof_record_count == case.expected_rule_count
    counters = dict(result.work_counters)
    assert counters["rules_visited"] == case.expected_rule_count
    if shape == "shared_dag":
        assert counters["memo_hits"] > 0
    if shape == "cycle_alternate":
        assert counters["cycle_rejections"] == 1
    if shape == "grounded_blocker":
        assert counters["grounded_evaluations"] == 1
    if shape == "binding_heavy":
        assert counters["bindings"] > 80


def test_cycle_only_dag_terminates_as_reference_unreachable():
    case = build_proof_dag_case(
        depth=8, relevant_nodes=80, shape="cycle_only",
        distractor_count=100)
    result = evaluate_proof_case(case)
    assert case.expected_status == "UNREACHABLE"
    assert result.status == "UNREACHABLE"
    assert result.matches_reference
    assert dict(result.work_counters)["cycle_rejections"] == 1


def test_primary_design_is_fixed_bounded_and_not_atomspace_cartesian():
    assert len(design_variants(
        "atomspace", "A2", design="primary")) == 13
    assert len(design_variants(
        "atomspace", "A0", design="primary", seed_index=0)) == 2
    assert len(design_variants(
        "atomspace", "A0", design="primary", seed_index=1)) == 1
    assert len(design_variants("proof", "P0", design="primary")) == 12
    assert len(design_variants("proof", "P2", design="primary")) == 15
    assert len(design_variants("bridge", "B2", design="primary")) == 35
    assert len(design_variants("bridge", "B4", design="primary")) == 21
    assert len(design_variants("fluid", "F2", design="primary")) == 8


def test_bridge_counts_oracle_and_replay_are_exact():
    case = build_bridge_case(80, 240, 12, 4, seed=8)
    first = evaluate_bridge_case(case)
    second = evaluate_bridge_case(case)
    assert len(case.view.nodes) == 80
    assert len(case.view.edges) == 240
    assert len(case.view.candidate_groundings) == 12
    assert first.bridge_separated
    assert first.deterministic_hash == second.deterministic_hash


def test_protected_bridge_union_never_loses_or_reorders_scalar_candidates():
    case = build_bridge_case(80, 240, 12, 4, seed=18)
    bridge = evaluate_bridge_case(case)
    first = evaluate_protected_readout(case, bridge)
    second = evaluate_protected_readout(case, bridge)
    assert first.scalar_winner_recalled
    assert first.expected_bridge_recalled
    assert first.scalar_order_preserved
    assert not first.fallback_required
    assert first.artifact_hash == second.artifact_hash


def test_scalar_bridge_arm_runs_no_bridge_compute_and_keeps_exact_prefix():
    case = build_bridge_case(80, 240, 12, 4, seed=17)
    result = evaluate_scalar_readout(case, scalar_top_k=3)
    assert result.scalar_winner_recalled
    assert result.scalar_order_preserved
    assert not result.bridge_added_operation_ids
    assert not result.expected_bridge_recalled
    isolated = run_isolated({
        "surface": "bridge", "tier": "scalar-test", "seed": 17,
        "parameters": {
            "arm": "scalar_pf_v2", "candidate_count": 12,
            "edge_count": 240, "goal_count": 4, "node_count": 80,
            "topology": "disconnected_distractors",
        },
    }, "test-source", arm="scalar_pf_v2", wall_seconds=30).to_dict()
    assert isolated["status"] == "completed"
    assert isolated["actual_work"]["estimates"] == 0
    assert isolated["correctness"]["bridge_separated"] is None
    assert audit_results([isolated], resamples=10)["valid"]


def test_source_sink_flow_arm_is_conservative_and_decision_safe():
    case = build_bridge_case(80, 240, 12, 4, seed=16)
    first = evaluate_source_sink_flow_readout(case)
    second = evaluate_source_sink_flow_readout(case)
    protected = first.protected_readout
    assert first.healthy
    assert first.edge_updates == 240
    assert first.maximum_normalized_mass_error <= 1e-9
    assert first.positivity_corrections == 0
    assert not first.fallback_to_messages
    assert protected.scalar_winner_recalled
    assert protected.expected_bridge_recalled
    assert protected.scalar_order_preserved
    assert first.artifact_hash == second.artifact_hash


def test_bridge_budget_exhaustion_returns_explicit_scalar_fallback():
    case = build_bridge_case(80, 240, 12, 4, seed=19)
    result = evaluate_protected_readout(
        case, maximum_nodes=40, maximum_edges=100)
    assert result.fallback_required
    assert result.fallback_reason == "materialization-budget-exhausted"
    assert result.scalar_winner_recalled
    assert result.scalar_order_preserved
    assert not result.bridge_added_operation_ids


@pytest.mark.parametrize("topology", (
    "sparse_dag", "shared_dag", "cyclic",
    "disconnected_distractors", "asymmetric_legality", "bottleneck",
))
def test_bridge_topology_families_keep_exact_counts_and_safe_meet(topology):
    case = build_bridge_case(80, 240, 12, 4, seed=31, topology=topology)
    result = evaluate_bridge_case(case)
    assert len(case.view.nodes) == 80
    assert len(case.view.edges) == 240
    assert result.bridge_separated


def test_dynamic_bridge_failure_moves_generation_and_falls_back():
    original = build_bridge_case(80, 240, 12, 4, seed=32)
    failed = apply_bridge_edge_failure(original)
    result = evaluate_protected_readout(failed)
    assert failed.view.topology_generation == original.view.topology_generation + 1
    assert failed.edge_count == original.edge_count - 1
    assert result.fallback_required
    assert result.fallback_reason == "topology-edge-failure"
    assert result.scalar_winner_recalled


@pytest.mark.parametrize("arm", (
    "protected_message", "corrected_probe", "path_persistence",
    "source_sink_flow"))
def test_every_bridge_arm_fails_closed_after_dynamic_edge_failure(arm):
    result = run_isolated({
        "surface": "bridge", "tier": "dynamic-failure-test", "seed": 32,
        "parameters": {
            "arm": arm, "candidate_count": 12, "edge_count": 240,
            "goal_count": 4, "node_count": 80,
            "topology": "dynamic_failure",
        },
    }, "test-source", arm=arm, wall_seconds=30).to_dict()
    assert result["status"] == "completed"
    assert result["correctness"]["fallback_required"]
    assert result["correctness"]["fallback_reason"] == (
        "topology-edge-failure")
    assert result["correctness"]["scalar_winner_recalled"]
    assert result["correctness"]["scalar_order_preserved"]
    assert audit_results([result], resamples=10)["valid"]


def test_corrected_probe_union_is_safe_or_falls_back_to_messages():
    case = build_bridge_case(80, 240, 12, 4, seed=20)
    first = evaluate_corrected_probe_readout(
        case, path_count=32, max_steps=8, seed=20)
    second = evaluate_corrected_probe_readout(
        case, path_count=32, max_steps=8, seed=20)
    protected = first.protected_readout
    assert protected.scalar_winner_recalled
    assert protected.expected_bridge_recalled
    assert protected.scalar_order_preserved
    assert first.probe_healthy != first.fallback_to_messages
    assert first.minimum_effective_sample_fraction > 0.0
    assert first.artifact_hash == second.artifact_hash


def test_path_persistence_is_bounded_deterministic_and_decision_safe():
    case = build_bridge_case(80, 240, 12, 4, seed=21)
    first = evaluate_path_persistence(case, iterations=6, dwell_threshold=3)
    second = evaluate_path_persistence(case, iterations=6, dwell_threshold=3)
    protected = first.protected_readout
    assert protected.scalar_winner_recalled
    assert protected.expected_bridge_recalled
    assert protected.scalar_order_preserved
    assert first.maximum_state_entries == 2 * case.candidate_count
    assert first.persisted_operation_ids
    assert first.artifact_hash == second.artifact_hash


def test_fluid_actual_work_mass_and_legality_are_exact():
    case = build_fluid_case(64, 16)
    result = run_fluid_case(case)
    assert result.edge_updates == case.expected_edge_updates
    assert result.final_state.accounted_total == pytest.approx(
        case.initial_state.accounted_total)
    assert all(row.healthy for row in result.steps)
    assert not sum(row.positivity_corrections for row in result.steps)


@pytest.mark.parametrize("degree", (2, 4, 8))
def test_sparse_dag_fluid_hits_exact_work_at_each_degree(degree):
    case = build_fluid_graph_case(
        edge_update_budget=10000, microsteps=50,
        average_degree=degree)
    result = run_fluid_case(case, aggregate=True)
    assert case.topology == "sparse_dag"
    assert result.edge_updates == 10000
    assert len(case.view.edges) == 200
    assert case.average_degree == pytest.approx(
        len(case.view.edges) / len(case.view.nodes))
    assert result.healthy
    assert result.maximum_normalized_mass_error <= 1e-9
    assert result.positivity_corrections == 0


def test_dynamic_edge_failures_use_zero_current_and_exact_repaired_work():
    original = build_fluid_case(64, 16)
    repaired = apply_fluid_edge_failures(original, 0.10, seed=94)
    result = run_fluid_case(repaired, aggregate=True)
    assert len(repaired.failed_edge_ids) == round(len(original.view.edges) * 0.10)
    assert result.edge_updates == repaired.expected_edge_updates
    assert result.healthy
    assert result.maximum_normalized_mass_error <= 1e-9
    assert all(
        repaired.forward_field.get(edge_id, 0.0) == 0.0
        and repaired.backward_field.get(edge_id, 0.0) == 0.0
        for edge_id in repaired.failed_edge_ids)


def test_malformed_scale_inputs_fail_validation():
    with pytest.raises(ValueError):
        build_atomspace_case(0)
    with pytest.raises(ValueError):
        build_proof_case(0)
    with pytest.raises(ValueError):
        build_bridge_case(4, 100, 1, 1)
    with pytest.raises(ValueError):
        build_fluid_case(1, 1)


def test_captured_amplifier_preserves_original_and_quarantines_clones():
    original = build_atomspace_case(24, 4, 2, "mixed", seed=81)
    from benchmarks.freeciv.scaling.atomspace_generator import benchmark_registry
    amplified = amplify_captured_records(
        original.snapshot_id, original.records, original.scopes,
        benchmark_registry(), replication_factor=3)

    assert amplified.original_subgraph_invariant
    assert len(amplified.records) == 24 * 4
    assert amplified.amplified_record_count == 72
    assert all(
        row.key.namespace.value == "diagnostic"
        and row.authority.value == "control_model"
        and all(term.entity_id.startswith("benchmark-amplified-")
                for term in row.key.arguments if hasattr(term, "entity_id"))
        for row in amplified.clone_records)


def test_captured_amplifier_preserves_retained_historical_validity():
    original = build_atomspace_case(24, 4, 1, "local", seed=83)
    record = original.records[0]
    from freeciv_agent.state.atomspace.model import ValidityInterval, AtomRecord
    historical = AtomRecord.create(
        record.key, record.authority, record.truth,
        ValidityInterval(
            snapshot_id="historical-snapshot", valid_from_turn=1,
            valid_through_turn=1, source_seq=1),
        record.supports, record.provenance_ids,
        record.lifecycle, record.tags)
    records = (historical,) + original.records[1:]
    from benchmarks.freeciv.scaling.atomspace_generator import benchmark_registry

    amplified = amplify_captured_records(
        original.snapshot_id, records, original.scopes,
        benchmark_registry(), replication_factor=2)

    assert amplified.original_subgraph_invariant
    assert amplified.validation_mode == "retained-historical-dependency-index"
    assert amplified.historical_validity_record_count == 3
    assert amplified.dependency_index.atom_by_id[
        historical.atom_id].validity.snapshot_id == "historical-snapshot"


def test_full_telemetry_loader_reconstructs_exact_typed_revision(tmp_path):
    original = build_atomspace_case(24, 4, 2, "mixed", seed=82)
    events = []

    def append(event_type, details):
        events.append({
            "game_id": "captured-game",
            "turn": 7,
            "type": event_type,
            "payload": {
                "details": details,
                "revision_id": original.revision_id,
                "snapshot_id": original.snapshot_id,
            },
        })

    append("atomspace_revision_started", {})
    for scope in original.scopes:
        append("scope_materialized", {"scope": scope.to_dict()})
    for record in original.records:
        for support in record.supports:
            append("atom_support_added", {"support": support.to_dict()})
        summary = record.to_dict()
        supports = summary.pop("supports")
        summary["support_ids"] = [row["support_id"] for row in supports]
        summary["dependency_count"] = sum(
            len(row["dependencies"]) for row in supports)
        append("atom_rederived", {"record": summary})
    append("atomspace_revision_committed", {
        "atom_count": original.atom_count,
        "scope_count": original.scope_count,
        "support_count": original.support_count,
        "projection_summary": {"fixture": True},
    })
    path = tmp_path / "events.jsonl"
    content = "".join(json.dumps(row, sort_keys=True) + "\n" for row in events)
    path.write_text(content)
    source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    captured = load_captured_revisions(
        str(path), (7,), expected_sha256=source_hash)[0]

    assert captured.source_sha256 == source_hash
    assert captured.revision_id == original.revision_id
    assert captured.projection_summary == {"fixture": True}
    assert [row.to_dict() for row in captured.records] == [
        row.to_dict() for row in original.records]
    assert [row.to_dict() for row in captured.scopes] == [
        row.to_dict() for row in original.scopes]
    assert captured.predicate_registry.predicates


def test_revision_retention_and_scope_counts_plateau():
    result = run_retention_cycles(
        atom_count=20, scope_count=4, cycles=12,
        retention=4, seed=93)
    assert result.maximum_retained_revisions == 4
    assert result.maximum_retained_scopes == 16
    assert not result.revision_leak
    assert not result.scope_leak
    assert result.retained_revision_counts[-1] == 4


def test_combined_case_retains_semantics_with_all_stages_live():
    actual, metrics, correctness = evaluate_combined_case({
        "atomspace": {
            "atom_count": 100,
            "scope_count": 5,
            "support_multiplicity": 1,
            "topology": "local",
            "churn_fraction": 0.01,
        },
        "proof": {
            "depth": 8,
            "relevant_nodes": 80,
            "distractor_count": 20,
            "shape": "shared_dag",
        },
        "bridge": {
            "node_count": 80,
            "edge_count": 240,
            "candidate_count": 12,
            "goal_count": 4,
            "topology": "disconnected_distractors",
        },
        "fluid": {"length": 64, "microsteps": 8},
    }, seed=111)
    assert actual["live_revision_atoms"] == 100
    assert actual["fluid_edge_updates"] == 2 * 63 * 8
    assert metrics["combined_elapsed_ms"] >= metrics["measured_stage_sum_ms"]
    assert all(correctness.values())
