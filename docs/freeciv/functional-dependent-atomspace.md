# Functional Dependent AtomSpace

Status: Phase 2 dependency materializer passed; component-only

Branch: `experimental/functional-dependent-atomspace`

Canonical implementation plan:
`agent-instructions/functional-dependent-atomspace-implementation-plan.md`

## Objective

FDAS will replace the thin, flat snapshot projection with a rich but bounded
knowledge substrate for city, economy, unit, region, threat, operation, and
episode reasoning. It remains a materialized view and never becomes a second
authority for FreeCiv state or action execution.

The intended path is:

```text
snapshot + ruleset + beliefs + operations + policy
  -> typed base projection
  -> dependency-aware scoped materialization
  -> local facts, deficits, proofs, and causal routes
  -> PF-PLN pressure and exact resource scheduling
  -> current-state/legal-action commit revalidation
  -> existing final execution gate
  -> observed episode and contextual learning
```

## Frozen boundaries

1. Engine snapshots remain ground truth.
2. Ruleset-exact facts are valid only for their compiled digest.
3. Derived facts retain support/dependency witnesses and never become
   authoritative facts.
4. Uncertain revision remains owned by `BeliefStore`.
5. Pressure, utility, urgency, prediction, and conductance never mutate truth.
6. Numeric state is exposed by typed grounded functions with units,
   dependencies, validity, and witnesses.
7. Negation requires a closed-domain completeness witness.
8. Planned or predicted state cannot satisfy a current factual predicate.
9. Every executable step binds to a byte-identical current legal action.
10. Existing packet/resource, commit-validation, quarantine, and execution
    gates remain downstream and authoritative.
11. Budget exhaustion produces `unknown` or truncation, not crisp falsehood.
12. Cold and incremental materialization must produce the same canonical
    records and explanations.

The architectural decision is recorded in
[FDAS is a dependent materialized view](../architecture/freeciv/fdas-materialized-view.md).

## Phase 0 baseline

Phase 0 changes no gameplay behavior. It freezes:

- current legacy projection predicates and canonical atoms;
- grounded predicate signatures;
- current technology proof results;
- captured candidate sets and selected operations;
- reconstructed current adapter graph identities and sizes;
- operation, resource, event, scope, namespace, and authority catalogs; and
- an explicit `not-built` capability manifest.

The source cohort is the 13 retained player-visible snapshots in
`city_defense_grounded_160_manifest.json`. The generated diagnostic is
`benchmarks/fdas/phase0-baseline.json`; its semantic hash excludes volatile
latency measurements.

Reproduction:

```bash
python3 scripts/run_fdas_phase0_baseline.py
python3 scripts/run_fdas_phase0_baseline.py --check --iterations 1
```

## Phase 1 typed core

The compatibility facade now sends the existing ten-predicate snapshot
projection through immutable typed records before returning the unchanged
`SnapshotAtomspaces` value. The component includes:

- typed entity and symbol terms with numeric leakage rejection;
- deterministic atom, support, materialization, and revision identities;
- predicate arity, namespace, argument-kind, and scope validation;
- authority and validity metadata;
- dependency-backed direct-projection supports;
- deterministic world and empire scopes;
- atomic, fail-closed full-build transactions; and
- an in-memory immutable revision store.

All 13 baseline fixtures produce exactly the frozen legacy view. The warm
captured-snapshot projection measured 21.1 ms mean and 29.8 ms p95 over 260
builds, within the initial 30 ms base-projection target. This phase implements
full rebuild only: reverse dependency indexes, invalidation, incremental
materialization, derivations, queries, and planning authority were absent at
the Phase 1 boundary.

## Phase 2 dependent materializer

The current store adds stable field/entity dependency keys, canonical snapshot
deltas, immutable reverse indexes, support-aware transitive retraction,
stratified pure derivations, completeness guards for negative outputs,
incremental support reuse, cold-reference verification, revision leases, and
decision-stale query rejection. `SnapshotStore` publishes the authoritative
snapshot, legacy view, and typed revision under one coordinator lock.

Incremental/cold equality passes for 20 deterministic randomized mutations and
all 12 transitions in the retained 13-snapshot game sequence. On adjacent or
same-turn captured revisions the full incremental transaction measured 16.2 ms
mean and 18.5 ms p95. Dependency invalidation measured 1.12 ms mean and 5.54 ms
p95 over 1,200 samples. Sparse captures spanning 2–60 turns require more
recomputation and measured 20.3 ms mean and 37.1 ms p95; they are retained as
worst-case catch-up evidence rather than represented as ordinary single-turn
updates.

This remains a compatibility-only materialized view. No generic domain rule,
goal, candidate, pressure, or execution path consumes FDAS yet.

## Activation

`profile/fdas_manifest.json` declares the typed core, dependency truth
maintenance, and incremental snapshot projection as `component-only`. The
compatibility facade is enabled, but policy authority is false and every
domain/policy capability remains `not-built`. `profile/fdas_catalog.json`
separates the ten legacy projected predicates and nine legacy groundings from
the proposed namespaces, authority classes, scopes, first-slice predicates,
and typed groundings.

Implementation state and authority state are intentionally separate. Future
phases advance individual capabilities through:

```text
not-built -> component-only -> shadow-live -> bounded-authority -> engine-live
```

No configuration field alone may skip those stages.

## First vertical slice

After the typed store, dependencies, ruleset projection, and generic proof
foundation exist, the first end-to-end slice is city stability/production,
followed by city defense and local movement. Individual citizen-to-tile
control remains outside the boundary until the proxy exposes assignments,
legal changes, and authoritative outcomes.

The first bounded authority candidate is production retention/switching only
when exact buildability, food, population, treasury, deadline, operation,
resource, current legal action, and commit-refresh guards all pass. It remains
default-off until fresh acceptance evidence exists.
