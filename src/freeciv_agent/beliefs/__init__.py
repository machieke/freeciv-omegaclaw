"""M4 uncertain evidence, provenance, revision, decay, and induction."""
"""Provenance-aware uncertain belief layer (M4)."""

from .inference import UncertainInference
from .memory import OpponentMemory, post_game_calibration
from .model import (
    BeliefKey,
    ConflictAtom,
    ContextQuarantineOperation,
    Contribution,
    Evidence,
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
    "ContextQuarantineOperation", "Contribution", "Evidence",
    "EvidenceConflict", "OpponentMemory", "Revision", "SelfSupportingProof",
    "UncertainBelief", "UncertainInference", "post_game_calibration",
)
