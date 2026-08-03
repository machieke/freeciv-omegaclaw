# FDAS PR63 candidate-transition calibration confirmation preregistration

Date: 2026-08-03

## Question and frozen boundary

PR63 asks whether the exact PR60 grounded transition model passes its original
yield and predictive gates on fresh games under the prospectively corrected
feature audit 2.0. Audit 2.0 was implemented and committed before any PR63
gameplay is collected.

This phase does not refit or alter the model. Feature schema, selected-actor
outcome target, lineage collapse, hierarchy, shrinkage strength, minimum bin
support, validation thresholds, endpoint rules, and the scalar controller all
remain frozen. PR60 and PR61 data cannot be pooled into this cohort.

## Cohort size and fresh seeds

The cohort remains 30 games. PR61 showed that this size can comfortably clear
the unchanged independent-yield thresholds, but PR63 does not reduce the size
after seeing that result. The fixed seeds are:

`108727, 108739, 108751, 108761, 108769, 108791, 108793, 108799, 108803,
108821, 108827, 108863, 108869, 108877, 108881, 108883, 108887, 108893,
108907, 108917, 108923, 108929, 108943, 108947, 108949, 108959, 108961,
108967, 108971, 108991`.

They are disjoint from PR59, every PR60 seed including reserves, and PR61. No
seed may be substituted, removed, added, resumed, or reclassified after
collection begins. Every row must originate from one clean source commit.

## Frozen mechanics audit

Feature audit 2.0 requires every game to pass all row invariants:

- candidate store validity;
- complete transition schema for every present move row;
- zero incomplete or imputed move grounding;
- byte-identical PR40 predictions;
- frozen fortify queries;
- no recorded audit error; and
- passing parent PR58/source/endpoint/authority mechanics.

The complete cohort must contain a move, a multi-move choice set, a diverse
multi-move set, and at least two transition signatures. The separate unchanged
yield gate remains much stricter.

## Frozen yield and predictive gates

The exact PR60 discovery model is
`docs/freeciv/evidence/fdas-pr60-candidate-transition-calibration-discovery.json`,
model result hash
`edca977ffc87f9e731e00d5b5bacf3be03e1d5f28887e51e86966cb975ee3aa5`.

All original outcome-yield gates must pass:

- at least 12 observed selected move outcomes;
- at least 3 positive and 8 negative move outcomes;
- at least 8 independent observed move lineages;
- at least 6 games with an observed move outcome;
- at least 6 selected grounded transition signatures; and
- at least 12 multi-move choice sets with distinct grounded signatures.

All original predictive gates must pass:

- prediction coverage at least `0.80`;
- at least 12 held-out effective lineages;
- candidate-specific prediction fraction at least `0.25`;
- at least 2 distinct prediction values;
- Brier score at most `0.30`;
- log loss at most `0.85`;
- calibration error at most `0.20`;
- mean prediction inside the empirical Wilson 95% interval; and
- game-clustered Brier improvement over action-only with 95% interval lower
  bound at least `-0.05`, using 2,000 samples and bootstrap seed `16061`.

The primary report passes only when mechanics, yield, and predictive gates all
pass.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr63-transition-calibration-confirmation-v1 \
  --config profile/freeciv_harness_fdas_pr63_transition_calibration_confirmation_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/validate_fdas_candidate_transition_calibration_cohort.py \
  artifacts/freeciv/fdas-pr63-transition-calibration-confirmation-v1 \
  --model docs/freeciv/evidence/fdas-pr60-candidate-transition-calibration-discovery.json \
  --output docs/freeciv/evidence/fdas-pr63-candidate-transition-calibration-confirmation.json \
  --confirmation-id fdas_candidate_transition_calibration_confirmation_v2 \
  --expected-source-commit "$SOURCE_COMMIT" \
  $(for seed in 108727 108739 108751 108761 108769 108791 108793 108799 108803 108821 108827 108863 108869 108877 108881 108883 108887 108893 108907 108917 108923 108929 108943 108947 108949 108959 108961 108967 108971 108991; do printf ' --expected-seed %s' "$seed"; done)
```

## Stop rules and claim boundary

- Preserve any failed engine row or primary report as failed evidence.
- Do not inspect partial outcomes or metrics.
- Do not change the cohort, audit, model, or thresholds after execution starts.
- Do not retry or replace a failed or terminal seed.
- Do not load the model into any live readout during this phase.

A pass establishes held-out selected-action predictive calibration under the
corrected mechanics audit and permits a separate default-off shadow readout-
yield experiment. It still does not identify censored alternative outcomes or
establish ranking quality, action authority, gameplay impact, score, or win
rate.
