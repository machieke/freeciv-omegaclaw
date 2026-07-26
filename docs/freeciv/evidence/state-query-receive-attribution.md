# State-query receive attribution

Date: 2026-07-26

Status: behavior-neutral client receive diagnostics and a fresh exact-replay
two-seed engine cohort passed. This is bottleneck attribution, not a
gameplay-score, win-rate, or speedup claim.

## Measurement

The shared state receiver measures the UTF-8 bytes and `json.loads` time for
messages it already receives. No request, response, wait, or state payload is
added. The harness retains:

- the existing query-minus-server-preparation delivery residual;
- client JSON decode time;
- delivery excluding JSON decode; and
- received wire bytes per state gate.

Byte metrics use the event unit `bytes`; timing remains in milliseconds.

## Engine result

`artifacts/freeciv/receive-attribution-20260726-a` ran seeds 104729 and
104743 serially for 30 turns with local WebSocket compression disabled and
`qwen3-coder-next:latest`.

| Per state gate | Accepted-action refresh | Turn boundary |
|---|---:|---:|
| Query count | 2.081 | 1.000 |
| Received bytes | 46,786 | 117,593 |
| Delivery residual | 18.131 ms | 11.263 ms |
| JSON decode | 1.445 ms | 5.283 ms |
| Delivery excluding decode | 16.686 ms | 5.980 ms |
| Complete state latency | 84.287 ms | 146.042 ms |

The boundary result makes payload compaction the next safe target: the single
response is approximately 118 KB, and decode alone costs approximately
5.3 ms. The action path is smaller but pays two request/response dispatches;
its remaining non-decode residual is therefore not primarily a JSON-parser
problem.

## Behavioral acceptance

Relative to
`artifacts/freeciv/no-websocket-compression-20260726-b`, both games retained:

- exact ordered canonical action payloads;
- scores and margins 107/-2 and 112/-3;
- zero rejected actions and zero model fallback; and
- unchanged v4/v5 stability behavior.

## Verification

- Complete repository FreeCiv lane: 355 passed.
- Receive and state-gate focused lane: 14 passed.
- Two engine games completed without infrastructure failures.
- Both traces passed all 11 applicable release-audit checks.
- Static compilation and whitespace checks passed.
