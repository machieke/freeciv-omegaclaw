# Action-planner pressure-index smoke

Date: 2026-07-26

Status: retained single-seed engine smoke with exact ordered-action replay.
This is local pressure-scheduling throughput evidence, not a gameplay-score,
win-rate, or statistically powered outer latency claim.

## Change

`PressureResult` stores canonical dependency, action-dependency, and pressure
rows as immutable tuples. Each lookup previously rebuilt the complete nested
dictionary from those tuples. Scheduling performs one pressure lookup for every
goal and operation pair, so one propagated result was reconstructed repeatedly.
Successful lookups also eagerly allocated a zero `PressureVector` even though
the default was unused.

`PressureResult` now creates private lookup indices once in `__post_init__` and
uses one frozen zero-pressure sentinel for misses. Canonical tuple storage,
artifact serialization, equality, truth values, and pressure values remain
unchanged. Regression coverage checks dependency, action-dependency, pressure,
miss, and serialized-artifact equivalence.

An isolated four-goal, 24-lookup Python 3.8 microbenchmark fell from 0.0932 to
0.0066 ms per lookup batch (-92.9%).

## Engine result

The fresh treatment `artifacts/freeciv/impact-pressure-index-20260726-a`
was compared with the same-seed
`artifacts/freeciv/impact-event-schema-inline-20260726-a` control:

| Metric | Control | Treatment | Change |
|---|---:|---:|---:|
| Pressure scheduling | 0.290 ms/call | 0.193 ms/call | -33.26% |
| Complete pressure ranking | 1.550 ms/call | 1.442 ms/call | -6.96% |
| Complete impact planning | 6.728 ms/turn | 6.569 ms/turn | -2.36% |
| Pressure propagation | 0.473 ms/call | 0.474 ms/call | noise |
| Pressure artifact materialization | 0.366 ms/call | 0.371 ms/call | noise |
| Score at turn 30 | 107 | 107 | identical |
| Score margin at turn 30 | -2 | -2 | identical |
| Engine rejection rate | 0 | 0 | identical |
| Confirmation timeouts | 0 | 0 | identical |

The treatment retained the exact ordered 48-action replay and complete
`run_completed.summary`. The primary claim is the pressure-scheduling slice;
the full pressure and planner reductions are consistent supporting
observations from this single engine pair.

## Verification

- Complete canonical-runtime repository FreeCiv lane: 365 passed.
- Complete pressure regression lane: 43 passed.
- Fresh treatment engine trace: 1 completed, 0 infrastructure failures.
- Treatment trace release audit: all 10 applicable top-level checks passed.
- Exact ordered canonical action comparison: identical.
- Complete `run_completed.summary` comparison: identical.
- Static whitespace checks passed.
- The repository-prescribed `just check` entry point remains unavailable because
  `just` is not installed; the complete direct FreeCiv lane above passed.
