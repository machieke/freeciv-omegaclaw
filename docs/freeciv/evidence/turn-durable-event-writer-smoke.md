# Turn-durable event-writer smoke

Date: 2026-07-25

Status: writer and harness regressions, two independent two-seed engine
cohorts, and four-trace release audit passed. This is operational throughput
evidence, not a gameplay score or win-rate claim.

## Root cause and change

The engine writer emitted every event as one validated atomic append and then
opened, fsynced, and closed the JSONL file. The accepted smoke traces contain
758 and 941 events, making per-record stable-storage barriers part of the
timed planner loop.

`EventWriter` now supports an explicit `turn` sync mode while preserving
`event` as the default. Engine-live selects turn mode and retains:

- schema validation before every write;
- one complete `O_APPEND` write per JSONL record;
- immediate file and live-tail visibility;
- an explicit sync after each completed turn's full-loop metric;
- a transition-time sync guard if a caller omitted the explicit checkpoint;
- a forced sync for `run_completed`.

Thus a process interruption can expose only complete lines, every completed
game turn is forced to stable storage before the harness waits for its
successor, and the final metrics/completion record are durable before return.

## Isolated persistence benchmark

Five local 1,001-record samples compared the unchanged event mode with turn
mode over 30 checkpoints:

| Mode | Mean total | Mean per record |
|---|---:|---:|
| Per-event fsync | 3,181.6 ms | 3.178 ms |
| Turn-level fsync | 372.6 ms | 0.372 ms |

The isolated reduction was 2,809.0 ms (88.29%). This benchmark measures local
storage mechanics only; the engine comparison below is the accepted
end-to-end evidence.

## Engine comparison

All cohorts used the same seeds, serial topology, 30-turn horizon, resident
`qwen3-coder-next:latest` model, planner policy, clean-successor recycle, and
authoritative state/score gates:

- per-event control:
  `artifacts/freeciv/clean-successor-recycle-repeat-20260725`
- turn-durable treatment:
  `artifacts/freeciv/turn-durable-events-smoke-20260725`
- independent treatment repeat:
  `artifacts/freeciv/turn-durable-events-repeat-20260725`

| Measure (two-seed mean) | Control | Treatment | Repeat | Control to treatment |
|---|---:|---:|---:|---:|
| Gameplay | 22,897.8 ms | 20,970.4 ms | 20,779.5 ms | -1,927.4 ms (-8.42%) |
| Complete backend | 24,569.4 ms | 22,700.9 ms | 22,531.7 ms | -1,868.5 ms (-7.61%) |
| Mean turn loop | 616.2 ms | 554.1 ms | 553.2 ms | -62.1 ms (-10.08%) |

The repeat improved gameplay by 2,118.2 ms (9.25%) and backend time by
2,037.7 ms (8.29%) relative to control. Both treatments retained exactly 758
events for seed 104729 and 941 for seed 104743.

## Behavioral acceptance

For both seeds, control, treatment, and repeat had identical:

- initial authoritative fingerprint;
- canonical action sequence, bit-for-bit;
- event count;
- engine and meaningful-action counts;
- fixed-horizon score and margin;
- city and settlement outcomes;
- zero rejected actions;
- zero deferred, expired, pending, or timed-out confirmations.

Seed 104729 remained at score 107, margin -2, 48 engine actions, 18 meaningful
actions, and one settlement. Seed 104743 remained at score 112, margin -3, 70
engine actions, 40 meaningful actions, and two settlements.

## Verification

- Focused event-writer suite: 22 passed.
- Focused state/recycle harness lane: 6 passed.
- Engine comparison: 6/6 arms completed without infrastructure failures.
- Full release audit: all checks passed for all four treatment traces,
  including the pinned external contract and every PF-PLN phase replay.

## Scope

This validates a storage-barrier optimization while preserving the event
contract, immediate persisted-first visibility, completed-turn durability, and
final replay completeness. It does not alter planner behavior or establish a
score or win-rate improvement.
