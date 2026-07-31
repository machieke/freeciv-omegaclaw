"""Deterministic candidate/domain-operation construction."""

from ..events.schema import structural_hash
from .operations import (
    OPERATION_SCHEMA_VERSION,
    OperationParticipant,
    OperationSpec,
    OperationStep,
)


_CITY_DEFENSE_COMPLETION_PREDICATES = {
    "emergency_build_defender":
        "city-defense:defender-production-completed",
    "fortify_existing_defender":
        "city-defense:defender-fortified-at-city",
    "hold_sole_defender":
        "city-defense:sole-defender-held-through-deadline",
    "intercept_immediate_threat":
        "city-defense:visible-threat-neutralized-before-deadline",
    "move_defender_to_city":
        "city-defense:defender-at-city-before-deadline",
}


def assemble_city_defense_operation(
        operation, created_turn,
        ruleset_digest,
        replacement_margin=0.0):
    """Convert a city-defence domain edge to a persistent operation spec."""
    if not isinstance(
            operation, dict):
        raise TypeError(
            "city-defence operation must be an object")
    operation_id = operation.get(
        "operation_id")
    operation_type = str(
        operation.get(
            "operation_type")
        or "")
    requirement_id = operation.get(
        "requirement_id")
    city_id = operation.get(
        "city_id")
    actor_id = operation.get(
        "actor_id")
    deadline_turn = operation.get(
        "deadline_turn")
    action = operation.get(
        "next_action")
    if (not isinstance(
            operation_id, str)
            or not operation_id):
        raise ValueError(
            "city-defence operation id is required")
    if operation_type not in (
            _CITY_DEFENSE_COMPLETION_PREDICATES):
        raise ValueError(
            "unsupported city-defence operation type")
    if (not isinstance(
            requirement_id, str)
            or not requirement_id):
        raise ValueError(
            "city-defence requirement id is required")
    if (isinstance(city_id, bool)
            or not isinstance(
                city_id, int)
            or city_id < 0):
        raise ValueError(
            "city-defence city id must be non-negative")
    if (isinstance(
            deadline_turn, bool)
            or not isinstance(
                deadline_turn, int)
            or deadline_turn
            < int(created_turn)):
        raise ValueError(
            "city-defence deadline must not precede creation")
    if (action is not None
            and not isinstance(
                action, dict)):
        raise TypeError(
            "city-defence next action must be an object or null")
    city_ref = "city:{}".format(
        city_id)
    if actor_id is None:
        participant = (
            OperationParticipant(
                role="producer",
                actor_id=city_ref,
                actor_class="city",
                required=True))
        actor_role = "producer"
    else:
        if (isinstance(actor_id, bool)
                or not isinstance(
                    actor_id, int)
                or actor_id < 0):
            raise ValueError(
                "city-defence actor id must be non-negative")
        participant = (
            OperationParticipant(
                role="defender",
                actor_id="unit:{}".format(
                    actor_id),
                actor_class="unit",
                required=True))
        actor_role = "defender"
    action_type = (
        str(action.get(
            "action_type") or "")
        if action is not None
        else "hold")
    if not action_type:
        raise ValueError(
            "city-defence action type is required")
    step_id = "step-" + structural_hash({
        "action_type": action_type,
        "operation_id": operation_id,
        "requirement_set_id":
            requirement_id,
        "target_ref": city_ref,
    })[:32]
    provenance = tuple(
        operation.get(
            "provenance")
        or (
            "city-defense-domain-operation",
        ))
    maximum_attempts = 1
    if operation_type == (
            "move_defender_to_city"):
        # A server-advertised move is a current legal route step, not proof
        # that the unit will occupy the destination in the next snapshot.
        # Keep retries bounded by the original threat deadline while allowing
        # the lifecycle to rebind each later, independently advertised step.
        maximum_attempts = max(
            1,
            int(deadline_turn)
            - int(created_turn)
            + 1)
    return OperationSpec(
        schema_version=(
            OPERATION_SCHEMA_VERSION),
        operation_id=operation_id,
        operation_type=operation_type,
        goal_ids=(
            "pf-impact:survival",),
        participants=(
            participant,),
        target_ref=city_ref,
        steps=(
            OperationStep(
                step_id=step_id,
                action_type=action_type,
                actor_role=actor_role,
                target_ref=city_ref,
                requirement_set_id=(
                    requirement_id),
                completion_predicate_id=(
                    _CITY_DEFENSE_COMPLETION_PREDICATES[
                        operation_type]),
                maximum_attempts=(
                    maximum_attempts)),),
        created_turn=int(
            created_turn),
        expiry_turn=deadline_turn,
        replacement_margin=float(
            replacement_margin),
        provenance=provenance,
        ruleset_digest=(
            ruleset_digest))
