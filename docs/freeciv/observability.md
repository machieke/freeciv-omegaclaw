# FreeCiv Decision Observatory

`apps/freeciv-observability` is a strict React/TypeScript replay and live-tail
application. Its only domain input is the versioned JSONL event contract under
`schemas/freeciv-events`; it does not import Python agent logic or recompute PLN,
belief revision, planning, paths, ETAs, calibration, or confidence intervals.

## Install, verify, and run

```bash
npm --prefix apps/freeciv-observability ci
npm --prefix apps/freeciv-observability test
npm --prefix apps/freeciv-observability run dev -- --port 4178
```

`npm test` type-checks, validates Python/TypeScript-compatible fixtures, checks the
event-only source boundary, runs as-of/deep-link/interaction/performance/live tests,
and makes a production build. Load any `events.jsonl` through Replay.

When the application is served by its Vite development or preview server, choose
**Experiment traces** to search and open generated streams under
`artifacts/freeciv`. The read-only catalog excludes archived `attempt-history`
streams, rejects traversal and out-of-root symlinks, and streams the selected JSONL
through the same strict parser and event limit as a manual file upload. At most 200
matching rows are rendered; refine the experiment, cohort, arm, or seed filter to
find older traces. Manual **Load JSONL** remains available.

The UI exposes one global `(turn, seq)` cursor across:

- the decision timeline and complete causal ancestry;
- AND/OR proof trees, formulas, frontiers, and proof diffs;
- current/as-of atom truth values, provenance, and revisions;
- plans, ledger, assumptions, invalidations, repairs, and map overlays;
- quarantined LLM claims and the write-through alarm; and
- harness-emitted calibration, latency, error, depth, and ablation metrics.

Unknown future event types are preserved as raw JSON. Missing source data is shown as
a logging gap. Duplicate, gap, out-of-order, incompatible-schema, causal-orphan,
crisp-drift, and duplicate-provenance diagnostics are visible rather than repaired in
the browser.

## Live mode

Start the persisted-first read-only tail over an existing event file:

```bash
PYTHONPATH=src python3 scripts/freeciv/serve_event_tail.py \
  --events artifacts/freeciv/v5-live-200/events.jsonl \
  --game-id pln-v5-live-200 --host 127.0.0.1 --port 8765
```

Set `ws://127.0.0.1:8765` and the matching game ID in the Live view. Reconnects
resume after the last accepted `(game_id, turn, seq)`. Backfilled and new records go
through the same validator, indexes, and fold as file replay.

Engine traces use turn-level durability without changing live visibility. Every
event is schema-validated and emitted as one atomic `O_APPEND` JSONL write;
the completed turn is fsynced before the harness waits for its successor, and
`run_completed` fsyncs the final metrics and completion record. The writer's
default remains per-event fsync for callers that do not explicitly select turn
mode.

Compare live-fold and fresh replay state at every cursor with:

```bash
apps/freeciv-observability/node_modules/.bin/vite-node \
  apps/freeciv-observability/scripts/compare-live-replay.ts \
  --events artifacts/freeciv/v5-live-200/events.jsonl \
  --output artifacts/freeciv/v5-live-200/equivalence.json
```

The accepted soak is documented in [Phase 12 evidence](evidence/phase-12-v5.md).
Replay/performance results are in [Phase 5 evidence](evidence/phase-5-v1-v2.md),
plan/map behavior in [Phase 7 evidence](evidence/phase-7-v3.md), and audit/metrics
behavior in [Phases 10](evidence/phase-10-m6-v4.md) and
[11](evidence/phase-11-m7-v4.md).
