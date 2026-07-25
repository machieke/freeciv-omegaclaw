# Active listener server-recycle smoke

Date: 2026-07-25

Status: implementation and two-seed engine acceptance passed; operational
latency evidence only, not a gameplay or score claim.

## Change

Every engine arm retains its required fresh dedicated civserver process. The
recycle gate previously:

1. terminated the old process;
2. polled every 250 ms for a different PID;
3. slept a fixed additional 500 ms.

The accepted gate polls every 100 ms and requires both a different PID and an
exact `LISTEN` entry for the dedicated port in `/proc/net/tcp*`. It does not
open a Freeciv connection, so readiness probing cannot allocate a transient
client/player slot. The 20-second failure deadline and fresh-process isolation
boundary are unchanged.

## Isolated recycle measurement

Three serial recycles on unused dedicated port 6002 measured:

| Sample | Fixed-tail control | Active-listener treatment |
|---:|---:|---:|
| 1 | 5,914.5 ms | 5,462.5 ms |
| 2 | 5,919.3 ms | 5,450.9 ms |
| 3 | 5,950.2 ms | 5,419.0 ms |
| Mean | 5,928.0 ms | 5,444.1 ms |

The active check saved 483.9 ms per recycle (8.16%).

## Engine comparison

Both arms used the release 300 ms confirmation/50 ms stability policy, the
same patched proxy, model, serial order, 30-turn horizon, and seeds.

- Fixed-tail control:
  `artifacts/freeciv/confirmation-timeout-300ms-live-smoke-20260725`
- Active-listener treatment:
  `artifacts/freeciv/active-listener-recycle-smoke-20260725`

| Seed | Preflight control | Preflight treatment | Backend control | Backend treatment |
|---:|---:|---:|---:|---:|
| 104729 | 5,936.3 ms | 5,437.7 ms | 42,790.9 ms | 42,430.3 ms |
| 104743 | 5,436.7 ms | 4,933.5 ms | 39,858.2 ms | 39,246.6 ms |
| Mean | 5,686.5 ms | 5,185.6 ms | 41,324.5 ms | 40,838.5 ms |

Mean preflight fell by 500.9 ms (8.81%) and mean complete backend time by
486.1 ms (1.18%). Mean gameplay time changed by only -42.3 ms (-0.12%).

## Behavioral acceptance

For each seed, control and treatment had identical:

- initial state fingerprint, authoritative state hash, and legal-action digest;
- canonical action sequence;
- fixed-horizon score and margin;
- engine-action count;
- deferred/recovered confirmation counts;
- zero expirations and zero rejected actions.

The focused recycle and backend-order tests passed before the engine run, and
both treatment arms completed without infrastructure failure.

## Scope

This is a deterministic operational boundary improvement with two engine
confirmation seeds. It does not alter planner behavior and does not support a
score, win-rate, or population-wide gameplay-performance claim.
