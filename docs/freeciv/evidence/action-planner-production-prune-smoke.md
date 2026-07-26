# Action-planner production-prune smoke

Date: 2026-07-26

Status: retained single-seed engine smoke with exact ordered-action replay.
This is local candidate-enumeration throughput evidence, not a gameplay-score,
win-rate, or statistically powered outer latency claim.

## Change

The impact planner's production policy can return candidates only for
ruleset-backed founder types and its declared economy or defense priorities.
It previously constructed current and proposed horizon projections for every
server-advertised production alternative before eventually rejecting all
unplanned target types.

Candidate enumeration now rejects targets outside those three sets before
projection. The server legal-action set, current-target protection, founder
capability grounding, all selectable target branches, candidate ordering, and
execution gate are unchanged. Static paired-baseline founder names remain
admitted explicitly. A focused regression proves that an irrelevant Pyramids
alternative is not projected while the eligible Library alternative remains
selected.

## Engine result

The fresh treatment `artifacts/freeciv/impact-production-prune-20260726-a`
was compared with the same-seed
`artifacts/freeciv/impact-pressure-index-20260726-a` control:

| Metric | Control | Treatment | Change |
|---|---:|---:|---:|
| Production evaluation | 1.336 ms/call | 0.907 ms/call | -32.11% |
| Complete candidate enumeration | 2.694 ms/call | 2.287 ms/call | -15.12% |
| Complete impact planning | 6.569 ms/turn | 6.022 ms/turn | -8.33% |
| Movement evaluation | 0.799 ms/call | 0.842 ms/call | noise |
| Complete pressure ranking | 1.442 ms/call | 1.498 ms/call | noise |
| Score at turn 30 | 107 | 107 | identical |
| Score margin at turn 30 | -2 | -2 | identical |
| Engine rejection rate | 0 | 0 | identical |
| Confirmation timeouts | 0 | 0 | identical |

The treatment retained the exact ordered 48-action replay and complete
`run_completed.summary`. The primary claim is the production slice. The
candidate and planner reductions are consistent supporting observations; the
independent movement and pressure variation is treated as single-run noise.

## Verification

- Complete canonical-runtime repository FreeCiv lane: 366 passed.
- Complete impact-planner regression lane: 64 passed.
- Fresh treatment engine trace: 1 completed, 0 infrastructure failures.
- Treatment trace release audit: all 10 applicable top-level checks passed.
- Exact ordered canonical action comparison: identical.
- Complete `run_completed.summary` comparison: identical.
- Static whitespace checks passed.
- The repository-prescribed `just check` entry point remains unavailable because
  `just` is not installed; the complete direct FreeCiv lane above passed.
