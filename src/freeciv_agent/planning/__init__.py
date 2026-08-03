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
    CandidateInstantiation,
    CandidateOperationFactory,
    GoalFactory,
    LocalGoalContext,
    ShadowCandidateComparison,
    ShadowOperationCandidate,
    compare_shadow_candidates,
    legacy_shadow_goal_routes,
)
from .fdas_defense import (
    FdasCityDefenseOperationAdapter,
    FdasDefenseActionBinding,
    FdasDefenseLifecycleUpdate,
    FdasDefenseRequirementContext,
)
from .fdas_episodes import (
    CAUSAL_INDUCTION_FEATURE_SCHEMA,
    EPISODE_SCHEMA_VERSION,
    INDUCTION_FEATURE_SCHEMA,
    DecisionEpisode,
    DecisionEpisodeStore,
    FdasDefenseEpisodeRecorder,
)
from .fdas_episode_learning import (
    EpisodeControlPrediction,
    EpisodeLearningExplanation,
    EpisodeLearningMetrics,
    EpisodeLearningResult,
    FdasEpisodeLearningAdapter,
)
from .fdas_episode_induction import (
    CAUSAL_INDUCTION_CONTEXT_KEYS,
    CAUSAL_INDUCTION_FEATURE_KEYS,
    IMMEDIATE_GOAL_RELIEF_TARGET,
    EpisodeInductionHeldoutResult,
    EpisodeInductionResult,
    EpisodeInductionShadowResult,
    EpisodeInductionSpec,
    FdasEpisodeInductionAdapter,
    FdasEpisodeInductionHeldoutGate,
    FdasEpisodeInductionShadow,
    FdasPromotedRuleCandidateImpactEvaluation,
    FdasPromotedRuleCandidateImpactShadow,
    causal_induction_feature_query,
    combine_episode_stores,
)
from .fdas_candidate_choices import (
    CANDIDATE_CHOICE_SCHEMA_VERSION,
    DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES,
    DEFENSE_CANDIDATE_CHOICE_SELECTION_ACTION_TYPES,
    DEFENSE_CANDIDATE_CHOICE_SURFACE,
    FdasCandidateChoice,
    FdasCandidateChoiceCalibrationExport,
    FdasCandidateChoiceSet,
    FdasCandidateChoiceSetRecorder,
    FdasCandidateChoiceSetStore,
    combine_candidate_choice_stores,
    candidate_choice_lineage_id,
    export_candidate_choice_calibration,
    unambiguous_defense_choice_surface_candidates,
)
from .fdas_candidate_calibration import (
    CALIBRATION_MODEL_IDENTITY,
    CANDIDATE_CALIBRATION_SCHEMA_VERSION,
    FdasCandidateCalibrationBin,
    FdasCandidateCalibrationModel,
    FdasCandidateCalibrationPrediction,
    fit_candidate_calibration,
)
from .fdas_candidate_calibration_validation import (
    DEFAULT_VALIDATION_THRESHOLDS,
    VALIDATION_IDENTITY,
    evaluate_candidate_calibration,
    load_candidate_calibration_confirmation,
    load_candidate_calibration_model,
)
from .fdas_calibrated_candidate_union import (
    CALIBRATED_CANDIDATE_UNION_IDENTITY,
    FdasCalibratedCandidateMember,
    FdasCalibratedCandidateReadout,
    FdasCalibratedCandidateUnion,
    build_calibrated_candidate_union,
)
from .fdas_probe_candidate_reachability import (
    PROBE_CANDIDATE_REACHABILITY_IDENTITY,
    FdasProbeCandidateMember,
    FdasProbeCandidateUnion,
    FdasProbeReachabilityReadout,
    build_probe_candidate_union,
)
from .fdas_induction_labels import (
    DURABLE_ACTOR_CITY_DEFENSE_TARGET,
    DURABLE_CITY_COVERAGE_TARGET,
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    LABEL_SCHEMA_VERSION,
    EpisodeInductionOutcomeLabel,
    EpisodeInductionOutcomeLabelStore,
    FdasDefenseActorPersistenceLabeler,
    FdasDefenseDurabilityLabeler,
    FdasSelectedDefenseActorPersistenceLabeler,
    combine_outcome_label_stores,
    delayed_outcome_episode_eligible,
)
from .fdas_observation import (
    FdasObservationActionBinding,
    FdasObservationAuthoritativeReturn,
    FdasObservationCommitValidation,
    FdasObservationExecutionBridge,
    FdasObservationReturnAbstention,
)
from .fdas_replacement import FdasCoordinatedReplacementAdapter
from .fdas_transport import (
    FdasFounderTransportProjectionAdapter,
    declared_transport_intents,
)
from .fdas_combat import FdasCombatProjectionAdapter
from .fdas_expansion import (
    FOUND_CITY_OPERATION,
    RECOVER_POPULATION_OPERATION,
    FdasExpansionLifecycleUpdate,
    FdasExpansionOperationAdapter,
)
from .fdas_commit import (
    FDASCommitBinding,
    FDASCommitValidation,
    FDASCommitValidator,
)
from .fdas_authority import (
    FdasAuthorityReadout,
    FdasBoundedCityAuthority,
    FdasBoundedDefenseAuthority,
)
from .fdas_consolidation import (
    LegacyConsolidationAudit,
    LegacyConsolidationReport,
    LegacyReplacementDecision,
    LegacyReplacementSpec,
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
    "CandidateInstantiation", "CandidateOperationFactory", "GoalFactory",
    "LocalGoalContext",
    "FdasCityDefenseOperationAdapter",
    "FdasDefenseActionBinding", "FdasDefenseLifecycleUpdate",
    "FdasDefenseRequirementContext",
    "CAUSAL_INDUCTION_CONTEXT_KEYS", "CAUSAL_INDUCTION_FEATURE_KEYS",
    "CAUSAL_INDUCTION_FEATURE_SCHEMA",
    "EPISODE_SCHEMA_VERSION", "INDUCTION_FEATURE_SCHEMA",
    "DecisionEpisode", "DecisionEpisodeStore",
    "FdasDefenseEpisodeRecorder",
    "EpisodeControlPrediction", "EpisodeLearningExplanation",
    "EpisodeLearningMetrics", "EpisodeLearningResult",
    "FdasEpisodeLearningAdapter",
    "EpisodeInductionHeldoutResult",
    "IMMEDIATE_GOAL_RELIEF_TARGET",
    "EpisodeInductionResult", "EpisodeInductionShadowResult",
    "EpisodeInductionSpec", "FdasEpisodeInductionAdapter",
    "FdasEpisodeInductionHeldoutGate", "FdasEpisodeInductionShadow",
    "FdasPromotedRuleCandidateImpactEvaluation",
    "FdasPromotedRuleCandidateImpactShadow",
    "causal_induction_feature_query", "combine_episode_stores",
    "CANDIDATE_CHOICE_SCHEMA_VERSION",
    "DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES",
    "DEFENSE_CANDIDATE_CHOICE_SELECTION_ACTION_TYPES",
    "DEFENSE_CANDIDATE_CHOICE_SURFACE",
    "FdasCandidateChoice", "FdasCandidateChoiceSet",
    "FdasCandidateChoiceCalibrationExport",
    "FdasCandidateChoiceSetRecorder", "FdasCandidateChoiceSetStore",
    "combine_candidate_choice_stores",
    "candidate_choice_lineage_id",
    "export_candidate_choice_calibration",
    "unambiguous_defense_choice_surface_candidates",
    "CALIBRATION_MODEL_IDENTITY",
    "CANDIDATE_CALIBRATION_SCHEMA_VERSION",
    "FdasCandidateCalibrationBin", "FdasCandidateCalibrationModel",
    "FdasCandidateCalibrationPrediction", "fit_candidate_calibration",
    "DEFAULT_VALIDATION_THRESHOLDS", "VALIDATION_IDENTITY",
    "evaluate_candidate_calibration",
    "load_candidate_calibration_confirmation",
    "load_candidate_calibration_model",
    "CALIBRATED_CANDIDATE_UNION_IDENTITY",
    "FdasCalibratedCandidateMember", "FdasCalibratedCandidateReadout",
    "FdasCalibratedCandidateUnion", "build_calibrated_candidate_union",
    "DURABLE_ACTOR_CITY_DEFENSE_TARGET", "DURABLE_CITY_COVERAGE_TARGET",
    "DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET",
    "LABEL_SCHEMA_VERSION",
    "EpisodeInductionOutcomeLabel", "EpisodeInductionOutcomeLabelStore",
    "FdasDefenseActorPersistenceLabeler", "FdasDefenseDurabilityLabeler",
    "FdasSelectedDefenseActorPersistenceLabeler",
    "combine_outcome_label_stores", "delayed_outcome_episode_eligible",
    "FdasObservationActionBinding",
    "FdasObservationAuthoritativeReturn",
    "FdasObservationCommitValidation",
    "FdasObservationExecutionBridge",
    "FdasObservationReturnAbstention",
    "FdasCoordinatedReplacementAdapter",
    "FdasFounderTransportProjectionAdapter",
    "declared_transport_intents",
    "FdasCombatProjectionAdapter",
    "FOUND_CITY_OPERATION", "RECOVER_POPULATION_OPERATION",
    "FdasExpansionLifecycleUpdate", "FdasExpansionOperationAdapter",
    "FDASCommitBinding", "FDASCommitValidation", "FDASCommitValidator",
    "FdasAuthorityReadout", "FdasBoundedCityAuthority",
    "FdasBoundedDefenseAuthority",
    "LegacyConsolidationAudit", "LegacyConsolidationReport",
    "LegacyReplacementDecision", "LegacyReplacementSpec",
    "ShadowCandidateComparison", "ShadowOperationCandidate",
    "compare_shadow_candidates", "legacy_shadow_goal_routes",
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
