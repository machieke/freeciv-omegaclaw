# PR56 powered randomized candidate-value discovery preregistration

Status: completed; mechanically rejected and not advanced

Implementation commit: `645ee5e835f9b6c5a291a15e982bd07a227f54de`

Power plan: `ba88a0c89575dfde0bc5ba3a7c4836ab20e6361a31baaea0844acd9f9b4c4d89`

## Purpose and claim boundary

PR56 is a fixed-size powered discovery cohort for the local causal effect of
the bounded nearest-score FDAS city-defense alternative on 32-turn durable
selected-actor city defense. It is the first cohort permitted to evaluate
candidate value, but discovery alone cannot establish a final candidate-value,
gameplay, score, or win-rate claim. A positive result must be repeated in a
separately preregistered, equally powered, held-out confirmation cohort.

The design was calculated from PR55 yield only. The planner consumes game,
opportunity, assignment, arm-cluster, and runtime counts and is structurally
unable to read outcomes. Tests mutate every outcome direction field without
changing the plan. PR55's descriptive effect is not an input.

## Frozen power design

| Parameter | Value |
|---|---:|
| Primary estimand | treatment minus control durable-defense probability |
| Minimum detectable risk difference | 0.35 |
| Two-sided alpha | 0.05 |
| Target power | 0.80 |
| Planning ICC | 0.25 |
| Mean assignments per opportunity game | 2.6667 |
| Cluster design effect | 1.4167 |
| Independent assignments per arm | 30.8304 |
| Required assignments per arm | 44 |
| Minimum game clusters per arm | 20 |
| Yield safety multiplier | 1.25 |
| Planned fresh games | 168 |
| Workers | 4 |
| Estimated engine time | 13.71 hours |
| Estimated wall time at PR55 throughput | 3.43 hours |

The machine-readable calculation is
`fdas-pr56-candidate-value-power-plan.json`. The material effect of 0.35 was
chosen before PR56 outcomes as the smallest difference large enough to justify
changing active local defense selection. This study is not powered for smaller
effects.

## Frozen execution

| Input | Value |
|---|---|
| Config | `profile/freeciv_harness_fdas_candidate_value_discovery_160_turn.yaml` |
| Seed count | 168 |
| Seed range | `106013` through `107999` |
| Ordered seed-list hash | `c3efe3dc41af8dc2fd2b301b82416f31033af4c44173ce0686b3281f8c7ef1db` |
| Horizon | 160 turns or validated terminal-absorbing endpoint |
| Backend | `engine-live` |
| Condition | `e_full_loop` only |
| Ports | 6001 through 6004 |
| FDAS config | `profile/dependent_atomspace_defense_choice_surface_shadow.yaml` |
| FDAS manifest | `profile/fdas_manifest_defense_alternative_collection_randomized_pilot.json` |
| Assignment policy | `fdas-defense-nearest-score-randomized/4.0`, probability 0.5 |
| Outcome | `durable-selected-actor-city-defense/32-turn/2.0` |
| Mechanical audit | `fdas-randomized-alternative-live-audit/1.5` |
| Discovery analysis | `fdas-randomized-candidate-value-discovery/1.0` |
| Bootstrap | 10,000 game-cluster samples, seed `8113` |
| Output | `artifacts/freeciv/fdas-candidate-value-discovery-v1` |

All 168 seeds are absent from existing repository artifacts at preregistration.
The launch uses the clean documentation/configuration descendant containing
this preregistration, `--main-only`, and `--no-resume`. There is no interim
analysis, optional stopping, seed replacement, outcome-dependent extension, or
resume into the claim cohort. An infrastructure failure remains a failed row.

## Mechanical acceptance

PR56 is mechanically valid only if:

1. every seed completes at turn 160/161 or at an audit-1.5 terminal-absorbing
   endpoint with exact observer authority and no pending assignment outcome;
2. there is no infrastructure failure or rejected engine action;
3. every assignment reconstructs its exogenous draw and propensity and links
   once to an accepted action, exact episode, selected choice, and observed
   outcome;
4. every execution uses component version 1.1 typed catalog-reprojection
   provenance and status counters match events;
5. all ledgers and stores validate without warning or quarantine; and
6. no truth, claim, score, flow, advection, capacity, or unrelated action
   authority appears.

Administrative censoring is reported but cannot count toward power. Any pending
assignment at a terminal-absorbing endpoint is a hard failure.

## Discovery analysis and decision rule

The fixed primary estimator is the inverse-propensity treatment-minus-control
risk difference among observed assignment outcomes. Its 95% interval is the
deterministic percentile interval from resampling whole games with replacement,
never individual rows. At least 99% of bootstrap replicates must contain both
arms.

The cohort is powered and mechanically analyzable only if it contains at least
44 observed assignments and 20 independent game clusters in each arm. No raw
assignment count can substitute for game clusters.

- Advance to held-out positive confirmation only if every mechanical and power
  gate passes and the 95% interval lower bound is strictly above zero.
- If the interval includes zero or is entirely negative, freeze the result and
  do not run positive confirmation.
- If assignment or cluster yield misses its planned threshold, declare the
  discovery mechanically incomplete; do not add games after outcomes are seen.

Even a positive discovery result is not a final claim. Confirmation must freeze
new seeds, the same estimator, the same minimum counts, and a one-sided positive
gate before its gameplay begins.

## Frozen result

PR56 executed all 168 exact seeds from clean source commit `51186e4` with
implementation digest
`cbe379821c78c57306053808a57b38d291b3f380ae879d6ac2762d7ed833553b`.
The harness closed 166 games successfully and preserved two infrastructure
failures; no seed was resumed or replaced.

The two failures were both engine rejections of proxy-advertised actions:

- seed `106417`, turn 135: the trusted legal set contained three negative-y
  moves on a non-wrapping map; the selected move to `(10,-1)` was rejected as
  outside game bounds; and
- seed `107123`, turn 42: a randomized treatment move for unit 125 was accepted,
  its bounded authoritative refresh timed out, and the same treatment was
  reprojected from the unchanged snapshot and rejected because the unit no
  longer had moves.

Audit 1.5 therefore rejects the cohort on the all-game gate and preserves both
failed rows. Its exact-seed, source-identity, no-overdue-outcome, and authority
boundary gates pass. The machine report is
`fdas-pr56-candidate-value-discovery-mechanical.json`, report hash
`21dc7c79b2090a788b2993793e726b20db8a3878e31eabd6bcd9c62db4197288`.

Yield also missed the frozen powered-analysis gate. The 166 valid games
provided 59 analyzable assignments: 30 control outcomes in 18 game clusters
and 27 observed treatment outcomes in 20 game clusters, with two treatment
outcomes pending in the failed stale-snapshot game. The design required 44
observed outcomes and 20 independent game clusters in each arm.

For completeness only, the invalid cohort's descriptive durable-defense rates
were 16/30 control and 9/27 treatment, a treatment-minus-control risk difference
of `-0.20` with interval `[-0.5112, 0.1603]`. Mechanical rejection and power
failure prohibit a candidate-value claim. The direction also fails the frozen
positive-discovery rule, so no same-design held-out confirmation is launched.
The next work is the claim-ineligible PR57 exact failure-seed hardening replay;
any later value study must use a new intervention rationale and a newly powered,
fresh-seed design.
