import json

from freeciv.harness.fdas_replacement_live import audit_fdas_replacement_live
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.events.writer import EventWriter


def _write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _atom_payload(snapshot_id, operation_id, store_digest):
    details = {
        "action_selection_changed": False,
        "binding": None,
        "disposition": "reservable",
        "identity": "fdas-coordinated-replacement-lifecycle/1.0",
        "operation_id": operation_id,
        "policy_authority": False,
        "previous_state": "proposed",
        "readout_authority": False,
        "reason": "current-coordinated-step-grounded",
        "snapshot_id": snapshot_id,
        "state": "reservable",
        "store_digest": store_digest,
        "truth_mutated": False,
    }
    material = {
        "component_id": "fdas-coordinated-replacement-lifecycle",
        "component_version": "1.0",
        "details": details,
        "revision_id": "revision-1",
        "ruleset_digest": "ruleset-proof",
        "snapshot_id": snapshot_id,
    }
    material["structural_hash"] = structural_hash(material)
    return material


def _fixture(tmp_path, with_operation=True):
    manifest = {
        "attempt_id": "attempt-proof",
        "dependent_atomspace": {
            "config": {"projection": {"operations": True}},
            "manifest": {"capabilities": {
                "coordinated_replacement_lifecycle": "shadow-live"}},
        },
        "game_id": "replacement-live-proof",
        "manifest_identity": "manifest-proof",
        "source": {"commit": "a" * 40, "dirty": False},
    }
    persistence = structural_hash([
        manifest["manifest_identity"], manifest["attempt_id"],
        manifest["game_id"],
        "fdas-coordinated-replacement-operations/1.0",
    ])
    records = []
    operation_id = "replacement-proof"
    if with_operation:
        spec = {
            "created_turn": 4,
            "expiry_turn": 8,
            "goal_ids": ["pf-impact:survival"],
            "operation_id": operation_id,
            "operation_type": "fdas-defense:coordinated-replacement",
            "participants": [
                {"actor_class": "unit", "actor_id": "8", "required": True,
                 "role": "replacement"},
                {"actor_class": "unit", "actor_id": "7", "required": True,
                 "role": "reinforcement"},
            ],
            "provenance": ["fdas-coordinated-replacement-shadow/1.0"],
            "replacement_margin": 0.0,
            "ruleset_digest": "ruleset-proof",
            "schema_version": 1,
            "steps": [
                {"action_type": "unit_move", "actor_role": "replacement",
                 "completion_predicate_id": "replacement-at-source",
                 "maximum_attempts": 3,
                 "requirement_set_id": "replacement-requirements",
                 "step_id": "replacement-step", "target_ref": "city:3"},
                {"action_type": "unit_move", "actor_role": "reinforcement",
                 "completion_predicate_id": "reinforcement-at-target",
                 "maximum_attempts": 3,
                 "requirement_set_id": "reinforcement-requirements",
                 "step_id": "reinforcement-step", "target_ref": "city:4"},
            ],
            "target_ref": "city:4",
        }
        spec["spec_digest"] = structural_hash(spec)
        records.append({
            "progress": {
                "attempt_count": 0, "blocked_reason": None,
                "current_step_index": 0, "last_snapshot_id": "snapshot-4",
                "last_updated_turn": 4, "operation_id": operation_id,
                "state": "reservable", "terminal_reason": None,
            },
            "spec": spec,
        })
    store = {
        "persistence_identity": persistence,
        "quarantine_reason": None,
        "records": records,
        "schema_version": 1,
        "store_identity": "freeciv-operation-store/1.0",
    }
    store["store_digest"] = structural_hash(store)
    _write_json(tmp_path / "manifest.json", manifest)
    _write_json(
        tmp_path / "fdas-coordinated-replacement-operations.json", store)

    counters = {
        "fdas_replacement_blocked": 0,
        "fdas_replacement_candidates": 1 if with_operation else 0,
        "fdas_replacement_completions": 0,
        "fdas_replacement_expirations": 0,
        "fdas_replacement_operations": 1 if with_operation else 0,
        "fdas_replacement_reconciliations": 1 if with_operation else 0,
        "fdas_replacement_reservable": 1 if with_operation else 0,
        "fdas_replacement_step_advances": 0,
    }
    _write_json(tmp_path / "status.json", dict(
        counters, completed=True, horizon_reached=True))
    writer = EventWriter(
        str(tmp_path / "events.jsonl"), manifest["game_id"], durable=False,
        id_factory=iter(("event-1", "event-2")).__next__)
    parent = None
    if with_operation:
        row = writer.emit(
            "atomspace_shadow_decision", 4,
            _atom_payload("snapshot-4", operation_id, store["store_digest"]))
        parent = row["event_id"]
    writer.emit(
        "run_completed", 4,
        {"status": "completed", "summary": counters},
        caused_by=(() if parent is None else (parent,)))


def test_replacement_live_accepts_observed_shadow_lifecycle(tmp_path):
    _fixture(tmp_path)

    report = audit_fdas_replacement_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["operations"] == 1
    assert report["summary"]["opportunity_observed"] is True


def test_replacement_live_accepts_auditable_zero_opportunity(tmp_path):
    _fixture(tmp_path, with_operation=False)

    report = audit_fdas_replacement_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["operations"] == 0
    assert report["summary"]["opportunity_observed"] is False


def test_replacement_live_rejects_authority_leak(tmp_path):
    _fixture(tmp_path)
    path = tmp_path / "events.jsonl"
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    rows[0]["payload"]["details"]["policy_authority"] = True
    rows[0]["payload"]["structural_hash"] = structural_hash(dict(
        (key, value) for key, value in rows[0]["payload"].items()
        if key != "structural_hash"))
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")

    report = audit_fdas_replacement_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    assert report["acceptance"]["checks"][
        "lifecycle_events_are_revision_bound_and_non_authorizing"] is False
