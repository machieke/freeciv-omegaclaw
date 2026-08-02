import json

from freeciv.harness.fdas_transport_operation_live import (
    COHORT,
    MECHANISM,
    audit_fdas_transport_operation_live,
)
from freeciv_agent.events.schema import structural_hash


OPERATION_ID = "operation-transport-test"


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _event(event_id, event_type, payload, caused_by=()):
    return {
        "caused_by": list(caused_by),
        "event_id": event_id,
        "game_id": "transport-operation-test",
        "payload": payload,
        "schema_version": "1.0",
        "seq": int(event_id[1:]),
        "ts": "2026-08-02T00:00:00Z",
        "turn": 1,
        "type": event_type,
    }


def _operation_payload(state, reason, claims):
    return {
        "claims": claims,
        "mechanism": MECHANISM,
        "operation_id": OPERATION_ID,
        "policy_authority": False,
        "reason_code": reason,
        "selected": False,
        "shadow_only": True,
        "state": state,
    }


def _fixture(tmp_path):
    source = {
        "commit": "a" * 40,
        "dirty": False,
        "implementation_sha256": "b" * 64,
    }
    for arm in ("baseline", "treatment"):
        directory = (
            tmp_path / "games" / "impact_pair" / COHORT / arm
            / "e_full_loop" / "104729-00")
        _write_json(directory / "manifest.json", {
            "dependent_atomspace": {
                "config": {
                    "authority_enabled": False,
                    "domain_authority": {"transport": False},
                    "enabled": True,
                    "projection": {
                        "operations": True,
                        "route_corridors": True,
                        "transport": True,
                        "unit": True,
                    },
                    "shadow_enabled": True,
                },
                "config_source": (
                    "profile/dependent_atomspace_transport_operation_shadow.yaml"),
                "manifest": {
                    "capabilities": {
                        "transport_operation_projection": "shadow-live",
                    },
                    "policy_authority": False,
                    "transport_operation_intents": {
                        "intents_by_seed": {"104729": [{"founder_unit_id": 102}]},
                        "mode": "diagnostic-configured-shadow-only",
                        "policy_authority": False,
                        "schema_version": "1.0",
                    },
                },
                "manifest_source": (
                    "profile/fdas_manifest_transport_operation_shadow.json"),
            },
            "seed": 104729,
            "source": source,
        })
        claims = tuple({
            "resource": {"kind": kind},
            "source_operation_id": OPERATION_ID,
        } for kind in (
            "action_budget", "actor", "move_points", "tile_occupancy",
            "transport_seat"))
        events = (
            _event("e1", "operation_projected", {
                "details": {"operation_id": OPERATION_ID}}),
            _event("e2", "operation_reserved", _operation_payload(
                "reserved", "grounded-current-transport-step-reserved", claims),
                caused_by=("e1",)),
            _event("e3", "operation_step_selected", _operation_payload(
                "step_selected", "next-transport-step-grounded-and-reserved",
                claims), caused_by=("e2",)),
            _event("e4", "operation_abandoned", _operation_payload(
                "abandoned", "required-founder-removed", ()),
                caused_by=("e3",)),
            _event("e5", "action_sent", {"action": {"action_type": "end_turn"}}),
            _event("e6", "action_result", {"status": "accepted"}),
            _event("e7", "metric_sample", {
                "name": "fdas_projection_latency_ms", "value": 10}),
            _event("e8", "metric_sample", {
                "name": "turn_full_loop_latency_ms", "value": 100}),
            _event("e9", "run_completed", {"summary": {"horizon_reached": True}}),
        )
        (directory / "events.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in events),
            encoding="utf-8")
        _write_json(directory / "status.json", {
            "completed": True,
            "engine_actions": 1,
            "fdas_authority_actions": 0,
            "fdas_transport_action_matches": 0,
            "fdas_transport_completions": 0,
            "fdas_transport_failures": 1,
            "fdas_transport_operations": 1,
            "fdas_transport_reconciliations": 3,
            "horizon_reached": True,
            "operation_authority_actions": 0,
            "rejected_actions": 0,
        })
        lifecycle = {
            "assemblies": [{
                "intent": {"founder_unit_id": 102},
            }],
            "controller_identity": "freeciv-founder-transport-lifecycle/1.0",
            "operation_store": {
                "quarantine_reason": None,
                "records": [{
                    "progress": {
                        "state": "abandoned",
                        "terminal_reason": "required-founder-removed",
                    },
                    "spec": {"operation_id": OPERATION_ID},
                }],
            },
            "policy_authority": False,
            "schema_version": 1,
            "shadow_only": True,
        }
        lifecycle["lifecycle_digest"] = structural_hash(lifecycle)
        _write_json(directory / "fdas-transport-lifecycle.json", lifecycle)
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


def test_transport_operation_live_audit_accepts_fail_closed_pair(tmp_path):
    _fixture(tmp_path)

    report = audit_fdas_transport_operation_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["operations"] == 2
    assert report["summary"]["action_matches"] == 0
    assert "no action-match" in report["claim_scope"]


def test_transport_operation_live_audit_rejects_authority_leak(tmp_path):
    _fixture(tmp_path)
    path = (tmp_path / "games" / "impact_pair" / COHORT / "treatment"
            / "e_full_loop" / "104729-00" / "events.jsonl")
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    rows[1]["payload"]["policy_authority"] = True
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")

    report = audit_fdas_transport_operation_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    treatment = next(row for row in report["arms"] if row["arm"] == "treatment")
    assert treatment["acceptance"]["checks"][
        "operation_shadow_events_are_non_authorizing"] is False


def test_transport_operation_live_audit_rejects_lifecycle_corruption(tmp_path):
    _fixture(tmp_path)
    path = (tmp_path / "games" / "impact_pair" / COHORT / "baseline"
            / "e_full_loop" / "104729-00" / "fdas-transport-lifecycle.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    value["operation_store"]["records"][0]["progress"]["state"] = "completed"
    _write_json(path, value)

    report = audit_fdas_transport_operation_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    baseline = next(row for row in report["arms"] if row["arm"] == "baseline")
    assert baseline["acceptance"]["checks"][
        "lifecycle_bundle_is_canonical_and_unquarantined"] is False
