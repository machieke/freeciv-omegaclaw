"""M3 proof-to-plan scheduling and linear resource ledgers."""
"""Proof-to-plan scheduling with explicit resources and deterministic artifacts."""

from .bounded import ProductionGoal, ProductionScheduler
from .impact import (DeferredImpactOutcomeLedger, DeferredImpactResolution,
                     GroundedGoalRelief, GroundedImpactPlanner,
                     ImpactCandidate, ImpactDecision, ImpactTurnBudget)
from .impact_flow_adapter import (
    CONTROLLER_MODES,
    AdvisoryDisagreement,
    AdvisoryPolicy,
    BridgeScalarImpactController,
    CanonicalUtilityController,
    ControlDecision,
    ControlOutcomeRecord,
    ControlQuery,
    ImpactControlAdapter,
    LegacyImpactPressureController,
    ScalarV2Controller,
    ShadowBudgetConfig,
    UnifiedFlowController,
)
from .commit_validator import (
    ImpactCommitValidator,
    ValidationDisposition,
    ValidationResult,
)
from .live_activation import (
    ControllerRollback,
    LimitedLiveActivationGate,
    LiveActivationResult,
    LiveScopePolicy,
    PairedCohortEvidence,
    RollbackResult,
)
from .decision_explainer import (
    ActionExplanation,
    AttentionExplanation,
    BeliefExplanation,
    DecisionExplainer,
)
from .control_events import (
    CONTROL_EVENT_SCHEMA_VERSION,
    ControlEventEmitter,
)
from .operation_assembler import (
    assemble_city_defense_operation,
)
from .combat_operations import (
    CombatOperationAssembler,
    CombatOperationAssembly,
    CombatOperationReadout,
    ConditionalProbabilityInterval,
    combat_target_capacities,
    conditional_success_interval,
)
from .combat_lifecycle import (
    CombatLifecycleUpdate,
    CombatOperationLifecycle,
)
from .transport_operations import (
    FounderTransportIntent,
    FounderTransportOperationAssembler,
    FounderTransportOperationAssembly,
    TransportOperationAssemblyDecision,
    TransportOperationReadout,
)
from .transport_lifecycle import (
    FounderTransportOperationLifecycle,
    SettlementRetentionResult,
    SettlementRetentionTracker,
    TransportLifecycleUpdate,
    TransportRepairDecision,
)
from .production_operations import (
    ProductionEnablingIntent,
    ProductionEnablingOperationAssembler,
    ProductionOperationAssembly,
    ProductionOperationReadout,
)
from .production_lifecycle import (
    ProductionLifecycleUpdate,
    ProductionOperationLifecycle,
)
from .research_operations import (
    ResearchEnablingIntent,
    ResearchEnablingOperationAssembler,
    ResearchOperationAssembly,
    ResearchOperationReadout,
)
from .research_lifecycle import (
    ResearchLifecycleUpdate,
    ResearchOperationLifecycle,
)
from .city_worker_macro import (
    CityWorkerMacroAssembler,
    CityWorkerMacroAssembly,
    CityWorkerMacroIntent,
    CityWorkerMacroResult,
)
from .operation_store import (
    OPERATION_STORE_SCHEMA_VERSION,
    OperationRecord,
    OperationStore,
    OperationStoreError,
    OperationTransitionError,
)
from .fdas import (
    CandidateOperationFactory,
    GoalFactory,
    LocalGoalContext,
    ShadowCandidateComparison,
    ShadowOperationCandidate,
    compare_shadow_candidates,
)
from .fdas_defense import (
    FdasCityDefenseOperationAdapter,
    FdasDefenseActionBinding,
    FdasDefenseLifecycleUpdate,
    FdasDefenseRequirementContext,
)
from .fdas_episodes import (
    EPISODE_SCHEMA_VERSION,
    DecisionEpisode,
    DecisionEpisodeStore,
    FdasDefenseEpisodeRecorder,
)
from .fdas_replacement import FdasCoordinatedReplacementAdapter
from .fdas_transport import FdasFounderTransportProjectionAdapter
from .fdas_combat import FdasCombatProjectionAdapter
from .fdas_commit import (
    FDASCommitBinding,
    FDASCommitValidation,
    FDASCommitValidator,
)
from .operations import (
    OPERATION_SCHEMA_VERSION,
    TERMINAL_OPERATION_STATES,
    OperationAuthorityKind,
    OperationAuthorityReadout,
    OperationParticipant,
    OperationProgress,
    OperationSpec,
    OperationState,
    OperationStep,
    operation_id_from_components,
    operation_transition_allowed,
)
from .impact_unified_flow import (
    UnifiedImpactFlowConfig,
    UnifiedImpactFlowEngine,
)
from .model import (BranchScore, NonPlan, Plan, PlanAssumption, PlanStep,
                    PlanningSnapshot, ResourceLedger, ResourceLedgerEntry)
from .scheduler import ProofScheduler, research_duration_turns, validate_next_step

__all__ = [
    "BranchScore", "NonPlan", "Plan", "PlanAssumption", "PlanStep",
    "DeferredImpactOutcomeLedger", "DeferredImpactResolution",
    "GroundedGoalRelief", "GroundedImpactPlanner", "ImpactCandidate",
    "ImpactDecision", "ImpactTurnBudget",
    "CONTROLLER_MODES", "BridgeScalarImpactController",
    "AdvisoryDisagreement", "AdvisoryPolicy",
    "CanonicalUtilityController", "ControlDecision",
    "ControlOutcomeRecord", "ControlQuery", "ImpactControlAdapter",
    "LegacyImpactPressureController", "ScalarV2Controller",
    "ShadowBudgetConfig",
    "UnifiedFlowController",
    "ImpactCommitValidator", "ValidationDisposition",
    "ValidationResult",
    "ControllerRollback", "LimitedLiveActivationGate",
    "LiveActivationResult", "LiveScopePolicy",
    "PairedCohortEvidence", "RollbackResult",
    "ActionExplanation", "AttentionExplanation",
    "BeliefExplanation", "DecisionExplainer",
    "CONTROL_EVENT_SCHEMA_VERSION",
    "ControlEventEmitter",
    "OPERATION_SCHEMA_VERSION",
    "OPERATION_STORE_SCHEMA_VERSION",
    "TERMINAL_OPERATION_STATES",
    "OperationAuthorityKind", "OperationAuthorityReadout",
    "OperationParticipant", "OperationProgress",
    "OperationRecord", "OperationSpec", "OperationState",
    "OperationStep", "OperationStore", "OperationStoreError",
    "OperationTransitionError",
    "assemble_city_defense_operation",
    "CombatOperationAssembler", "CombatOperationAssembly",
    "CombatOperationReadout", "ConditionalProbabilityInterval",
    "CityWorkerMacroAssembler", "CityWorkerMacroAssembly",
    "CityWorkerMacroIntent", "CityWorkerMacroResult",
    "CandidateOperationFactory", "GoalFactory", "LocalGoalContext",
    "FdasCityDefenseOperationAdapter",
    "FdasDefenseActionBinding", "FdasDefenseLifecycleUpdate",
    "FdasDefenseRequirementContext",
    "EPISODE_SCHEMA_VERSION", "DecisionEpisode", "DecisionEpisodeStore",
    "FdasDefenseEpisodeRecorder",
    "FdasCoordinatedReplacementAdapter",
    "FdasFounderTransportProjectionAdapter",
    "FdasCombatProjectionAdapter",
    "FDASCommitBinding", "FDASCommitValidation", "FDASCommitValidator",
    "ShadowCandidateComparison", "ShadowOperationCandidate",
    "compare_shadow_candidates",
    "CombatLifecycleUpdate", "CombatOperationLifecycle",
    "combat_target_capacities", "conditional_success_interval",
    "FounderTransportIntent",
    "FounderTransportOperationAssembler",
    "FounderTransportOperationAssembly",
    "TransportOperationAssemblyDecision",
    "TransportOperationReadout",
    "FounderTransportOperationLifecycle",
    "SettlementRetentionResult",
    "SettlementRetentionTracker",
    "TransportLifecycleUpdate",
    "TransportRepairDecision",
    "ProductionEnablingIntent",
    "ProductionEnablingOperationAssembler",
    "ProductionOperationAssembly",
    "ProductionOperationReadout",
    "ProductionLifecycleUpdate",
    "ProductionOperationLifecycle",
    "ResearchEnablingIntent",
    "ResearchEnablingOperationAssembler",
    "ResearchOperationAssembly",
    "ResearchOperationReadout",
    "ResearchLifecycleUpdate",
    "ResearchOperationLifecycle",
    "operation_id_from_components",
    "operation_transition_allowed",
    "UnifiedImpactFlowConfig",
    "UnifiedImpactFlowEngine",
    "PlanningSnapshot",
    "ProductionGoal", "ProductionScheduler", "ProofScheduler",
    "ResourceLedger", "ResourceLedgerEntry", "research_duration_turns", "validate_next_step",
]
