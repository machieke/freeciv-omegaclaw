from copy import deepcopy

from freeciv.harness.fdas_randomized_alternative_live import (
    ASSIGNMENT_IDENTITY,
    ASSIGNMENT_POLICY,
    ASSIGNMENT_UNIT,
    assignment_draw,
    assignment_material,
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
