# Clean-successor server-recycle smoke

Date: 2026-07-25

Status: process-manager unit tests, focused harness tests, two independent
two-seed engine cohorts, proxy regression suite, and four-trace release audit
passed. This is operational throughput evidence, not a gameplay-performance,
score, or win-rate claim.

## Root cause and change

Publite2 applied a fixed five-second delay after every Freeciv server exit,
including normal status-zero completion. The harness then waited for a fresh
PID and listening socket before every arm, so a correct isolation boundary
cost approximately 5.25 seconds.

The tracked external patch now uses:

- 100 ms before restart after exact status-zero completion;
- the unchanged five-second backoff after nonzero exit, signal failure, or
  launcher exception.

The harness records the PID used by a successfully completed arm. Its next arm
may accept only a distinct PID with an exact `LISTEN` socket on the dedicated
port. A failed arm never records a reusable predecessor and therefore takes
the unconditional kill/recycle path. The chosen method and PID are persisted
as `engine_server_recycle_method` and `engine_server_pid`.

The tracked external patch digest is
`c3c58d71996737a92ce27bd3616dcbfdfb831a6f327331622a4ce2d3e9340437`.

## Engine comparison

All cohorts used the same seeds, serial topology, 30-turn horizon, resident
`qwen3-coder-next:latest` model, planner policy, packet-sequence-aware state
cache, 50 ms state stability, and authoritative final-score gate:

- five-second control:
  `artifacts/freeciv/final-global-turn-smoke-20260725`
- clean-restart treatment:
  `artifacts/freeciv/clean-successor-recycle-smoke-20260725`
- independent treatment repeat:
  `artifacts/freeciv/clean-successor-recycle-repeat-20260725`

| Measure (two-seed mean) | Control | Treatment | Repeat | Control to treatment |
|---|---:|---:|---:|---:|
| Engine preflight | 5,253.8 ms | 423.9 ms | 398.9 ms | -4,829.9 ms (-91.93%) |
| Complete backend | 29,498.1 ms | 24,675.1 ms | 24,569.4 ms | -4,823.0 ms (-16.35%) |
| Gameplay | 22,988.6 ms | 23,023.0 ms | 22,897.8 ms | +34.5 ms (+0.15%) |

The first treatment measured 560.3 ms and 287.4 ms of preflight; the repeat
measured 562.0 ms and 235.8 ms. The repeat explicitly recorded
`kill-then-listener` for its first arm and
`clean-successor-listener` for its second. Gameplay variation brackets zero,
as expected for an optimization outside the game loop.

## Behavioral acceptance

For both seeds, control, treatment, and repeat had identical:

- initial authoritative fingerprint;
- canonical action sequence, bit-for-bit;
- engine and meaningful-action counts;
- fixed-horizon score and margin;
- city and settlement outcomes;
- zero rejected actions;
- zero deferred, expired, pending, or timed-out confirmations.

Seed 104729 remained at score 107, margin -2, 48 engine actions, 18 meaningful
actions, and one settlement. Seed 104743 remained at score 112, margin -3, 70
engine actions, 40 meaningful actions, and two settlements. All six arms
reached turn 30 without an infrastructure failure.

## Verification

- Publite2 clean/error restart policy: 2 passed.
- Focused harness recycle and backend-order tests: 3 passed.
- Focused patched-proxy suite: 113 passed, 4 skipped.
- Engine comparison: 6/6 arms completed.
- Full release audit: all checks passed for all four treatment traces,
  including the pinned external contract and every PF-PLN phase replay.
- Fresh patch reverse-check: passed against upstream commit
  `26ba7124249f34fd3050ef29bf191bd4d8808018`.

## Scope

This establishes that the five-second delay was a clean-exit process-manager
backoff rather than necessary server startup time. The new path retains
failure backoff and fresh-process isolation while making successful serial
cohorts readiness-limited. It does not change planner behavior or establish a
score or win-rate improvement.
