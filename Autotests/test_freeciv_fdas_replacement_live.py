import json

from freeciv.harness.fdas_replacement_live import audit_fdas_replacement_live
from freeciv.harness.fdas_replacement_readout_live import (
    audit_fdas_replacement_readout_live,
)
from freeciv.harness.fdas_replacement_readout_cohort import (
    audit_fdas_replacement_readout_cohort,
)
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


def _add_candidate_readout(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    activation = manifest["dependent_atomspace"]["manifest"]
    activation["capabilities"][
        "coordinated_replacement_candidate_readout"] = "shadow-live"
    activation["coordinated_replacement_candidate_readout_diagnostic"] = {
        "action_selection_changed": False,
        "combined_native_route_grounding_required": True,
        "direct_control_semantics": "protected-source-garrison-direct-move",
        "policy_authority": False,
        "readout_authority": False,
        "transition_value_estimated": False,
        "truth_mutated": False,
    }
    _write_json(manifest_path, manifest)

    pair = {
        "combined_estimated_turns": 2,
        "combined_movement_cost": 2,
        "direct_action_key": "direct-action",
        "direct_operation_id": "direct-proof",
        "direct_unsafe_reason": "protected-source-garrison",
        "lifecycle_operation_id": "replacement-proof",
        "replacement_action_key": "replacement-action",
        "replacement_actor_id": 8,
        "replacement_estimated_turns": 1,
        "replacement_movement_cost": 1,
        "replacement_operation_id": "replacement-proof",
        "reinforcement_actor_id": 7,
        "reinforcement_estimated_turns": 1,
        "reinforcement_movement_cost": 1,
        "requirement_context_hash": "requirement-proof",
        "safe_chain_grounded": True,
        "source_city_id": 3,
        "target_city_id": 4,
    }
    pair["result_hash"] = structural_hash(pair)
    details = {
        "action_selection_changed": False,
        "candidate_recall_changed": True,
        "direct_candidate_count": 1,
        "identity": "fdas-coordinated-replacement-candidate-readout/1.0",
        "pairs": [pair],
        "policy_authority": False,
        "readout_authority": False,
        "reason": "grounded-safe-chain-recalled",
        "rejected": [],
        "replacement_candidate_count": 1,
        "revision_id": "revision-1",
        "snapshot_id": "snapshot-4",
        "status": "eligible-shadow",
        "transition_value_estimated": False,
        "truth_mutated": False,
    }
    details["result_hash"] = structural_hash(details)
    payload = {
        "component_id": "fdas-coordinated-replacement-candidate-readout",
        "component_version": "1.0",
        "details": details,
        "revision_id": "revision-1",
        "ruleset_digest": "ruleset-proof",
        "snapshot_id": "snapshot-4",
    }
    payload["structural_hash"] = structural_hash(payload)
    events_path = tmp_path / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(
        encoding="utf-8").splitlines()]
    readout_event = {
        **events[-1],
        "caused_by": [events[0]["event_id"]],
        "event_id": "event-readout",
        "payload": payload,
        "seq": 1,
        "type": "atomspace_shadow_decision",
    }
    events[-1]["caused_by"] = ["event-readout"]
    events[-1]["seq"] = 2
    counters = {
        "fdas_replacement_readout_abstentions": 0,
        "fdas_replacement_readout_candidates": 1,
        "fdas_replacement_readout_direct_controls": 1,
        "fdas_replacement_readout_evaluations": 1,
        "fdas_replacement_readout_grounded_pairs": 1,
        "fdas_replacement_readout_rejections": 0,
    }
    events[-1]["payload"]["summary"].update(counters)
    events_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n"
                for row in (events[0], readout_event, events[-1])),
        encoding="utf-8")
    status_path = tmp_path / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.update(counters)
    _write_json(status_path, status)


def _activate_zero_opportunity_readout(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    activation = manifest["dependent_atomspace"]["manifest"]
    activation["capabilities"][
        "coordinated_replacement_candidate_readout"] = "shadow-live"
    activation["coordinated_replacement_candidate_readout_diagnostic"] = {
        "action_selection_changed": False,
        "combined_native_route_grounding_required": True,
        "direct_control_semantics": "protected-source-garrison-direct-move",
        "policy_authority": False,
        "readout_authority": False,
        "transition_value_estimated": False,
        "truth_mutated": False,
    }
    _write_json(manifest_path, manifest)
    counters = {
        "fdas_replacement_readout_abstentions": 0,
        "fdas_replacement_readout_candidates": 0,
        "fdas_replacement_readout_direct_controls": 0,
        "fdas_replacement_readout_evaluations": 0,
        "fdas_replacement_readout_grounded_pairs": 0,
        "fdas_replacement_readout_rejections": 0,
    }
    status_path = tmp_path / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.update(counters)
    _write_json(status_path, status)
    events_path = tmp_path / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(
        encoding="utf-8").splitlines()]
    events[-1]["payload"]["summary"].update(counters)
    events_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in events),
        encoding="utf-8")


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


def test_replacement_readout_live_accepts_grounded_safe_chain(tmp_path):
    _fixture(tmp_path)
    _add_candidate_readout(tmp_path)

    report = audit_fdas_replacement_readout_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["grounded_pairs"] == 1
    assert report["summary"]["replacement_candidates"] == 1


def test_replacement_readout_allows_zero_opportunity_in_cohort_scope(tmp_path):
    _fixture(tmp_path, with_operation=False)
    _activate_zero_opportunity_readout(tmp_path)

    report = audit_fdas_replacement_readout_live(
        str(tmp_path), require_grounded_pair=False)

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["grounded_pairs"] == 0


def test_replacement_readout_cohort_requires_two_opportunity_games(tmp_path):
    run_dir = tmp_path / "cohort"
    games = run_dir / "games" / "main" / "e_full_loop"
    for seed in (101, 103):
        game_dir = games / (str(seed) + "-00")
        game_dir.mkdir(parents=True)
        _fixture(game_dir)
        _add_candidate_readout(game_dir)
    _write_json(run_dir / "run-summary.json", {
        "completed": 2, "infrastructure_failures": 0,
        "jobs": 2, "resumed": 0,
    })

    report = audit_fdas_replacement_readout_cohort(
        str(run_dir), (101, 103), expected_source_commit="a" * 40)

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["opportunity_game_count"] == 2
    assert report["summary"]["grounded_pair_count"] == 2
