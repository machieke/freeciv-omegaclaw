# Invalid-action wire filtering experiment

Date: 2026-07-26

Status: rejected and reverted after two independent exact-behavior engine
cohorts. No state-query or loop-latency speedup is claimed.

## Experiment

The experimental PLN projection omitted action advertisements explicitly
marked `is_valid=false`. The authoritative DTO and every live selector already
reject those rows, so the canonical executable action set was unchanged. The
temporary patch digest was
`260c126ede8e24a90114c107b1f6d33d2f4eb972e82f586c1bd5065b8d747274`.

All cohorts used seeds 104729 and 104743, the serial 30-turn topology,
`qwen3-coder-next:latest`, and local WebSocket compression disabled:

- control: `artifacts/freeciv/receive-attribution-20260726-a`;
- experiments: `artifacts/freeciv/valid-actions-only-20260726-a` and
  `artifacts/freeciv/valid-actions-only-20260726-b`.

The treatment column is the mean of both experimental cohorts.

| Measure | Control | Treatment mean | Change |
|---|---:|---:|---:|
| Accepted-action received bytes | 46,786 | 44,291 | -5.33% |
| Accepted-action JSON decode | 1.445 ms | 1.422 ms | -1.60% |
| Accepted-action delivery | 18.131 ms | 18.604 ms | +2.60% |
| Accepted-action refresh | 84.287 ms | 85.203 ms | +1.09% |
| Boundary received bytes | 117,593 | 113,361 | -3.60% |
| Boundary JSON decode | 5.283 ms | 5.554 ms | +5.13% |
| Boundary delivery | 11.263 ms | 12.185 ms | +8.17% |
| Boundary state | 146.042 ms | 144.165 ms | -1.29% |
| Complete action phase | 131.393 ms/turn | 131.303 ms/turn | -0.07% |
| Mean turn loop | 408.916 ms/turn | 408.771 ms/turn | -0.04% |

Filtering produced a modest deterministic byte reduction, but its end-to-end
action-phase and loop effects were flat while delivery regressed. It was
therefore reverted rather than adding an alternate wire catalog with no
measurable throughput benefit.

All four experimental games retained exact ordered canonical actions, scores
107/112, margins -2/-3, zero rejected actions, zero model fallback, and the
unchanged v4/v5 stability contract.

The promoted patch remains
`72813abbb7c45be3cc357592dd0bba33ca3537178cd7c34482f5c5033c5e5dd5`.
