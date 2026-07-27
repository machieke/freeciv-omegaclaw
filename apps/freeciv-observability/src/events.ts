import type {
  Atom,
  EventEnvelope,
  Plan,
  PlnResult,
  ProofTree,
  TruthValue,
} from "../../../schemas/freeciv-events/v1/types.generated";

export type TraceEvent = EventEnvelope<string, Record<string, unknown>>;

export interface Cursor {
  turn: number;
  seq: number;
}

export interface AtomRevisionView {
  turn: number;
  seq: number;
  eventId: string;
  tv: TruthValue;
  provenanceId?: string;
  operation: string;
}

export interface AtomView {
  atom: Atom;
  history: AtomRevisionView[];
  lastTurn: number;
  duplicateProvenance: boolean;
}

export interface ReplayState {
  cursor: Cursor;
  events: TraceEvent[];
  eventsById: Map<string, TraceEvent>;
  atoms: Map<string, AtomView>;
  plans: Map<string, Plan>;
  proofs: Array<{ event: TraceEvent; result: PlnResult }>;
  pfPlnEvents: TraceEvent[];
  pressurePropagations: TraceEvent[];
  operationScores: TraceEvent[];
  conductanceUpdates: TraceEvent[];
  quarantines: TraceEvent[];
  metrics: TraceEvent[];
  unknown: TraceEvent[];
  loggingGaps: TraceEvent[];
  snapshots: TraceEvent[];
  invalidations: Map<string, TraceEvent>;
  verifications: TraceEvent[];
  actionResults: TraceEvent[];
  technologyCatalogs: TraceEvent[];
  technologyProgress: TraceEvent[];
  productionStates: TraceEvent[];
  unitLifecycles: TraceEvent[];
}

export const compareCursor = (left: Cursor, right: Cursor): number =>
  left.turn - right.turn || left.seq - right.seq;

export const cursorOf = (event: TraceEvent): Cursor => ({ turn: event.turn, seq: event.seq });

export const atOrBefore = (event: TraceEvent, cursor: Cursor): boolean =>
  compareCursor(cursorOf(event), cursor) <= 0;

export const eventOrder = (left: TraceEvent, right: TraceEvent): number =>
  left.turn - right.turn || left.seq - right.seq || left.event_id.localeCompare(right.event_id);

export const isAtom = (value: unknown): value is Atom => {
  if (!value || typeof value !== "object") return false;
  const row = value as Partial<Atom>;
  return typeof row.atom_id === "string" && typeof row.predicate === "string"
    && Array.isArray(row.args) && typeof row.crisp === "boolean"
    && !!row.tv && typeof row.tv.strength === "number"
    && typeof row.tv.confidence === "number";
};

export const isProofResult = (value: unknown): value is PlnResult => {
  if (!value || typeof value !== "object") return false;
  const row = value as Partial<PlnResult>;
  return typeof row.query_id === "string" && !!row.proof
    && Array.isArray((row.proof as ProofTree).nodes);
};

export const isPlan = (value: unknown): value is Plan => {
  if (!value || typeof value !== "object") return false;
  const row = value as Partial<Plan>;
  return typeof row.plan_id === "string" && Array.isArray(row.steps);
};

export const maxCursor = (events: TraceEvent[]): Cursor => {
  const last = [...events].sort(eventOrder).at(-1);
  return last ? cursorOf(last) : { turn: 0, seq: 0 };
};

export const formatAtom = (atom: Atom): string =>
  `${atom.predicate}(${atom.args.map((arg) => JSON.stringify(arg)).join(", ")})`;
