# Compact state JSON experiment

Date: 2026-07-26

Status: rejected and reverted after two independent exact-behavior engine
cohorts. No serialization or delivery speedup is claimed.

## Experiment

The experimental proxy encoded full, cached, and unchanged state-query
responses with `json.dumps(..., separators=(',', ':'))`. This removed optional
JSON whitespace without changing parsed objects, key order, values, stability
markers, or planner inputs. Its temporary patch digest was
`c891ebde451ed08cbdab89f1e05730d2a6cc2e2c8710f9d89d5ef6ffead9dd6e`.

All cohorts used seeds 104729 and 104743, a serial 30-turn topology,
`qwen3-coder-next:latest`, and local WebSocket compression disabled:

- control: `artifacts/freeciv/receive-attribution-20260726-a`;
- experiments: `artifacts/freeciv/compact-state-json-20260726-a` and
  `artifacts/freeciv/compact-state-json-20260726-b`.

The treatment column is the mean of both independent experimental cohorts.

| Measure | Control | Treatment mean | Change |
|---|---:|---:|---:|
| Accepted-action received bytes | 46,786 | 43,432 | -7.17% |
| Accepted-action JSON decode | 1.445 ms | 1.518 ms | +5.01% |
| Accepted-action delivery | 18.131 ms | 18.634 ms | +2.77% |
| Accepted-action refresh | 84.287 ms | 85.575 ms | +1.53% |
| Boundary received bytes | 117,593 | 112,931 | -3.96% |
| Boundary JSON decode | 5.283 ms | 5.195 ms | -1.67% |
| Boundary delivery | 11.263 ms | 11.905 ms | +5.69% |
| Boundary state | 146.042 ms | 147.284 ms | +0.85% |
| Mean turn loop | 408.916 ms/turn | 413.996 ms/turn | +1.24% |

The byte reduction was deterministic, but it did not improve decode, delivery,
or end-to-end latency. The serializer option was therefore reverted rather
than accepting a bandwidth-only tradeoff in the local engine benchmark.

All four experimental games retained exact ordered canonical actions, scores
107/112, margins -2/-3, zero rejected actions, zero model fallback, and the
unchanged stability contract.

The promoted patch remains
`72813abbb7c45be3cc357592dd0bba33ca3537178cd7c34482f5c5033c5e5dd5`.
