from copy import deepcopy
import json

from freeciv.harness.fdas_randomized_alternative_live import (
    ASSIGNMENT_IDENTITY,
    ASSIGNMENT_POLICY,
    ASSIGNMENT_UNIT,
    assignment_draw,
    assignment_material,
    audit_randomized_alternative_run,
    randomized_outcome_summary,
    wilson_interval,
)


def _event():
    return {
        "game_id": "game-randomized-audit",
        "turn": 17,
        "payload": {"details": {
            "arms": [
                {"arm": "control", "action_key": "control-action"},
                {"arm": "treatment", "action_key": "treatment-action"},
            ],
            "config": {
                "randomization_seed": 9341,
                "treatment_probability": 0.5,
            },
            "experiment_id": "randomized-audit-test",
            "identity": ASSIGNMENT_IDENTITY,
            "policy_version": ASSIGNMENT_POLICY,
            "status": "eligible-randomized-diagnostic",
        }},
    }


def test_assignment_audit_reconstructs_only_exogenous_material():
    event = _event()

    material = assignment_material(event)
    material_hash, draw = assignment_draw(event)

    assert material == {
        "assignment_unit": ASSIGNMENT_UNIT,
        "control_action_key": "control-action",
        "experiment_id": "randomized-audit-test",
        "game_id": "game-randomized-audit",
        "policy_version": ASSIGNMENT_POLICY,
        "randomization_seed": 9341,
        "treatment_action_key": "treatment-action",
        "turn": 17,
    }
    assert len(material_hash) == 64
    assert 0.0 <= draw < 1.0


def test_assignment_audit_ignores_arm_bookkeeping_but_not_action_identity():
    event = _event()
    changed = deepcopy(event)
    for arm in changed["payload"]["details"]["arms"]:
        arm.update({
            "commit_validation_hash": "changed-commit",
            "operation_id": "changed-operation",
            "pressure_evaluation_hash": "changed-pressure",
            "resource_packet_artifact_hash": "changed-packet",
        })

    assert assignment_draw(changed) == assignment_draw(event)

    changed["payload"]["details"]["arms"][1][
        "action_key"] = "different-treatment-action"
    assert assignment_draw(changed) != assignment_draw(event)


def test_randomized_summary_keeps_administrative_censoring_out_of_outcomes():
    rows = (
        {"assigned_arm": "control", "game_id": "game-1",
         "label_due_by_endpoint": True,
         "label_outcome": True, "label_status": "observed",
         "selection_propensity": 0.5},
        {"assigned_arm": "control", "game_id": "game-2",
         "label_due_by_endpoint": False,
         "label_outcome": None, "label_status": "pending",
         "selection_propensity": 0.5},
        {"assigned_arm": "treatment", "game_id": "game-3",
         "label_due_by_endpoint": True,
         "label_outcome": False, "label_status": "observed",
         "selection_propensity": 0.5},
    )

    summary = randomized_outcome_summary(rows)

    assert summary["arms"]["control"]["assigned"] == 2
    assert summary["arms"]["control"]["observed"] == 1
    assert summary["arms"]["control"]["positive"] == 1
    assert summary["arms"]["control"]["administratively_pending"] == 1
    assert summary["arms"]["control"]["assigned_games"] == 2
    assert summary["arms"]["control"]["effective_sample_size"] == 1.0
    assert summary["arms"]["control"]["observed_games"] == 1
    assert summary["arms"]["treatment"]["rate"] == 0.0
    assert summary["risk_difference"] == -1.0
    assert summary["unresolved_after_due"] == 0


def test_randomized_summary_distinguishes_overdue_from_administrative_pending():
    summary = randomized_outcome_summary(({
        "assigned_arm": "control",
        "game_id": "game-overdue",
        "label_due_by_endpoint": True,
        "label_outcome": None,
        "label_status": "pending",
        "selection_propensity": 0.5,
    },))

    assert summary["arms"]["control"]["administratively_pending"] == 0
    assert summary["unresolved_after_due"] == 1


def test_wilson_interval_is_bounded_and_rejects_invalid_counts():
    assert wilson_interval(0, 0) is None
    lower, upper = wilson_interval(5, 10)
    assert 0.0 < lower < 0.5 < upper < 1.0

    import pytest
    with pytest.raises(ValueError):
        wilson_interval(2, 1)


def test_run_audit_preserves_early_failed_game_as_rejected_row(tmp_path):
    game = tmp_path / "games" / "main" / "e_full_loop" / "123-00"
    game.mkdir(parents=True)
    (game / "manifest.json").write_text(json.dumps({
        "game_id": "failed-game-123",
        "seed": 123,
        "source": {
            "commit": "source-commit",
            "dirty": False,
            "implementation_sha256": "implementation-hash",
        },
    }), encoding="utf-8")
    (game / "status.json").write_text(json.dumps({
        "completed": False,
        "error": "ValueError: startup failed after manifest",
        "infrastructure_failure": True,
    }), encoding="utf-8")

    report = audit_randomized_alternative_run(
        str(tmp_path), expected_seeds=(123,),
        expected_source_commit="source-commit",
        expected_implementation_sha256="implementation-hash",
        allow_zero_assignment_games=True)

    assert report["passed"] is False
    assert report["assignments"] == 0
    assert report["assignment_events"] == 0
    assert report["gates"]["exact_expected_seeds_completed"] is True
    assert report["games"][0]["failure"]["missing_evidence"]
    assert report["games"][0]["gates"][
        "failed_game_is_preserved_not_completed"] is True
    assert report["games"][0]["gates"][
        "complete_randomized_evidence_present"] is False
