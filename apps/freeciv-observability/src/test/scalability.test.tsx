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
});
