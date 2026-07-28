import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { PlnResult } from "../../../../schemas/freeciv-events/v1/types.generated";
import {
  EconomyProductionDashboard, ProofExplorer, TechnologyDashboard,
  UnitLifecycleDashboard,
} from "../App";
import { foldEvents } from "../store";
import { event } from "./helpers";

const hash = "a".repeat(64);
const government = {
  available: true, current_id: 0, current_name: "Anarchy",
  target_id: 0, target_name: "Anarchy", revolution_finishes: 20,
  in_revolution: true, selection_required: true, diagnostic: null,
};
const catalog = event(1, "technology_catalog", {
  catalog_id: "civ2civ3:test", ruleset: "civ2civ3", ir_hash: hash,
  technologies: [
    { name: "Industrialization", rule_id: "tech:industrialization",
      prerequisites: ["Banking", "Railroad"] },
    { name: "The Corporation", rule_id: "tech:corporation",
      prerequisites: ["Economics", "Industrialization"] },
    { name: "Banking", rule_id: "tech:banking", prerequisites: [] },
    { name: "Railroad", rule_id: "tech:railroad", prerequisites: [] },
    { name: "Economics", rule_id: "tech:economics", prerequisites: [] },
  ],
}, 1, 1);
const progress = event(2, "technology_progress", {
  snapshot_id: "snapshot-20", available: true,
  known_techs: ["Banking", "Railroad", "Economics"],
  researchable_techs: ["Industrialization"],
  blocked_technologies: [{
    name: "The Corporation", missing_prerequisites: ["Industrialization"],
  }],
  acquired_techs: [], status: "stalled", stalled_turns: 6,
  stall_reason: "government_anarchy", government,
  target: {
    id: 36, name: "Industrialization", progress: 1115, cost: 1140,
    remaining: 25, beakers_per_turn: 0, eta_turns: null,
  },
}, 20, 1);
const frozenProgress = event(6, "technology_progress", {
  snapshot_id: "snapshot-21", available: true,
  known_techs: ["Banking", "Railroad", "Economics"],
  researchable_techs: ["Industrialization"],
  blocked_technologies: [{
    name: "The Corporation", missing_prerequisites: ["Industrialization"],
  }],
  acquired_techs: [], status: "stalled", stalled_turns: 1,
  stall_reason: "research_progress_not_advancing", government: {
    ...government, current_id: 3, current_name: "Republic",
    target_id: 3, target_name: "Republic", revolution_finishes: null,
    in_revolution: false, selection_required: false,
  },
  target: {
    id: 36, name: "Industrialization", progress: 1115, cost: 1140,
    remaining: 25, beakers_per_turn: 41, eta_turns: 1,
  },
}, 21, 1);
const production = event(3, "production_state", {
  snapshot_id: "snapshot-20", government,
  economy: {
    available: true, gold: 50, gold_per_turn: 1,
    city_gold_surplus_per_turn: 4, unit_gold_upkeep: 3,
    gold_upkeep_reserve: 3, gold_upkeep_style: "Mixed",
    tax_rate: 40, science_rate: 60, luxury_rate: 0,
  },
  cities: [{
    city_id: 101, name: "Roma", size: 3, food_stock: 11, shield_stock: 19,
    outputs: { food: 5, shield: 4, trade: 2, gold: 1, luxury: 0, science: 1 },
    surplus: { food: 3, shield: 4, trade: 2, gold: 1, luxury: 0, science: 1 },
    target: { kind: 6, value: 10, name: "Riflemen" },
    buildable_count: 32, had_famine: true,
    governor: {
      available: true, enabled: true,
      minimal_surplus: [1, 0, 0, 0, 0, 0],
      factor: [6, 2, 2, 1, 1, 2],
      require_happy: false, allow_disorder: false, max_growth: false,
      allow_specialists: true, happy_factor: 0,
    },
    mood: {
      final: { happy: 0, content: 1, unhappy: 2, angry: 0 },
      stages: { happy: [0], content: [1], unhappy: [2], angry: [0] },
      disorder: true, margin: -2, was_happy: false,
    },
    support: { count: 3, food: 1, shield: 2, gold: 0 },
  }],
}, 20, 2);
const lifecycle = event(4, "unit_lifecycle", {
  lifecycle_id: "life-7", transition: "disappeared", unit_id: 7,
  unit_type: "Riflemen", cause: "unknown_turn_boundary",
  evidence_quality: "unattributed", from_snapshot_id: "snapshot-19",
  to_snapshot_id: "snapshot-20", evidence_event_ids: ["state-19", "state-20"],
  detail: "The unit vanished between snapshots; this trace contains no causal removal packet.",
}, 20, 3);
const upkeepLoss = event(5, "unit_lifecycle", {
  lifecycle_id: "life-8", transition: "disappeared", unit_id: 8,
  unit_type: "Settlers", cause: "upkeep_food",
  evidence_quality: "exact", from_snapshot_id: "snapshot-19",
  to_snapshot_id: "snapshot-20", evidence_event_ids: ["state-20"],
  detail: "Freeciv server notification: Famine feared in Roma, Settlers lost!",
}, 20, 4);
const state = foldEvents(
  [catalog, progress, production, lifecycle, upkeepLoss],
  { turn: 20, seq: 4 },
);

describe("typed domain observability", () => {
  it("shows stalled research, exact prerequisite status, and the ruleset graph", () => {
    render(<TechnologyDashboard state={state} onSelect={() => undefined} />);
    expect(screen.getByText("Industrialization", { selector: ".research-hero h3" }))
      .toBeInTheDocument();
    expect(screen.getByText("6 turns")).toBeInTheDocument();
    expect(screen.getByText(
      /projected rate is 0 per turn and the observed turn-boundary rate is unknown/i,
    )).toBeInTheDocument();
    expect(screen.getByText(/Freeciv is waiting for a government selection/i))
      .toBeInTheDocument();
    expect(screen.getByText(/PF-PLN now prioritizes/i)).toBeInTheDocument();
    expect(screen.getByText(/A technology with unmet prerequisites appears as/i))
      .toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Prerequisite graph for Industrialization/i }))
      .toBeInTheDocument();
  });

  it("explains an authoritative research counter that stopped advancing", () => {
    const frozenState = foldEvents(
      [catalog, progress, frozenProgress],
      { turn: 21, seq: 1 },
    );
    render(<TechnologyDashboard state={frozenState} onSelect={() => undefined} />);
    expect(screen.getByText(/authoritative research total did not advance/i))
      .toBeInTheDocument();
    expect(screen.getByText(/treasury bankruptcy/i)).toBeInTheDocument();
  });

  it("shows named yields, city stocks, queues, and model coverage", () => {
    render(<EconomyProductionDashboard state={state} onSelect={() => undefined} />);
    expect(screen.getByText("Riflemen")).toBeInTheDocument();
    expect(screen.getByText("shield stock")).toBeInTheDocument();
    expect(screen.getByText("19")).toBeInTheDocument();
    expect(screen.getByText("disorder")).toBeInTheDocument();
    expect(screen.getByText(/1 food · 2 shields · 0 gold/i)).toBeInTheDocument();
    expect(screen.getByText(/server reported famine this turn/i)).toBeInTheDocument();
    expect(screen.getByText("net cash flow")).toBeInTheDocument();
    expect(screen.getByText("city gold surplus")).toBeInTheDocument();
    expect(screen.getByText(/Mixed upkeep style/i)).toBeInTheDocument();
    expect(screen.getByText("unit upkeep")).toBeInTheDocument();
    expect(screen.getByText(/planner reserve satisfied/i)).toBeInTheDocument();
    expect(screen.getByText("food governor")).toBeInTheDocument();
    expect(screen.getByText(/packet floor 1 · food weight 6/i)).toBeInTheDocument();
    expect(screen.getAllByText(/PF goal not logged/i)).toHaveLength(4);
    expect(screen.getByText(/No buildable PLN query was logged/i)).toBeInTheDocument();
  });

  it("shows disappearance cause and evidence quality without upgrading it", () => {
    render(<UnitLifecycleDashboard state={state} onSelect={() => undefined} />);
    expect(screen.getAllByText("unattributed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Unknown Turn Boundary").length).toBeGreaterThan(0);
    expect(screen.getAllByText("exact").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Upkeep Food").length).toBeGreaterThan(0);
    expect(screen.getByText(/insufficient-gold disbands/i)).toBeInTheDocument();
  });

  it("keeps future domain events out of an earlier cursor", () => {
    const earlier = foldEvents(
      [catalog, progress, production, lifecycle, upkeepLoss],
      { turn: 1, seq: 1 },
    );
    expect(earlier.technologyCatalogs).toHaveLength(1);
    expect(earlier.technologyProgress).toHaveLength(0);
    expect(earlier.productionStates).toHaveLength(0);
    expect(earlier.unitLifecycles).toHaveLength(0);
  });
});

const proof = (queryId: string, status: PlnResult["status"], atomId: string): PlnResult => ({
  query_id: queryId, status, chain_depth: 1, latency_ms: 1, dampening_lambda: null,
  proof: {
    root_node_id: `${atomId}-node`, structural_hash: hash,
    nodes: [{
      node_id: `${atomId}-node`, kind: "goal",
      atom: {
        atom_id: atomId, predicate: "researchable", args: [0, atomId],
        tv: { strength: status === "PROVED" ? 1 : 0, confidence: 0.99 },
        crisp: true, provenance_ids: [],
      },
      tv: { strength: status === "PROVED" ? 1 : 0, confidence: 0.99 },
      crisp: true, satisfied: status === "PROVED", rule_applied: null,
      premise_node_refs: [], subtree_hash: hash,
    }],
  },
  unsatisfied_frontier: status === "PROVED" ? [] : [{
    node_id: `${atomId}-node`, blocker_type: "missing-tech",
    atom_id: atomId, detail: `${atomId} is not yet known`,
  }],
});

it("defaults Proof Explorer to the latest proof and labels historical selection", async () => {
  const user = userEvent.setup();
  const firstResult = proof("turn-one-proof", "BLOCKED", "Industrialization");
  const latestResult = proof("turn-227-proof", "PROVED", "The Corporation");
  const first = event(10, "pln_result",
    firstResult as unknown as Record<string, unknown>, 1, 0);
  const latest = event(11, "pln_result",
    latestResult as unknown as Record<string, unknown>, 227, 0);
  const proofState = foldEvents([first, latest], { turn: 240, seq: 100 });
  render(<ProofExplorer state={proofState} onSelect={() => undefined} />);
  expect(screen.getByText("Current proof at cursor")).toBeInTheDocument();
  expect(screen.getByText(/PLN boundary \/ PROVED/i)).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Proof"), first.event_id);
  expect(screen.getByText("Historical proof selected")).toBeInTheDocument();
  expect(screen.getByText((_, element) => Boolean(
    element?.classList.contains("frontier-definition")
    && element.textContent?.includes("means the named technology"))))
    .toBeInTheDocument();
});
