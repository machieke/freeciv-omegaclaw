# Action-planner production-context reuse smoke

Date: 2026-07-26

Status: complete candidate attribution, focused regression, and two independent
two-seed engine treatments passed with exact action replay. This is a local
planner-throughput result, not a gameplay-score or win-rate claim.

## Attribution and invariant

After canonical action reuse, a fresh engine cohort at
`artifacts/freeciv/action-planner-candidate-attribution-20260726-a` split the
remaining 7.519 ms candidate-enumeration call as follows:

| Candidate component | Latency | Share |
|---|---:|---:|
| Production evaluation | 6.407 ms | 85.2% |
| Movement evaluation | 0.607 ms | 8.1% |
| Candidate setup | 0.149 ms | 2.0% |
| Other action evaluation | 0.125 ms | 1.7% |
| Catalog access | 0.056 ms | 0.7% |
| Final ordering | 0.034 ms | 0.4% |
| Timer/loop residual | 0.141 ms | 1.9% |

One snapshot advertised a mean 141.870 legal actions but yielded only 2.742
grounded candidates per planner call. Each legal production alternative
independently repeated snapshot-wide founder scans, queued-founder projections,
current-target projections, unit-score batch lookups, and defender scans.

Candidate enumeration now creates one private, call-scoped production context.
Each shared value is computed lazily at the same first decision point as before,
then reused only by the remaining alternatives from the same immutable snapshot
and exclusion set. Action-specific projections, exact canonical keys, utility
ordering, PF-pressure ranking, and the execution gate are unchanged.

## Engine comparison

The attribution cohort above is the control. The independent treatments were:

- `artifacts/freeciv/action-planner-production-context-20260726-a`; and
- `artifacts/freeciv/action-planner-production-context-20260726-b`.

All cohorts used seeds 104729 and 104743, a serial 30-turn topology, and the
retained proxy patch digest
`72813abbb7c45be3cc357592dd0bba33ca3537178cd7c34482f5c5033c5e5dd5`.
Treatment values below are the mean of both independent cohorts.

| Measure | Control | Treatment mean | Change |
|---|---:|---:|---:|
| Production evaluation per planner call | 6.407 ms | 1.443 ms | -77.48% |
| Complete candidate enumeration | 7.519 ms | 2.652 ms | -64.73% |
| Complete impact-planner call | 9.517 ms | 4.979 ms | -47.69% |
| Impact planning per turn | 18.792 ms | 9.766 ms | -48.03% |
| Non-refresh action work | 42.829 ms/turn | 34.834 ms/turn | -18.67% |
| Complete action phase | 126.537 ms/turn | 122.808 ms/turn | -2.95% |
| Complete full-turn work | 227.389 ms/turn | 226.381 ms/turn | -0.44% |
| Mean turn loop | 383.837 ms/turn | 381.851 ms/turn | -0.52% |

The attributed mechanism repeated almost exactly: production evaluation was
1.444 and 1.443 ms/call, while complete planner decisions were 4.962 and
4.995 ms/call. Refresh and PF-pressure timing varied independently. The
retained claim is the production, candidate, planner, and non-refresh action
reduction; the noisier action-phase, full-turn, and loop observations are not
promoted to standalone latency claims.

## Behavioral acceptance

Relative to the control, all four treatment games retained:

- exact ordered canonical action payloads;
- exact run-completion summaries;
- scores and margins 107/-2 and 112/-3;
- identical legal-action and candidate counts; and
- zero infrastructure failures.

## Verification

- Complete repository FreeCiv lane: 360 passed.
- Complete impact-planner test file: 61 passed.
- Both independent two-game engine treatments: 4 completed, 0 infrastructure
  failures.
- All four treatment traces passed all 13 top-level release-audit checks at
  `artifacts/freeciv/action-planner-production-context-release-audit-20260726/report.json`.
- Exact ordered-action comparison was empty for both seeds in both treatments.
- Scores, margins, and run-completion summaries were identical.
- Static compilation and whitespace checks passed.
- The repository-prescribed `just check` entry point remains unavailable because
  `just` is not installed; the complete direct FreeCiv lane above passed.
