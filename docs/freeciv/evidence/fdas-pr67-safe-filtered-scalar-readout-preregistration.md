# FDAS PR67 safety-filtered scalar readout preregistration

Date: 2026-08-03

## Purpose and correction

PR66 proved that `protected-source-garrison`, not missing route mechanics,
blocked 56 scalar move controls. Those candidates are valid observations of an
unmet reinforcement route but unsafe decision alternatives: moving the actor
would create a source-city defense deficit.

PR67 adds an exact pre-union safety filter. It retains every candidate in the
existing choice-set store for censored observational learning, but only a
candidate that passes its matching bounded fortify or reinforcement validator
can enter the grounded-transition union. Scalar top-1 and calibrated recall
are then computed over that safety-eligible subset. An empty safe subset emits
the filter result and no union or readout.

## Frozen filter contract

Each input candidate produces a hash-bound row containing operation and action
identity, action type, complete blocker set, eligibility status, exact
exclusion reason, and the supporting atom for eligible rows. The aggregate
event partitions every input exactly once and declares:

- the observational candidate surface is preserved;
- only calibrated-union input is filtered;
- action selection, policy, readout, and truth authority remain false; and
- the filter is revision-current and uses the existing bounded validators.

`protected-source-garrison` remains a hard exclusion. It is not added to an
allowlist. The PR60 model, PR63 confirmation, scalar scoring, interval width,
recall bounds, and grounded non-inferiority are unchanged. Flow and capacity
solving remain disabled.

## Fresh engine smoke

Fixed fresh seed `109031` is first in a schema-valid 30-seed profile:

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr67-safe-filtered-scalar-readout-smoke-v1 \
  --config profile/freeciv_harness_fdas_pr67_safe_filtered_scalar_readout_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --condition e_full_loop --main-only --limit-seeds 1 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_safe_filtered_scalar_readout.py \
  artifacts/freeciv/fdas-pr67-safe-filtered-scalar-readout-smoke-v1 \
  --expected-seed 109031 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr67-safe-filtered-scalar-readout-smoke.json
```

The audit passes only if:

- the fixed seed reaches its horizon or a genuine absorbing terminal without
  infrastructure failure or rejected action;
- the clean source, exact profile/manifest, confirmed model, event ledger, and
  counters are valid and warning-free;
- filter-event count equals complete observational choice-set count;
- every candidate is partitioned once with a valid row and exact blockers;
- at least one `protected-source-garrison` candidate is excluded and none is
  eligible;
- every union candidate belongs to its immediately preceding filter's eligible
  set on the same revision;
- at least one safe candidate reaches a union with a candidate-specific
  estimate; and
- at least one safety-filtered scalar control is fully grounded in the readout.

An alternative, interval comparison, or preference is not required in this
one-game correction smoke.

## Stop and claim boundary

- Preserve any failed run or audit as failed evidence.
- Do not retry, replace, add, or remove the fixed seed.
- Do not change the filter, model, thresholds, auditor, or endpoint after
  collection starts.
- Do not use the filter, union, or readout as live action authority.

A pass establishes exact safety filtering and safe control mechanics only. It
makes no preference, ranking, counterfactual outcome, gameplay, score, or win-
rate claim.
