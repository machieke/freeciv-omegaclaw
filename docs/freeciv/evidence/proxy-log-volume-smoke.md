# Proxy hot-path logging smoke

Date: 2026-07-25

Status: proxy regression coverage, two independent two-seed engine treatments,
an exact-final-pin confirmation, exact-behavior comparison, and release
validation passed. This is operational throughput evidence, not a gameplay
score or win-rate claim.

## Root cause and invariant

The proxy logger admitted DEBUG records in the release process and emitted
roughly a dozen payload-shape, normalization, sanitization, validation, and
full-state-summary records for every accepted action and authoritative query.
Every record was synchronously propagated to Docker stdout, and the same logger
also had a DEBUG file handler. Logging therefore sat directly on both the
action-acknowledgement and state-refresh critical paths.

The corrected policy:

1. defaults `freeciv-proxy` to `INFO`, with an explicit
   `FREECIV_PROXY_LOG_LEVEL` override;
2. moves action payload and transformation details to DEBUG;
3. moves the multiline successful-state payload summary to DEBUG;
4. retains one accepted-action INFO summary and state-extraction timing;
5. retains all rejection, security, warning, and error records; and
6. changes no action, state, stability, timeout, or planner protocol.

The proxy regression fixture now also requires `end_turn` to remain the sole
legal fallback when unit, city, and research categories have no action.

## Attribution

The preceding telemetry-only controls were:

- `artifacts/freeciv/action-refresh-attribution-treatment-20260725`; and
- `artifacts/freeciv/action-refresh-attribution-treatment-repeat-20260725`.

They showed that an accepted-action refresh spent 86.1--89.6 ms in
authoritative queries, 4.5--5.9 ms in DTO parsing, and requested 55.6--61.1 ms
of quiet/stability waiting. Parsing was therefore not the meaningful target.
The proxy trace separately showed 11--32 ms action acknowledgements surrounded
by repeated synchronous action diagnostics.

The logging treatments were:

- `artifacts/freeciv/proxy-log-volume-treatment-20260725`; and
- `artifacts/freeciv/proxy-log-volume-treatment-repeat-20260725`.

Both used seeds 104729 and 104743, the serial 30-turn topology,
`qwen3-coder-next:latest`, and otherwise identical gameplay configuration.

| Measure | Control mean | Treatment mean | Change |
|---|---:|---:|---:|
| Loop latency | 466.513 ms/turn | 421.220 ms/turn | -9.71% |
| Action phase | 143.613 ms/turn | 136.935 ms/turn | -4.65% |
| End-turn submission | 15.620 ms | 13.082 ms | -16.25% |
| Boundary state | 187.499 ms | 150.648 ms | -19.65% |
| Accepted-action refresh | 93.822 ms | 89.425 ms | -4.69% |
| Accepted-action query | 88.099 ms | 84.157 ms | -4.47% |
| Non-end action acknowledgement | 13.491 ms | 10.808 ms | -19.88% |
| End-turn acknowledgement | 14.317 ms | 11.910 ms | -16.81% |

The promoted patch digest is
`8ff1e005735076502860226a051178c23d515d6f0c343f7291d1f68f05d1500f`.
The two measurement treatments used the runtime-identical preceding digest;
the promoted digest adds only the logging-level contract test. An additional
exact-pin engine confirmation at
`artifacts/freeciv/proxy-log-volume-final-confirmation-20260725` completed both
seeds with loop latencies of 445.095 and 386.155 ms/turn and boundary-state
latencies of 141.082 and 156.490 ms.

## Behavioral acceptance

All six treatment games retained, per seed:

- exact ordered canonical action payloads relative to the controls;
- scores and margins 107/-2 and 112/-3;
- 48 and 70 engine actions;
- zero rejected actions and zero model fallback; and
- the same fixed 50 ms stability policy and authoritative state contract.

## Verification

- Patched proxy lane: 277 passed, 4 skipped.
- Six engine treatment games completed without infrastructure failures.
- The final four-trace release audit passed all 13 top-level checks at
  `artifacts/freeciv/proxy-log-volume-release-audit-20260725/report.json`.
- The promoted patch passed the complete 353-test repository FreeCiv lane.
