import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../../..");
const schemaDir = path.join(repo, "schemas/freeciv-events/v1");
const fixtureDir = path.join(repo, "Autotests/fixtures/freeciv-events/v1");

const readJson = (name) => JSON.parse(fs.readFileSync(path.join(schemaDir, name), "utf8"));
const envelopeSchema = readJson("envelope.schema.json");
const payloadsSchema = readJson("payloads.schema.json");

const ajv = new Ajv2020({ allErrors: true, strict: true, allowUnionTypes: true });
addFormats(ajv);
ajv.addSchema(payloadsSchema);
const validateEnvelope = ajv.compile(envelopeSchema);
const payloadValidators = new Map();
const knownTypes = new Set([
  "run_started", "run_completed", "ruleset_compiled", "state_snapshot",
  "observation", "revision", "belief_conflict", "context_quarantine",
  "llm_proposal", "goal_selection", "verification", "quarantine",
  "pln_query", "pln_result", "pressure_propagated", "operation_scored",
  "conductance_updated", "rule_proposed", "rule_validated",
  "llm_call_scheduled", "llm_gateway_result", "rule_parameter_updated",
  "plan_created", "monitor_trigger",
  "plan_invalidated", "plan_step_executed", "action_sent", "action_result",
  "grounded_check", "metric_sample", "logging_gap",
]);

for (const type of knownTypes) {
  if (!payloadsSchema.$defs[type]) {
    throw new Error(`known payload definition missing: ${type}`);
  }
  payloadValidators.set(type, ajv.compile({
    $ref: `${payloadsSchema.$id}#/$defs/${type}`,
  }));
}

let events = 0;
const files = fs.readdirSync(fixtureDir).filter((name) => name.endsWith(".jsonl")).sort();
for (const name of files) {
  const lines = fs.readFileSync(path.join(fixtureDir, name), "utf8").split("\n").filter(Boolean);
  for (let index = 0; index < lines.length; index += 1) {
    const event = JSON.parse(lines[index]);
    if (!validateEnvelope(event)) {
      throw new Error(`${name}:${index + 1} envelope: ${ajv.errorsText(validateEnvelope.errors)}`);
    }
    const validatePayload = payloadValidators.get(event.type);
    if (validatePayload && !validatePayload(event.payload)) {
      throw new Error(`${name}:${index + 1} payload: ${ajv.errorsText(validatePayload.errors)}`);
    }
    events += 1;
  }
}

const future = {
  schema_version: "1.0",
  event_id: "future-1",
  game_id: "future-game",
  turn: 0,
  seq: 0,
  ts: "2026-01-01T00:00:00Z",
  type: "future_event",
  caused_by: [],
  payload: { retained: true },
};
if (!validateEnvelope(future) || payloadValidators.has(future.type)) {
  throw new Error("unknown future event envelope contract failed");
}

console.log(JSON.stringify({ files: files.length, events, valid: true }));
