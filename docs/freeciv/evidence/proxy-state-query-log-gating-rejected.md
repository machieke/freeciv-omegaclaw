# Proxy state-query log gating experiment

Date: 2026-07-25

Status: rejected and reverted after two independent exact-behavior engine
cohorts. No state-query latency improvement is claimed.

## Experiment

The experiment wired `log_state_queries=false` into four INFO records on the
authoritative-query path: query received, state build started, turn wait
started, and turn wait completed. Timeout warnings and all error paths remained
unconditional. The experimental patch digest was
`644119540b409c38c1978488cad9405ce524add7c838bf4e280ec10138ff70c0`.

Both comparisons used seeds 104729 and 104743, the serial 30-turn topology,
`qwen3-coder-next:latest`, and otherwise identical gameplay configuration:

- controls:
  `artifacts/freeciv/proxy-success-log-treatment-20260725` and
  `artifacts/freeciv/proxy-success-log-treatment-repeat-20260725`;
- experiments:
  `artifacts/freeciv/proxy-state-query-log-treatment-20260725` and
  `artifacts/freeciv/proxy-state-query-log-treatment-repeat-20260725`.

| Measure | Control mean | Experiment mean | Change |
|---|---:|---:|---:|
| Boundary-state query | 143.884 ms | 147.201 ms | +2.31% |
| Boundary state | 150.780 ms | 154.175 ms | +2.25% |
| Accepted-action query | 84.302 ms | 83.683 ms | -0.73% |
| Accepted-action refresh | 89.066 ms | 89.067 ms | +0.00% |
| Loop latency | 419.716 ms/turn | 423.115 ms/turn | +0.81% |

All four experimental games retained exact ordered canonical actions, scores
107/112, margins -2/-3, and zero rejection or model fallback. Post-restart logs
confirmed that the four intended records were absent. The state-boundary
acceptance criterion nevertheless failed in both pooled repeats, so the handler
gating was reverted.

The retained release configuration declares state-query lifecycle logging
enabled, matching the retained handler behavior. The promoted patch digest is
`aec725fae2618872023fc0eb0baea4c23323e5d46e037d470f33ca10e2eb71a5`;
it otherwise retains the accepted action-path logging optimization.
