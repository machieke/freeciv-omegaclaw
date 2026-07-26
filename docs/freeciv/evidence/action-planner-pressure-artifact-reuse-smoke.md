# Action-planner pressure-artifact reuse smoke

Date: 2026-07-26

Status: retained single-seed engine smoke with exact ordered-action replay.
This is local planner-throughput evidence, not a gameplay-score, win-rate, or
statistically powered outer latency claim.

## Change

Impact pressure ranking emits both the complete propagated-pressure dictionary
and a scheduler artifact containing its structural hash. The scheduler
previously reconstructed the same pressure dictionary solely to calculate that
hash after the adapter had already constructed the value for emission.

The adapter now passes the emitted pressure dictionary into
`decision_artifact`. The scheduler hashes that exact value while continuing to
reuse its precomputed operation scores. The artifact value, hash material,
allocation, selection, score ordering, and public fallback path are unchanged.
Regression coverage asserts byte-equivalent artifact dictionaries between the
fallback and both reuse inputs.

## Engine result

The fresh treatment `artifacts/freeciv/impact-pressure-artifact-reuse-20260726-a`
was compared with the same-seed
`artifacts/freeciv/impact-lazy-unit-batch-20260726-a` control:

| Metric | Control | Treatment | Change |
|---|---:|---:|---:|
| Pressure artifact materialization | 0.394 ms/call | 0.351 ms/call | -10.84% |
| Complete pressure ranking | 1.623 ms/call | 1.533 ms/call | -5.53% |
| Pressure propagation | 0.495 ms/call | 0.456 ms/call | supporting |
| Pressure scheduling | 0.310 ms/call | 0.295 ms/call | supporting |
| Score at turn 30 | 107 | 107 | identical |
| Score margin at turn 30 | -2 | -2 | identical |
| Engine rejection rate | 0 | 0 | identical |
| Confirmation timeouts | 0 | 0 | identical |

The treatment retained the exact ordered 48-action replay and complete
`run_completed.summary`. Candidate and outer action-phase timing varied
independently, so the retained claim is limited to artifact materialization and
complete pressure ranking.

## Verification

- Complete canonical-runtime repository FreeCiv lane: 363 passed.
- Complete pressure and impact-planner test files: 99 passed.
- Fresh treatment engine trace: 1 completed, 0 infrastructure failures.
- Treatment trace release audit: all 10 applicable top-level checks passed.
- Exact ordered canonical action comparison: empty.
- Complete `run_completed.summary` comparison: identical.
- Static compilation and whitespace checks passed.
- The repository-prescribed `just check` entry point remains unavailable because
  `just` is not installed; the complete direct FreeCiv lane above passed.
