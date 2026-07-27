# FreeCiv Agent Observability: React App Specification

Visualization layer for the PLN-FreeCiv agent (see `pln-freeciv-spec.md`). Purpose: make every decision auditable — from raw observation through PLN inference to scheduled action — with the PLN input/output boundary as a first-class object, not a log line.

Companion principle to I6: **the UI renders the trace; it never recomputes agent logic.** Any derivation shown must come from the event log. If the UI needs a number the log doesn't contain, that's a logging gap (fix the emitter), not a UI computation.

---

## 0. Users & Core Questions

| User | Question the UI must answer |
|------|-----------------------------|
| Architecture reviewer (you) | "Why did the agent do X on turn 41?" — full causal chain in < 5 clicks |
| Epistemic auditor | "Did any unverified LLM claim reach the belief store?" / "Is confidence inflating along inference chains?" |
| Milestone validator | "Is A1.1 / A4.1 / A6.1 passing, and where are the failures?" |
| Tuning | "How does calibration move when λ or decay changes?" |

Non-goal: playing the game through this UI. Read-only observability, replay-first.

---

## 1. Data Contract (Event Log Schema)

The agent emits a **turn-scoped JSONL event stream**. This schema is the interface; both emitter and UI are versioned against it (`schema_version` on every event).

### 1.1 Event envelope

```json
{
  "schema_version": "1.0",
  "game_id": "uuid",
  "turn": 41,
  "seq": 17,
  "ts": "ISO-8601",
  "type": "pln_query | pln_result | observation | revision | llm_proposal |
           verification | quarantine | plan_created | plan_invalidated |
           plan_step_executed | action_sent | action_result | state_snapshot |
           technology_catalog | technology_progress | production_state |
           unit_lifecycle | metric_sample",
  "payload": { }
}
```

- **R1.1** Every event carries `turn`, monotone `seq` within turn, and `ts`. Ordering is (turn, seq), never wall-clock.
- **R1.2** Causal linkage: events reference parents by ID (`caused_by: [event_id]`). An `action_sent` must be reachable back to its `llm_proposal`, `pln_result`s, and `plan_created` via `caused_by` edges. Orphan actions are a logging bug the UI must surface, not hide.
- **R1.3** PLN boundary events are lossless:
  - `pln_query`: query atom, query type (deps / verify / grade), invoking layer (llm-verification / planner / monitor).
  - `pln_result`: full proof tree (nested AND/OR with per-node atom, TV ⟨s,c⟩, satisfied flag, rule applied, premise node refs), unsatisfied frontier, latency ms, chain depth, dampening λ applied per step.
- **R1.4** `revision` events carry: target atom, prior TV, evidence TV, posterior TV, provenance ID, revision formula inputs. (This is what makes A4.2/A4.3 auditable visually.)
- **R1.5** `quarantine` events carry the verbatim LLM claim, the failed check, and the atomspace evidence that contradicted it.
- **R1.6** `state_snapshot` (per turn): own-state summary + all uncertain atoms above a floor confidence, with map coordinates where applicable.
- **R1.7** Log volume budget: ≤ 5 MB/turn typical; proof trees deduplicated by structural hash (repeated identical subtrees stored once per turn, referenced).
- **R1.8** Domain observability events are explicit rather than reconstructed in the browser:
  - `technology_catalog`: hash-pinned compiled technology dependencies.
  - `technology_progress`: target, progress, cost, rate, ETA, stall duration, acquisitions, and exact known/researchable/blocked sets.
  - `production_state`: named six-yield vectors, city stocks and queues, and player economy.
  - `unit_lifecycle`: appearances/removals with cause and `exact | inferred | unattributed` evidence quality.

### Acceptance

- **A1.1** JSON Schema published in-repo; emitter and UI CI both validate against it; unknown `type` renders as raw JSON, never dropped silently.
- **A1.2** Causal completeness check: harness script over a 200-turn log finds zero `action_sent` events not reachable to a root `llm_proposal` or `monitor` trigger.
- **A1.3** A full 200-turn game log loads in the UI in < 10 s.

---

## 2. Application Shell

- **R2.1** Modes: **Replay** (load JSONL file / URL) and **Live** (WebSocket tail of a running game). Identical rendering path — live is replay with a moving end.
- **R2.2** Global turn scrubber: timeline across the top, one tick per turn, event-density heat strip (more events = darker), markers for plan invalidations (red) and quarantine events (amber). Scrubbing sets a global `(turn, seq)` cursor; every view renders **as-of** that cursor.
- **R2.3** As-of semantics are strict: no view may show information from events after the cursor. (Prevents hindsight leaking into audits.)
- **R2.4** Deep-linkable state: current view + cursor + selected entity encoded in URL.
- **R2.5** Layout: left nav (views), main panel, right inspector panel (renders whatever entity is selected anywhere: atom, event, plan, proof node).

### Acceptance

- **A2.1** Scrub from turn 1→200 at ≥ 10 turns/s without dropped frames on a 200-turn log (virtualized rendering).
- **A2.2** As-of property test: for 50 random cursors, no rendered atom TV differs from the TV reconstructible from events ≤ cursor.
- **A2.3** Any deep link reproduces the exact view state in a fresh session.

---

## 3. Views

### 3.1 Decision Timeline (default view)

Per-turn swimlane of the loop: `state ingest → LLM proposal → verification → PLN queries → plan → actions → engine results`, one lane per stage, events as nodes, `caused_by` edges drawn between lanes.

- **R3.1.1** Clicking any node opens it in the inspector; double-click follows to the specialized view (proof tree, plan, etc.).
- **R3.1.2** "Why this action?" affordance: select an `action_sent`, UI highlights the full causal ancestry path across lanes.
- **R3.1.3** Stage latency annotations per turn; turns exceeding the 30 s budget (R6.5 of agent spec) flagged.
- **A3.1** From cold load, answering "why did the agent do X on turn 41" — i.e., reaching the originating LLM proposal and the supporting proof tree — takes ≤ 5 interactions. Scripted UX test.

### 3.2 Proof Tree Explorer (the PLN I/O view)

Renders a `pln_result` proof tree. This is the centerpiece.

- **R3.2.1** AND/OR tree layout, collapsible; per node: atom (human-readable form), ⟨s, c⟩, satisfied ✓/✗, rule name. Unsatisfied frontier auto-highlighted (this *is* the blocked/ready surface).
- **R3.2.2** Crisp vs. uncertain visual channel: crisp nodes neutral; uncertain nodes colored on a confidence ramp. A crisp-only tree containing any node with s < 1.0 renders a violation badge (R1.6 of agent spec, visible).
- **R3.2.3** Confidence flow: hovering an uncertain root shows per-step derivation — premise TVs → formula → dampened result, with λ shown. Makes chained-inference inflation visually detectable.
- **R3.2.4** Diff mode: two proof trees for the same goal at different turns, structural diff (nodes appeared/vanished/TV-changed). Primary tool for understanding replans.
- **R3.2.5** OR-branch comparison strip: feasibility grade and scheduler cost side by side per branch, visually distinct (grade is not cost — two columns, never merged).
- **R3.2.6** The default selection is the newest proof at the global cursor. Manually selected older proofs carry a visible historical-proof label with emitted and cursor turns. `missing-tech` is defined in-view as an absent, currently researchable prerequisite rather than an unmet prerequisite of its own.
- **A3.2.1** Trees to 200 nodes render < 300 ms; larger trees virtualize (collapsed beyond depth 4 by default).
- **A3.2.2** Seeded log with a known confidence-inflation bug: reviewer locates the offending inference step via R3.2.3 in under 2 minutes (usability gate).

### 3.3 Atomspace Inspector

- **R3.3.1** Searchable/filterable atom table: predicate, args, current TV as-of cursor, provenance count, last-revised turn. Filters: crisp/uncertain, predicate type, confidence band, decaying-soon.
- **R3.3.2** Atom detail (inspector panel): full revision history as a sparkline of (s, c) over turns; each revision expandable to its `revision` event (prior/evidence/posterior, provenance ID).
- **R3.3.3** Provenance idempotence audit surface: atoms whose history contains same-provenance-ID double application flagged red (visual A4.2/A4.3).
- **A3.3.1** TV-as-of-cursor for any atom matches independent log fold (property test, 50 atoms × 20 cursors).
- **A3.3.2** Filter + search over 50k atoms responds < 200 ms (indexed client-side, or backend query — implementer's choice, budget is the contract).

### 3.4 Map Overlay

- **R3.4.1** Tile map (from `state_snapshot`) with layers: own units/cities (crisp), uncertain enemy atoms as markers with confidence encoded by opacity and age by ring decay, fog as-of cursor.
- **R3.4.2** Clicking a marker opens the atom in the inspector (revision history shows the observation → decay → re-scout arc).
- **R3.4.3** Plan overlay: selected plan's spatial steps drawn on map with ETA labels; broken-assumption tiles flash on invalidation events.
- **A3.4.1** A staleness scenario log (unit seen once, never re-scouted) is visually identifiable: marker fades below actionable threshold at the configured window. Screenshot test against reference.

### 3.5 Plan Board

- **R3.5.1** All plans as-of cursor: status (ACTIVE / COMPLETED / INVALID), goal, steps with predicted vs. actual turn, resource ledger, assumption list with live TVs and thresholds.
- **R3.5.2** Assumption margin bars: per assumption, current confidence vs. acceptance threshold. Assumptions within 0.05 of threshold rendered amber — the "about to break" surface.
- **R3.5.3** Invalidation view: broken atom named, TV drop shown, affected subtree highlighted in the linked proof tree, repair event linked (locality of repair visible per A5.2 of agent spec).
- **R3.5.4** ETA error chart per completed plan (predicted vs. actual, feeds A3.1 of agent spec).
- **A3.5.1** For a scripted invalidation log, the board shows cause-named invalidation within the same turn tick, and the repair's reused-vs-rederived subtrees are visually distinguishable.

### 3.6 Quarantine & Epistemic Audit

- **R3.6.1** Quarantine table: every quarantined LLM claim verbatim, failed check, contradicting evidence atoms (linked), turn. Running write-through counter (must read 0 — rendered large).
- **R3.6.2** Verification funnel per turn: LLM claims made → verified → quarantined → (write-throughs). A funnel with a nonzero final bar is the loudest thing on screen.
- **A3.6.1** Seeded log from agent-spec A6.1 (40 known-false claims): all 40 appear in quarantine table with correct evidence links; write-through counter reads 0; a deliberately corrupted log makes the counter read nonzero and the UI alarm.

### 3.7 Metrics Dashboard (M7 surface)

- **R3.7.1** Calibration plot: strength buckets vs. empirical frequency with ±0.15 band (agent A4.1), per game and pooled; per-λ overlay when the log contains sweep runs.
- **R3.7.2** Time series: engine-rejected-action rate, loop latency percentiles, replan latency, proof-tree depth distribution.
- **R3.7.3** Ablation comparison: side-by-side metric panels across harness conditions (a)–(e), reading condition ID from `game_id` metadata.
- **A3.7.1** Calibration plot from harness output matches the harness's own computed calibration numbers exactly (UI recomputes nothing — reads `metric_sample` events; cross-check in CI).

### 3.8 Technology Progress

- **R3.8.1** Current target card: accumulated/cost/remaining beakers, beakers per turn, ETA, status, and consecutive stalled turns.
- **R3.8.2** Hash-pinned prerequisite graph and searchable catalog show emitted known/current/researchable/blocked status and named missing prerequisites.
- **R3.8.3** Post-initial acquisitions and target progress/rate series link back to their source events and relevant PLN proof.
- **A3.8.1** A trace with 0 beakers/turn clearly reports that running longer under the unchanged economy will not converge; a later proof at the cursor replaces an earlier blocked proof by default.

### 3.9 Economy & Production

- **R3.9.1** Named food/shield/trade/gold/luxury/science output and surplus, stocks, economy allocation, current queues, and explicit queue changes.
- **R3.9.2** PF-PLN production projections render verbatim from `operation_scored`; the view separately reports whether buildable PLN proofs were actually invoked.
- **R3.9.3** Observed unit completions retain their lifecycle evidence quality.
- **A3.9.1** No city yield array index or PF projection is decoded/recomputed in the browser.

### 3.10 Unit Lifecycle

- **R3.10.1** Appearance/disappearance ledger with unit identity, cause, detail, source snapshots, and evidence quality.
- **R3.10.2** Cause and evidence-quality summaries never merge inferred or unattributed removals into exact combat claims.
- **R3.10.3** Future engine runs correlate `PACKET_UNIT_COMBAT_INFO` zero-HP outcomes with `PACKET_UNIT_REMOVE`; historical traces are enriched only by a non-destructive offline copy.
- **A3.10.1** Unknown historical boundary removals remain visibly unattributed; a packet-backed combat fixture renders attacker/defender loss as exact.

---

## 4. Technical Requirements

- **R4.1** React + TypeScript, strict mode. State: event-sourced store — the app state *is* a fold over the event log up to the cursor; views are projections. No view-local derived caches that can diverge from the fold.
- **R4.2** All list/tree rendering virtualized (logs are large; A2.1/A3.2.1 budgets are the contract).
- **R4.3** Charting: any capable lib (recharts/d3); tree layout custom or d3-hierarchy. No canvas-only rendering for proof trees — nodes must be selectable/inspectable DOM for the audit workflows.
- **R4.4** Live mode: WebSocket, append-only; reconnect resumes from last `(turn, seq)` (emitter supports replay-from-cursor).
- **R4.5** No agent-logic imports. The UI package must not depend on the PLN/scheduler code (enforced in CI by dependency check). Shared code is the schema types only.
- **R4.6** Replay files loadable fully client-side (no backend required for replay mode); live mode needs only the WS endpoint.
- **R4.7** Testing: property tests for the as-of fold (A2.2, A3.3.1); screenshot tests for map/proof-tree reference scenarios; scripted UX tests for A3.1 and A3.2.2 click budgets.

---

## 5. Milestones

| # | Deliverable | Gate |
|---|-------------|------|
| V0 | Schema + validator + synthetic log generator (scripted scenarios incl. the seeded-bug logs used in acceptance) | A1.1; every later milestone tests against V0 logs |
| V1 | Shell, scrubber, as-of fold, inspector, Decision Timeline | A2.1–A2.3, A3.1 |
| V2 | Proof Tree Explorer + Atomspace Inspector | A3.2.*, A3.3.* |
| V3 | Plan Board + Map Overlay | A3.4.1, A3.5.1 |
| V4 | Quarantine/Audit + Metrics Dashboard | A3.6.1, A3.7.1 |
| V4.1 | Technology + Economy/Production + Unit Lifecycle | A3.8.1, A3.9.1, A3.10.1 |
| V5 | Live mode | R4.4 soak: 200-turn live game, zero divergence from post-hoc replay of the same log |

V0's synthetic generator is deliberately first: the UI is built and accepted against *scripted* logs with known-correct renderings (including deliberately broken ones), so UI acceptance never depends on agent correctness — and vice versa.

---

## 6. Invariants

| # | Invariant | Enforcement |
|---|-----------|-------------|
| U1 | UI renders the trace, never recomputes agent logic | R4.5 dependency check; A3.7.1 cross-check |
| U2 | Strict as-of semantics — no hindsight leakage | A2.2 property test |
| U3 | Lossless PLN boundary — every query/result inspectable to formula level | R1.3, R3.2.3 |
| U4 | Anomalies are loud, not filtered (orphan events, write-throughs, crisp-drift, double-provenance) | R1.2, A3.6.1, R3.2.2, R3.3.3 |
| U5 | Grade ≠ cost, everywhere they co-appear | R3.2.5 review checklist |
