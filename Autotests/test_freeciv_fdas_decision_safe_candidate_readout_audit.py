import copy
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_decision_safe_candidate_readout import (  # noqa: E402
    REQUIRED_NONINFERIORITY_CHECKS,
    _validate_readout,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    DECISION_SAFE_CANDIDATE_READOUT_IDENTITY,
    FdasDecisionSafeCandidateReadoutConfig,
)


def _candidate(operation_id, *, estimate, lower, upper, turns=1, cost=3):
    return {
        "action_key": "action-" + operation_id,
        "actor_id": 7 if operation_id == "control" else 8,
        "effective_lineages": 12,
        "eligibility_reason": (
            "active-control" if operation_id == "control" else "eligible"),
        "estimate": estimate,
        "estimated_turns": turns,
        "first_step_movement_cost": 3,
        "homecity_relation": "target",
        "hp": 10,
        "interval_lower": lower,
        "interval_upper": upper,
        "moves_left": 3,
        "noninferiority_checks": (
            [] if operation_id == "control"
            else sorted(REQUIRED_NONINFERIORITY_CHECKS)),
        "operation_id": operation_id,
        "source_atom_id": "atom-" + operation_id,
        "target_city_id": 3,
        "total_movement_cost": cost,
        "unit_type": "Warriors",
        "veteran": 0,
    }


def _details():
    semantic = {
        "action_selection_changed": False,
        "baseline_operation_id": "control",
        "calibrated_union_result_hash": "c" * 64,
        "candidates": [
            _candidate("control", estimate=0.4, lower=0.3, upper=0.5),
            _candidate("treatment", estimate=0.8, lower=0.7, upper=0.9),
        ],
        "config": FdasDecisionSafeCandidateReadoutConfig().to_dict(),
        "counterfactual_change": True,
        "identity": DECISION_SAFE_CANDIDATE_READOUT_IDENTITY,
        "policy_authority": False,
        "proposed_operation_id": "treatment",
        "readout_authority": False,
        "reason": "calibrated-and-grounded-dominance",
        "rejected": [],
        "revision_id": "revision-1",
        "snapshot_id": "snapshot-1",
        "status": "eligible-shadow",
        "truth_mutated": False,
    }
    return dict(semantic, result_hash=structural_hash(semantic))


def _payload():
    return {"revision_id": "revision-1", "snapshot_id": "snapshot-1"}


def _parent():
    return {
        "result_hash": "c" * 64,
        "revision_id": "revision-1",
        "snapshot_id": "snapshot-1",
    }


def test_decision_safe_audit_accepts_separated_grounded_shadow_readout():
    errors, measures = _validate_readout(_details(), _payload(), _parent())

    assert errors == ()
    assert measures == {
        "abstained": 0,
        "candidates": 2,
        "counterfactual_changes": 1,
        "eligible": 1,
        "evaluations": 1,
    }


def test_decision_safe_audit_rejects_overlap_and_grounded_regression():
    details = _details()
    details["candidates"][1]["interval_lower"] = 0.4
    details["candidates"][1]["estimated_turns"] = 2
    details["candidates"][1]["total_movement_cost"] = 6
    semantic = copy.deepcopy(details)
    semantic.pop("result_hash")
    details["result_hash"] = structural_hash(semantic)

    errors, _measures = _validate_readout(details, _payload(), _parent())

    assert "decision-safe-intervals-are-not-separated" in errors
    assert "decision-safe-grounded-noninferiority-differs" in errors


def test_decision_safe_audit_rejects_rehashed_authority():
    details = _details()
    details["readout_authority"] = True
    semantic = copy.deepcopy(details)
    semantic.pop("result_hash")
    details["result_hash"] = structural_hash(semantic)

    errors, _measures = _validate_readout(details, _payload(), _parent())

    assert "decision-safe-shadow-authority-differs" in errors
