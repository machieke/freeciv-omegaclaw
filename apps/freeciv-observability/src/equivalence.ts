import { createHash } from "node:crypto";

import type { ReplayState, TraceEvent } from "./events";

const orderedObject = (value: unknown): unknown => {
  if (Array.isArray(value)) return value.map(orderedObject);
  if (value instanceof Map) return [...value.entries()]
    .sort(([left], [right]) => String(left).localeCompare(String(right)))
    .map(([key, item]) => [key, orderedObject(item)]);
  if (value instanceof Set) return [...value].sort().map(orderedObject);
  if (value && typeof value === "object") return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, orderedObject(item)]));
  return value;
};

export const replayProjection = (state: ReplayState): unknown => orderedObject({
  actionResults: state.actionResults.map((event) => event.event_id),
  atoms: state.atoms,
  cursor: state.cursor,
  eventIds: state.events.map((event) => event.event_id),
  invalidations: new Map([...state.invalidations].map(([key, event]) => [key, event.event_id])),
  loggingGaps: state.loggingGaps.map((event) => event.event_id),
  metrics: state.metrics.map((event) => event.event_id),
  pfPlnEvents: state.pfPlnEvents.map((event) => event.event_id),
  pressurePropagations: state.pressurePropagations.map((event) => event.event_id),
  operationScores: state.operationScores.map((event) => event.event_id),
  conductanceUpdates: state.conductanceUpdates.map((event) => event.event_id),
  teleologyEstimates: state.teleologyEstimates.map((event) => event.event_id),
  requirementSets: state.requirementSets.map((event) => event.event_id),
  bridgeEstimates: state.bridgeEstimates.map((event) => event.event_id),
  flowProjections: state.flowProjections.map((event) => event.event_id),
  packetReservations: state.packetReservations.map((event) => event.event_id),
  packetReturns: state.packetReturns.map((event) => event.event_id),
  flowSelections: state.flowSelections.map((event) => event.event_id),
  candidateRevalidations: state.candidateRevalidations.map((event) => event.event_id),
  controllerFallbacks: state.controllerFallbacks.map((event) => event.event_id),
  controlOutcomes: state.controlOutcomes.map((event) => event.event_id),
  plans: state.plans,
  proofs: state.proofs.map((row) => ({ eventId: row.event.event_id, result: row.result })),
  quarantines: state.quarantines.map((event) => event.event_id),
  snapshots: state.snapshots.map((event) => event.event_id),
  unknown: state.unknown.map((event) => event.event_id),
  verifications: state.verifications.map((event) => event.event_id),
});

export const replayDigest = (state: ReplayState): string => createHash("sha256")
  .update(JSON.stringify(replayProjection(state))).digest("hex");

export const eventLogDigest = (events: TraceEvent[]): string => createHash("sha256")
  .update(events.map((event) => JSON.stringify(orderedObject(event))).join("\n"))
  .digest("hex");
