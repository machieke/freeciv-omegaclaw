"""Paired engine-shadow audit contract tests."""

import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.fdas_shadow_cohort import (  # noqa: E402
    _mechanism_diagnostics,
    _volume,
    audit_fdas_shadow_cohort,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402


def _fdas_payload(event_type, details):
    semantic = {
        "component_id": "test-fdas",
        "component_version": "1.0",
        "details": details,
        "revision_id": "revision-1",
        "ruleset_digest": "ruleset-1",
        "snapshot_id": "snapshot-1",
    }
    semantic["structural_hash"] = structural_hash(semantic)
    return semantic


def _write_run(root, seed, enabled, action=None, dirty=False):
    run_dir = root / "games" / "main" / "e_full_loop" / "{}-00".format(seed)
    run_dir.mkdir(parents=True)
    config = {
        "authority_enabled": False,
        "domain_authority": {"city_stability": False},
        "enabled": enabled,
        "materialization": {"maximum_atoms_global": 100},
        "shadow_enabled": True,
    }
    manifest = {
        "backend": "engine-live", "beliefs": {}, "capabilities": {},
        "condition_id": "e_full_loop", "controller_workers": 1,
        "controller_worker_execution": "thread", "engine": {},
        "engine_finalization_turns": 0, "engine_max_turns": 30,
        "impact_policy": {}, "machine_profile": "test", "model": "model",
        "model_config": {}, "opponent": {}, "pf_pln_controller": {},
        "pf_pln_runtime": {}, "release_game_config": {}, "rulebase": {},
        "ruleset": "rules", "seed": seed, "sequence": 0, "track": "main",
        "turn_limit": 30, "events_path": "events.jsonl",
        "manifest_identity": "manifest-{}-{}".format(seed, enabled),
        "source": {
            "commit": "commit", "dirty": dirty,
            "implementation_sha256": "implementation",
        },
        "dependent_atomspace": {
            "config": config, "manifest": {"policy_authority": False}},
    }
    with open(run_dir / "manifest.json", "w", encoding="utf-8") as stream:
        json.dump(manifest, stream)
    with open(run_dir / "status.json", "w", encoding="utf-8") as stream:
        json.dump({"status": "completed"}, stream)
    writer = EventWriter(
        str(run_dir / "events.jsonl"), "game-{}-{}".format(seed, enabled))
    root_event = writer.emit("run_started", 0, {
        "condition_id": "e_full_loop",
        "manifest_identity": manifest["manifest_identity"],
    })
    parent = root_event["event_id"]
    selection = writer.emit("goal_selection", 1, {
        "candidate_count": 1,
        "goal": {
            "arguments": ["player-1", "Pottery"],
            "goal_id": "goal-1", "predicate": "researchable",
            "target_id": "rules:tech:Pottery",
        },
        "model_call_avoided": True,
        "policy": "canonical-singleton-bypass-v1",
        "proposal_id": "proposal-1", "selection_id": "selection-1",
        "source": "canonical_catalog",
    }, caused_by=[parent])
    parent = selection["event_id"]
    action = action or {"action_type": "end_turn"}
    sent = writer.emit("action_sent", 1, {
        "action": action, "action_id": "action-1",
        "legal_actions_digest": "legal", "plan_id": None,
        "snapshot_id": "snapshot", "step_id": None,
    }, caused_by=[parent])
    result = writer.emit("action_result", 1, {
        "action_id": "action-1", "engine_response": {},
        "engine_turn": 1, "status": "accepted",
    }, caused_by=[sent["event_id"]])
    parent = result["event_id"]
    if enabled:
        committed = writer.emit(
            "atomspace_revision_committed", 1,
            _fdas_payload("atomspace_revision_committed", {
                "atom_count": 10, "build_hash": "build",
                "detail_event_count": 1, "omitted_detail_event_count": 0,
                "scope_count": 2, "support_count": 4,
            }), caused_by=[parent])
        parent = committed["event_id"]
        shadow = writer.emit(
            "atomspace_shadow_decision", 1,
            _fdas_payload("atomspace_shadow_decision", {
                "authority_eligible": False, "comparison": {
                    "authority_violations": [], "comparison_hash": "comparison",
                    "explained_legacy_count": 2,
                    "extra_fdas_count": 0, "fdas_candidate_count": 1,
                    "legal_binding_failures": [], "legacy_candidate_count": 1,
                    "missing_legacy_count": 0, "overlap_count": 1,
                    "safety_downgrades": [],
                }, "evaluation_hash": "evaluation",
                "candidate_instantiation_hash": "instantiation",
                "decision_explanation_hash": "explanation",
                "decision_route_kind": "candidate", "decision_blockers": [],
                "latency_ms": 4.0, "omitted_detail_event_count": 0,
                "reason": None, "schedule_hash": "schedule",
                "selected_operation_id": "operation", "stage_latency_ms": {
                    "candidate_instantiation": 2.0,
                    "pressure_evaluation": 1.0}, "status": "selected",
            }), caused_by=[parent])
        parent = shadow["event_id"]
        for name, value in (
                ("fdas_projection_latency_ms", 20.0),
                ("fdas_shadow_evaluation_latency_ms", 4.0)):
            metric = writer.emit("metric_sample", 1, {
                "labels": {
                    "cold_equivalent": "True", "cold_verified": "True",
                    "condition": "e_full_loop", "track": "main"},
                "name": name, "unit": "ms", "value": value,
            }, caused_by=[parent])
            parent = metric["event_id"]
    metric = writer.emit("metric_sample", 1, {
        "labels": {"condition": "e_full_loop", "track": "main"},
        "name": "turn_full_loop_latency_ms", "unit": "ms", "value": 100.0,
    }, caused_by=[parent])
    writer.emit("run_completed", 30, {
        "status": "completed", "summary": {
            "actions": 1, "decision_impact_actions": 0,
            "horizon_reached": True, "meaningful_actions": 0,
            "opponent_score": 10, "score": 11, "score_lead": True,
            "score_margin": 1, "terminal_game_over": False,
            "terminal_player_elimination": False, "won": True,
        }}, caused_by=[metric["event_id"]])


def test_audit_accepts_exact_read_only_shadow_pairs(tmp_path):
    control = tmp_path / "control"
    shadow = tmp_path / "shadow"
    for seed in (11, 13, 17):
        _write_run(control, seed, False)
        _write_run(shadow, seed, True)

    report = audit_fdas_shadow_cohort(control, shadow)

    assert report["acceptance"]["accepted"]
    assert report["aggregate"]["totals"]["decision_count"] == 3
    assert report["aggregate"]["totals"]["cold_verification_count"] == 3
    assert report["aggregate"]["totals"]["explained_legacy_count"] == 6
    assert all(pair["action_trace_match"] for pair in report["pairs"])


def test_audit_rejects_action_divergence_and_dirty_source(tmp_path):
    control = tmp_path / "control"
    shadow = tmp_path / "shadow"
    for seed in (11, 13, 17):
        _write_run(control, seed, False)
        _write_run(
            shadow, seed, True,
            action={"action_type": "unit_move", "actor_id": 1},
            dirty=seed == 13)

    report = audit_fdas_shadow_cohort(control, shadow)
    kinds = {failure["kind"] for failure in report["failures"]}

    assert not report["acceptance"]["accepted"]
    assert "ordered-action-trace-mismatch" in kinds
    assert "source-identity-mismatch-or-dirty" in kinds


def test_high_entity_volume_and_bridge_flow_work_are_reconstructed():
    events = [
        {"type": "state_snapshot", "payload": {
            "own_state": {"cities": [{}, {}], "units": [{}, {}, {}]},
            "grounded_context": {"legal_actions": [{}, {}, {}, {}]},
        }},
        {"type": "scope_materialized", "payload": {
            "snapshot_id": "s1", "details": {
                "scope_id": "r1", "scope_kind": "region"}}},
        {"type": "scope_materialized", "payload": {
            "snapshot_id": "s1", "details": {
                "scope_id": "r2", "scope_kind": "region"}}},
        {"type": "pressure_graph_built", "payload": {"details": {
            "candidate_atom_count": 7, "goal_count": 5}}},
        {"type": "pressure_propagated", "payload": {"dependency": {
            "goal-a": {"candidate-a": 0.5, "candidate-b": 0.5},
            "goal-b": {"candidate-b": 1.0}}}},
        {"type": "pln_result", "payload": {
            "chain_depth": 11, "tree_size": 31}},
        {"type": "atomspace_revision_committed", "payload": {"details": {
            "atom_count": 100, "scope_count": 8, "support_count": 50,
            "omitted_detail_event_count": 0}}},
        {"type": "bridge_estimated", "payload": {"summary": {
            "goal_summaries": [{"node_count": 123}]}}},
        {"type": "flow_projected", "payload": {"summary": {
            "projections": [{
                "health": "healthy", "iterations": 17}]}}},
    ]

    volume = _volume(events)
    mechanisms = _mechanism_diagnostics(events)
    assert volume["cities"] == 2
    assert volume["units"] == 3
    assert volume["region_scopes"] == 2
    assert volume["concurrent_goals"] == 5
    assert volume["grounded_candidates"] == 7
    assert volume["control_nodes"] == 4
    assert volume["control_edges"] == 3
    assert volume["proof_chain_depth"] == 11
    assert volume["proof_tree_size"] == 31
    assert mechanisms == {
        "bridge_event_count": 1,
        "controller_fallback_count": 0,
        "flow_event_count": 1,
        "flow_projection_count": 1,
        "maximum_bridge_nodes": 123,
        "maximum_flow_iterations": 17,
        "unhealthy_flow_projection_count": 0,
        "unexplained_controller_fallback_count": 0,
    }


def test_g8_scenario_fails_closed_without_scale_flow_or_detail(tmp_path):
    control = tmp_path / "control"
    shadow = tmp_path / "shadow"
    _write_run(control, 11, False)
    _write_run(shadow, 11, True)
    scenario = {
        "schema_version": "freeciv-scalability-engine-shadow/1.0",
        "scenario_id": "test-he1", "minimum_pairs": 20,
        "horizon_turn": 30, "require_clean_source": True,
        "release_game_config": {
            "fogofwar": False, "startunits": "ccccxxxxxxxxdddddddd"},
        "required_shadow_mechanisms": [
            "functional_dependent_atomspace", "protected_bridge",
            "source_sink_flow"],
        "reference_cohort": {"root": "test", "report_sha256": "0" * 64},
        "reference_maximum_volume": {
            "atoms": 10, "cities": 1, "concurrent_goals": 1,
            "grounded_candidates": 1, "legal_actions": 1,
            "region_scopes": 1, "scopes": 2, "supports": 4,
            "units": 1,
        },
    }
    for root in (control, shadow):
        path = root / "games" / "main" / "e_full_loop" / "11-00" / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["engine_shadow_scenario"] = scenario
        manifest["release_game_config"] = scenario["release_game_config"]
        manifest["impact_policy"].update({
            "pressure_bridge_enabled": True,
            "pressure_controller_mode": "unified_flow_advisory",
            "pressure_flow_enabled": True,
            "pressure_flow_live_enabled": False,
        })
        path.write_text(json.dumps(manifest), encoding="utf-8")

    report = audit_fdas_shadow_cohort(control, shadow, minimum_pairs=1)
    kinds = {failure["kind"] for failure in report["failures"]}

    assert not report["acceptance"]["accepted"]
    assert "bridge-flow-shadow-not-exercised" in kinds
    assert "full-detail-sample-missing" in kinds
    assert "high-entity-volume-not-expanded" in kinds
