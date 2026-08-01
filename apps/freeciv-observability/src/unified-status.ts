export type UnifiedStageState = "passed" | "stopped" | "skipped";

export interface UnifiedStageStatus {
  stage: string;
  title: string;
  state: UnifiedStageState;
  scope: string;
}

export const UNIFIED_CONTROLLER_STATUS = {
  statusDate: "2026-07-30",
  supportedController: "scalar-v2 + whole-packet scheduling",
  experimentalController: "GDO-9-gated bridge / source–sink flow advisory",
  authority: "offline · replay · shadow · experimental advisory",
  releaseDecision: "Live authority stopped",
  releaseReason: "Contextual prediction is calibrated, but no B4 route-allocation residual or value-above-cost evidence opens GDO-9.",
  stages: [
    { stage: "S0", title: "frozen baseline", state: "passed",
      scope: "source, fixture, ruleset, runtime, solver, and golden identity" },
    { stage: "S1", title: "scalar PF-v2", state: "passed",
      scope: "typed semantics, risk, signed demand, RequirementSets, whole packets" },
    { stage: "S2", title: "teleology", state: "passed",
      scope: "explicit loss, leverage, typed advantage, metacontrol, calibration ledgers" },
    { stage: "S3", title: "bridge", state: "passed",
      scope: "held-out synthetic and captured-snapshot bridge scope" },
    { stage: "S4", title: "conserved flow", state: "passed",
      scope: "1,024 held-out synthetic cases; shadow integration authorized" },
    { stage: "S5", title: "engine integration", state: "stopped",
      scope: "infrastructure complete; live release gate failed on the primary endpoint" },
    { stage: "S6", title: "native acceleration", state: "skipped",
      scope: "entry criteria were not met; Python remains the semantic oracle" },
  ] satisfies UnifiedStageStatus[],
  confirmation: {
    pairs: 100,
    arms: 200,
    scoreDelta: "+0.05",
    confidenceInterval: "[-0.33, +0.43]",
    exactP: "0.839085",
    signs: "22 improved · 21 declined · 57 tied",
    claim: "No score, gameplay, score-lead, or win-rate claim",
  },
  terminalGuard: {
    pairs: 10,
    guarded: 5,
    terminalDisplacementsAccepted: 0,
    settlementDelta: "0.00",
    scoreResult: "-0.10 [-0.30, 0.00]",
    decision: "Correctness defect closed · no v2 pilot",
  },
  overhead: {
    impactPlanning: "≈220–230 ms / turn",
    fullLoop: "≈266–292 ms / turn",
  },
  evidence: {
    status: "agent-instructions/freeciv_unified_pln_pressure_bridge_fluid_implementation_status.md",
    confirmation: "docs/freeciv/evidence/pf-unified-flow-advisory-confirmatory-v1.md",
    terminalGuard: "docs/freeciv/evidence/pf-unified-flow-advisory-terminal-guard-diagnostic-v2.md",
  },
} as const;
