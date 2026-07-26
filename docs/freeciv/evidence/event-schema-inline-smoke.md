# Event-schema inline-reference smoke

Date: 2026-07-26

Status: retained single-seed engine smoke with exact ordered-action replay.
This is local event-validation throughput evidence, not a gameplay-score,
win-rate, or statistically powered outer latency claim.

## Change

Each event-type validator previously resolved its root payload reference, and
any nested payload references, during every validation. The published payload
schema has an acyclic local-reference graph.

Payload validators now expand that graph once when each event type is first
compiled. Runtime validation still applies every envelope and payload
constraint. Public schemas and diagnostics are unchanged. Compilation rejects
unknown, external, sibling-bearing, or cyclic references rather than silently
weakening validation. Regression coverage checks all known compiled validators
for remaining references and proves that a malformed nested plan still returns
the exact prior diagnostic.

The representative pressure/operation/plan validation triplet fell from
approximately 0.694 to 0.599 ms in an isolated Python 3.8 microbenchmark
(-13.7%).

## Engine result

The fresh treatment `artifacts/freeciv/impact-event-schema-inline-20260726-a`
was compared with the same-seed
`artifacts/freeciv/impact-pressure-hash-reuse-20260726-a` control:

| Metric | Control | Treatment | Change |
|---|---:|---:|---:|
| Impact decision-event emission | 1.997 ms/turn | 1.773 ms/turn | -11.21% |
| Action-sent event emission | 0.444 ms/call | 0.394 ms/call | -11.34% |
| Action-completion event emission | 1.522 ms/call | 1.137 ms/call | -25.31% |
| Impact resolution-event emission | 0.821 ms/turn | 0.650 ms/turn | -20.85% |
| Action-refresh event emission | 0.815 ms/turn | 0.741 ms/turn | -9.16% |
| Complete impact planning | 6.628 ms/turn | 6.728 ms/turn | noise |
| Score at turn 30 | 107 | 107 | identical |
| Score margin at turn 30 | -2 | -2 | identical |
| Engine rejection rate | 0 | 0 | identical |
| Confirmation timeouts | 0 | 0 | identical |

The treatment retained the exact ordered 48-action replay and complete
`run_completed.summary`. The consistent movement across separately timed event
families supports the event-path claim. The outer planning observation is not
promoted because it moved independently within single-run noise.

## Verification

- Complete canonical-runtime repository FreeCiv lane: 364 passed.
- Focused event regression lane: 23 passed.
- Fresh treatment engine trace: 1 completed, 0 infrastructure failures.
- Treatment trace release audit: all 10 applicable top-level checks passed.
- Exact ordered canonical action comparison: identical.
- Complete `run_completed.summary` comparison: identical.
- Static whitespace checks passed.
- The repository-prescribed `just check` entry point remains unavailable because
  `just` is not installed; the complete direct FreeCiv lane above passed.
