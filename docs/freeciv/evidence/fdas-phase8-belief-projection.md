# FDAS Phase 8 belief projection evidence

Status: component-only, shadow-only, no policy authority.

`BeliefProjector` is a read-only scoped view over the existing `BeliefStore`.
It does not reproduce evidence union, uncertain deduction, decay, conflict, or
quarantine formulas. Each projected support instead depends on the immutable
belief revision and its evidence records.

One bounded opponent-belief scope is materialized per opponent represented by
current positive-confidence beliefs. The generic proposition atom retains the
full typed belief key in its support witness while truth remains explicitly
non-crisp in the `belief` namespace under `uncertain_belief` authority.
Simulation model identity and confidence caps, selection-policy correction,
evidence lineage, contexts, and current belief revision are inspectable.

The projector refuses beliefs whose last revision turn is not the current
snapshot turn. Callers must invoke the store's declared decay operation before
building the new revision; stale confidence therefore cannot silently cross a
turn boundary. Disappearance from visibility is not translated into negative
evidence.

Active conflicts are uncertain belief atoms. Their lineages and all applied
context quarantine relations are diagnostic/control records. Neither can
appear in authoritative or operation namespaces, create a legal binding, or
authorize an action. Same-snapshot belief-store changes use explicit FDAS
rematerialization and are checked against a cold build.

Coverage is in `Autotests/test_freeciv_fdas_belief.py`.
