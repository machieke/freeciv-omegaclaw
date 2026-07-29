# Unified PF-PLN flow advisory diagnostic v2

Status: complete, diagnostic only; no performance claim

The source-clean, engine-backed
`unified_flow_advisory_diagnostic_v2` cohort completed all four predeclared
seed pairs at turn 60 on commit
`e39673b63885114ad6576231b22dd30f87dcc9a3`. The seeds
`4711650`, `4729417`, `4752647`, and `4782417` are disjoint from v1 and from
the untouched 40-pair pilot.

## Outcomes

Treatment-minus-baseline score deltas were `[0, -2, +7, 0]`. Their mean was
`+1.25` with paired-bootstrap interval `[-1.50, +5.25]`. The fixed-horizon
score-lead-rate delta was `+0.25 [0.00, +0.75]`, and score margin changed by
`+3.25 [0.00, +8.75]`.

The result is underpowered and claim-ineligible. The interval crosses zero,
the exact paired sign-flip p-value is `1.0`, and no score or win-rate claim
may be made or pooled with another cohort.

## Mechanism and safety

- All eight arms and all four pairs completed with no infrastructure failure.
- Initial-state fidelity passed with zero mismatches.
- Engine rejected-action and model-fallback rates were zero in both arms.
- Every turn met the 30-second full-loop gate.
- Treatment produced 205 healthy flow selections, 13 direct
  flow-versus-scalar disagreements, and 23 visible fail-closed scalar
  fallbacks.
- Those 13 initiating disagreements led to 94 turn-level action-sequence
  differences. Two pairs remained effectively unchanged; the other two
  diverged from turns 2 and 4.
- The positive score movement was primarily citizen score and one additional
  settlement, partly offset by technology score. These are diagnostic
  associations, not independently identified causal effects.

The diagnostic validates the corrected mechanism: overlap selects a
per-goal region and typed PF scores the operations inside it. It also exposes
both directions of risk. One pair gained seven points after flow-guided
founder movement; another lost two while flow repeatedly preferred movement
over an immediately legal city-founding operation. The pilot must estimate
the population effect without tuning this threshold against these four
outcomes.

## Controller-inclusive cost

Mean Impact planning latency increased from `30.11` to `159.28` ms/turn, a
paired increase of `129.17 [106.15, 157.27]` ms. Flow decision computation
accounted for about `66.16` ms/turn, while aggregate decision-event emission
accounted for `135.50` ms/turn above baseline because the same large semantic
decision hash was recomputed for every event in a causal chain.

The subsequent event hardening computes that semantic decision hash once per
chain and reuses the already recorded outcome hash. This is a
telemetry-only optimization; it does not alter query identity, selected
candidates, packets, or outcome semantics. A reused-seed performance replay
must verify the latency change before the untouched pilot.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3.8 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/unified-flow-advisory-diagnostic-v2-engine \
  --backend engine-live \
  --cohort unified_flow_advisory_diagnostic_v2 \
  --workers 2 \
  --server-ports 6001,6003 \
  --no-resume
```
