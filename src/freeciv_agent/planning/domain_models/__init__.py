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
from .city_workers import (
    CITY_OUTPUT_NAMES,
    GroundedCityWorkerTransitionModel,
    city_output_vector,
)
from .context import (
    EstimateAuthority,
    EstimateValidity,
    GroundedTransitionEstimate,
    TransitionContextKey,
    canonical_model_artifact,
)
from .defense import (
    CITY_DEFENSE_LIVE_OPERATION_TYPES,
    CityDefenseAnalysis,
    CityDefenseAnalyzer,
    CityDefenseAssignment,
    CityDefenseOperation,
    CityDefenseRequirement,
    DefenderProfile,
    DefenseOperationType,
    ExactCityDefenseAssignmentSolver,
    build_city_defense_assignment_artifact,
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
from .research import (
    GroundedResearchTransitionModel,
    ResearchDependencyProfile,
    research_dependency_profile,
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
    "CITY_DEFENSE_LIVE_OPERATION_TYPES",
    "CityDefenseAnalysis",
    "CityDefenseAnalyzer",
    "CityDefenseAssignment",
    "CityDefenseOperation",
    "CityDefenseRequirement",
    "CITY_OUTPUT_NAMES",
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
    "build_city_defense_assignment_artifact",
    "GroundedTransitionEstimate",
    "GroundedCityWorkerTransitionModel",
    "GroundedMovementTransitionModel",
    "GroundedProductionTransitionModel",
    "GroundedResearchTransitionModel",
    "GroundedTransportTransitionModel",
    "GroundedCombatTransitionModel",
    "grounded_operation_result",
    "grounded_threat_result",
    "LegacyProjectionTransitionModel",
    "TransitionContextKey",
    "ProductionTargetProfile",
    "ResearchDependencyProfile",
    "TransportUnitProfile",
    "VisibleCityThreat",
    "canonical_model_artifact",
    "city_output_vector",
    "finite_duel_distribution",
    "production_target_profile",
    "research_dependency_profile",
    "transport_unit_profile",
]
