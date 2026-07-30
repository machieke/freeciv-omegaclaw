"""Deterministic dispatch for grounded and shadow transition models."""

import copy

from ...pressure.transitions import ExpectedTransition
from .base import DomainEstimateRequest
from .context import (
    EstimateAuthority,
    GroundedTransitionEstimate,
    TransitionContextKey,
    canonical_context_token,
)


def horizon_bucket(request):
    remaining = max(
        0,
        int(request.horizon_turn)
        - int(request.validity.estimated_at_turn))
    if remaining == 0:
        return "immediate"
    if remaining <= 3:
        return "near"
    if remaining <= 12:
        return "short"
    if remaining <= 50:
        return "medium"
    return "long"


def context_key_for_request(request):
    projection = getattr(request.candidate, "projection", None) or {}
    goal_id = (
        request.goal_losses[0][0]
        if len(request.goal_losses) == 1 else
        "multi_goal")
    return TransitionContextKey(
        schema_version=1,
        action_category=canonical_context_token(
            request.action_category),
        action_type=canonical_context_token(
            request.action_type),
        goal_id=canonical_context_token(goal_id),
        lifecycle_state=canonical_context_token(
            projection.get("lifecycle_state", "immediate")),
        actor_class=canonical_context_token(
            projection.get("actor_class"))
        if projection.get("actor_class") is not None else None,
        target_class=canonical_context_token(
            projection.get("target_class"))
        if projection.get("target_class") is not None else None,
        threat_regime=canonical_context_token(
            projection.get("threat_regime"))
        if projection.get("threat_regime") is not None else None,
        terrain_bucket=canonical_context_token(
            projection.get("terrain_bucket"))
        if projection.get("terrain_bucket") is not None else None,
        horizon_bucket=horizon_bucket(request),
        ruleset_digest=request.validity.ruleset_digest,
    )


def residual_losses(request):
    losses = tuple(
        (goal_id, max(float(loss), 1e-12))
        for goal_id, loss in request.goal_losses)
    wildcard = max(
        (value for _, value in losses), default=1.0)
    return tuple(sorted(losses + (("*", wildcard),)))


class AbstainingTransitionModel:
    model_id = "grounded-domain-abstention"
    model_version = "1.0"
    immutable_request_safe = True

    def __init__(self, reason="unsupported-action-type"):
        if not isinstance(reason, str) or not reason:
            raise ValueError("abstention model requires a reason")
        self.reason = reason

    def supports(self, request):
        return isinstance(request, DomainEstimateRequest)

    def estimate(self, request):
        return GroundedTransitionEstimate(
            transition=ExpectedTransition(
                operation_id=request.stable_operation_id,
                outcomes=(),
                residual_probability=1.0,
                model_id="{}/{}".format(
                    self.model_id, self.model_version),
                calibration_group="abstain:{}".format(
                    request.action_type),
                residual_goal_losses=residual_losses(request)),
            context_key=context_key_for_request(request),
            authority=EstimateAuthority.ABSTAIN,
            confidence=0.0,
            validity=request.validity,
            estimator_id=self.model_id,
            estimator_version=self.model_version,
            provenance=("explicit-domain-model-abstention",),
            abstention_reason=self.reason,
        )


class DomainTransitionModelRegistry:
    """Select exactly one primary model and any declared shadow models."""

    def __init__(self, fallback_model=None):
        self._models = {}
        self._shadow_models = {}
        self.fallback_model = fallback_model or AbstainingTransitionModel()

    @property
    def registered_action_types(self):
        return tuple(sorted(self._models))

    def register(self, action_type, model, shadow=False):
        action_type = canonical_context_token(action_type)
        target = self._shadow_models if shadow else self._models
        if action_type in target:
            raise ValueError(
                "domain transition model already registered for {}".format(
                    action_type))
        for attribute in ("model_id", "model_version"):
            if not isinstance(getattr(model, attribute, None), str) or not getattr(
                    model, attribute):
                raise TypeError(
                    "domain transition model requires stable {}".format(
                        attribute.replace("_", " ")))
        if (not callable(getattr(model, "supports", None))
                or not callable(getattr(model, "estimate", None))):
            raise TypeError(
                "domain transition model has the wrong interface")
        target[action_type] = model

    @staticmethod
    def _validate(request, model, estimate):
        if not isinstance(estimate, GroundedTransitionEstimate):
            raise TypeError(
                "domain transition model must return GroundedTransitionEstimate")
        if estimate.transition.operation_id != request.stable_operation_id:
            raise ValueError(
                "domain transition operation ID must match stable request identity")
        if estimate.estimator_id != model.model_id:
            raise ValueError(
                "domain transition estimator ID must match selected model")
        if estimate.estimator_version != model.model_version:
            raise ValueError(
                "domain transition estimator version must match selected model")
        if estimate.validity != request.validity:
            raise ValueError(
                "domain transition estimate validity must match request")
        return estimate

    @staticmethod
    def _isolated_request(request, model):
        # Avoid copying a large authoritative snapshot for a model whose exact
        # implementation has been reviewed as immutable-input safe. Trust is
        # intentionally not inherited: a subclass must declare and review its
        # own safety contract.
        trusted = (
            type(model).__dict__.get(
                "immutable_request_safe") is True)
        return request if trusted else copy.deepcopy(request)

    def estimate(self, request):
        if not isinstance(request, DomainEstimateRequest):
            raise TypeError(
                "domain transition registry requires DomainEstimateRequest")
        model = self._models.get(
            canonical_context_token(request.action_type),
            self.fallback_model)
        isolated = self._isolated_request(
            request, model)
        if not model.supports(isolated):
            model = AbstainingTransitionModel(
                "selected-model-declined-context")
        return self._validate(
            request, model, model.estimate(isolated))

    def shadow_estimates(self, request):
        estimates = []
        for action_type, model in sorted(self._shadow_models.items()):
            if action_type != canonical_context_token(
                    request.action_type):
                continue
            isolated = self._isolated_request(
                request, model)
            if model.supports(isolated):
                estimates.append(self._validate(
                    request, model, model.estimate(isolated)))
        return tuple(estimates)
