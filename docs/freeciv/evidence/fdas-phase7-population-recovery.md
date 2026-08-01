# FDAS Phase 7 population-recovery projection evidence

Status: component-only; no policy authority.

This slice projects a founder population-recovery scope only when the current
server snapshot advertises a valid `unit_join_city` action, the founder and
owned target city are exactly colocated, and one unambiguous compiled unit rule
proves all of `Cities`, `AddToCity`, and a positive integral `pop_cost`.

The population gain is ruleset-derived and is not inferred from unit names.
All records depend on current founder identity/type/tile, city identity/tile/
size, the byte-identical legal action, and the compiled ruleset digest. Missing
capability, population cost, colocation, or legality therefore produces no
positive recovery claim rather than a guessed negative.

Acceptance coverage is in `Autotests/test_freeciv_fdas_recovery.py`, including
incremental/cold equivalence when the action retracts. Persistent action/effect/
goal-relief separation remains a subsequent expansion-lifecycle slice.
