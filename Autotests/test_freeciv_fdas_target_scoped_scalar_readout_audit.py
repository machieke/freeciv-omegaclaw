import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_target_scoped_scalar_readout import (  # noqa: E402
    _target_gates,
)
from audit_fdas_safe_filtered_scalar_readout import (  # noqa: E402
    _validate_target_filter,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402


def test_target_filter_audit_accepts_exact_partition():
    rows = [
        {
            "action_key": "action-a",
            "operation_id": "operation-a",
            "operation_type": "move",
            "scope_failures": [],
            "status": "in-scope",
            "target_ref": "city:3",
        },
        {
            "action_key": "action-b",
            "operation_id": "operation-b",
            "operation_type": "move",
            "scope_failures": ["target-ref-mismatch"],
            "status": "out-of-scope",
            "target_ref": "city:4",
        },
    ]
    rows = [dict(value, result_hash=structural_hash(value)) for value in rows]
    semantic = {
        "action_selection_changed": False,
        "baseline_operation_id": "operation-a",
        "baseline_operation_type": "move",
        "baseline_target_ref": "city:3",
        "candidate_surface_preserved": True,
        "calibrated_union_input_filtered": True,
        "eligible_operation_ids": [],
        "identity": "fdas-target-scoped-candidate-filter/1.0",
        "in_scope_operation_ids": ["operation-a"],
        "input_candidate_count": 2,
        "out_of_scope_operation_ids": ["operation-b"],
        "policy_authority": False,
        "readout_authority": False,
        "readouts": rows,
        "revision_id": "revision-test",
        "snapshot_id": "snapshot-test",
        "truth_mutated": False,
    }
    semantic.pop("eligible_operation_ids")
    details = dict(semantic, result_hash=structural_hash(semantic))

    errors, measures = _validate_target_filter(details, {
        "revision_id": "revision-test",
        "snapshot_id": "snapshot-test",
    })

    assert errors == ()
    assert measures == {
        "evaluations": 1,
        "in_scope": 1,
        "inputs": 2,
        "out_of_scope": 1,
        "singleton_surfaces": 1,
    }


def test_target_scoped_gates_require_real_grounded_alternative():
    parent = {
        "passed": True,
        "totals": {
            "readout_grounded_alternatives": 1,
            "target_filter_evaluations": 3,
            "target_filter_in_scope": 4,
            "target_filter_out_of_scope": 2,
            "union_additions": 1,
        },
        "games": [{"measures": {
            "readout_grounded_alternatives": 1,
        }}],
    }

    gates, games, surfaces = _target_gates(parent)

    assert all(gates.values())
    assert games == 1
    assert surfaces == 1


def test_target_scoped_gates_reject_singleton_only_surfaces():
    parent = {
        "passed": True,
        "totals": {
            "readout_grounded_alternatives": 0,
            "target_filter_evaluations": 3,
            "target_filter_in_scope": 3,
            "target_filter_out_of_scope": 2,
            "union_additions": 0,
        },
        "games": [{"measures": {
            "readout_grounded_alternatives": 0,
        }}],
    }

    gates, _games, surfaces = _target_gates(parent)

    assert gates["multi_candidate_target_scope_observed"] is False
    assert gates["grounded_same_target_alternative_observed"] is False
    assert gates["additions_only_recall_observed"] is False
    assert surfaces == 0
