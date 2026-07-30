"""Grounded server-side city-worker macro transition estimates.

Pressure chooses a city and bounded output constraints.  The advertised
``city_governor`` action delegates tile/specialist assignment to Freeciv's
citizen manager.  This model never decomposes that macro into citizen actions
and never invents a pre-execution solver result.
"""

from ...events.schema import canonical_json_bytes
from ...pressure.transitions import ExpectedTransition, PredictedOutcome
from .base import DomainEstimateRequest
from .context import (
    EstimateAuthority,
    GroundedTransitionEstimate,
    canonical_model_artifact,
)
from .registry import context_key_for_request, residual_losses


CITY_OUTPUT_NAMES = (
    "food", "shield", "trade",
    "gold", "luxury", "science",
)


def city_output_vector(city):
    """Return typed gross/used/net outputs, or ``None`` when incomplete."""
    result = {}
    for field, values in (
            ("produced", getattr(city, "production", ())),
            ("used", getattr(city, "usage", ())),
            ("net", getattr(city, "surplus", ()))):
        if (
                not isinstance(values, tuple)
                or len(values) < len(CITY_OUTPUT_NAMES)
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    for value in values[:len(CITY_OUTPUT_NAMES)])
        ):
            return None
        result[field] = {
            name: int(value)
            for name, value in zip(
                CITY_OUTPUT_NAMES, values)
        }
    return result


class GroundedCityWorkerTransitionModel:
    """Model one advertised citizen-manager request as an atomic macro."""

    model_id = "grounded_city_worker_macro"
    model_version = "1.0"
    immutable_request_safe = True

    def supports(self, request):
        return (
            isinstance(request, DomainEstimateRequest)
            and request.action_type == "city_governor")

    def _abstain(
            self, request, reason_code,
            missing_fields=(), artifact_extra=None):
        artifact = {
            "assignment": {
                "citizen_actions_emitted": False,
                "delegated_to": "server-citizen-manager",
                "individual_assignment_visible": False,
            },
            "city_id": (
                request.legal_action.get("city_id")
                if isinstance(request.legal_action, dict)
                else None),
            "current_output_vector": None,
            "legal_action": (
                dict(request.legal_action)
                if isinstance(request.legal_action, dict)
                else None),
            "missing_fields": list(sorted(set(missing_fields))),
            "predicted_output_vector": {
                "point_estimate": None,
                "status": "unavailable",
            },
            "reason_code": reason_code,
            "schema_version": "1.0",
            "solver": {
                "optimality_gap": None,
                "optimality_gap_status": "unavailable",
                "status": "not-invoked",
            },
            "unknown_mass": 1.0,
        }
        artifact.update(artifact_extra or {})
        return GroundedTransitionEstimate(
            transition=ExpectedTransition(
                operation_id=request.stable_operation_id,
                outcomes=(),
                residual_probability=1.0,
                model_id="{}/{}".format(
                    self.model_id, self.model_version),
                calibration_group="city-worker:unsupported",
                residual_goal_losses=residual_losses(request)),
            context_key=context_key_for_request(request),
            authority=EstimateAuthority.ABSTAIN,
            confidence=0.0,
            validity=request.validity,
            estimator_id=self.model_id,
            estimator_version=self.model_version,
            provenance=(
                "server-advertised-action",
                "missing-grounded-city-worker-input",
            ),
            abstention_reason=reason_code,
            model_artifact_json=canonical_model_artifact(artifact))

    def estimate(self, request):
        if not self.supports(request):
            return self._abstain(
                request, "unsupported-action-type", ("action_type",))
        action = request.legal_action
        snapshot = request.snapshot
        target = action.get("target")
        city_id = action.get("city_id")
        reserve = (
            target.get("food_surplus_reserve")
            if isinstance(target, dict) else None)
        require_happy = (
            target.get("require_happy", False)
            if isinstance(target, dict) else None)
        advertised = bool(
            canonical_json_bytes(action).decode("utf-8")
            in set(getattr(snapshot, "legal_action_json", ())))
        city = (
            snapshot.city(city_id)
            if (
                isinstance(city_id, int)
                and not isinstance(city_id, bool)
                and callable(getattr(snapshot, "city", None)))
            else None)
        missing = []
        if not advertised:
            missing.append("advertised_legal_action")
        if (
                isinstance(city_id, bool)
                or not isinstance(city_id, int)
                or city_id < 0
        ):
            missing.append("city_id")
        if city is None:
            missing.append("city")
        elif city.owner != getattr(
                snapshot, "player_id", city.owner):
            missing.append("owned_city")
        elif city.governor_available is not True:
            missing.append("city.governor_available")
        if (
                isinstance(reserve, bool)
                or not isinstance(reserve, int)
                or not 0 <= reserve <= 10
        ):
            missing.append(
                "target.food_surplus_reserve")
        if not isinstance(require_happy, bool):
            missing.append("target.require_happy")
        output = (
            city_output_vector(city)
            if city is not None else None)
        if output is None:
            missing.append("city.output_vector")
        if missing:
            return self._abstain(
                request, "city-worker-input-missing",
                tuple(missing),
                artifact_extra={
                    "current_output_vector": output,
                })

        current_turn = int(snapshot.turn)
        constraint = {
            "food_surplus_minimum": reserve,
            "require_happy": require_happy,
        }
        currently_satisfied = bool(
            output["net"]["food"] >= reserve
            and (
                not require_happy
                or (
                    city.was_happy is True
                    and city.disorder is not True)))
        artifact = {
            "assignment": {
                "citizen_actions_emitted": False,
                "delegated_to": "server-citizen-manager",
                "individual_assignment_visible": False,
                "macro_action_atomic": True,
            },
            "city_id": city_id,
            "city_name": city.name,
            "constraints": {
                "currently_satisfied": currently_satisfied,
                "requested": constraint,
            },
            "current_output_vector": output,
            "legal_action": dict(action),
            "missing_fields": [],
            "predicted_output_vector": {
                "lower_bounds": {
                    "food_surplus": reserve,
                },
                "point_estimate": None,
                "reason":
                    "server-interface-does-not-expose-preexecution-cm-result",
                "status": "unavailable-before-execution",
            },
            "pressure_decision": {
                "city_budget_target": "city:{}".format(city_id),
                "minimum_constraints": constraint,
                "output_priorities": (
                    ["happiness", "food"]
                    if require_happy else ["food"]),
            },
            "reason_code": None,
            "schema_version": "1.0",
            "solver": {
                "authority": "server-citizen-manager",
                "optimality_gap": None,
                "optimality_gap_status":
                    "not-exposed-by-server-interface",
                "status": "advertised-macro-not-yet-executed",
            },
            "unknown_mass": 0.0,
        }
        outcome = PredictedOutcome(
            outcome_id="{}:macro-submitted".format(
                request.stable_operation_id),
            probability=1.0,
            next_truth_summaries=(),
            # Submitting the macro does not prove a feasible assignment or
            # any output relief. The later snapshot result is authoritative.
            next_goal_features=tuple(request.goal_losses),
            resource_delta=((
                "city_worker_assignment:city:{}".format(city_id),
                -1.0),),
            completion_turn=float(current_turn),
            adverse_loss=0.0,
            provenance=(
                "server-advertised-city-governor-action",
                "authoritative-current-city-output",
                "macro-submission-not-solver-result",
            ))
        return GroundedTransitionEstimate(
            transition=ExpectedTransition(
                operation_id=request.stable_operation_id,
                outcomes=(outcome,),
                residual_probability=0.0,
                model_id="{}/{}".format(
                    self.model_id, self.model_version),
                calibration_group="city-worker:{}".format(
                    "happy-food"
                    if require_happy else "food"),
                residual_goal_losses=residual_losses(request)),
            context_key=context_key_for_request(request),
            authority=EstimateAuthority.DETERMINISTIC_DERIVED,
            confidence=1.0,
            validity=request.validity,
            estimator_id=self.model_id,
            estimator_version=self.model_version,
            provenance=(
                "server-advertised-city-governor-action",
                "authoritative-city-governor-capability",
                "authoritative-city-output-vector",
                "server-side-assignment-boundary",
            ),
            model_artifact_json=canonical_model_artifact(artifact))
