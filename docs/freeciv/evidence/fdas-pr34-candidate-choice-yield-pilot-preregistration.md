# FDAS PR34 candidate-choice yield pilot preregistration

Status: frozen before engine execution; claim-ineligible mechanism/yield pilot.

## Purpose

PR33 proves that selected candidate outcomes can be recorded without turning
rejected alternatives into failures. This pilot measures whether ordinary
160-turn games produce enough same-decision candidate variation and outcome
contrast to justify fitting a candidate-specific transition-value model.

It does not fit, select, tune, or evaluate a model. It grants no truth,
readout, policy, or action authority and makes no gameplay, score, or win-rate
claim.

## Frozen design

| Field | Declaration |
|---|---|
| Cohort ID | `fdas_candidate_choice_yield_pilot_v1` |
| Backend | `engine-live` |
| Ruleset | `civ2civ3` |
| Horizon | 160 turns |
| Condition | `e_full_loop` only |
| Seeds | `104743`, `104759`, `104761` |
| Model | `qwen3-coder-next:latest`, temperature 0, thinking disabled |
| FDAS profile | `fdas_manifest_defense_actor_persistence_candidate_impact_shadow.json` |
| Outcome | `durable-attributed-actor-city-defense/32-turn/1.0` |
| Action category | `fdas-shadow:unit-fortification-opportunity:unit_fortify` |
| Resume | disabled |
| Workers | 1, dedicated serial process recycle |

These seeds are a development-yield sample and are excluded from any later
confirmation claim. Results will not change the frozen PR29/PR30 model.

## Mechanical acceptance gates

All must pass:

1. all three games complete the horizon without infrastructure failure;
2. every event ledger validates with zero errors and warnings;
3. every engine has zero rejected actions;
4. every choice store loads without quarantine and has a current digest;
5. all feature queries are outcome-free;
6. all nonselected choices are explicitly `nonselected-censored`;
7. each exported training row corresponds to one observed selected choice;
8. no truth, readout, policy, or action-selection authority is granted by the
   candidate-choice component; and
9. source identities are identical and clean for all games.

## Descriptive yield measures

Report without optimization:

- choice sets and candidates per game;
- same-decision multi-candidate choice sets;
- in-scope selections and out-of-scope censored sets;
- observed, pending, and otherwise censored selected outcomes;
- positive and negative selected outcomes;
- distinct selected feature signatures;
- distinct selected actor/context signatures; and
- outcome yield per engine hour.

## Progression gate

A later candidate-specific discovery cohort may be designed only if this pilot
contains all of:

- at least 12 observed selected outcomes;
- at least two positive and two negative selected outcomes;
- at least three multi-candidate choice sets; and
- at least three distinct selected actor/context signatures.

These thresholds assess whether the data-generating regime is usable; they do
not establish calibration or ranking improvement. If any threshold fails, do
not fit on this pilot and do not retune the flow controller. Diagnose the
candidate materialization, selection policy, or delayed target first.

## Planned command

```bash
FREECIV_RULESET_ROOT=/path/to/freeciv/data \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_actor_persistence_causal_induction_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_actor_persistence_candidate_impact_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-candidate-choice-yield-pilot-v1 \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --seed-offset 1 --limit-seeds 3 --condition e_full_loop \
  --main-only --no-resume
```
