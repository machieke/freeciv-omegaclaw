# Expiry-aware Ollama readiness smoke

Date: 2026-07-25

Status: focused coverage, two independent two-seed engine treatments, exact
behavior comparison, and release validation passed. This is an operational
efficiency result, not a gameplay score or win-rate claim.

## Root cause and contract

After the first complete native chat validated the configured
`qwen3-coder-next:latest` endpoint, every later arm still made an empty
`/api/generate` request to renew the 30-minute keep-alive. On the recorded host,
`/api/ps` took less than one millisecond while that redundant refresh took about
384 milliseconds, even when the reported resident expiry remained almost 30
minutes away.

The versioned `chat-once-expiry-aware-resident-v2` policy keeps the original
complete-chat and process-lock guarantees. For a previously verified exact
endpoint/model/think tuple, it:

1. obtains the exact configured model row from `/api/ps`;
2. parses Ollama's timezone-qualified nanosecond `expires_at` value
   conservatively;
3. reuses residency only when at least the configured 300-second safety floor
   remains;
4. sends the former zero-token refresh when expiry is missing, malformed, or
   near; and
5. falls back to complete chat validation if that refresh fails.

The selected method, latency, reuse flag, and remaining residency seconds are
persisted in each engine arm's `status.json`.

## Engine confirmation

Both cohorts used seeds 104729 and 104743, a serial 30-turn engine topology,
the pinned proxy patch, and otherwise identical configuration:

- controls:
  `artifacts/freeciv/settled-turn-boundary-pinned-treatment-20260725` and
  `artifacts/freeciv/settled-turn-boundary-pinned-treatment-repeat-20260725`;
- treatments:
  `artifacts/freeciv/expiry-aware-readiness-treatment-20260725` and
  `artifacts/freeciv/expiry-aware-readiness-treatment-repeat-20260725`.

| Measure | Control 1 | Treatment 1 | Control 2 | Treatment 2 |
|---|---:|---:|---:|---:|
| First-arm complete chat | 2,175.0 ms | 2,216.6 ms | 2,130.0 ms | 2,156.4 ms |
| Later-arm readiness | 362.4 ms | 1.8 ms (-99.51%) | 418.9 ms | 2.5 ms (-99.39%) |
| Later-arm complete backend | 17,606.8 ms | 17,395.1 ms (-1.20%) | 17,959.0 ms | 17,838.9 ms (-0.67%) |
| Later-arm reported residency | refreshed | 1,789.6 s | refreshed | 1,789.4 s |

The mean later-arm readiness cost fell from 390.6 to 2.2 milliseconds
(-99.45%). Complete backend time also decreased in both repeats, although
gameplay timing noise makes the isolated readiness measurement the appropriate
claim.

## Behavioral acceptance

All four treatment games retained, per seed:

- exact ordered canonical action payloads relative to both controls;
- scores and margins 107/-2 and 112/-3;
- 48/70 engine actions, 18/40 planned actions, and 17/39 impact actions;
- zero rejected actions and zero infrastructure failures;
- one boundary state query per turn with the settled v5 contract; and
- configuration hash
  `08ffc6b811480d844cc8f446476b5d31c6da8c64b8a8196622afc720ef426fe5`.

## Verification

- Focused readiness and configuration lane: 18 passed.
- Four engine treatment games completed without infrastructure failures.
- The four-trace release audit passed all 13 top-level checks at
  `artifacts/freeciv/expiry-aware-readiness-release-audit-20260725/report.json`.
- Complete repository FreeCiv lane: 351 passed.
