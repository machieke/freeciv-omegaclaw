# State-summary action-kind reuse smoke

Date: 2026-07-26

Status: complete state-bridge coverage and two independent two-seed engine
treatments passed with exact action replay. This is a typed-boundary and
host-throughput result, not a gameplay-score or win-rate claim.

## Root cause and invariant

`ProxyStateDTO` already normalizes every advertised legal action into its exact
canonical execution document. `StateSummaryService` then decoded every one of
those JSON documents again solely to expose the distinct action-kind names to
the LLM query summary. The engine traces carry tens of kilobytes of canonical
actions per snapshot, so that duplicate decode dominated summary construction.

The DTO now records a sorted `legal_action_kinds` tuple while each normalized
action is still an in-memory typed dictionary. The immutable snapshot carries
that derived tuple, and the query-only summary copies it without exposing legal
payloads. The canonical action JSON and digest are unchanged and remain the
only execution-gate authority. Invalid actions remain excluded before both the
canonical set and kind tuple are constructed.

## Engine comparison

All cohorts used seeds 104729 and 104743, a serial 30-turn topology, the
retained proxy digest
`72813abbb7c45be3cc357592dd0bba33ca3537178cd7c34482f5c5033c5e5dd5`,
and otherwise identical configuration:

- controls: `artifacts/freeciv/continuation-view-deferral-20260726-a` and
  `artifacts/freeciv/continuation-view-deferral-20260726-b`;
- treatments: `artifacts/freeciv/summary-action-kinds-reuse-20260726-a` and
  `artifacts/freeciv/summary-action-kinds-reuse-20260726-b`.

Each column is the mean of both independent cohorts.

| Measure | Control mean | Treatment mean | Change |
|---|---:|---:|---:|
| Summary construction | 0.807 ms/turn | 0.057 ms/turn | -92.90% |
| Non-model cognition | 3.299 ms/turn | 2.533 ms/turn | -23.20% |
| Model latency | 87.318 ms/turn | 87.226 ms/turn | -0.11% |
| Total cognition | 90.617 ms/turn | 89.760 ms/turn | -0.95% |
| Action-refresh DTO parse | 4.830 ms/refresh | 4.972 ms/refresh | +2.95% |
| Boundary DTO parse | 6.077 ms/turn | 6.151 ms/turn | +1.22% |
| Complete full-turn work | 239.969 ms/turn | 241.204 ms/turn | +0.51% |
| Mean turn loop | 397.484 ms/turn | 399.048 ms/turn | +0.39% |

The summary mechanism repeated independently at 0.055 and 0.059 ms/turn.
Adding the kind to the existing DTO normalization loop was much smaller than
the removed summary decode, although DTO and unrelated action timing varied
slightly upward. The retained claim is the attributed summary/non-model
cognition reduction; the noisy end-to-end measurements do not support a loop
latency claim.

## Behavioral acceptance

All four treatment games retained, relative to both controls:

- exact ordered canonical action payloads;
- scores and margins 107/-2 and 112/-3;
- the identical LLM-visible legal action-kind sets;
- one necessary model selection and 29 canonical avoidances per game; and
- zero infrastructure failures.

## Verification

- Complete repository FreeCiv lane: 357 passed.
- Complete state-bridge test file: 20 passed.
- Both two-game treatment cohorts completed without infrastructure failures.
- Four treatment traces passed all 13 top-level release-audit checks.
- Exact ordered-action comparison was empty for both seeds in both cohorts.
- Scores, opponent scores, and margins were identical in all comparisons.
- Static compilation and whitespace checks passed.
