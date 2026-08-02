# FDAS Phase 10 operator diagnostics evidence

Status: component-only and read-only.

`AtomSpaceDiagnostics` supplies deterministic in-process report builders for
revision statistics, active scopes, atom explanations, why-not queries,
revision diffs, dependencies, dependents, captured shadow decisions, and
incremental/cold verification. Reports retain revision and snapshot identity
and structural hashes where appropriate.

The runtime readout now also creates a single machine-readable decision bundle
for the selected grounded candidate, explicit inference gap, or not-applicable
result. It connects the selected operation to goal/deficit proof, causal
pressure rule, grounded candidate and current legal action, resource claims,
operation requirements/steps/completion predicate, selected scheduler
evidence, and why-not blockers. `atomspace_shadow_decision` exposes the bundle
hash, route kind, and blockers; the replay artifact retains the full bounded
bundle for inspection.

Diagnostics operate on an immutable `DependentAtomSpaceRevision`. They cannot
publish revisions, mutate supports, update truth or beliefs, reserve resources,
bind legal actions, or acquire policy authority. A missing condition remains
`UNKNOWN` unless the typed query layer has an explicit blocker; diagnostics do
not turn absence into falsehood.

Coverage is in `Autotests/test_freeciv_fdas_diagnostics.py` plus the existing
revision, query, dependency, and cold-equivalence suites.
