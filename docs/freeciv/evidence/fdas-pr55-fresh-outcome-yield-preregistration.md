# PR55 fresh randomized outcome-yield cohort preregistration

Status: mechanically rejected; outcome-yield progression threshold met

Implementation commit: `285796528273f38d0e85dffa9661eb9b80b99241`

## Purpose and claim boundary

PR55 is the first unseen-gameplay-seed cohort after the choice-identity,
bounded-reprojection, failure-audit, and reprojection-observability hardening.
It estimates randomized defense-alternative opportunity and complete-outcome
yield so a later powered candidate-value study can be designed. It is not
powered or eligible for a candidate-value, gameplay, score, or win-rate claim.

No PR55 seed has a game directory anywhere in the repository's existing
FreeCiv artifacts as of preregistration. Outcome direction cannot change the
mechanical or progression rules.

## Frozen design

| Input | Value |
|---|---|
| Config | `profile/freeciv_harness_fdas_randomized_outcome_yield_160_turn.yaml` |
| Seed slice | offset 12, limit 12 |
| Seeds | `105619`, `105649`, `105653`, `105667`, `105673`, `105683`, `105691`, `105701`, `105727`, `105733`, `105751`, `105761` |
| Horizon | 160 turns |
| Backend | `engine-live` |
| Condition | `e_full_loop` only |
| Workers | 4 isolated processes on ports 6001 through 6004 |
| FDAS config | `profile/dependent_atomspace_defense_choice_surface_shadow.yaml` |
| FDAS manifest | `profile/fdas_manifest_defense_alternative_collection_randomized_pilot.json` |
| Assignment policy | `fdas-defense-nearest-score-randomized/4.0`, probability `0.5` |
| Assignment unit | game, turn, and exact control/treatment action pair |
| Outcome | `durable-selected-actor-city-defense/32-turn/2.0` |
| Audit | `fdas-randomized-alternative-live-audit/1.4` |
| Output | `artifacts/freeciv/fdas-randomized-outcome-yield-v2` |

The launch uses a clean documentation-only descendant of the implementation
commit, `--seed-offset 12`, `--limit-seeds 12`, `--main-only`, and
`--no-resume`. The local ruleset, proxy, token, and container bindings are
process-local and excluded from evidence.

## Mechanical acceptance

PR55 is mechanically accepted only if:

1. all 12 exact seeds reach the fixed endpoint without infrastructure failure
   or a rejected engine action;
2. every assignment reconstructs to the recorded exogenous draw and propensity
   and has one accepted action, exact episode, selected choice, and correctly
   resolved or administratively censored label;
3. every alternative execution uses component version 1.1 with a typed
   `authority_catalog_reprojected` value, and every per-game status counter
   equals the execution ledger;
4. all event ledgers and persisted stores are valid, hash-consistent, and not
   quarantined; and
5. no truth, claim, score, flow, advection, capacity, or unrelated action
   authority appears.

Zero-assignment games are retained and valid. Any early failed game's raw
assignment events are preserved but excluded from analyzable statistics.
Pending labels whose due turn lies after the fixed endpoint are administrative
censoring; a pending label due on or before the endpoint is a hard failure.

## Frozen progression rule

Progression to powered candidate-value design requires, in each arm:

- at least two observed outcomes;
- at least two independent game clusters; and
- effective sample size at least two under inverse-propensity weighting.

The treatment-minus-control risk difference and Wilson/Newcombe intervals are
descriptive only. If the progression rule fails, the cohort is frozen as yield
evidence and the next decision may use assignment and cluster counts—but never
outcome direction—to preregister a larger fresh block or revise the candidate
surface. No seed is added, removed, resumed, or rerun after outcomes are seen.

## Frozen result

PR55 executed all 12 frozen unseen seeds from clean source commit `f5d7483`
with implementation digest
`c7422be000364cdf39076c8e1a394d6362d2db689f50e23598b62fe92911299c`.
All games completed without infrastructure failure or rejected engine action.
Eleven reached final observed turn 161. Seed `105667` was authoritatively
eliminated at turn 138; its terminal score was carried forward under
`terminal_absorbing_score_carried_to_horizon`, but `horizon_reached` remained
false. Under the frozen fixed-endpoint rule, that single row mechanically
rejects the cohort. It had zero randomized assignments and does not change any
assignment outcome statistic.

The other gates passed exactly:

- 8 assignment events and 8 analyzable assignments;
- 4 control and 4 treatment assignments;
- 4 observed outcomes in 2 independent games in each arm;
- inverse-propensity effective sample size 4 in each arm;
- no pending or overdue outcomes;
- every execution used version 1.1 typed reprojection provenance;
- zero catalog reprojections in this fresh cohort; and
- valid warning-free ledgers and unquarantined digest-valid stores.

Opportunity-bearing games were 3 of 12, rate `0.25` with Wilson interval
`[0.0889, 0.5323]`. Assignment yield was 8 across 12 games, or `0.667` per
game; the Wilson interval for the binary at-least-one-assignment game rate is
the opportunity interval, not the assignment-per-game rate. Total engine time
was 3,524.66 seconds, mean 293.72 seconds per game under four-worker
contention.

The descriptive outcomes were 4/4 positive control and 1/4 positive treatment:
risk difference `-0.75`, Newcombe interval `[-0.9544, 0.1892]`. This is sparse,
clustered, and not claim-eligible. Per the frozen rule, neither its direction
nor magnitude may tune the next design. The yield-only progression gate did
pass, demonstrating enough independent clusters to parameterize a separately
preregistered powered study after terminal-endpoint semantics are frozen.

The machine-readable primary report is `fdas-pr55-fresh-outcome-yield.json`,
report hash
`9f080889f4a1bb26a04d9c97656655dbfd61ff73d3967597e66763fb725aa60f`.
The rejected row and all eight valid assignment lifecycles remain preserved;
no seed will be rerun or replaced.
