# Action-planner pressure-score reuse smoke

Date: 2026-07-26

Status: complete pressure-stage attribution, focused regression, and two
independent two-seed engine treatments passed with exact action replay. This is
a local planner-throughput result, not a gameplay-score or win-rate claim.

## Attribution and invariant

A fresh engine cohort at
`artifacts/freeciv/action-planner-pressure-attribution-20260726-a` split the
2.221 ms PF-pressure ranker call as follows:

| Pressure component | Latency | Share |
|---|---:|---:|
| Artifact materialization | 0.901 ms | 40.6% |
| Pressure propagation | 0.511 ms | 23.0% |
| Graph construction | 0.404 ms | 18.2% |
| Scheduling and final ordering | 0.310 ms | 13.9% |
| Operation construction | 0.077 ms | 3.5% |
| Timer residual | 0.018 ms | 0.8% |

The ranker calculated the ordered `OperationScore` tuple once for candidate
selection. `PressureScheduler.decision_artifact` then calculated the same
immutable scores once for its rows and a third time for budget allocation.

The scheduler now accepts an optional already-ranked score tuple and reuses it
for selection, serialized rows, and allocation. Existing callers that do not
supply scores retain the original behavior. A direct regression disables
rescoring after obtaining the tuple and proves that the resulting decision
artifact is exactly equal to the original artifact, including its structural
hash.

## Engine comparison

The attribution cohort above is the control. The independent treatments were:

- `artifacts/freeciv/action-planner-pressure-score-reuse-20260726-a`; and
- `artifacts/freeciv/action-planner-pressure-score-reuse-20260726-b`.

All cohorts used seeds 104729 and 104743, a serial 30-turn topology, and the
retained proxy patch digest
`72813abbb7c45be3cc357592dd0bba33ca3537178cd7c34482f5c5033c5e5dd5`.
Treatment values below are the mean of both independent cohorts.

| Measure | Control | Treatment mean | Change |
|---|---:|---:|---:|
| Pressure artifact materialization | 0.901 ms | 0.436 ms | -51.66% |
| Complete PF-pressure ranking | 2.221 ms | 1.806 ms | -18.67% |
| Complete impact-planner call | 4.982 ms | 4.568 ms | -8.30% |
| Impact planning per turn | 9.765 ms | 8.960 ms | -8.24% |
| Non-refresh action work | 34.280 ms/turn | 33.715 ms/turn | -1.65% |
| Complete action phase | 121.795 ms/turn | 119.787 ms/turn | -1.65% |
| Complete full-turn work | 226.901 ms/turn | 222.977 ms/turn | -1.73% |
| Mean turn loop | 382.474 ms/turn | 380.357 ms/turn | -0.55% |

The attributed mechanism repeated at 0.444 and 0.427 ms/call for artifact
materialization, while complete pressure ranking measured 1.816 and
1.796 ms/call. The retained claim is the artifact, pressure-ranker, and complete
planner reduction. The smaller outer changes remain supporting observations.

## Behavioral acceptance

Relative to the control, all four treatment games retained:

- exact ordered canonical action payloads;
- exact run-completion summaries;
- scores and margins 107/-2 and 112/-3;
- byte-identical direct scheduler decision artifacts in regression coverage;
  and
- zero infrastructure failures.

## Verification

- Complete repository FreeCiv lane: 361 passed.
- Complete pressure and impact-planner test files: 97 passed.
- Both independent two-game engine treatments: 4 completed, 0 infrastructure
  failures.
- All four treatment traces passed all 13 top-level release-audit checks at
  `artifacts/freeciv/action-planner-pressure-score-reuse-release-audit-20260726/report.json`.
- Exact ordered-action comparison was empty for both seeds in both treatments.
- Scores, margins, and run-completion summaries were identical.
- Static compilation and whitespace checks passed.
- The repository-prescribed `just check` entry point remains unavailable because
  `just` is not installed; the complete direct FreeCiv lane above passed.
