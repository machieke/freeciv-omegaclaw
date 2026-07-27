import type { Atom, Plan, PlnResult, TruthValue } from "../../../schemas/freeciv-events/v1/types.generated";
import {
  type AtomRevisionView, type AtomView, type Cursor, type ReplayState, type TraceEvent,
  atOrBefore, eventOrder, isAtom, isPlan, isProofResult,
} from "./events";
import { isKnownType } from "./validation";

const PF_PLN_EVENT_TYPES = new Set([
  "pressure_propagated",
  "operation_scored",
  "conductance_updated",
  "rule_proposed",
  "rule_validated",
  "llm_call_scheduled",
  "llm_gateway_result",
  "rule_parameter_updated",
]);

const recordAtom = (
  atoms: Map<string, AtomView>, atom: Atom, event: TraceEvent,
  operation: string, provenanceId?: string,
): void => {
  const prior = atoms.get(atom.atom_id);
  const history: AtomRevisionView[] = prior ? [...prior.history] : [];
  history.push({ turn: event.turn, seq: event.seq, eventId: event.event_id,
    tv: structuredClone(atom.tv), provenanceId, operation });
  const seen = history.filter((entry) => entry.provenanceId).map((entry) => entry.provenanceId);
  atoms.set(atom.atom_id, {
    atom: structuredClone(atom), history, lastTurn: event.turn,
    duplicateProvenance: new Set(seen).size !== seen.length,
  });
};

export const foldEvents = (allEvents: TraceEvent[], cursor: Cursor): ReplayState => {
  const events = [...allEvents].filter((event) => atOrBefore(event, cursor)).sort(eventOrder);
  const eventsById = new Map<string, TraceEvent>();
  const atoms = new Map<string, AtomView>();
  const plans = new Map<string, Plan>();
  const proofs: Array<{ event: TraceEvent; result: PlnResult }> = [];
  const pfPlnEvents: TraceEvent[] = [];
  const pressurePropagations: TraceEvent[] = [];
  const operationScores: TraceEvent[] = [];
  const conductanceUpdates: TraceEvent[] = [];
  const quarantines: TraceEvent[] = [];
  const metrics: TraceEvent[] = [];
  const unknown: TraceEvent[] = [];
  const loggingGaps: TraceEvent[] = [];
  const snapshots: TraceEvent[] = [];
  const invalidations = new Map<string, TraceEvent>();
  const verifications: TraceEvent[] = [];
  const actionResults: TraceEvent[] = [];
  const technologyCatalogs: TraceEvent[] = [];
  const technologyProgress: TraceEvent[] = [];
  const productionStates: TraceEvent[] = [];
  const unitLifecycles: TraceEvent[] = [];

  for (const event of events) {
    eventsById.set(event.event_id, event);
    const payload = event.payload;
    if (!isKnownType(event.type)) unknown.push(event);
    if (event.type === "state_snapshot") {
      snapshots.push(event);
      const uncertain = payload.uncertain_atoms;
      if (Array.isArray(uncertain)) {
        for (const atom of uncertain) if (isAtom(atom)) recordAtom(atoms, atom, event, "snapshot");
      }
    } else if (event.type === "observation" && isAtom(payload.atom)) {
      recordAtom(atoms, payload.atom, event, "observation", String(payload.provenance_id));
    } else if (event.type === "revision" && isAtom(payload.target_atom)) {
      recordAtom(atoms, payload.target_atom, event, String(payload.operation),
        payload.provenance_id ? String(payload.provenance_id) : undefined);
    } else if (event.type === "belief_conflict" && isAtom(payload.conflict_atom)) {
      recordAtom(atoms, payload.conflict_atom, event, "conflict");
    } else if (event.type === "pln_result" && isProofResult(payload)) {
      proofs.push({ event, result: payload });
      for (const node of payload.proof.nodes) recordAtom(atoms, node.atom, event, "proof");
    } else if (event.type === "plan_created" && isPlan(payload.plan)) {
      plans.set(payload.plan.plan_id, structuredClone(payload.plan));
    } else if (event.type === "plan_invalidated") {
      const planId = String(payload.plan_id ?? "");
      const prior = plans.get(planId);
      if (prior) plans.set(planId, { ...prior, status: "INVALID" });
      invalidations.set(planId, event);
    } else if (event.type === "plan_step_executed") {
      const planId = String(payload.plan_id ?? "");
      const stepId = String(payload.step_id ?? "");
      const prior = plans.get(planId);
      if (prior) {
        const status = payload.status === "completed" ? "COMPLETED"
          : payload.status === "failed" || payload.status === "rejected" ? "FAILED" : "ACTIVE";
        plans.set(planId, { ...prior, steps: prior.steps.map((step) => step.step_id === stepId
          ? { ...step, status, actual_turn: payload.status === "completed" ? event.turn : step.actual_turn }
          : step) });
      }
    }
    if (event.type === "quarantine") quarantines.push(event);
    if (PF_PLN_EVENT_TYPES.has(event.type)) pfPlnEvents.push(event);
    if (event.type === "pressure_propagated") pressurePropagations.push(event);
    if (event.type === "operation_scored") operationScores.push(event);
    if (event.type === "conductance_updated") conductanceUpdates.push(event);
    if (event.type === "metric_sample") metrics.push(event);
    if (event.type === "logging_gap") loggingGaps.push(event);
    if (event.type === "verification") verifications.push(event);
    if (event.type === "action_result") actionResults.push(event);
    if (event.type === "technology_catalog") technologyCatalogs.push(event);
    if (event.type === "technology_progress") technologyProgress.push(event);
    if (event.type === "production_state") productionStates.push(event);
    if (event.type === "unit_lifecycle") unitLifecycles.push(event);
  }
  return {
    cursor, events, eventsById, atoms, plans, proofs, pfPlnEvents,
    pressurePropagations, operationScores, conductanceUpdates, quarantines, metrics,
    unknown, loggingGaps, snapshots, invalidations, verifications, actionResults,
    technologyCatalogs, technologyProgress, productionStates, unitLifecycles,
  };
};

export const ancestry = (state: ReplayState, eventId: string): Set<string> => {
  const result = new Set<string>();
  const visit = (id: string): void => {
    if (result.has(id)) return;
    const event = state.eventsById.get(id);
    if (!event) return;
    result.add(id);
    for (const parent of event.caused_by) visit(parent);
  };
  visit(eventId);
  return result;
};

export const densityByTurn = (events: TraceEvent[]): Map<number, number> => {
  const density = new Map<number, number>();
  for (const event of events) density.set(event.turn, (density.get(event.turn) ?? 0) + 1);
  return density;
};

export const latestTv = (state: ReplayState, atomId: string): TruthValue | undefined =>
  state.atoms.get(atomId)?.atom.tv;
