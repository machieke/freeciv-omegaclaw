# Final global-turn gate smoke

Date: 2026-07-25

Status: focused regression, two-seed engine acceptance, and full release audit
passed. This is scoring-correctness and diagnostic latency evidence, not a
population-wide performance, score, or win-rate claim.

## Change

Final scoring previously used a fixed 250 ms sleep before requesting observer
state. Readiness required units, technologies, players, and both scores, but it
did not prove that those values belonged to the completed horizon.

The observer response already carries an authoritative `turn`. The harness now:

- requires initial and inter-turn observer state to reach the matching player
  snapshot turn;
- requires the post-horizon observer turn after the final `end_turn`;
- accepts the current terminal turn after exact player elimination, where no
  next begin-turn packet exists;
- polls at the contract-supported 50 ms interval instead of pre-sleeping;
- records `final_global_settle_latency_ms`;
- bounds each response wait by the caller's remaining deadline.

## Engine comparison

Both cohorts used the same packet-sequence-aware proxy, 50 ms player-state
stability interval, serial engine topology, 30-turn horizon, resident
`qwen3-coder-next:latest` model, planner policy, and seeds:

- fixed-sleep control:
  `artifacts/freeciv/turn-boundary-50ms-smoke-20260725`
- authoritative-turn treatment:
  `artifacts/freeciv/final-global-turn-smoke-20260725`

| Measure | Control | Treatment | Difference |
|---|---:|---:|---:|
| Gameplay, two-seed mean | 23,364.4 ms | 22,988.6 ms | -375.9 ms (-1.61%) |
| Complete backend, two-seed mean | 29,761.9 ms | 29,498.1 ms | -263.8 ms (-0.89%) |
| Mean turn loop | 623.9 ms | 615.1 ms | -8.9 ms (-1.42%) |
| Final gate | fixed 250 ms pre-sleep | 82.5 ms observed | -167.5 ms pre-query wait |

The treatment reached authoritative observer turn 31 in 74.3 ms for seed
104729 and 90.7 ms for seed 104743. The gameplay difference also includes
ordinary engine timing variance across the preceding turns, so it must not be
attributed entirely to the final gate.

## Behavioral acceptance

For both seeds, control and treatment had identical:

- initial authoritative fingerprint;
- canonical action sequence, bit-for-bit;
- engine and meaningful-action counts;
- fixed-horizon score and margin;
- city and settlement outcomes;
- zero rejected actions;
- zero deferred, expired, pending, or timed-out confirmations.

Seed 104729 remained at score 107, margin -2, 48 engine actions, 18 meaningful
actions, and one settlement. Seed 104743 remained at score 112, margin -3, 70
engine actions, 40 meaningful actions, and two settlements. Both treatment
arms reached turn 30 and collected scores from observer turn 31 without an
infrastructure failure.

## Verification

- Focused state/global-state tests: 5 passed.
- Engine comparison: 4/4 arms completed.
- Treatment release audit: all checks passed for both cognitive traces,
  including the pinned external contract and every PF-PLN phase replay.

## Scope

This validates an authoritative score-observation boundary and removes a
timer-based assumption on two deterministic engine seeds. It supports the
correctness hardening and its operational latency benefit. It does not
establish a general speedup, score improvement, or win-rate improvement.
