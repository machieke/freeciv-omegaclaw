import json
from types import SimpleNamespace

from freeciv.harness.engine_live import _emit_fdas_observation_pressure
from freeciv.harness.fdas_observation_live import (
    COHORT,
    MECHANISM,
    audit_fdas_observation_live,
)
from freeciv_agent.beliefs import BeliefKey, UncertainBelief
from freeciv_agent.events.writer import EventWriter


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _event(seq, event_type, payload, caused_by=()):
    return {
        "caused_by": list(caused_by),
        "event_id": "e{}".format(seq),
        "game_id": "observation-live-test",
        "payload": payload,
        "schema_version": "1.0",
        "seq": seq,
        "ts": "2026-08-02T00:00:00Z",
        "turn": 1,
        "type": event_type,
    }


def _packet_summary():
    decision_sensitivity = 0.16
    return {
        "evidence_count_after_planning": 1,
        "evidence_count_before_planning": 1,
        "evidence_registration_status": "awaiting-authoritative-return",
        "evidence_store_hash_after_planning": "d" * 64,
        "evidence_store_hash_before_planning": "d" * 64,
        "evidence_write_authorized": False,
        "information_values": [{
            "bounded_decision_analysis": {
                "decision_change_probability": decision_sensitivity,
                "decision_sensitive": True,
                "outcomes": [
                    {"changes_decision": False},
                    {"changes_decision": True},
                ],
            },
            "expected_information_gain": 0.08,
            "test": {
                "decision_sensitivity": decision_sensitivity,
                "model_provenance": {
                    "confidence_cap": 0.6,
                    "exact": False,
                    "source_kind": "simulator",
                },
            },
        }],
        "mechanism": MECHANISM,
        "packet_schedule": {
            "accounting": {
                "cpu": {"consumed": 1, "declared": 1, "stranded": 0},
                "observation": {
                    "consumed": 1, "declared": 1, "stranded": 0},
            },
            "committed_operation_ids": ["observe:refresh"],
            "conserved": True,
        },
        "policy_authority": False,
        "selected_operation_ids": ["observe:refresh"],
        "selection_effect_widening": {
            "configured_unknown_propensity_discount": 0.5,
            "propensity": None,
            "status": "required-on-authoritative-return",
        },
        "selection_records": [{
            "operation_id": "observe:refresh",
            "selected": True,
        }],
        "shadow_only": True,
        "truth_mutated": False,
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
            / "e_full_loop" / "314159-00")
        _write_json(directory / "manifest.json", {
            "beliefs": {
                "selection_unknown_discount": 0.5,
                "simulation_confidence_cap": 0.6,
            },
            "dependent_atomspace": {
                "config": {
                    "authority_enabled": False,
                    "enabled": True,
                    "inference": {"uncertain_assessment_enabled": True},
                    "projection": {"beliefs": True},
                    "shadow_enabled": True,
                },
                "config_source": (
                    "profile/dependent_atomspace_observation_pressure_shadow.yaml"),
                "manifest": {
                    "capabilities": {
                        "belief_domain_projection": "shadow-live",
                        "observation_pressure_planning": "shadow-live",
                    },
                    "policy_authority": False,
                },
                "manifest_source": (
                    "profile/fdas_manifest_observation_pressure_shadow.json"),
            },
            "source": source,
        })
        events = (
            _event(1, "pressure_propagated", {
                "config": {"mechanism": MECHANISM}}),
            _event(2, "operation_scored", {}, caused_by=("e1",)),
            _event(3, "packet_reserved", {
                "summary": _packet_summary()}, caused_by=("e2",)),
            _event(4, "metric_sample", {
                "name": "fdas_observation_pressure_latency_ms",
                "value": 3.0}, caused_by=("e3",)),
            _event(5, "action_sent", {
                "action": {"action_type": "end_turn"}}, caused_by=("e4",)),
            _event(6, "action_result", {
                "status": "accepted"}, caused_by=("e5",)),
        )
        (directory / "events.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in events),
            encoding="utf-8")
        _write_json(directory / "status.json", {
            "engine_actions": 1,
            "fdas_authority_actions": 0,
            "fdas_observation_pressure_decisions": 1,
            "fdas_observation_pressure_packet_commits": 1,
            "fdas_observation_pressure_selected": 1,
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


def _event_path(tmp_path, arm):
    return (tmp_path / "games" / "impact_pair" / COHORT / arm
            / "e_full_loop" / "314159-00" / "events.jsonl")


def test_observation_live_audit_accepts_non_authorizing_pair(tmp_path):
    _fixture(tmp_path)

    report = audit_fdas_observation_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["observation_pressure_decisions"] == 2
    assert report["summary"]["packet_commits"] == 2
    assert report["summary"]["selected_evidence_write_throughs"] == 0


def test_observation_live_audit_rejects_evidence_write_through(tmp_path):
    _fixture(tmp_path)
    path = _event_path(tmp_path, "treatment")
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    rows[2]["payload"]["summary"][
        "evidence_store_hash_after_planning"] = "e" * 64
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")

    report = audit_fdas_observation_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    treatment = next(row for row in report["arms"]
                     if row["arm"] == "treatment")
    assert treatment["acceptance"]["checks"][
        "evidence_firewall_remained_closed"] is False


def test_observation_live_audit_rejects_decision_insensitive_test(tmp_path):
    _fixture(tmp_path)
    path = _event_path(tmp_path, "baseline")
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    rows[2]["payload"]["summary"]["information_values"][0][
        "bounded_decision_analysis"]["decision_sensitive"] = False
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")

    report = audit_fdas_observation_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    baseline = next(row for row in report["arms"]
                    if row["arm"] == "baseline")
    assert baseline["acceptance"]["checks"][
        "bounded_decision_can_change"] is False


def test_engine_emits_schema_valid_observation_pressure_without_mutation(
        tmp_path):
    path = tmp_path / "events.jsonl"
    writer = EventWriter(str(path), "observation-emission", durable=False)
    root = writer.emit("metric_sample", 1, {
        "labels": {}, "name": "root", "unit": "ratio", "value": 1.0})
    belief = UncertainBelief(
        BeliefKey("opponent-present", ("2",)),
        1.0,
        0.85,
        ("visible-player",),
        (("visible-player",),),
        1)

    class ReadOnlyStore(object):
        evidence = ("visible-player",)
        artifact_hash = "f" * 64

    snapshot = SimpleNamespace(
        identity=SimpleNamespace(source_seq=7),
        snapshot_id="snapshot-1",
        turn=1)
    manifest = {
        "beliefs": {
            "selection_unknown_discount": 0.5,
            "simulation_confidence_cap": 0.6,
        },
        "dependent_atomspace": {"declaration_hash": "a" * 64},
        "condition_id": "e_full_loop",
        "game_id": "observation-emission",
        "ruleset": "civ2civ3",
        "track": "impact_pair",
    }

    parent, decision = _emit_fdas_observation_pressure(
        belief, snapshot, manifest, ReadOnlyStore(), writer,
        root["event_id"])

    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    assert rows[-1]["event_id"] == parent
    assert rows[-2]["type"] == "packet_reserved"
    assert rows[-2]["payload"]["summary"]["truth_mutated"] is False
    assert rows[-1]["payload"]["name"] == (
        "fdas_observation_pressure_latency_ms")
    assert decision["selected_operation_ids"]
