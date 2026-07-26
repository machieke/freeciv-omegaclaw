# Impact post-confirmation and conductance persistence smoke

Date: 2026-07-26

Status: retained single-seed engine smoke with exact ordered-action replay.
This is mechanism evidence for a bounded CPU optimization, not a gameplay-score,
win-rate, or statistically powered latency claim.

## Attribution

The fresh trace `artifacts/freeciv/impact-learning-attribution-20260726-a`
split the 1.760 ms/turn post-confirmation block:

| Component | Latency |
|---|---:|
| Outcome resolution | 1.726 ms/turn |
| Effect detection | 0.019 ms/turn |
| Turn-budget accounting | 0.008 ms/turn |
| Deferred reconciliation | 0.004 ms/turn |

Resolution divided almost evenly between planner/conductance learning at
0.843 ms/turn and required `conductance_updated` event emission at
0.876 ms/turn. Learning then divided into:

| Component | Latency |
|---|---:|
| Conductance feedback | 0.566 ms/turn |
| Downstream route credit | 0.094 ms/turn |
| Route bookkeeping | 0.088 ms/turn |
| Local grounding | 0.066 ms/turn |
| Goal-relief calculation | 0.020 ms/turn |
| Feedback identity | 0.001 ms/turn |

The conductance trace
`artifacts/freeciv/impact-conductance-attribution-20260726-a` showed that
atomic JSON persistence occupied 0.419 ms/turn, returned state hashing occupied
0.068 ms/turn, and the in-memory update occupied only 0.059 ms/turn.

## Change

Conductance persistence still writes every applied grounded feedback to a
temporary file and atomically replaces the attempt-scoped state file. The
optimized implementation:

- returns the state hash already computed for the persisted snapshot instead of
  recomputing it immediately;
- caches that immutable hash until a route or feedback ID changes; and
- writes the identical JSON value in canonical compact form.

Reload validation, feedback idempotency, one-save-per-feedback crash behavior,
and the state-hash material are unchanged.

## Result

The fresh treatment
`artifacts/freeciv/impact-conductance-save-reuse-20260726-a` retained the exact
48-action replay and complete run summary:

| Metric | Control | Treatment | Change |
|---|---:|---:|---:|
| Conductance feedback | 0.577 ms/turn | 0.399 ms/turn | -30.77% |
| Conductance atomic save | 0.419 ms/turn | 0.310 ms/turn | -26.13% |
| Returned state hash | 0.068 ms/turn | 0.001 ms/turn | -99.17% |
| Complete outcome learning | 0.851 ms/turn | 0.605 ms/turn | -28.95% |
| Complete post-confirmation | 1.742 ms/turn | 1.474 ms/turn | -15.36% |
| Score at turn 30 | 107 | 107 | identical |
| Score margin at turn 30 | -2 | -2 | identical |
| Engine rejection rate | 0 | 0 | identical |
| Confirmation timeouts | 0 | 0 | identical |

A 100-feedback microbenchmark reduced a cached decision snapshot from
0.0211 to 0.0013 ms/call and persistent feedback from 0.2665 to
0.1245 ms/call. Reloading the compact file reproduced the exact live state
hash.

Full action-phase latency remained noisy across individual engine runs, so no
outer latency claim is made from this single seed. Conductance-event emission
is now the largest post-confirmation component and remains unchanged because it
is required for causal replay and live observability.

## Verification

- Complete canonical-runtime repository FreeCiv lane: 362 passed.
- Complete pressure and impact-planner test files: 98 passed.
- Fresh attribution and treatment engine traces: 3 completed, 0
  infrastructure failures.
- Treatment trace release audit: all 10 applicable top-level checks passed.
- Exact ordered canonical action comparison: empty.
- Complete `run_completed.summary` comparison: identical.
- Static compilation and whitespace checks passed.
- The repository-prescribed `just check` entry point remains unavailable because
  `just` is not installed; the complete direct FreeCiv lane above passed.
