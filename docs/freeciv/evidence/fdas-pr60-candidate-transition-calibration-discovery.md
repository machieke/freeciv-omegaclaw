# FDAS PR60 candidate-transition calibration discovery

## Result

The preregistered discovery cohort passed every mechanical, feature, and
outcome-yield gate, and the frozen hierarchical move-transition model was fit.
This is in-sample, selected-only evidence. It does not validate the model on
new games or establish a counterfactual value for any nonselected candidate.

All 12 games ran from clean commit
`67c3c0ed7c52c1c5ab4e47b9c750f73b0bce258a`, reached observed turn 161,
and completed with zero infrastructure failures, rejected actions, or resumes.
The feature audit passed across 716 choice sets and 1,730 candidates. All 1,520
move candidates had complete PR59 grounding; they exposed 83 unique transition
signatures, and 343 multi-move sets contained distinct signatures. All 210
fortification rows remained on the frozen schema, and the original PR40
prediction was byte-identical for every enriched move query.

## Frozen yield gates

All discovery thresholds passed:

| Measure | Observed | Minimum |
|---|---:|---:|
| Observed selected move outcomes | 48 | 12 |
| Positive move outcomes | 25 | 3 |
| Negative move outcomes | 23 | 8 |
| Independent observed move lineages | 17 | 8 |
| Games with an observed move | 6 | 6 |
| Selected transition signatures | 14 | 6 |
| Diverse multi-move choice sets | 343 | 12 |

Only six games contributed an observed move label, exactly the frozen minimum.
Repeated rows within a durable actor/target/action lineage were collapsed, so
48 sequential labels contribute only 17 independent units of support.

## Fitted support

The model contains 102 hash-bound bins. Supported candidate-specific bins
include three compact, two compact+lifecycle, three full, and two
full+lifecycle bins. Broader ETA, route, and lifecycle backoffs remain
available. On the outcome-free discovery choice surface all 1,520 move queries
received an estimate: 970 (`63.8%`) used a candidate-specific level more
specific than action/lifecycle, and the model emitted 12 distinct estimate/
interval triples.

Intervals remain appropriately broad. For example, the supported action bin
has 17 lineages and estimate `0.476` with interval `[0.262, 0.690]`; supported
candidate-specific intervals have widths of roughly `0.54-0.63`. Discovery
therefore establishes feature-dependent predictive variation, not safe
candidate dominance.

## Operational note

The first fitter invocation supplied a mistyped manually expanded expected
commit and stopped at the source-identity gate before fitting. Re-running with
the exact clean commit already recorded by every game passed the unchanged
audit. No seed, threshold, feature, outcome, hierarchy, or model setting was
changed.

## Claim boundary and next gate

The fitted artifact is non-authorizing and in-sample. It cannot enter the live
candidate union or PR58 readout. The untouched 12-game confirmation cohort and
all preregistered predictive gates remain required. Failure there preserves
this discovery result as exploratory only.

Evidence:

- Discovery artifact:
  `docs/freeciv/evidence/fdas-pr60-candidate-transition-calibration-discovery.json`
- Discovery report hash:
  `b954be880a28cdd1cbc505b6d3c9a34d0151a424ef7330f31f3d5759f72c45d0`
- Model result hash:
  `edca977ffc87f9e731e00d5b5bacf3be03e1d5f28887e51e86966cb975ee3aa5`
- Feature audit hash:
  `459863117cfb954ec2d10f0a841084236a344c29081e4a9a7f309a15fbcd2500`
