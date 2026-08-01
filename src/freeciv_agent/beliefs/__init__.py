"""M4 uncertain evidence, provenance, revision, decay, and induction."""
"""Provenance-aware uncertain belief layer (M4)."""

from .inference import UncertainInference
from .memory import OpponentMemory, post_game_calibration
from .rule_engine import (
    DeterministicRuleEngine,
    InferenceOutcome,
    InferenceRequest,
    ProofRecord,
    RuleBinding,
    TypedRuleIndex,
    compare_technology_proof,
)
from .model import (
    BeliefKey,
    ConflictAtom,
    ContextQuarantineOperation,
    Contribution,
    Evidence,
    ModelProvenance,
    Revision,
    UncertainBelief,
)
from .store import (
    BeliefStore,
    ContextQuarantineConflict,
    EvidenceConflict,
    SelfSupportingProof,
)

__all__ = (
    "BeliefKey", "BeliefStore", "ConflictAtom", "ContextQuarantineConflict",
    "ContextQuarantineOperation", "Contribution", "Evidence", "ModelProvenance",
    "DeterministicRuleEngine", "EvidenceConflict", "InferenceOutcome",
    "InferenceRequest", "OpponentMemory", "ProofRecord", "Revision",
    "RuleBinding", "SelfSupportingProof", "TypedRuleIndex", "UncertainBelief",
    "UncertainInference", "compare_technology_proof", "post_game_calibration",
)
