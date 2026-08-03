# FDAS PR42 candidate-calibration confirmation preregistration

Status: frozen before engine execution; held-out predictive confirmation only.

## Purpose and exclusions

PR40 fit a selected-only action/lifecycle model on ten discovery seeds. PR41
implemented the held-out evaluator before accessing the eight seeds reserved
here. This cohort tests whether that exact frozen model remains calibrated on
independent engine games and whether lifecycle conditioning is safely
noninferior to action-only backoff.

All engineering smokes, PR34-PR38 yield cohorts, and PR40 discovery seeds are
excluded. No parameter, bin, threshold, model, lineage definition, or policy
may be changed after outcome inspection. Nonselected candidates remain
censored and cannot become counterfactual labels.

## Frozen design

| Field | Declaration |
|---|---|
| Confirmation ID | `fdas_candidate_calibration_confirmation_v1` |
| Backend | `engine-live` |
| Ruleset | `civ2civ3` |
| Horizon | 160 turns |
| Condition | `e_full_loop` only |
| Seeds | `104971`, `104987`, `104999`, `105019`, `105023`, `105031`, `105037`, `105071` |
| Source | one identical clean commit after this preregistration |
| Model | `qwen3-coder-next:latest`, temperature 0, thinking disabled |
| Calibration artifact | `fdas-pr40-candidate-calibration-discovery.json` |
| Frozen model hash | `9d2af28d765e75cfe3a0aade43be9d5f0a251904f605dd79394db93363a2562a` |
| Surface | exact legal, unambiguous move/fortify action bindings |
| Outcome | 32-turn selected-actor city-defense persistence v2 |
| Lineage | deterministic game + participants + target + action stratum |
| Resume/workers | disabled; one serial worker |
| Bootstrap | 2,000 game-cluster samples, seed `7751` |

## Mechanical and yield gates

All eight games must complete without infrastructure failure or rejected
actions. Event ledgers must validate without errors or warnings. Source
identities must be identical and clean. Stores must be independent,
non-quarantined, selected-only, outcome-free at choice time, explicitly
censored for alternatives, non-authorizing, and disjoint from all discovery
store digests. Every candidate must carry the frozen durable lineage.

The cohort must additionally contain:

- at least 40 observed selected outcomes;
- at least eight positive and eight negative outcomes;
- at least ten multi-candidate sets;
- at least eight mixed move/fortify sets;
- at least five selected actions in each action stratum;
- at least five selected and five observed durable lineages per stratum; and
- at least eight distinct selected actor/context signatures.

## Frozen predictive gates

All gates must pass:

- outcome-blind prediction coverage at least `0.95`;
- lineage-level overall Brier score at most `0.25`;
- lineage-level overall log loss at most `0.75`;
- absolute overall calibration-in-the-large error at most `0.15`;
- absolute calibration error at most `0.25` in each action stratum;
- the frozen mean prediction lies within the empirical Wilson 95% interval in
  each action stratum; and
- the game-clustered 95% lower bound for Brier improvement of lifecycle
  conditioning over action-only backoff is at least `-0.05`.

The final condition is a noninferiority gate, not a superiority claim. Passing
permits design of a protected candidate-union readout in shadow only. It does
not authorize ranking, infer outcomes for censored alternatives, establish a
causal gameplay effect, improve score, or establish win rate. Failure stops
progression; do not lower a threshold, extend the cohort, or refit on these
confirmation outcomes.

## Frozen execution

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_choice_surface_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_choice_surface_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-candidate-calibration-confirmation-v1 \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --seed-offset 22 --limit-seeds 8 --condition e_full_loop \
  --main-only --no-resume
```

Frozen validation invocation:

```bash
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/validate_fdas_candidate_calibration.py \
  artifacts/freeciv/fdas-candidate-calibration-confirmation-v1 \
  --model docs/freeciv/evidence/fdas-pr40-candidate-calibration-discovery.json \
  --output docs/freeciv/evidence/fdas-pr42-candidate-calibration-confirmation.json \
  --yield-output docs/freeciv/evidence/fdas-pr42-candidate-calibration-confirmation-yield.json \
  --confirmation-id fdas_candidate_calibration_confirmation_v1 \
  --expected-model-hash 9d2af28d765e75cfe3a0aade43be9d5f0a251904f605dd79394db93363a2562a \
  --expected-seed 104971 --expected-seed 104987 \
  --expected-seed 104999 --expected-seed 105019 \
  --expected-seed 105023 --expected-seed 105031 \
  --expected-seed 105037 --expected-seed 105071 \
  --bootstrap-samples 2000 --bootstrap-seed 7751 \
  --minimum-observed-selected-outcomes 40 \
  --minimum-observed-each-outcome 8 \
  --minimum-multi-candidate-sets 10 \
  --minimum-mixed-operation-type-sets 8 \
  --minimum-selected-each-operation-type 5 \
  --minimum-selected-operation-type-lineages 5 \
  --minimum-observed-operation-type-lineages 5 \
  --minimum-actor-context-signatures 8 \
  --minimum-prediction-coverage 0.95 \
  --maximum-brier-score 0.25 \
  --maximum-log-loss 0.75 \
  --maximum-calibration-error 0.15 \
  --maximum-action-calibration-error 0.25 \
  --minimum-lifecycle-brier-improvement-ci-lower -0.05
```
