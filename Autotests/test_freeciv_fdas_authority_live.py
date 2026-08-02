import json

from freeciv.harness.fdas_authority_live import audit_fdas_authority_live


def _write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _event(event_id, event_type, payload, caused_by=(), turn=7):
    return {
        "caused_by": list(caused_by),
        "event_id": event_id,
        "game_id": "fdas-live-test",
        "payload": payload,
        "schema_version": "1.0",
        "seq": int(event_id[1:]),
        "ts": "2026-08-02T00:00:00Z",
        "turn": turn,
        "type": event_type,
    }


def _fixture(tmp_path, result_status="accepted"):
    action = {
        "action_type": "city_governor", "city_id": 17,
        "target": {"food_surplus_reserve": 1},
    }
    action_key = json.dumps(action, sort_keys=True, separators=(",", ":"))
    events = [
        _event("e1", "atomspace_authority_decision", {"details": {
            "action_key": action_key,
            "authority_slice": "fdas-bounded-city-stability/1.0",
            "authority_pressure": {"status": "complete"},
            "checks": [
                "domain-authority-gate",
                "revision-current-evaluation",
                "legacy-winner-fdas-route-binding",
                "bounded-city-stability-contract",
                "authority-pressure-readout",
                "resource-and-packet-schedule",
                "exact-fdas-commit-validation",
            ],
            "commit_validation": {
                "checks": [
                    "snapshot-and-legal-action-refresh",
                    "fdas-revision-identity",
                    "fdas-source-supports",
                    "fdas-candidate-identity",
                    "server-legal-action-membership",
                    "causal-effect-and-requirement-firewall",
                    "domain-authority-gate",
                ],
                "current_revision_id": "revision-7",
                "current_snapshot_id": "snapshot-7",
                "disposition": "commit", "execution_authority": False,
                "plan_materialization_authorized": True,
            },
            "operation_id": "operation-17",
            "policy_authority": True,
            "revision_id": "revision-7",
            "scheduling": {
                "policy_authority": False,
                "packet_schedule": {
                    "conserved": True, "policy_authority": False},
                "resource_schedule": {
                    "policy_authority": False, "shadow_only": True,
                    "status": "exact"},
            },
            "snapshot_id": "snapshot-7",
            "status": "authorized",
        }, "revision_id": "revision-7", "snapshot_id": "snapshot-7"}),
        _event("e2", "plan_created", {}, ("e1",)),
        _event("e3", "action_sent", {
            "action": action, "action_id": "action-17",
            "snapshot_id": "snapshot-7",
        }, ("e2",)),
        _event("e4", "action_result", {
            "action_id": "action-17", "status": result_status,
        }, ("e3",)),
        _event("e5", "atomspace_authority_decision", {"details": {
            "reason": "legacy-selected-candidate-unavailable",
            "status": "fallback",
        }}, ("e4",)),
        _event("e6", "run_completed", {"summary": {
            "actions": 1,
            "fdas_authority_actions": 1,
            "fdas_authority_fallbacks": 1,
            "fdas_authority_opportunities": 2,
            "horizon_reached": True,
            "opponent_score": 100,
            "score": 101,
        }}, ("e5",)),
    ]
    (tmp_path / "events.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in events),
        encoding="utf-8")
    _write_json(tmp_path / "manifest.json", {
        "configuration_hash": "config-hash",
        "dependent_atomspace": {
            "config_source": "authority.yaml",
            "declaration_hash": "declaration-hash",
            "manifest_source": "authority.json",
        },
        "game_id": "fdas-live-test",
        "seed": 17,
        "source": {
            "commit": "a" * 40,
            "dirty": False,
            "implementation_sha256": "implementation-hash",
        },
        "turn_limit": 7,
    })
    _write_json(tmp_path / "status.json", {"rejected_actions": 0})


def test_authority_live_audit_accepts_exact_causal_materialization(tmp_path):
    _fixture(tmp_path)
    report = audit_fdas_authority_live(str(tmp_path))
    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["authorized"] == 1
    assert report["summary"]["fallbacks"] == 1
    assert report["authorizations"][0]["authority_to_send_distance"] == 2
    assert report["authorizations"][0]["result_causal_distance"] == 1


def test_authority_live_audit_rejects_nonaccepted_engine_result(tmp_path):
    _fixture(tmp_path, result_status="rejected")
    report = audit_fdas_authority_live(str(tmp_path))
    assert report["acceptance"]["accepted"] is False
    assert report["acceptance"]["checks"][
        "all_authorized_actions_accepted"] is False
