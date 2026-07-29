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
    "PlanningSnapshot",
    "ProductionGoal", "ProductionScheduler", "ProofScheduler",
    "ResourceLedger", "ResourceLedgerEntry", "research_duration_turns", "validate_next_step",
]
