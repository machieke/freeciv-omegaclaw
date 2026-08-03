# FDAS PR74 ruleset-defensive opportunity cohort preregistration

Date: 2026-08-03

## Question and frozen boundary

PR73 confirmed readout `1.1` on a known opportunity but could not estimate how
often comparable candidates appear. PR74 freezes the same scalar PF-v2 model,
calibration artifact, safety filter, target scope, additions-only recall,
ruleset defensive comparator, interval gate, and zero-authority boundary. No
threshold, ranking, candidate generation, or gameplay behavior changes.

The cohort measures these stages independently:

1. a grounded same-target alternative reaches the readout;
2. control and alternative have different unit types;
3. the cross-type pair passes all ruleset defensive capability checks;
4. the alternative is noninferior on every grounded check;
5. calibrated intervals separate; and
6. a shadow preference is emitted.

Mechanical acceptance does not require positive yield. A zero at any stage is
a valid, named scientific result rather than an infrastructure failure.

## Fixed unseen cohort

The 16 fixed seeds, not used by PR68--PR73 result cohorts, are:

`109313, 109321, 109331, 109337, 109343, 109349, 109357, 109363, 109373, 109379, 109391, 109403, 109411, 109421, 109433, 109439`.

No seed may be substituted, added, removed, retried, resumed, or reclassified.
Earlier cohorts cannot be pooled into the primary result. Game-level grounded
alternative, cross-type, and interval-separation rates receive descriptive 95%
Wilson intervals; these do not turn the cohort into a gameplay claim.

## Frozen gates

All 16 exact games must complete from one clean source identity and pass the
parent endpoint, ledger, counter, filter, target, union, readout, rejection,
and authority checks. At least one scalar readout must occur, and every scalar
readout must use only ruleset-defensive identity `1.1`.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr74-ruleset-defensive-opportunity-v1 \
  --config profile/freeciv_harness_fdas_pr74_ruleset_defensive_opportunity_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --seed-offset 25 --limit-seeds 16 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_ruleset_defensive_opportunity_cohort.py \
  artifacts/freeciv/fdas-pr74-ruleset-defensive-opportunity-v1 \
  --expected-seed 109313 --expected-seed 109321 \
  --expected-seed 109331 --expected-seed 109337 \
  --expected-seed 109343 --expected-seed 109349 \
  --expected-seed 109357 --expected-seed 109363 \
  --expected-seed 109373 --expected-seed 109379 \
  --expected-seed 109391 --expected-seed 109403 \
  --expected-seed 109411 --expected-seed 109421 \
  --expected-seed 109433 --expected-seed 109439 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr74-ruleset-defensive-opportunity.json
```

## Claim boundary

A mechanically accepted cohort estimates opportunity and interval yield only.
It establishes no counterfactual ranking quality, treatment effect, gameplay
impact, score improvement, or win rate and grants no action authority.
