import json

from freeciv.harness.fdas_induction_live import audit_fdas_induction_live
from freeciv_agent.events.schema import structural_hash


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _event(seq, event_type, payload, caused_by=()):
    return {
        "caused_by": list(caused_by),
        "event_id": "e{}".format(seq),
        "game_id": "induction-live-test",
        "payload": payload,
        "schema_version": "1.0",
        "seq": seq,
        "ts": "2026-08-02T00:00:00Z",
        "turn": seq,
        "type": event_type,
    }


def _ledger(status="quarantined"):
    proposal_id = "induced-test-proposal"
    material = {
        "identity": "induction-live-test",
        "proposals": {
            proposal_id: {
                "proposal": {"proposal_id": proposal_id},
                "status": status,
                "validation_ids": [],
            },
        },
        "schema_version": "1.0",
        "validations": {},
    }
    material["state_hash"] = structural_hash(material)
    return material


def _fixture(tmp_path):
    _write_json(tmp_path / "manifest.json", {
        "dependent_atomspace": {
            "config": {
                "learning": {
                    "contextual_conductance_enabled": True,
                    "episode_attribution_enabled": True,
                    "induced_rule_readout_enabled": False,
                    "induction_enabled": True,
                },
            },
            "config_source": (
                "profile/dependent_atomspace_defense_induction_shadow.yaml"),
            "manifest": {"capabilities": {
                "episode_induction_bridge": "shadow-live",
                "induced_rule_heldout_gate": "component-only",
                "quarantined_contextual_induction": "shadow-live",
            }},
            "manifest_source": (
                "profile/fdas_manifest_defense_induction_shadow.json"),
        },
        "source": {
            "commit": "a" * 40,
            "dirty": False,
            "implementation_sha256": "b" * 64,
        },
    })
    _write_json(tmp_path / "fdas-decision-episodes.json", {
        "episodes": [
            {"episode_id": "episode-1",
             "outcome_status": "goal-relief-observed"},
            {"episode_id": "episode-2",
             "outcome_status": "no-effect-observed"},
        ],
        "quarantine_reason": None,
    })
    _write_json(tmp_path / "fdas-induction-ledger.json", _ledger())
    _write_json(tmp_path / "status.json", {
        "completed": True,
        "engine_actions": 1,
        "fdas_induction_duplicate_proposals": 0,
        "fdas_induction_episode_abstentions": 0,
        "fdas_induction_episodes_encoded": 2,
        "fdas_induction_promoted_rules": 0,
        "fdas_induction_proposals_quarantined": 1,
        "horizon_reached": True,
        "rejected_actions": 0,
    })
    events = (
        _event(1, "metric_sample", {
            "labels": {
                "accepted_encodings": "1",
                "abstained_encodings": "0",
                "policy_authority": "False",
                "truth_mutated": "False",
            },
            "name": "fdas_episode_induction_latency_ms",
            "value": 3.0,
        }, caused_by=("source-1",)),
        _event(2, "metric_sample", {
            "labels": {
                "accepted_encodings": "1",
                "abstained_encodings": "0",
                "policy_authority": "False",
                "truth_mutated": "False",
            },
            "name": "fdas_episode_induction_latency_ms",
            "value": 2.0,
        }, caused_by=("source-2",)),
        _event(3, "induced_rule_quarantined", {"details": {
            "policy_authority": False,
            "proposal_id": "induced-test-proposal",
            "status": "quarantined",
            "truth_mutated": False,
        }}, caused_by=("e2",)),
        _event(4, "action_sent", {"action": {"action_type": "end_turn"}}),
        _event(5, "action_result", {"status": "accepted"}, caused_by=("e4",)),
    )
    (tmp_path / "events.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in events),
        encoding="utf-8")


def test_induction_live_audit_accepts_quarantine_only_evidence(tmp_path):
    _fixture(tmp_path)

    report = audit_fdas_induction_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["attributable_episodes"] == 2
    assert report["summary"]["proposals_quarantined"] == 1
    assert report["summary"]["rules_promoted"] == 0


def test_induction_live_audit_rejects_promoted_rule(tmp_path):
    _fixture(tmp_path)
    _write_json(tmp_path / "fdas-induction-ledger.json", _ledger("promoted"))

    report = audit_fdas_induction_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    assert report["acceptance"]["checks"][
        "ledger_is_hash_valid_and_quarantine_only"] is False


def test_induction_live_audit_rejects_policy_authority(tmp_path):
    _fixture(tmp_path)
    path = tmp_path / "events.jsonl"
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    rows[0]["payload"]["labels"]["policy_authority"] = "True"
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")

    report = audit_fdas_induction_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    assert report["acceptance"]["checks"][
        "induction_evaluations_are_causal_and_bounded"] is False


def test_induction_live_audit_rejects_corrupted_ledger_hash(tmp_path):
    _fixture(tmp_path)
    ledger = _ledger()
    ledger["state_hash"] = "0" * 64
    _write_json(tmp_path / "fdas-induction-ledger.json", ledger)

    report = audit_fdas_induction_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    assert report["acceptance"]["checks"][
        "ledger_is_hash_valid_and_quarantine_only"] is False
