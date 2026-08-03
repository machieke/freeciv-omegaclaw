# FDAS PR69 scalar pair-scope diagnostic preregistration

Date: 2026-08-03

## Question and frozen boundary

PR68 produced 27 calibrated additions and 50 grounded controls but zero
grounded alternatives. All six additions that coincided with a grounded move
control were rejected by the aggregate `pair-scope-mismatch` predicate before
alternative grounding. PR69 asks which exact fail-closed scope predicates are
responsible on fresh games.

PR69 changes rejection observability only. A rejected candidate remains
rejected when any existing predicate is true. The diagnostic reports duplicate
action, operation-type mismatch, target-ref mismatch, identical resource set,
and each exact overlapping resource separately. The PR60 model, PR67 filter,
protected union, scalar baseline, interval and noninferiority gates, action
output, and every authority declaration remain unchanged.

## Cohort size and fixed seeds

Three of eight PR68 games descriptively contained at least one addition paired
with a grounded move control. This is used only to size a diagnostic cohort.
At an assumed three-eighths contributing-game probability, eight fresh games
have `1 - (5/8)^8 = 0.9767` probability of containing at least one such event.

The fixed fresh seeds are:

`109133, 109139, 109141, 109147, 109159, 109169, 109171, 109199`.

They are the next eight unused entries in the committed PR67 profile. No seed
may be added, removed, substituted, retried, resumed, or reclassified. Prior
games cannot be pooled.

## Frozen gates

All eight games must pass the complete PR67 safety-filter audit. The diagnostic
additionally requires:

- at least one exact pair-scope rejection;
- zero legacy aggregate `pair-scope-mismatch` rejections;
- every exact reason to use a registered predicate form; and
- at least one exact resource-overlap rejection.

No scope relaxation, grounded alternative, interval comparison, preference, or
action change is required.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr69-pair-scope-diagnostic-v1 \
  --config profile/freeciv_harness_fdas_pr67_safe_filtered_scalar_readout_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --seed-offset 9 --limit-seeds 8 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_scalar_baseline_pair_scope_diagnostic.py \
  artifacts/freeciv/fdas-pr69-pair-scope-diagnostic-v1 \
  --expected-seed 109133 \
  --expected-seed 109139 \
  --expected-seed 109141 \
  --expected-seed 109147 \
  --expected-seed 109159 \
  --expected-seed 109169 \
  --expected-seed 109171 \
  --expected-seed 109199 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr69-pair-scope-diagnostic.json
```

## Stop and claim boundary

- Preserve any failed game or report as failed evidence.
- Do not inspect partial results or adapt the cohort after execution starts.
- Do not alter scope eligibility, the model, filter, or auditor.
- Do not grant action, policy, truth, readout, flow, or capacity authority.

A pass establishes exact scope-failure observability only. It does not justify
scope relaxation and makes no alternative-grounding, ranking, counterfactual,
gameplay, score, or win-rate claim.
