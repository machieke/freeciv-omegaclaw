# Engine WebSocket compression opt-out smoke

Date: 2026-07-26

Status: two independent two-seed engine treatments, exact-behavior replay, and
release validation passed. This is a local engine-harness throughput result,
not a gameplay-score or win-rate claim.

## Root cause and scope

The engine-live proxy and benchmark client run on the same host, but their
WebSocket negotiated per-message deflate. The proxy configures compression at
level 9. State-query attribution measured approximately 19--23 ms per state
gate outside handler preparation, while authoritative projection itself cost
only 7--10 ms.

The engine-live connection now disables compression by default. JSON,
authentication, state, stability, action, and planner semantics are unchanged.
Remote harnesses can set `FREECIV_PROXY_WEBSOCKET_COMPRESSION=true` to restore
`deflate` when bandwidth savings outweigh local compression work.

## Engine comparison

All cohorts used seeds 104729 and 104743, a serial 30-turn engine topology,
`qwen3-coder-next:latest`, and the same pinned proxy and planner configuration:

- control: `artifacts/freeciv/timing-attribution-20260726-a`;
- treatments: `artifacts/freeciv/no-websocket-compression-20260726-a` and
  `artifacts/freeciv/no-websocket-compression-20260726-b`.

The treatment column is the mean of the two independent treatment cohorts.

| Measure | Control | Treatment mean | Change |
|---|---:|---:|---:|
| Accepted-action delivery residual | 22.903 ms | 18.456 ms | -19.41% |
| Accepted-action query | 84.616 ms | 79.215 ms | -6.38% |
| Accepted-action refresh | 89.712 ms | 83.941 ms | -6.43% |
| Boundary delivery residual | 18.854 ms | 12.103 ms | -35.81% |
| Boundary-state query | 141.704 ms | 136.968 ms | -3.34% |
| Boundary state | 148.153 ms | 144.211 ms | -2.66% |
| Complete action phase | 137.056 ms/turn | 131.566 ms/turn | -4.01% |
| Mean turn loop | 416.831 ms/turn | 408.575 ms/turn | -1.98% |
| End-turn acknowledgement | 11.806 ms | 12.168 ms | +3.06% |

The small end-turn response did not benefit from removing compression, but
the state-heavy action phase improved in both treatment cohorts and dominates
that local regression.

## Behavioral acceptance

All four treatment games retained, relative to the instrumented control:

- exact ordered canonical action payloads;
- scores and margins 107/-2 and 112/-3;
- 48/70 total engine actions and 18/40 planned actions;
- one/two completed settlements;
- zero rejected actions and zero model fallback; and
- unchanged 50 ms v4/v5 stability policies and 100% boundary settled markers.

## Verification

- Complete repository FreeCiv lane: 355 passed.
- Compression default/remote-opt-in contract: 2 focused tests passed.
- Both two-game treatment cohorts completed without infrastructure failures.
- Four treatment traces passed all 13 top-level release-audit checks.
- The exact ordered action comparison was empty for both seeds in both
  treatments.
- Static compilation and whitespace checks passed.
