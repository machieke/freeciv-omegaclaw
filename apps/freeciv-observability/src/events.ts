import type {
  Atom,
  EventEnvelope,
  Plan,
  PlnResult,
  ProofTree,
  TruthValue,
} from "../../../schemas/freeciv-events/v1/types.generated";

export type TraceEvent = EventEnvelope<string, Record<string, unknown>>;

export const FDAS_EVENT_TYPES = new Set([
  "atomspace_revision_started", "snapshot_delta_computed",
  "projection_batch_applied", "atom_support_added", "atom_support_retracted",
  "atom_invalidated", "atom_rederived", "atomspace_revision_committed",
  "scope_activation_requested", "scope_materialized", "scope_budget_exhausted",
  "grounding_evaluated", "grounding_cache_hit", "derivation_fired",
  "derivation_unknown", "completeness_witness_used", "goal_instantiated",
  "goal_resolved", "operation_projected", "operation_candidate_instantiated",
  "operation_candidate_rejected", "pressure_graph_built",
  "atomspace_shadow_decision", "atomspace_authority_decision", "episode_opened",
  "episode_effect_observed", "episode_relief_attributed",
  "episode_outcome_label_opened", "episode_outcome_label_observed",
  "operation_outcome_label_opened", "operation_outcome_label_product_observed",
  "operation_outcome_label_observed", "transition_prediction_abstained",
  "conductance_sample_recorded", "induced_rule_quarantined",
  "induced_rule_promoted", "induced_rule_demoted",
]);

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

export interface FdasTerm {
  term_type?: string;
  kind?: string;
  entity_id?: string;
  catalog?: string;
  symbol?: string;
}

export interface FdasAtomRecord {
  atom_id: string;
  authority: string;
  dependency_count: number;
  key: {
    arguments: FdasTerm[];
    namespace: string;
    predicate: string;
    scope_id: string;
  };
  lifecycle: string;
  materialization_key?: string;
  provenance_ids: string[];
  support_ids: string[];
  tags: unknown[];
  truth: unknown;
  validity: Record<string, unknown>;
}

export interface FdasAtomView {
  atomId: string;
  predicate: string;
  namespace: string;
  scopeId: string;
  authority: string;
  status: "active" | "invalidated";
  record?: FdasAtomRecord;
  event: TraceEvent;
  history: TraceEvent[];
  linkedGoalIds: string[];
  linkedOperationIds: string[];
}

export interface FdasScopeView {
  scopeId: string;
  scopeKind: string;
  atomCount: number;
  scope?: Record<string, unknown>;
  event: TraceEvent;
}

export interface FdasSupportView {
  supportId: string;
  derivationId: string;
  outputAtomIds: string[];
  support?: Record<string, unknown>;
  event: TraceEvent;
}

export interface ReplayState {
  cursor: Cursor;
  events: TraceEvent[];
  eventsById: Map<string, TraceEvent>;
  atoms: Map<string, AtomView>;
  fdasAtoms: Map<string, FdasAtomView>;
  fdasScopes: Map<string, FdasScopeView>;
  fdasSupports: Map<string, FdasSupportView>;
  fdasEvents: TraceEvent[];
  fdasRevisionEvents: TraceEvent[];
  plans: Map<string, Plan>;
  proofs: Array<{ event: TraceEvent; result: PlnResult }>;
  pfPlnEvents: TraceEvent[];
  pressurePropagations: TraceEvent[];
  operationScores: TraceEvent[];
  conductanceUpdates: TraceEvent[];
  teleologyEstimates: TraceEvent[];
  domainEstimates: TraceEvent[];
  domainAbstentions: TraceEvent[];
  transitionValueEstimates: TraceEvent[];
  transitionValueUpdates: TraceEvent[];
  pathPersistenceEvents: TraceEvent[];
  requirementSets: TraceEvent[];
  bridgeEstimates: TraceEvent[];
  flowProjections: TraceEvent[];
  packetReservations: TraceEvent[];
  packetReturns: TraceEvent[];
  flowSelections: TraceEvent[];
  candidateRevalidations: TraceEvent[];
  controllerFallbacks: TraceEvent[];
  controlOutcomes: TraceEvent[];
  resourceSchedules: TraceEvent[];
  resourceClaims: TraceEvent[];
  resourceCapacities: TraceEvent[];
  operationEvents: TraceEvent[];
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
