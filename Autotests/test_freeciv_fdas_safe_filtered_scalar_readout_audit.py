import copy
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_safe_filtered_scalar_readout import (  # noqa: E402
    _validate_filter,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402


def _row(operation_id, status, blockers, reason, source_atom_id):
    semantic = {
        "action_key": "action-" + operation_id,
        "action_type": "unit_move",
        "blockers": sorted(blockers),
        "operation_id": operation_id,
        "reason": reason,
        "source_atom_id": source_atom_id,
        "status": status,
    }
    return {**semantic, "result_hash": structural_hash(semantic)}


def _details():
    eligible = _row(
        "safe", "eligible", ("uncompiled-action-effect",), None,
        "deficit-atom-safe")
    excluded = _row(
        "unsafe", "excluded",
        ("protected-source-garrison", "uncompiled-action-effect"),
        "candidate-has-noncontractual-blockers", None)
    semantic = {
        "action_selection_changed": False,
        "calibrated_union_input_filtered": True,
        "candidate_surface_preserved": True,
        "eligible_operation_ids": ["safe"],
        "excluded_operation_ids": ["unsafe"],
        "identity": "fdas-decision-safe-candidate-filter/1.0",
        "input_candidate_count": 2,
        "policy_authority": False,
        "readout_authority": False,
        "readouts": [eligible, excluded],
        "revision_id": "revision-test",
        "snapshot_id": "snapshot-test",
        "truth_mutated": False,
    }
    return {**semantic, "result_hash": structural_hash(semantic)}


def test_safe_filter_audit_accepts_hash_bound_source_garrison_exclusion():
    errors, measures = _validate_filter(_details(), {
        "revision_id": "revision-test",
        "snapshot_id": "snapshot-test",
    })

    assert errors == ()
    assert measures == {
        "eligible": 1,
        "empty_surfaces": 0,
        "evaluations": 1,
        "excluded": 1,
        "inputs": 2,
        "source_garrison_exclusions": 1,
    }


def test_safe_filter_audit_rejects_rehashed_unsafe_eligibility():
    details = _details()
    details["readouts"][1]["status"] = "eligible"
    details["readouts"][1]["reason"] = None
    details["readouts"][1]["source_atom_id"] = "unsafe-source"
    row = copy.deepcopy(details["readouts"][1])
    row.pop("result_hash")
    details["readouts"][1]["result_hash"] = structural_hash(row)
    details["eligible_operation_ids"] = ["safe", "unsafe"]
    details["excluded_operation_ids"] = []
    semantic = copy.deepcopy(details)
    semantic.pop("result_hash")
    details["result_hash"] = structural_hash(semantic)

    errors, _measures = _validate_filter(details, {
        "revision_id": "revision-test",
        "snapshot_id": "snapshot-test",
    })

    assert "protected-source-garrison-became-eligible" in errors
