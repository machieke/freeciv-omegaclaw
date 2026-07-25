# Settled turn-boundary projection smoke

Date: 2026-07-25

Status: focused host/proxy coverage, two independent two-seed engine
treatments, exact-behavior comparison, and release validation passed. This is
correctness and engineering-latency evidence, not a gameplay score or win-rate
claim.

## Root cause and v5 contract

The v4 turn boundary used one full atomic projection followed by a compact
`state_unchanged` request after the required 50 ms quiet interval. That removed
the second projection build and transfer, but still paid two authenticated
WebSocket request paths per boundary.

The v5 request adds bounded `settle_quiet_ms`. The proxy:

1. waits for a source sequence newer than the caller's retained snapshot;
2. builds the full projection under the packet/projection lock;
3. waits for that exact projected revision to remain unchanged for 50 ms;
4. rebuilds after any changed packet revision; and
5. marks the response only after rechecking the exact source sequence under
   the same lock.

The harness accepts the marker only when its policy, source sequence, and
interval match the returned projection and current stability requirement.
Unmarked responses fall back to the v4 sample path.

## Rejected action-refresh scope

An initial trial enabled v5 for both turn boundaries and same-turn action
effect confirmation. One of four games produced two deferred confirmations
and changed the ordering of two same-turn actions even though final scores
matched. That scope was rejected. Delayed action-effect packets need the
longer post-projection v4 observation window, so the released harness uses v5
only when `require_decision_ready` identifies a new-turn boundary. Focused
tests fail if an ordinary action refresh sends `settle_quiet_ms`.

## Engine comparison

All cohorts used seeds 104729 and 104743, a serial 30-turn engine topology,
the resident `qwen3-coder-next:latest` model, and identical planner, score,
observer, action-confirmation, and durability configuration:

- controls:
  `artifacts/freeciv/pln-cache-bypass-treatment-20260725` and
  `artifacts/freeciv/pln-cache-bypass-treatment-repeat-20260725`;
- treatments:
  `artifacts/freeciv/settled-turn-boundary-pinned-treatment-20260725` and
  `artifacts/freeciv/settled-turn-boundary-pinned-treatment-repeat-20260725`.

| Measure | Control 1 | Treatment 1 | Control 2 | Treatment 2 |
|---|---:|---:|---:|---:|
| Boundary state queries | 2.000 | 1.000 (-50.00%) | 2.000 | 1.000 (-50.00%) |
| Boundary settled response rate | n/a | 1.000 | n/a | 1.000 |
| Required quiet interval | 50.0 ms | 50.0 ms | 50.0 ms | 50.0 ms |
| Boundary state gate | 195.3 ms | 188.6 ms (-3.44%) | 197.9 ms | 188.1 ms (-4.93%) |
| Complete boundary | 206.5 ms | 197.3 ms (-4.43%) | 209.3 ms | 196.8 ms (-5.98%) |
| Complete full turn | 274.8 ms | 270.1 ms (-1.70%) | 274.3 ms | 270.0 ms (-1.57%) |
| Mean turn loop | 481.5 ms | 468.2 ms (-2.77%) | 484.0 ms | 467.3 ms (-3.44%) |
| Gameplay | 18,728.0 ms | 18,062.7 ms (-3.55%) | 18,701.7 ms | 18,292.2 ms (-2.19%) |
| Complete backend | 20,455.6 ms | 19,775.0 ms (-3.33%) | 20,381.5 ms | 20,005.6 ms (-1.84%) |

The gain comes from removing one boundary request/response dispatch and its
client processing. It does not remove or shorten the stability wait.

## Behavioral acceptance

Both accepted treatments retained, per seed:

- identical initial authoritative fingerprints;
- exact canonical action hashes and ordered actions relative to both controls;
- scores and margins 107/-2 and 112/-3;
- 48/70 engine actions, 18/40 planned actions, and 17/39 impact actions;
- one/two settlement completions;
- zero rejected actions and zero deferred, recovered, expired, pending, or
  timed-out confirmations;
- one boundary state query per turn and a 100% accepted settled-marker rate;
- no v5 markers on action refreshes.

## Verification

- Complete repository FreeCiv lane: 348 passed.
- Focused patched-proxy lane: 118 passed, 4 skipped.
- Publite2 regression lane: 2 passed.
- Four treatment games completed without infrastructure failures.
- The four-trace release audit passed all 13 top-level checks.
- Clean patch reconstruction and reverse-application checks passed at digest
  `3722fd29b2bcae1f979426e6ff800fb2e54d01717bd2304b2063f5115234e1b2`.
