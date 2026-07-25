# Scheduler observer-boundary smoke

Date: 2026-07-25

Status: focused boundary tests, two independent two-seed engine cohorts, and
four-trace release audit passed. This is truth-boundary and operational
throughput evidence, not a gameplay score or win-rate claim.

## Root cause and change

The harness queried observer-global state after every new player turn. That
state serves two purposes:

- the plain-condition scout driver reads global enemy unit positions;
- initial paired identity/fidelity and final fixed-horizon scoring read
  authoritative player scores.

Scheduler-enabled conditions never invoke the scout driver. Their
`GroundedImpactPlanner` candidates use only the packet-visible authoritative
player snapshot, so 29 inter-turn observer queries in a 30-turn game had no
consumer.

The harness now keeps per-turn queries for plain conditions but limits
scheduler games to:

1. initial opponent/score identity and fidelity; and
2. authoritative post-horizon scoring.

The final query remains turn-gated and now fails closed on timeout instead of
falling back to a stale prior-turn global snapshot. The
`observer_global_state_queries` metric makes the boundary auditable.

## Engine comparison

All cohorts used the same seeds, serial topology, 30-turn horizon, resident
`qwen3-coder-next:latest` model, planner policy, turn-durable event writer, and
authoritative state/score gates:

- 31-query control:
  `artifacts/freeciv/turn-durable-events-repeat-20260725`
- two-query treatment:
  `artifacts/freeciv/scheduler-observer-boundary-smoke-20260725`
- independent treatment repeat:
  `artifacts/freeciv/scheduler-observer-boundary-repeat-20260725`

| Measure (two-seed mean) | Control | Treatment | Repeat | Control to treatment |
|---|---:|---:|---:|---:|
| Observer-global queries | 31 | 2 | 2 | -29 (-93.55%) |
| Gameplay | 20,779.5 ms | 20,304.6 ms | 20,106.2 ms | -474.9 ms (-2.29%) |
| Complete backend | 22,531.7 ms | 22,000.1 ms | 21,835.8 ms | -531.7 ms (-2.36%) |
| Mean turn loop | 553.2 ms | 533.5 ms | 534.9 ms | -19.7 ms (-3.56%) |

The repeat improved gameplay by 673.3 ms (3.24%) and backend time by 695.9 ms
(3.09%) relative to control.

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
engine actions, 40 meaningful actions, and two settlements. Each treatment
trace recorded exactly two observer-global queries.

## Verification

- Focused global-state and scheduler-boundary lane: 3 passed.
- Engine comparison: 6/6 arms completed without infrastructure failures.
- Full release audit: all checks passed for all four treatment traces,
  including the pinned external contract and every PF-PLN phase replay.

## Scope

This removes observer work that had no scheduler consumer and makes final score
failure semantics stricter. Plain scout conditions retain their required
per-turn observer refresh. The result does not alter grounded planner behavior
or establish a score or win-rate improvement.
