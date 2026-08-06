import type { Atom, Plan, PlnResult, TruthValue } from "../../../schemas/freeciv-events/v1/types.generated";
import {
  FDAS_EVENT_TYPES,
  type AtomRevisionView, type AtomView, type Cursor, type FdasAtomRecord,
  type FdasAtomView, type FdasScopeView, type FdasSupportView,
  type ReplayState, type TraceEvent, atOrBefore, eventOrder, isAtom, isPlan,
  isProofResult,
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
  "teleology_estimated",
  "domain_estimate_emitted",
  "domain_estimate_abstained",
  "transition_value_estimated",
  "transition_value_updated",
  "path_persistence_applied",
  "reverse_operator_applied",
  "requirement_set_materialized",
  "bridge_estimated",
  "probe_block_completed",
  "path_current_deposited",
  "flow_projected",
  "attention_advected",
  "packet_reserved",
  "packet_returned",
  "flow_candidate_selected",
  "candidate_revalidated",
  "controller_fallback",
  "control_outcome_recorded",
  "selection_coverage_sample",
  "resource_schedule_decided",
  "resource_claim_requested",
  "resource_claim_reserved",
  "resource_claim_rejected",
  "resource_claim_released",
  "resource_capacity_changed",
  "operation_proposed",
  "operation_reserved",
  "operation_activated",
  "operation_step_selected",
  "operation_step_revalidated",
  "operation_step_committed",
  "operation_blocked",
  "operation_repaired",
  "operation_suspended",
  "operation_completed",
  "operation_failed",
  "operation_abandoned",
  "operation_expired",
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

const objectValue = (value: unknown): Record<string, unknown> | undefined =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : undefined;

const fdasDetails = (event: TraceEvent): Record<string, unknown> =>
  objectValue(event.payload.details) ?? {};

const fdasRecord = (value: unknown): FdasAtomRecord | undefined => {
  const row = objectValue(value);
  const key = objectValue(row?.key);
  if (!row || !key || typeof row.atom_id !== "string"
    || typeof key.predicate !== "string" || typeof key.namespace !== "string"
    || typeof key.scope_id !== "string" || !Array.isArray(key.arguments)) return undefined;
  return {
    atom_id: row.atom_id,
    authority: typeof row.authority === "string" ? row.authority : "unknown",
    dependency_count: typeof row.dependency_count === "number" ? row.dependency_count : 0,
    key: {
      arguments: key.arguments as FdasAtomRecord["key"]["arguments"],
      namespace: key.namespace,
      predicate: key.predicate,
      scope_id: key.scope_id,
    },
    lifecycle: typeof row.lifecycle === "string" ? row.lifecycle : "active",
    materialization_key: typeof row.materialization_key === "string"
      ? row.materialization_key : undefined,
    provenance_ids: Array.isArray(row.provenance_ids)
      ? row.provenance_ids.map(String) : [],
    support_ids: Array.isArray(row.support_ids) ? row.support_ids.map(String) : [],
    tags: Array.isArray(row.tags) ? row.tags : [],
    truth: row.truth,
    validity: objectValue(row.validity) ?? {},
  };
};

export const foldEvents = (allEvents: TraceEvent[], cursor: Cursor): ReplayState => {
  const events = [...allEvents].filter((event) => atOrBefore(event, cursor)).sort(eventOrder);
  const eventsById = new Map<string, TraceEvent>();
  const atoms = new Map<string, AtomView>();
  const fdasAtoms = new Map<string, FdasAtomView>();
  const fdasScopes = new Map<string, FdasScopeView>();
  const fdasSupports = new Map<string, FdasSupportView>();
  const fdasEvents: TraceEvent[] = [];
  const fdasRevisionEvents: TraceEvent[] = [];
  const plans = new Map<string, Plan>();
  const proofs: Array<{ event: TraceEvent; result: PlnResult }> = [];
  const pfPlnEvents: TraceEvent[] = [];
  const pressurePropagations: TraceEvent[] = [];
  const operationScores: TraceEvent[] = [];
  const conductanceUpdates: TraceEvent[] = [];
  const teleologyEstimates: TraceEvent[] = [];
  const domainEstimates: TraceEvent[] = [];
  const domainAbstentions: TraceEvent[] = [];
  const transitionValueEstimates: TraceEvent[] = [];
  const transitionValueUpdates: TraceEvent[] = [];
  const pathPersistenceEvents: TraceEvent[] = [];
  const requirementSets: TraceEvent[] = [];
  const bridgeEstimates: TraceEvent[] = [];
  const flowProjections: TraceEvent[] = [];
  const packetReservations: TraceEvent[] = [];
  const packetReturns: TraceEvent[] = [];
  const flowSelections: TraceEvent[] = [];
  const candidateRevalidations: TraceEvent[] = [];
  const controllerFallbacks: TraceEvent[] = [];
  const controlOutcomes: TraceEvent[] = [];
  const resourceSchedules: TraceEvent[] = [];
  const resourceClaims: TraceEvent[] = [];
  const resourceCapacities: TraceEvent[] = [];
  const operationEvents: TraceEvent[] = [];
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
    if (FDAS_EVENT_TYPES.has(event.type)) {
      fdasEvents.push(event);
      const details = fdasDetails(event);
      if (event.type === "atomspace_revision_started") {
        fdasRevisionEvents.push(event);
        fdasScopes.clear();
        if (details.cold_build === true) {
          fdasAtoms.clear();
          fdasSupports.clear();
        }
      } else if (event.type === "atomspace_revision_committed") {
        fdasRevisionEvents.push(event);
      } else if (event.type === "scope_materialized") {
        const scope = objectValue(details.scope);
        const scopeId = typeof details.scope_id === "string" ? details.scope_id
          : typeof scope?.scope_id === "string" ? scope.scope_id : undefined;
        const scopeKind = typeof details.scope_kind === "string" ? details.scope_kind
          : typeof scope?.scope_kind === "string" ? scope.scope_kind : "unknown";
        if (scopeId) fdasScopes.set(scopeId, {
          scopeId, scopeKind,
          atomCount: typeof details.atom_count === "number" ? details.atom_count : 0,
          scope, event,
        });
      } else if (event.type === "atom_rederived") {
        const record = fdasRecord(details.record);
        const atomId = record?.atom_id ?? (typeof details.atom_id === "string"
          ? details.atom_id : undefined);
        if (atomId) {
          const prior = fdasAtoms.get(atomId);
          fdasAtoms.set(atomId, {
            atomId,
            predicate: record?.key.predicate ?? (typeof details.predicate === "string"
              ? details.predicate : prior?.predicate ?? "unknown"),
            namespace: record?.key.namespace ?? prior?.namespace ?? "unknown",
            scopeId: record?.key.scope_id ?? prior?.scopeId ?? "unknown",
            authority: record?.authority ?? prior?.authority ?? "unknown",
            status: "active", record: record ?? prior?.record, event,
            history: [...(prior?.history ?? []), event],
            linkedGoalIds: prior?.linkedGoalIds ?? [],
            linkedOperationIds: prior?.linkedOperationIds ?? [],
          });
        }
      } else if (event.type === "atom_invalidated") {
        const record = fdasRecord(details.record);
        const atomId = record?.atom_id ?? (typeof details.atom_id === "string"
          ? details.atom_id : undefined);
        if (atomId) {
          const prior = fdasAtoms.get(atomId);
          fdasAtoms.set(atomId, {
            atomId,
            predicate: record?.key.predicate ?? prior?.predicate ?? "unknown",
            namespace: record?.key.namespace ?? prior?.namespace ?? "unknown",
            scopeId: record?.key.scope_id ?? prior?.scopeId ?? "unknown",
            authority: record?.authority ?? prior?.authority ?? "unknown",
            status: "invalidated", record: record ?? prior?.record, event,
            history: [...(prior?.history ?? []), event],
            linkedGoalIds: prior?.linkedGoalIds ?? [],
            linkedOperationIds: prior?.linkedOperationIds ?? [],
          });
        }
      } else if (event.type === "atom_support_added") {
        const support = objectValue(details.support);
        const supportId = typeof details.support_id === "string" ? details.support_id
          : typeof support?.support_id === "string" ? support.support_id : undefined;
        if (supportId) fdasSupports.set(supportId, {
          supportId,
          derivationId: typeof details.derivation_id === "string" ? details.derivation_id
            : typeof support?.derivation_id === "string" ? support.derivation_id : "unknown",
          outputAtomIds: Array.isArray(details.output_atom_ids)
            ? details.output_atom_ids.map(String) : [],
          support, event,
        });
      } else if (event.type === "atom_support_retracted"
        && typeof details.support_id === "string") {
        fdasSupports.delete(details.support_id);
      } else if (event.type === "goal_instantiated"
        && typeof details.deficit_atom_id === "string") {
        const prior = fdasAtoms.get(details.deficit_atom_id);
        if (prior) fdasAtoms.set(prior.atomId, {
          ...prior,
          predicate: typeof details.deficit_predicate === "string"
            ? details.deficit_predicate : prior.predicate,
          scopeId: typeof details.scope_id === "string" ? details.scope_id : prior.scopeId,
          linkedGoalIds: typeof details.goal_id === "string"
            ? [...new Set([...prior.linkedGoalIds, details.goal_id])]
            : prior.linkedGoalIds,
        });
      } else if (event.type === "operation_projected"
        && typeof details.operation_id === "string" && Array.isArray(details.atom_ids)) {
        for (const atomId of details.atom_ids.map(String)) {
          const prior = fdasAtoms.get(atomId);
          if (prior) fdasAtoms.set(atomId, {
            ...prior,
            linkedOperationIds: [
              ...new Set([...prior.linkedOperationIds, details.operation_id]),
            ],
          });
        }
      }
    }
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
    if (event.type === "teleology_estimated") teleologyEstimates.push(event);
    if (event.type === "domain_estimate_emitted") domainEstimates.push(event);
    if (event.type === "domain_estimate_abstained") domainAbstentions.push(event);
    if (event.type === "transition_value_estimated") transitionValueEstimates.push(event);
    if (event.type === "transition_value_updated") transitionValueUpdates.push(event);
    if (event.type === "path_persistence_applied") pathPersistenceEvents.push(event);
    if (event.type === "requirement_set_materialized") requirementSets.push(event);
    if (event.type === "bridge_estimated") bridgeEstimates.push(event);
    if (event.type === "flow_projected") flowProjections.push(event);
    if (event.type === "packet_reserved") packetReservations.push(event);
    if (event.type === "packet_returned") packetReturns.push(event);
    if (event.type === "flow_candidate_selected") flowSelections.push(event);
    if (event.type === "candidate_revalidated") candidateRevalidations.push(event);
    if (event.type === "controller_fallback") controllerFallbacks.push(event);
    if (event.type === "control_outcome_recorded") controlOutcomes.push(event);
    if (event.type === "resource_schedule_decided") resourceSchedules.push(event);
    if (event.type.startsWith("resource_claim_")) resourceClaims.push(event);
    if (event.type === "resource_capacity_changed") resourceCapacities.push(event);
    if (event.type.startsWith("operation_") && event.type !== "operation_scored") {
      operationEvents.push(event);
    }
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
    cursor, events, eventsById, atoms, fdasAtoms, fdasScopes, fdasSupports,
    fdasEvents, fdasRevisionEvents, plans, proofs, pfPlnEvents,
    pressurePropagations, operationScores, conductanceUpdates, quarantines, metrics,
    teleologyEstimates, domainEstimates, domainAbstentions,
    transitionValueEstimates, transitionValueUpdates,
    pathPersistenceEvents, requirementSets, bridgeEstimates, flowProjections,
    packetReservations, packetReturns, flowSelections, candidateRevalidations,
    controllerFallbacks, controlOutcomes, resourceSchedules, resourceClaims,
    resourceCapacities, operationEvents,
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
