import json

from freeciv.harness.fdas_observation_return_live import (
    COHORT,
    MECHANISM,
    audit_fdas_observation_return_live,
)


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _event(seq, event_type, payload, caused_by=()):
    return {
        "caused_by": list(caused_by),
        "event_id": "e{}".format(seq),
        "game_id": "observation-return-test",
        "payload": payload,
        "schema_version": "1.0",
        "seq": seq,
        "ts": "2026-08-02T00:00:00Z",
        "turn": 2,
        "type": event_type,
    }


def _fixture(tmp_path):
    action = {
        "action_type": "unit_move",
        "actor_id": 7,
        "target": {"x": 1, "y": 1},
    }
    source = {
        "commit": "a" * 40,
        "dirty": False,
        "implementation_sha256": "b" * 64,
    }
    for arm in ("baseline", "treatment"):
        directory = (
            tmp_path / "games" / "impact_pair" / COHORT / arm
            / "e_full_loop" / "173205-00")
        _write_json(directory / "manifest.json", {
            "dependent_atomspace": {
                "config": {
                    "authority_enabled": False,
                    "inference": {"uncertain_assessment_enabled": True},
                    "projection": {"beliefs": True},
                },
                "config_source": (
                    "profile/dependent_atomspace_observation_execution_shadow.yaml"),
                "manifest": {
                    "capabilities": {
                        "belief_domain_projection": "shadow-live",
                        "observation_pressure_planning": "shadow-live",
                    },
                    "observation_execution": {
                        "authoritative_return_required": True,
                        "mode": "legacy-selected-visibility-return-shadow",
                        "policy_authority": False,
                    },
                    "policy_authority": False,
                },
                "manifest_source": (
                    "profile/fdas_manifest_observation_execution_shadow.json"),
            },
            "release_game_config": {"fogofwar": True},
            "source": source,
        })
        binding = {
            "action": action,
            "action_key": json.dumps(action, sort_keys=True,
                                     separators=(",", ":")),
            "binding_hash": "c" * 64,
            "operation_id": "observe:visibility-frontier",
            "policy_authority": False,
            "selection_record": {"selected": True},
        }
        token = {
            "base_weight": 1.0,
            "decay_class": "visibility",
            "observation_policy": {
                "channel": "observe",
                "goal_id": "observe:frontier",
                "priority": 0.2,
                "propensity": None,
            },
            "source": "authoritative-player-visibility-delta",
            "strength": 1.0,
            "timestamp": 2,
            "token_id": "observation-return-token",
        }
        events = (
            _event(1, "pressure_propagated", {
                "config": {"mechanism": MECHANISM}}),
            _event(2, "packet_reserved", {"summary": {
                "evidence_count_after_planning": 1,
                "evidence_count_before_planning": 1,
                "evidence_store_hash_after_planning": "d" * 64,
                "evidence_store_hash_before_planning": "d" * 64,
                "mechanism": MECHANISM,
                "truth_mutated": False,
            }}, caused_by=("e1",)),
            _event(3, "candidate_revalidated", {"summary": {
                "binding": binding,
                "commit_validation": {
                    "policy_authority": False,
                    "reason": None,
                    "status": "committed",
                },
            }}, caused_by=("e2",)),
            _event(4, "action_sent", {"action": action}, caused_by=("e3",)),
            _event(5, "action_result", {"status": "accepted"},
                   caused_by=("e4",)),
            _event(6, "packet_returned", {"summary": {
                "authoritative_return": {
                    "binding_hash": "c" * 64,
                    "evidence_token": token,
                    "new_visible_tile_ids": [3, 4],
                    "operation_id": "observe:visibility-frontier",
                    "outcome_id": "visibility-expanded",
                },
            }}, caused_by=("e5", "refresh-state")),
            _event(7, "observation", {
                "provenance_id": "observation-return-token",
                "source": "authoritative-player-visibility-delta",
            }, caused_by=("e6",)),
        )
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "events.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in events),
            encoding="utf-8")
        _write_json(directory / "status.json", {
            "completed": True,
            "engine_actions": 1,
            "fdas_authority_actions": 0,
            "fdas_observation_action_bindings": 1,
            "fdas_observation_authoritative_returns": 1,
            "fdas_observation_commit_revalidations": 1,
            "fdas_observation_evidence_write_throughs": 1,
            "fdas_observation_return_abstentions": 0,
            "fdas_observation_visibility_expansions": 1,
            "fdas_observation_visibility_unchanged": 0,
            "horizon_reached": True,
            "operation_authority_actions": 0,
            "rejected_actions": 0,
        })
    _write_json(tmp_path / "impact-aggregate.json", {
        "claim_evaluation": {"status": "ineligible"},
        "complete_pairs": 1,
        "design": {"claim_eligible": False, "cohort": COHORT},
        "failures": [],
        "source_freeze": {"passed": True},
    })
    _write_json(tmp_path / "impact-run-summary.json", {
        "completed": 2,
        "infrastructure_failures": 0,
        "source_stable": True,
    })


def test_observation_return_audit_accepts_exact_legacy_bound_pair(tmp_path):
    _fixture(tmp_path)

    report = audit_fdas_observation_return_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["bindings"] == 2
    assert report["summary"]["evidence_returns"] == 2


def test_observation_return_audit_rejects_pre_return_evidence_mutation(tmp_path):
    _fixture(tmp_path)
    path = (tmp_path / "games" / "impact_pair" / COHORT / "baseline"
            / "e_full_loop" / "173205-00" / "events.jsonl")
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    rows[1]["payload"]["summary"]["evidence_count_after_planning"] = 2
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")

    report = audit_fdas_observation_return_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    baseline = next(row for row in report["arms"]
                    if row["arm"] == "baseline")
    assert baseline["acceptance"]["checks"][
        "planning_firewall_stays_closed_until_return"] is False


def test_observation_return_audit_rejects_unlinked_action_result(tmp_path):
    _fixture(tmp_path)
    path = (tmp_path / "games" / "impact_pair" / COHORT / "treatment"
            / "e_full_loop" / "173205-00" / "events.jsonl")
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    rows[5]["caused_by"] = ["refresh-state"]
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")

    report = audit_fdas_observation_return_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False


def test_observation_return_audit_accepts_explicit_censored_no_write(tmp_path):
    _fixture(tmp_path)
    directory = (tmp_path / "games" / "impact_pair" / COHORT / "baseline"
                 / "e_full_loop" / "173205-00")
    event_path = directory / "events.jsonl"
    rows = [json.loads(line) for line in event_path.read_text(
        encoding="utf-8").splitlines()]
    rows[5]["payload"]["summary"] = {
        "belief_evidence_count_after": 1,
        "belief_evidence_count_before": 1,
        "evidence_token_count_after": 0,
        "evidence_token_count_before": 0,
        "return_abstention": {
            "abstention_hash": "e" * 64,
            "action_event_id": "e5",
            "after_snapshot_id": "snapshot-after",
            "before_snapshot_id": "snapshot-before",
            "binding_hash": "c" * 64,
            "evidence_registered": False,
            "observed_visible_tile_ids": [1, 2, 3],
            "operation_id": "observe:visibility-frontier",
            "policy_authority": False,
            "reason": "actor-removed-before-observation-proof",
            "truth_mutated": False,
        },
        "truth_mutated": False,
    }
    rows = rows[:6]
    event_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")
    status_path = directory / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.update({
        "fdas_observation_authoritative_returns": 0,
        "fdas_observation_evidence_write_throughs": 0,
        "fdas_observation_return_abstentions": 1,
        "fdas_observation_visibility_expansions": 0,
    })
    _write_json(status_path, status)

    report = audit_fdas_observation_return_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    baseline = next(row for row in report["arms"]
                    if row["arm"] == "baseline")
    assert baseline["summary"]["evidence_returns"] == 0
    assert baseline["summary"]["return_abstentions"] == 1
