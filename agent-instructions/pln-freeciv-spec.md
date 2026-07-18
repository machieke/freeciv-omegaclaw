# PLN-FreeCiv Agent: Goals, Requirements, Acceptance Criteria

Functional specification for a hybrid LLM + PLN + scheduler agent for FreeCiv.
Architecture: **LLM = goal proposer**, **PLN = dependency oracle, belief store, assumption monitor**, **scheduler = planner**, **engine = ground truth**.

Milestones are strictly ordered. The invariant discipline mirrors CID-parity: **the crisp layer must agree with the engine exactly before any uncertain atom is admitted.**

---

## M0 — Ruleset → Atomese Compiler (Crisp Layer)

### Goal
Mechanically compile FreeCiv ruleset files (techs, buildings, units, requirement vectors) into a crisp Atomese/MeTTa rulebase. No hand-authored rules.

### Requirements

- **R0.1** Parse ruleset files (`techs.ruleset`, `buildings.ruleset`, `units.ruleset`, plus `requirements` vectors) for at least the `civ2civ3` default ruleset.
- **R0.2** Emit one `Implication` per action/tech/building with a conjunctive antecedent. Requirement `present=false` → `Not` inside the `And`. Requirement `range` (local/city/player/world) → variable scope.
- **R0.3** Distinct predicates for distinct game notions: `has-tech`, `researchable`, `buildable`, `has-building`, `usable-action`. No collapsing.
- **R0.4** All compiled rules carry truth value ⟨1.0, 0.99⟩.
- **R0.5** Quantitative requirements (shield cost, gold cost, city size) compile to **grounded predicate calls**, not derived atoms. The compiler emits the predicate signature; evaluation is deferred to M2.
- **R0.6** Compiler is deterministic: same ruleset input → byte-identical rulebase output (canonical atom ordering).
- **R0.7** Compiler handles at least two rulesets (`civ2civ3`, `classic`) without code changes.

### Acceptance Criteria

- **A0.1** Rule/edge parity: emit one implication per target as required by R0.2, and verify that the complete prerequisite edge set inside those antecedents equals the `req1`/`req2` edge set in the ruleset file. Report target-rule count and prerequisite-edge count separately, using an independent extraction script (ADR 0001).
- **A0.2** Round-trip audit: for 20 randomly sampled techs and 20 units, a human-readable dump of the compiled antecedent matches the ruleset file requirements exactly (automated diff against a reference extraction, not manual inspection).
- **A0.3** Determinism: two compiler runs on the same input produce identical hashes.
- **A0.4** Zero hand-written game rules anywhere in the repo (enforced by convention: rulebase directory is build-artifact only, gitignored).

---

## M1 — Dependency Oracle (Backward Chaining, Crisp)

### Goal
Backward chainer over the canonical M0 rulebase answering: given goal G (tech/unit/building) and current player state, return the AND/OR dependency tree with unsatisfied leaves. The typed canonical IR and generated Atomese are outputs of one compiler; the persistent crisp query service executes the IR and must prove IR/Atomese manifest parity (ADR 0002). PLN truth-value machinery remains authoritative for the uncertain layer introduced at M4.

### Requirements

- **R1.1** Query interface: `deps(goal, player-state) → proof-tree | UNREACHABLE`.
- **R1.2** Proof tree preserves AND/OR structure; unsatisfied leaves are explicitly flagged and typed (missing-tech, missing-building, unsatisfied-grounded-predicate).
- **R1.3** Multiple proof paths (OR branches, e.g., buy vs. build) are all returned, not just the first.
- **R1.4** Chaining terminates on cyclic or unreachable goals with explicit `UNREACHABLE` + the blocking frontier.
- **R1.5** Latency budget: full-depth tech query (longest chain in `civ2civ3`, ~40+ nodes) completes in < 500 ms on the dev machine.
- **R1.6** Crisp deduction sanity: with all-crisp premises, derived truth values are exactly ⟨1.0, 0.99-floor⟩ — the deduction formula's term-probability terms must contribute zero drift. Any strength ≠ 1.0 on a crisp-only derivation is a bug.

### Acceptance Criteria (CID-parity gate)

- **A1.1** **Engine parity:** for every tech in the ruleset, from 50 randomized player tech-states, the oracle's prerequisite set equals FreeCiv's own tech-goal computation (`research_goal_*` path) exactly. Zero mismatches. This is the hard gate for M2+.
- **A1.2** Unsatisfied-leaf correctness: for 100 randomized (goal, state) pairs, satisfying exactly the reported leaves in the engine makes the goal achievable next step; omitting any one reported leaf leaves it blocked. Verified by driving the actual engine.
- **A1.3** `UNREACHABLE` returned for goals disabled in the loaded ruleset, never a partial tree presented as complete.
- **A1.4** Latency measured and logged in CI; regression > 2x fails the build.

---

## M2 — State Bridge & Grounded Predicates

### Goal
Live, authoritative game state mirrored into the atomspace; quantitative predicates evaluated by grounded procedures against that state. PLN never does arithmetic.

### Requirements

- **R2.1** Per-turn ingestion from the FreeCiv connection (freeciv-web / CivRealm interface): own techs, cities, units, production, gold, beakers, visible map.
- **R2.2** Grounded predicates for all quantitative checks emitted by M0 (`shields-available`, `gold-available`, `city-size-at-least`, ...), evaluated against the state store at query time.
- **R2.3** Own-state atoms are crisp ⟨1.0, 0.99⟩ and **overwritten**, not revised, each turn (they are observations of authoritative state, not evidence).
- **R2.4** The LLM has no direct authoritative state; every state fact it consumes is a query result from this layer.
- **R2.5** Grounded evaluation includes turn-rate accessors (`beakers-per-turn`, `shields-per-turn city`) exposed as plain numbers for M3, not as atoms.

### Acceptance Criteria

- **A2.1** State fidelity: over a 100-turn scripted game, every atomspace own-state fact matches the engine state at end of each turn (automated comparator; zero tolerance).
- **A2.2** No stale-state actions: the agent harness rejects any action whose preconditions fail grounded evaluation; over 100 turns of random legal play, zero engine-rejected actions due to state mismatch.
- **A2.3** No arithmetic-by-inference: static check that no compiled or runtime rule derives numeric accumulation (audit: atomspace contains no derived atoms of quantitative predicates, only grounded evaluations).

---

## M3 — Scheduler Pass (Plans from Proof Trees)

### Goal
Convert M1 proof trees into ordered, durationed, resource-consistent plans. This layer owns ordering, duration, consumption, and cost — the three things the proof tree lacks.

### Requirements

- **R3.1** Input: AND/OR proof tree + grounded rates (R2.5). Output: totally-ordered plan with per-step ETA (turn numbers) and resource ledger.
- **R3.2** Resource consumption is linear-logic-style in the *scheduler*: a stockpile satisfies each demand at most once; double-spend across AND branches is impossible by construction.
- **R3.3** OR-branch selection by explicit cost function (turns-to-goal default; gold-weighted variant available). Confidence is **not** cost — feasibility grades and cost are separate fields on each candidate plan.
- **R3.4** Tech-only plans: greedy topological sort with beaker durations. Production-interleaved plans: bounded-horizon solver (HTN or small ILP), horizon ≤ 30 turns.
- **R3.5** Plans are inspectable artifacts: serialized with their proof tree, assumptions, and ledger (needed by M5).

### Acceptance Criteria

- **A3.1** ETA accuracy: for 30 tech goals executed in live games with no interference, predicted completion turn within ±1 turn of actual for ≥ 95% of goals.
- **A3.2** Double-spend impossible: property-based test generating AND-trees with shared resource demands; ledger never allocates the same stockpile twice (10k random trees, zero violations).
- **A3.3** Tech scheduling near-optimality: on the full `civ2civ3` tech DAG, greedy schedule ≤ 5% worse (total turns) than exhaustive/ILP optimum for 20 sampled goals.
- **A3.4** Every executed plan step corresponds to an engine-legal action at execution time (zero rejections over a 200-turn game).

---

## M4 — Uncertain Layer (Fog of War & Opponent Model)

### Goal
Admit non-crisp atoms: enemy state under partial observability, inferred via the same crisp rulebase. First point at which PLN's uncertainty machinery does real work.

### Requirements

- **R4.1** Observation atoms with strength/confidence: `(at enemy-unit tile)` ⟨s, c⟩, confidence decaying with observation age (explicit decay schedule, tunable).
- **R4.2** Abductive tech inference: sighting a unit type raises `(has-tech enemy X)` for X in that unit's prerequisite closure, at bounded confidence.
- **R4.3** Deduction over crisp rules + uncertain ground atoms yields derived threat atoms (`(buildable Musketeers enemy-city)` ⟨s', c'⟩).
- **R4.4** **Anti-double-counting:** a single observation event carries a provenance ID; revision merges same-provenance evidence idempotently. Re-deriving the same conclusion via multiple inference paths from one observation must not inflate confidence.
- **R4.5** Chained-inference dampening: derived confidence is penalized per inference step (tunable λ) to compensate for the deduction formula's independence assumption over correlated map facts. λ is a declared, logged parameter — not buried.
- **R4.6** Induction over repeated games: behavioral implications (`massing-on-border → attack-within-10`) accumulate evidence counts across games, persisted between sessions.

### Acceptance Criteria

- **A4.1** Calibration: bucket derived enemy-state predictions by strength (0.1 bins); over ≥ 50 games against fixed AI opponents, empirical frequency in each bucket within ±0.15 of bucket strength. This is the headline metric for the layer.
- **A4.2** Idempotent revision: replaying the same observation stream twice produces identical truth values to playing it once (automated test; zero drift).
- **A4.3** Path-independence: constructed scenario where one observation supports a conclusion via 3 inference paths — final confidence equals the single-path value (within revision-formula tolerance), not the naively compounded one.
- **A4.4** Abduction soundness: inferred `has-tech` atoms, checked against engine omniscient state post-game, are true in ≥ 80% of cases where confidence > 0.5, and the layer never asserts crisp certainty about unobserved enemy state.
- **A4.5** Decay behaves: a unit observed once and never again drops below actionable confidence threshold within the configured window; agent provably re-scouts rather than acting on the stale atom (scenario test).

---

## M5 — Truth Maintenance & Replan Triggers

### Goal
Plans carry their assumptions; belief revision invalidates plans *with a reason* and triggers local re-chaining from the broken node.

### Requirements

- **R5.1** Each plan (M3 artifact) enumerates its uncertain assumption atoms with the confidence threshold under which it was accepted.
- **R5.2** A monitor watches assumption atoms; when revision drops one below its threshold, the plan is marked INVALID with the specific broken assumption attached.
- **R5.3** Repair is local: re-chain from the node whose subtree depended on the broken assumption; untouched subtrees are reused verbatim.
- **R5.4** Invalidation reasons are surfaced to the LLM layer in structured form (broken atom, old/new TV, affected plan steps).

### Acceptance Criteria

- **A5.1** Scripted scenario (enemy seizes assumed-clear chokepoint): plan invalidated within 1 turn of the disconfirming observation, with the chokepoint atom named as cause.
- **A5.2** Locality: in a plan with N independent subtrees where 1 assumption breaks, re-chaining touches only the affected subtree (instrumented; other subtrees' atoms not re-derived).
- **A5.3** No zombie plans: over 50 adversarial games, zero executed actions belonging to a plan already marked INVALID.
- **A5.4** Repair latency < 2 s for plans up to 50 steps.

---

## M6 — LLM Integration (Proposer / Grader Loop)

### Goal
LLM proposes strategic goals and hypotheses in natural language; PLN validates reachability and grades feasibility; verified content only enters the belief store. Failed claims are quarantined.

### Requirements

- **R6.1** Proposer interface: LLM receives structured state summary (query results, not raw engine state) + current plan status, emits candidate goals.
- **R6.2** Translation layer NL → goal query (constrained: goals must name atoms/predicates that exist in the compiled rulebase; free-text goals are rejected, not guessed).
- **R6.3** Every LLM factual claim about game state is checked against the atomspace before use; unverifiable claims go to a quarantine store with provenance, never to the main belief store (believe / disbelieve / quarantine sink).
- **R6.4** PLN feasibility grade + M3 cost returned to the LLM per candidate goal; LLM selects among *graded* options.
- **R6.5** Per-turn latency budget for the full loop (state ingest → propose → verify → schedule → act): ≤ 30 s.

### Acceptance Criteria

- **A6.1** **Confabulation write-through rate = 0:** seeded test set of 100 LLM outputs containing 40 known-false state claims; zero false claims reach the main belief store, all 40 land in quarantine with provenance.
- **A6.2** Goal validity: ≥ 95% of LLM-proposed goals pass translation (name real atoms); rejects produce a corrective re-prompt, not a crash.
- **A6.3** Grading changes behavior: A/B over 30 games — LLM choosing among PLN-graded goals vs. ungraded self-selection; graded condition must show measurable win-rate or score improvement (see M7 for harness).
- **A6.4** Loop latency within budget for ≥ 95% of turns in a 200-turn game.

---

## M7 — Evaluation Harness & Ablations

### Goal
Attribute performance to layers. Prediction to test: the state oracle gives most of the delta; induction shows value only across repeated games vs. consistent opponents.

### Requirements

- **R7.1** Baselines: (a) stock BaseLang/Mastaba-class LLM agent, (b) + atomspace state oracle only (M2, no inference), (c) + dependency oracle & scheduler (M1/M3), (d) + uncertain layer (M4/M5), (e) full loop (M6).
- **R7.2** Fixed opponent pool (built-in AI at fixed difficulty), fixed map seeds, ≥ 30 games per condition.
- **R7.3** Metrics: win rate, score at turn N, engine-rejected-action rate, confabulation-write-through rate, calibration (A4.1), plan-ETA error, replan latency.
- **R7.4** Repeated-opponent track for induction: ≥ 20 consecutive games vs. the same AI personality, opponent-model prediction accuracy tracked over the sequence.

### Acceptance Criteria

- **A7.1** All five conditions run to completion on the same seeds; results reproducible from a single harness command.
- **A7.2** Per-layer attribution report: each layer's marginal effect on each metric with confidence intervals (30 games/condition minimum).
- **A7.3** The stated prediction is *tested*, not assumed: harness output explicitly compares oracle-only delta vs. induction delta. Either outcome is a result.
- **A7.4** Negative results are reported at the same fidelity as positive ones.

---

## Cross-Cutting Invariants (all milestones)

| # | Invariant | Enforcement |
|---|-----------|-------------|
| I1 | Crisp layer agrees with engine exactly (A1.1 gate) before uncertain atoms admitted | CI gate between M1 and M4 |
| I2 | PLN never does arithmetic; scheduler never does inference | Static audits A2.3, code review checklist |
| I3 | One observation, one unit of evidence (provenance-idempotent revision) | A4.2, A4.3 property tests |
| I4 | LLM output is hypothesis until verified; quarantine on failure | A6.1, zero-tolerance |
| I5 | Every confidence-affecting parameter (decay schedule, dampening λ, thresholds) is declared, logged, and swept in M7 | Config schema + harness |
| I6 | Ground truth is the engine, always; any oracle/engine disagreement is a bug in the oracle | Comparators in M1, M2, M4 post-game audits |

---

## Explicitly Out of Scope (v1)

- Diplomacy/negotiation modeling (uncertain intent over dialogue) — after M7.
- Combat micro-tactics — delegated to grounded odds computation + LLM heuristics, not PLN.
- Multi-agent PLN (shared atomspace across allied agents).
- Learning the dampening λ / decay schedules online — v1 sweeps them offline in M7.
