import copy
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_grounded_transition_candidate_readout import (  # noqa: E402
    CALIBRATION_ARTIFACT_HASH,
    CONFIRMATION_REPORT_HASH,
    MODEL_RESULT_HASH,
    MOVE_OPERATION_TYPE,
    _completed_endpoint,
    _validate_union,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402


def _details():
    semantic = {
        "abstained_operation_ids": [],
        "action_selection_changed": False,
        "baseline_selected_operation_id": "operation-1",
        "calibrated_added_operation_ids": [],
        "calibrated_per_action": 1,
        "capacity_solver_enabled": False,
        "flow_advection_enabled": False,
        "identity": "fdas-calibrated-candidate-union/1.0",
        "maximum_interval_width": 0.55,
        "members": [{
            "operation_id": "operation-1",
            "reasons": [
                "calibrated-transition-recall",
                "scalar-top-k",
                "scalar-winner",
            ],
        }],
        "model_result_hash": MODEL_RESULT_HASH,
        "policy_authority": False,
        "readout_authority": False,
        "readouts": [{
            "action_key": "action-1",
            "baseline_priority": 0.0,
            "baseline_rank": 1,
            "effective_lineages": 7,
            "eligible_for_calibrated_recall": True,
            "eligibility_reason": "supported-calibrated-transition",
            "estimate": 0.6,
            "interval_lower": 0.4,
            "interval_upper": 0.8,
            "interval_width": 0.4,
            "operation_id": "operation-1",
            "operation_type": MOVE_OPERATION_TYPE,
            "prediction_reason": "route-lifecycle-estimate",
            "prediction_result_hash": "prediction-hash",
            "prediction_status": "estimated",
        }],
        "revision_id": "fdas-revision-test",
        "scalar_final_score_authority": True,
        "scalar_top_k": 1,
        "snapshot_id": "snapshot-test",
        "truth_mutated": False,
    }
    details = dict(semantic)
    details["result_hash"] = structural_hash(semantic)
    details["calibration_artifact_hash"] = CALIBRATION_ARTIFACT_HASH
    details["calibration_model_kind"] = "grounded-transition"
    details["confirmation_report_hash"] = CONFIRMATION_REPORT_HASH
    return details


def _rehash(details):
    semantic = copy.deepcopy(details)
    for name in (
            "calibration_artifact_hash", "calibration_model_kind",
            "confirmation_report_hash", "result_hash"):
        semantic.pop(name)
    details["result_hash"] = structural_hash(semantic)


def test_grounded_transition_union_accepts_candidate_specific_estimate():
    errors, measures = _validate_union(_details(), {
        "revision_id": "fdas-revision-test",
        "snapshot_id": "snapshot-test",
    })

    assert errors == ()
    assert measures == {
        "abstentions": 0,
        "additions": 0,
        "broad_backoff_predictions": 0,
        "candidate_specific_predictions": 1,
        "estimated_predictions": 1,
        "members": 1,
        "readouts": 1,
        "union_events": 1,
    }


def test_grounded_transition_union_rejects_rehashed_authority_change():
    details = _details()
    details["readout_authority"] = True
    _rehash(details)

    errors, _measures = _validate_union(details, {
        "revision_id": "fdas-revision-test",
        "snapshot_id": "snapshot-test",
    })

    assert "shadow-authority-differs" in errors


def test_grounded_transition_union_rejects_unbound_model_kind():
    details = _details()
    details["calibration_model_kind"] = "action-lifecycle"

    errors, _measures = _validate_union(details, {
        "revision_id": "fdas-revision-test",
        "snapshot_id": "snapshot-test",
    })

    assert "calibration-model-kind-differs" in errors


def test_grounded_transition_completion_accepts_declared_endpoints():
    horizon = {
        "completed": True,
        "horizon_reached": True,
        "infrastructure_failure": False,
        "terminal_game_over": False,
        "terminal_player_elimination": False,
    }
    eliminated = dict(horizon)
    eliminated.update({
        "horizon_reached": False,
        "terminal_player_elimination": True,
    })
    failed = dict(eliminated)
    failed["infrastructure_failure"] = True

    assert _completed_endpoint(horizon) is True
    assert _completed_endpoint(eliminated) is True
    assert _completed_endpoint(failed) is False
