import { performance } from "node:perf_hooks";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import type { PlnResult, ProofNode } from "../../../../schemas/freeciv-events/v1/types.generated";
import { ProofExplorer } from "../App";
import type { ReplayState, TraceEvent } from "../events";
import { atom, event } from "./helpers";

it("renders a 200-node DOM-selectable proof in under 300 ms", () => {
  const nodes: ProofNode[] = Array.from({ length: 200 }, (_, index) => ({
    atom: atom(`proof-${index}`, 1, 0.99), crisp: false,
    kind: index === 0 ? "goal" : "premise", node_id: `node-${index}`,
    premise_node_refs: index === 0 ? Array.from({ length: 199 }, (__, child) => `node-${child + 1}`) : [],
    rule_applied: index === 0 ? "uncertain-conjunction" : null,
    satisfied: true, subtree_hash: index.toString(16).padStart(64, "0"),
    tv: { strength: 1, confidence: 0.99 },
  }));
  const result: PlnResult = {
    chain_depth: 2, dampening_lambda: 0.1, latency_ms: 2,
    proof: { nodes, root_node_id: "node-0", structural_hash: "f".repeat(64) },
    query_id: "large-proof", status: "PROVED", unsatisfied_frontier: [],
  };
  const proofEvent = event(1, "pln_result", result as unknown as Record<string, unknown>, 1, 0);
  const state: ReplayState = {
    cursor: { turn: 1, seq: 0 }, events: [proofEvent],
    eventsById: new Map([[proofEvent.event_id, proofEvent]]), atoms: new Map(), plans: new Map(),
    proofs: [{ event: proofEvent, result }], pfPlnEvents: [], pressurePropagations: [],
    operationScores: [], conductanceUpdates: [], quarantines: [], metrics: [], unknown: [],
    loggingGaps: [], snapshots: [], invalidations: new Map(), verifications: [], actionResults: [],
  };
  const started = performance.now();
  render(<ProofExplorer state={state} onSelect={() => undefined} />);
  const elapsed = performance.now() - started;
  expect(screen.getAllByRole("treeitem")).toHaveLength(200);
  expect(elapsed).toBeLessThan(300);
});

it("keeps proof nodes beyond the default depth-four collapse inspectable", async () => {
  const user = userEvent.setup();
  const nodes: ProofNode[] = Array.from({ length: 8 }, (_, index) => ({
    atom: atom(`deep-${index}`, 1, 0.99), crisp: true,
    kind: index === 0 ? "goal" : "premise", node_id: `deep-node-${index}`,
    premise_node_refs: index < 7 ? [`deep-node-${index + 1}`] : [],
    rule_applied: index < 7 ? "deep-chain" : null, satisfied: true,
    subtree_hash: index.toString(16).padStart(64, "0"),
    tv: { strength: 1, confidence: 0.99 },
  }));
  const result: PlnResult = {
    chain_depth: 8, dampening_lambda: null, latency_ms: 2,
    proof: { nodes, root_node_id: "deep-node-0", structural_hash: "e".repeat(64) },
    query_id: "deep-proof", status: "PROVED", unsatisfied_frontier: [],
  };
  const proofEvent = event(1, "pln_result", result as unknown as Record<string, unknown>, 1, 0);
  const state: ReplayState = {
    cursor: { turn: 1, seq: 0 }, events: [proofEvent],
    eventsById: new Map([[proofEvent.event_id, proofEvent]]), atoms: new Map(), plans: new Map(),
    proofs: [{ event: proofEvent, result }], pfPlnEvents: [], pressurePropagations: [],
    operationScores: [], conductanceUpdates: [], quarantines: [], metrics: [], unknown: [],
    loggingGaps: [], snapshots: [], invalidations: new Map(), verifications: [], actionResults: [],
  };
  render(<ProofExplorer state={state} onSelect={() => undefined} />);
  expect(screen.getAllByRole("treeitem")).toHaveLength(5);
  await user.click(screen.getByRole("button", { name: /Expand premises for .*deep-4/i }));
  expect(screen.getAllByRole("treeitem")).toHaveLength(6);
  await user.click(screen.getByRole("button", { name: /Expand premises for .*deep-5/i }));
  expect(screen.getByRole("treeitem", { name: /premise .*deep-6/i })).toBeInTheDocument();
});
