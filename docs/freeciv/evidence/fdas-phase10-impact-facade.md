# FDAS Phase 10 Impact facade decomposition

Status: behavior-preserving structural consolidation.

Stable Impact data contracts, explicit strategic priority defaults, and pure
action/map helpers now live in `planning/impact_types.py`. `planning/impact.py`
re-exports the identical objects, so existing callers and serialized candidate
semantics remain unchanged. The unchanged imperative implementation is now in
`planning/impact_legacy.py`; the public `planning/impact.py` integration facade
is 75 lines instead of 7,432. No legacy decision branch was removed.

The separation makes policy defaults visible as policy rather than ruleset
facts and allows FDAS operation adapters to consume stable candidate/outcome
contracts without importing the planner's full imperative implementation.
Semantic deletion remains controlled by the independent legacy-consolidation
audit and is not authorized by this refactor.

Dedicated facade tests cover object identity, canonical action keys, scope and
turn-budget behavior, grounded relief serialization, and deferred outcome
resolution. The broader Impact/FDAS regression passed 189 tests at this
boundary.
