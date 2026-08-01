export type GroundedGateState = "passed" | "bounded" | "closed";

export interface GroundedGateStatus {
  id: string;
  title: string;
  state: GroundedGateState;
  result: string;
  evidence: string;
}

export const GROUNDED_PROGRAM_STATUS = {
  statusDate: "2026-07-30",
  programStatus: "Implementation complete",
  supportedComparator: "B4 · grounded bounded exact operation scheduling",
  authorityBoundary: "slice-specific · default-off · exactly revalidated",
  claimBoundary: "Mechanism and prediction claims only; no general score or win-rate claim",
  gates: [
    { id: "GDO-0", title: "Frozen baseline", state: "passed",
      result: "B0/B1 identities, golden replays, engine cohorts, latency, and 1,063-test regression frozen.",
      evidence: "benchmarks/gdo/baseline_manifest.json" },
    { id: "GDO-1", title: "Typed transition envelope", state: "passed",
      result: "Candidate-invariant authority, context, validity, confidence, provenance, unknown mass, and abstention.",
      evidence: "docs/evidence/gdo/gdo1_grounded_transition_shadow.md" },
    { id: "GDO-2", title: "Grounded domain models", state: "passed",
      result: "Movement and combat supported subsets have parity; unsupported mechanics abstain explicitly.",
      evidence: "docs/evidence/gdo/gdo2_grounded_models_shadow.md" },
    { id: "GDO-3", title: "Identity resources", state: "passed",
      result: "Authoritative capacities, current-hard versus conditional-future claims, and deterministic B4 scheduling.",
      evidence: "benchmarks/gdo/gdo3_resource_shadow_diagnostic.json" },
    { id: "GDO-4", title: "City defence", state: "passed",
      result: "30 paired seeds passed operation completion, threat coverage, safety, source, trace, and latency gates.",
      evidence: "benchmarks/gdo/gdo4_city_defense_immediate_fortify_process_isolation_confirmation.json" },
    { id: "GDO-5", title: "Atomic combat", state: "passed",
      result: "Fresh pilot improved the operation mechanism with zero partial activation and bounded material risk.",
      evidence: "benchmarks/gdo/gdo5_combat_material_atomic_repair_engine_pilot.json" },
    { id: "GDO-6", title: "Founder transport", state: "bounded",
      result: "Seat capacity, partnership, routes, lifecycle, replacement, and retention are implemented; fresh embark evidence is absent.",
      evidence: "docs/evidence/gdo/gdo6_transport_input_audit.md" },
    { id: "GDO-7", title: "Production and research", state: "passed",
      result: "Production, research, and city-worker estimators have retained mechanism replays and remain scope-gated.",
      evidence: "docs/evidence/gdo/gdo7a_grounded_production.md" },
    { id: "GDO-8", title: "Contextual calibration", state: "passed",
      result: "Frozen disjoint holdout improved Brier error with complete support; gameplay benefit was not established.",
      evidence: "benchmarks/gdo/gdo8_contextual_engine_confirmation.json" },
    { id: "GDO-9", title: "Bridge / flow re-entry", state: "closed",
      result: "Four of seven prerequisites pass. No B4 route-allocation residual or value-above-cost evidence exists.",
      evidence: "benchmarks/gdo/gdo9_bridge_flow_entry_audit.json" },
  ] satisfies GroundedGateStatus[],
  pilots: {
    cityDefense: {
      pairs: 30,
      operations: "22 / 36 selected operations completed",
      threatDelta: "−389 uncovered city/snapshot observations",
      safety: "0 legality · 0 hard reservation · 0 sole-defender violations",
      latency: "8.76 ms preparation p95",
    },
    combat: {
      completionDelta: "+8.05 pp completion / selection",
      activation: "80 selected · 46 activated · 0 partial activations",
      material: "−0.8874 shield-equivalent residual shift",
      score: "+2.37 [−0.83, +5.80] · descriptive only",
    },
  },
  calibration: {
    trainingArms: 60,
    holdoutArms: 60,
    outcomes: 1831,
    coverage: "100%",
    rawBrier: 0.267491,
    contextualBrier: 0.041237,
    improvement: 0.226254,
    interval: "[0.210036, 0.242391]",
  },
  bridgeFlow: {
    passed: 4,
    total: 7,
    historicalScore: "+0.05 [−0.33, +0.43]",
    overhead: "+291.57 ms / full turn",
    decision: "Live bridge and source–sink flow authority disabled",
  },
} as const;

