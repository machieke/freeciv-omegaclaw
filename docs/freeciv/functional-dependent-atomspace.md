# Functional Dependent AtomSpace

Status: Phase 0 contract and baseline passed; FDAS core not built

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

## Activation

`profile/fdas_manifest.json` declares every FDAS capability `not-built`, with
the component and policy authority disabled. `profile/fdas_catalog.json`
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
