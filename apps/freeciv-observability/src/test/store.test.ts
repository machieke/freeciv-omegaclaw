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

  it("round trips view, cursor, selection, search, and channel", () => {
    const encoded = encodeUrlState({
      view: "atoms", cursor: { turn: 41, seq: 17 }, selected: "a-1",
      search: "chokepoint", channel: "uncertain",
    });
    expect(decodeUrlState(encoded, { turn: 0, seq: 0 })).toEqual({
      view: "atoms", cursor: { turn: 41, seq: 17 }, selected: "a-1",
      search: "chokepoint", channel: "uncertain",
    });
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
