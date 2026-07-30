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
from .defense import (
    CityDefenseAnalysis,
    CityDefenseAnalyzer,
    CityDefenseAssignment,
    CityDefenseOperation,
    CityDefenseRequirement,
    DefenderProfile,
    DefenseOperationType,
    ExactCityDefenseAssignmentSolver,
    VisibleCityThreat,
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
    "CityDefenseAnalysis",
    "CityDefenseAnalyzer",
    "CityDefenseAssignment",
    "CityDefenseOperation",
    "CityDefenseRequirement",
    "DomainEstimateRequest",
    "DomainTransitionModel",
    "DomainTransitionModelRegistry",
    "DefenderProfile",
    "DefenseOperationType",
    "DuelDistribution",
    "DuelTerminalOutcome",
    "DomainEstimateShadowExecutor",
    "EstimateAuthority",
    "EstimateValidity",
    "ExactCityDefenseAssignmentSolver",
    "GroundedTransitionEstimate",
    "GroundedMovementTransitionModel",
    "GroundedCombatTransitionModel",
    "LegacyProjectionTransitionModel",
    "TransitionContextKey",
    "VisibleCityThreat",
    "canonical_model_artifact",
    "finite_duel_distribution",
]
