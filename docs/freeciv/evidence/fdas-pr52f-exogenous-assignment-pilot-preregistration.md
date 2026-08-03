# PR52f exogenous-assignment randomized execution pilot preregistration

Status: frozen before execution

Corrected implementation commit: `1a14afd`

## Purpose and claim boundary

PR52f is the final claim-ineligible mechanics retry. It combines the
selection-indexed delayed-label lifecycle proven in PR52e with a randomization
unit isolated from FDAS revision and diagnostic bookkeeping. It can confirm
mechanics and observed opportunity yield only. It cannot support candidate
value, policy quality, gameplay, score, or win-rate claims and is permanently
excluded from causal fitting and performance evaluation.

## Frozen inputs

All gameplay inputs remain identical to PR52e:

| Input | Value |
|---|---|
| Engine seed | `105491` |
| Horizon | 160 turns |
| Backend | `engine-live` |
| FDAS config | `profile/dependent_atomspace_defense_choice_surface_shadow.yaml` |
| FDAS manifest | `profile/fdas_manifest_defense_alternative_collection_randomized_pilot.json` |
| Experiment ID | `fdas-reinforcement-randomized-execution-pilot-v1` |
| Assignment seed | `2` |
| Treatment probability | `0.5` |
| Policy | `fdas-defense-nearest-score-randomized/4.0` |
| Randomization unit | `game-turn-exact-action-pair/1.0` |
| Action slice | `unit_move` / `city_garrison_move` |
| Alternative source | bounded nearest score |
| Outcome | `durable-selected-actor-city-defense/32-turn/2.0` |
| Frozen output | `artifacts/freeciv/fdas-randomized-execution-pilot-v1-exogenous-assignment` |

The previously observed turn-17 pair has actor `112` control and actor `117`
treatment. Under the frozen exogenous key, its deterministic draw is
`0.0959203857568428`, so this deliberately targeted mechanics run is expected
to exercise treatment and remains scientifically claim-ineligible.

## Mechanical acceptance criteria

All ten original PR52 criteria and the explicit PR52e label criteria remain
binding. In addition:

- the assignment material must contain exactly assignment unit, experiment,
  game, turn, policy version, randomization seed, and the two exact action keys;
- it must contain no revision, snapshot, union, operation, pressure, packet,
  commit, episode, label, score, or outcome identity;
- re-evaluation at the same legal action pair must reproduce the exact draw,
  arm, propensity, and assignment hash;
- the treatment action must pass independent preflight and the final planner
  gate, be accepted by the engine, and link to exactly one episode, label, and
  observed choice-set outcome.

Source must be clean at commit `1a14afd`; all event and store hashes must pass;
all submitted actions must be accepted; and no truth, claim, flow, advection,
capacity, or unrelated policy authority may appear.

## Decision rule

If any criterion fails, preserve and reject the run. If all pass, mechanics are
complete and the next step is not another targeted pilot: it is a separately
preregistered, fresh-seed randomized outcome cohort with lineage clustering,
effective-sample-size gates, confidence intervals, and explicit stopping and
missingness rules.
