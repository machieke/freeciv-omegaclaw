# FDAS PR71 target-scoped scalar readout preregistration

Date: 2026-08-03

## Correction and frozen boundary

PR70 showed that every PR68 calibrated addition served a different bounded
target than scalar top-1. PR71 keeps the readout's exact same-target and
resource safety rules. It inserts a separate revision-bound filter after the
PR67 safety filter, retaining only candidates with scalar top-1's exact
operation type and target reference for calibrated union/readout input.

The full observational surface and the full safety-filter partition remain
unchanged. The calibrated union is versioned to `1.1` and its single recall
slot now counts additions beyond scalar top-k, so an eligible scalar member
cannot consume the alternative slot. Scalar score and action output remain
unchanged; all filter, union, readout, policy, truth, flow, and capacity
authority remains false.

## Fixed fresh cohort

The eight fixed unused seeds are:

`109201, 109211, 109229, 109253, 109267, 109279, 109297, 109303`.

No seed may be substituted, added, removed, retried, resumed, or reclassified.
Prior cohorts cannot be pooled.

## Frozen gates

All games must pass exact source/profile/manifest, endpoint, ledger, counter,
safety partition, and authority checks. Every union must be the sole child of a
valid target filter, every target filter the sole child of a valid safety
filter, and every union operation must be target-in-scope. The cohort requires:

- an observed cross-target exclusion;
- at least one target scope containing a non-baseline candidate;
- at least one additions-only calibrated recall;
- at least one grounded same-target alternative; and
- at least one game containing a grounded same-target alternative.

Interval separation and preference are not required.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr71-target-scoped-readout-v1 \
  --config profile/freeciv_harness_fdas_pr71_target_scoped_scalar_readout_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --seed-offset 17 --limit-seeds 8 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_target_scoped_scalar_readout.py \
  artifacts/freeciv/fdas-pr71-target-scoped-readout-v1 \
  --expected-seed 109201 --expected-seed 109211 \
  --expected-seed 109229 --expected-seed 109253 \
  --expected-seed 109267 --expected-seed 109279 \
  --expected-seed 109297 --expected-seed 109303 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr71-target-scoped-readout.json
```

## Claim boundary

A pass establishes correct target-scoped protected-comparison yield only. It
does not establish ranking correctness, counterfactual value, gameplay impact,
score improvement, or win rate and grants no action authority.
