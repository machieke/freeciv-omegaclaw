import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScalabilityDashboard } from "../ScalabilityDashboard";
import type { ScalingEvidence } from "../scalability";

const surface = (gate: string) => ({
  absolute_labels: {
    "research-usable": { p95: 123, sample_count: 1, status: "not-entered" },
  },
  exponent: 1.1, exponent_95_ci: [1, 1.2], gate,
  maximum_exponent: 1.35, points: [[100, 10], [1000, 100]],
});

const evidence: ScalingEvidence = {
  aggregate: {
    engine_shadow: { gate: "not-entered", pair_count: 0 },
    phase_reports: {
      discovery: {
        captured: { gate: "not-entered", maximum_rss_ratio: 0.48,
          maximum_timing_ratio: 1.14, paired_trials: 1 },
        combined: { gate: "not-entered", paired_trials: 0 },
        gates: { atomspace: "fail", bridge: "not-entered", fluid: "pass", proof: "not-entered" },
        surfaces: { atomspace: surface("fail"), bridge: surface("not-entered"),
          fluid: surface("pass"), proof: { ...surface("not-entered"), fit_trial_ids: [] } },
      },
      heldout: {
        captured: { gate: "not-entered", paired_trials: 0 },
        combined: { gate: "not-entered", paired_trials: 0 },
        gates: { atomspace: "not-entered", bridge: "not-entered",
          fluid: "not-entered", proof: "not-entered" },
        surfaces: { atomspace: surface("not-entered"), bridge: surface("not-entered"),
          fluid: surface("not-entered"), proof: surface("not-entered") },
      },
    },
  },
  audit: { semantic_failures: ["pre-fix bridge failure"], valid: true },
  claims: { cell_accounting: [], frozen: false, g9_complete: false, heldout_result_count: 0 },
  discovery: [{
    actual_work: { live_revision_atoms: 25000, scopes: 250, supports: 25000 },
    correctness: {}, metrics: { incremental_ms: 100, peak_rss_bytes: 1024 ** 2 },
    status: "completed", trial_id: "trial-a2",
    trial: { arm: "kernel", phase: "discovery", source_identity: "source",
      cell: { parameters: {}, seed: 1, surface: "atomspace", tier: "A2" } },
  }, {
    actual_work: { indexed_distractor_rules: 10_000, relevant_rules: 999 },
    correctness: {}, metrics: { kernel_elapsed_ms: 100, peak_rss_bytes: 1024 ** 2 },
    status: "completed", trial_id: "trial-proof-stress",
    trial: { arm: "kernel", phase: "discovery", source_identity: "source",
      cell: { parameters: { shape: "and_tree" }, seed: 1, surface: "proof", tier: "P1" } },
  }],
  environment: { git_commit: "1234567890abcdef", git_dirty: true, machine: "x86_64" },
  frozen: null, heldout: [], preregistration: {},
};

describe("scalability dashboard", () => {
  it("keeps discovery evidence distinct from an empty held-out cohort", () => {
    render(<ScalabilityDashboard initialData={evidence} />);
    expect(screen.getByRole("heading", { name: "Scalability campaign" })).toBeInTheDocument();
    expect(screen.getByText(/25.0k atoms/)).toBeInTheDocument();
    expect(screen.getByText(/integrity valid · 1 retained semantic failures/)).toBeInTheDocument();
    expect(screen.queryByText(/999 relevant/)).not.toBeInTheDocument();
    expect(screen.getByText(/Screening evidence can find defects/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "held-out" }));

    expect(screen.getByText(/Frozen cells may enter a claim/)).toBeInTheDocument();
    expect(screen.getAllByText("not entered").length).toBeGreaterThan(0);
  });

  it("publishes natural engine volume, overhead, mechanisms, and synthetic transfer", () => {
    const entered = structuredClone(evidence);
    entered.aggregate.engine_shadow = {
      engine_shadow_scenario: {
        horizon_turn: 30, minimum_pairs: 20,
        release_game_config: { fogofwar: false, startunits: "ccccxxxxxxxxdddddddd" },
        scenario_id: "scalability-v1-high-entity-he1",
      },
      gate: "pass", pair_count: 20, source_report_hash: "abcdef1234567890", valid: true,
      maximum_volume: {
        atoms: 12500, bridge_nodes: 144, cities: 4, concurrent_goals: 5,
        control_edges: 240, control_nodes: 90, events: 32000, flow_iterations: 24,
        grounded_candidates: 18, legal_actions: 402, proof_chain_depth: 7,
        proof_tree_size: 31, region_scopes: 6, scopes: 44, supports: 17300, units: 24,
      },
      performance: {
        controller_latency_ms: { maximum_ms: 81, p95_ms: 42 },
        controller_process_peak_rss_bytes: { maximum_bytes: 256 * 1024 ** 2, p95_bytes: 240 * 1024 ** 2 },
        fdas_projection_latency_ms: { count: 600, p95_ms: 8.5 },
        fdas_turn_contribution_ms: { p95_ms: 12.2 },
      },
      synthetic_transfer: {
        entered: true,
        latency_ratio_engine_fdas_projection_p95_to_synthetic_incremental_p95: 1.24,
        memory_ratio_engine_controller_rss_p95_to_synthetic_process_rss_p95: 0.82,
        nearest_synthetic_tier: "A1", nearest_synthetic_work_atoms: 10000,
      },
      totals: {
        bridge_event_count: 600, cold_verification_count: 20,
        controller_fallback_count: 0, decision_count: 600, explained_legacy_count: 592,
        extra_fdas_count: 12, flow_event_count: 600, flow_projection_count: 3000,
        full_detail_pair_count: 1, revision_count: 600,
      },
      volume_expansion: {
        atoms: { achieved: 12500, passed: true, reference: 1196 },
        cities: { achieved: 4, passed: true, reference: 3 },
      },
    };
    render(<ScalabilityDashboard initialData={entered} />);

    expect(screen.getByRole("heading", { name: "Engine-backed shadow confirmation" })).toBeInTheDocument();
    expect(screen.getByText("scalability-v1-high-entity-he1")).toBeInTheDocument();
    expect(screen.getByText("12.5k")).toBeInTheDocument();
    expect(screen.getByText("1.24× latency · 0.82× memory")).toBeInTheDocument();
    expect(screen.getByText("8.5 ms")).toBeInTheDocument();
    expect(screen.getAllByText("expanded")).toHaveLength(2);
  });
});
