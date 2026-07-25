# Turn-boundary 50 ms stability smoke

Date: 2026-07-25

Status: focused regression, two-seed engine acceptance, and full release audit
passed. The latency result is diagnostic engineering evidence, not a
population-wide speed, score, or win-rate claim.

## Change

The accepted-action refresh already required two identical decision
fingerprints separated by 50 ms. Initial and inter-turn readiness used the
same exact fingerprint and sample count but retained a 100 ms default
interval. The harness now uses 50 ms for every identical-state sample while
retaining:

- bounded source-sequence waits;
- two matching samples where stability is required;
- reset-on-change behavior;
- authoritative state, visible-enemy, and exact legal-action-digest coverage;
- the proxy contract's 50 ms minimum wait guard.

A focused regression records the default sleep and requires exactly 50 ms
between two stable samples.

## Engine comparison

Both cohorts used the packet-sequence-aware extractor cache, the same serial
engine topology, 30-turn horizon, resident `qwen3-coder-next:latest` model,
planner policy, and seeds:

- 100 ms control:
  `artifacts/freeciv/extractor-source-seq-cache-repeat-20260725`
- 50 ms treatment:
  `artifacts/freeciv/turn-boundary-50ms-smoke-20260725`

Inter-turn boundary latency is calculated as total loop time minus the sum of
per-turn work, divided by the 29 transitions.

| Measure | 100 ms control | 50 ms treatment | Difference |
|---|---:|---:|---:|
| Gameplay, two-seed mean | 24,601.2 ms | 23,364.4 ms | -1,236.7 ms (-5.03%) |
| Complete backend, two-seed mean | 31,139.9 ms | 29,761.9 ms | -1,378.0 ms (-4.43%) |
| Mean turn loop | 665.8 ms | 623.9 ms | -41.8 ms (-6.28%) |
| Mean inter-turn boundary | 308.8 ms | 260.1 ms | -48.7 ms (-15.76%) |
| Mean impact confirmation | 129.4 ms | 129.0 ms | -0.4 ms (-0.32%) |

The boundary reduction is the expected mechanism: roughly one 50 ms sleep is
removed from each stable transition. Impact confirmation is unchanged because
it already used the 50 ms interval.

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
arms reached turn 30 without an infrastructure failure.

## Verification

- Focused default-interval regression and state tests: 8 passed.
- Engine comparison: 4/4 arms completed.
- Treatment release audit: all checks passed for both cognitive traces,
  including the pinned external contract and PF-PLN phase replay.

## Scope

This cohort demonstrates that the duplicate 100 ms boundary interval can be
reduced to the contract-supported 50 ms interval without changing behavior on
the two deterministic smoke seeds. The result is suitable for operational
optimization acceptance. It does not establish a general speedup, score
improvement, or win-rate improvement.
