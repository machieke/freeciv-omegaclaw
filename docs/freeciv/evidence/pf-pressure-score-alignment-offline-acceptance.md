# PF-PLN score-alignment offline acceptance

Status: implementation acceptance passed; fresh v1 pilot completed and rejected

## Goal

The 100-pair candidate-scoped direct-completion confirmation established a
precise null score result: +0.03 points at turn 60, 95% interval
[-0.25, 0.31], exact paired sign-flip p=0.8912. Exact replay also showed that
PF pressure replaced the grounded utility leader in 384 of 6,726 treatment
decisions.

`grounded-impact-planner/1.3` addresses that observed mechanism directly.
Pressure may still select a different non-safety operation only when it:

- preserves the best deadline-fitting grounded utility; or
- has a strictly larger, ruleset-grounded score completion guaranteed by the
  fixed horizon.

The implementation also:

- marks generic exploration satisfied when the engine configuration provides
  no information gain, while retaining exact packet-known hut routes;
- activates score pressure only for immediate city founding, grounded
  population recovery, or an explicitly guaranteed unit-score completion that
  fits the remaining horizon;
- computes opportunity cost per category instead of allowing a weak category
  to borrow a stronger same-goal category's utility;
- rejects projections explicitly completing after the horizon;
- binds tactical actions and city fortification to the proximate visible
  threat that activated safety, failing closed when actor or threat geometry
  is incomplete; and
- retains lexicographic safety priority for a grounded defense deficit or a
  relevant threat response.

The new behavior is controlled by
`pressure_score_alignment_enabled`. Generic exploration information value is
declared separately by `pressure_exploration_information_enabled`. Direct
planner consumers default to legacy behavior. The engine-live profile enables
score alignment and disables generic exploration information because its game
configuration explicitly sets `fogofwar: false`.

## Immutable confirmation replay

The new `--score-alignment-counterfactual` mode replayed the 100 immutable
treatment traces from
`pf-pressure-direct-completion-confirmatory-v1`. It held candidates, grounded
utilities, learned conductance, recorded goal state, and pressure configuration
fixed.

| Measure | Recorded PF | Score-aligned replay | Change |
|---|---:|---:|---:|
| Decisions | 6,726 | 6,726 | 0 |
| Departures from grounded utility leader | 384 | 137 | -247 (-64.3%) |
| Departure rate | 5.71% | 2.04% | -3.67 pp |
| Summed grounded utility regret | 24,847.48 | 18,436.48 | -6,411.00 (-25.8%) |
| Traces with a changed recorded choice | — | 89 of 100 | — |
| Score-alignment guard rejections | — | 20,913 candidate rows | — |
| Explicit deadline rejections | — | 38 candidate rows | — |

The replay artifact hash is
`26730149f84fcb5341f721ca58a7a80c8903ca7ec679d95b96620f2434493880`;
its 100-file source-set hash is
`10de9f20ecbd0e998357ad0b168a04273e1f714356b7a74ade437580ccea4e0b`.

Most recorded choices changed by the new policy were generic exploration:
128 `exploration_move` choices reverted to `city_defense`, 107 reverted to
`tactical_move`, and one reverted to `tactical_attack`. Those are local
counterfactual transitions, not independent samples.

The remaining 137 departures from canonical ordering are predominantly
recorded safety choices. Old `operation_scored` artifacts do not retain enough
actor and target geometry to determine whether each tactical operation answers
the activating threat. Replay therefore preserves recorded survival candidates
conservatively. Fresh engine execution applies the stricter threat binding.

Replay cannot evolve engine state after the first changed action and cannot
measure downstream score. These numbers establish policy targeting and
correctness only; they are not a gameplay score or win-rate claim.

Reproduction:

```bash
PYTHONPATH=src:benchmarks python3 \
  scripts/freeciv/replay_pressure_decisions.py \
  --score-alignment-counterfactual \
  artifacts/freeciv/pf-pressure-direct-completion-confirmatory-v1/games/impact_pair/pressure_direct_completion_confirmatory_v1/treatment
```

## Engine-backed diagnostic smoke

A one-pair, turn-30 engine-live smoke used predeclared seed `3332523` and
changed only `pressure_score_alignment_enabled`. The temporary smoke
configuration was explicitly development-only because the implementation
worktree was dirty. Both arms completed, both event schemas and all safety
gates passed, initial states matched, and engine rejection was zero.

| Measure | Legacy-pressure arm | Score-aligned arm |
|---|---:|---:|
| Turn-30 score | 113 | 113 |
| Opponent score | 114 | 114 |
| Cities gained | 1 | 1 |
| Pressure decisions | 13 | 13 |
| Mean pressure-planning latency | 1.276 ms | 1.255 ms |

The aligned arm emitted 49 candidate-row guard rejections across its 13
pressure decisions. It selected the same grounded action as the legacy arm in
this seed, so the zero score delta is expected and has no inferential value.
The diagnostic aggregate is under
`artifacts/freeciv/pf-pressure-score-alignment-smoke-v1` with configuration
hash
`dc10c86159a215bbe9c12c48f5e6b943c89af2c51c758aaf5aa6ec6d6a6fa1ca`.

## Fresh paired gate

`pressure_score_alignment_pilot_v1` predeclares 40 fresh, seed-disjoint pairs
at turn 60. Both arms retain PF pressure and learning; the only arm difference
is `pressure_score_alignment_enabled`. Historical pressure cohorts explicitly
pin that flag to `false`, preserving their recorded treatment semantics.

Acceptance requires:

- a clean, stable committed source identity for all 80 arms;
- all 40 pairs complete, exact within-pair ordering, and matched initial state;
- zero engine rejections, zero safe-fallback use, and every loop under 30
  seconds in both arms;
- valid event schemas and exact replay of every aligned-arm pressure decision;
- observed guard/deadline intervention counts and transition categories;
- paired score and fixed-horizon lead estimates reported with their
  predeclared intervals and exact tests; and
- no claim language, cohort promotion, or pooling with historical cohorts
  regardless of the pilot point estimate.

After the implementation is committed:

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-score-alignment-pilot-v1 \
  --backend engine-live \
  --cohort pressure_score_alignment_pilot_v1 \
  --workers 3 \
  --server-ports 6001,6002,6003
```

Only a separately predeclared, clean-source confirmatory cohort may support a
score or lead-rate superiority claim after this pilot passes its correctness
and safety gates.

## Completed pilot result

The 40-pair gate subsequently completed all 80 current arms at commit
`c2226c8`. Correctness, source-freeze, replay, and safety gates passed, but
score alignment reduced mean score by 0.70 points with interval
[-1.45, -0.15] and exact paired sign-flip p=0.02246. The v1 mechanism is
rejected and must not advance to confirmation. Full outcome and root-cause
evidence are in
[`pf-pressure-score-alignment-pilot-v1.md`](pf-pressure-score-alignment-pilot-v1.md).
