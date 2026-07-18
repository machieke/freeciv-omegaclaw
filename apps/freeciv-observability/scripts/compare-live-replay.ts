#!/usr/bin/env -S vite-node
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { basename, relative, resolve } from "node:path";

import { cursorOf, eventOrder, type TraceEvent } from "../src/events";
import { replayDigest } from "../src/equivalence";
import { foldEvents } from "../src/store";
import { parseJsonl } from "../src/validation";

const args = process.argv.slice(2);
const option = (name: string): string | undefined => {
  const index = args.indexOf(name);
  return index < 0 ? undefined : args[index + 1];
};
const input = option("--events");
const output = option("--output");
if (!input) throw new Error("usage: compare-live-replay.ts --events LOG [--output REPORT]");

const inputPath = resolve(input);
const relativeInput = relative(process.cwd(), inputPath);
const logicalInput = relativeInput.startsWith("..") ? basename(inputPath) : relativeInput;
const bytes = readFileSync(inputPath);
const parsed = parseJsonl(bytes.toString("utf8"));
if (parsed.quarantined.length) throw new Error(`event validation rejected ${parsed.quarantined.length} lines`);
const posthoc = parsed.events.sort(eventOrder);
const live: TraceEvent[] = [];
const samples: Array<Record<string, unknown>> = [];
let previousTurn: number | undefined;
let divergence = 0;

const sample = (event: TraceEvent): void => {
  const cursor = cursorOf(event);
  const liveDigest = replayDigest(foldEvents(live, cursor));
  const replayedDigest = replayDigest(foldEvents(posthoc, cursor));
  if (liveDigest !== replayedDigest) divergence += 1;
  samples.push({ cursor, live_digest: liveDigest, replay_digest: replayedDigest,
    equal: liveDigest === replayedDigest });
};

for (const event of posthoc) {
  live.push(event);
  if (previousTurn !== undefined && event.turn !== previousTurn) sample(live[live.length - 2]);
  previousTurn = event.turn;
}
if (live.length) sample(live[live.length - 1]);

const report = {
  schema_version: "1.0", comparator: "browser-event-fold-equivalence/1.0",
  input: logicalInput, game_id: posthoc[0]?.game_id ?? null,
  event_count: posthoc.length, sampled_cursors: samples.length,
  divergence_count: divergence, passed: divergence === 0,
  exact_log_sha256: createHash("sha256").update(bytes).digest("hex"),
  final_state_sha256: samples.at(-1)?.live_digest ?? null, samples,
};
const serialized = `${JSON.stringify(report, null, 2)}\n`;
if (output) writeFileSync(resolve(output), serialized);
process.stdout.write(serialized);
process.exitCode = report.passed ? 0 : 1;
