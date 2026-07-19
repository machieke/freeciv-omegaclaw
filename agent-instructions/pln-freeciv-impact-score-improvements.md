# FreeCiv impact-score improvement protocol

## Purpose

The completed 30-turn v4 cohort remains immutable historical evidence. Its
treatment-minus-baseline score estimate was `+0.13` with a bootstrap 95% CI of
`[+0.02, +0.27]` and an exact paired sign-flip `p=0.09375`. The result was too
sparse for a claim: 93 of 100 score pairs tied, and most treatment failovers
occurred too late to affect turn-30 production or scoring.

This hardening targets measurement fidelity and intervention timing before any
fresh confirmatory cohort is frozen. It does not reinterpret or extend v4.

## Implemented controls

1. Decision snapshots are accepted only after ruleset, research, economy, city
   buildability, legal release action, and movement data are ready. Two identical
   decision fingerprints are required, excluding packet source sequence.
2. Initial observer scores must be finite and populated for both the controlled
   player and an opponent. Missing score values no longer silently become zero.
3. Each arm records an initial-state fingerprint that combines stable decision
   inputs and both initial scores. Paired aggregation fails its safety gate when
   fingerprints are absent or differ.
4. Candidate enumeration is read-only. Exploration history is updated at stable
   turn boundaries, not from transient action-refresh packet cadence.
5. A production action counts as an effect only when the authoritative city
   target exactly matches the requested production kind and value. An unrelated
   state-hash change cannot create a false recovery.
6. Production changes require at least eight turns of scoring runway; founder
   production requires twelve. The thresholds are explicit policy settings, and
   the planner receives the cohort's actual fixed horizon.
7. Non-claim-eligible 60-turn pilot cohorts use disjoint, deterministically
   derived seed pairs. Their manifests use 60 turns for the engine, policy, and
   outcome declaration.
8. The first 60-turn pilot iteration exposed an accepted production order with
   no subsequent source-sequence update, two initial legal-action mismatches,
   and one over-budget turn. The hardened `pilot_horizon_60_v2` cohort therefore
   uses a bounded two-second action refresh, closes ambiguous unrefreshed scopes,
   requires five stable initial samples after a quiet period, and stops impact
   work before the whole-turn budget is exhausted.

## Evaluation sequence

Run a small engine-backed plumbing check first:

```bash
PYTHONPATH=src:benchmarks python scripts/freeciv/run_impact_evaluation.py \
  --backend engine-live \
  --cohort pilot_horizon_60_v2 \
  --limit-pairs 1 \
  --out artifacts/freeciv/impact-pilot-horizon60-v2-smoke
```

After the source is committed and clean, run the complete pilot without a pair
limit:

```bash
PYTHONPATH=src:benchmarks python scripts/freeciv/run_impact_evaluation.py \
  --backend engine-live \
  --cohort pilot_horizon_60_v2 \
  --out artifacts/freeciv/impact-pilot-horizon60-v2
```

The pilot must be used for mechanism and variance estimation only. Inspect
initial-state fidelity, score tie rate, treatment activation timing, exact
production effects, paired score variance, and safety gates. Then freeze a new,
disjoint confirmatory namespace and sample size before running any of its arms.

## Completed hardened pilot

The engine-backed `pilot_horizon_60_v2` run completed all 40 pairs on commit
`d43638439d069535d8dd0b4c429f7260d5921207`. One baseline engine attempt timed
out waiting for turn 12; resume mode archived that attempt and the exact arm then
completed successfully. The active cohort has 80 completed arms, zero active
failures, matching initial-state fingerprints for all pairs, zero rejected actions,
zero model fallbacks, and a 100% under-30-second full-loop rate.

The treatment-minus-baseline score estimate is `+0.20`, with bootstrap 95% CI
`[-0.05, +0.475]` and exact paired sign-flip `p=0.25`. The pilot is therefore not
a positive score claim. Thirty-five pairs tied, four favored treatment, and one
favored baseline. Treatment failover activated in 14/40 pairs, made 29 attempts,
and recorded 26 exact recoveries. Activated pairs averaged `+0.571` score while
non-activated pairs tied, which supports the intended mechanism but is a
post-treatment diagnostic subgroup rather than a claimable causal estimand.

The observed paired score SD is `0.8533`. A fresh score-only design is frozen as
`confirmatory_score_horizon_60_v1`: 200 turn-60 pairs, minimum detectable score
delta `0.20`, maximum planning SD `1.0`, 80% target power, and namespace
`pln-freeciv-impact-confirmatory-score-horizon60-v1`. The normal planning bound
requires 197 pairs. Its 200 seeds occupy `1400000..1699999`, disjoint from every
development, pilot, and prior confirmatory cohort. The previously exposed V4 score
cohort is retired from claim eligibility.

## Acceptance criteria for a future claim cohort

- Every predeclared pair completes under one clean committed implementation.
- Initial-state fingerprint mismatches and unavailable fingerprints are zero.
- Engine rejection and model safe-fallback rates are zero in both arms.
- The score endpoint uses the predeclared fixed horizon for every arm.
- The number of pairs is frozen from pilot variance for the declared minimum
  detectable effect; it is not adjusted after inspecting confirmatory outcomes.
- Score superiority requires both a bootstrap interval lower bound above zero
  and a two-sided exact paired sign-flip p-value at or below alpha.
- A meaningful score claim separately requires the same two gates above the
  predeclared meaningful margin.
- Fixed-horizon score-lead rate remains hierarchically gated behind score
  superiority and is not described as an engine-reported terminal victory.
