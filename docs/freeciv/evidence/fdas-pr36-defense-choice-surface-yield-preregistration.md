# FDAS PR36 defense choice surface yield preregistration

Status: frozen before engine execution; claim-ineligible discovery-yield gate.

## Purpose

PR35's engineering smoke showed that the cross-action observational surface
can create real same-decision competition and delayed outcome contrast. This
fresh cohort tests whether that yield repeats under clean, identical source
before any selected outcomes are inspected or used to fit a model.

This cohort does not fit, select, tune, or evaluate a transition model. It
grants no truth, readout, policy, action-selection, gameplay, or score
authority. Its seeds are excluded from later confirmation of a fitted model.

## Frozen design

| Field | Declaration |
|---|---|
| Cohort ID | `fdas_defense_choice_surface_yield_v1` |
| Backend | `engine-live` |
| Ruleset | `civ2civ3` |
| Horizon | 160 turns |
| Condition | `e_full_loop` only |
| Seeds | `104773`, `104779`, `104789` |
| Model | `qwen3-coder-next:latest`, temperature 0, thinking disabled |
| FDAS profile | `fdas_manifest_defense_choice_surface_shadow.json` |
| Surface | `fdas-defense-choice-surface/1.0` |
| Action strata | exact legal garrison move and unit fortification |
| Outcome | `durable-selected-actor-city-defense/32-turn/2.0` |
| Resume | disabled |
| Workers | 1, dedicated serial process recycle |

The seeds have not been used by PR35 or the earlier PR34 yield pilot. The
thresholds below were chosen after the PR35 engineering smoke and are frozen
before these seeds run.

## Mechanical acceptance gates

All must pass:

1. all three games complete the horizon without infrastructure failure;
2. every event ledger validates with zero errors and warnings;
3. every engine has zero rejected actions;
4. every choice store loads without quarantine and has a current digest;
5. all feature queries are outcome-free;
6. all nonselected choices are explicitly `nonselected-censored`;
7. each exported row corresponds to one observed selected choice;
8. candidate-choice events grant no truth, readout, policy, or
   action-selection authority;
9. the exact surface and v2 delayed target match this declaration; and
10. all games have identical clean source identities.

## Descriptive measures

Report without optimization:

- choice sets, exact candidates, and selected actions by game;
- multi-candidate and mixed-action-stratum choice sets;
- choices and selections separately for move and fortify strata;
- observed, pending, and otherwise censored selected outcomes;
- positive and negative selected outcomes;
- distinct selected feature and actor/context signatures;
- outcome yield per engine hour; and
- all store, source, event-ledger, and report hashes.

## Progression gate

An action-stratified transition-value discovery split may be designed only if
the mechanically accepted cohort contains all of:

- at least 12 observed selected outcomes;
- at least two positive and two negative selected outcomes;
- at least three multi-candidate choice sets;
- at least three mixed move/fortify choice sets;
- at least two selected actions from each action stratum; and
- at least three distinct selected actor/context signatures.

Failure stops progression. Do not lower thresholds, add same-cohort seeds, fit
on the failed cohort, or retune the flow controller. Diagnose candidate
materialization, episode eligibility, horizon attrition, or action-stratum
imbalance first.

Passing this gate establishes only a usable observational discovery surface.
It does not establish causal effects for nonselected actions, calibrated
ranking, decision safety, gameplay impact, score improvement, or win rate.

## Frozen command

```bash
FREECIV_RULESET_ROOT=/path/to/freeciv/data \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_choice_surface_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_choice_surface_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-defense-choice-surface-yield-v1 \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --seed-offset 4 --limit-seeds 3 --condition e_full_loop \
  --main-only --no-resume
```

Frozen audit invocation:

```bash
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_candidate_choice_yield.py \
  artifacts/freeciv/fdas-defense-choice-surface-yield-v1 \
  --pilot-id fdas_defense_choice_surface_yield_v1 \
  --expected-seed 104773 --expected-seed 104779 --expected-seed 104789 \
  --require-surface-strata
```
