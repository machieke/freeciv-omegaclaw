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
    grounded_operation_result,
    grounded_threat_result,
    VisibleCityThreat,
)
from .legacy import LegacyProjectionTransitionModel
from .movement import GroundedMovementTransitionModel
from .production import (
    GroundedProductionTransitionModel,
    ProductionTargetProfile,
    production_target_profile,
)
from .registry import (
    AbstainingTransitionModel,
    DomainTransitionModelRegistry,
)
from .shadow import DomainEstimateShadowExecutor
from .transport import (
    GroundedTransportTransitionModel,
    TransportUnitProfile,
    transport_unit_profile,
)

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
    "GroundedProductionTransitionModel",
    "GroundedTransportTransitionModel",
    "GroundedCombatTransitionModel",
    "grounded_operation_result",
    "grounded_threat_result",
    "LegacyProjectionTransitionModel",
    "TransitionContextKey",
    "ProductionTargetProfile",
    "TransportUnitProfile",
    "VisibleCityThreat",
    "canonical_model_artifact",
    "finite_duel_distribution",
    "production_target_profile",
    "transport_unit_profile",
]
