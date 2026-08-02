import json

from freeciv.harness.fdas_transport_live import audit_fdas_transport_live


COHORT = "fdas_transport_shadow_diagnostic_v1"
PROXY = (
    "26ba7124249f34fd3050ef29bf191bd4d8808018+patch-sha256:"
    "d8f586ad5741106beb23b24c3e5f599fd74cb8e1b0f0a33961f2c966e66fe7d4")
PREDICATES = (
    "transport-accepts-unit-class", "transport-backed-by-unit",
    "transport-cargo-compatible", "transport-compatible-founder",
    "transport-seat-available", "transport-seat-resource",
    "unit-ruleset-founder-capable",
)


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _event(seq, event_type, payload):
    return {
        "caused_by": [], "event_id": "e{}".format(seq),
        "game_id": "transport-live-test", "payload": payload,
        "schema_version": "1.0", "seq": seq,
        "ts": "2026-08-02T00:00:00Z", "turn": 30, "type": event_type,
    }


def _fixture(tmp_path):
    source = {
        "commit": "a" * 40, "dirty": False,
        "implementation_sha256": "b" * 64,
    }
    for arm in ("baseline", "treatment"):
        directory = (tmp_path / "games" / "impact_pair" / COHORT / arm
                     / "e_full_loop" / "104729-00")
        _write_json(directory / "manifest.json", {
            "dependent_atomspace": {
                "config": {
                    "authority_enabled": False,
                    "domain_authority": {"transport": False},
                    "enabled": True,
                    "projection": {
                        "operations": False, "ruleset": True,
                        "transport": True, "unit": True,
                    },
                    "shadow_enabled": True,
                },
                "config_source": "profile/dependent_atomspace_transport_shadow.yaml",
                "manifest": {
                    "capabilities": {
                        "transport_capability_projection": "shadow-live",
                        "transport_operation_projection": "component-only",
                    },
                    "policy_authority": False, "status": "shadow-live",
                },
                "manifest_source": "profile/fdas_manifest_transport_shadow.json",
            },
            "engine": {"proxy_commit": PROXY},
            "release_game_config": {"startunits": "csdf"},
            "source": source,
        })
        _write_json(directory / "status.json", {
            "completed": True, "engine_actions": 1,
            "horizon_reached": True, "rejected_actions": 0,
        })
        events = [
            _event(1, "scope_materialized", {
                "details": {"atom_count": 8, "scope_kind": "transport"}}),
        ]
        events.extend(
            _event(index + 2, "atom_rederived", {
                "details": {"predicate": predicate}})
            for index, predicate in enumerate(PREDICATES))
        events.extend((
            _event(10, "action_sent", {
                "action_id": "action-1", "action": {"action_type": "end_turn"}}),
            _event(11, "action_result", {
                "action_id": "action-1", "status": "accepted"}),
            _event(12, "metric_sample", {
                "labels": {"cold_equivalent": "True", "cold_verified": "True"},
                "name": "fdas_projection_latency_ms", "value": 20}),
            _event(13, "metric_sample", {
                "labels": {}, "name": "fdas_shadow_evaluation_latency_ms",
                "value": 2}),
            _event(14, "metric_sample", {
                "labels": {}, "name": "turn_full_loop_latency_ms", "value": 100}),
            _event(15, "run_completed", {"summary": {
                "fdas_authority_actions": 0, "horizon_reached": True,
                "operation_authority_actions": 0,
            }}),
        ))
        (directory / "events.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in events),
            encoding="utf-8")
    _write_json(tmp_path / "impact-aggregate.json", {
        "claim_evaluation": {"status": "ineligible"},
        "complete_pairs": 1,
        "design": {"claim_eligible": False, "cohort": COHORT},
        "failures": [],
        "source_freeze": {"passed": True},
    })
    _write_json(tmp_path / "impact-run-summary.json", {
        "completed": 2, "infrastructure_failures": 0, "source_stable": True,
    })


def test_transport_live_audit_accepts_corrected_capability_pair(tmp_path):
    _fixture(tmp_path)

    report = audit_fdas_transport_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["transport_scopes"] == 2
    assert report["summary"]["accepted_action_results"] == 2


def test_transport_live_audit_rejects_missing_seat_readout(tmp_path):
    _fixture(tmp_path)
    path = (tmp_path / "games" / "impact_pair" / COHORT / "treatment"
            / "e_full_loop" / "104729-00" / "events.jsonl")
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    rows = [row for row in rows if not (
        row["type"] == "atom_rederived"
        and row["payload"].get("details", {}).get("predicate")
        == "transport-seat-available")]
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")

    report = audit_fdas_transport_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    treatment = next(row for row in report["arms"] if row["arm"] == "treatment")
    assert treatment["acceptance"]["checks"][
        "seat_capacity_is_present_for_every_transport_scope"] is False
