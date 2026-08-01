# FDAS focused scope activation evidence

Status: component-only; no default live wiring.

`ScopeActivator` now turns explicit signals into deterministic activation
requests carrying reason, funding identity, priority, causal parents, turn,
expiry, and retained-momentum status. Ruleset/world/empire and configured
summary scopes remain always materialized. Focused region, corridor,
settlement, transport, combat, task-force, recovery, and belief scopes compete
under global and per-kind limits.

Rejected requests name the exhausted budget. TTL retention prevents scope
thrashing but expires without deriving any world fact from the loss of focus.
`ActivatedDomainProjector` can wrap an existing pure projector, materialize
against its complete internal scope topology, and publish only funded records.
It cannot omit the world or empire base scopes.

The default profile and manifest remain component-only, so this wrapper does
not change live decisions. Coverage is in
`Autotests/test_freeciv_fdas_scope_activation.py` plus existing scope and
transaction budget tests.
