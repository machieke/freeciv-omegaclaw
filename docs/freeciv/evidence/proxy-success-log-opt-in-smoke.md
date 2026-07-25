# Proxy success-log opt-in smoke

Date: 2026-07-25

Status: proxy regression coverage, two independent two-seed engine treatments,
exact-behavior comparison, and release validation passed. This is an
action-path throughput result, not a state-query, gameplay-score, or win-rate
claim.

## Root cause and invariant

After verbose payload diagnostics were moved behind DEBUG, the proxy still
performed synchronous INFO writes for every accepted action, every successful
security action event, every authoritative extraction, and two additional
success records at each end-turn boundary. The existing `log_actions`,
`log_state_queries`, and `log_performance` configuration fields were not used by
those hot paths.

The release configuration now makes successful action, state-query, and
performance logging opt-in. The implementation:

1. checks `log_actions` once on each accepted action;
2. suppresses accepted-action, executed-action, turn-ended, and rate-reset
   success records when it is false;
3. moves successful extraction timing to DEBUG;
4. leaves rejection, rate-limit, security-warning, warning, and error records
   unconditional;
5. retains lifecycle and authentication INFO records; and
6. changes no action, state, stability, timeout, rate-limit, or planner
   behavior.

The pinned patch digest is
`9ab6fbae638fd77668e04d5cafb2031e73f490aea066f181b5a25f98068081cd`.
A proxy contract test fixes all three successful hot-path logging flags to
false for the release configuration.

## Engine confirmation

Both comparisons used seeds 104729 and 104743, the serial 30-turn topology,
`qwen3-coder-next:latest`, and otherwise identical gameplay configuration:

- controls:
  `artifacts/freeciv/proxy-log-volume-treatment-20260725` and
  `artifacts/freeciv/proxy-log-volume-treatment-repeat-20260725`;
- treatments:
  `artifacts/freeciv/proxy-success-log-treatment-20260725` and
  `artifacts/freeciv/proxy-success-log-treatment-repeat-20260725`.

| Measure | Control mean | Treatment mean | Change |
|---|---:|---:|---:|
| Non-end action acknowledgement | 10.808 ms | 10.087 ms | -6.67% |
| End-turn acknowledgement | 11.910 ms | 11.276 ms | -5.32% |
| End-turn submission metric | 13.082 ms | 12.394 ms | -5.26% |
| Action phase | 136.935 ms/turn | 135.423 ms/turn | -1.10% |
| Accepted-action refresh | 89.425 ms | 89.066 ms | -0.40% |
| Loop latency | 421.220 ms/turn | 419.716 ms/turn | -0.36% |
| Boundary state | 150.648 ms | 150.780 ms | +0.09% |

Boundary-state and authoritative-query timing were flat within engine variance;
no state-query speedup is claimed. The accepted result is the direct,
repeatable action-acknowledgement reduction and deterministic removal of unused
synchronous writes.

## Behavioral acceptance

All four treatment games retained, per seed:

- exact ordered canonical action payloads relative to both controls;
- scores and margins 107/-2 and 112/-3;
- 48 and 70 engine actions;
- zero rejected actions and zero model fallback;
- no suppressed rejection or security-warning record; and
- the same fixed 50 ms stability and authoritative-state contracts.

## Verification

- Patched proxy lane: 278 passed, 4 skipped.
- Four engine treatment games completed without infrastructure failures.
- Post-restart logs contained no accepted-action, action-executed,
  extraction-success, turn-ended, or rate-reset success records.
- The four-trace release audit passed all 13 top-level checks at
  `artifacts/freeciv/proxy-success-log-release-audit-20260725/report.json`.
