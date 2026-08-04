# FDAS PR85 logical-order paired replacement preregistration

Date: 2026-08-04

## Correction trigger

The frozen PR84 cohort exposed a decision-safe readout defect before its final
analysis. On seed `109721`, both arms produced the same three grounded logical
replacement tuples at turn 30, but their lifecycle operation IDs differed
because operation identity includes an arm-specific goal identity. The PR84
tracker ordered candidates by lifecycle operation ID, selecting replacement
actor `122` in control and `112` in treatment. PR84 correctly classifies that
seed as an opportunity mismatch and remains frozen; no PR84 arm will be
retried, replaced, or pooled with this correction.

## Frozen corrections

PR85 changes four mechanically coupled boundaries: first-opportunity ordering,
route-derived attempt capacity, treatment materialization when the legacy
planner has no action, and exact operation rematerialization across legacy
candidate filters. A grounded pair is ordered
lexicographically by:

```text
(replacement_actor_id,
 reinforcement_actor_id,
 source_city_id,
 target_city_id,
 lifecycle_operation_id)
```

The operation ID is only a final deterministic tie-breaker after the complete
logical tuple.

Before any PR85 seed was run, PR84 treatment seed `109721` exposed a second
mechanical defect: a native route needed more accepted tile actions than the
operation step's turn-ETA-derived attempt limit. PR85 therefore also freezes
`maximum_attempts=native_route.path_length+1` for each movement step. Candidate
readout requires the persisted limits to equal both current native route path
lengths plus one. Immediately before each treatment action, the remaining
attempt budget must still cover the current native path length; otherwise the
operation terminates failed before submission instead of raising or exceeding
the bound. No rejected action is retried.

Two later PR84 treatment arms exposed the third defect before any PR85 seed was
run: an exact, grounded, current legal replacement action could be authorized
when the legacy planner returned no action, but the integration layer required
a legacy decision solely to construct an `ImpactDecision`. PR85 permits the
existing exact-current-candidate materialization boundary to accept a null
baseline. It records `baseline_candidate_key=null` and `changed_winner=true`;
the authority action must still pass the current snapshot, legal-action,
category, operation, requirement, and downstream commit gates.

A fourth PR84 treatment failure then occurred before any PR85 engine seed was
run. After one accepted movement step, legacy candidate reprojection could omit
the next exact operation row or represent its byte-identical action under a
different current category even though the operation remained active and
within its own bounded attempt budget. PR85 makes the active exact authority
action exempt from the duplicate legacy retry policy and treats exact current
action identity as primary over category decoration. It prefers a category
match when available and otherwise retains the deterministic current candidate
category. The operation's persisted route-derived step budget remains the sole
retry bound, and all exact authority and commit gates remain unchanged.

All other grounding, safety checks, intention vector, 32-turn observation
window, treatment authority boundary, and legacy control policy remain
unchanged. The manifest must declare
`selection_policy=lexicographic-logical-tuple-v1`,
`attempt_budget_policy=native-route-path-length-plus-one-v1`,
`attempt_budget_failure=terminal-fail-before-submit`,
`baseline_absence_policy=exact-current-candidate-materialization-v1`,
`candidate_rematerialization_policy=exact-action-primary-current-category-v1`,
and
`legacy_suppression_policy=operation-attempt-budget-controls-exact-authority-v1`.

## Fixed paired cohort

The 16 fresh seeds are:

`109903, 109913, 109919, 109937, 109943, 109961, 110017, 110023, 110039,
110051, 110059, 110063, 110069, 110083, 110119, 110129`.

Each seed runs once per arm from one clean correction commit with no resume.
The experiment ID is
`fdas-replacement-intention-logical-order-paired-pilot-v2`. Within-pair arm
order uses the same frozen encoding as PR84, substituting the PR85 experiment
ID: UTF-8 `<experiment-id>:<base-10-seed>`, with SHA-256 low bit zero meaning
control then treatment and one meaning treatment then control. Independent
pairs may run concurrently; arms within a pair remain serial.

## Endpoints and missingness

Assignment, the +32 endpoint vector, disappearance attribution, analysis,
missingness, and claim boundaries are exactly those preregistered for PR84.
A pair is mechanically matched only when both arms select the same assignment
turn and logical tuple. No opportunity, censoring, infrastructure failure, and
terminal-state handling remain unchanged.

## Mechanical acceptance

- all 32 arms complete from one clean source with warning-free ledgers and
  zero engine rejections;
- every manifest and persisted assignment is bound to the corrected experiment
  and selection policy;
- every seed with an opportunity in both arms selects the same turn and logical
  tuple;
- no seed has a one-arm opportunity or outcome mismatch;
- at least four seed pairs are matched and observed; and
- the deterministic audit reproduces byte-for-byte.

If the corrected cohort still has a logical mismatch, preserve it as a failed
mechanical cohort and diagnose state/candidate divergence. Do not append or
replace seeds.

## Progression and claim boundary

The PR84 value progression rule is unchanged. PR85 is a claim-ineligible
paired mechanism correction. Even mechanical acceptance and a favorable
descriptive vector do not establish calibrated transition value, general
policy improvement, score impact, or win rate.
