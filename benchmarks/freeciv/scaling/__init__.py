"""Reproducible scalability experiments for FDAS, proof, bridge, and flow."""

from .atomspace_generator import (
    AtomSpaceCase,
    AtomSpaceChurnResult,
    apply_atomspace_churn,
    build_atomspace_case,
)
from .baseline import BaselineVerification, verify_frozen_baseline
from .captured_amplifier import CapturedAmplification, amplify_captured_records
from .captured_loader import CapturedRevision, load_captured_revisions
from .bridge_generator import (
    BridgeCase,
    CorrectedProbeReadoutEvaluation,
    PathPersistenceEvaluation,
    ProtectedReadoutEvaluation,
    SourceSinkFlowEvaluation,
    apply_bridge_edge_failure,
    build_bridge_case,
    evaluate_bridge_case,
    evaluate_corrected_probe_readout,
    evaluate_path_persistence,
    evaluate_protected_readout,
    evaluate_scalar_readout,
    evaluate_source_sink_flow_readout,
)
from .fluid_generator import (
    FluidCase,
    apply_fluid_edge_failures,
    build_fluid_case,
    build_fluid_graph_case,
    run_fluid_case,
)
from .model import ScaleCell, TrialResult, TrialSpec
from .proof_generator import (
    ProofCase,
    build_proof_case,
    build_proof_dag_case,
    evaluate_proof_case,
)
from .retention import RetentionCycleResult, run_retention_cycles

__all__ = (
    "AtomSpaceCase",
    "AtomSpaceChurnResult",
    "BaselineVerification",
    "BridgeCase",
    "CapturedAmplification",
    "CapturedRevision",
    "CorrectedProbeReadoutEvaluation",
    "FluidCase",
    "PathPersistenceEvaluation",
    "ProofCase",
    "ProtectedReadoutEvaluation",
    "RetentionCycleResult",
    "SourceSinkFlowEvaluation",
    "ScaleCell",
    "TrialResult",
    "TrialSpec",
    "apply_atomspace_churn",
    "apply_bridge_edge_failure",
    "apply_fluid_edge_failures",
    "amplify_captured_records",
    "load_captured_revisions",
    "build_atomspace_case",
    "build_bridge_case",
    "build_fluid_case",
    "build_fluid_graph_case",
    "build_proof_case",
    "build_proof_dag_case",
    "evaluate_bridge_case",
    "evaluate_corrected_probe_readout",
    "evaluate_path_persistence",
    "evaluate_protected_readout",
    "evaluate_scalar_readout",
    "evaluate_source_sink_flow_readout",
    "evaluate_proof_case",
    "run_fluid_case",
    "run_retention_cycles",
    "verify_frozen_baseline",
)
