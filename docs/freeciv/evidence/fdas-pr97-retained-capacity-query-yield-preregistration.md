# FDAS PR97 retained-capacity query-enabled yield preregistration

Date: 2026-08-04

## Question

PR96 established deterministic query/episode joins and showed that the reused
PR94 rate for the rare `effect-without-goal-relief` status is too uncertain to
justify launching a discovery or confirmation cohort directly. PR97 asks a
narrower prospective question: in 64 fresh query-enabled games, how often do
retained-capacity queries open, become terminal, remain censored, and enter
each terminal outcome class?

This is the fixed mechanics/yield pilot required by PR96. Its rows are excluded
from model fitting and from any later confirmation cohort.

## Frozen cohort

The profile
`profile/freeciv_harness_fdas_pr97_retained_capacity_query_yield_160_turn.yaml`
declares exactly these 64 seeds:

`130003, 130021, 130027, 130043, 130051, 130057, 130069, 130073,
130079, 130087, 130099, 130121, 130127, 130147, 130171, 130183,
130199, 130201, 130211, 130223, 130241, 130253, 130259, 130261,
130267, 130279, 130303, 130307, 130337, 130343, 130349, 130363,
130367, 130369, 130379, 130399, 130409, 130411, 130423, 130439,
130447, 130457, 130469, 130477, 130483, 130489, 130513, 130517,
130523, 130531, 130547, 130553, 130579, 130589, 130619, 130621,
130631, 130633, 130639, 130643, 130649, 130651, 130657, 130681`.

Before registration, one exact-token scan found no occurrence of any seed in
versioned FDAS profiles, preregistrations, evidence, or instructions, nor in
the manifests of locally retained FreeCiv artifacts. The ascending primes were
chosen mechanically from 130003 onward; no gameplay result informed selection.

All 64 games remain in the denominator. No seed may be replaced, retried,
resumed, or appended because of zero query yield, censoring, terminal status,
game outcome, or infrastructure behavior. A failed or incomplete fixed cohort
is retained as evidence and requires a separately preregistered replacement,
not an in-place rescue.

## Frozen runtime and observation boundary

Each game uses the current 160-turn full-loop engine profile and the unchanged
shadow-live retained-capacity query, outcome, and episode components. Queries
continue to abstain with no estimate, interval, or model ID. Every terminal
episode remains prediction-free and non-authorizing.

The PR96 exporter supplies one exact terminal or right-censored row per query.
A PR97 cohort wrapper may summarize those already-exported rows, but may not
relabel an outcome, drop a zero-query game, impute a censored result, pool
multiple events as independent games, or fit any parameter.

## Frozen summaries

The report records:

- fixed, completed, failed, resumed, and infrastructure-failure game counts;
- games with queries and zero-query games;
- query, terminal, and right-censored row counts;
- games bearing at least one occurrence of each terminal status;
- episode counts for each terminal status;
- 95% Wilson intervals for games with queries, terminal-bearing games,
  right-censored-query-bearing games, and each status-bearing game rate; and
- categorical feature-signature frequencies split by terminal/censored status.

The game is the independence unit for every reported interval. Multiple rows
of one status in one game contribute one status-bearing game. The intervals
are fixed-cohort recurrence descriptions, not population or causal estimates.

After the fixed report is sealed, the existing exact binomial planner is rerun
using PR97 status-bearing game counts. The updated prospective discovery and
confirmation sizes are descriptive planning outputs only. They may be used in
a new preregistration before declaring later seeds; they do not authorize
fitting from this pilot.

## Acceptance criteria

- the source worktree is clean and every game records the same exact commit;
- the run summary declares exactly 64 jobs and 64 completions, zero resumes,
  and zero infrastructure failures;
- every game passes the complete PR95 live audit;
- every query store and capacity episode store is typed, identity-bound,
  digest-valid, and non-quarantined;
- all 64 games, including zero-query games, are retained exactly once;
- every query produces exactly one terminal or right-censored PR96 row;
- every terminal episode is consumed exactly once and no orphan exists;
- all game, seed, operation, label, query, episode, and row identities are
  unique;
- status-bearing counts use one occurrence maximum per game;
- the cohort export and updated yield calculation are byte-identical on a
  second pass; and
- all truth, learning, transition-value, conductance, readout, policy, and
  action authority flags remain false.

There is deliberately no minimum query or terminal recurrence gate. Zero yield
is a scientifically valid result and must not trigger seed replacement.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr97-retained-capacity-query-yield-v1 \
  --config profile/freeciv_harness_fdas_pr97_retained_capacity_query_yield_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --limit-seeds 64 --no-resume
```

The aggregate audit/export command is frozen by the PR97 cohort-wrapper
implementation before launch and must name all 64 seeds and the exact
`SOURCE_COMMIT`.

## Claim boundary

A pass establishes fresh engine-backed query, terminal, censoring, status, and
feature recurrence on this fixed pilot only. It cannot train or validate a
transition-value model, establish causal action value, alter policy, or support
a gameplay, score, or win-rate claim.
