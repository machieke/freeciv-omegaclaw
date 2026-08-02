import json

from freeciv.harness.fdas_expansion_live import audit_fdas_expansion_live
from freeciv_agent.events.schema import structural_hash


def _write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _event(event_id, event_type, payload, caused_by=(), turn=4):
    return {
        "caused_by": list(caused_by),
        "event_id": event_id,
        "game_id": "fdas-expansion-live-test",
        "payload": payload,
        "schema_version": "1.0",
        "seq": int(event_id[1:]),
        "ts": "2026-08-02T00:00:00Z",
        "turn": turn,
        "type": event_type,
    }


def _fixture(tmp_path):
    operation_id = "operation-expansion-live"
    snapshot_id = "snapshot-4"
    action = {"action_type": "unit_build_city", "actor_id": 102}
    spec = {
        "created_turn": 4,
        "expiry_turn": 6,
        "goal_ids": ["pf-impact:expansion"],
        "operation_id": operation_id,
        "operation_type": "fdas_expansion_found_city",
        "participants": [{
            "actor_class": "unit", "actor_id": "unit:102",
            "required": True, "role": "founder",
        }],
        "provenance": ["fdas-expansion-operation-adapter/1.0"],
        "replacement_margin": 0.0,
        "ruleset_digest": "a" * 64,
        "schema_version": 1,
        "steps": [{
            "action_type": "unit_build_city", "actor_role": "founder",
            "completion_predicate_id": "founder-consumed-and-city-at-tile",
            "maximum_attempts": 1, "requirement_set_id": "requirement-1",
            "step_id": "step-1", "target_ref": "tile:484",
        }],
        "target_ref": "tile:484",
    }
    spec["spec_digest"] = structural_hash(spec)
    store = {
        "persistence_identity": "persistence-expansion-live",
        "quarantine_reason": None,
        "records": [{
            "progress": {
                "attempt_count": 1, "blocked_reason": None,
                "current_step_index": 0,
                "last_snapshot_id": "snapshot-5", "last_updated_turn": 5,
                "operation_id": operation_id, "state": "completed",
                "terminal_reason": "authoritative-expansion-effect-observed",
            },
            "spec": spec,
        }],
        "schema_version": 1,
        "store_identity": "freeciv-operation-store/1.0",
    }
    store["store_digest"] = structural_hash(store)
    _write_json(tmp_path / "fdas-expansion-operations.json", store)

    lifecycle = {
        "operation_id": operation_id, "policy_authority": False,
        "selected": False, "shadow_only": True,
    }
    events = [
        _event("e1", "operation_projected", {
            "details": {"operation_id": operation_id}}),
        _event("e2", "action_sent", {
            "action": action, "action_id": "action-1",
            "snapshot_id": snapshot_id}, ("e1",)),
        _event("e3", "action_result", {
            "action_id": "action-1", "status": "accepted"}, ("e2",)),
        _event("e4", "operation_activated", dict(
            lifecycle, next_action=action, snapshot_id=snapshot_id), ("e3",)),
        _event("e5", "operation_completed", dict(
            lifecycle, next_action=None, snapshot_id="snapshot-5"), ("e4",),
            turn=5),
        _event("e6", "metric_sample", {
            "labels": {"cold_equivalent": "True", "cold_verified": "True"},
            "name": "fdas_projection_latency_ms", "unit": "ms", "value": 25,
        }, ("e5",), turn=5),
        _event("e7", "metric_sample", {
            "labels": {}, "name": "fdas_shadow_evaluation_latency_ms",
            "unit": "ms", "value": 2,
        }, ("e6",), turn=5),
        _event("e8", "metric_sample", {
            "labels": {}, "name": "turn_full_loop_latency_ms",
            "unit": "ms", "value": 100,
        }, ("e7",), turn=5),
        _event("e9", "run_completed", {"summary": {
            "fdas_expansion_action_matches": 1,
            "fdas_expansion_completions": 1,
            "fdas_expansion_expirations": 0,
            "fdas_expansion_failures": 0,
        }}, ("e8",), turn=5),
    ]
    (tmp_path / "events.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in events),
        encoding="utf-8")
    _write_json(tmp_path / "manifest.json", {
        "dependent_atomspace": {
            "config": {
                "authority_enabled": False,
                "domain_authority": {"expansion": False},
                "enabled": True,
                "shadow_enabled": True,
            },
            "manifest": {"policy_authority": False, "status": "shadow-live"},
        },
        "source": {"commit": "b" * 40, "dirty": False},
    })
    _write_json(tmp_path / "status.json", {
        "completed": True, "engine_actions": 1, "horizon_reached": True,
        "rejected_actions": 0,
    })


def test_expansion_live_audit_accepts_exact_non_authorizing_lifecycle(tmp_path):
    _fixture(tmp_path)

    report = audit_fdas_expansion_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["action_matches"] == 1
    assert report["summary"]["completions"] == 1
    assert all(report["operations"][0]["causal"].values())


def test_expansion_live_audit_rejects_any_fdas_authority_event(tmp_path):
    _fixture(tmp_path)
    path = tmp_path / "events.jsonl"
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    rows.insert(-1, _event("e10", "atomspace_authority_decision", {
        "details": {"status": "authorized"}}, ("e8",), turn=5))
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")

    report = audit_fdas_expansion_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    assert report["acceptance"]["checks"]["no_fdas_authority_events"] is False
