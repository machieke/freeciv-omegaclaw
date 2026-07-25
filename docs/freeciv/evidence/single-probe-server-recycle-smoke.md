# Single-probe clean-successor recycle smoke

Date: 2026-07-25

Status: focused coverage, a direct live probe, two independent two-seed engine
treatments, exact-behavior comparison, and release validation passed. This is
operational throughput evidence, not a gameplay score or win-rate claim.

## Root cause and invariant

The clean-successor path already required both a PID distinct from the
successfully completed predecessor and an exact listening socket on the
dedicated port. Its first process-table query often returned that successor,
but the polling loop discarded the result and immediately queried the same
process table again before checking the socket.

Each Docker execution cost roughly 100--140 milliseconds on the recorded host.
The corrected path carries the first PID into the poll:

1. an absent PID still waits and retries;
2. the predecessor PID is never accepted;
3. a distinct PID is accepted only when the dedicated port is listening;
4. failed predecessors still cannot publish the clean-successor shortcut; and
5. the unconditional kill/recycle path retains its fresh-PID and listener
   checks.

The status record now separates `engine_proxy_clear_latency_ms` and
`engine_server_recycle_latency_ms` inside `engine_preflight_latency_ms`.

## Direct measurement

Against the same already-running clean successor, the exact
`_recycle_server` check fell from 394.1 to 244.8 milliseconds (-37.88%). The
proxy hard-clear measured 3.6 milliseconds and was not the preflight
bottleneck.

## Engine confirmation

Both cohorts used seeds 104729 and 104743, the serial 30-turn topology, the
expiry-aware resident-model policy, and otherwise identical configuration:

- controls:
  `artifacts/freeciv/expiry-aware-readiness-treatment-20260725` and
  `artifacts/freeciv/expiry-aware-readiness-treatment-repeat-20260725`;
- treatments:
  `artifacts/freeciv/single-probe-recycle-treatment-20260725` and
  `artifacts/freeciv/single-probe-recycle-treatment-repeat-20260725`.

| Measure | Control 1 | Treatment 1 | Control 2 | Treatment 2 |
|---|---:|---:|---:|---:|
| Clean-successor preflight | 311.0 ms | 191.0 ms (-38.61%) | 314.7 ms | 210.0 ms (-33.28%) |
| Proxy clear | not split | 1.7 ms | not split | 1.5 ms |
| Server recycle | not split | 189.2 ms | not split | 208.5 ms |
| Complete backend | 17,395.1 ms | 17,132.2 ms | 17,838.9 ms | 17,164.2 ms |

Mean clean-successor preflight fell from 312.9 to 200.5 milliseconds
(-35.93%), saving 112.4 milliseconds per later serial arm. Complete backend
time was lower in both repeats, but the isolated preflight measurement is the
appropriate claim because gameplay latency also varied.

## Behavioral acceptance

All four treatment games retained, per seed:

- exact ordered canonical action payloads relative to both controls;
- scores and margins 107/-2 and 112/-3;
- 48/70 engine actions, 18/40 planned actions, and 17/39 impact actions;
- zero rejected actions and zero infrastructure failures;
- the `kill-then-listener` first-arm boundary; and
- the `clean-successor-listener` second-arm boundary.

## Verification

- Focused recycle and backend-order lane: 3 passed.
- Four engine treatment games completed without infrastructure failures.
- The four-trace release audit passed all 13 top-level checks at
  `artifacts/freeciv/single-probe-recycle-release-audit-20260725/report.json`.
- Complete repository FreeCiv lane: 351 passed.
