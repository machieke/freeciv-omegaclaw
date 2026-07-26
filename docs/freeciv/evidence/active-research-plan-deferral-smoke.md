# Active-research plan deferral smoke

Date: 2026-07-26

Status: focused policy coverage and two independent two-seed engine
treatments passed with exact action replay. This is a planner-throughput
result, not a gameplay-score or win-rate claim.

## Root cause and invariant

The active-research selection bypass removed redundant model selection, but
the canonical continuation proposal still entered goal grading, dependency
expansion, and scheduling on every turn. The exact legal-action catalog had
already proved that no research action could execute on those turns.

The planner now emits a child `verification` event with check
`active_research_has_no_new_selection_action` and returns `end_turn` without
creating a research plan only when all of these conditions hold:

1. the constrained planner and versioned
   `canonical-singleton-bypass-v1` policy are active;
2. the exact proxy legal set advertises no new research choice;
3. the authoritative snapshot has an active research target; and
4. that active target is the sole validated catalog target.

The canonical proposal still passes through the strict constrained parser and
symbol catalog. A new legal research choice, multiple targets, a model error,
or a non-constrained condition continues through the full planning path.

## Engine comparison

All cohorts used seeds 104729 and 104743, a serial 30-turn topology, the
retained proxy digest
`72813abbb7c45be3cc357592dd0bba33ca3537178cd7c34482f5c5033c5e5dd5`,
and otherwise identical configuration:

- controls: `artifacts/freeciv/active-research-bypass-20260726-a` and
  `artifacts/freeciv/active-research-bypass-20260726-b`;
- treatments: `artifacts/freeciv/active-research-plan-bypass-20260726-a` and
  `artifacts/freeciv/active-research-plan-bypass-20260726-b`.

Each column is the mean of both independent cohorts.

| Measure | Control mean | Treatment mean | Change |
|---|---:|---:|---:|
| Logical model-selection call rate | 0.033 | 0.033 | 0.00% |
| Selection-call avoided rate | 0.967 | 0.967 | 0.00% |
| Cognitive latency | 100.721 ms/turn | 92.554 ms/turn | -8.11% |
| Action latency | 135.230 ms/turn | 136.583 ms/turn | +1.00% |
| Boundary latency | 154.670 ms/turn | 154.961 ms/turn | +0.19% |
| Complete full-turn work | 248.415 ms/turn | 242.027 ms/turn | -2.57% |
| Mean turn loop | 404.781 ms/turn | 398.879 ms/turn | -1.46% |

The two treatment repeats independently measured cognitive reductions of
7.59% and 8.62% relative to their paired control repeats. The unrelated action
and boundary phases moved slightly in the second repeat, but the end-to-end
loop remained faster in both.

## Behavioral acceptance

All four treatment games retained, relative to the controls:

- exact ordered canonical action payloads;
- scores and margins 107/-2 and 112/-3;
- 48/70 total engine actions;
- one necessary selection query and 29 canonical avoidances per game;
- 29 continuation verifications per game; and
- zero infrastructure failures.

Each treatment removed 29 research planning passes: plan creation fell from
78 to 49 events for seed 104729 and from 100 to 71 for seed 104743. Planning
continues for executable non-research actions.

## Verification

- Complete repository FreeCiv lane: 356 passed.
- Focused active-research selection and catalog tests passed.
- Both two-game treatment cohorts completed without infrastructure failures.
- Four treatment traces passed all 13 top-level release-audit checks.
- Exact ordered-action comparison was empty for both seeds in both cohorts.
- Scores, opponent scores, and margins were identical in all comparisons.
- Static compilation and whitespace checks passed.
