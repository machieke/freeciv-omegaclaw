# Adaptive initial-readiness candidate (rejected)

Date: 2026-07-25

Status: rejected and reverted after two independent two-seed engine cohorts.
The artifacts are retained to prevent repeating an attractive but ineffective
micro-optimization.

## Candidate

The harness has a 500 ms quiet period after `game_ready`, followed by five
identical packet-sequence-aware decision snapshots at 50 ms intervals. The
candidate removed the fixed quiet period and retained the complete
decision-readiness predicate and all five stability samples.

## Evidence

- control:
  `artifacts/freeciv/clean-successor-recycle-repeat-20260725`
- candidate:
  `artifacts/freeciv/adaptive-initial-readiness-smoke-20260725`
- independent candidate repeat:
  `artifacts/freeciv/adaptive-initial-readiness-repeat-20260725`

| Measure (two-seed mean) | Control | Candidate | Repeat |
|---|---:|---:|---:|
| Run start to first snapshot | 3,348.5 ms | 2,906.4 ms | 2,991.4 ms |
| Gameplay | 22,897.8 ms | 23,034.1 ms | 23,319.7 ms |
| Complete backend | 24,569.4 ms | 24,685.3 ms | 24,980.2 ms |

The first snapshot moved earlier by 442.1 ms and 357.1 ms, but complete
gameplay increased by 136.3 ms (0.60%) and 421.9 ms (1.84%). Early querying
therefore shifted packet/extraction work instead of removing end-to-end work.

Both candidate cohorts preserved exact initial fingerprints, canonical action
sequences, scores, margins, action counts, settlements, and zero failure
counters. Correctness was not the rejection reason; lack of end-to-end
efficiency was.

## Decision

The fixed 500 ms quiet period was restored. A future candidate must reduce
complete gameplay/backend time, not only advance the first snapshot timestamp,
and must retain exact behavioral acceptance.
