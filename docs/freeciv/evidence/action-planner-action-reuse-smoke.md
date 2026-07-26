# Action-planner canonical action reuse smoke

Date: 2026-07-26

Status: complete focused regression and two independent two-seed engine
treatments passed with exact action replay. This is a local planner-throughput
result, not a gameplay-score or win-rate claim.

## Root cause and invariant

Observation, five pruning-telemetry inspections, and candidate planning decoded
the same immutable snapshot's canonical legal-action JSON independently.
Candidate enumeration then serialized every decoded action again for exclusion
membership even though `AuthoritativeSnapshot.legal_action_json` already holds
the exact canonical execution strings.

The planner now retains only the current snapshot's decoded actions and reuses
the existing canonical strings for exclusions and production-batch membership.
The cache is invalidated by snapshot object identity, is private to the planner,
and does not change or manufacture an action. The existing legal-action digest,
execution-gate membership check, utility ordering, and PF-pressure ranker remain
unchanged.

## Engine comparison

The control was
`artifacts/freeciv/action-planner-stage-attribution-20260726-b`. The independent
treatments were:

- `artifacts/freeciv/action-planner-action-reuse-20260726-a`; and
- `artifacts/freeciv/action-planner-action-reuse-20260726-b`.

All cohorts used seeds 104729 and 104743, a serial 30-turn topology, and the
retained proxy patch digest
`72813abbb7c45be3cc357592dd0bba33ca3537178cd7c34482f5c5033c5e5dd5`.
Treatment values below are the mean of both independent cohorts.

| Measure | Control | Treatment mean | Change |
|---|---:|---:|---:|
| Candidate enumeration per planner call | 12.819 ms | 7.442 ms | -41.94% |
| Complete impact-planner call | 14.299 ms | 9.443 ms | -33.96% |
| Impact planning per turn | 27.697 ms | 18.684 ms | -32.54% |
| Non-refresh action work | 53.466 ms/turn | 42.799 ms/turn | -19.95% |
| Complete action phase | 136.984 ms/turn | 128.624 ms/turn | -6.10% |
| Complete full-turn work | 240.227 ms/turn | 231.362 ms/turn | -3.69% |
| Mean turn loop | 395.884 ms/turn | 387.293 ms/turn | -2.17% |

The mechanism repeated closely: candidate enumeration measured 7.472 and
7.412 ms/call, while complete planner calls measured 9.461 and 9.426 ms/call.
PF-pressure ranking varied upward from 1.430 to 1.939 ms/call and unrelated
refresh/submission timing also varied. The retained claim is the directly
attributed candidate and planner reduction; the smaller full-turn and loop
changes are supporting observations rather than independent latency claims.

## Behavioral acceptance

Relative to the control, all four treatment games retained:

- exact ordered canonical action payloads;
- exact run-completion summaries;
- scores and margins 107/-2 and 112/-3;
- identical planner-decision and model-selection counts; and
- zero infrastructure failures.

## Verification

- Complete repository FreeCiv lane: 359 passed.
- Complete impact-planner test file before the final cache-specific regression:
  59 passed.
- Focused instrumentation and cache-invalidation regressions: 2 passed.
- Both independent two-game engine treatments: 4 completed, 0 infrastructure
  failures.
- All four treatment traces passed all 13 top-level release-audit checks at
  `artifacts/freeciv/action-planner-action-reuse-release-audit-20260726/report.json`.
- Exact ordered-action comparison was empty for both seeds in both treatments.
- Scores, margins, and run-completion summaries were identical.
- Static compilation and whitespace checks passed.
- The repository-prescribed `just check` entry point remains unavailable because
  `just` is not installed; the complete direct FreeCiv lane above passed.
