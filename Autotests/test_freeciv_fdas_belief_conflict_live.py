import json

from freeciv.harness.fdas_belief_conflict_live import (
    COHORT,
    REQUIRED_PREDICATES,
    audit_fdas_belief_conflict_live,
)


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _event(seq, event_type, payload, caused_by=()):
    return {
        "caused_by": list(caused_by),
        "event_id": "e{}".format(seq),
        "game_id": "belief-conflict-test",
        "payload": payload,
        "schema_version": "1.0",
        "seq": seq,
        "ts": "2026-08-02T00:00:00Z",
        "turn": 1,
        "type": event_type,
    }


def _atom(predicate, provenance, strength, confidence, arguments):
    return {
        "args": list(arguments),
        "atom_id": "belief-alphabet",
        "crisp": False,
        "predicate": predicate,
        "provenance_ids": list(provenance),
        "tv": {"confidence": confidence, "strength": strength},
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
            / "e_full_loop" / "161803-00")
        _write_json(directory / "manifest.json", {
            "dependent_atomspace": {
                "config": {
                    "authority_enabled": False,
                    "domain_authority": {"research": False},
                    "projection": {"beliefs": True},
                },
                "config_source": (
                    "profile/dependent_atomspace_belief_conflict_shadow.yaml"),
                "manifest": {
                    "belief_conflict_diagnostic": {
                        "apply_all_context_quarantines": True,
                        "conflict_min_confidence": 0.5,
                        "conflict_severity_threshold": 0.25,
                        "mode": "model-prior-versus-visible-roster-shadow",
                        "model_id": "fdas-opponent-presence-prior",
                        "model_version": "1.0",
                        "policy_authority": False,
                        "prior_confidence": 0.6,
                        "prior_strength": 0.0,
                        "target_predicate": "opponent-present",
                    },
                    "capabilities": {
                        "belief_conflict_quarantine": "shadow-live"},
                    "policy_authority": False,
                },
                "manifest_source": (
                    "profile/fdas_manifest_belief_conflict_shadow.json"),
            },
            "source": source,
        })
        prior_atom = _atom(
            "opponent-present", ("prior",), 0.0, 0.6, ("any",))
        observed_atom = _atom(
            "opponent-present", ("visible",), 1.0, 0.9, ("any",))
        aggregate_atom = _atom(
            "opponent-present", ("prior", "visible"), 0.58, 0.9,
            ("any",))
        events = [
            _event(1, "metric_sample", {
                "labels": {"declaration": "fdas_diagnostic_override"},
                "name": "belief_conflict_min_confidence",
                "unit": "ratio", "value": 0.5}),
            _event(2, "metric_sample", {
                "labels": {"declaration": "fdas_diagnostic_override"},
                "name": "belief_conflict_severity_threshold",
                "unit": "ratio", "value": 0.25}, caused_by=("e1",)),
            _event(3, "observation", {
                "age_turns": 0,
                "atom": prior_atom,
                "model_provenance": {
                    "confidence_cap": 0.6,
                    "exact": False,
                    "model_hash": "c" * 64,
                    "model_id": "fdas-opponent-presence-prior",
                    "model_version": "1.0",
                    "source_kind": "simulator",
                },
                "observation_id": "prior-observation",
                "provenance_id": "prior",
                "source": "simulator",
                "source_lineage_id": "simulator-model:prior:1",
            }, caused_by=("e2",)),
            _event(4, "revision", {
                "evidence_tv": {"confidence": 0.6, "strength": 0.0},
                "formula": {"inputs": {}, "name": "provenance-union"},
                "operation": "apply",
                "posterior_tv": {"confidence": 0.6, "strength": 0.0},
                "prior_tv": None,
                "provenance_id": "prior",
                "target_atom": prior_atom,
            }, caused_by=("e3",)),
            _event(5, "observation", {
                "age_turns": 0,
                "atom": observed_atom,
                "observation_id": "visible-observation",
                "provenance_id": "visible",
                "source": "player-visible-roster-packet",
                "source_lineage_id": "player-visible-roster-packet:game:2",
            }, caused_by=("e4",)),
            _event(6, "revision", {
                "evidence_tv": {"confidence": 0.9, "strength": 1.0},
                "formula": {"inputs": {
                    "selection_factor": 1,
                    "unique_provenance": 2,
                }, "name": "provenance-union"},
                "operation": "apply",
                "posterior_tv": {"confidence": 0.9, "strength": 0.58},
                "prior_tv": {"confidence": 0.6, "strength": 0.0},
                "provenance_id": "visible",
                "target_atom": aggregate_atom,
            }, caused_by=("e5",)),
            _event(7, "belief_conflict", {
                "conflict_atom": _atom(
                    "Conflict", ("prior", "visible"), 0.46, 0.6,
                    ("belief-alphabet", ["prior"], ["visible"])),
                "conflict_id": "conflict-alphabet",
                "context_ids": ["context-prior", "context-visible"],
                "detected_turn": 1,
                "left_provenance_ids": ["prior"],
                "left_source_lineage_ids": ["simulator-model:prior:1"],
                "left_tv": {"confidence": 0.6, "strength": 0.0},
                "overlap": 0.0,
                "right_provenance_ids": ["visible"],
                "right_source_lineage_ids": [
                    "player-visible-roster-packet:game:2"],
                "right_tv": {"confidence": 0.9, "strength": 1.0},
                "severity": 0.46,
                "target_atom_id": "belief-alphabet",
            }, caused_by=("e6",)),
            _event(8, "context_quarantine", {
                "conflict_id": "conflict-alphabet",
                "context_id": "context-prior",
                "excluded_provenance_ids": ["visible"],
                "operation_id": "quarantine-prior",
                "reason": "provenance-distinct conflicting context",
                "retained_provenance_ids": ["prior"],
                "target_atom_id": "belief-alphabet",
                "turn": 1,
            }, caused_by=("e7",)),
            _event(9, "context_quarantine", {
                "conflict_id": "conflict-alphabet",
                "context_id": "context-visible",
                "excluded_provenance_ids": ["prior"],
                "operation_id": "quarantine-visible",
                "reason": "provenance-distinct conflicting context",
                "retained_provenance_ids": ["visible"],
                "target_atom_id": "belief-alphabet",
                "turn": 1,
            }, caused_by=("e8",)),
        ]
        seq = 10
        for predicate in sorted(REQUIRED_PREDICATES):
            events.append(_event(seq, "atom_rederived", {
                "details": {"predicate": predicate}}, caused_by=("e9",)))
            seq += 1
        events.append(_event(seq, "atom_rederived", {
            "details": {"predicate": "belief-conflict-lineage"}},
            caused_by=("e9",)))
        seq += 1
        events.extend((
            _event(seq, "action_sent", {
                "action": {"action_type": "end_turn"}}),
            _event(seq + 1, "action_result", {"status": "accepted"},
                   caused_by=("e{}".format(seq),)),
            _event(seq + 2, "run_completed", {
                "summary": {"horizon_reached": True}}),
        ))
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "events.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in events),
            encoding="utf-8")
        _write_json(directory / "status.json", {
            "completed": True,
            "engine_actions": 1,
            "fdas_authority_actions": 0,
            "fdas_belief_conflict_model_priors": 1,
            "fdas_belief_conflicts_detected": 1,
            "fdas_belief_context_quarantines": 2,
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


def test_conflict_live_audit_accepts_independent_lineage_pair(tmp_path):
    _fixture(tmp_path)

    report = audit_fdas_belief_conflict_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["conflicts"] == 2
    assert report["summary"]["context_quarantines"] == 4


def test_conflict_live_audit_rejects_same_source_lineage(tmp_path):
    _fixture(tmp_path)
    path = (tmp_path / "games" / "impact_pair" / COHORT / "baseline"
            / "e_full_loop" / "161803-00" / "events.jsonl")
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    rows[6]["payload"]["right_source_lineage_ids"] = [
        "simulator-model:prior:1"]
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")

    report = audit_fdas_belief_conflict_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False


def test_conflict_live_audit_rejects_partial_context_quarantine(tmp_path):
    _fixture(tmp_path)
    path = (tmp_path / "games" / "impact_pair" / COHORT / "treatment"
            / "e_full_loop" / "161803-00" / "events.jsonl")
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    rows = [row for row in rows if row["event_id"] != "e9"]
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")

    report = audit_fdas_belief_conflict_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
