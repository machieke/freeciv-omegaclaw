# Unified server inspection smoke

Date: 2026-07-25

Status: focused fail-closed coverage, a direct live probe, two independent
two-seed engine treatments, exact-behavior comparison, and release validation
passed. This is operational throughput evidence, not a gameplay score or
win-rate claim.

## Root cause and invariant

After the duplicate process-table query was removed, each successful server
poll still used one Docker execution to find the exact process and another to
read the TCP listener tables. Docker startup dominated both checks.

The corrected poll executes one Python inspection inside the container. It:

1. scans `/proc/*/cmdline` for the exact `freeciv-web` executable and
   separate `--port` argument;
2. reads both `/proc/net/tcp` and `/proc/net/tcp6`;
3. reports a typed PID/listening snapshot as JSON;
4. rejects malformed or incomplete inspection output;
5. retains the distinct-PID and listening requirements; and
6. opens no Freeciv protocol connection, so readiness inspection cannot
   allocate a transient player slot.

The clean-successor path still requires a recorded successfully completed
predecessor. The forced recycle path still kills the old PID, waits at least
one poll interval, and requires a different listening PID.

## Direct measurement

Against the same already-running clean successor, `_recycle_server` fell from
244.8 to 132.0 milliseconds (-46.09%). Five consecutive container snapshots
before integration measured 127.6--151.6 milliseconds each and all returned
the exact PID and listener.

## Engine confirmation

Both cohorts used seeds 104729 and 104743, the serial 30-turn topology,
expiry-aware model residency, and otherwise identical configuration:

- controls:
  `artifacts/freeciv/single-probe-recycle-treatment-20260725` and
  `artifacts/freeciv/single-probe-recycle-treatment-repeat-20260725`;
- treatments:
  `artifacts/freeciv/unified-recycle-inspection-treatment-20260725` and
  `artifacts/freeciv/unified-recycle-inspection-treatment-repeat-20260725`.

| Boundary | Control 1 | Treatment 1 | Control 2 | Treatment 2 |
|---|---:|---:|---:|---:|
| Forced kill/recycle preflight | 552.3 ms | 496.0 ms (-10.18%) | 597.1 ms | 506.5 ms (-15.18%) |
| Clean-successor preflight | 191.0 ms | 140.0 ms (-26.66%) | 210.0 ms | 120.2 ms (-42.77%) |
| Clean-successor recycle component | 189.2 ms | 137.5 ms | 208.5 ms | 117.5 ms |

Mean forced recycle preflight fell from 574.7 to 501.3 milliseconds
(-12.78%), while mean clean-successor preflight fell from 200.5 to 130.1
milliseconds (-35.10%). Complete backend comparisons are intentionally omitted:
the server-isolation timing is directly measured, while gameplay latency varies
independently.

## Behavioral acceptance

All four treatment games retained, per seed:

- exact ordered canonical action payloads relative to both controls;
- scores and margins 107/-2 and 112/-3;
- 48/70 engine actions, 18/40 planned actions, and 17/39 impact actions;
- zero rejected actions and zero infrastructure failures;
- the `kill-then-listener` first-arm boundary; and
- the `clean-successor-listener` second-arm boundary.

## Verification

- Focused recycle, malformed-inspection, and backend-order lane: 5 passed.
- Four engine treatment games completed without infrastructure failures.
- The four-trace release audit passed all 13 top-level checks at
  `artifacts/freeciv/unified-recycle-inspection-release-audit-20260725/report.json`.
- Complete repository FreeCiv lane: 353 passed.
