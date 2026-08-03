# FDAS PR38 action-family yield preregistration

Status: frozen before engine execution; claim-ineligible independent-yield
gate.

## Purpose and exclusion

PR37 repaired selected-action recall and route-step attribution but its
repeated seed produced only one independently grouped observed move lineage.
This fresh cohort tests whether both action strata produce enough independent
observed support to justify designing a calibrated discovery split.

No model is fit, tuned, selected, or evaluated here. Seeds from PR34–PR37 are
excluded. These PR38 seeds will also be excluded from later held-out model
confirmation.

## Frozen design

| Field | Declaration |
|---|---|
| Cohort ID | `fdas_defense_action_family_yield_v1` |
| Backend | `engine-live` |
| Ruleset | `civ2civ3` |
| Horizon | 160 turns |
| Condition | `e_full_loop` only |
| Seeds | `104803`, `104827`, `104831`, `104849` |
| Source | one identical clean commit after this preregistration |
| Model | `qwen3-coder-next:latest`, temperature 0, thinking disabled |
| FDAS profile | `fdas_manifest_defense_choice_surface_shadow.json` |
| Surface | exact legal, unambiguous move/fortify action bindings |
| Outcome | 32-turn selected-actor city-defense persistence v2 |
| Resume/workers | disabled; one serial worker |

## Mechanical gates

All four games must complete the horizon without infrastructure failure or
rejected actions. Every event ledger must validate without errors or warnings.
All source identities must be identical and clean. Choice stores must be
independent, current, non-quarantined, outcome-free, selected-only, explicitly
censored for alternatives, and non-authorizing. The exact surface, action
families, and outcome target must match the manifest.

## Frozen progression gates

All must pass before a model-discovery design is allowed:

- at least 16 observed selected outcomes;
- at least four positive and four negative outcomes;
- at least five multi-candidate sets;
- at least five mixed move/fortify sets;
- at least two selected actions in each action stratum;
- at least two selected `(game, actor, action stratum)` lineages per stratum;
- at least two observed `(game, actor, action stratum)` lineages per stratum;
  and
- at least five distinct selected actor/context signatures.

Raw route steps from one actor may contribute descriptive rows but cannot
satisfy the lineage gates independently. Censored alternatives are never
negative examples.

Failure stops progression. Do not lower thresholds, extend this cohort, pool
the inspected PR37 seed, or retune policy. Passing establishes only that a
future observational discovery cohort is feasible; it does not establish a
causal counterfactual, calibration, ranking safety, gameplay improvement,
score, or win rate.

## Frozen command

```bash
FREECIV_RULESET_ROOT=/path/to/freeciv/data \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_choice_surface_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_choice_surface_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-defense-action-family-yield-v1 \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --seed-offset 8 --limit-seeds 4 --condition e_full_loop \
  --main-only --no-resume
```

Frozen audit invocation:

```bash
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_candidate_choice_yield.py \
  artifacts/freeciv/fdas-defense-action-family-yield-v1 \
  --pilot-id fdas_defense_action_family_yield_v1 \
  --expected-seed 104803 --expected-seed 104827 \
  --expected-seed 104831 --expected-seed 104849 \
  --require-surface-strata \
  --minimum-observed-selected-outcomes 16 \
  --minimum-observed-each-outcome 4 \
  --minimum-multi-candidate-sets 5 \
  --minimum-mixed-operation-type-sets 5 \
  --minimum-selected-each-operation-type 2 \
  --minimum-selected-operation-type-lineages 2 \
  --minimum-observed-operation-type-lineages 2 \
  --minimum-actor-context-signatures 5
```
