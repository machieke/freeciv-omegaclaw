import type { Cursor } from "./events";

export type ViewName =
  | "timeline" | "proofs" | "atoms" | "plans" | "map" | "audit" | "metrics" | "pfpln"
  | "technology" | "economy" | "forces" | "about";

export interface UrlState {
  view: ViewName;
  cursor: Cursor;
  selected?: string;
  decision?: string;
  search?: string;
  channel?: "all" | "crisp" | "uncertain";
  focus?: boolean;
  inspector?: boolean;
}

const views = new Set<ViewName>([
  "timeline", "proofs", "atoms", "plans", "map", "audit", "metrics", "pfpln",
  "technology", "economy", "forces", "about",
]);

export const decodeUrlState = (search: string, fallback: Cursor): UrlState => {
  const params = new URLSearchParams(search);
  const requested = params.get("view") as ViewName | null;
  const turnRaw = params.get("turn");
  const seqRaw = params.get("seq");
  const turn = turnRaw === null ? Number.NaN : Number(turnRaw);
  const seq = seqRaw === null ? Number.NaN : Number(seqRaw);
  const decision = params.get("decision");
  return {
    view: requested && views.has(requested) ? requested : "timeline",
    cursor: {
      turn: Number.isInteger(turn) && turn >= 0 ? turn : fallback.turn,
      seq: Number.isInteger(seq) && seq >= 0 ? seq : fallback.seq,
    },
    selected: params.get("selected") ?? undefined,
    ...(decision ? { decision } : {}),
    search: params.get("q") ?? undefined,
    channel: params.get("channel") === "crisp" || params.get("channel") === "uncertain"
      ? params.get("channel") as "crisp" | "uncertain" : "all",
    ...(params.get("focus") === "1" ? { focus: true } : {}),
    ...(params.get("inspector") === "0" ? { inspector: false } : {}),
  };
};

export const encodeUrlState = (state: UrlState): string => {
  const params = new URLSearchParams();
  params.set("view", state.view);
  params.set("turn", String(state.cursor.turn));
  params.set("seq", String(state.cursor.seq));
  if (state.selected) params.set("selected", state.selected);
  if (state.decision) params.set("decision", state.decision);
  if (state.search) params.set("q", state.search);
  if (state.channel && state.channel !== "all") params.set("channel", state.channel);
  if (state.focus) params.set("focus", "1");
  if (state.inspector === false) params.set("inspector", "0");
  return `?${params.toString()}`;
};
