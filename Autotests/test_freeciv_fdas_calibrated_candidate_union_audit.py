import copy
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_calibrated_candidate_union import (  # noqa: E402
    CALIBRATION_ARTIFACT_HASH,
    CONFIRMATION_REPORT_HASH,
    MODEL_RESULT_HASH,
    _validate_union,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402


def _details():
    semantic = {
        "abstained_operation_ids": ["operation-1"],
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
            "reasons": ["scalar-top-k", "scalar-winner"],
        }],
        "model_result_hash": MODEL_RESULT_HASH,
        "policy_authority": False,
        "readout_authority": False,
        "readouts": [{
            "action_key": "action-1",
            "baseline_priority": 0.0,
            "baseline_rank": 1,
            "effective_lineages": 3,
            "eligible_for_calibrated_recall": False,
            "eligibility_reason": "prediction-interval-too-wide",
            "estimate": 0.5,
            "interval_lower": 0.1,
            "interval_upper": 0.9,
            "interval_width": 0.8,
            "operation_id": "operation-1",
            "operation_type": (
                "fdas-shadow:city-garrison-deficit:unit_move"),
            "prediction_reason": "lifecycle-stratum-estimate",
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
    details["confirmation_report_hash"] = CONFIRMATION_REPORT_HASH
    return details


def test_candidate_union_audit_accepts_wide_interval_abstention():
    details = _details()
    errors, measures = _validate_union(details, {
        "revision_id": "fdas-revision-test",
        "snapshot_id": "snapshot-test",
    })

    assert errors == ()
    assert measures == {
        "abstentions": 1,
        "additions": 0,
        "eligible_readouts": 0,
        "members": 1,
        "mixed_action": False,
        "readouts": 1,
    }


def test_candidate_union_audit_rejects_rehashed_authority_change():
    details = _details()
    details["action_selection_changed"] = True
    semantic = copy.deepcopy(details)
    semantic.pop("calibration_artifact_hash")
    semantic.pop("confirmation_report_hash")
    semantic.pop("result_hash")
    details["result_hash"] = structural_hash(semantic)

    errors, _measures = _validate_union(details, {
        "revision_id": "fdas-revision-test",
        "snapshot_id": "snapshot-test",
    })

    assert "shadow-authority-differs" in errors
