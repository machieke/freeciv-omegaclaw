# PLN-FreeCiv Implementation Plan From the Existing Base

Status: fully realized on `feature/pln-freeciv-agent` (2026-07-18 UTC)  
Companion specifications:

- `pln-freeciv-spec.md` — agent goals M0-M7
- `pln-freeciv-observability-spec.md` — observability goals V0-V5

## Realization record

All implementation-plan phases P0-P12 and their acceptance gates have been
implemented and verified from this retained base. The criterion-by-criterion evidence
index is [the release checklist](../docs/freeciv/release-checklist.md), with detailed
phase reports under `docs/freeciv/evidence/` and reproducible outputs under
`artifacts/freeciv/`.

The final release identity uses configuration
`e92fe9c4e0013df320d9b5a393b04bd4e53198efebca50ec9201335566d58400`,
implementation
`780d9146dd462d10d1767fe8bd1a08c707668a38ff6db597323ac264fddfc0d4`,
FreeCiv/freeciv-llm commit `26ba7124249f34fd3050ef29bf191bd4d8808018`,
and upstream patch SHA-256
`2c0fae26da7936470fe00eb4d4eb9096e0b8c2620defa2eff27e6b4b104f23f0`.
The configured live model is `qwen3-coder-next:latest` with temperature zero and
explicit `think: false`.

Final release evidence includes:

- the 250-job real engine matrix, with five 30-game main arms, two 20-game
  sequential induction arms, two 30-game grading arms, and zero final failures;
- a real 200-turn full-loop game with 200/200 turns below 30 seconds and zero
  rejected engine actions;
- a byte-reproducible 250-job representative matrix and aggregate;
- the 200-turn live/replay soak with zero divergence at 201 cursors;
- a passing cognitive-trace release audit, 152 Python tests, 18 observability tests,
  a production UI build, and 12 patched-proxy contract tests.

Subsequent impact-evaluation hardening preserves that realization while extending P11.R4. The
paired seed remains the experimental unit: its two arms execute serially, in the predeclared
alternating order, on one dedicated server port, while independent pairs may execute on three
workers. Worker count is part of behavioral manifest identity and is frozen for claim-eligible
cohorts. The proxy cache is game-scoped, the effective per-agent state-polling budget is tested,
and each next arm retains the authoritative pre-arm hard recycle. The redundant post-arm recycle
was removed because it duplicated the next pre-arm isolation boundary.

The original agent specification's A6.3 positive-effect prediction remains explicitly
recorded as `NOT MET`: the representative grading result is null, while the engine
grading win-rate point estimate is `+0.0333` with an interval including zero and its
score delta is zero. This does not fail implementation-plan P10.A3, which deliberately
requires the correctly controlled experiment and unfiltered result rather than a
positive empirical outcome.

This document turns the two specifications into an ordered implementation plan for this repository. It assumes the current FreeCiv implementation is retained as a tested operational base, while the reasoning core, planning model, event contract, and observability application are replaced behind stable boundaries.

The governing architecture remains:

- **FreeCiv engine** is ground truth.
- **State bridge** owns authoritative observed state and grounded numeric access.
- **PLN** owns dependency inference, uncertain beliefs, and assumption monitoring.
- **Scheduler** owns order, time, resource allocation, and plan cost.
- **LLM** proposes goals and hypotheses; it does not write authoritative facts.
- **Event log** is the only input to the observability application.

---

## 1. Delivery Decision

Do not create a new repository and do not discard the working game integration. Build a new domain architecture inside this repository and migrate the live loop to it phase by phase.

The current implementation has three roles during the migration:

1. **Reusable infrastructure:** FreeCiv client, turn advancement, legal-action validation, provider configuration, LLM transport, deterministic serialization helpers, and run reporting.
2. **Regression oracle:** existing tests and live smoke scenarios establish that transport and action submission continue to work while the cognitive core changes.
3. **Evaluation baseline:** the plain current LLM agent becomes M7 condition (a). The current hand-authored PLN hint rules are temporary legacy code, not part of the target architecture.

The target is therefore a **vertical replacement of the cognitive core**, not a rewrite of the operational shell.

### 1.1 Reuse and replacement map

| Current component | Disposition | Target use |
|---|---|---|
| `benchmarks/freeciv/client.py` | Keep and harden | HTTP/WebSocket transport, state and legal-action retrieval |
| `benchmarks/freeciv/turncycle.py` | Keep | Turn completion, monotonic turn advancement, reconnect behavior |
| `benchmarks/freeciv/actions.py` | Keep and extend | Final action shape validation plus snapshot/version validation |
| `benchmarks/freeciv/adapter.py` | Split | Keep raw-shape normalization and hashing; replace heuristic fact emission |
| `benchmarks/freeciv/atoms.py` | Reuse selectively | Canonical rendering and syntax validation helpers |
| `benchmarks/freeciv/freeciv_tool.py` | Replace state semantics | Keep tool boundary; route through the new state store and executor |
| `benchmarks/freeciv/reason.py` | Replace | Long-lived dependency/proof service; no output regex and no best-effort empty result |
| `benchmarks/freeciv/rules.metta` | Remove by the M0 gate | Generated ruleset artifacts only; no hand-authored game rules |
| `src/metta_sessions.py` | Do not use as the belief store | It may remain for non-FreeCiv features, but the agent gets a domain belief store |
| `src/scheduler.py` | Do not use as the planner | It schedules cron/webhook jobs and is unrelated to M3 |
| `src/tracing.py` | Reuse append mechanics only | New typed FreeCiv event emitter and causal validator |
| `src/memory_schema.py` | Reuse design ideas only | Provenance metadata concepts, not similarity retrieval as truth maintenance |
| duel/A-B runners and reporters | Extend | Fixed-seed five-condition M7 harness |
| `benchmarks/freeciv/viz/` | Retire after replacement | UX reference only; target UI is React + TypeScript and trace-only |

### 1.2 Compliance point for the legacy rules

M0 acceptance criterion A0.4 requires zero hand-written game rules anywhere in the repository. Therefore:

- Phase 0 may characterize the legacy PLN-hint behavior.
- The historical implementation remains recoverable from Git history and its run artifacts remain available.
- Before Phase 2 is accepted, `benchmarks/freeciv/rules.metta` must be removed, and no copied or renamed version may remain as executable game logic or a test fixture.
- M7 condition (a) uses the plain stock LLM agent. Later conditions use only the mechanically compiled rulebase.

---

## 2. Target Architecture and Repository Layout

### 2.1 Runtime flow

```text
FreeCiv engine / proxy
        |
        v
Authoritative State Bridge -----> append-only domain events ----------+
        |                                                            |
        +--> current state store --> grounded predicates              |
        |                              |                              |
        |                              v                              |
        +--> crisp atomspace --> dependency oracle --> proof tree     |
                                      |                              |
LLM query summary --> goal proposer --+--> verifier/grader            |
                                      |                              |
                                      v                              |
                              scheduler/planner --> action executor --+--> engine
                                      |
uncertain belief store --> assumption monitor / local repair          |
                                                                       v
                                                          JSONL replay + live tail
                                                                       |
                                                                       v
                                                        React observability app
```

Every arrow that changes state or contributes to a decision emits an event. The UI consumes only those events and shared schema types.

### 2.2 Proposed repository boundaries

The exact names may be adjusted in Phase 0, but the dependency boundaries must remain:

```text
src/freeciv_agent/
  rulesets/          # parser, canonical IR, compiler, generated signatures
  oracle/            # backward queries and proof objects
  state/             # authoritative snapshots and grounded procedures
  planning/          # schedules, resource ledgers, plan artifacts
  beliefs/           # uncertain atoms, evidence, revision, decay
  monitoring/        # assumptions, invalidation, local repair
  llm/               # query summaries, constrained proposals, verification
  execution/         # versioned action gate and engine submission
  events/            # event types, emitter, causal validation

schemas/freeciv-events/v1/
  envelope.schema.json
  payloads/*.schema.json

apps/freeciv-observability/
  src/event-store/   # parser, validator, as-of fold
  src/views/         # timeline, proofs, atoms, plans, map, audit, metrics

benchmarks/freeciv/
  legacy runners     # retained only where needed for condition (a)
  harness/           # M7 conditions, manifests, metrics, reports

scripts/freeciv/
  compile_ruleset
  validate_events
  generate_synthetic_log
  run_engine_parity
  run_harness

Autotests/freeciv/
  unit/
  property/
  integration/
  engine_parity/
  scenarios/
```

Generated Atomese, engine fixtures derived from rulesets, game logs, and large evaluation artifacts belong under ignored build/artifact directories. Compiler source, schemas, compact deterministic fixtures, manifests, and tests are tracked.

### 2.3 Dependency rules

- `rulesets` has no dependency on live state, the LLM, or the UI.
- `oracle` consumes compiled rules and typed state-query interfaces; it never reads raw proxy JSON.
- `state` may depend on transport DTOs but not on the LLM or scheduler.
- `planning` consumes proof trees and numeric accessors; it must not call PLN inference internally.
- `beliefs` may consume observations and crisp rule references but never overwrite authoritative own-state.
- `llm` consumes query-result DTOs and plan status, not raw engine snapshots.
- `execution` accepts only a validated plan step tied to a current snapshot ID.
- `apps/freeciv-observability` may import generated schema types only. It must not import Python agent logic or reimplement inference, revision, planning, or metrics.

---

## 3. Delivery Invariants and Gate Policy

### 3.1 Hard ordering

Agent milestones remain strictly ordered M0 through M7. Observability V0 starts early because it supplies the shared event contract. UI work after V0 may proceed against synthetic logs, but no UI progress relaxes an agent gate.

The following gates are absolute:

1. M0 compiler audit passes before M1 is accepted.
2. M1 engine parity is zero-mismatch before M2 is accepted as an agent input.
3. M2 authoritative-state fidelity passes before the scheduler can execute a plan.
4. M4 uncertain atoms are disabled in production configuration until all crisp gates pass.
5. M6 cannot write an LLM claim to a belief store without verification.
6. M7 reports failures and negative deltas without filtering or relabeling them.

### 3.2 Definition of done for every phase

A phase is complete only when all of the following are true:

- Its code and configuration are committed-ready and contain no workstation-specific paths.
- Its public interfaces and versioned artifacts are documented.
- Unit tests cover normal, boundary, malformed-input, and deterministic behavior.
- Required property, engine, scenario, or UI tests pass.
- Events emitted by the phase validate against the current schema.
- Performance measurements required by the phase are recorded by repeatable commands.
- Existing FreeCiv transport/action regression tests still pass.
- The phase acceptance report records command, configuration, dependency versions, random seed, result, and artifact hashes.

### 3.3 Reproducibility policy

Every run manifest must record at least:

- repository commit and dirty-state flag;
- FreeCiv and `freeciv-llm` commits or immutable image digests;
- ruleset name and ruleset source hash;
- compiler version and generated rulebase hash;
- model/provider name and sampling parameters;
- game seed, opponent identity and difficulty;
- confidence/decay/dampening/threshold configuration;
- event schema version;
- condition ID and enabled capabilities;
- wall-clock start/end and host performance profile.

Do not depend on `/home/...` paths or an uncommitted external proxy checkout. If `freeciv-llm` needs new state fields, land or pin that change upstream and reference an immutable commit/image from this repository.

---

## 4. Pre-Implementation Decisions

These decisions must be recorded as short architecture decision records during Phase 0.

### D1 — M0 edge-count ambiguity

R0.2 requires one implication per target with a conjunctive antecedent, while A0.1 describes the number of implications as equal to the number of `req1`/`req2` edges. Those statements cannot both be literal for a tech with two prerequisites.

Recommended resolution:

- emit one canonical implication per target;
- independently extract and compare the complete prerequisite **edge set** inside all antecedents;
- report both target-rule count and prerequisite-edge count;
- update A0.1 wording before declaring M0 complete.

### D2 — Crisp reasoner execution model

The current subprocess-per-query, regex-based PeTTa bridge cannot meet lossless proof or latency requirements. Phase 0 must spike and select one long-lived execution boundary:

- a persistent MeTTa/PeTTa service that exposes structured proof objects; or
- a persistent host proof service over the exact canonical compiled IR, with generated Atomese remaining the PLN representation and parity checked between representations.

Whichever is selected, there must be one compiler source of truth, no hand-maintained duplicate rules, structured errors, and no silent `[]` fallback. If the second option changes the intended meaning of “PLN dependency oracle,” amend the specification explicitly before Phase 3.

### D3 — Engine parity adapter

Select a repeatable way to invoke FreeCiv's native `research_goal_*` and buildability behavior against randomized states. Preferred order:

1. a small test executable linked to the same FreeCiv source/version used by the server;
2. a supported server scripting/test interface;
3. controlled ephemeral games only if the first two are infeasible.

The comparator must not reimplement the expected answer in Python.

### D4 — Bounded planner backend

Choose and pin either an HTN implementation or a small ILP/CP-SAT dependency for production-interleaved plans. Record deterministic tie-breaking, timeout behavior, and the fallback result returned when the bounded solver cannot prove a plan.

### D5 — Shared schema generation

Choose JSON Schema as the authoritative wire definition and decide how Python and TypeScript types are generated or validated from it. Hand-maintained divergent event interfaces are not acceptable.

---

## 5. Phased Implementation

## Phase 0 — Preserve and Characterize the Working Base

**Maps to:** migration foundation; no M/V milestone claimed  
**Depends on:** current `main` branch and working local FreeCiv stack

### Goal

Create a reproducible baseline, establish package boundaries, and resolve the high-risk architectural questions before modifying the live agent.

### Requirements

- **P0.R1** Record the current plain-LLM behavior as baseline condition `a_stock_llm`; do not label the handwritten hint system as the target PLN architecture.
- **P0.R2** Add a machine-readable run manifest with repository, engine, proxy, ruleset, provider, model, seed, and configuration identities.
- **P0.R3** Document the current proxy endpoints, WebSocket handshake, state shapes, legal-action format, and action response semantics as integration contracts.
- **P0.R4** Establish the target source, schema, UI, test, and artifact directories described above without moving unrelated OmegaClaw code.
- **P0.R5** Complete and record decisions D1-D5.
- **P0.R6** Create a capability matrix for the five future harness conditions so features can be enabled through configuration rather than maintained as five code forks.
- **P0.R7** Define a clean-development setup that pins the external FreeCiv/proxy version and does not rely on an arbitrary checkout in a developer home directory.
- **P0.R8** Preserve current user changes and keep the new architecture disabled by default until its phase gate passes.

### Deliverables

- baseline manifest schema and one captured baseline manifest;
- integration-contract documentation and DTO fixtures;
- ADRs for D1-D5;
- capability/condition configuration schema;
- smoke-test command for observe -> validate action -> submit -> advance turn;
- initial package skeletons with dependency-boundary tests.

### Acceptance criteria

- **P0.A1** The focused existing suite passes with no regressions; the current reference is 80 passed and 6 integration-dependent skips.
- **P0.A2** One clean baseline command produces a run artifact, manifest, per-turn records, and final summary for a fixed seed.
- **P0.A3** A one-turn live smoke test observes authoritative state, submits only a server-advertised legal action, and observes a monotonic turn advance.
- **P0.A4** Re-running the baseline with the same deterministic non-LLM inputs produces the same manifest identity and normalized state hashes.
- **P0.A5** No new code contains absolute developer paths; the external stack identity is a commit or immutable image digest.
- **P0.A6** D1-D5 have explicit decisions, owners, consequences, and reversal conditions.

---

## Phase 1 — V0 Event Contract, Validator, and Synthetic Logs

**Maps to:** observability V0 and cross-cutting trace foundation  
**Depends on:** Phase 0

### Goal

Define the versioned event interface before implementing new reasoning. Make correct, malformed, and adversarial traces available independently of agent correctness.

### Requirements

- **P1.R1** Publish JSON Schema for a common envelope containing `schema_version`, `event_id`, `game_id`, `turn`, turn-monotone `seq`, `ts`, `type`, `caused_by`, and typed `payload`.
- **P1.R2** Define payload schemas for every event in the observability specification, including complete proof trees, revisions, quarantines, plans, action lifecycle, snapshots, and metrics.
- **P1.R3** Define stable identifiers for atoms, proof nodes, proof subtrees, plans, plan steps, observations, provenance, snapshots, actions, and LLM proposals.
- **P1.R4** Deduplicate repeated proof subtrees by a canonical structural hash while preserving a lossless reference graph.
- **P1.R5** Implement an append-only writer with atomic line emission and a single sequence allocator per `(game_id, turn)`.
- **P1.R6** Implement streaming and full-file validators for schema, ordering, unique IDs, valid parent references, causal cycles, missing proof references, and action ancestry.
- **P1.R7** Unknown future event types remain valid at the envelope level and are preserved as raw JSON; known types must validate their payload schema.
- **P1.R8** Generate deterministic synthetic logs for:
  - a normal crisp proposal -> proof -> plan -> action path;
  - an unreachable goal and unsatisfied frontier;
  - a plan invalidation and local repair;
  - confidence decay and re-scout;
  - same-provenance replay and multi-path inference;
  - 40 quarantined false claims plus zero write-through;
  - deliberately corrupted orphan action, crisp-TV drift, duplicate provenance application, and nonzero write-through;
  - a 200-turn performance dataset with large atom/proof collections.
- **P1.R9** Add schema compatibility rules: additive optional fields within v1, explicit migration for breaking changes, and fixtures for every supported schema version.
- **P1.R10** Keep the generic trace format separate; do not overload `phase` strings to represent domain events.

### Deliverables

- `schemas/freeciv-events/v1/` schemas;
- Python event DTO/emitter and generated or validated TypeScript types;
- validator and causal-completeness CLI;
- deterministic synthetic log generator;
- good and seeded-bad compact fixtures;
- schema evolution guide.

### Acceptance criteria

- **P1.A1** Every generated good event validates in Python and TypeScript-compatible schema validation.
- **P1.A2** Each seeded corruption fails with the intended stable diagnostic and event ID; no unrelated diagnostic masks it.
- **P1.A3** A 200-turn synthetic log contains zero orphan `action_sent` events and validates causal reachability to `llm_proposal` or `monitor` roots.
- **P1.A4** Generation with the same seed produces byte-identical JSONL except where a test explicitly enables real timestamps or random IDs.
- **P1.A5** Typical generated log volume remains at or below 5 MB/turn, with a report showing subtree deduplication savings.
- **P1.A6** The validator streams the 200-turn fixture without loading the entire file and completes within the documented performance budget.
- **P1.A7** V0 A1.1 is satisfied. The UI load-time portion of observability A1.3 is deferred to Phase 5, when a UI exists.

---

## Phase 2 — M0 Ruleset Parser, Canonical IR, and Atomese Compiler

**Maps to:** agent M0  
**Depends on:** Phases 0-1 and resolution of D1

### Goal

Mechanically compile `civ2civ3` and `classic` FreeCiv rulesets into deterministic crisp rules and grounded-predicate signatures with complete source provenance.

### Requirements

- **P2.R1** Parse the FreeCiv secfile constructs used by `techs.ruleset`, `units.ruleset`, and `buildings.ruleset`: sections, comments, quoted/translatable strings, continuations, vectors/tables, booleans, optional columns, and empty vectors.
- **P2.R2** Normalize stable game identities from `rule_name` when present and documented fallback names otherwise; retain display name separately.
- **P2.R3** Represent requirements as typed IR with kind, target, range, `present`, source file/section/line, and whether the requirement is symbolic or grounded/quantitative.
- **P2.R4** Model `req1`, `req2`, `root_req`, `research_reqs`, unit/building `reqs`, obsolescence, disabled/`Never` targets, costs, and relevant city/player/world scopes without flattening distinct semantics.
- **P2.R5** Emit one canonical implication per target under the D1 resolution, with deterministic `And`, `Not`, variable, and atom ordering.
- **P2.R6** Emit distinct `has-tech`, `researchable`, `buildable`, `has-building`, and `usable-action` predicates.
- **P2.R7** Emit grounded predicate signatures for shield, gold, city-size, and other quantitative checks; emit no inferred numeric accumulation.
- **P2.R8** Attach crisp TV `<1.0, 0.99>` and ruleset/source metadata to every generated rule.
- **P2.R9** Produce canonical IR JSON, Atomese/MeTTa, a human-readable audit report, compiler diagnostics, and a manifest containing all source/output hashes.
- **P2.R10** Reject unsupported requirement kinds loudly with source location. Silent omission is forbidden.
- **P2.R11** Implement an independent extraction/count path for audits; it may share secfile lexical parsing but not the compiler's rule-building functions.
- **P2.R12** Generated game rulebases are build artifacts and ignored. No target rule may be handwritten or patched after generation.

### Deliverables

- secfile parser and typed canonical IR;
- deterministic Atomese compiler;
- grounded-signature catalog;
- independent audit extractor;
- ruleset manifests and audit commands for `civ2civ3` and `classic`;
- removal of the legacy hand-authored game rulebase.

### Acceptance criteria

- **P2.A1 / A0.1** Target-rule counts and complete prerequisite-edge sets match the independent extraction for both rulesets, under the amended D1 wording.
- **P2.A2 / A0.2** Seeded samples of 20 techs and 20 units produce antecedent dumps that exactly match the independent reference extraction.
- **P2.A3 / A0.3** Two clean compiler runs produce byte-identical IR, Atomese, reports, manifests, and hashes.
- **P2.A4 / A0.4** A repository scan finds zero hand-written game rules; generated rule directories are ignored and reproducible from source.
- **P2.A5** Every unsupported construct causes compilation failure with file, section, field, and reason.
- **P2.A6** `civ2civ3` and `classic` compile through the same code path with ruleset selection supplied only as data/configuration.
- **P2.A7** Static audit finds no numeric-accumulation conclusion in generated rules.
- **P2.A8** Compiler events and manifests validate under the Phase 1 schema or a backward-compatible schema extension.

---

## Phase 3 — M1 Crisp Dependency Oracle and Engine-Parity Harness

**Maps to:** agent M1, proof events needed by observability V2  
**Depends on:** Phase 2 and decisions D2-D3

### Goal

Return complete, deterministic AND/OR dependency proofs with explicit blocking frontiers and establish exact parity with FreeCiv before any uncertain reasoning is enabled.

### Requirements

- **P3.R1** Expose a typed `deps(goal, state_view)` API returning `ProofTree` or `Unreachable`, never unstructured text.
- **P3.R2** Proof nodes contain stable ID, atom, crisp TV, satisfied state, node kind, applied rule/source, premise references, scope, and optional grounded-predicate result.
- **P3.R3** Preserve conjunctions and all alternative paths. Deterministic canonical ordering must not be confused with selecting the first branch.
- **P3.R4** Return a typed unsatisfied frontier with missing-tech, missing-building, grounded-predicate, disabled-goal, and cycle blockers.
- **P3.R5** Detect cycles using the active query path and memoize completed subproofs; distinguish cyclic from globally unreachable goals.
- **P3.R6** Use a persistent reasoner/session or service. Process startup and rulebase import are outside the per-query hot path.
- **P3.R7** Return structured timeout/runtime errors. Never convert reasoner failure to an empty successful result.
- **P3.R8** Define and test crisp TV propagation so strength remains exactly 1.0 and confidence obeys the declared 0.99 floor semantics without formula drift.
- **P3.R9** Build the D3 native engine adapter and seed randomized legal and adversarial player tech states reproducibly.
- **P3.R10** Compare the oracle with `research_goal_*` for every tech and preserve minimized mismatch fixtures automatically.
- **P3.R11** Emit lossless `pln_query` and `pln_result` events, including full/deduplicated proof, frontier, latency, depth, and applied formula fields.
- **P3.R12** Isolate performance tests from cold-start setup and log p50, p95, p99, maximum, tree size, and cache status.

### Deliverables

- persistent crisp dependency service and typed client;
- proof/frontier schemas and canonical serializers;
- native FreeCiv engine oracle adapter;
- randomized parity/property harness with failure shrinking;
- performance benchmark and regression threshold;
- real Phase 1-compatible proof event fixtures.

### Acceptance criteria

- **P3.A1 / A1.1** For every tech and 50 randomized player tech states, prerequisite sets match FreeCiv exactly: zero mismatches.
- **P3.A2 / A1.2** For 100 randomized goal/state pairs, satisfying all reported leaves makes the engine goal available as defined by the amended test semantics; omitting each required leaf individually leaves it blocked.
- **P3.A3 / A1.3** Disabled and impossible goals return typed `UNREACHABLE` with a blocking frontier, never a partial proof labeled complete.
- **P3.A4 / A1.4** The longest full-depth `civ2civ3` tech query completes below 500 ms on the recorded dev profile; a regression over 2x the accepted baseline fails CI.
- **P3.A5** Crisp proof property tests find zero node with strength other than 1.0 or confidence outside the declared floor rule.
- **P3.A6** Synthetic cycle and diamond/OR graphs terminate, preserve all paths, and reuse structurally identical subproofs without losing parent references.
- **P3.A7** Killing or timing out the reasoner produces a visible structured failure event and prevents plan/action execution.
- **P3.A8** The observability causal validator can traverse each real `pln_result` back to its query and invoking event.

This is the crisp parity hard gate. Phase 8 cannot begin unless P3.A1 remains green.

---

## Phase 4 — M2 Authoritative State Bridge and Grounded Predicates

**Maps to:** agent M2  
**Depends on:** Phase 3

### Goal

Replace heuristic/accumulating FreeCiv facts with complete per-turn authoritative snapshots, grounded quantitative queries, and snapshot-versioned action safety.

### Requirements

- **P4.R1** Define typed proxy DTOs and domain snapshots for own techs/research progress, cities, units, production, stockpiles, gold, beakers, per-turn rates, visible map/fog, and server legal/buildable actions.
- **P4.R2** Extend and pin `freeciv-llm` where its current optimized state omits required authoritative fields. Contract fixtures must accompany upstream changes.
- **P4.R3** Give each snapshot a stable `(game_id, turn, source_seq, state_hash)` identity and store one current authoritative snapshot per game/player.
- **P4.R4** Replace own-state facts transactionally each turn. Removal from the engine state removes the corresponding crisp atom; it is not revised or retained as uncertain evidence.
- **P4.R5** Keep authoritative own-state, visible observations, and uncertain beliefs in separate namespaces/stores with explicit conversion boundaries.
- **P4.R6** Generate a grounded-predicate registry from Phase 2 signatures. Every call reads a supplied snapshot ID and returns typed value, satisfaction result, inputs, and diagnostic.
- **P4.R7** Expose `beakers-per-turn`, per-city `shields-per-turn`, costs, stockpiles, and other planner rates as numeric accessors, never derived atoms.
- **P4.R8** Provide query APIs that build the LLM-visible state summary. Remove direct raw-state injection from the target LLM path.
- **P4.R9** Attach source snapshot ID and legal-action-set digest to every proposed plan step/action. Reject execution if the current snapshot differs or grounded preconditions no longer hold.
- **P4.R10** Treat a missing server buildability bitvector or ruleset packet as unavailable/invalid state, not as permission to build.
- **P4.R11** Emit `state_snapshot`, grounded-check, verification, `action_sent`, and `action_result` events with causal links and snapshot identities.
- **P4.R12** Build an engine-side scripted comparator that checks every own-state field and atom at each turn.

### Deliverables

- versioned proxy/domain DTO contracts;
- transactional authoritative state store;
- crisp atomspace synchronizer with replacement semantics;
- generated grounded-predicate registry and numeric accessors;
- query-only state summary service;
- snapshot-versioned execution gate;
- 100-turn state/action comparator scenario.

### Acceptance criteria

- **P4.A1 / A2.1** Across a 100-turn scripted game, every own-state atom and grounded value matches engine state at end of turn with zero tolerance.
- **P4.A2 / A2.2** Across 100 turns of randomized legal play, no action reaches the engine from a stale snapshot and the engine rejects zero actions because of state mismatch.
- **P4.A3 / A2.3** Static and runtime audits find no numeric accumulation performed through inference and no quantitative derived atoms stored in the atomspace.
- **P4.A4** A disappearing unit/city/production assignment is absent immediately after the next transactional snapshot; no previous-turn authoritative atom survives accidentally.
- **P4.A5** Deliberately replaying an action from the prior snapshot is rejected locally with a `stale_snapshot` reason and no engine submission.
- **P4.A6** Missing/incomplete ruleset or buildability data blocks affected queries/actions with an observable diagnostic.
- **P4.A7** The target LLM request path can be dependency-tested to show it receives query summaries and cannot import/access the raw proxy snapshot type.

---

## Phase 5 — V1/V2 Replay Shell, Decision Timeline, Proofs, and Atomspace

**Maps to:** observability V1-V2  
**Depends on:** Phase 1; use Phase 3-4 real logs in addition to synthetic fixtures

### Goal

Replace the vanilla dashboard with a strict React/TypeScript event-sourced replay application that can audit the crisp pipeline without recomputing it.

### Requirements

- **P5.R1** Create a React + TypeScript strict-mode package with locked dependencies and reproducible build/test commands.
- **P5.R2** Parse JSONL incrementally, validate envelopes/payloads, preserve unknown events, and build application state solely by folding events through a global `(turn, seq)` cursor.
- **P5.R3** Implement strict as-of semantics, indexed event/atom/proof access, URL deep links, and selected-entity inspector state.
- **P5.R4** Implement the global scrubber, event density, invalidation/quarantine markers, left navigation, main view, and right inspector shell.
- **P5.R5** Implement the decision timeline swimlanes and causal ancestry highlighting for “why this action?” workflows.
- **P5.R6** Implement DOM-selectable, virtualized AND/OR proof trees with crisp/uncertain channels, frontier highlighting, formula details, diffs, and grade-vs-cost separation.
- **P5.R7** Implement the atomspace table, filters, as-of TVs, provenance/revision history, and duplicate-provenance flags.
- **P5.R8** Enforce a dependency rule that the UI imports only event schema/types, not agent, PLN, state, scheduler, or harness implementations.
- **P5.R9** Keep all large lists/trees virtualized and measure the specification's load, scrub, render, search, and interaction budgets.
- **P5.R10** Retire offline atom reconstruction. If required data is absent, render a logging-gap diagnostic.

### Deliverables

- React/TypeScript application and build pipeline;
- event store, cursor fold, indexes, and migrations;
- replay loader and deep-link router;
- shell, timeline, proof explorer, atomspace inspector;
- property, performance, screenshot, accessibility, and scripted UX tests;
- dependency-boundary CI check.

### Acceptance criteria

- **P5.A1 / A1.3** The 200-turn Phase 1 performance log loads in under 10 seconds on the recorded browser/dev profile.
- **P5.A2 / A2.1** Scrubbing turns 1-200 sustains at least 10 turns/second without dropped-frame budget violations.
- **P5.A3 / A2.2** For 50 random cursors, every displayed atom TV equals an independent fold over events at or before the cursor.
- **P5.A4 / A2.3** A fresh browser session reproduces view, cursor, selection, and filters from a deep link.
- **P5.A5 / A3.1** The scripted “why action X on turn 41?” workflow reaches proposal and supporting proof within five interactions.
- **P5.A6 / A3.2.1** A 200-node proof renders in under 300 ms; larger trees virtualize/collapse according to the specification.
- **P5.A7 / A3.2.2** The seeded confidence-inflation trace exposes the offending inference step through the formula view within the usability limit.
- **P5.A8 / A3.3.1** Independent atom folds match for 50 atoms across 20 cursors.
- **P5.A9 / A3.3.2** Search/filter over 50,000 atoms responds under 200 ms on the recorded profile.
- **P5.A10** Static dependency analysis finds zero agent-logic imports and tests demonstrate that missing fields are not recomputed by a view.

---

## Phase 6 — M3 Proof-to-Plan Scheduler

**Maps to:** agent M3  
**Depends on:** Phase 4 and D4

### Goal

Turn proof alternatives into deterministic, durationed, resource-consistent plans without moving inference or confidence semantics into the scheduler.

### Requirements

- **P6.R1** Define immutable `Plan`, `PlanStep`, `ResourceLedger`, `PlanAssumption`, and `BranchScore` artifacts with versioned serialization.
- **P6.R2** Accept only an M1 proof plus M2 grounded numeric/rate snapshot. The planner may inspect proof structure but may not issue new logical deductions.
- **P6.R3** Topologically order tech dependencies with deterministic tie-breaking and calculate durations from costs, current progress, beakers, and applicable rates.
- **P6.R4** Represent each stockpile and future production allocation explicitly. Ledger validation must prevent allocation to more than one consuming branch/step.
- **P6.R5** Preserve every feasible OR candidate long enough to report feasibility grade separately from scheduler cost, then select by a declared cost profile.
- **P6.R6** Support default turns-to-goal and a configurable gold-weighted cost profile. Confidence is never added numerically to cost.
- **P6.R7** Use the D4 bounded planner for production-interleaved goals with horizon at most 30 turns, deterministic timeout, and explicit `NO_PLAN_WITHIN_HORIZON` output.
- **P6.R8** Include source proof hash, snapshot ID, assumptions, selected/rejected branches, ledger, predicted turns, solver identity, and cost profile in every plan.
- **P6.R9** Revalidate the next plan step against the current M2 snapshot immediately before execution.
- **P6.R10** Emit `plan_created`, `plan_step_executed`, relevant query/check, action, and metric events as a connected causal graph.

### Deliverables

- plan domain model and serializers;
- tech DAG scheduler;
- bounded production scheduler;
- linear resource ledger and validator;
- branch cost profiles and deterministic selection;
- pre-execution step validator;
- plan property/scenario/performance test suites.

### Acceptance criteria

- **P6.A1 / A3.1** For 30 uninterrupted live tech goals, predicted completion is within +/-1 turn for at least 95%.
- **P6.A2 / A3.2** Ten thousand generated AND trees with shared demands produce zero resource double-spends.
- **P6.A3 / A3.3** On 20 sampled `civ2civ3` goals, the greedy tech schedule is no more than 5% worse than exhaustive/ILP optimum.
- **P6.A4 / A3.4** Every executed step remains engine-legal at execution time, with zero rejected planned actions over a 200-turn game.
- **P6.A5** Grade and cost remain distinct fields in schema, plan output, logs, and tests; no formula combines them.
- **P6.A6** Identical proof, snapshot, and configuration produce byte-identical plan artifacts.
- **P6.A7** Solver timeout or horizon exhaustion emits a typed non-plan result and never falls through to an unverified action.

---

## Phase 7 — V3 Plan Board and Map Overlay

**Maps to:** observability V3  
**Depends on:** Phases 5-6

### Goal

Make scheduled intent, resource use, spatial steps, ETA error, and future assumption failures auditable from replay events.

### Requirements

- **P7.R1** Render all plans as-of cursor with status, goal, source proof, steps, predicted/actual turns, cost profile, and resource ledger.
- **P7.R2** Render selected-plan spatial steps and ETAs over the event-provided map snapshot; do not calculate paths in the UI.
- **P7.R3** Render assumptions and confidence margins even though crisp plans initially have none; use synthetic M5 events until Phase 9 produces real ones.
- **P7.R4** Link plan branches, proof nodes, grounded checks, action lifecycle, and map entities bidirectionally through event IDs.
- **P7.R5** Compute no ETA/calibration/ledger metric in the UI. Render event-provided values and independently cross-check them in tests.
- **P7.R6** Add screenshot/reference scenarios for crisp plan execution, shared resource demand, spatial plan, and invalidation/repair.

### Deliverables

- Plan Board, ledger view, ETA chart, and linked inspector;
- map/fog/own-unit/uncertain-marker layers driven by snapshots;
- selected plan overlay and invalidation rendering;
- reference screenshots and interaction tests.

### Acceptance criteria

- **P7.A1 / A3.4.1** The staleness fixture visibly fades an uncertain marker below threshold at the configured turn without reading future events.
- **P7.A2 / A3.5.1** The invalidation fixture names the broken assumption in the same turn tick and distinguishes reused from re-derived subtrees.
- **P7.A3** Ledger allocations, plan ETAs, and actual turns match their source events exactly in DOM assertions.
- **P7.A4** Selecting any plan step reaches its source proof and action result without losing the global cursor.
- **P7.A5** Map and plan views pass screenshot tests at defined viewports and keyboard selection remains available for auditable nodes.

---

## Phase 8 — M4 Provenance-Aware Uncertain Beliefs

**Maps to:** agent M4  
**Depends on:** P3.A1 crisp parity and Phase 4 fidelity; uncertainty feature flag remains off until this phase passes

### Goal

Add fog-of-war and opponent inference without contaminating authoritative state or double-counting correlated evidence.

### Requirements

- **P8.R1** Model each visible enemy observation as immutable evidence with unique provenance ID, game/turn/location, source sensor, observed atom, and TV.
- **P8.R2** Store uncertain beliefs separately from current crisp own-state and retain complete revision history.
- **P8.R3** Implement configurable, declared confidence decay by observation age and predicate class; record the exact schedule and threshold in manifests/events.
- **P8.R4** Implement abductive prerequisite-closure inference from observed unit/building types using only the compiled crisp rulebase.
- **P8.R5** Implement uncertain deduction and threat/buildability conclusions with per-step dampening lambda applied and logged.
- **P8.R6** Make revision idempotent by provenance. Replaying the same event or reaching the same conclusion through several paths rooted in one provenance ID contributes evidence once.
- **P8.R7** Track support as provenance sets/graphs so path correlation is explicit rather than inferred from coincident TVs.
- **P8.R8** Persist cross-game induction evidence counts by opponent identity and ruleset/model version. Do not mix incompatible opponent or ruleset populations silently.
- **P8.R9** Expose omniscient engine truth only to post-game audit/calibration jobs, never to the live agent.
- **P8.R10** Emit observation, revision, decay, derivation, and metric events with formula inputs, prior/evidence/posterior TVs, lambda, and provenance IDs.
- **P8.R11** Add parameter sweep definitions for decay, lambda, and actionable thresholds; no confidence-affecting constant may exist only in code.

### Deliverables

- uncertain atom/evidence/provenance data model;
- decay service and revision engine;
- abductive and uncertain deduction queries;
- provenance-idempotence graph/index;
- cross-game opponent evidence store;
- post-game omniscient comparator and calibration report;
- scenario, replay, property, and multi-game tests.

### Acceptance criteria

- **P8.A1 / A4.1** Across at least 50 fixed-opponent games, each populated 0.1 strength bucket is within +/-0.15 empirical frequency or is explicitly reported insufficient-sample; pooled and per-opponent counts are shown.
- **P8.A2 / A4.2** Replaying the identical observation stream twice produces byte-identical final beliefs/TVs to one replay.
- **P8.A3 / A4.3** A single observation supporting one conclusion through three paths yields the single-provenance value within declared numeric tolerance.
- **P8.A4 / A4.4** At confidence over 0.5, abductive `has-tech` conclusions are at least 80% true against post-game ground truth, and no unseen enemy claim becomes crisp.
- **P8.A5 / A4.5** A once-seen unit decays below threshold within the configured window and the scripted policy requests re-scouting instead of acting on stale belief.
- **P8.A6** Crisp M1 parity tests remain unchanged and green with the uncertain layer installed but disabled/enabled.
- **P8.A7** Static configuration audit accounts for every confidence-affecting parameter in manifest, event log, and sweep schema.

---

## Phase 9 — M5 Assumption Monitoring and Local Plan Repair

**Maps to:** agent M5 and real V3 invalidation data  
**Depends on:** Phase 8

### Goal

Tie plan validity to explicit uncertain assumptions and repair only the dependency subtree invalidated by belief revision.

### Requirements

- **P9.R1** Every plan records each uncertain assumption, acceptance threshold, supporting proof node/subtree, provenance support, and affected steps.
- **P9.R2** Maintain an index from atom revision to active plan assumptions and from assumptions to exact proof/plan subtrees.
- **P9.R3** Evaluate monitors after each relevant revision/decay and before each action execution.
- **P9.R4** On threshold crossing, transition plan atomically from ACTIVE to INVALID with broken atom, old/new TV, threshold, revision event, and affected steps.
- **P9.R5** Prevent the executor from sending any step whose plan is invalid or whose assumption check belongs to an older revision.
- **P9.R6** Re-run dependency/planning only from the invalidated node. Reuse unaffected immutable subtrees by structural hash and record reused/re-derived sets.
- **P9.R7** Surface repair failure as an explicit no-plan state rather than restoring the invalid plan.
- **P9.R8** Emit `plan_invalidated`, repair query/result, replacement `plan_created`, and metrics with complete causal linkage.

### Deliverables

- assumption/threshold representation;
- reverse dependency indexes and monitor loop;
- atomic plan status transitions and executor guard;
- local proof/plan repair pipeline;
- invalidation and locality instrumentation;
- adversarial scenario suite.

### Acceptance criteria

- **P9.A1 / A5.1** The chokepoint scenario invalidates the plan within one turn and names the exact chokepoint atom and revision.
- **P9.A2 / A5.2** In an N-subtree plan with one broken assumption, instrumentation shows only the affected subtree was re-derived; all unaffected subtree hashes are reused.
- **P9.A3 / A5.3** Across 50 adversarial games, zero actions execute from already-invalid plans.
- **P9.A4 / A5.4** Repair completes under two seconds for plans up to 50 steps on the recorded dev profile.
- **P9.A5** Simultaneous assumption failures produce one coherent invalidation transaction and deterministic repair input, not racing replacement plans.
- **P9.A6** Replay UI renders the real invalidation/repair identically to the Phase 7 fixture and shows no future-state leakage.

---

## Phase 10 — M6 Constrained LLM Proposer/Verifier/Grader and V4 Audit

**Maps to:** agent M6 and observability V4 quarantine surface  
**Depends on:** Phase 9

### Goal

Restrict the LLM to proposing typed goals and claims, verify everything before use, grade candidates through PLN/planning, and expose the complete epistemic audit.

### Requirements

- **P10.R1** Build the LLM input exclusively from M2 query results, current plan status, invalidation reasons, allowed goal predicates/entities, and declared budgets.
- **P10.R2** Define a versioned structured output schema for candidate goals, factual claims, rationale, and selection. Goals reference canonical rulebase IDs rather than guessed free text.
- **P10.R3** Validate syntax and symbol existence before any query. Reject unknown predicate/entity/scope with a bounded corrective re-prompt.
- **P10.R4** Route every factual claim to exactly one sink: believe after verification, disbelieve with evidence, or quarantine when unverifiable/invalid.
- **P10.R5** Quarantine stores verbatim claim, proposal ID, model/config, failed check, contradicting/insufficient evidence, and timestamp; it is not queryable as belief.
- **P10.R6** Run dependency feasibility and planner cost for each valid candidate and return distinct grade/cost fields to the LLM for final selection.
- **P10.R7** Require the selected goal/action ancestry to include proposal, verification, PLN result, plan, current snapshot, and action result events.
- **P10.R8** Enforce per-stage and whole-turn timeouts with an explicit safe no-op/end-turn policy; timeout cannot bypass verification.
- **P10.R9** Track proposal validity, retries, quarantines, write-throughs, per-stage latency, token use, and selection changes.
- **P10.R10** Implement the V4 quarantine table, verification funnel, write-through alarm, and links to contradictory atoms/events.

### Deliverables

- query-summary builder and allowed-symbol catalog;
- structured proposer/selection schemas and prompt versions;
- claim translator/verifier and three-sink router;
- quarantine store and write-through detector;
- candidate grade/cost loop;
- timeout/fallback policy;
- Quarantine & Epistemic Audit UI;
- seeded confabulation and behavior A/B fixtures.

### Acceptance criteria

- **P10.A1 / A6.1** Of 100 seeded outputs containing 40 known-false claims, zero false claims reach authoritative/belief stores and all 40 appear in quarantine with provenance/evidence.
- **P10.A2 / A6.2** At least 95% of proposals on the evaluation prompt set translate to real goals; all rejects produce bounded correction or typed failure without crash.
- **P10.A3 / A6.3** A 30-game graded-vs-ungraded experiment runs through the M7-compatible harness and reports win-rate/score effect without requiring a positive result to pass infrastructure validation.
- **P10.A4 / A6.4** At least 95% of turns in a 200-turn game complete the full loop within 30 seconds.
- **P10.A5 / A3.6.1** The seeded 40-false-claim log shows all claims, correct links, and write-through count zero; a corrupted trace produces a prominent nonzero alarm.
- **P10.A6** Attempts to inject raw state, unknown atoms, or quarantined claims into planner/belief APIs fail dependency/security tests.
- **P10.A7** Every sent action passes the causal-completeness validator back to a proposal or monitor trigger.

---

## Phase 11 — M7 Five-Condition Harness, Statistics, and V4 Metrics

**Maps to:** agent M7 and remaining observability V4  
**Depends on:** Phase 10

### Goal

Run reproducible ablations that attribute behavior and performance to each layer, including negative results and repeated-opponent induction.

### Requirements

- **P11.R1** Implement conditions from one codebase and immutable capability configurations:
  - `a_stock_llm`;
  - `b_state_oracle` (M2, no inference/planner);
  - `c_dependency_scheduler` (M1/M2/M3);
  - `d_uncertain_monitor` (M1-M5);
  - `e_full_loop` (M1-M6).
- **P11.R2** Use the same fixed seed list, opponent pool/difficulty, ruleset, turn limit, engine/proxy versions, and machine class for all conditions.
- **P11.R3** Run at least 30 completed games per condition and distinguish retry/infrastructure failure from game loss.
- **P11.R4** Support resumable execution, isolated game IDs/ports/artifacts, bounded concurrency, and deterministic assignment of seeds to workers.
- **P11.R5** Calculate win rate, score at turn N, rejected-action rate, confabulation write-through, calibration, ETA error, replan latency, and loop latency from validated metric events.
- **P11.R6** Predeclare statistical methods: Wilson interval for binary rates and bootstrap or another declared interval for continuous/paired deltas; pair conditions by seed where possible.
- **P11.R7** Run at least 20 consecutive games against the same identified opponent personality for induction, preserving opponent memory only where the condition allows it.
- **P11.R8** Produce per-game raw manifests/events, a machine-readable aggregate, and a human-readable report containing failures and negative/null results at equal fidelity.
- **P11.R9** Explicitly compare the oracle-only marginal delta with the induction delta rather than assuming the stated prediction.
- **P11.R10** Implement the V4 metrics UI exclusively from `metric_sample` and aggregate events; the UI must not recalculate calibration or confidence intervals.
- **P11.R11** Cross-check every displayed aggregate against the harness artifact in CI.

### Deliverables

- capability/condition runner and one-command harness;
- pinned seed and opponent manifests;
- retry/resume/parallel isolation controller;
- metric calculators and statistical report generator;
- repeated-opponent track;
- Metrics Dashboard with calibration, latency, errors, depth, and ablation views;
- compact representative result fixture suitable for CI.

### Acceptance criteria

- **P11.A1 / A7.1** All five conditions complete on identical seed sets from one documented command and can be reproduced from their manifests.
- **P11.A2 / A7.2** The report shows each layer's paired marginal effect on every metric with the declared confidence interval and sample count.
- **P11.A3 / A7.3** Oracle-only and induction deltas are compared explicitly; the report is valid whether either delta is positive, null, or negative.
- **P11.A4 / A7.4** Losses, failed hypotheses, null effects, and infrastructure exclusions are visible and retain the same per-game fidelity as wins.
- **P11.A5** At least 30 valid games exist per condition and at least 20 sequential same-opponent games exist for the induction track.
- **P11.A6 / A3.7.1** UI calibration/ablation values match harness-emitted metrics exactly, including bounds and sample counts.
- **P11.A7** Re-running the aggregator over unchanged event logs produces byte-identical machine-readable results.
- **P11.A8** No condition imports code disallowed by its capability manifest; this is enforced by runtime assertions and tests.

---

## Phase 12 — V5 Live Mode, Soak, and Release Gate

**Maps to:** observability V5 and whole-system readiness  
**Depends on:** Phase 11

### Goal

Use the exact replay data path for a live append-only event tail, prove replay/live equivalence, and complete a whole-system release audit.

### Requirements

- **P12.R1** Expose a read-only live WebSocket event tail with resume from the last `(game_id, turn, seq)` and bounded reconnect/backfill.
- **P12.R2** Persist events before broadcast or otherwise guarantee that an acknowledged event can be replayed after process restart.
- **P12.R3** Feed live events into the same validator, fold, indexes, and views as replay mode. No live-only state model or agent API is allowed.
- **P12.R4** Detect duplicate, gap, out-of-order, incompatible-schema, and truncated events visibly; repair only through replay-from-cursor.
- **P12.R5** Bound memory with indexed/virtualized storage without changing as-of results.
- **P12.R6** Run a 200-turn live soak, archive its exact event log, and compare live application state with a fresh post-hoc replay at sampled and final cursors.
- **P12.R7** Run all cross-cutting static audits: no handwritten rules, no UI agent imports, no arithmetic inference, all confidence parameters declared, no raw state to LLM, no orphan action, no invalid-plan action.
- **P12.R8** Publish setup, configuration, operations, failure recovery, ruleset compilation, parity, harness, and UI documentation.

### Deliverables

- live event-tail service and reconnect protocol;
- replay/live equivalence comparator;
- soak report and archived manifest/hashes;
- operational and developer documentation;
- final invariant audit report;
- release checklist mapping every M0-M7 and V0-V5 criterion to evidence.

### Acceptance criteria

- **P12.A1 / V5** A 200-turn live game has zero divergence from post-hoc replay of the exact same log at every sampled cursor and final state.
- **P12.A2** Forced UI disconnect/reconnect resumes without missing or double-applying events.
- **P12.A3** Forced emitter/UI restart preserves causal completeness and deterministic replay.
- **P12.A4** The complete log remains within the volume budget or records an approved schema-compatible mitigation with no information loss.
- **P12.A5** Every original M0-M7 and V0-V5 acceptance criterion links to a command, artifact, and passing result or is explicitly recorded as not met; no implicit waiver is allowed.
- **P12.A6** A clean environment can follow the setup documentation through ruleset compile, focused tests, one live smoke turn, replay UI load, and a small harness smoke run.

---

## 6. Configuration and Environment Strategy

### 6.1 Configuration layers

Use versioned configuration files for behavior and environment variables only for secrets or deployment-specific endpoints.

Suggested configuration groups:

- `config/freeciv/engine.yaml` — proxy URLs, pinned engine/proxy identity, ruleset, turn limits;
- `config/freeciv/agent.yaml` — capability flags, query/planner limits, timeout policy;
- `config/freeciv/beliefs.yaml` — decay schedule, dampening lambda, thresholds, persistence policy;
- `config/freeciv/harness/*.yaml` — conditions, seeds, opponents, repetitions, statistics;
- existing provider profile — model, API style, base URL, API key environment variable;
- UI runtime configuration — replay URL and live event endpoint only.

### 6.2 Environment variables

Names must be confirmed against existing conventions in Phase 0. Expected categories are:

- provider secrets such as `OLLAMA_API_KEY` when the provider requires one;
- engine/proxy endpoint overrides for container/CI deployment;
- event output/artifact directory overrides;
- CI-only engine binary or ruleset-root discovery when not packaged in an image.

Do not require secrets for local Ollama if the local server does not enforce them. Do not store model sampling, confidence parameters, seed lists, or capability conditions only in environment variables; they belong in manifests and versioned configuration.

### 6.3 Clean setup target

By Phase 4, a developer should need only:

1. the repository checkout;
2. a pinned FreeCiv/proxy image or documented build command;
3. Python and Node package installation from locked dependencies;
4. an available configured LLM endpoint for LLM phases;
5. no undisclosed credentials for compiler, oracle, state, planner, replay UI, or non-LLM tests.

CI should run M0/M1 unit/parity subsets and V0/replay tests without an LLM. Expensive live and 30/50-game suites should run as explicit integration/nightly/release jobs with retained artifacts.

---

## 7. Test and CI Structure

### 7.1 Fast pull-request lane

- existing FreeCiv adapter/client/turn/action regressions;
- secfile parser and compiler unit/golden tests;
- deterministic serialization tests;
- proof-tree unit/property tests on compact graphs;
- state replacement and grounded-predicate tests with fixtures;
- planner ledger property subset;
- event schema/causal validation;
- UI unit/as-of property tests and compact screenshots;
- dependency/static invariant audits.

### 7.2 Engine integration lane

- full M0 compilation for both rulesets;
- M1 native engine parity matrix;
- scripted M2 state comparator;
- planner live-step legality;
- live turn smoke and reconnect tests.

### 7.3 Nightly/statistical lane

- 10,000-case ledger property suite;
- long proof and UI performance fixtures;
- adversarial games and repair latency;
- partial calibration/LLM latency trend runs;
- replay/live soak subsets.

### 7.4 Release/evaluation lane

- full M4 50-game calibration requirement;
- M5 50-game zombie-plan audit;
- M6 200-turn latency and 30-game grading test;
- M7 five conditions x at least 30 games;
- 20-game repeated-opponent track;
- V5 200-turn live/replay equivalence soak.

All randomized tests log and preserve failing seeds. Property-test failures should shrink to compact fixtures that are added to the fast lane.

---

## 8. Risk Register and Early Mitigations

| Risk | Why it matters | Mitigation/gate |
|---|---|---|
| FreeCiv secfile semantics are broader than a simple config parser | Silent requirement loss would invalidate every later layer | Typed unsupported diagnostics, independent extractor, two-ruleset audit in Phase 2 |
| PeTTa cannot expose structured backward proofs within latency | Current regex bridge cannot meet M1 or observability requirements | D2 spike in Phase 0; persistent service; explicit spec amendment if host proof recorder is required |
| Native engine parity is hard to drive with randomized states | A Python reimplementation is not a valid ground truth | D3 native test adapter and minimized mismatch fixtures before M1 work expands |
| Proxy optimized state omits rates/resources | M2 fidelity and M3 ETA cannot pass with zeros/missing fields | Upstream/pin proxy changes, DTO fixtures, missing-data-is-invalid policy |
| Legacy rules conflict with A0.4 | Keeping them anywhere fails the zero-handwritten-rule gate | Characterize in Phase 0, remove by Phase 2, preserve history/artifacts only |
| Scheduler and inference responsibilities blur | Hidden arithmetic/inference invalidates auditability | Package dependency rules, typed inputs, static audits, grade/cost separation |
| Correlated observations inflate confidence | M4 conclusions become miscalibrated and unsafe | Provenance support sets, idempotence/path tests before calibration runs |
| Logs become too large or incomplete | UI cannot answer causal questions reliably | V0 first, structural proof hashes, streaming validation, volume metrics |
| Long stochastic runs are flaky or irreproducible | M7 deltas become uninterpretable | immutable manifests, paired seeds, retries classified separately, resumable harness |
| LLM latency exceeds 30 seconds with the configured local model | M6 loop cannot meet the turn budget | per-stage telemetry, bounded proposals, persistent reasoner, timeout policy, model/config recorded |

---

## 9. Milestone Evidence Matrix

Each row must eventually link to retained evidence rather than merely be checked in prose.

| Milestone | Implemented in | Primary evidence |
|---|---|---|
| M0 | Phase 2 | compiler manifests, edge audit, sampled diffs, determinism hashes, rule scan |
| M1 | Phase 3 | native parity matrix, frontier property results, latency report, proof events |
| M2 | Phase 4 | 100-turn state comparator, stale-action test, arithmetic audit |
| M3 | Phase 6 | ETA trials, 10k ledger property run, optimality comparison, 200-turn legality |
| M4 | Phase 8 | calibration report, provenance replay/path tests, abduction audit, decay scenario |
| M5 | Phase 9 | invalidation scenario, locality hashes, zombie-plan audit, repair latency |
| M6 | Phase 10 | seeded confabulation report, goal validity, graded A/B, loop latency |
| M7 | Phase 11 | five-condition manifests, paired statistics, induction track, negative-result report |
| V0 | Phase 1 | schemas, validators, synthetic good/bad logs |
| V1 | Phase 5 | replay fold, scrub/deep-link and timeline UX/performance evidence |
| V2 | Phase 5 | proof/atom property, performance, and usability evidence |
| V3 | Phase 7 | plan/map screenshot and invalidation fixture evidence |
| V4 | Phases 10-11 | quarantine and metrics cross-check evidence |
| V5 | Phase 12 | 200-turn live/replay equivalence report |

---

## 10. Recommended First Execution Slice

The first implementation slice should stop before uncertain reasoning or a production planner. Its purpose is to retire the highest architectural risks quickly.

Execute in this order:

1. Phase 0 baseline manifest, integration contract, and D1-D5 decisions.
2. Phase 1 event envelope, validator, and one crisp synthetic causal trace.
3. Phase 2 parser/IR for techs only, then complete units/buildings and both rulesets.
4. Phase 3 native engine adapter and tech parity before optimizing proof rendering.
5. Phase 4 one authoritative snapshot and stale-action rejection, then the 100-turn comparator.
6. Phase 5 minimal replay shell against synthetic and real crisp logs.

At the end of this slice, the repository must demonstrate:

- compiled rather than handwritten game rules;
- exact engine parity for crisp tech dependencies;
- current-turn authoritative state replacement;
- a versioned causal trace from observation through proof and action result;
- a replay UI that displays that trace without recomputation.

That is the minimum credible foundation for M3-M7. If exact engine parity cannot be achieved, later uncertain reasoning, LLM grading, and evaluation work should remain blocked rather than being built on an unverified oracle.
