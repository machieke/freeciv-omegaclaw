"""Grounded, candidate-invariant Freeciv transition estimates."""

from .base import (
    CandidateDomainFeatures,
    DomainEstimateRequest,
    DomainTransitionModel,
)
from .combat import GroundedCombatTransitionModel
from .combat_rules import (
    DuelDistribution,
    DuelTerminalOutcome,
    finite_duel_distribution,
)
from .context import (
    EstimateAuthority,
    EstimateValidity,
    GroundedTransitionEstimate,
    TransitionContextKey,
    canonical_model_artifact,
)
from .legacy import LegacyProjectionTransitionModel
from .movement import GroundedMovementTransitionModel
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
    "DuelDistribution",
    "DuelTerminalOutcome",
    "DomainEstimateShadowExecutor",
    "EstimateAuthority",
    "EstimateValidity",
    "GroundedTransitionEstimate",
    "GroundedMovementTransitionModel",
    "GroundedCombatTransitionModel",
    "LegacyProjectionTransitionModel",
    "TransitionContextKey",
    "canonical_model_artifact",
    "finite_duel_distribution",
]
