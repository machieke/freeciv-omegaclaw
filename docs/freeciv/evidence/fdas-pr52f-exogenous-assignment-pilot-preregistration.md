# PR52f exogenous-assignment randomized execution pilot preregistration

Status: mechanically passed

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

The source worktree must be clean and all implementation files must be
byte-identical to implementation commit `1a14afd`; documentation-only
preregistration descendants are permitted. All event and store hashes must
pass, all submitted actions must be accepted, and no truth, claim, flow,
advection, capacity, or unrelated policy authority may appear.

## Decision rule

If any criterion fails, preserve and reject the run. If all pass, mechanics are
complete and the next step is not another targeted pilot: it is a separately
preregistered, fresh-seed randomized outcome cohort with lineage clustering,
effective-sample-size gates, confidence intervals, and explicit stopping and
missingness rules.

## Frozen outcome

PR52f passed every mechanical gate. The clean engine-backed game reached the
fixed horizon with 406 accepted and zero rejected actions. Its sole eligible
turn-17 assignment reproduced exogenous material hash
`188e3d07d868775df772c064da0a80e6238ba769d84a60e350f8901651d03b32`
and draw `0.0959203857568428`, selected treatment actor `117`, changed the
legacy winner, passed independent preflight and the final planner gate, and
linked the accepted engine result to exactly one episode.

That episode opened exactly one selected-actor label at turn 17, due turn 49,
despite terminating as effect without immediate goal relief. The label was
observed at turn 49 as negative because actor `117` was not at the target city,
and the exact candidate choice set resolved to the same negative outcome. The
event ledger has zero errors and warnings; store hashes, source identity,
propensity, causal ancestry, censored alternatives, and authority boundaries
all pass the reusable fail-closed auditor.

The machine-readable result is
`fdas-pr52f-exogenous-assignment-pilot.json`, report hash
`72cc089699d2d746fdc05abcbe791b6b2b9c6812ef71d30946ac1fb5e74b2f3d`.
This confirms mechanics only. The deliberately targeted seed and single
negative treatment outcome support no candidate-value or gameplay claim.
