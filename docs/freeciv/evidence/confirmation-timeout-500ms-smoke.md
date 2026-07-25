# Deferred confirmation 500 ms engine smoke

Date: 2026-07-25

This is non-claim engineering evidence for the accepted-action confirmation
latency policy. It does not revise the paired score or win-rate claim.

## Design

- Backend: engine-live
- Condition: `e_full_loop`
- Seeds: 104729 and 104743
- Horizon: 30 turns
- Workers: one, serial order
- Model: `qwen3-coder-next:latest`
- Control configuration hash:
  `8d23000b0ae000186d988d4d5c134a455b2effecf990e8c99d9bd9577333d6ec`
- Candidate configuration hash:
  `0b9269dcff52b1810b8b4ab0faf9a55025fff87bbfbec60cf5b21a7093d531ac`
- Isolated policy change: `refresh_timeout_seconds` from 2.0 to 0.5

The development artifacts are:

- `artifacts/freeciv/readiness-policy-live-smoke-20260725`
- `artifacts/freeciv/confirmation-timeout-500ms-live-smoke-20260725`

## Results

| Seed | 2.0 s wall time | 0.5 s wall time | Reduction | Score | Margin | Actions |
|---|---:|---:|---:|---:|---:|---:|
| 104729 | 87.544 s | 49.793 s | 43.1% | 107 in both | -2 in both | 71 in both |
| 104743 | 89.142 s | 46.495 s | 47.8% | 109 in both | -6 in both | 68 in both |
| Mean | 88.343 s | 48.144 s | 45.5% | — | — | — |

Mean reported gameplay-loop latency fell from 2,592.2 ms to 1,229.8 ms
(52.5%). Mean effect-confirmation latency fell from 1,522.9 ms to 459.5 ms
(69.8%).

The candidate replay preserved, seed by seed:

- score and score margin;
- engine and meaningful-action counts;
- one founded city and 33 explored positions;
- `decision_effect_observed_rate=1`;
- zero grounded no-effect actions;
- zero deferred-confirmation expirations or pending outcomes.

Seed 104743 deferred and recovered one additional accepted action under the
shorter deadline (29 instead of 28), as expected. It did not change the
executed action count or any listed outcome.

Both candidate event streams passed strict causal validation (923 and 894
events) with zero errors. The result supports the shorter bounded wait because
the deferred ledger, rather than elapsed wall time, remains the authoritative
outcome mechanism.

## Scope

These were development smokes from a working tree and only two exposed seeds.
They establish implementation parity and a latency direction, not a
statistically general performance or gameplay claim. Configuration identity
prevents old 2.0-second arms from being resumed or pooled into a 0.5-second
cohort.
