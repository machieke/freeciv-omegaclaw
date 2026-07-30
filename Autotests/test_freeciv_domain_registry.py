"""Deterministic grounded domain-model dispatch and abstention."""

import os
import sys
from dataclasses import replace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import ImpactCandidate  # noqa: E402
from freeciv_agent.planning.domain_models import (  # noqa: E402
    DomainEstimateRequest,
    DomainTransitionModelRegistry,
    EstimateAuthority,
    EstimateValidity,
    LegacyProjectionTransitionModel,
)


def _request(
        utility=10.0, request_id="a" * 64,
        action_type="unit_fortify"):
    candidate = ImpactCandidate(
        action={
            "action_type": action_type,
            "actor_id": 7,
        },
        category="city_defense",
        utility=utility,
        rationale="test",
        projection={
            "success_probability": 0.75,
            "next_goal_cost_to_go": {
                "pf-impact:survival": 0.25},
        })
    return DomainEstimateRequest(
        request_id=request_id,
        snapshot={"turn": 8},
        ruleset_ir=None,
        legal_action=dict(candidate.action),
        candidate=candidate,
        goal_losses=(("pf-impact:survival", 1.0),),
        operation_context=None,
        validity=EstimateValidity(
            "game:8", "legal", "ruleset", 8, 8),
        horizon_turn=12)


def test_unregistered_action_abstains_with_explicit_reason():
    estimate = DomainTransitionModelRegistry().estimate(
        _request())

    assert estimate.authority == EstimateAuthority.ABSTAIN
    assert estimate.abstention_reason == "unsupported-action-type"
    assert estimate.transition.residual_probability == 1.0


def test_legacy_wrapper_is_explicitly_proxy_and_deterministic():
    registry = DomainTransitionModelRegistry(
        fallback_model=LegacyProjectionTransitionModel())

    first = registry.estimate(_request())
    second = registry.estimate(_request())

    assert first == second
    assert first.authority == EstimateAuthority.LEGACY_PROXY
    assert first.transition.modeled_probability == 0.75
    assert first.transition.operation_id == (
        "gdo-operation:" + "a" * 64)


def test_duplicate_registration_and_wrong_interface_fail_fast():
    registry = DomainTransitionModelRegistry()
    registry.register(
        "unit_fortify", LegacyProjectionTransitionModel())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(
            "unit_fortify", LegacyProjectionTransitionModel())
    with pytest.raises(TypeError, match="stable model id"):
        registry.register("unit_move", object())


def test_registry_isolates_request_snapshot_from_model_mutation():
    class MutatingLegacy(LegacyProjectionTransitionModel):
        model_id = "mutating-legacy"

        def estimate(self, request):
            request.snapshot["turn"] = 999
            result = super().estimate(request)
            return replace(result, estimator_id=self.model_id)

    request = _request()
    registry = DomainTransitionModelRegistry()
    registry.register("unit_fortify", MutatingLegacy())

    registry.estimate(request)

    assert request.snapshot == {"turn": 8}
