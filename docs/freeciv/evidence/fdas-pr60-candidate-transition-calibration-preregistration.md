# FDAS PR60 candidate-transition calibration preregistration

## Question and frozen boundary

PR59 proves that exact-turn route and source mechanics distinguish grounded
reinforcement candidates, while the frozen PR40 model necessarily collapses
them to one lifecycle estimate. PR60 asks a narrower question: can selected
reinforcement outcomes support a hierarchical, candidate-specific predictive
model on untouched games?

The model remains selected-only and observational. A nonselected candidate is
still censored, so even a passing confirmation cannot establish its
counterfactual outcome or authorize candidate ranking. The model, fitter,
validator, and reports all deny truth, policy, and readout authority. PR40 and
PR58 remain frozen; the existing scalar controller continues to select every
action during both cohorts.

## Frozen model

Only `fdas-shadow:city-garrison-deficit:unit_move` rows with PR59 schema
`fdas-candidate-transition-features/1.0` and complete grounding enter the fit.
Sequential observations are collapsed to the durable game-local candidate
lineage before estimating support. Fortification and incomplete rows cannot
enter this model.

The hierarchy is fixed from broad to specific:

1. action;
2. lifecycle;
3. ETA;
4. ETA + lifecycle;
5. unit type + ETA + source-city relation;
6. the preceding route stratum + lifecycle;
7. compact mechanics: route stratum + total-cost band + source-support band;
8. compact mechanics + lifecycle;
9. every grounded transition feature; and
10. every grounded transition feature + lifecycle.

Prediction searches in reverse order and uses the first supported bin. Frozen
minimum independent lineages are respectively `12, 10, 12, 10, 10, 8, 8, 6,
6, 5`. Each child uses four parent-equivalent pseudo-observations to shrink its
center toward the exact parent. Its Wilson interval width is still computed at
the child's actual lineage N, so the prior cannot manufacture independent
precision. An unseen fine stratum backs off; it is never synthesized.

## Frozen discovery cohort and yield gates

The first 12 seeds in
`profile/freeciv_harness_fdas_pr60_transition_calibration_160_turn.yaml` are
discovery only:

`108023, 108037, 108041, 108053, 108061, 108079, 108089, 108107, 108109,
108127, 108131, 108139`.

Every game must pass the PR59 feature auditor and parent PR58 mechanics audit.
The complete cohort must contain at least:

- 12 observed selected move outcomes;
- 3 positive and 8 negative selected move outcomes;
- 8 independent observed move lineages;
- 6 games with an observed move outcome;
- 6 selected grounded transition signatures; and
- 12 multi-move choice sets with distinct grounded signatures.

Failure of any gate stops fitting. The thresholds and hierarchy may not be
changed after the discovery outcome is inspected.

## Frozen confirmation cohort and gates

Seeds at offsets 12-23 are untouched confirmation only:

`108161, 108179, 108187, 108191, 108193, 108203, 108211, 108217, 108223,
108233, 108247, 108263`.

The remaining six profile seeds are reserved and cannot be added to either
cohort after execution starts.

They must pass the same feature and outcome-yield gates. The frozen discovery
model then must pass all of:

- at least 80% prediction coverage;
- at least 12 held-out effective lineages;
- at least 25% candidate-specific (more specific than action/lifecycle)
  predictions;
- at least 2 distinct prediction values;
- Brier score at most `0.30`;
- log loss at most `0.85`;
- calibration-in-the-large error at most `0.20`;
- predicted mean inside the held-out empirical Wilson 95% interval; and
- game-clustered Brier improvement versus action-only with 95% interval lower
  bound at least `-0.05` (`2,000` bootstrap samples, seed `16061`).

This final gate is noninferiority, not superiority. Passing would permit a
separate shadow readout-yield design. It would not prove censored alternative
value, ranking quality, gameplay impact, score improvement, or win rate.

## Frozen execution

Discovery:

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr60-transition-calibration-discovery-v1 \
  --config profile/freeciv_harness_fdas_pr60_transition_calibration_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --limit-seeds 12 --condition e_full_loop --main-only --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/fit_fdas_candidate_transition_calibration.py \
  artifacts/freeciv/fdas-pr60-transition-calibration-discovery-v1 \
  --output docs/freeciv/evidence/fdas-pr60-candidate-transition-calibration-discovery.json \
  --discovery-id fdas_candidate_transition_calibration_discovery_v1 \
  --model-id fdas_candidate_transition_calibration_v1 \
  --expected-source-commit "$SOURCE_COMMIT" \
  $(for seed in 108023 108037 108041 108053 108061 108079 108089 108107 108109 108127 108131 108139; do printf ' --expected-seed %s' "$seed"; done)
```

Confirmation may start only after a passing discovery artifact:

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr60-transition-calibration-confirmation-v1 \
  --config profile/freeciv_harness_fdas_pr60_transition_calibration_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --seed-offset 12 --limit-seeds 12 --condition e_full_loop \
  --main-only --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/validate_fdas_candidate_transition_calibration.py \
  artifacts/freeciv/fdas-pr60-transition-calibration-confirmation-v1 \
  --model docs/freeciv/evidence/fdas-pr60-candidate-transition-calibration-discovery.json \
  --output docs/freeciv/evidence/fdas-pr60-candidate-transition-calibration-confirmation.json \
  --confirmation-id fdas_candidate_transition_calibration_confirmation_v1 \
  --expected-source-commit "$SOURCE_COMMIT" \
  $(for seed in 108161 108179 108187 108191 108193 108203 108211 108217 108223 108233 108247 108263; do printf ' --expected-seed %s' "$seed"; done)
```

## Stop rules

- Do not replace, extend, pool, or reclassify seeds after execution starts.
- Do not use seed `108013`, the failed `24ee0b3` integration attempt, PR56,
  PR40, or PR42 outcomes to fit PR60.
- Do not change features, hierarchy, prior, support, yield, or validation gates
  after inspecting either cohort.
- Preserve a failed discovery or confirmation as failed evidence.
- Do not load the PR60 model into the live candidate union or PR58 readout in
  this phase.
