# PR53 fresh-seed randomized outcome-yield preregistration

Status: preregistered; execution not started

Implementation commit: `caf9010bfdb67a0cb0acb37ad165b7fd75153559`

## Purpose and claim boundary

PR53 measures how often the frozen, narrowly bounded city-defense alternative
decision occurs on unseen engine seeds and how many assignment-linked 32-turn
outcomes are available at a fixed endpoint. It is a claim-ineligible yield
study. It cannot establish candidate value, gameplay quality, score, or
win-rate improvement, and its outcomes cannot be reused in a later discovery
or confirmation claim.

The implementation, action slice, assignment unit, probability, outcome, and
gameplay policy are frozen before execution. PR52 through PR52f seeds and all
prior FDAS fitting, pilot, replay, discovery, and confirmation seeds are
excluded.

## Frozen design

| Input | Value |
|---|---|
| Harness config | `profile/freeciv_harness_fdas_randomized_outcome_yield_160_turn.yaml` |
| Gameplay base | `profile/freeciv_harness_fdas_pr49_160_turn.yaml` |
| Horizon | 160 turns |
| Backend | `engine-live` |
| Condition | `e_full_loop` only |
| Workers | 4 isolated processes on ports 6001 through 6004 |
| FDAS config | `profile/dependent_atomspace_defense_choice_surface_shadow.yaml` |
| FDAS manifest | `profile/fdas_manifest_defense_alternative_collection_randomized_pilot.json` |
| Assignment seed | `2` |
| Treatment probability | `0.5` |
| Policy | `fdas-defense-nearest-score-randomized/4.0` |
| Randomization unit | `game-turn-exact-action-pair/1.0` |
| Action slice | `unit_move` / `city_garrison_move` |
| Alternative source | bounded nearest score |
| Outcome | `durable-selected-actor-city-defense/32-turn/2.0` |
| Audit | `fdas-randomized-alternative-live-audit/1.1` |
| Output | `artifacts/freeciv/fdas-randomized-outcome-yield-v1` |

The exact ordered seed cohort is:

```text
105503, 105509, 105517, 105527, 105529, 105533,
105541, 105557, 105563, 105601, 105607, 105613
```

The source commit used for execution must be the clean documentation-only
descendant containing this preregistration. The implementation digest must be
identical for every game. The seed overlay may replace only the seed list; the
resolved 160-turn gameplay configuration is otherwise inherited unchanged.

## Missingness, clustering, and stopping

- Every eligible exact action pair is assigned once by its frozen exogenous
  game/turn/action-pair key. No observed state, score, outcome, revision,
  diagnostic artifact, or selection-dependent bookkeeping enters the draw.
- Outcomes are analyzed only when their due turn is observed. A pending label
  whose due turn is after the fixed endpoint is administrative censoring and
  is never imputed negative. A pending label due on or before the endpoint is
  a mechanical failure.
- Games, rather than assignments, are the independent lineage clusters.
  Assignment counts and inverse-propensity effective sample size are reported,
  but neither may substitute for the number of observed game clusters.
- All 12 seeds are run exactly once. There is no outcome-, assignment-, or
  arm-dependent stopping, seed replacement, or extension. Infrastructure
  failures are preserved and reported rather than silently retried into the
  cohort.
- PR53 reports opportunity yield per game, observed outcome yield per game and
  engine hour, arm balance, positive rates, Wilson intervals, and the
  descriptive treatment-minus-control risk difference when both arms exist.
  Those estimates remain claim-ineligible.

## Mechanical acceptance gates

The cohort mechanically passes only if:

1. exactly the 12 frozen seeds reach the fixed endpoint with one clean source
   identity, no infrastructure failure, and zero rejected engine actions;
2. every event ledger validates with no warning, all stores are hash-valid and
   not quarantined, and status counters match events;
3. games with no eligible assignment are retained and pass all non-assignment
   gates rather than being excluded;
4. every assignment reconstructs the exact draw, arm, propensity, accepted
   action, episode, label, choice set, and causal ancestry;
5. no label remains unresolved after its due turn; and
6. truth mutation, flow/advection/capacity authority, and gameplay or claim
   eligibility remain disabled outside the declared bounded action readout.

## Progression rule

Mechanical acceptance is separate from scientific yield. Progression to a
powered discovery design additionally requires at least two due-turn-observed
independent game clusters in each randomized arm. If that threshold is not
met, the result is still retained: the narrow opportunity surface, horizon, or
outcome collection design must be improved before a causal value cohort is
economically defensible.

No result from PR53, favorable or unfavorable, changes these criteria.
