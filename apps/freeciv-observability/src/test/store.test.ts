import { describe, expect, it } from "vitest";
import { performance } from "node:perf_hooks";

import { replayDigest } from "../equivalence";
import { foldEvents } from "../store";
import { decodeUrlState, encodeUrlState } from "../url-state";
import { parseJsonl, parseJsonlStream } from "../validation";
import { atom, event } from "./helpers";

describe("event sourced replay", () => {
  it("preserves valid unknown events and quarantines malformed lines", () => {
    const future = event(1, "future_capability", { retained: true }, 1, 0);
    const result = parseJsonl(`${JSON.stringify(future)}\n{broken`);
    expect(result.events).toEqual([future]);
    expect(result.quarantined).toHaveLength(1);
    expect(foldEvents(result.events, { turn: 1, seq: 0 }).unknown).toEqual([future]);
  });

  it("parses chunked JSONL incrementally without splitting multibyte text", async () => {
    const row = JSON.stringify(event(1, "future_capability", { note: "scout Ω" }, 1, 0));
    const bytes = new TextEncoder().encode(`${row}\n`);
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (let offset = 0; offset < bytes.length; offset += 3) {
          controller.enqueue(bytes.slice(offset, offset + 3));
        }
        controller.close();
      },
    });
    const parsed = await parseJsonlStream(stream);
    expect(parsed.quarantined).toEqual([]);
    expect(parsed.events[0].payload.note).toBe("scout Ω");
  });

  it("matches an independent strict as-of fold for 50 random cursors", () => {
    const events = Array.from({ length: 1_000 }, (_, index) => event(
      index + 1, "revision",
      {
        target_atom: atom(`a-${index % 50}`, (index % 100) / 100),
        operation: "revision", provenance_id: `p-${index}`,
      }, Math.floor(index / 5) + 1, index % 5,
    ));
    let seed = 1777;
    for (let sample = 0; sample < 50; sample += 1) {
      seed = (seed * 48271) % 0x7fffffff;
      const turn = 1 + (seed % 200);
      const seq = seed % 5;
      const state = foldEvents(events, { turn, seq });
      for (let atomIndex = 0; atomIndex < 50; atomIndex += 1) {
        const expected = events.filter((row) => row.turn < turn || (row.turn === turn && row.seq <= seq))
          .filter((row) => (row.payload.target_atom as { atom_id?: string }).atom_id === `a-${atomIndex}`).at(-1);
        expect(state.atoms.get(`a-${atomIndex}`)?.atom.tv)
          .toEqual((expected?.payload.target_atom as { tv?: unknown } | undefined)?.tv);
      }
    }
  });

  it("round trips view, cursor, selection, PF decision, filters, and workspace layout", () => {
    const encoded = encodeUrlState({
      view: "about", cursor: { turn: 41, seq: 17 }, selected: "a-1",
      decision: "decision-7", search: "chokepoint", channel: "uncertain",
      focus: true, inspector: false,
    });
    expect(decodeUrlState(encoded, { turn: 0, seq: 0 })).toEqual({
      view: "about", cursor: { turn: 41, seq: 17 }, selected: "a-1",
      decision: "decision-7", search: "chokepoint", channel: "uncertain",
      focus: true, inspector: false,
    });
  });

  it("indexes PF-PLN event families strictly as of the replay cursor", () => {
    const pressure = event(1, "pressure_propagated", {}, 2, 1);
    const scored = event(2, "operation_scored", {}, 2, 2);
    const learned = event(3, "conductance_updated", {}, 3, 1);
    const beforeLearning = foldEvents([pressure, scored, learned], { turn: 2, seq: 2 });
    expect(beforeLearning.pfPlnEvents).toEqual([pressure, scored]);
    expect(beforeLearning.pressurePropagations).toEqual([pressure]);
    expect(beforeLearning.operationScores).toEqual([scored]);
    expect(beforeLearning.conductanceUpdates).toEqual([]);
    expect(foldEvents([pressure, scored, learned], { turn: 3, seq: 1 }).conductanceUpdates)
      .toEqual([learned]);
  });

  it("indexes unified controller lineage strictly as of the replay cursor", () => {
    const teleology = event(11, "teleology_estimated", {}, 4, 1);
    const requirements = event(12, "requirement_set_materialized", {}, 4, 2);
    const bridge = event(13, "bridge_estimated", {}, 4, 3);
    const projection = event(14, "flow_projected", {}, 4, 4);
    const packet = event(15, "packet_reserved", {}, 4, 5);
    const selection = event(16, "flow_candidate_selected", {}, 4, 6);
    const fallback = event(17, "controller_fallback", {}, 4, 7);
    const revalidation = event(18, "candidate_revalidated", {}, 4, 8);
    const outcome = event(19, "control_outcome_recorded", {}, 5, 1);
    const rows = [
      teleology, requirements, bridge, projection, packet, selection, fallback,
      revalidation, outcome,
    ];
    const beforeOutcome = foldEvents(rows, { turn: 4, seq: 8 });
    expect(beforeOutcome.teleologyEstimates).toEqual([teleology]);
    expect(beforeOutcome.requirementSets).toEqual([requirements]);
    expect(beforeOutcome.bridgeEstimates).toEqual([bridge]);
    expect(beforeOutcome.flowProjections).toEqual([projection]);
    expect(beforeOutcome.packetReservations).toEqual([packet]);
    expect(beforeOutcome.flowSelections).toEqual([selection]);
    expect(beforeOutcome.controllerFallbacks).toEqual([fallback]);
    expect(beforeOutcome.candidateRevalidations).toEqual([revalidation]);
    expect(beforeOutcome.controlOutcomes).toEqual([]);
    expect(foldEvents(rows, { turn: 5, seq: 1 }).controlOutcomes).toEqual([outcome]);
  });

  it("folds a representative 200-turn, 50k-atom trace within the UI budgets", () => {
    const events = Array.from({ length: 50_000 }, (_, index) => event(
      index + 1, "observation",
      { atom: atom(`atom-${index}`, (index % 100) / 100), provenance_id: `p-${index}` },
      Math.floor(index / 250) + 1, index % 250,
    ));
    const start = performance.now();
    const state = foldEvents(events, { turn: 200, seq: 249 });
    const loadMs = performance.now() - start;
    const searchStart = performance.now();
    const result = [...state.atoms.values()].filter((row) => row.atom.predicate === "threat-at"
      && row.atom.args.some((arg) => String(arg).includes("499")));
    const searchMs = performance.now() - searchStart;
    expect(state.atoms.size).toBe(50_000);
    expect(result.length).toBeGreaterThan(0);
    expect(loadMs).toBeLessThan(10_000);
    expect(searchMs).toBeLessThan(200);
  }, 15_000);

  it("keeps live append and post-hoc replay byte-equivalent at all 200 turn cursors", () => {
    const posthoc = Array.from({ length: 1_000 }, (_, index) => event(
      index + 1, "observation",
      { atom: atom(`live-${index % 200}`, (index % 100) / 100), provenance_id: `lp-${index}` },
      Math.floor(index / 5) + 1, index % 5,
    ));
    const live: typeof posthoc = [];
    for (const row of posthoc) {
      live.push(row);
      if (row.seq !== 4) continue;
      const cursor = { turn: row.turn, seq: row.seq };
      expect(replayDigest(foldEvents(live, cursor))).toBe(
        replayDigest(foldEvents(posthoc, cursor)));
    }
  });
});
