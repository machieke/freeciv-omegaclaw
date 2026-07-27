import Ajv2020, { type ValidateFunction } from "ajv/dist/2020";
import addFormats from "ajv-formats";

import envelopeSchema from "../../../schemas/freeciv-events/v1/envelope.schema.json";
import payloadsSchema from "../../../schemas/freeciv-events/v1/payloads.schema.json";
import type { KnownEventType } from "../../../schemas/freeciv-events/v1/types.generated";
import type { TraceEvent } from "./events";

const knownTypes: KnownEventType[] = [
  "run_started", "run_completed", "ruleset_compiled", "state_snapshot",
  "technology_catalog", "technology_progress", "production_state", "unit_lifecycle",
  "observation", "revision", "belief_conflict", "context_quarantine",
  "llm_proposal", "goal_selection", "verification", "quarantine",
  "pln_query", "pln_result", "pressure_propagated", "operation_scored",
  "conductance_updated", "rule_proposed", "rule_validated",
  "llm_call_scheduled", "llm_gateway_result",
  "rule_parameter_updated",
  "plan_created", "monitor_trigger",
  "plan_invalidated", "plan_step_executed", "action_sent", "action_result",
  "grounded_check", "metric_sample", "logging_gap",
];

const known = new Set<string>(knownTypes);
const ajv = new Ajv2020({ allErrors: true, strict: true, allowUnionTypes: true });
addFormats(ajv);
ajv.addSchema(payloadsSchema);
const validateEnvelope = ajv.compile(envelopeSchema);
const payloadValidators = new Map<string, ValidateFunction>();
for (const type of knownTypes) {
  payloadValidators.set(type, ajv.compile({
    $ref: `${payloadsSchema.$id}#/$defs/${type}`,
  }));
}

export interface QuarantinedLine {
  line: number;
  raw: string;
  reason: string;
}

export interface ParseResult {
  events: TraceEvent[];
  quarantined: QuarantinedLine[];
}

const diagnostics = (validator: ValidateFunction): string =>
  ajv.errorsText(validator.errors, { separator: "; " });

export const validateTraceEvent = (value: unknown): { valid: boolean; reason?: string } => {
  if (!validateEnvelope(value)) return { valid: false, reason: diagnostics(validateEnvelope) };
  const event = value as unknown as TraceEvent;
  const payloadValidator = payloadValidators.get(event.type);
  if (payloadValidator && !payloadValidator(event.payload)) {
    return { valid: false, reason: diagnostics(payloadValidator) };
  }
  return { valid: true };
};

export const isKnownType = (type: string): boolean => known.has(type);

export const parseJsonl = (text: string): ParseResult => {
  const events: TraceEvent[] = [];
  const quarantined: QuarantinedLine[] = [];
  const lines = text.split(/\r?\n/);
  for (let index = 0; index < lines.length; index += 1) {
    const raw = lines[index];
    if (!raw.trim()) continue;
    try {
      const value: unknown = JSON.parse(raw);
      const result = validateTraceEvent(value);
      if (!result.valid) quarantined.push({ line: index + 1, raw, reason: result.reason ?? "invalid" });
      else events.push(value as TraceEvent);
    } catch (error) {
      quarantined.push({
        line: index + 1, raw,
        reason: error instanceof Error ? error.message : "invalid JSON",
      });
    }
  }
  return { events, quarantined };
};

const parseLine = (raw: string, line: number, result: ParseResult): void => {
  if (!raw.trim()) return;
  try {
    const value: unknown = JSON.parse(raw);
    const validation = validateTraceEvent(value);
    if (!validation.valid) {
      result.quarantined.push({ line, raw, reason: validation.reason ?? "invalid" });
    } else {
      result.events.push(value as TraceEvent);
    }
  } catch (error) {
    result.quarantined.push({
      line, raw, reason: error instanceof Error ? error.message : "invalid JSON",
    });
  }
};

export async function parseJsonlStream(stream: ReadableStream<Uint8Array>): Promise<ParseResult> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  const result: ParseResult = { events: [], quarantined: [] };
  let pending = "";
  let line = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    pending += decoder.decode(value, { stream: true });
    const rows = pending.split(/\r?\n/);
    pending = rows.pop() ?? "";
    for (const raw of rows) parseLine(raw, ++line, result);
  }
  pending += decoder.decode();
  if (pending) parseLine(pending, ++line, result);
  return result;
}
