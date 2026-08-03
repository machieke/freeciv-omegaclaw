import copy
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_probe_candidate_union import (  # noqa: E402
    PROBE_CONFIG,
    _completed_endpoint,
    _validate_probe_union,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    PROBE_CANDIDATE_REACHABILITY_IDENTITY,
)


MOVE = "fdas-shadow:city-garrison-deficit:unit_move"


def _signal_ledger():
    uses = tuple({
        "model_id": None,
        "residualized": False,
        "signal_name": signal,
        "stage": "diagnostics" if signal == "raw_probe_count" else (
            "baseline_candidate_union"
            if signal == "calibrated_transition_estimate" else
            "candidate_union"),
        "transformation": "count_only" if signal == "raw_probe_count" else (
            "protected_membership_only"
            if signal == "calibrated_transition_estimate" else
            "top_k_membership_only"),
        "used_in_final_score": False,
    } for signal in (
        "calibrated_transition_estimate",
        "corrected_bridge_overlap",
        "corrected_probe_weight",
        "raw_probe_count",
    ))
    semantic = {
        "contract_version": "single-use-bridge-signals/1.0",
        "uses": list(uses),
    }
    return dict(semantic, ledger_hash=structural_hash(semantic))


def _details():
    operation_id = "operation-1"
    semantic = {
        "action_selection_changed": False,
        "backward_probe_batch_hash": "a" * 64,
        "base_calibrated_operation_ids": [operation_id],
        "baseline_selected_operation_id": operation_id,
        "bridge_selection_hash": "b" * 64,
        "calibrated_union_result_hash": "c" * 64,
        "capacity_solver_enabled": False,
        "fallback_reason": None,
        "fallback_required": False,
        "flow_advection_enabled": False,
        "forward_probe_batch_hash": "d" * 64,
        "goal_id": DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
        "graph_artifact_hash": "e" * 64,
        "graph_complete": True,
        "graph_probe_semantic_hash": "f" * 64,
        "identity": PROBE_CANDIDATE_REACHABILITY_IDENTITY,
        "maximum_probe_regions": 1,
        "members": [{
            "operation_id": operation_id,
            "reasons": [
                "probe-informed-reachability",
                "scalar-top-k",
                "scalar-winner",
            ],
        }],
        "policy_authority": False,
        "probe_added_operation_ids": [],
        "probe_config": dict(PROBE_CONFIG),
        "probe_healthy": True,
        "probe_per_action": 1,
        "probe_selected_operation_ids": [operation_id],
        "readout_authority": False,
        "readouts": [{
            "action_key": "action-1",
            "backward_support": 1.0,
            "baseline_rank": 1,
            "corrected_overlap": 1.0,
            "forward_support": 1.0,
            "location_eligibility": 1.0,
            "operation_id": operation_id,
            "operation_node_id": "flow:operation:1",
            "operation_type": MOVE,
            "selected_for_probe_recall": True,
            "uncertainty": 0.0,
        }],
        "revision_id": "fdas-revision-test",
        "scalar_final_score_authority": True,
        "signal_ledger": _signal_ledger(),
        "snapshot_id": "snapshot-test",
        "truth_mutated": False,
    }
    return dict(semantic, result_hash=structural_hash(semantic))


def _parent():
    return {
        "baseline_selected_operation_id": "operation-1",
        "members": [{"operation_id": "operation-1"}],
        "result_hash": "c" * 64,
    }


def _payload():
    return {
        "revision_id": "fdas-revision-test",
        "snapshot_id": "snapshot-test",
    }


def test_probe_union_audit_accepts_bounded_membership_only_readout():
    errors, measures = _validate_probe_union(
        _details(), _payload(), _parent())

    assert errors == ()
    assert measures == {
        "additions": 0,
        "fallbacks": 0,
        "healthy": 1,
        "incomplete_graphs": 0,
        "members": 1,
        "mixed_action": False,
        "readouts": 1,
        "selected": 1,
        "selection_changes": 0,
    }


def test_probe_union_audit_rejects_rehashed_authority_and_parent_changes():
    details = _details()
    details["action_selection_changed"] = True
    semantic = copy.deepcopy(details)
    semantic.pop("result_hash")
    details["result_hash"] = structural_hash(semantic)

    errors, _measures = _validate_probe_union(
        details, _payload(), dict(_parent(), result_hash="0" * 64))

    assert "probe-shadow-authority-differs" in errors
    assert "probe-calibrated-parent-binding-differs" in errors


def test_probe_union_completion_accepts_only_real_completed_endpoints():
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
    interrupted = dict(eliminated, completed=False)

    assert _completed_endpoint(horizon)
    assert _completed_endpoint(eliminated)
    assert not _completed_endpoint(interrupted)
