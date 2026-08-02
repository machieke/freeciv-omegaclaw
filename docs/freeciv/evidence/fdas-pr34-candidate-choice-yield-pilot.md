# FDAS PR34 candidate-choice yield pilot

Status: mechanically failed exactly as preregistered and did not pass the
progression gate. Outcome contrast is sufficient for a later observational
model, but the exact fortification slice supplies no competing candidates.

## Frozen execution

The preregistered seeds `104743`, `104759`, and `104761` ran from clean,
identical commit `59dffa6498a67fc539f56af567c67f5999789935` with
implementation digest
`bd62619aa84922d82966836b81256c3d9c79723643918597d1f13017a14a4b73`.
All three engine jobs completed without infrastructure failure and with zero
rejected actions. Seed `104761` was eliminated at turn 153, so it did not
reach the preregistered 160-turn horizon. The mechanical cohort gate therefore
failed and is not reinterpreted after seeing the result.

All 62,676 events validated with zero errors and warnings. All choice-store,
outcome-free-query, selected-only export, censorship, and non-authority gates
passed.

## Yield

| Measure | Result |
|---|---:|
| Choice sets / choices | 15 / 15 |
| Observed selected outcomes | 15 |
| Positive / negative outcomes | 11 / 4 |
| Pending or otherwise censored selected outcomes | 0 |
| Distinct selected feature signatures | 9 |
| Actor/context signatures | 11 |
| Multi-candidate choice sets | 0 |
| Nonselected candidate rows | 0 |
| Engine time | 0.0934 hours |
| Observed outcomes per engine hour | 160.68 |

The observed-count, outcome-contrast, and actor/context progression thresholds
passed. The multi-candidate threshold failed (`0 < 3`), so the overall
progression gate failed. The machine-readable report is
`fdas-pr34-candidate-choice-yield-pilot.json`, with report hash
`e6cf7375d4891b63a3dcb8790e1551e5a0b27193a876125f3756e1956ceafd06`.

## Root cause

The failure is not candidate-budget truncation, readout loss, or insufficient
outcome collection.

Across all 15 captured decisions:

- FDAS instantiated exactly one `unit-fortification-opportunity` goal;
- that goal was keyed to one exact `(unit, city)` pair;
- `CandidateOperationFactory._action_matches` admitted only the
  `unit_fortify` legal action for that exact unit;
- omitted-unprotected-candidate count was always zero; and
- category readout faithfully retained that one operation.

The broader live pressure graphs often contained garrison-move alternatives:
the graph had as many as 10 operations, but the promoted PR29/PR30 rule scope
and PR32 readout are fixed to
`fdas-shadow:unit-fortification-opportunity:unit_fortify`. Those moves are a
different lifecycle/action type and correctly did not receive a fortification
prediction.

Fortification in this regime is also sequential. The currently advertised
nonfortified defender can be fortified, after which a later snapshot may
advertise another unit. These are not mutually exclusive alternatives in one
decision. Treating them as a candidate ranking problem would manufacture a
competition that FreeCiv did not present.

## Consequence

More games of this exact slice can improve an observational estimate of
fortified-actor persistence, because the pilot produced real 11/4 outcome
contrast. They cannot establish actor-relative candidate ranking value when
every decision has one candidate.

The next bounded implementation must capture a genuinely competitive defense
choice surface, most naturally the category union of current legal garrison
moves and fortification. It must:

1. preserve action-type and lifecycle strata rather than applying a
   fortification rule to movement;
2. open outcome episodes for accepted legacy-selected defense actions without
   granting FDAS authority;
3. use one delayed actor-at-target-defense outcome whose eligibility and
   attribution semantics are valid for both movement and fortification;
4. retain nonselected operations as censored; and
5. require a fresh discovery/holdout cycle before any cross-action candidate
   readout or rank claim.

The existing four-rule fortification model remains frozen and non-authorizing.
No controller retuning or score experiment is justified by this pilot.
