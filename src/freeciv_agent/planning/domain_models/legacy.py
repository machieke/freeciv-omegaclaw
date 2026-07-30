"""Explicit compatibility wrapper for the current projection transition model."""

from ...pressure.transitions import ExpectedTransition, PredictedOutcome
from .base import DomainEstimateRequest
from .context import EstimateAuthority, GroundedTransitionEstimate
from .registry import context_key_for_request


class LegacyProjectionTransitionModel:
    """Expose legacy projection semantics without granting grounded authority."""

    model_id = "legacy_projection"
    model_version = "1.0"
    # This implementation reads only the snapshot turn and never writes any
    # request field. Registry trust is class-local: subclasses must undergo
    # their own review before they can opt out of isolation copying.
    immutable_request_safe = True

    def supports(self, request):
        return (
            isinstance(request, DomainEstimateRequest)
            and isinstance(request.legal_action, dict))

    def estimate(self, request):
        fallback_loss = max(
            (float(value) for _, value in request.goal_losses),
            default=1.0)
        projection = dict(
            getattr(request.candidate, "projection", None) or {})
        operation = request.operation_context
        probability = projection.get(
            "success_probability",
            (
                float(getattr(
                    operation, "success_probability", 1.0))
                * float(getattr(
                    operation, "feasibility", 1.0))))
        probability = float(probability)
        if not 0.0 <= probability <= 1.0:
            raise ValueError(
                "legacy projected probability must be in [0,1]")
        goal_features = projection.get(
            "next_goal_cost_to_go", {})
        if not isinstance(goal_features, dict):
            raise TypeError(
                "next_goal_cost_to_go must be an object")
        resource_delta = projection.get(
            "resource_delta", {})
        if not isinstance(resource_delta, dict):
            raise TypeError(
                "resource_delta must be an object")
        truth_summaries = projection.get(
            "next_truth_summaries", ())
        if isinstance(truth_summaries, dict):
            truth_summaries = tuple(
                (
                    str(key),
                    value["strength"],
                    value["confidence"],
                )
                for key, value in sorted(
                    truth_summaries.items()))
        else:
            truth_summaries = tuple(
                tuple(row) for row
                in truth_summaries)
        eta = next((
            projection.get(name)
            for name in (
                "settlement_eta_turns",
                "preexpansion_sequence_settlement_eta_turns",
                "repeat_completion_eta_turns",
                "completion_eta_turns",
                "founder_route_eta_turns",
            )
            if projection.get(name) is not None), None)
        turn = getattr(
            request.snapshot, "turn", None)
        if turn is None and isinstance(
                request.snapshot, dict):
            turn = request.snapshot.get("turn")
        completion_turn = (
            None if eta is None else
            float(eta) + (
                float(turn) if turn is not None else 0.0))
        risk = projection.get(
            "risk_estimate", {})
        adverse_loss = (
            float(risk.get("expected_loss", 0.0))
            if isinstance(risk, dict) else 0.0)
        declared_provenance = projection.get(
            "provenance", ())
        if isinstance(declared_provenance, str):
            declared_provenance = (
                declared_provenance,)
        provenance = set(
            str(value) for value in declared_provenance
            if value)
        provenance.add(
            "candidate-projection:{}".format(
                request.action_category))
        provenance.update(
            "{}={}".format(key, projection[key])
            for key in sorted(projection)
            if key.endswith("_source")
            and projection[key])
        outcome = PredictedOutcome(
            outcome_id="{}:projected-success".format(
                request.stable_operation_id),
            probability=probability,
            next_truth_summaries=truth_summaries,
            next_goal_features=tuple(sorted(
                (str(key), float(value))
                for key, value in goal_features.items())),
            resource_delta=tuple(sorted(
                (str(key), float(value))
                for key, value in resource_delta.items())),
            completion_turn=completion_turn,
            adverse_loss=adverse_loss,
            provenance=tuple(sorted(provenance)))
        transition = ExpectedTransition(
            operation_id=request.stable_operation_id,
            outcomes=(() if probability == 0.0
                      else (outcome,)),
            residual_probability=1.0 - probability,
            model_id="{}/{}".format(
                self.model_id, self.model_version),
            calibration_group=(
                "legacy-projection:{}".format(
                    request.action_category)),
            residual_goal_losses=(
                ("*", max(fallback_loss, 1e-12)),))
        return GroundedTransitionEstimate(
            transition=transition,
            context_key=context_key_for_request(request),
            authority=EstimateAuthority.LEGACY_PROXY,
            confidence=0.0,
            validity=request.validity,
            estimator_id=self.model_id,
            estimator_version=self.model_version,
            provenance=(
                "existing-impact-candidate-projection",
                "legacy-proxy-no-live-authority",
            ),
        )
