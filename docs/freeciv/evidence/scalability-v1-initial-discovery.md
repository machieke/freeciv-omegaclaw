# Scalability v1 initial discovery checkpoint

Date: 2026-08-16
Branch: `experimental/larger-atomspace-inference-depth`
Baseline commit: `c11620134c0b671c3bc7f1f5c8f7dd2bf70e2f17`
Claim class: implementation screening and bounded single-seed discovery only

## What is implemented

- A frozen baseline manifest checks production defaults, source/config hashes,
  and the pre-existing FDAS proof, G3 bridge, and G4 flow evidence hashes.
- Strict hash-addressed scale-cell, trial, and result contracts are defined.
- The typed AtomSpace generator uses real `AtomRecord`, `SupportRecord`,
  `ScopeSpec`, `AtomSpaceTransaction`, and `DependencyIndex` APIs.
- Cold and support-aware incremental churn builds are compared by exact
  revision and record hashes.
- Deep proof inputs use real `RulesetIR` and `DeterministicRuleEngine` APIs and
  are checked by an independent graph reachability evaluator.
- Bridge inputs use exact-size `FlowView` graphs and the deterministic message
  estimator. Fluid inputs use the conservative production advection kernel.
- Captured records can be amplified while preserving the original subgraph;
  all clones are forced into diagnostic namespace and control-model authority.
- Every trial runs in a fresh process with the preregistered 120 s wall and
  16 GiB address-space limits. Actual work, CPU/wall time, RSS, GC state, and
  correctness hashes are recorded.
- Analysis uses Theil-Sen log slopes and graph-seed cluster bootstrap intervals.
  Results from different source/code digests are never pooled.
- The audit reconstructs trial and result identities and rejects tampering.

Two scaling defects were found and corrected during screening:

1. support invalidation rescanned every record once per invalid support; it now
   rewrites each indexed affected atom once;
2. fluid `run()` retained full state and overlap arrays for every microstep; an
   aggregate run path now preserves final state and safety counters with memory
   bounded by the current topology/state rather than topology times steps.

The relevant production regression and scale suites pass after both changes.

## Largest completed isolated discovery points

These trials use different evolving source digests and one seed each. They show
that the requested primary sizes can execute within the stop rules; they do not
constitute fitted scaling, p95, or held-out claims.

| Surface | Achieved work | Kernel/update time | Peak RSS | Correctness | Absolute-label indication |
|---|---:|---:|---:|---|---|
| A4 AtomSpace | 100,000 atoms, 100,000 supports, 1,000 scopes, 1,000 changed dependencies | 6.16 s incremental; 5.14 s cold rebuild | 1.25 GB | exact cold/incremental revision and record hashes | above 2 s A4 research label |
| P3 proof | depth 96, 100,000 proof records, 100,000 indexed distractor rules | 7.70 s proof | 870 MB | exact independent-oracle status/record agreement | below 15 s stress label |
| B3 bridge | 10,000 nodes, 40,000 edges, 2,048 candidates, 16 goals; 160,000 estimates | 2.71 s estimator | 487 MB | deterministic replay and bridge separation | above 2 s B3 research label |
| F3 fluid | 100,001 nodes, 200,000 directed edges, 10,000,000 edge updates | 30.51 s transport | 942 MB | exact work, no corrections, maximum normalized step error `3.33e-16` | above 5 s F3 research label |

Smaller discovery checkpoints also completed, including P2 with 10,000 proof
records in about 735 ms, B2 with 20,000 edges/eight goals in about 582 ms, and
F2 with one million edge updates in about 2.04 s. These numbers are diagnostic
single observations and must not be compared across code digests as a formal
fit.

## Current bounded conclusion

The Python implementation can represent and correctly process the plan's A4,
P3, B3, and F3 isolated primary work sizes without reaching the 16 GiB/120 s
stop limits. P3's point estimate is within its stress label; A4, B3, and F3 are
correct but miss their absolute point thresholds. No p95, scaling-exponent,
combined-load, engine-transfer, gameplay, score, or win-rate conclusion is yet
authorized.

The machine-readable reconstruction is in
`docs/freeciv/evidence/scalability-v1-initial-audit.json`; raw discovery trials
are under `artifacts/freeciv/scalability-v1/discovery/`.

## Required next work

1. commit a clean implementation and freeze selected cells plus held-out
   seeds before timing them;
2. execute the G2-G5 held-out cohorts and the frozen G6 combined design;
3. run the claim-eligible CA2/CA4 captured timing cohort and the new
   high-entity paired engine-shadow cohort;
4. publish held-out fits, confidence intervals, absolute labels, observability
   views, and explicit G0-G9 decisions.

## Second implementation checkpoint — 2026-08-16

The campaign implementation has advanced beyond the initial isolated kernels,
but its claim status has deliberately not advanced beyond discovery.

### Correctness and provenance hardening completed

- A real `DependentAtomSpaceStore` retention workload now runs 100
  publish/expiry/GC cycles. At A0 scale it retained at most four revisions and
  100 scopes, showed no revision or scope leak, and had 0% second-half
  post-GC RSS range on the recorded run. It completed in 34.40 seconds with a
  98,533,376-byte peak RSS.
- The proof engine now exposes deterministic counts for goal attempts, rules
  visited, bindings, memo hits, cycle rejections, grounded evaluations, and
  maximum attempted depth. Shared-DAG benchmark budgets account for memoized
  goal visits separately from unique rule count.
- Protected bridge readout now exercises the production candidate selector,
  explicit budget fallback, corrected-probe fallback, and bounded path
  persistence across sparse DAG, shared DAG, cyclic, disconnected,
  asymmetric-legality, bottleneck, and dynamic-failure inputs.
- Fluid trials support deterministic edge failure, zero current on retired
  edges, stale projection/topology rejection, exact accepted edge-update
  counts, and bounded-memory aggregate transport.
- The scaling source identity now covers every production module used by the
  tested kernels. Retention invariants are mandatory audit inputs rather than
  informational fields.
- A frozen held-out manifest binds the exact workload payloads and executable
  source identity. Held-out work refuses an absent freeze, a changed source,
  or an unregistered cell.
- Discovery and held-out reports are separate. The generated claim manifest
  consumes held-out evidence only and accounts frozen cells as completed,
  failed, stopped, or not entered.

The production scalar baseline, G3 bridge verification, and G4 flow sandbox
were replayed after the production changes and remain valid. The consolidated
scale/production regression slice contains 72 passing tests, and every scaling
JSON schema validates under JSON Schema 2020-12.

### Combined, captured, engine, and final-audit infrastructure

- G6 has a fixed 16-cell low/high design over AtomSpace, proof, bridge, and
  optional flow load plus a center cell. Prior stage working sets remain live
  during later stages. The interaction gate only pairs a combined result with
  same-source, same-seed isolated stages and enforces the preregistered 2x
  upper bound.
- Full AtomRecord telemetry can now be reconstructed into typed
  `AtomRecord`, `SupportRecord`, `ScopeSpec`, and `PredicateRegistry` values by
  streaming the ledger. Committed atom/scope/unique-support counts and the
  source ledger SHA-256 are verified.
- Retained live revisions were found to contain intentionally historical
  validity intervals. The captured amplifier does not weaken the
  same-snapshot transaction rule: it labels these inputs and validates them
  through a separate immutable production `DependencyIndex` path.
- G8 imports the repository's existing paired engine-shadow report and
  reconstructs its hash. It requires at least 20 pairs, exact ordered
  action/result/completion parity, valid ledgers, accepted clean source, and
  zero authority, omission, binding, or safety faults.
- The audit command now emits `aggregate.json`, `audit.json`, and
  `claim-manifest.json` in the campaign root in addition to the requested
  evidence output.

### First realistic-shape transfer point

The 500-turn full-detail ledger has SHA-256
`fbf665b6468c7af79915b684435acd52b77356a284f462d3788e562e2b4d8e4a`.
Its last turn-250 revision contained 817 records, 672 unique supports, and 17
scopes. It was amplified to 25,327 records, 20,832 unique supports, and 527
scopes while preserving the original subgraph exactly and quarantining all
24,510 cloned records in diagnostic/control-model identity space.

In the isolated discovery trial, amplification took 3,228.46 ms, ledger
loading took 6,424.97 ms, and peak RSS was 172,957,696 bytes. Its same-source
synthetic A2 construction took 2,821.81 ms and peaked at 357,388,288 bytes.
The current transfer ratios are therefore 1.144 for construction time and
0.484 for RSS, both below the 2x envelope.

This is one discovery snapshot, not the required 20-snapshot CA2/CA4 cohort.
G7 remains `not-entered`.

### Current gate state

The latest audit reconstructs 29 completed discovery trials with no integrity
errors. There are no frozen or held-out results. Consequently every held-out
surface, G6, G7, G8, and G9 remains `not-entered` or incomplete. The overall
discovery report retains an AtomSpace exponent failure and a fluid exponent
pass from older same-version discovery subsets; neither is a held-out claim.
The claim manifest explicitly reports `frozen=false`, zero held-out results,
and `g9_complete=false`.

## Third implementation checkpoint — same-source transfer and Scale Lab

The isolated runner now supplies an explicit repository and `src/` import path
to every worker. This fixes a clean-shell failure where the parent CLI could
import the benchmark package but a fresh worker could not import
`freeciv_agent`. A regression test executes a worker after changing out of the
repository and removing inherited `PYTHONPATH`.

A new same-source, same-measurement-contract discovery pair was completed at
turn 250 of the frozen full-AtomRecord ledger:

| Tier | Synthetic construction | Captured amplification | Captured/synthetic time | Synthetic RSS | Captured RSS | RSS ratio |
|---|---:|---:|---:|---:|---:|---:|
| A2 / CA2 | 2,617.71 ms | 3,167.04 ms | 1.210x | 358,023,168 B | 172,888,064 B | 0.483x |
| A4 / CA4 | 11,910.78 ms | 15,367.71 ms | 1.290x | 1,254,998,016 B | 555,601,920 B | 0.443x |

CA2 produced 25,327 amplified atoms from 817 source records; CA4 produced
100,491. Both preserve the original subgraph, verify the source SHA-256, and
quarantine every cloned record under diagnostic/control-model identity. These
two transfer points are within the preregistered 2x envelope. They remain
discovery evidence: only one captured turn has been evaluated, versus the 20
early/middle/late snapshots required by G7.

The observability app now has a dedicated **Scale lab** view backed by the
fixed `/api/freeciv-scalability` endpoint. It separates discovery from
held-out evidence and shows G2-G9 status, achieved work, log-scale performance
plots, absolute labels, combined-load interactions, captured transfer,
engine-shadow parity, claim eligibility, frozen-cell disposition, and the
source/freeze boundary. Displayed cards and plots are constrained to the
aggregate's selected source identity so evolving benchmark revisions cannot be
mixed visually. Browser verification covered both phases and all new panels
with no captured console or server errors.

## Fourth implementation checkpoint — executable primary matrix

The runner now has a read-only `plan` command and a fixed `primary` design.
The one-seed design contains 297 hash-addressed cells: 30 AtomSpace, 57 proof,
161 bridge, 32 fluid, and 17 combined cells. Ten discovery seeds contain 2,961
cells because the 100-cycle retention case runs only once. The design is
deliberately not a full Cartesian product.

The expanded mechanisms are:

- local, chain, hub, balanced-tree, shared-DAG, disconnected-shard, and mixed
  FDAS dependencies, with separate churn and support-multiplicity stress;
- chain, AND, 50%/90% diamonds, shared DAG, three OR cases, alternate/cycle-only
  cases, grounded blockers, binding-heavy proofs, and within-tier distractor
  levels;
- frozen scalar, protected message, corrected probe, path persistence, and
  numerical source-sink flow arms across seven bridge topologies; and
- conservative corridor and exact-work sparse-DAG transport at realized degree
  2/4/8 with zero, 1%, and 10% deterministic edge failures.

Canonical primary fits are explicitly selected: local 1%/one-support FDAS,
zero-distractor shared-DAG proof, protected-message/disconnected bridge, and
zero-failure corridor flow. Stress trials are retained and reported but never
pooled into those fits or their absolute labels. Proof distractor slopes are
fit within fixed P1/P2/P3 relevant-work strata. Captured and combined pairing
also selects only same-source canonical isolated rows.

Held-out orchestration distinguishes 40 semantic seeds from 50 canonical
timing samples per tier. Timing samples are assigned to three deterministic
randomized blocks. Exact trial identities resume from the artifact ledger
without rerunning, and the source identity now binds the experiment profiles
and all scaling schemas as well as executable code.

The first low-tier matrix checkpoint executed 57 isolated A0/P0/B0/F0 cells:
2 AtomSpace, 12 proof, 35 bridge, and 8 fluid. All 57 workers completed. The
run found one real dynamic-failure defect: path persistence could overwrite a
scalar fallback after an edge-generation change. Probe and persistence arms
now stop before readout on a failed topology; protected message, corrected
probe, path persistence, and source-sink flow all return the exact
`topology-edge-failure` fallback in the corrected replay.

The raw campaign currently contains 97 results: 95 completed and two preserved
historical clean-shell worker failures. The integrity audit is valid with zero
hash or identity errors. It separately retains the pre-fix path-persistence
row as one semantic failure, so the selected discovery bridge gate is `fail`
rather than allowing a repaired revision to erase the negative result. No
held-out claim is authorized.

The Scale Lab now displays the canonical fit contract on each surface and does
not promote a stress trial when the canonical set is empty. Final ProofShot
sessions verified discovery/held-out separation, zero-row behavior, and the
separation of audit integrity from retained semantic failures with zero
console or server errors.

## Fifth implementation checkpoint — three-seed semantic screening

The primary discovery runner now supports bounded parallel semantic screening
while retaining one-process execution for claim-eligible timing. Parallel rows
use the explicit `semantic-screening` telemetry mode, are checkpointed after
every completion, resume by exact trial identity, and are excluded from
scaling fits, absolute latency labels, captured-transfer references, and G6
interaction ratios. Repeating the same wall/OOM disposition on two seeds stops
the remaining tier while classifying every unentered row with both trigger
trial IDs; unaffected tiers continue.

The complete three-seed primary matrix contains 889 planned rows. All 889 are
accounted for under source identity
`c11620134c0b671c3bc7f1f5c8f7dd2bf70e2f17:7f1543bfe7899edc0c1b2d3e545a064f228233464227841d9309c03db0573504:4f957dd5d3ee827815923785c6cb48f99533e98ca2e82b52421ad4dee11e0c01`:

| Surface | Planned | Completed | Stopped | Screening conclusion |
|---|---:|---:|---:|---|
| AtomSpace | 88 | 70 | 18 | A0-A3 completed; A4 support-multiplicity 4 repeated the 120 s wall stop and stopped the remaining A4 tier |
| Proof | 171 | 171 | 0 | all P0-P3 proof families and distractor strata matched the independent oracle |
| Bridge | 483 | 446 | 37 | all 420 B0-B3 rows passed; descriptive B4 repeated protected-message/dynamic-failure wall stops and stopped the tier |
| Fluid | 96 | 96 | 0 | all F0-F3 corridor/sparse-DAG degree/failure rows preserved numerical and legality invariants |
| Combined | 51 | 49 | 2 | all completed rows preserved semantics; two C15 rows exceeded 120 s |
| **Total** | **889** | **832** | **57** | integrity valid; zero semantic failures |

The stop results are boundedness findings, not correctness defects. A4 has two
direct wall stops plus 16 declared tier-stop rows. B4 has 11 direct wall stops
plus 26 declared tier-stop rows. C15 has two direct wall stops. The audit
reconstructs every result/trial hash with no integrity error and finds zero
semantic failure among completed rows.

This cohort does not authorize timing or scaling claims. The three workers ran
simultaneously, so its measured latency/RSS values are screening diagnostics
only. In particular, the previously observable G6 ratios are now suppressed
for this cohort rather than presenting contention-influenced timings as
single-process estimates. The scaling test slice now has 83 passing tests.

## Sixth implementation checkpoint — ten-seed semantic screening

The primary semantic-screening matrix has now expanded from three to all ten
planned discovery seeds. Under source identity
`c11620134c0b671c3bc7f1f5c8f7dd2bf70e2f17:4076fe80607d9e487a31f51c49546824dfbfaacda3d3b355a170398e6bb1bcda:ff6f70fb777b59c033298c3248561be29d189853c6e2bf3399192b873df81976`,
all 2,961 planned rows are accounted for:

| Surface | Planned | Completed | Direct resource stops | Not entered after stop rule | Screening conclusion |
|---|---:|---:|---:|---:|---|
| AtomSpace | 291 | 182 | 2 | 107 | A0-A3 and 130 A2 shape/churn/support rows passed; A4 support-multiplicity 4 established the bounded resource edge |
| Proof | 570 | 570 | 0 | 0 | every P0-P3 proof family and distractor stratum matched the independent oracle |
| Bridge | 1,610 | 1,415 | 16 | 179 | all 1,400 B0-B3 rows passed; B4 bounded protected-message and path-persistence stress |
| Fluid | 320 | 320 | 0 | 0 | every F0-F3 corridor/sparse-DAG degree/failure row preserved mass, positivity, and legality invariants |
| Combined | 170 | 156 | 8 | 6 | all completed rows preserved semantics; C07/C11 had isolated wall stops and C13/C15 activated the repeated-stop rule |
| **Total** | **2,961** | **2,643** | **26** | **292** | schema-valid and audit-valid; zero semantic failures |

The tier detail is important. A4 contains 21 completions, two direct stops,
and 107 not-entered rows. B4 contains 15 completions, 16 direct stops, and 179
not-entered rows. C07 and C11 each contain nine completions and one direct
stop. C13 and C15 each contain four completions, three direct stops, and three
not-entered rows. Every P0-P3, B0-B3, and F0-F3 row completed.

All 2,961 rows validate against the strict JSON Schema. The audit reconstructs
every result hash and trial identity with zero integrity errors and reports no
semantic failure among the 2,643 completed rows. The stopped rows are explicit
boundedness outcomes; they are not reclassified as semantic successes.

This ten-seed run still does not authorize timing, scaling-exponent, p95, or G6
interaction claims. Its three workers ran concurrently under the explicit
`semantic-screening` telemetry mode. Those measurements are excluded from
canonical fits, absolute latency labels, captured-transfer references, and
combined interaction ratios. The next scientific boundary is therefore a
clean source freeze followed by the preregistered serial held-out semantic and
timing cohorts, not interpretation of these contention-influenced durations.

## Seventh implementation checkpoint — captured semantic transfer

The frozen full-AtomRecord ledger has the expected SHA-256
`fbf665b6468c7af79915b684435acd52b77356a284f462d3788e562e2b4d8e4a`
and contains committed revisions for every turn from 1 through 500. Twenty
preregistered early/middle/late turns were loaded: 1, 25, 50, and then every
25 turns through 500. Each snapshot was independently amplified to CA2 and
CA4 under the ten-seed screening source identity, yielding 40/40 successful
captured rows.

The captured source revisions range from 456 to 1,804 atoms. CA2 produced
25,080–26,262 amplified atoms, 288–684 scopes, and 13,122–22,876 unique
supports. CA4 produced 100,031–101,166 amplified atoms, 1,104–2,682 scopes,
and 50,301–89,698 unique supports. All 40 rows verify the source hash, preserve
the original subgraph exactly, meet the target atom count, and quarantine all
clones under diagnostic/control-model identity.

This is complete G7 semantic discovery coverage, not a transfer-performance
claim. The run used three parallel workers and explicit `semantic-screening`
telemetry, so all 40 timing/RSS observations are excluded from transfer-ratio
pairing. Captured analysis now reports semantic cohort completeness separately
from aggregate-timing completeness and returns `not-entered`, rather than
`fail`, when no claim-eligible timing cohort exists. When multiple source
versions exist, report selection prioritizes a passing gate, then complete
semantic coverage and cohort size, before pair count; this prevents an older
two-pair timing sample from hiding the complete 40-row semantic cohort.

The regenerated full-ledger audit contains 4,058 rows, has zero integrity
errors, and deliberately retains the one historical pre-fix semantic failure.
The selected captured version has 40 completed semantic rows, zero timing
rows, zero transfer pairs, and a `not-entered` transfer gate. The current
campaign-specific test slice has 85 passing tests.
