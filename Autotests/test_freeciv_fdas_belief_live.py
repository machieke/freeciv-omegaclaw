import json

from freeciv.harness.fdas_belief_live import (
    COHORT,
    REQUIRED_PREDICATES,
    audit_fdas_belief_live,
)


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _event(seq, event_type, payload, caused_by=()):
    return {
        "caused_by": list(caused_by),
        "event_id": "e{}".format(seq),
        "game_id": "belief-live-test",
        "payload": payload,
        "schema_version": "1.0",
        "seq": seq,
        "ts": "2026-08-02T00:00:00Z",
        "turn": 2,
        "type": event_type,
    }


def _atom(predicate="opponent-present", confidence=0.8):
    return {
        "args": ["2"],
        "atom_id": "belief-test",
        "crisp": False,
        "predicate": predicate,
        "provenance_ids": ["visible-opponent"],
        "tv": {"confidence": confidence, "strength": 1.0},
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
            / "e_full_loop" / "271828-00")
        _write_json(directory / "manifest.json", {
            "dependent_atomspace": {
                "config": {
                    "authority_enabled": False,
                    "domain_authority": {"research": False},
                    "enabled": True,
                    "projection": {
                        "beliefs": True,
                        "empire": True,
                        "world": True,
                    },
                    "shadow_enabled": True,
                },
                "config_source": "profile/dependent_atomspace_belief_shadow.yaml",
                "manifest": {
                    "capabilities": {
                        "belief_domain_projection": "shadow-live",
                        "observation_pressure_planning": "component-only",
                    },
                    "policy_authority": False,
                },
                "manifest_source": "profile/fdas_manifest_belief_shadow.json",
            },
            "source": source,
        })
        events = [
            _event(1, "observation", {"atom": _atom()}),
            _event(2, "revision", {
                "operation": "apply",
                "target_atom": _atom(confidence=0.9),
            }, caused_by=("e1",)),
            _event(3, "revision", {
                "formula": {"name": "linear-window"},
                "operation": "decay",
                "posterior_tv": {"confidence": 0.8},
                "prior_tv": {"confidence": 0.9},
                "provenance_id": "revision-decay",
                "target_atom": _atom(),
            }, caused_by=("e2",)),
            _event(4, "scope_materialized", {
                "details": {"scope_kind": "opponent-belief"}}),
        ]
        for index, predicate in enumerate(sorted(REQUIRED_PREDICATES), 5):
            events.append(_event(index, "atom_rederived", {
                "details": {"predicate": predicate}}))
        events.extend((
            _event(10, "atomspace_revision_committed", {"details": {
                "atom_count": 5, "support_count": 5}}),
            _event(11, "atom_invalidated", {
                "details": {"reason": "absent-from-current-committed-revision"}}),
            _event(12, "metric_sample", {
                "labels": {"cold_equivalent": "True", "cold_verified": "True"},
                "name": "fdas_projection_latency_ms", "value": 10}),
            _event(13, "metric_sample", {
                "labels": {},
                "name": "fdas_belief_rematerialization_latency_ms",
                "value": 2}),
            _event(14, "metric_sample", {
                "labels": {}, "name": "turn_full_loop_latency_ms", "value": 100}),
            _event(15, "action_sent", {"action": {"action_type": "end_turn"}}),
            _event(16, "action_result", {"status": "accepted"}),
            _event(17, "run_completed", {"summary": {"horizon_reached": True}}),
        ))
        (directory / "events.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in events),
            encoding="utf-8")
        _write_json(directory / "status.json", {
            "completed": True,
            "engine_actions": 1,
            "fdas_authority_actions": 0,
            "fdas_belief_decay_revisions": 1,
            "fdas_belief_rematerializations": 1,
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


def test_belief_live_audit_accepts_uncertain_decay_pair(tmp_path):
    _fixture(tmp_path)

    report = audit_fdas_belief_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["observations"] == 2
    assert report["summary"]["decay_revisions"] == 2
    assert report["summary"]["conflicts"] == 0


def test_belief_live_audit_rejects_invented_absence(tmp_path):
    _fixture(tmp_path)
    path = (tmp_path / "games" / "impact_pair" / COHORT / "treatment"
            / "e_full_loop" / "271828-00" / "events.jsonl")
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    rows[0]["payload"]["atom"]["predicate"] = "opponent-absent"
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")

    report = audit_fdas_belief_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    treatment = next(row for row in report["arms"] if row["arm"] == "treatment")
    assert treatment["acceptance"]["checks"][
        "expired_support_is_invalidated_not_negated"] is False


def test_belief_live_audit_rejects_nonmonotone_decay(tmp_path):
    _fixture(tmp_path)
    path = (tmp_path / "games" / "impact_pair" / COHORT / "baseline"
            / "e_full_loop" / "271828-00" / "events.jsonl")
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    rows[2]["payload"]["posterior_tv"]["confidence"] = 1.0
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")

    report = audit_fdas_belief_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    baseline = next(row for row in report["arms"] if row["arm"] == "baseline")
    assert baseline["acceptance"]["checks"][
        "decay_is_explicit_causal_and_monotone"] is False
