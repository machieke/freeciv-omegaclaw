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
find older traces. **Open** replaces the active replay. **Compare** loads a second
stream into a turn-aligned comparison slot without changing the active replay.
When the catalog contains an opposing arm with the same experiment, cohort,
condition, and run/seed, **Open pair** loads both streams together and labels the
comparison an **exact pair**. When one arm is named `treatment`, it becomes the
active replay so PF-PLN controls remain available even if the action was initiated
from the baseline row. Loading a new primary trace clears any older
comparison so stale pairings cannot carry across replays.
Manual **Load JSONL** remains available.

The UI exposes one global `(turn, seq)` cursor across:

- an in-app **How it works** guide that explains the event pipeline, trust
  boundary, recommended investigation workflow, paired-comparison limits, and
  routes each common diagnostic question to the relevant view. Its applied
  PF-PLN walkthrough follows authoritative state through grounded goals,
  reverse pressure transport, safety-constrained scheduling, the unchanged
  execution gate, and conductance updates backed by verified goal relief;
- the decision timeline, turn-by-stage activity matrix, milestone overlays, and
  complete causal ancestry;
- selectable AND/OR proof topology, lossless tree, formulas, frontiers, and proof
  diffs;
- current/as-of atom truth values, predicate distribution, provenance, and
  revision sparklines;
- plan dependency timing, ledger, assumptions, invalidations, repairs, and a
  full-extent map overlay. It renders packet tiles/visibility when logged and
  also uses exact own-city, own-unit, visible-opponent, atom, and nested action
  target coordinates, so older dimensions-only engine traces retain a useful
  positional view with an explicit coverage warning;
- quarantined LLM claims, claim-handling chronology, and the write-through alarm;
- the PF-PLN goal field, pressure transport lineage, emitted operation schedule,
  candidate rank, selected operation, conductance trends, activation phases,
  runtime composition, and paired trace outcomes; and
- grouped harness-emitted calibration, latency, error, depth, and ablation metric
  series.

The **Economy & production** view separates operating cash flow from Coinage
shield conversion, then shows their effective net, city gold surplus, packet
upkeep style, unit and building upkeep, and the immediate upkeep reserve. Each
yield is displayed as produced, consumed, and net at empire and city level.
Gross science, technology upkeep, and net beakers share the same view and also
appear beside the current target in **Technology**.
The Technology view keeps the packet projection and authoritative observation
separate. **Projected rate** is the latest proxy-reported net beaker rate.
**Observed rate** is the change in the same target's authoritative progress
counter divided by elapsed game turns. Same-turn refreshes update the next
boundary baseline but do not add elapsed stalled time. A negative observed
delta is emitted as `research_progress_declining`; an unchanged positive-cost
target is `research_progress_not_advancing`. These diagnoses remain visible
even when the projected rate is positive, so a nominal science allocation is
not presented as delivered research throughput.
The accepted live-tail visual check is retained in the
[research-throughput ProofShot report](../../proofshot-artifacts/2026-07-28_18-43-05_verify-live-technology-view-distinguishe/SUMMARY.md).
It marks food-reserve, treasury-reserve, and local-defense status alongside the exact PF goal context,
adds a per-city `+1` food-reserve check, identifies sustainability queue
overrides and their discarded shields, and indexes rate, rehome, disband, and
production interventions without reconstructing unlogged planner state.
The current score, opponent leader, exact gap, fleet completions, building
inventory, building upkeep, and observed building completion/removal transitions
make strategic stalls visible. Building/yield correlation remains explicitly
city-level; the UI does not claim that one building caused a contemporaneous
yield delta. FreeCiv's negative hidden-score sentinel is normalized to unknown;
it cannot create a leader comparison or a PF-PLN score-pressure route.

The header can collapse the inspector or enable focus mode. View, cursor, selected
entity, atom filters, PF decision, focus mode, and inspector state are deep-linked
in the URL.

Unknown future event types are preserved as raw JSON. Missing source data is shown as
a logging gap. Duplicate, gap, out-of-order, incompatible-schema, causal-orphan,
crisp-drift, and duplicate-provenance diagnostics are visible rather than repaired in
the browser.

## PF-PLN replay

Open **PF-PLN** after loading a pressure-enabled treatment trace. The view matches
each `operation_scored` decision to its `pressure_propagated` input by the logged
`pressure_id`, and exposes:

- goal utility, urgency, safety, target strength, and grounded context;
- the scheduler's emitted candidate order, admissibility, priority, value,
  rejection reason, selected operation, and solver identity;
- a goal → rule-conclusion → candidate-premise pressure graph, with edge width
  scaled from the logged transported value;
- grounded `conductance_updated` feedback, including prior/posterior
  conductance, credit kind, and per-category chronological sparklines;
- `pf_pln_phase_enabled` activation records; and
- emitted pressure-planning and conductance-learning latency metrics, grouped by
  their logged units.

To compare paired arms, open the intended primary arm, choose **Experiment
traces**, and press **Compare** on its matching seed/arm. The PF-PLN view aligns
the comparison to the selected decision turn, reports whether the emitted
category/action diverged, and displays the difference between the latest logged
`score_turn_*`, `score_gain`, `cities_founded`, `settlement_completions`, and
`game_win` values. This is a descriptive replay aid. It is not a paired estimator,
confidence interval, or causal claim; statistical claims remain the responsibility
of the experiment harness.

Prefer **Open pair** when it is available. Manually selected comparisons receive
an explicit match-quality badge: exact only when experiment, cohort, condition,
run/seed, and opposing arm all agree; otherwise the UI names the mismatched keys.
This prevents visual alignment from being mistaken for valid paired-seed evidence.

All values remain subject to the global `(turn, seq)` cursor and open their exact
source event in the inspector. The cards count indexed event families, but the
application does not recalculate pressure, rescore operations, infer missing
goals, or estimate unlogged latency. A missing family is displayed as a logging
gap. Baseline traces without PF-PLN events therefore remain explicitly empty
rather than being presented as zero-pressure runs.

## Visualization and calculation boundary

Every chart remains a projection over accepted trace events at the global cursor:

- sparklines connect logged samples in event order;
- heatmap opacity is a count of displayed events within a turn and track;
- ranking bars scale logged scheduler values against the largest visible value;
- runtime bars scale only against metrics with the same logged unit;
- atom predicate counts and mean confidence are labeled display aggregations; and
- graph layout, path geometry, color, opacity, and edge thickness are presentation
  transforms, not agent outputs.

Large proof and pressure graphs state their visible node/route limit. Exact payloads
remain available through selection and the inspector, and the PF candidate chart
retains a collapsible exact scheduler table. The UI never fills missing series,
infers unlogged map paths, terrain, or fog, recomputes pressure, or turns a visual
difference into a performance claim. A map with dimensions but no tile packets is
shown as a neutral grid carrying only logged entities and targets. Tile-rich v6
traces distinguish exact visible indexes from remembered terrain and report their
record, visibility, and marker counts.

## Live mode

Start the persisted-first read-only tail over an existing event file:

```bash
PYTHONPATH=src python3 scripts/freeciv/serve_event_tail.py \
  --events artifacts/freeciv/v5-live-200/events.jsonl \
  --game-id pln-v5-live-200 --host 127.0.0.1 --port 18765
```

Set `ws://127.0.0.1:18765` and the matching game ID in the Live view. Reconnects
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
The matched 480-turn active-tail runtime check is documented in
[live-tail runtime evidence](evidence/live-tail-runtime-comparison-v1.md).
Replay/performance results are in [Phase 5 evidence](evidence/phase-5-v1-v2.md),
plan/map behavior in [Phase 7 evidence](evidence/phase-7-v3.md), and audit/metrics
behavior in [Phases 10](evidence/phase-10-m6-v4.md) and
[11](evidence/phase-11-m7-v4.md).
