# Active-research planning-view deferral smoke

Date: 2026-07-26

Status: focused continuation coverage and two independent two-seed engine
treatments passed with exact action replay. This is a host-planner efficiency
result, not a gameplay-score or win-rate claim.

## Root cause and invariant

After active-research plan deferral, the continuation gate returned before
grading, dependency expansion, and scheduling. It nevertheless constructed a
`CrispStateView` and a `PlanningSnapshot` first, including a scan and
normalization of the complete compiled technology-cost table.

Those views have no consumer when the exact legal catalog proves that research
is already active and no new research action can execute. Construction now
occurs after the continuation and model-fallback returns. Any turn that reaches
grading or planning receives the identical views from the identical
authoritative snapshot.

A focused regression enables both dependency and scheduler capabilities,
forces a valid active continuation, and fails if technology-cost construction
is reached. The turn must still emit its canonical `goal_selection` and child
verification.

## Engine comparison

All cohorts used seeds 104729 and 104743, a serial 30-turn topology, the
retained proxy digest
`72813abbb7c45be3cc357592dd0bba33ca3537178cd7c34482f5c5033c5e5dd5`,
and otherwise identical configuration:

- controls: `artifacts/freeciv/proposal-parser-reuse-20260726-a` and
  `artifacts/freeciv/proposal-parser-reuse-20260726-b`;
- treatments: `artifacts/freeciv/continuation-view-deferral-20260726-a` and
  `artifacts/freeciv/continuation-view-deferral-20260726-b`.

Each column is the mean of both independent cohorts.

| Measure | Control mean | Treatment mean | Change |
|---|---:|---:|---:|
| Cognitive setup | 0.552 ms/turn | 0.137 ms/turn | -75.20% |
| Non-model cognition | 3.652 ms/turn | 3.299 ms/turn | -9.69% |
| Model latency | 85.956 ms/turn | 87.318 ms/turn | +1.58% |
| Total cognition | 89.609 ms/turn | 90.617 ms/turn | +1.13% |
| Complete full-turn work | 240.374 ms/turn | 239.969 ms/turn | -0.17% |
| Mean turn loop | 398.296 ms/turn | 397.484 ms/turn | -0.20% |

The deterministic setup saving repeated in both treatments at 0.137 ms/turn.
Variation in the one real model call obscured that saving in total cognitive
time, so the retained claim is the attributed host-work reduction. Pooled
full-turn and loop latency remained slightly lower.

## Behavioral acceptance

All four treatment games retained, relative to both controls:

- exact ordered canonical action payloads;
- scores and margins 107/-2 and 112/-3;
- one necessary model selection and 29 canonical avoidances per game;
- 29 active-continuation verifications per game; and
- zero infrastructure failures.

## Verification

- Complete repository FreeCiv lane: 357 passed.
- Focused active-continuation, singleton, and multi-candidate tests passed.
- Both two-game treatment cohorts completed without infrastructure failures.
- Four treatment traces passed all 13 top-level release-audit checks.
- Exact ordered-action comparison was empty for both seeds in both cohorts.
- Scores, opponent scores, and margins were identical in all comparisons.
- Static compilation and whitespace checks passed.
