# Larger AtomSpace, deeper inference, and scaled bridge/fluid experiment plan

**Status:** In progress; G0-G7 decided from frozen held-out evidence, G8 preregistered but not entered, G9 open
**Target branch:** `experimental/larger-atomspace-inference-depth`
**Claim type:** scalability, boundedness, correctness, and performance only
**Policy authority:** disabled throughout this plan

## Implementation checkpoint — 2026-08-16

The benchmark-only contracts, frozen baseline manifest, isolated subprocess
runner, exact-work generators, robust analysis, audit reconstruction,
held-out-only claim manifest, combined stress design, full-telemetry captured
loader/amplifier, and engine-shadow import gate are implemented under
`benchmarks/freeciv/scaling/`. Production authority and controller defaults
remain unchanged.

Initial discovery has reached every largest non-stretch isolated primary tier:
A4 (100,000 atoms), P3 (depth 96 / 100,000 proof records plus 100,000 indexed
distractors), B3 (10,000 nodes / 40,000 edges / 16 goals), and F3 (10 million
edge updates). These are single-seed discovery results, not held-out scaling or
p95 claims. Their current outcome is documented in
`docs/freeciv/evidence/scalability-v1-initial-discovery.md`.

The 100-cycle A0 retained-revision/scope/RSS check passes, all required bridge
topology and scalar/protected/probe/persistence/source-sink mechanisms have
executable discovery coverage, dynamic edge failure and stale topology fail
closed, and one same-source realistic CA2 transfer point is inside the 2x
envelope. The campaign-specific implementation slice has 85 passing tests.

The dedicated observability Scale Lab is implemented and browser-verified. It
separates discovery and held-out phases; exposes G2-G9, absolute labels,
combined-load interactions, captured transfer, engine parity, claim status,
frozen-cell accounting, and provenance; and keeps each plotted surface within
its selected source identity.

A clean-shell worker-launch defect was fixed and regression-tested. Under the
resulting single source identity, A2/CA2 and A4/CA4 turn-250 pairs both preserve
the original subgraph and fall inside the 2x synthetic-transfer envelope:
1.210x/0.483x timing/RSS at A2 and 1.290x/0.443x at A4.

The primary matrix is now dry-runnable and hash-addressed. One discovery seed
expands to 297 bounded cells; ten seeds expand to 2,961 cells. It covers seven
FDAS dependency shapes, twelve proof families, five controller arms across
seven bridge topologies, and corridor/sparse-DAG fluid degree/failure stress.
Only canonical rows enter primary fits or latency labels. Held-out selection
uses 40 semantic seeds plus 50 canonical timing samples in three deterministic
randomized blocks. Exact trial identities resume without rerunning.

The first complete low-tier primary checkpoint ran all 57 A0/P0/B0/F0 cells.
All workers completed. It exposed one path-persistence dynamic-failure case
that overwrote scalar fallback; all non-scalar arms now retain the declared
topology-edge-failure fallback. The original negative discovery row remains in
the audit as a semantic failure, while audit integrity remains valid.

The ten-seed primary semantic-screening matrix is complete: all 2,961 planned
rows are accounted for, with 2,643 completed and 318 stopped under the fixed
resource rules. All rows validate against the strict trial schema, integrity
reconstruction passes, and every completed row satisfies its required
semantic invariants. A4 local/1%-churn/support-multiplicity-4 repeated the
120-second wall stop and bounded the remaining A4 tier; B4 exposed a wider
protected-message/path-persistence resource boundary and bounded its
remaining descriptive tier. Combined C07 and C11 each had one isolated wall
stop, while C13 and C15 each had three direct stops plus three rows explicitly
not entered after the repeated-stop rule. P0-P3, B0-B3, and F0-F3 completed
their full ten-seed semantic matrices. Parallel screening telemetry is
excluded from timing fits, absolute labels, and G6 interaction ratios.

The captured transfer screen is also complete at the semantic boundary. Twenty
turns spanning 1 through 500 were each amplified to CA2 and CA4, producing 40
successful rows. Every row preserves the original subgraph, verifies the
source ledger hash, and quarantines all clones. Because the three-worker run
uses semantic-screening telemetry, its timing/RSS values are excluded and the
G7 transfer-ratio gate correctly remains not entered.

The campaign is not complete. A clean source freeze, the
40-semantic-seed/50-timing-sample held-out cohorts, the claim-eligible G7
captured timing cohort, a new 20-pair high-entity engine shadow cohort, and
final G9 claim decisions remain open. No held-out claim is currently
authorized.

## Held-out checkpoint — 2026-08-20

The frozen one-worker held-out cohort is complete and all 12,061 planned rows
are accounted for: 11,179 completed and 882 stopped. Together with discovery,
the audit reconstructs 16,119 results, retains two historical failures and
1,259 stopped trials, reports one discovery semantic failure, and has no
identity or reconstruction error.

G2 is **fail/bounded** as a whole because 92 A4 stress rows reached the frozen
resource stop and both absolute latency labels fail. Its canonical hypotheses
do pass: incremental-time exponent 1.115 (95% clustered-bootstrap CI
1.103–1.126, limit 1.35) and peak-RSS exponent 0.855 (CI 0.855–0.856, limit
1.15), with no completed-row semantic error.

G3 **passes**. All 2,320 held-out proof trials completed correctly. Relevant
work exponent is 1.054 (CI 1.041–1.064, limit 1.50); indexed-distractor cost
also passes its 1.10 bound. P2 passes its 2-second label at 1.627 seconds p95;
P3 narrowly misses its 15-second label at 15.984 seconds p95.

G4 is **fail/bounded** as a whole because B4 resource boundaries account for
789 stops and B3 misses its 2-second label (9.114 seconds p95). H3 itself
passes through B3: exponent 1.405 (CI 1.396–1.416, limit 1.50), completed
semantics are exact, and B1 passes the 500 ms live-capable label at 430 ms
p95.

G5 **passes** its numerical and scaling gate through F3. All 1,320 held-out
rows complete with exact semantics and exponent 1.064 (CI 1.058–1.073, limit
1.25). F3 is nevertheless not research-usable under the absolute 5-second
label: measured p95 is 45.714 seconds.

G6 is **fail/incomplete**, not an interaction failure. All 679 completed rows
preserve semantic invariants and all 639 eligible isolated-stage pairs pass
the 2x interaction bound (maximum 1.532, p95 1.043). One C07 row stopped at
the wall limit. The 40 repeated C16 center rows have no preregistered isolated
`proof:center` comparator and therefore cannot enter H5; this frozen design
omission is retained rather than retrofitted.

G7 **passes**. All 40 claim-eligible captured snapshot/tier pairs preserve the
source ledger, original subgraph, and clone quarantine. Maximum synthetic
transfer ratios are 1.953 for timing and 1.066 for RSS, inside the 2x bound.

G8 is now preregistered in
`docs/freeciv/evidence/scalability-v1-engine-shadow-preregistration.md`: a new
20-seed, 40-arm, 30-turn high-entity paired control/shadow cohort with bridge
and source-sink flow advisory execution, one full-detail sample, per-process
RSS, strict natural-volume expansion, and exact action/result parity. No G8
engine arm had been entered at this checkpoint, so G9 remains incomplete.

## 1. Executive decision

Run a preregistered, staged scalability campaign with three independently
controlled axes:

1. concurrently materialized Functional Dependent AtomSpace (FDAS) size and
   update churn;
2. inference depth, breadth, sharing, cycles, and irrelevant distractors; and
3. bridge/source-sink-flow graph size, density, path length, goal count,
   candidate count, and transport work.

The experiment must not infer scalability from a longer game alone. The
existing 500-, 1,000-, and 2,000-turn traces show temporal boundedness, but all
three reached the same 2,325-atom peak. This plan deliberately increases the
concurrent working set and the amount of relevant reasoning.

The campaign has two distinct performance labels:

- **scales predictably:** correctness holds and measured time/memory growth
  stays within preregistered scaling envelopes;
- **live-capable:** the same workload also satisfies an absolute controller
  latency budget.

A tier can earn the first label without earning the second. Synthetic success
does not imply a FreeCiv score or win-rate improvement.

## 2. Existing measured baseline

The following values are the baseline to reproduce, not new claims:

| Surface | Current measurement or bound |
|---|---:|
| Long live FDAS run | 2,000 turns; 2,019 committed revisions |
| Concurrent atoms | median 1,068; p95 1,246; peak 2,325 |
| Concurrent supports/scopes | peak 1,161 / 24 |
| Dependency activity | 31,556 derivations; 57,260 re-derivations; 26,065 invalidations |
| Explicit live PLN proofs | 14 results, all depth 1 and tree size 4 |
| Standalone ruleset proof maximum | depth 12; 132 proof nodes |
| Standalone proof latency | 435 misses; p95 32.53 ms; maximum 90.18 ms |
| Captured live bridge view | 354 nodes; 855 edges; 34 candidates; 2 goals |
| Captured bridge controller latency | p95 approximately 245 ms |
| Fluid transport corridor | lengths 4 through 128; about 0.13 microseconds/edge update at length 128 |

Current checked defaults are intentionally smaller than the proposed stress
tiers:

- FDAS global cap: 25,000 atoms;
- live materialization depth: 6;
- generic proof default: depth 32, 4,096 bindings, 4,096 rule fires;
- factorized flow view: 1,024 nodes, 4,096 edges, 512 candidates;
- pressure propagation: 64 hops and 32 routes per conclusion; and
- corrected probes: 128 paths and 16 steps by default.

Experiment-only configurations may raise these values. Production defaults
must remain byte-identical.

## 3. Research questions and preregistered hypotheses

### RQ1 — Concurrent AtomSpace size

Can the immutable revision store, scoped materialization, dependency index,
invalidation, and re-derivation operate correctly at 10,000, 25,000, 50,000,
and 100,000 live atoms?

**H1:** For local 1% churn, elapsed update time grows no faster than
`O(N^1.35)` and peak memory no faster than `O(N^1.15)` from 10,000 through
100,000 atoms, with exact cold/incremental equivalence.

### RQ2 — Deep and broad inference

Can the typed deterministic engine complete exact proofs substantially deeper
and larger than the current depth-12/132-node ruleset maximum?

**H2:** Completed proof time grows primarily with the reachable proof DAG,
not total unrelated AtomSpace size. The upper 95% confidence bound on the
time exponent versus visited proof nodes must be at most 1.50, while the
exponent versus indexed-but-unreachable distractor atoms must be at most 1.10.

### RQ3 — Bridge scale

Can deterministic protected bridge readout retain the same candidate union
and ordering invariants on control graphs larger than 354 nodes/855 edges?

**H3:** Message-based bridge construction and readout remain deterministic,
fail closed on budget exhaustion, preserve the protected scalar candidate,
and grow no faster than `O(E^1.50)` through 10,000 nodes/40,000 edges.

### RQ4 — Fluid scale

Does conservative two-dye transport remain numerically healthy and
predictably bounded with longer paths and more edge updates?

**H4:** Runtime grows no faster than `O(U^1.25)`, where `U` is actual edge
updates, through 10 million updates. Normalized mass error remains at or below
`1e-9`, and no unapproved positivity correction or illegal-edge transport is
accepted.

### RQ5 — Combined load

Do large materialization, deep inference, and a large control view interact in
a way that is substantially worse than their isolated costs?

**H5:** In selected combined cells, controller-inclusive latency is no more
than twice the sum predicted from the isolated stages, and semantic output is
unchanged by irrelevant AtomSpace or graph expansion.

## 4. Non-negotiable claim and safety boundary

Every experiment in this plan must satisfy all of the following:

- FDAS, bridge, probes, persistence, and flow remain shadow-only.
- The frozen scalar PF-v2 plus whole-operation packets remains the comparator
  and effective policy.
- Epistemic truth is never changed by pressure, bridge, or flow state.
- Synthetic atoms, rules, scopes, entities, and actions use a separate
  benchmark identity space and can never reach execution.
- Captured-snapshot amplification is labelled synthetic amplification, not an
  engine-observed world.
- An engine shadow cohort must reproduce the exact ordered action trace of its
  paired control.
- Budget exhaustion returns explicit `UNKNOWN`, truncation, or scalar fallback;
  it must never silently return false, unreachable, or an incomplete winner.
- No score, gameplay, or win-rate claim is in scope.
- No production cap or controller default may be raised by this experiment.

## 5. Workload architecture

### 5.1 Atom-counting contract

Do not substitute cumulative lifecycle events or configured caps for
concurrent AtomSpace size. Report three non-overlapping measurements:

- `live_revision_atoms`: unique `AtomRecord` IDs in the published dynamic
  revision; this is the primary `N` used by the A tiers and is comparable to
  the measured 2,325-atom peak;
- `static_ruleset_atoms`: unique records retained once in the digest-keyed
  ruleset store; and
- `query_visible_atoms`: the unique union visible to the tested query after
  imports, with duplicate IDs counted once.

Supports, scopes, dependency edges, proof records, and flow nodes are reported
as separate dimensions. Primary scaling fits use `live_revision_atoms`, with
a sensitivity fit against `query_visible_atoms` where static ruleset content
is present.

### 5.2 Two complementary AtomSpace workloads

Both workloads are required because simply appending disconnected atoms is an
inadequate scalability test.

#### A. Typed synthetic FDAS generator

Generate valid `AtomRecord`, `SupportRecord`, `ScopeSpec`, dependency, and
revision structures through the real transaction and store APIs. A
benchmark-only predicate registry will contain typed predicates such as
`scale-fact`, `scale-depends-on`, `scale-local-goal`, and `scale-operation`.
It must not alter the production registry.

The generator must support:

- exact target atom/support/scope counts;
- independent namespaces and authority classes;
- local chains, balanced trees, shared DAGs, high-fan-out hubs, and disconnected
  distractor shards;
- 0.1%, 1%, 5%, 20%, and 100% dependency churn;
- mean support multiplicity 1, 2, and 4;
- retained revision counts 1 and 4; and
- stable semantic hashes across process and insertion order.

#### B. Captured FreeCiv snapshot amplifier

Clone real city, unit, region, operation, and dependency motifs under new
benchmark entity IDs while retaining valid scope and predicate contracts.
Original entities must remain distinguishable. Queries and decisions over the
original subgraph must be byte-identical before and after amplification.

This workload measures realistic record shapes and indexes. It is still not
engine-authentic and must be reported separately from live engine results.

### 5.3 AtomSpace scale tiers

| Tier | Live atoms | Target scopes | Primary role |
|---|---:|---:|---|
| A0 | 2,500 | 25 | reproduce current order of magnitude |
| A1 | 10,000 | 100 | indexed working-set scale |
| A2 | 25,000 | 250 | checked-profile cap |
| A3 | 50,000 | 500 | above-current-cap research tier |
| A4 | 100,000 | 1,000 | primary large-AtomSpace claim tier |
| A5 | 250,000 | 2,500 | stretch; entered only after A4 passes resource gates |

The main `N` sweep holds mean supports at 1 and churn at 1%. Separate stress
sweeps run support multiplicity 2/4 and churn 0.1/5/20/100% at A2 and A4.
Local-fan-out and hub-fan-out are reported independently.

### 5.4 Inference graph families

An independent generator must produce expected proof outcomes using a simple
topological reference evaluator, not the implementation under test.

Required families:

1. single chains;
2. balanced AND trees;
3. OR alternatives with one, several, or no successful branches;
4. diamonds and shared DAGs at 50% and 90% subtree sharing;
5. legal cycles with an alternate proof path;
6. cycle-only unreachable targets;
7. grounded-premise blockers;
8. binding-heavy rules; and
9. reachable graphs embedded in large indexed distractor sets.

| Proof tier | Maximum required depth | Relevant proof-node envelope | Distractor envelope |
|---|---:|---:|---:|
| P0 | 12 | 132 | 0 |
| P1 | 24 | 1,000 | 10,000 |
| P2 | 48 | 10,000 | 25,000 |
| P3 | 96 | 100,000 | 100,000 |
| P4 | 128 | 250,000 | 250,000; stretch only |

Depth and proof-node count are independent axes. For example, a 96-node chain
tests depth, while a shallower shared DAG tests 100,000 relevant nodes. Every
trial records realized depth, reachable nodes, visited rules, bindings, rule
fires, memo hits, cycle rejections, proof records, and blockers.

### 5.5 Bridge graph tiers

Build `FlowView` graphs directly for kernel isolation and through
`FreeCivFactorGraphBuilder` for controller-inclusive trials.

| Tier | Nodes | Edges | Candidates | Goals |
|---|---:|---:|---:|---:|
| B0 | 354 | 855 | 34 | 2 |
| B1 | 1,000 | 4,000 | 128 | 4 |
| B2 | 5,000 | 20,000 | 512 | 8 |
| B3 | 10,000 | 40,000 | 2,048 | 16 |
| B4 | 50,000 | 200,000 | 8,192 | 32 |
| B5 | 100,000 | 400,000 | 16,384 | 64 |

Each tier includes sparse tree, shared DAG, cyclic, disconnected distractor,
asymmetric forward/backward legality, bottleneck, and dynamic-failure
topologies. Average degree 2, 4, and 8 is screened; the primary comparison
uses degree 4.

The bridge arms are frozen in increasing complexity:

1. scalar PF-v2 plus packets;
2. protected deterministic message bridge, with no advection;
3. corrected probe-informed union;
4. smoothed path persistence; and
5. source-sink flow readout.

Candidate sets, transition estimates, packet costs, and scalar scores must be
identical across arms. Bridge/probe/flow signals cannot be reused in final
scalar scoring.

### 5.6 Fluid work tiers

Fluid performance is indexed by actual edge updates, not node count alone.

| Tier | Edge-update budget | Representative topology |
|---|---:|---|
| F0 | 10,000 | short sparse graph |
| F1 | 100,000 | 1k-node graph or long corridor |
| F2 | 1,000,000 | 10k-node multi-step graph |
| F3 | 10,000,000 | primary large transport tier |
| F4 | 50,000,000 | stretch only after F3 passes |

Corridor lengths are extended to 128, 256, 512, 1,024, and 2,048. General
graphs vary average degree 2/4/8, microsteps 1/8/32/128, commodities 1/2/4/8,
and dynamic edge failures 0%/1%/10%. The scheduler must cap a trial by edge
updates before allocating it.

## 6. Experiment design

### 6.1 Screening, freeze, and held-out execution

Do not run the entire Cartesian product.

1. **Mechanism screening:** ten discovery seeds per candidate cell identify
   impossible resource combinations and implementation defects.
2. **Manifest freeze:** publish selected primary cells, thresholds, code
   digest, generator digest, environment identity, seeds, and analysis script.
3. **Held-out run:** forty new graph seeds per primary semantic cell. Timing
   claim cells run in three randomized blocks with at least fifty isolated
   process samples per tier.
4. **No tuning on held-out data:** a code or parameter change creates a new
   versioned experiment and new held-out seeds.

The predetermined primary cells are:

- A0–A4 with 1% local churn and one support per atom;
- A2/A4 crossed with churn 0.1/5/20/100%;
- P0–P3 for chain, AND, shared DAG, cyclic, and distractor families;
- B0–B3 at average degree 4 for all five arms;
- B4 for scalar, protected bridge, and path persistence; flow is included only
  if its estimated resource use remains inside the stop rules;
- F0–F3 for corridors and sparse DAGs; and
- a fractional combined design with low/high A, P, and B/F levels plus a
  repeated center cell.

A5, P4, B5, and F4 are stretch tiers and cannot rescue a failed primary tier.

### 6.2 Cold, warm, and telemetry arms

Every primary tier separates:

- cold construction in a new process;
- warm indexed query/update;
- full rebuild;
- incremental local-churn revision;
- aggregate telemetry only;
- sampled full-detail telemetry; and
- serialization disabled versus enabled.

Full AtomRecord telemetry is recorded for one representative seed per tier,
not every timing trial. This prevents the prior 716 MiB event stream from
dominating the algorithm measurement.

### 6.3 Paired execution

All controller arms receive the same canonical graph, candidate order,
transition values, packet declarations, and seed. Arm order is randomized
within block. Statistical resampling clusters by graph seed, never by repeated
timing sample.

## 7. Measurements

### 7.1 Correctness and semantics

Record:

- cold versus incremental revision hash equality;
- expected versus actual proof status, blockers, depth, and proof DAG;
- deterministic replay across insertion order and process;
- unsupported, stale, or cross-namespace atoms;
- dependency and support referential integrity;
- budget/truncation/fallback disposition;
- scalar winner protection and candidate recall;
- packet conservation and resource feasibility;
- truth hash before/after control computations;
- forward/backward legality violations;
- mass balance, minimum mass, correction count, and correction mass; and
- decision invariance under disconnected distractors and captured amplification.

### 7.2 Size and work

Record actual, not requested:

- atoms, supports, dependency edges, scopes, retained revisions;
- relevant and distractor proof nodes;
- rules visited, bindings, fires, memo hits, and cycle rejections;
- flow nodes/edges/candidates/goals/frontier stubs;
- bridge messages, probe paths/steps/effective sample size;
- solver iterations, transport microsteps, commodities, and edge updates; and
- emitted events and serialized bytes.

### 7.3 Performance and resources

Measure each stage independently and controller-inclusively:

- wall and CPU time at p50/p95/p99/maximum;
- peak resident set size in an isolated subprocess;
- bytes per atom, support, proof node, flow node, and flow edge;
- Python allocation peak as a diagnostic, separate from RSS;
- garbage-collection counts and time;
- cache hit rate and invalidation fan-out;
- build, query, proof, bridge, solver, advection, readout, explanation, and
  serialization latency; and
- timeout, OOM, signal, or explicit stop disposition.

Host CPU, core count, memory, OS, Python version, load average, commit, dirty
state, and configuration hashes are mandatory artifact fields.

## 8. Statistical analysis

### 8.1 Primary estimands

1. FDAS time and peak-RSS scaling exponents versus live atoms.
2. Proof-time exponent versus relevant visited nodes and separately versus
   unreachable distractors.
3. Bridge-time exponent versus realized edges.
4. Fluid-time exponent versus realized edge updates.
5. Paired latency ratio and semantic disagreement rate for each controller arm
   versus frozen scalar PF-v2 plus packets.

Fit `log(metric) = alpha + beta * log(work)` with a robust regression. Obtain
95% intervals by deterministic graph-seed cluster bootstrap with 10,000
resamples. Publish raw points and residuals; a fitted exponent without them is
insufficient.

### 8.2 Distributional reporting

Timing samples are never silently discarded. Infrastructure interruptions are
reported separately; scheduler or GC outliers remain in maximum and
percentile results. Publish median paired ratios, cluster-bootstrap intervals,
p50/p95/p99/max, and the count above each absolute latency threshold.

Primary hypotheses use alpha 0.05. Secondary topology and arm comparisons use
Holm correction within their family. Stretch-tier results are descriptive and
cannot change a failed primary decision.

### 8.3 Absolute capability labels

The relative scaling gate and absolute labels are separate:

| Label | Required p95, aggregate telemetry |
|---|---:|
| FDAS interactive at A2, 1% local churn | <= 500 ms per revision |
| FDAS research-usable at A4 | <= 2 s per revision |
| Protected bridge live-capable at B1 | <= 500 ms controller-inclusive |
| Protected bridge research-usable at B3 | <= 2 s controller-inclusive |
| Fluid research-usable at F3 | <= 5 s per transport run |
| Deep proof research-usable at 10k relevant nodes | <= 2 s per proof |
| Deep proof stress-usable at 100k relevant nodes | <= 15 s per proof |

Failing an absolute label does not erase a valid scaling measurement.

## 9. Phased implementation and acceptance gates

## Phase 0 — Baseline freeze and preregistration

### Goal

Make current semantic and performance identities reproducible before adding
generators or experimental budgets.

### Requirements

- Parse and freeze the existing full-AtomRecord and G3/G4 evidence.
- Add one machine-readable baseline manifest.
- Re-run the existing proof, G3 bridge, and G4 fluid microbenchmarks.
- Hash production configs and controller defaults.

### Acceptance criteria — G0

- Existing semantic hashes reproduce exactly.
- Baseline counts reproduce exactly.
- Timing is reported with host identity; a host-dependent timing difference is
  visible but is not treated as semantic failure.
- Production defaults before and after the phase are identical.

## Phase 1 — Workload generators and independent oracles

### Goal

Create deterministic scale inputs without weakening production validation.

### Requirements

- Implement typed FDAS, captured amplifier, proof-DAG, bridge, and fluid
  generators.
- Add independent expected-result evaluators.
- Support exact count targets and deliberate cap exhaustion.
- Add generator schema, identity, and replay tests.

### Acceptance criteria — G1

- Generated counts equal requested counts for 100 randomized small cases.
- Reference and implementation outcomes agree for every small case.
- Insertion-order permutations retain identical semantic hashes.
- Synthetic identities cannot bind to live legal actions or authority.
- Deliberate malformed/cyclic/budget cases fail in their declared way.

## Phase 2 — AtomSpace size and churn

### Goal

Measure concurrent size, dependency shape, churn, retention, and memory through
A4.

### Acceptance criteria — G2

- A0–A4 complete without corruption or unplanned truncation.
- Cold and incremental revisions are semantically identical in 100% of trials.
- No retained-revision or scope leak remains after 100 update/expiry cycles;
  post-GC RSS drift must be below 5% after the warm plateau.
- H1 time and memory exponent gates pass for local churn.
- Hub-fan-out results are reported separately and cannot be averaged into the
  local-churn result.
- A2/A4 absolute labels are reported pass or fail without changing thresholds.

## Phase 3 — Deep and broad inference

### Goal

Measure exact proof behavior through depth 96 and 100,000 relevant nodes.

### Acceptance criteria — G3

- P0–P3 expected statuses and proof structures agree in every held-out case.
- Depth, binding, and rule-fire exhaustion return explicit `UNKNOWN` and the
  correct blocker.
- Cycle-only and alternate-path cycle cases terminate deterministically.
- Proof output is invariant to unreachable distractors.
- H2 relevant-node and distractor exponent gates pass.
- The 10k and 100k absolute proof labels are reported.

## Phase 4 — Bridge scale

### Goal

Scale protected candidate readout before introducing fluid transport.

### Acceptance criteria — G4

- B0–B3 complete for scalar, deterministic bridge, corrected probes, and path
  persistence; all primary arms use identical inputs.
- Protected scalar winner recall is 100%.
- Deterministic bridge union and ordering are replay-identical.
- Irrelevant graph expansion changes neither the protected union nor final
  scalar ordering.
- Budget exhaustion produces an explicit scalar fallback.
- H3 passes through B3; B1/B3 absolute labels are reported.
- Probe cost and effective sample size are published separately; probe failure
  cannot invalidate a healthy deterministic bridge result.

## Phase 5 — Source-sink and two-dye fluid scale

### Goal

Measure numerical invariants and edge-update scaling through F3.

### Acceptance criteria — G5

- F0–F3 finish without undeclared transport on illegal edges.
- Normalized mass error is <= `1e-9` in every accepted run.
- Negative mass beyond tolerance, excessive correction, or solver imbalance
  fails closed and is never repaired silently.
- Dynamic-failure and stale-topology cases choose the declared repair or scalar
  fallback deterministically.
- H4 exponent gate and the F3 absolute label are reported.

## Phase 6 — Combined factorial stress

### Goal

Detect interactions hidden by isolated microbenchmarks.

### Requirements

Use a frozen fractional factorial with:

- A2/A4 live atoms;
- P1/P2 relevant proof size;
- B1/B3 control graph size;
- no flow versus F2 flow; and
- a repeated center cell.

### Acceptance criteria — G6

- All semantic, truth, packet, legality, and fallback invariants hold.
- H5 interaction bound passes or the exact interaction is localized.
- Peak RSS stays below the trial resource limit.
- Results are not pooled with isolated-stage fits.

## Phase 7 — Captured FreeCiv transfer

### Goal

Test whether synthetic scaling estimates transfer to realistic record and
candidate shapes.

### Acceptance criteria — G7

- At least 20 captured snapshots spanning early, middle, and late game are
  amplified to A2 and A4.
- Original-subgraph queries, proof outcomes, candidates, protected union, and
  scalar selection remain exact under amplification.
- Measured latency and RSS fall inside 2x of the synthetic model prediction or
  the transfer gap is explained by a measured component.
- No amplified result is labelled engine-observed.

## Phase 8 — Engine-backed shadow confirmation

### Goal

Confirm real integration and overhead without granting policy authority.

### Requirements

- Build fixed high-entity scenarios or savegames with more cities, units,
  regions, concurrent goals, and grounded candidates than current runs.
- Run paired control/shadow arms on at least 20 fixed seeds per scenario tier.
- Use aggregate telemetry for timing and one full-detail sample per tier.

### Acceptance criteria — G8

- Every arm completes with a valid event ledger and clean frozen source.
- Ordered actions and action-result statuses are exact between each pair.
- No authority-eligible FDAS/bridge/fluid decision is emitted.
- No stale binding, unsupported atom, illegal candidate, detail omission in the
  sampled trace, or unexplained fallback occurs.
- Natural achieved atom/proof/control-graph scale is reported; configured caps
  are not reported as achieved scale.
- Controller p95, RSS, and synthetic-to-engine transfer ratio are published.

## Phase 9 — Audit, documentation, and claim decision

### Acceptance criteria — G9

- One audit reconstructs every primary estimate from raw artifacts.
- All planned cells are classified completed, failed, stopped, or not entered.
- Discovery, held-out, and stretch results are clearly separated.
- A machine-readable claim manifest lists exactly which tiers earned
  `correct-at-scale`, `scales-predictably`, `research-usable`, or
  `live-capable`.
- Negative and null results remain in the final report.

## 10. Resource and stop rules

Each scale trial runs in an isolated subprocess with hard limits:

- 16 GiB peak RSS;
- 120 seconds wall time per primary trial;
- 50 million edge updates per fluid trial;
- 250,000 live atoms before explicit stretch approval;
- 250,000 relevant proof nodes before explicit stretch approval; and
- 25 GiB total artifact budget for the campaign.

Stop a tier immediately after any of the following:

- two OOM or wall-limit terminations in the same cell;
- semantic mismatch, truth mutation, illegal-edge transport, or decision-safety
  violation;
- nondeterministic hash under exact replay;
- unbounded retained-revision, scope, or support growth; or
- inability to reconstruct actual work counts.

A stopped tier is a valid boundedness result. Lower tiers continue if they are
not affected by the same defect. Do not increase a resource limit merely to
turn a failed primary gate into a pass.

## 11. Implementation layout

Add a self-contained benchmark package:

```text
benchmarks/freeciv/scaling/
  model.py                 # trial/cell/result contracts
  atomspace_generator.py
  captured_amplifier.py
  proof_generator.py
  proof_reference.py
  bridge_generator.py
  fluid_generator.py
  runner.py                # isolated subprocess orchestration
  analysis.py              # fits, intervals, gates
  audit.py

scripts/freeciv/run_scalability_campaign.py
scripts/freeciv/audit_scalability_campaign.py

profile/dependent_atomspace_scaling_shadow.yaml
profile/freeciv_scalability_experiment.yaml

schemas/freeciv-scaling/
  manifest.schema.json
  trial.schema.json
  report.schema.json

Autotests/test_freeciv_scaling_*.py
docs/freeciv/evidence/scalability-*.md
```

Production constructors should gain dependency injection only where required:

- experiment-supplied `FlowBuildBudget` instead of changing its default;
- experiment-supplied `InferenceRequest` budgets;
- benchmark-only predicate registry and ruleset IR; and
- stage timers/work counters that are inert unless enabled.

No benchmark module may be imported by the normal game execution path.

## 12. Artifact contract

Use this hierarchy:

```text
artifacts/freeciv/scalability-v1/
  preregistration.json
  environment.json
  baseline/
  discovery/
  heldout/
    atomspace/
    proof/
    bridge/
    fluid/
    combined/
    captured/
    engine/
  raw-trials.jsonl
  aggregate.json
  audit.json
  report.md
  claim-manifest.json
```

Every trial identity hashes the source commit, dirty state, generator version,
seed, requested/actual scale, topology, budgets, arm, telemetry mode, and host
measurement contract. Resume is allowed only for an exact identity match.

## 13. Planned command surface

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_scalability_campaign.py \
  baseline --out artifacts/freeciv/scalability-v1

PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_scalability_campaign.py \
  plan --out artifacts/freeciv/scalability-v1 --surface all \
  --design primary --seeds 10

PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_scalability_campaign.py \
  discovery --out artifacts/freeciv/scalability-v1 --surface all \
  --design primary --seeds 10 --workers 3

PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_scalability_campaign.py \
  freeze --out artifacts/freeciv/scalability-v1 --surface all \
  --design primary --seeds 40 --timing-samples 50 \
  --captured-events artifacts/freeciv/fdas-full-atomrecord-500-seed104743-v2/games/main/e_full_loop/104743-00/events.jsonl \
  --captured-sha256 fbf665b6468c7af79915b684435acd52b77356a284f462d3788e562e2b4d8e4a \
  --turns 1,25,50,75,100,125,150,175,200,225,250,275,300,325,350,375,400,425,450,500

PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_scalability_campaign.py \
  heldout --out artifacts/freeciv/scalability-v1 --surface all \
  --design primary --seeds 40 --timing-samples 50 --workers 1 \
  --captured-events artifacts/freeciv/fdas-full-atomrecord-500-seed104743-v2/games/main/e_full_loop/104743-00/events.jsonl \
  --captured-sha256 fbf665b6468c7af79915b684435acd52b77356a284f462d3788e562e2b4d8e4a \
  --turns 1,25,50,75,100,125,150,175,200,225,250,275,300,325,350,375,400,425,450,500

PYTHONPATH=src:benchmarks python3 scripts/freeciv/audit_scalability_campaign.py \
  --root artifacts/freeciv/scalability-v1 \
  --output docs/freeciv/evidence/scalability-v1.json
```

Parallel workers may be used for semantic screening. Claim-eligible timing runs
use one benchmark process at a time unless a separate concurrency experiment
is preregistered.

## 14. Expected conclusions

The final report must choose one of these bounded conclusions per surface:

1. correct and predictably scaling through the highest passed tier;
2. correct but not within the absolute latency label;
3. bounded only through a lower tier, with the first failed tier identified;
4. semantically incorrect or nondeterministic at scale; or
5. inconclusive because the measurement contract failed.

The strongest possible conclusion from this plan is:

> On the frozen Python FDAS/control implementation and recorded host, exact
> dependency maintenance, bounded inference, and decision-safe bridge/fluid
> readout remain correct and exhibit the reported scaling behavior through the
> measured concurrent-atom, proof-DAG, and control-graph tiers. Engine-backed
> shadow runs confirm integration and overhead at their naturally achieved
> scale.

It still would not establish distributed OpenCog/Hyperon AtomSpace scaling,
unrestricted PLN theorem-search scaling, or improved FreeCiv gameplay.

## 15. Definition of done

This plan is complete only when:

- G0 through G9 have an explicit pass/fail/stop/not-entered decision;
- A4, P3, B3, and F3 have either completed or hit a preregistered stop rule;
- all held-out primary cells are accounted for;
- semantic and resource audits reconstruct from raw artifacts;
- production defaults and effective policy remain unchanged;
- results are visible in the observability app's experiment selector and a
  dedicated scale view showing atoms/supports/scopes, proof depth/nodes,
  control nodes/edges, edge updates, latency, RSS, scaling fits, and gate
  status; and
- the final claim states achieved measurements, not configured limits.
