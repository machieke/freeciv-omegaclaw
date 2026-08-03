import copy
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_scalar_baseline_candidate_readout import (  # noqa: E402
    REQUIRED_NONINFERIORITY_CHECKS,
    RULESET_DEFENSIVE_NONINFERIORITY_CHECKS,
    _validate_readout,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    CALIBRATED_EQUIVALENCE_PARETO_CANDIDATE_READOUT_IDENTITY,
    DEFENSIVE_CAPABILITY_IDENTITY,
    RULESET_DEFENSIVE_SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY,
)


def _candidate(operation_id, estimate, lower, upper, eligibility_reason,
               checks=()):
    return {
        "action_key": "action-" + operation_id,
        "actor_id": 7 if operation_id == "control" else 8,
        "effective_lineages": 12,
        "eligibility_reason": eligibility_reason,
        "estimate": estimate,
        "estimated_turns": 1,
        "first_step_movement_cost": 1,
        "homecity_relation": "target",
        "hp": 10,
        "interval_lower": lower,
        "interval_upper": upper,
        "moves_left": 3,
        "noninferiority_checks": sorted(checks),
        "operation_id": operation_id,
        "source_atom_id": "source-" + operation_id,
        "target_city_id": 3,
        "total_movement_cost": 3,
        "unit_type": "Warriors",
        "veteran": 1,
    }


def _parent():
    return {
        "baseline_selected_operation_id": "control",
        "members": [
            {"operation_id": "control"},
            {"operation_id": "treatment"},
        ],
        "result_hash": "protected-union-hash",
        "revision_id": "revision-test",
        "snapshot_id": "snapshot-test",
    }


def _capability(rule_id, defense=4.0):
    return {
        "defense": defense,
        "defensive_effect_signature": ["effect-city-defense"],
        "firepower": 1.0,
        "identity": DEFENSIVE_CAPABILITY_IDENTITY,
        "maximum_hitpoints": 20.0,
        "rule_id": rule_id,
        "ruleset_digest": "ruleset-digest",
        "unit_class": "Land",
    }


def _details():
    semantic = {
        "action_selection_changed": False,
        "baseline_operation_id": "control",
        "candidates": [
            _candidate(
                "control", 0.3, 0.2, 0.4,
                "protected-scalar-control"),
            _candidate(
                "treatment", 0.8, 0.7, 0.9, "eligible",
                REQUIRED_NONINFERIORITY_CHECKS),
        ],
        "config": {
            "allowed_action_type": "unit_move",
            "minimum_interval_separation": 0.0,
            "require_grounded_noninferiority": True,
            "require_same_target_ref": True,
        },
        "control_semantics": "protected-fdas-scalar-top-1",
        "identity": "fdas-scalar-baseline-candidate-readout/1.0",
        "policy_authority": False,
        "proposed_operation_id": "treatment",
        "protected_union_result_hash": "protected-union-hash",
        "readout_authority": False,
        "reason": "calibrated-and-grounded-dominance",
        "rejected": [],
        "revision_id": "revision-test",
        "shadow_preference": True,
        "snapshot_id": "snapshot-test",
        "status": "eligible-shadow",
        "truth_mutated": False,
    }
    details = dict(semantic)
    details["result_hash"] = structural_hash(semantic)
    return details


def test_scalar_baseline_audit_accepts_separated_grounded_preference():
    errors, measures = _validate_readout(_details(), {
        "revision_id": "revision-test",
        "snapshot_id": "snapshot-test",
    }, _parent())

    assert errors == ()
    assert measures == {
        "abstentions": 0,
        "eligible": 1,
        "evaluations": 1,
        "grounded_alternatives": 1,
        "interval_overlaps": 0,
        "shadow_preferences": 1,
    }


def test_scalar_baseline_audit_rejects_rehashed_authority_change():
    details = _details()
    details["action_selection_changed"] = True
    semantic = copy.deepcopy(details)
    semantic.pop("result_hash")
    details["result_hash"] = structural_hash(semantic)

    errors, _measures = _validate_readout(details, {
        "revision_id": "revision-test",
        "snapshot_id": "snapshot-test",
    }, _parent())

    assert "scalar-baseline-shadow-authority-differs" in errors


def test_scalar_baseline_audit_rejects_parent_baseline_substitution():
    parent = _parent()
    parent["baseline_selected_operation_id"] = "treatment"

    errors, _measures = _validate_readout(_details(), {
        "revision_id": "revision-test",
        "snapshot_id": "snapshot-test",
    }, parent)

    assert "scalar-baseline-protected-membership-differs" in errors


def test_scalar_baseline_audit_accepts_ruleset_defensive_noninferiority():
    details = _details()
    details["identity"] = (
        RULESET_DEFENSIVE_SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY)
    details["candidates"][0]["defensive_capability"] = _capability(
        "unit-riflemen")
    details["candidates"][1]["unit_type"] = "Alpine Troops"
    details["candidates"][1]["defensive_capability"] = _capability(
        "unit-alpine")
    details["candidates"][1]["noninferiority_checks"] = sorted(
        RULESET_DEFENSIVE_NONINFERIORITY_CHECKS)
    semantic = copy.deepcopy(details)
    semantic.pop("result_hash")
    details["result_hash"] = structural_hash(semantic)

    errors, measures = _validate_readout(details, {
        "revision_id": "revision-test",
        "snapshot_id": "snapshot-test",
    }, _parent())

    assert errors == ()
    assert measures["shadow_preferences"] == 1


def test_scalar_baseline_audit_rejects_inferior_ruleset_defense():
    details = _details()
    details["identity"] = (
        RULESET_DEFENSIVE_SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY)
    details["candidates"][0]["defensive_capability"] = _capability(
        "unit-control", defense=5.0)
    details["candidates"][1]["defensive_capability"] = _capability(
        "unit-treatment", defense=4.0)
    details["candidates"][1]["noninferiority_checks"] = sorted(
        RULESET_DEFENSIVE_NONINFERIORITY_CHECKS)
    semantic = copy.deepcopy(details)
    semantic.pop("result_hash")
    details["result_hash"] = structural_hash(semantic)

    errors, _measures = _validate_readout(details, {
        "revision_id": "revision-test",
        "snapshot_id": "snapshot-test",
    }, _parent())

    assert "scalar-baseline-grounded-noninferiority-differs" in errors


def test_scalar_baseline_audit_accepts_calibrated_equivalence_pareto():
    details = _details()
    details["identity"] = (
        CALIBRATED_EQUIVALENCE_PARETO_CANDIDATE_READOUT_IDENTITY)
    details["reason"] = (
        "calibrated-equivalence-and-grounded-pareto-dominance")
    control, treatment = details["candidates"]
    control["estimated_turns"] = 2
    control["total_movement_cost"] = 6
    control["defensive_capability"] = _capability("unit-control")
    treatment["unit_type"] = "Alpine Troops"
    treatment["estimated_turns"] = 1
    treatment["total_movement_cost"] = 3
    treatment["defensive_capability"] = _capability("unit-treatment")
    treatment["estimate"] = control["estimate"] = 0.4
    treatment["interval_lower"] = control["interval_lower"] = 0.2
    treatment["interval_upper"] = control["interval_upper"] = 0.6
    treatment["effective_lineages"] = control["effective_lineages"] = 17
    for candidate in (control, treatment):
        candidate["calibration_prediction_reason"] = "action-estimate"
        candidate["strict_grounded_improvements"] = []
    treatment["strict_grounded_improvements"] = [
        "estimated-turns", "total-movement-cost"]
    treatment["noninferiority_checks"] = sorted(
        RULESET_DEFENSIVE_NONINFERIORITY_CHECKS)
    treatment["eligibility_reason"] = (
        "eligible-calibrated-equivalence-pareto")
    semantic = copy.deepcopy(details)
    semantic.pop("result_hash")
    details["result_hash"] = structural_hash(semantic)

    errors, measures = _validate_readout(details, {
        "revision_id": "revision-test",
        "snapshot_id": "snapshot-test",
    }, _parent())

    assert errors == ()
    assert measures["shadow_preferences"] == 1
