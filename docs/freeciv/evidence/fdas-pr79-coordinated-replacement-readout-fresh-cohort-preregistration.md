# FDAS PR79 coordinated-replacement fresh recall cohort preregistration

Date: 2026-08-04

## Question

PR78 recalls all 33 grounded replacement candidates on one deliberately reused
opportunity seed. PR79 asks whether that opportunity and exact readout transfer
to independent games. It does not change the implementation or estimate chain
value.

## Frozen cohort

The first 16 seeds in
`freeciv_harness_fdas_pr79_replacement_readout_fresh_cohort_160_turn.yaml`
are new to the repository and fixed before execution:

`109601, 109603, 109607, 109609, 109613, 109617, 109619, 109621, 109623,
109627, 109631, 109633, 109637, 109639, 109643, 109647`.

Sixteen games are a bounded transfer cohort. Using PR76's descriptive
three-of-sixteen grounded-alternative game rate only as a planning assumption,
16 independent games have about 83.1% probability of observing at least two
contributing games. This is not a power calculation for score or outcomes.
No seed will be replaced, retried, or appended if the opportunity gate fails.

## Acceptance

- all 16 games complete from one clean source commit without resume or
  infrastructure failure;
- every game passes the PR77 persistence/lifecycle audit;
- every observed PR78 pair passes exact route, lifecycle, hash, and
  zero-authority checks;
- zero-opportunity games remain valid and are reported as zero rather than
  dropped; and
- at least two distinct games contain one or more grounded safe-chain pairs.

The game is the independent unit for the reported recall rate. Pair rows within
one game are not treated as independent samples. The report includes the
descriptive 95% Wilson interval for the opportunity-game rate.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr79-coordinated-replacement-readout-fresh-cohort-v1 \
  --config profile/freeciv_harness_fdas_pr79_replacement_readout_fresh_cohort_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --limit-seeds 16 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_replacement_readout_cohort.py \
  artifacts/freeciv/fdas-pr79-coordinated-replacement-readout-fresh-cohort-v1 \
  --expected-seeds 109601,109603,109607,109609,109613,109617,109619,109621,109623,109627,109631,109633,109637,109639,109643,109647 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr79-coordinated-replacement-readout-fresh-cohort.json
```

The final audit is rerun to a temporary path and compared byte-for-byte.

## Claim boundary

A pass establishes fresh-game candidate-recall transfer only. It makes no
calibrated transition-value, preference, action, causal relief, score, or
win-rate claim. A failure is preserved and does not authorize seed expansion.
