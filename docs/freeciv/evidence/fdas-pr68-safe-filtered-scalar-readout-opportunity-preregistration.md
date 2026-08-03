# FDAS PR68 safety-filtered scalar readout opportunity preregistration

Date: 2026-08-03

## Question and frozen boundary

PR67 established the correctness of the pre-union safety filter but its single
fresh game contained no safety-eligible move. PR68 asks only whether the exact
PR67 implementation yields a real, grounded comparison between its safe scalar
control and at least one protected calibrated alternative in a prospectively
sized fresh cohort.

The PR60 transition model, PR63 confirmation, PR67 safety filter, scalar
baseline, calibrated recall rules, interval estimates, bounded validators,
manifest, profile, and all authority declarations remain frozen. The complete
observational choice surface remains available for censored records; only the
calibrated readout union is safety-filtered. No active policy, action selection,
truth, flow, or capacity behavior changes.

## Cohort size and fresh seeds

Across the separate PR65, PR66, and PR67 diagnostic games, one of three games
descriptively contained a grounded safe move control. This is not a performance
estimate. It is used only as a prospective engineering sizing assumption: at a
one-third contributing-game probability, eight fresh games have
`1 - (2/3)^8 = 0.961` probability of containing at least one contributing
game.

The fixed eight seeds are:

`109037, 109049, 109063, 109073, 109097, 109103, 109111, 109121`.

They are the next eight entries after PR67's consumed seed in the already
committed schema-valid profile. No seed may be substituted, removed, added,
retried, resumed, or reclassified after collection begins. PR65--PR67 games
cannot be pooled into this cohort.

## Frozen mechanics and opportunity gates

Every game must pass the complete PR67 audit, including clean source identity,
terminal or horizon endpoint, valid warning-free event ledger, zero rejected
actions, exact profile and manifest, matching runtime counters, complete
candidate partitioning, exclusion of every protected-source-garrison move,
and proof that every union member belongs to the immediately preceding
safety-eligible partition.

The complete cohort must additionally contain:

- at least one candidate-specific safe union prediction;
- at least one grounded safety-filtered scalar control;
- at least one calibrated candidate added beyond safe scalar top-1;
- at least one grounded protected alternative compared by the readout; and
- at least one game containing such a grounded protected alternative.

A separated interval, shadow preference, or action change is not required. The
cohort auditor is committed before execution and requires exactly these eight
unique seeds.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr68-safe-filtered-scalar-readout-opportunity-v1 \
  --config profile/freeciv_harness_fdas_pr67_safe_filtered_scalar_readout_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --seed-offset 1 --limit-seeds 8 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_safe_filtered_scalar_readout_cohort.py \
  artifacts/freeciv/fdas-pr68-safe-filtered-scalar-readout-opportunity-v1 \
  --expected-seed 109037 \
  --expected-seed 109049 \
  --expected-seed 109063 \
  --expected-seed 109073 \
  --expected-seed 109097 \
  --expected-seed 109103 \
  --expected-seed 109111 \
  --expected-seed 109121 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr68-safe-filtered-scalar-readout-opportunity.json
```

## Stop rules and claim boundary

- Preserve any failed game or cohort report as failed evidence.
- Do not inspect partial outcomes or adapt the cohort after execution starts.
- Do not change the model, filter, readout, thresholds, endpoint, or auditor.
- Do not rerun or replace a failed, sparse, or terminal seed.
- Do not grant the filter, union, or readout live authority.

A pass establishes fresh safety-filtered grounded-alternative comparison yield
only. It does not establish correct ranking, censored counterfactual value,
causal benefit, gameplay impact, score improvement, or win rate.
