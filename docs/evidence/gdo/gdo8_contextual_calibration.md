# GDO-8 contextual calibration and conductance

## Result

The support-aware contextual calibration implementation passes its synthetic
mechanism gate. It corrects a controlled category-level negative-transfer
regime while preserving strict context, ruleset, estimator-version, and
policy-version boundaries.

The deterministic diagnostic uses four contexts in two categories. Each
category contains contexts with opposite residuals, so category-only pooling
cancels the useful correction. A frozen v2 model is fitted on 160 causally
eligible outcomes and evaluated on 100 disjoint holdout outcomes.

| Metric | Simpler raw/category-neutral baseline | Contextual v2 |
|---|---:|---:|
| Brier score | 0.305400 | 0.000420 |
| supported holdout coverage | — | 100% |
| mean Brier improvement | — | 0.304980 |
| 95% bootstrap improvement interval | — | [0.293274, 0.316671] |

All four supported contexts have causal conductance observations and none
exceeds the predeclared per-context Brier-regression tolerance.

## Frozen thresholds

These thresholds are declared before any engine-backed v2 confirmation:

- minimum direct support: 30 eligible outcomes;
- maximum confidence half-width: 0.50;
- confidence alpha: 0.05;
- parent shrinkage kappa: 10;
- minimum intended-slice holdout coverage: 80%;
- maximum supported high-volume context Brier regression: 0.02;
- deterministic bootstrap samples: 2,000;
- aggregate 95% bootstrap interval must exclude zero improvement.

The support count and confidence defaults retain the already-declared v1
transition-value thresholds. Coverage, per-context tolerance, and bootstrap
criteria instantiate the numerical GDO-8 gate before a live v2 cohort exists.
They must not be changed after seeing a confirmation cohort.

## Context and backoff contract

`ContextualTransitionValueKey` uses this exact declared chain:

1. exact semantic context;
2. action + actor/target class + threat/horizon bucket + lifecycle;
3. action + actor class;
4. action category;
5. global prior.

Every level is also isolated by goal, ruleset family, estimator version, and
policy version. The two most specific levels additionally require the exact
ruleset digest. A query can use only one of these declared parents; it cannot
silently pool an unrelated bucket.

Legacy schema-v1 observations can be imported only as visibly tagged category
priors. They are not rewritten as v2 outcomes, do not contribute direct v2
support counts, and cannot make an exact or parent context authoritative.

## Outcome and conductance contract

Each v2 outcome records:

- semantic context, estimator version, and policy version;
- selected policy and propensity when stochastic;
- action and operation identities;
- predicted transition identity and predicted relief;
- authoritative realized outcome and goal relief;
- adverse loss or an explicit unknown status;
- causal eligibility trace;
- terminal, no-effect, or unknown status.

Unknown and causally ineligible outcomes are retained for audit but excluded
from calibration. Unknown adverse loss is not coerced to zero: it may calibrate
authoritative goal relief but cannot contribute contextual conductance support.
Conductance is bounded realized goal relief minus observed adverse loss; it is
therefore causal effectiveness, not route popularity or activation frequency.

The live readout uses calibrated realized-relief bounds and reports
conductance separately. It does not multiply both values and double-count the
same effect.

## Runtime safety

The new runtime layer is default off. Shadow collection requires:

- scalar-v2 semantics;
- grounded domain estimates;
- the contextual v2 schema.

Authority additionally requires:

- an explicit read-only model path and identity;
- a disjoint held-out Brier report whose hash binds it to that exact model
  state;
- all predeclared gates passing;
- exact commit revalidation.

Legacy transition-value and contextual-v2 calibration cannot run together.
Evaluation cannot update the frozen model. Path persistence may consume either
an approved legacy transition model or an approved contextual-v2 model.

## Reproduction

```sh
PYTHONPATH=.:src:benchmarks \
  python3 scripts/run_gdo_contextual_calibration_diagnostic.py

PYTHONPATH=.:src:benchmarks python3 -m pytest -q \
  Autotests/test_freeciv_contextual_transition_value.py \
  Autotests/test_freeciv_transition_model_training.py \
  Autotests/test_freeciv_teleological_impact.py \
  Autotests/test_freeciv_pf_runtime.py \
  Autotests/test_freeciv_transition_value.py
```

The canonical result is
`benchmarks/gdo/gdo8_contextual_calibration_diagnostic.json`.

The complete FreeCiv subsystem regression passed after implementation:
1,017 tests in 328.36 seconds using
`PYTHONPATH=.:src:benchmarks python3 -m pytest -q
Autotests/test_freeciv*.py`.

## Engine confirmation

The frozen thresholds above were subsequently applied without retuning to two
clean, claim-ineligible engine cohorts:

- 30 training seed pairs / 60 arms;
- 30 disjoint holdout seed pairs / 60 arms;
- 60 turns per arm;
- three declared controller workers;
- zero gameplay or infrastructure failures.

The training treatment traces produced 1,587 eligible contextual outcomes.
The frozen model supports 38 of 43 observed training keys through the declared
exact-to-parent hierarchy. The disjoint holdout contains 1,831 eligible
outcomes:

| Metric | Raw grounded prediction | Frozen contextual v2 |
|---|---:|---:|
| Brier score | 0.267491 | 0.041237 |
| supported holdout coverage | — | 100% |
| mean Brier improvement | — | 0.226254 |
| 95% bootstrap improvement interval | — | [0.210036, 0.242391] |

Every predeclared gate passes. Training and holdout seed sets are disjoint,
their clean source identities match, the model is immutable during evaluation,
and the approval hash binds the holdout report to the exact model state.

The canonical engine audit is
`benchmarks/gdo/gdo8_contextual_engine_confirmation.json`. The frozen model,
training provenance, and approval bundle are:

- `docs/freeciv/evidence/gdo8-contextual-transition-training-v1-model.json`;
- `docs/freeciv/evidence/gdo8-contextual-transition-training-v1-report.json`;
- `docs/freeciv/evidence/gdo8-contextual-transition-holdout-v1-approval.json`.

## Claim boundary and next evidence

The synthetic result proves context isolation, declared backoff, strict
migration, and controlled negative-transfer correction. The engine result
additionally establishes a disjoint selected-action prediction-calibration
improvement under the frozen gate.

This is not an off-policy value estimate and does not prove that changing live
candidate order improves Freeciv score or win rate. Contextual authority
remains default-off. The approved bundle may now be exercised only in a fresh,
claim-ineligible authority diagnostic; a gameplay claim would require a
separate frozen pilot and confirmation.
