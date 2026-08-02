# FDAS Phase 2 dependency materializer evidence

Status: passed, component-only

Date: 2026-08-01

Branch: `experimental/functional-dependent-atomspace`

## Claim boundary

FDAS is now a dependency-aware incremental materialized view for the frozen
ten-predicate compatibility projection. It has no planning or execution
authority. Ruleset projection, generic domain inference, rich city/unit scopes,
operations, pressure adaptation, and episode learning remain outside this
claim.

## Implemented

- canonical `SnapshotDelta` values use stable field and entity keys rather
  than Python object identity;
- direct projection supports depend on exact stable source fields rather than
  whole snapshot identities;
- immutable reverse indexes cover atoms, supports, dependencies, derivations,
  scopes, entities, operations, and beliefs;
- changed source keys invalidate supports transitively through atom
  dependencies, retracting an atom only after its final independent support is
  lost;
- projection batches reject undeclared dependencies and cross-scope writes;
- derivations are versioned, stratified, pure-context evaluations with
  instrumented declared source access and output budgets;
- negative output templates fail closed without an explicit completeness
  witness;
- incremental refresh reuses unchanged supports and recomputes only relations
  whose source fingerprints changed;
- a cold builder provides a canonical differential oracle;
- immutable revision retention honors active leases;
- decision-safe queries reject stale snapshot revisions; and
- `SnapshotStore` coordinates snapshot, legacy view, and typed revision
  publication under the same re-entrant lock.

## Correctness results

| Check | Result |
| --- | ---: |
| randomized deterministic mutations | 20 / 20 cold-equivalent |
| retained game transitions | 12 / 12 cold-equivalent |
| exact legacy projection | unchanged |
| frozen Phase 0 semantic hash | reproduced |
| independent-support retention | passed |
| transitive support retraction | passed |
| undeclared dependency rejection | passed |
| cycle/invalid-stratum rejection | passed |
| negative-without-completeness rejection | passed |
| stale decision query rejection | passed |
| lease-protected revision retention | passed |
| policy authority | false |

One city production-target mutation recomputes exactly one relation, refreshes
the other 11 records, invalidates one support, and is cold-equivalent. Across
the sparse retained sequence, a transition recomputed 44.2 of 386.3 records on
average. The largest transition spans 60 turns and recomputes 213 of 436
records; it is intentionally retained as catch-up stress rather than presented
as an ordinary-turn result.

## Performance results

The 13 retained captures contain 12 transitions. Same-turn and adjacent-turn
transitions are the ordinary-turn cohort; the complete cohort also includes
gaps of 2, 4, 21, 22, and 60 turns.

| Measurement | Samples | Mean | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| ordinary full incremental transaction | 140 | 16.16 ms | 18.53 ms | 19.22 ms |
| all sparse captured transitions | 240 | 20.25 ms | 37.14 ms | 38.79 ms |
| dependency invalidation | 1,200 | 1.12 ms | 5.54 ms | 7.18 ms |

The ordinary transaction is below the initial 30 ms snapshot-delta/base-
projection target, and invalidation is below its 15 ms target. Sparse
multi-turn catch-up remains below the 150 ms ordinary total-FDAS allocation but
is not used to claim the ordinary stage gate. Cyclic garbage collection is
suspended only inside the globally serialized immutable build transaction and
restored afterward, eliminating periodic 15–20 ms scan spikes without changing
reference-count reclamation or record semantics.

## Reproduction

```bash
python3 scripts/run_fdas_phase0_baseline.py --check --iterations 1
pytest -q \
  Autotests/test_freeciv_fdas_dependencies.py \
  Autotests/test_freeciv_fdas_core.py \
  Autotests/test_freeciv_fdas_phase0.py \
  Autotests/test_freeciv_state_bridge.py \
  Autotests/test_freeciv_rulesets.py \
  Autotests/test_freeciv_beliefs.py \
  Autotests/test_freeciv_planning.py \
  Autotests/test_freeciv_pressure.py \
  Autotests/test_freeciv_pressure_v2.py
```

## Activation state

```text
dependent_atomspace_core = component-only
dependency_truth_maintenance = component-only
incremental_snapshot_projection = component-only
component_enabled = true
policy_authority = false
all domain/policy capabilities = not-built
```

## Rich-projector follow-on hardening

The later rich runtime now applies the same dependent-view principle at a
coarse component boundary. Each rich projector declares conservative snapshot
roots and durable dependency kinds. The composite stores a bounded eight-
revision component cache and may reuse a prior output only when:

- the declared input digest is identical;
- every previously observed support dependency outside that declaration is
  still identical; and
- the projector's complete scope-ID set is identical.

Reused atoms are reconstructed with the current scope validity; the prior
record object is never published as current. Missing cache state, an absent
declaration, a scope change, or an input change falls back to full component
projection. Sampled verification publishes the already-verified incremental
revision, while the independent cold build remains the canonical oracle.

The full captured rich-shadow cohort passed 37/37 differential transitions
with zero failures. Focused tests prove both non-empty reuse on an unchanged
same-turn input and forced recomputation on a declared city-surplus mutation.
Materialization metrics now expose recomputed/reused projector IDs and record
counts plus the total recomputation ratio. All authority flags remain false.

Rich projection is also guarded by a fail-closed top-level access audit. The
composite supplies a read-only recording view to every recomputed projector and
rejects publication if the projector reads a semantic snapshot root absent
from its incremental declaration. Direct `snapshot_id` use as a cache key is
treated as transaction plumbing; nested identity reads remain audited, while
scope validity, support dependencies, conservative declarations, and cold
parity protect output identity. A regression deliberately removes `cities`
from the city/economy declaration and confirms that the snapshot is rejected.

The audit exposed two previously implicit transitive inputs before activation:
transport capacity extraction reads city/economy/research capacity sources,
and route-corridor visibility reads map tiles and turn state. Those inputs are
now declared. After correction, the audited full-rich captured cohort again
passed 37/37 differential transitions with zero failures.
