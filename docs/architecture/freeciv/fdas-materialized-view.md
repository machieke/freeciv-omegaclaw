# ADR: FDAS is a dependent materialized view

Status: accepted for implementation

Date: 2026-08-01

## Context

OmegaClaw already has an immutable authoritative FreeCiv snapshot, compiled
ruleset semantics, uncertain beliefs, durable operation state, pressure and
resource controllers, exact legal-action checks, commit revalidation, and a
final execution gate. The current AtomSpace projection exposes only a small
flat subset of that state and is rebuilt wholesale.

A richer knowledge substrate is needed for local causal reasoning, but making
that substrate a second state authority would create stale-state, truth/control
conflation, and action-safety risks.

## Decision

The Functional Dependent AtomSpace (FDAS) is a typed, scoped, versioned,
dependency-tracked materialized view over:

- the immutable authoritative snapshot;
- compiled ruleset semantics;
- explicitly qualified uncertain belief revisions;
- persistent operation revisions;
- versioned policy values; and
- compact observed decision episodes.

Every deterministic derived atom has a versioned support record naming its
exact dependency keys and fingerprints. Changed dependencies invalidate only
affected supports. Multiple independent supports are retained separately. A
cold rebuild and incremental update for the same revision must be canonically
equivalent.

FDAS does not send actions. An executable operation must still bind to the
byte-identical current legal action, reserve required packet/game resources,
pass exact commit revalidation, and pass the existing final execution gate.

Pressure, goal utility, predictions, and learned conductance are control
records, not epistemic truth. Numeric state remains behind typed grounded
functions. Negative conclusions require explicit completeness witnesses.

## Consequences

- One physical indexed store serves bounded logical scopes instead of one
  copied graph per entity.
- Snapshot and FDAS revisions must commit atomically.
- Every authority-bearing domain is independently feature-gated and begins in
  shadow mode.
- Existing projection, proof, candidate, execution, and safety behavior remain
  the compatibility oracle until each replacement slice passes its gates.
- Rich explanations become reconstructible from dependency/support records.
- The initial implementation is in-memory and reconstructible; persistence is
  introduced only if profiling justifies it.

## Rejected alternatives

- A second mutable game-state store: it would compete with engine authority.
- A single eagerly materialized global graph: it would create unbounded route,
  tile, and counterfactual fan-out.
- Numeric values as ordinary atoms: it would cause churn and weaken units and
  authority semantics.
- Direct action execution from inferred atoms: it would bypass the repository's
  proven legal-action and execution firewalls.
- Immediate replacement of `planning/impact.py`: it would combine semantic
  migration with policy change and prevent clean attribution.

## Acceptance boundary

This ADR authorizes component implementation only. Gameplay authority requires
the separate shadow, replay, safety, latency, and fresh empirical gates in the
FDAS implementation plan.
