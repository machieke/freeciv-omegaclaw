"""Grounded, candidate-invariant Freeciv transition estimates."""

from .base import (
    CandidateDomainFeatures,
    DomainEstimateRequest,
    DomainTransitionModel,
)
from .context import (
    EstimateAuthority,
    EstimateValidity,
    GroundedTransitionEstimate,
    TransitionContextKey,
)
from .legacy import LegacyProjectionTransitionModel
from .registry import (
    AbstainingTransitionModel,
    DomainTransitionModelRegistry,
)
from .shadow import DomainEstimateShadowExecutor

__all__ = [
    "AbstainingTransitionModel",
    "CandidateDomainFeatures",
    "DomainEstimateRequest",
    "DomainTransitionModel",
    "DomainTransitionModelRegistry",
    "DomainEstimateShadowExecutor",
    "EstimateAuthority",
    "EstimateValidity",
    "GroundedTransitionEstimate",
    "LegacyProjectionTransitionModel",
    "TransitionContextKey",
]
