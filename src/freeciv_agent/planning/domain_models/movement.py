"""Conservative grounded estimates for advertised one-step unit movement."""

from ...events.schema import canonical_json_bytes
from ...pressure.transitions import ExpectedTransition, PredictedOutcome
from ..path_corridors import adjacent_action_corridor
from .base import DomainEstimateRequest
from .context import (
    EstimateAuthority,
    GroundedTransitionEstimate,
    canonical_model_artifact,
)
from .registry import context_key_for_request, residual_losses


class GroundedMovementTransitionModel:
    """Model only the explicit-cost, visible adjacent-move subset."""

    model_id = "grounded_adjacent_movement"
    model_version = "1.0"
    immutable_request_safe = True

    def supports(self, request):
        return (
            isinstance(request, DomainEstimateRequest)
            and request.action_type == "unit_move")

    def _abstain(
            self, request, reason_code,
            missing_fields, corridor=None):
        artifact = {
            "blockers": [],
            "candidate_next_hops": (
                [] if corridor is None else [
                    list(value)
                    for value in corridor
                    .candidate_next_hops]),
            "corridor": (
                None if corridor is None
                else corridor.to_dict()),
            "estimated_turns_to_destination":
                None,
            "legal_first_action": dict(
                request.legal_action),
            "minimum_current_turn_movement_cost":
                None,
            "missing_fields": list(
                sorted(set(missing_fields))),
            "movement_points_remaining":
                None,
            "path_risk": {
                "occupancy": "unknown",
            },
            "parity_status": "unverified",
            "reachable": None,
            "reason_code": reason_code,
            "schema_version": "1.0",
            "supported_subset":
                "advertised-visible-explicit-cost-adjacent",
            "transport_requirement": None,
            "unknown_mass": 1.0,
        }
        return GroundedTransitionEstimate(
            transition=ExpectedTransition(
                operation_id=(
                    request.stable_operation_id),
                outcomes=(),
                residual_probability=1.0,
                model_id="{}/{}".format(
                    self.model_id,
                    self.model_version),
                calibration_group=(
                    "movement:unsupported"),
                residual_goal_losses=(
                    residual_losses(request))),
            context_key=context_key_for_request(
                request),
            authority=EstimateAuthority.ABSTAIN,
            confidence=0.0,
            validity=request.validity,
            estimator_id=self.model_id,
            estimator_version=(
                self.model_version),
            provenance=(
                "server-advertised-action",
                "missing-grounded-movement-input",
            ),
            abstention_reason=reason_code,
            model_artifact_json=(
                canonical_model_artifact(
                    artifact)))

    def estimate(self, request):
        if not self.supports(request):
            return self._abstain(
                request,
                "unsupported-action-type",
                ("action_type",))
        action = request.legal_action
        snapshot = request.snapshot
        try:
            corridor = adjacent_action_corridor(
                snapshot, action)
        except (TypeError, ValueError):
            return self._abstain(
                request,
                "movement-input-missing-position",
                ("actor_position",
                 "target_position"))
        missing = []
        advertised = (
            canonical_json_bytes(
                action).decode("utf-8")
            in set(getattr(
                snapshot,
                "legal_action_json", ())))
        if not advertised:
            missing.append(
                "advertised_legal_action")
        actor_id = action.get(
            "actor_id", action.get("unit_id"))
        unit = (
            snapshot.unit(actor_id)
            if callable(getattr(
                snapshot, "unit", None))
            else None)
        if unit is None:
            missing.append("actor")
        elif unit.activity != "idle":
            missing.append(
                "actor_idle_activity")
        moves_left = (
            None if unit is None
            else unit.moves_left)
        if moves_left is None:
            missing.append(
                "moves_left")
        elif moves_left <= 0:
            return self._abstain(
                request,
                "movement-actor-exhausted",
                (), corridor=corridor)
        movement_cost = action.get(
            "movement_cost")
        if (isinstance(movement_cost, bool)
                or not isinstance(
                    movement_cost, (int, float))
                or float(movement_cost) <= 0.0):
            missing.append(
                "authoritative_movement_cost")
        transport_required = action.get(
            "transport_required")
        if not isinstance(
                transport_required, bool):
            missing.append(
                "transport_requirement")
        elif transport_required:
            return self._abstain(
                request,
                "movement-transport-unsupported",
                ("grounded_transport_context",),
                corridor=corridor)
        if unit is not None and (
                not isinstance(
                    unit.transported, bool)):
            missing.append(
                "actor_transport_state")
        if unit is not None and (
                not isinstance(
                    unit.done_moving, bool)):
            missing.append(
                "actor_done_moving_state")
        elif (unit is not None
              and unit.done_moving):
            return self._abstain(
                request,
                "movement-actor-done",
                (), corridor=corridor)
        target_tile = corridor.tile_path[-1]
        if target_tile not in set(getattr(
                snapshot,
                "visible_tile_ids", ())):
            missing.append(
                "visible_target_occupancy")
        target_enemy_ids = tuple(sorted(
            row.unit_id
            for row in getattr(
                snapshot,
                "visible_enemy_units", ())
            if (row.x, row.y)
            == corridor.destination_position))
        if target_enemy_ids:
            return self._abstain(
                request,
                "movement-target-enemy-occupied",
                (), corridor=corridor)
        if missing:
            return self._abstain(
                request,
                "movement-input-missing",
                tuple(missing),
                corridor=corridor)
        movement_cost = float(
            movement_cost)
        if movement_cost > float(
                moves_left):
            return self._abstain(
                request,
                "movement-cost-exceeds-available",
                (), corridor=corridor)
        remaining = (
            float(moves_left)
            - movement_cost)
        current_turn = int(getattr(
            snapshot, "turn", 0))
        goal_features = tuple(sorted(
            (goal_id, float(loss))
            for goal_id, loss
            in request.goal_losses))
        artifact = {
            "blockers": [],
            "candidate_next_hops": [
                list(value)
                for value in corridor
                .candidate_next_hops],
            "corridor": corridor.to_dict(),
            "estimated_turns_to_destination":
                0,
            "legal_first_action":
                dict(action),
            "minimum_current_turn_movement_cost":
                movement_cost,
            "missing_fields": [],
            "movement_points_remaining":
                remaining,
            "path_risk": {
                "occupancy":
                    "currently-visible-clear",
                "visible_enemy_unit_ids": [],
            },
            "parity_status": "unverified",
            "reachable": True,
            "reason_code": None,
            "schema_version": "1.0",
            "supported_subset":
                "advertised-visible-explicit-cost-adjacent",
            "transport_requirement":
                transport_required,
            "unknown_mass": 0.0,
        }
        outcome = PredictedOutcome(
            outcome_id="{}:arrived".format(
                request.stable_operation_id),
            probability=1.0,
            next_truth_summaries=(),
            next_goal_features=(
                goal_features),
            resource_delta=(
                ("movement_points",
                 -movement_cost),),
            completion_turn=float(
                current_turn),
            adverse_loss=0.0,
            provenance=(
                "server-advertised-action",
                "authoritative-explicit-movement-cost",
                "currently-visible-target",
            ))
        return GroundedTransitionEstimate(
            transition=ExpectedTransition(
                operation_id=(
                    request.stable_operation_id),
                outcomes=(outcome,),
                residual_probability=0.0,
                model_id="{}/{}".format(
                    self.model_id,
                    self.model_version),
                calibration_group=(
                    "movement:visible-explicit-cost"),
                residual_goal_losses=(
                    residual_losses(request))),
            context_key=context_key_for_request(
                request),
            # The explicit edge facts are deterministic, but the mapping to
            # Freeciv movement semantics is not live-approved before native
            # parity covers this declared subset.
            authority=EstimateAuthority.HEURISTIC,
            confidence=0.5,
            validity=request.validity,
            estimator_id=self.model_id,
            estimator_version=(
                self.model_version),
            provenance=(
                "server-advertised-action",
                "clean-room-adjacent-corridor",
                "explicit-action-movement-cost",
                "native-parity-not-yet-established",
            ),
            model_artifact_json=(
                canonical_model_artifact(
                    artifact)))
