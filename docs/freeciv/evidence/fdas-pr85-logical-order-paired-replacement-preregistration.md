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

## Frozen correction

PR85 changes only the first-opportunity order key. A grounded pair is ordered
lexicographically by:

```text
(replacement_actor_id,
 reinforcement_actor_id,
 source_city_id,
 target_city_id,
 lifecycle_operation_id)
```

The operation ID is only a final deterministic tie-breaker after the complete
logical tuple. All grounding, safety checks, manifests, intention vector,
32-turn observation window, PR82 treatment executor, and legacy control policy
remain unchanged. The manifest must declare
`selection_policy=lexicographic-logical-tuple-v1`.

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
