import json

from freeciv.harness.fdas_execution_hardening import (
    audit_execution_hardening,
)


def _write_json(path, value):
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _fixture(tmp_path, *, second_unit=False, target=(1, 1)):
    run_dir = tmp_path / "run"
    game_dir = run_dir / "games" / "main" / "e_full_loop" / "7-00"
    game_dir.mkdir(parents=True)
    action = {
        "action_type": "unit_move",
        "actor_id": 4,
        "target": {"x": target[0], "y": target[1]},
    }
    events = [
        {
            "type": "state_snapshot", "seq": 1, "turn": 9,
            "payload": {
                "snapshot_id": "snapshot-1",
                "map": {"width": 2, "height": 2},
                "grounded_context": {"legal_actions": [action]},
            },
        },
        {
            "type": "action_sent", "seq": 2, "turn": 9,
            "payload": {
                "action": action,
                "action_id": "action-1",
                "snapshot_id": "snapshot-1",
            },
        },
        {
            "type": "action_result", "seq": 3, "turn": 9,
            "payload": {
                "action_id": "action-1", "status": "accepted",
                "engine_response": {"accepted": True},
            },
        },
    ]
    if second_unit:
        events.append({
            "type": "action_sent", "seq": 4, "turn": 9,
            "payload": {
                "action": action,
                "action_id": "action-2",
                "snapshot_id": "snapshot-1",
            },
        })
    with (game_dir / "events.jsonl").open("w", encoding="utf-8") as stream:
        for event in events:
            stream.write(json.dumps(event) + "\n")
    _write_json(game_dir / "manifest.json", {
        "game_id": "game-7", "seed": 7,
        "source": {"commit": "abc", "dirty": False},
    })
    _write_json(game_dir / "status.json", {
        "completed": True,
        "decision_stale_unit_scope_followups_blocked": 0,
        "infrastructure_failure": False,
        "rejected_actions": 0,
    })
    randomized = tmp_path / "randomized.json"
    _write_json(randomized, {
        "audit_identity": "fdas-randomized-alternative-live-audit/1.5",
        "games": [{"seed": 7}],
        "passed": True,
        "report_hash": "audit-hash",
    })
    return run_dir, randomized


def test_execution_hardening_audit_accepts_safe_trace(tmp_path):
    run_dir, randomized = _fixture(tmp_path)

    report = audit_execution_hardening(
        str(run_dir), str(randomized), expected_seeds=(7,),
        historical_seed=7, historical_turn=9)

    assert report["passed"] is True
    assert report["games"][0]["spatial_actions_checked"] == 1


def test_execution_hardening_audit_rejects_off_map_catalog_action(tmp_path):
    run_dir, randomized = _fixture(tmp_path, target=(1, -1))

    report = audit_execution_hardening(
        str(run_dir), str(randomized), expected_seeds=(7,),
        historical_seed=7, historical_turn=9)

    assert report["passed"] is False
    assert report["games"][0]["spatial_violations"]


def test_execution_hardening_audit_rejects_stale_unit_replay(tmp_path):
    run_dir, randomized = _fixture(tmp_path, second_unit=True)

    report = audit_execution_hardening(
        str(run_dir), str(randomized), expected_seeds=(7,),
        historical_seed=7, historical_turn=9)

    assert report["passed"] is False
    assert report["games"][0]["duplicate_after_acceptance"]
    assert report["games"][0]["stale_unit_scope_followups"]
