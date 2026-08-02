# FDAS PR31 promoted-rule shadow confirmation

Status: preregistered fresh engine cohort accepted; readout coverage and point
predictive improvement repeated; statistical improvement remains unresolved;
no induced-rule authority, gameplay, score, or win-rate claim.

## Cohort integrity

All six preregistered seeds ran from clean commit `188ebc1` through the fixed
160-turn horizon. There were no retries, replacements, resumes, or
outcome-dependent changes. Every status is complete and horizon-reaching;
every event ledger validates without warnings; all six delayed-outcome audits
accept the exact `defense-episode-features/3.0` schema and 32-turn attributed-
actor target.

| Seed | Observed labels | Positive | Negative | Delayed-label audit hash |
|---:|---:|---:|---:|---|
| 104911 | 4 | 4 | 0 | `5dd6d6af68d3aea112c049d5d6098199d8e9a8f86c424ee7b14ce43885958e39` |
| 104917 | 5 | 3 | 2 | `ef3c912e97a756a0e3b841eb450ffaad27bc2bbff8ca08305cb9473157ac8ba8` |
| 104933 | 2 | 2 | 0 | `3704f1f957c0ade5ae9b6c36c98ba25cbfffc77f7410f45f42ebb20938a6de22` |
| 104947 | 3 | 2 | 1 | `d8627a6a71fad4dd5bf0a67789cf6a250e6b36e523ce50ca8d34e8a502f86916` |
| 104953 | 3 | 3 | 0 | `6b92a50b04d214f6520c198f00cf1a3288df8372de2145672644f1a4c4d381ca` |
| 104959 | 3 | 2 | 1 | `25609ae425e5dd48182b9876595df60f7dbceb30baf44eb36376e48a46080693` |
| **Total** | **20** | **16** | **4** | |

The underlying controller executed 1,877 accepted engine actions with zero
rejections. Twenty were existing bounded FDAS defense actions. The promoted-
rule readout ran only in the offline outcome-blind evaluator and changed none
of those selections or actions.

## Predeclared gate result

| Gate | Required | Observed | Result |
|---|---:|---:|---|
| Encoded delayed outcomes | at least 20 | 20 | pass |
| Shadow predictions | at least 12 | 19 | pass |
| Readout coverage | implicit | 95% | diagnostic |
| Ambiguous predictions | at most 20% | 0% | pass |
| Conditional Brier improvement | at least 0 | +0.00771 | pass |
| Truth/readout/policy/action authority | none | none | pass |

One fortification episode had no matching approved rule because the frozen
rules were scoped to the defender-movement operation. It abstained explicitly.
All 19 matching episodes produced a prediction, and overlapping same-direction
maximal rules resolved conservatively without conflict.

## Predictive result

On the 19 covered episodes, 15 outcomes were positive and four negative.

| Metric | Baseline | Shadow readout | Difference |
|---|---:|---:|---:|
| Brier score | 0.17186 | 0.16415 | +0.00771 improvement |
| Log loss | 0.52938 | 0.50857 | +0.02081 improvement |
| Exact-prediction calibration error | — | 0.06817 | — |

The deterministic paired 10,000-sample bootstrap interval for Brier
improvement is `[-0.01402, +0.02530]`. The point estimate therefore repeated
in fresh games, but the interval crosses zero. This is directional predictive
evidence, not a statistically resolved superiority claim.

The strata also explain why authority would be premature. Unit-production
episodes alone had Brier change `-0.00258`; two overlapping-rule strata each
had two positive and two negative outcomes and Brier change `-0.02415`.
Improvement came mainly from other covered contexts. The next model increment
must calibrate contextual readout estimates rather than treating the overall
mean as uniform decision value.

## Claim boundary and next gate

The result confirms that the approval-bound four-rule basis can be read with
high coverage, bounded uncertainty, explicit abstention, and zero control
authority on a fresh cohort. It does not show that consulting the prediction
would choose a better action, cause durable defense, improve score, or improve
win rate.

The next safe step is a shadow candidate-impact join: attach predictions to
the exact defense candidates that were already selected or rejected, record
counterfactual ranking deltas without changing the winner, and calibrate by
operation/lifecycle context. Only a later randomized bounded-authority trial
can establish intervention value.

The machine-readable report is
[`fdas-pr31-promoted-rule-shadow-engine.json`](fdas-pr31-promoted-rule-shadow-engine.json).
Its structural hash is
`948b840e13adb107a6c0411a82c6c1162d7cd05a79508bf24979aed0db2c15ae`.
