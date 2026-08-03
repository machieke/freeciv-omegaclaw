import copy
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_path_persistence_union import (  # noqa: E402
    MAXIMUM_REACHABILITY_REGRET,
    PERSISTENCE_CONFIG,
    _validate_path_persistence_union,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    PATH_PERSISTENCE_CANDIDATE_UNION_IDENTITY,
)


MOVE = "fdas-shadow:city-garrison-deficit:unit_move"


def _signal_ledger():
    uses = [{
        "model_id": None,
        "residualized": False,
        "signal_name": signal,
        "stage": "candidate_union",
        "transformation": "membership_only",
        "used_in_final_score": False,
    } for signal in (
        "corrected_bridge_overlap",
        "smoothed_corridor_reachability",
        "raw_route_momentum",
        "corridor_dwell_state",
    )]
    semantic = {
        "contract_version": "single-use-bridge-signals/1.0",
        "uses": uses,
    }
    return dict(semantic, ledger_hash=structural_hash(semantic))


def _details():
    first = "operation-1"
    second = "operation-2"
    semantic = {
        "action_selection_changed": False,
        "base_probe_operation_ids": [first],
        "baseline_selected_operation_id": first,
        "capacity_solver_enabled": False,
        "config": dict(PERSISTENCE_CONFIG),
        "expired_route_ids": ["fdas-path-corridor:expired"],
        "fallback_reason": None,
        "fallback_required": False,
        "flow_advection_enabled": False,
        "identity": PATH_PERSISTENCE_CANDIDATE_UNION_IDENTITY,
        "maximum_reachability_regret": MAXIMUM_REACHABILITY_REGRET,
        "members": [{
            "operation_id": first,
            "reasons": ["scalar-top-k", "scalar-winner"],
        }, {
            "operation_id": second,
            "reasons": ["path-persistence-recall"],
        }],
        "path_persistence_authority": False,
        "persistence_added_operation_ids": [second],
        "persistence_selected_operation_id": second,
        "persistence_selected_route_id": "fdas-path-corridor:second",
        "policy_authority": False,
        "probe_union_result_hash": "a" * 64,
        "reachability_regret": 0.05,
        "readout_authority": False,
        "readouts": [{
            "baseline_rank": 1,
            "dwell_bonus": 0.0,
            "instantaneous_reachability": 1.0,
            "operation_id": first,
            "operation_type": MOVE,
            "persistence_score": 1.0,
            "persistence_selected": False,
            "probe_member": True,
            "route_id": "fdas-path-corridor:first",
            "route_momentum": 0.0,
            "smoothed_reachability": 1.0,
        }, {
            "baseline_rank": 2,
            "dwell_bonus": 0.0,
            "instantaneous_reachability": 0.95,
            "operation_id": second,
            "operation_type": MOVE,
            "persistence_score": 1.0,
            "persistence_selected": True,
            "probe_member": False,
            "route_id": "fdas-path-corridor:second",
            "route_momentum": 0.0,
            "smoothed_reachability": 1.0,
        }],
        "regret_rejected": False,
        "retained_by_dwell": False,
        "retained_by_hysteresis": False,
        "retained_by_smoothing": True,
        "revision_id": "fdas-revision-test",
        "scalar_final_score_authority": True,
        "signal_ledger": _signal_ledger(),
        "snapshot_id": "snapshot-test",
        "source_sink_flow_enabled": False,
        "state_after_hash": "b" * 64,
        "state_before_hash": "c" * 64,
        "switch_cause": "retained-by-smoothing",
        "truth_mutated": False,
        "turn": 2,
    }
    return dict(semantic, result_hash=structural_hash(semantic))


def _parent():
    return {
        "baseline_selected_operation_id": "operation-1",
        "members": [{
            "operation_id": "operation-1",
            "reasons": ["scalar-top-k", "scalar-winner"],
        }],
        "result_hash": "a" * 64,
    }


def _payload():
    return {
        "revision_id": "fdas-revision-test",
        "snapshot_id": "snapshot-test",
    }


def test_path_persistence_audit_accepts_temporal_membership_only_addition():
    errors, measures = _validate_path_persistence_union(
        _details(), _payload(), _parent())

    assert errors == ()
    assert measures == {
        "additions": 1,
        "expired_routes": 1,
        "fallbacks": 0,
        "members": 2,
        "readouts": 2,
        "regret_rejections": 0,
        "retained_by_dwell": 0,
        "retained_by_hysteresis": 0,
        "retained_by_smoothing": 1,
        "selection_changes": 0,
        "temporal_additions": 1,
        "temporal_retentions": 1,
    }


def test_path_persistence_audit_rejects_rehashed_authority_and_bad_cause():
    details = _details()
    details["action_selection_changed"] = True
    details["switch_cause"] = "corridor-retained"
    semantic = copy.deepcopy(details)
    semantic.pop("result_hash")
    details["result_hash"] = structural_hash(semantic)

    errors, _measures = _validate_path_persistence_union(
        details, _payload(), _parent())

    assert "persistence-shadow-authority-differs" in errors
    assert "persistence-switch-cause-attribution-differs" in errors


def test_path_persistence_audit_rejects_probe_parent_changes():
    errors, _measures = _validate_path_persistence_union(
        _details(), _payload(), dict(_parent(), result_hash="0" * 64))

    assert "persistence-probe-parent-binding-differs" in errors


def test_path_persistence_audit_accepts_zero_regret_smoothing_tie_break():
    details = _details()
    details["readouts"][1]["instantaneous_reachability"] = 1.0
    details["reachability_regret"] = 0.0
    semantic = copy.deepcopy(details)
    semantic.pop("result_hash")
    details["result_hash"] = structural_hash(semantic)

    errors, measures = _validate_path_persistence_union(
        details, _payload(), _parent())

    assert errors == ()
    assert measures["temporal_additions"] == 1
