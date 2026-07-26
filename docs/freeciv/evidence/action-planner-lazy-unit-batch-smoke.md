# Action-planner lazy unit-batch smoke

Date: 2026-07-26

Status: retained single-seed engine smoke with exact ordered-action replay.
This is local planner-throughput evidence, not a gameplay-score, win-rate, or
statistically powered outer latency claim.

## Change

Civilization-wide unit-score batch projection is required only when a legal
military production target could contribute a batch member. Candidate
enumeration previously constructed that projection at the first production
alternative, even when the expansion deficit, remaining horizon, or target kind
made the result unusable.

The projection is now evaluated lazily inside the existing defender-target
branch. Its snapshot/legal-set cache identity, projections, canonical action
keys, batch-intent behavior, utility ordering, and execution boundary are
unchanged. A focused regression proves that an expansion-required catalog
selects its founder candidate without invoking unit-batch projection.

## Engine result

The fresh treatment `artifacts/freeciv/impact-lazy-unit-batch-20260726-a`
was compared with the same-seed
`artifacts/freeciv/impact-conductance-save-reuse-20260726-a` control:

| Metric | Control | Treatment | Change |
|---|---:|---:|---:|
| Production evaluation | 1.384 ms/call | 1.275 ms/call | -7.89% |
| Complete candidate enumeration | 2.691 ms/call | 2.571 ms/call | -4.45% |
| Complete planner decision | 4.372 ms/call | 4.252 ms/call | -2.74% |
| Impact planning | 6.850 ms/turn | 6.662 ms/turn | -2.74% |
| Pressure ranking | 1.622 ms/call | 1.623 ms/call | +0.01% |
| Score at turn 30 | 107 | 107 | identical |
| Score margin at turn 30 | -2 | -2 | identical |
| Engine rejection rate | 0 | 0 | identical |
| Confirmation timeouts | 0 | 0 | identical |

The treatment retained the exact ordered 48-action replay and complete
`run_completed.summary`. Full action-phase latency also fell in this trace, but
that noisier single-seed observation is not promoted to a standalone claim.

## Verification

- Complete canonical-runtime repository FreeCiv lane: 363 passed.
- Complete impact-planner test file: 63 passed.
- Fresh treatment engine trace: 1 completed, 0 infrastructure failures.
- Treatment trace release audit: all 10 applicable top-level checks passed.
- Exact ordered canonical action comparison: empty.
- Complete `run_completed.summary` comparison: identical.
- Static compilation and whitespace checks passed.
- The repository-prescribed `just check` entry point remains unavailable because
  `just` is not installed; the complete direct FreeCiv lane above passed.
