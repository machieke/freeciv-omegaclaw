# Unified PF-PLN flow advisory diagnostic v1

Status: complete, diagnostic only; no performance claim

The source-clean, engine-backed
`unified_flow_advisory_diagnostic_v1` cohort completed both of its
predeclared seed pairs at turn 60 on commit
`456bf5c6231b2b0f698f555c9bbeccdff9cc2da4`. The treatment isolated
`unified_flow_advisory` from `scalar_v2`; all other policy settings were
identical.

The score delta was `0.00 [0.00, 0.00]`, and the fixed-horizon score-lead
rate delta was `0.000 [0.000, 0.000]`. This two-pair diagnostic is
claim-ineligible and is not power evidence.

## Safety and mechanism findings

- All four current arms completed. Four earlier `KeyError: 'dependency'`
  attempts remain archived as historical failures and are excluded from the
  active paired estimate.
- Initial-state fidelity passed with zero mismatches.
- Engine rejected-action and model-fallback rates were zero in both arms.
- Every turn met the 30-second full-loop gate.
- Treatment emitted 150 healthy flow selections and 11 explicit
  `unified_flow_advisory -> scalar_v2` fallbacks across 161 control outcomes.
  The fallbacks were visible and fail-closed.
- All 282 executed treatment actions exactly matched their paired scalar-v2
  actions. There was no behavioral disagreement to which a score effect
  could be attributed.

## Root cause and disposition

The v1 production selector treated every positive-overlap operation as
eligible and then sorted that set by the unchanged scalar PF priority. The
flow computation therefore added controller cost but could change behavior
only in the exceptional case where the scalar winner had exactly zero
overlap.

Commit `429f2b0` corrects this mechanism before any pilot: flow overlap now
selects a bounded per-goal candidate region, typed PF priority scores
operations once within that region, and the artifact records scalar/flow
disagreements plus the signal-use ledger. A fresh, seed-disjoint
`unified_flow_advisory_diagnostic_v2` is predeclared in the `4700000..4799999`
range. Neither diagnostic seed set may be pooled with the untouched
40-pair pilot.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3.8 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/unified-flow-advisory-diagnostic-v1-engine \
  --backend engine-live \
  --cohort unified_flow_advisory_diagnostic_v1 \
  --workers 2 \
  --server-ports 6001,6003 \
  --no-resume
```
