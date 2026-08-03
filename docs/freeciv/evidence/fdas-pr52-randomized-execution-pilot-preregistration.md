# PR52 randomized alternative execution pilot preregistration

Status: frozen before execution

Implementation commit: `0b94cd2`

## Purpose and claim boundary

This is a one-game engineering pilot for the first claim-ineligible FDAS
randomized alternative execution. Its only purpose is to validate assignment,
exact rematerialization, final-gate execution, and delayed-outcome linkage. It
cannot support a candidate-value, gameplay, score, or win-rate claim.

The seed and policy randomization key were chosen after inspecting the PR51
shadow opportunity so that the known pair is expected to exercise the
treatment branch. That deliberate mechanics targeting excludes this run from
all causal fitting and evaluation.

## Frozen inputs

| Input | Value |
|---|---|
| Engine seed | `105491` |
| Horizon | 160 turns |
| Backend | `engine-live` |
| FDAS config | `profile/dependent_atomspace_defense_choice_surface_shadow.yaml` |
| FDAS manifest | `profile/fdas_manifest_defense_alternative_collection_randomized_pilot.json` |
| Experiment ID | `fdas-reinforcement-randomized-execution-pilot-v1` |
| Assignment seed | `3` |
| Treatment probability | `0.5` |
| Action slice | `unit_move` / `city_garrison_move` |
| Alternative source | bounded nearest score |
| Outcome | `durable-selected-actor-city-defense/32-turn/2.0` |

Both arms must share target reference, operation type, unit type, first-step
movement cost, deficit atom, typed priority, and risk penalty. They must retain
disjoint actor resources and independently reproduce pressure, packet, and
exact commit proofs.

## Mechanical acceptance criteria

The pilot passes only if all of the following hold:

1. the game reaches the fixed horizon without infrastructure failure;
2. every submitted engine action is accepted and no final-gate rejection
   occurs;
3. at least one assignment is `eligible-randomized-diagnostic`;
4. at least one treatment assignment changes the legacy winner;
5. every eligible assignment has exactly one execution attempt;
6. every attempt is accepted and links to exactly one decision episode;
7. assignment, operation-authority, plan, action-result, episode, and
   candidate-choice events form one causal chain;
8. the choice-set and episode provenance preserve assignment result hash,
   assigned arm, stochastic policy kind, propensity `0.5`, policy authority,
   and `claim-eligible:false`;
9. the delayed label is either observed by horizon or explicitly remains
   pending with a valid due turn; no nonselected alternative receives a label;
10. event schema validation, cold/incremental checks, store hashes, and terminal
    counters pass without warnings.

## Safety stops

Stop and reject the pilot on any stale revision, changed arm proof, ambiguous
candidate/action binding, missing current native route, source-garrison guard,
overlapping actor resource, packet or commit failure, unexpected action type,
action rejection, missing episode, truth mutation, flow activation, or claim
eligibility.

## Decision after the pilot

If the pilot fails, repair the mechanism and rerun under a new preregistration.
If it passes, use it only to confirm mechanics and estimate opportunity yield.
A larger randomized collection cohort requires a separate frozen design with
independent assignment seeds, game/actor lineage clustering, minimum effective
sample size, confidence intervals, and no reuse of PR51/PR52 outcomes.

## Frozen outcome

PR52 was rejected before gameplay. The harness produced zero completed games
and classified the attempt as an infrastructure failure because its startup
validator referenced the runtime object before runtime construction. No engine
action, assignment, or outcome was generated. The failed artifact is preserved
at `artifacts/freeciv/fdas-randomized-execution-pilot-v1`; the one-line ordering
defect was corrected in commit `26ae8fd`. PR52 is not resumed or overwritten.

