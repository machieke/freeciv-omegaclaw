# Action-planner pressure-identity reuse smoke

Date: 2026-07-26

Status: retained single-seed engine smoke with exact ordered-action replay.
This is local event-path throughput evidence, not a gameplay-score, win-rate,
or statistically powered outer latency claim.

## Change

Impact pressure scheduling binds each exact materialized pressure artifact to a
`pressure_hash`. Decision-event emission previously serialized and hashed the
same pressure dictionary again to produce the `pressure_propagated.result_hash`
and `pressure_id`.

The engine harness now reuses the scheduler's bound `pressure_hash`. The
pressure payload, schedule, causal event order, schema validation, atomic
append, turn-boundary durability, and replay identities are unchanged.
Regression coverage explicitly checks that the scheduler hash equals a fresh
structural hash of the pressure artifact.

## Engine result

The fresh treatment `artifacts/freeciv/impact-pressure-hash-reuse-20260726-a`
was compared with the same-seed
`artifacts/freeciv/impact-pressure-artifact-reuse-20260726-a` control:

| Metric | Control | Treatment | Change |
|---|---:|---:|---:|
| Impact decision-event emission | 2.261 ms/turn | 1.997 ms/turn | -11.71% |
| Complete impact planning | 6.682 ms/turn | 6.628 ms/turn | -0.82% |
| Complete pressure ranking | 1.533 ms/call | 1.540 ms/call | noise |
| Score at turn 30 | 107 | 107 | identical |
| Score margin at turn 30 | -2 | -2 | identical |
| Engine rejection rate | 0 | 0 | identical |
| Confirmation timeouts | 0 | 0 | identical |

The treatment retained the exact ordered 48-action replay and complete
`run_completed.summary`. The retained throughput claim is limited to the
decision-event slice because this is a single live-engine pair and the outer
planner movement is small relative to run noise.

## Verification

- Complete canonical-runtime repository FreeCiv lane: 363 passed.
- Focused pressure and harness regression lane: 83 passed.
- Fresh treatment engine trace: 1 completed, 0 infrastructure failures.
- Treatment trace release audit: all 10 applicable top-level checks passed.
- Exact ordered canonical action comparison: identical.
- Complete `run_completed.summary` comparison: identical.
- Static whitespace checks passed.
- The repository-prescribed `just check` entry point remains unavailable because
  `just` is not installed; the complete direct FreeCiv lane above passed.
