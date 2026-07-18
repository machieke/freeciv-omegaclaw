import type { Atom } from "../../../../schemas/freeciv-events/v1/types.generated";
import type { TraceEvent } from "../events";

export const atom = (id: string, strength: number, confidence = 0.8): Atom => ({
  atom_id: id,
  predicate: "threat-at",
  args: [id, 4, 7],
  tv: { strength, confidence },
  crisp: false,
  provenance_ids: [`p-${id}`],
});

export const event = (
  index: number, type: string, payload: Record<string, unknown>,
  turn = Math.floor(index / 10), seq = index % 10,
): TraceEvent => ({
  schema_version: "1.0",
  event_id: `e-${index.toString().padStart(8, "0")}`,
  game_id: "test-game",
  turn,
  seq,
  ts: "2026-01-01T00:00:00Z",
  type,
  caused_by: index ? [`e-${(index - 1).toString().padStart(8, "0")}`] : [],
  payload,
});
