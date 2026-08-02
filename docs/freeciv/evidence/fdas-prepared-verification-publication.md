# FDAS prepared verification publication

Date: 2026-08-01  
Claim scope: implementation efficiency under strict parity verification

## Defect

On a sampled cold-parity update, the runtime previously performed three rich
projections:

1. prepare the incremental candidate revision;
2. prepare an independent cold revision and compare it;
3. discard the verified candidate and ask `SnapshotStore.replace()` to prepare
   the same incremental revision again.

This was correct but needlessly inflated the most expensive diagnostic path.

## Correction

`DependentAtomSpaceStore.prepare_verified_incremental()` now returns both the
prepared incremental revision and its immutable differential proof.
`SnapshotStore.replace_prepared()` publishes that revision under the shared
coordinator lock only when the expected prior revision is still current. A
concurrent advance, snapshot mismatch, parity mismatch, or ordering regression
fails closed before publication.

The ordinary unsampled path and the public `verify_incremental()` contract are
unchanged.

## Verification

- Runtime/state/dependency/core regressions: `61 passed in 22.28s`.
- Regression instrumentation proves a sampled update invokes exactly two
  prepares, `[incremental, cold]`, and publishes the first revision.
- Strict captured transitions: 37/37 incremental/cold equivalent; zero
  failures.

| 100%-verification projection latency | Before | After |
|---|---:|---:|
| Mean | 605.10 ms | 412.44 ms |
| p50 | 596.99 ms | 403.65 ms |
| p95 | 1,119.24 ms | 756.69 ms |
| Maximum | 1,310.63 ms | 881.78 ms |

The before values are from the final captured report at `5fc41ff`; the after
values are from the same checked corpus and configuration after the correction.
This is not yet fine-grained rich projector incrementality: it removes a
duplicate publication build while retaining the mandatory cold comparison.
