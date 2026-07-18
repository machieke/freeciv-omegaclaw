import type { Cursor } from "./events";

export type ViewName = "timeline" | "proofs" | "atoms" | "plans" | "map" | "audit" | "metrics";

export interface UrlState {
  view: ViewName;
  cursor: Cursor;
  selected?: string;
  search?: string;
  channel?: "all" | "crisp" | "uncertain";
}

const views = new Set<ViewName>(["timeline", "proofs", "atoms", "plans", "map", "audit", "metrics"]);

export const decodeUrlState = (search: string, fallback: Cursor): UrlState => {
  const params = new URLSearchParams(search);
  const requested = params.get("view") as ViewName | null;
  const turnRaw = params.get("turn");
  const seqRaw = params.get("seq");
  const turn = turnRaw === null ? Number.NaN : Number(turnRaw);
  const seq = seqRaw === null ? Number.NaN : Number(seqRaw);
  return {
    view: requested && views.has(requested) ? requested : "timeline",
    cursor: {
      turn: Number.isInteger(turn) && turn >= 0 ? turn : fallback.turn,
      seq: Number.isInteger(seq) && seq >= 0 ? seq : fallback.seq,
    },
    selected: params.get("selected") ?? undefined,
    search: params.get("q") ?? undefined,
    channel: params.get("channel") === "crisp" || params.get("channel") === "uncertain"
      ? params.get("channel") as "crisp" | "uncertain" : "all",
  };
};

export const encodeUrlState = (state: UrlState): string => {
  const params = new URLSearchParams();
  params.set("view", state.view);
  params.set("turn", String(state.cursor.turn));
  params.set("seq", String(state.cursor.seq));
  if (state.selected) params.set("selected", state.selected);
  if (state.search) params.set("q", state.search);
  if (state.channel && state.channel !== "all") params.set("channel", state.channel);
  return `?${params.toString()}`;
};
