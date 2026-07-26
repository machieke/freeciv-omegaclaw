# State-query timing attribution

Date: 2026-07-26

Status: behavior-neutral protocol diagnostics, focused proxy coverage, a fresh
two-seed engine cohort, exact replay comparison, and release validation passed.
This is bottleneck attribution, not a gameplay-score, win-rate, or performance
improvement claim.

## Measurement boundary

The v5 proxy response now carries an optional top-level `server_timing` object.
It records:

1. source wait, including the new-turn signal and bounded source-sequence wait;
2. authoritative projection construction under the packet lock;
3. the exact-revision quiet wait;
4. projection attempts after packet churn; and
5. total handler time before JSON serialization.

The client admits only finite, non-negative values for declared fields. The
diagnostic is outside response `data`, is not parsed into
`AuthoritativeSnapshot`, and is absent from the decision fingerprint. The
harness subtracts server preparation from observed query latency to report
delivery overhead, which includes JSON serialization, WebSocket transfer, and
client scheduling.

The promoted external patch is pinned at SHA-256
`72813abbb7c45be3cc357592dd0bba33ca3537178cd7c34482f5c5033c5e5dd5`.

## Engine result

`artifacts/freeciv/timing-attribution-20260726-a` ran seeds 104729 and
104743 serially for 30 turns with `qwen3-coder-next:latest`.

| Per state gate | Accepted-action refresh | Turn boundary |
|---|---:|---:|
| Complete state latency | 89.712 ms | 148.153 ms |
| Query latency | 84.616 ms | 141.704 ms |
| Query count | 2.118 | 1.000 |
| Source/turn wait | 49.211 ms | 55.894 ms |
| Exact-revision quiet wait | 0.000 ms | 51.131 ms |
| Projection construction | 6.794 ms | 10.085 ms |
| Handler preparation | 61.713 ms | 122.851 ms |
| Serialization/delivery/scheduling residual | 22.903 ms | 18.854 ms |
| DTO parse | 4.663 ms | 5.535 ms |
| Projection attempts | 1.143 | 1.207 |

Action refresh uses the v4 conditional acknowledgement, so its required
50 ms stability interval is recorded as source wait in its second query.
Turn boundaries use one v5 settled response, so the same interval is recorded
as quiet wait.

The result rules out projection construction as the dominant cost. Required
correctness waits account for approximately 49 ms of an action refresh and
107 ms of a boundary. The largest safely optimizable remainder is response
serialization, compression, delivery, and scheduling at approximately
19--23 ms per state gate. Projection remains a secondary 7--10 ms target.

## Behavioral acceptance

Relative to
`artifacts/freeciv/proxy-success-log-final-confirmation-20260725`, both games
retained:

- exact ordered canonical action payloads;
- scores and margins 107/-2 and 112/-3;
- 48/70 total engine actions and 18/40 planned actions;
- one/two completed settlements;
- zero rejected actions and zero model fallback; and
- the unchanged 50 ms v4/v5 source-stability policies.

## Verification

- Complete repository FreeCiv lane: 354 passed.
- Client turn-cycle lane: 12 passed.
- Patched authoritative proxy contract: 25 passed.
- Focused patched-proxy lane: 278 passed, 4 skipped.
- Two engine games completed without infrastructure failures.
- Both trace release audits passed all 11 applicable top-level checks.
- Patch reverse-application and exact SHA-256 checks passed.
- The state extractor remained healthy after the proxy restart.

The repository-wide lane initially found six mock-call compatibility failures
because diagnostics were passed even when collection was inactive. The client
now preserves the legacy call shape unless a diagnostics dictionary is
supplied; all six focused regressions and the corrected complete lane pass.
