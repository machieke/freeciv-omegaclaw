# FDAS PR87 replacement-opportunity funnel preregistration

Date: 2026-08-04

## Question

PR86b produced six matched-observed replacement pairs, one matched-censored
pair, and nine no-opportunity pairs. All nine no-opportunity pairs nevertheless
contained critical garrisons, garrison deficits, and reinforcement routes; none
materialized `unit-coordinated-replacement-for`. PR87 asks where fresh games
lose the exact protected replacement chain. It does not change candidate
construction, ranking, transition value, or action selection.

## Frozen diagnostic

Every revision that receives the existing coordinated-replacement readout also
receives exactly one typed, hash-bound funnel event. The event reports raw
counts and the first applicable stage in this fixed order:

1. `grounded-pair-available`;
2. `no-deficit-target-city`;
3. `no-critical-source-garrison`;
4. `no-safe-replacement-relation`;
5. `no-reinforcement-route`;
6. `no-structural-source-target-join`;
7. `structural-join-not-current-candidate`;
8. `no-protected-direct-control`; or
9. `current-candidate-not-grounded`.

The funnel is `shadow-live`, revision-current, causally downstream of the
existing readout, and explicitly has no truth, policy, readout, transition
value, or action authority. The new activation manifest is an additive copy of
the frozen PR78/PR79 manifest.

## Fixed cohort

The first 16 seeds in
`profile/freeciv_harness_fdas_pr87_replacement_opportunity_funnel_160_turn.yaml`
were absent from repository and artifact evidence when registered:

`110419, 110431, 110437, 110441, 110459, 110477, 110479, 110491, 110501,
110503, 110527, 110533, 110543, 110557, 110563, 110567`.

All 16 games remain in the denominator. No seed is replaced, retried, resumed,
or appended based on its stage distribution. The remaining 14 registered
seeds are reserve-only and are not part of PR87.

## Acceptance criteria

- all 16 games complete from one clean source commit without resume or
  infrastructure failure;
- every game passes the existing lifecycle and candidate-readout audits;
- every readout revision has exactly one typed, hash-valid funnel event;
- every funnel event is causally bound to the same-revision readout and keeps
  all authority/value flags false;
- status and terminal counters match the event ledger exactly;
- every game contributes at least one evaluation; and
- the mutually exclusive stage counts partition all evaluations.

No particular stage frequency is required for mechanical acceptance. Stage
frequencies and game counts are reported descriptively; this prevents a
diagnostic expectation from becoming an outcome-conditioned pass rule.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr87-replacement-opportunity-funnel-v1 \
  --config profile/freeciv_harness_fdas_pr87_replacement_opportunity_funnel_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --limit-seeds 16 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_replacement_opportunity_cohort.py \
  artifacts/freeciv/fdas-pr87-replacement-opportunity-funnel-v1 \
  --expected-seeds 110419,110431,110437,110441,110459,110477,110479,110491,110501,110503,110527,110533,110543,110557,110563,110567 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr87-replacement-opportunity-funnel.json
```

The final audit is rerun to a temporary path and compared byte-for-byte.

## Claim boundary

A pass establishes exhaustive, fresh-game why-not observability for the current
safe replacement relation and readout. It does not establish that broadening
candidate generation is safe, that any candidate has positive transition
value, or that policy, score, or win rate improves.
