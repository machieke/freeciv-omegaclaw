# FDAS PR76 calibrated-equivalence Pareto opportunity preregistration

Date: 2026-08-03

## Question and frozen boundary

PR75 confirmed readout `1.2` on a known high-yield seed. PR76 freezes the same
candidate surface, scalar PF-v2 scores, calibration artifact, safety and target
filters, additions-only union, ruleset defensive comparator, interval route,
equivalence-Pareto route, and zero-authority boundary. It estimates how often
the new preference appears on unseen seeds.

Mechanical acceptance does not require a preference. Grounded-alternative,
strict-improvement, and equivalence-Pareto preference game rates are reported
separately with descriptive 95% Wilson intervals. A zero at any stage is a
valid named result.

## Fixed unseen cohort

The 16 fixed seeds are:

`109447, 109453, 109459, 109471, 109483, 109489, 109501, 109507, 109519, 109531, 109537, 109549, 109561, 109567, 109579, 109591`.

No seed may be substituted, added, removed, retried, resumed, or reclassified.
PR75 and earlier games cannot be pooled into the primary result.

## Frozen gates

All exact games must complete from one clean source identity and pass inherited
endpoint, ledger, counter, filter, target, union, semantic readout, rejection,
and authority checks. Every scalar event must use readout `1.2`, and at least
one scalar event must be observed. Yield is measured, not required.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr76-calibrated-equivalence-pareto-opportunity-v1 \
  --config profile/freeciv_harness_fdas_pr76_calibrated_equivalence_pareto_opportunity_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --seed-offset 41 --limit-seeds 16 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_calibrated_equivalence_pareto_opportunity.py \
  artifacts/freeciv/fdas-pr76-calibrated-equivalence-pareto-opportunity-v1 \
  --expected-seed 109447 --expected-seed 109453 \
  --expected-seed 109459 --expected-seed 109471 \
  --expected-seed 109483 --expected-seed 109489 \
  --expected-seed 109501 --expected-seed 109507 \
  --expected-seed 109519 --expected-seed 109531 \
  --expected-seed 109537 --expected-seed 109549 \
  --expected-seed 109561 --expected-seed 109567 \
  --expected-seed 109579 --expected-seed 109591 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr76-calibrated-equivalence-pareto-opportunity.json
```

## Claim boundary

A mechanically accepted result estimates non-authorizing preference yield only.
It establishes no counterfactual ranking quality, treatment effect, gameplay
impact, score improvement, or win rate.
