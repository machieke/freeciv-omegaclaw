# FDAS PR60 candidate-transition calibration confirmation

Date: 2026-08-03

## Verdict

The preregistered PR60 confirmation is **rejected**. The frozen transition
model passed every predictive-quality gate, but the untouched cohort did not
meet the independent-game and held-out-lineage yield requirements. The result
must not be promoted into a live candidate readout.

This is a yield failure rather than evidence that the grounded model predicts
poorly. It is also not permission to lower the frozen thresholds, add the six
reserved seeds, or pool this cohort into a replacement confirmation.

## Immutable execution

- source commit: `511c5eb9eec71bf645c1948b42f59100b37b575f`
- discovery model result:
  `edca977ffc87f9e731e00d5b5bacf3be03e1d5f28887e51e86966cb975ee3aa5`
- discovery artifact hash:
  `b954be880a28cdd1cbc505b6d3c9a34d0151a424ef7330f31f3d5759f72c45d0`
- confirmation report hash:
  `98009a5e434e86c1077d7b64399d7c272218a4271febb5062aafff2bc5a9e143`
- feature-audit hash:
  `d4c3f801ecd3f0726674ad3bfbfd7e588219c418bc056d1f7d33bac44f32601c`
- aggregate SHA-256:
  `ebf6c9e31dafcffe94387a85ad0fe65a0ea29467d54581464b313a6a97b38814`
- confirmation JSON SHA-256:
  `b3d538b81ddfe409305f57c81336015c0e469f40b5598f77021c485e564e584d`

All 12 frozen confirmation seeds reached observed turn 161. The engine cohort
completed without infrastructure failure, resume, or rejected action and
emitted 288,694 events. No source file changed during collection.

## Frozen yield result

| Measure | Required | Observed | Result |
|---|---:|---:|---|
| observed selected move outcomes | 12 | 25 | pass |
| positive move outcomes | 3 | 13 | pass |
| negative move outcomes | 8 | 12 | pass |
| observed move lineages | 8 | 10 | pass |
| games with an observed move | 6 | 4 | **fail** |
| selected transition signatures | 6 | 14 | pass |
| diverse multi-move choice sets | 12 | 399 | pass |

The validation layer separately required at least 12 held-out effective
lineages. The cohort supplied 10, so that gate also failed. Sequential rows
were not treated as independent evidence to manufacture support.

## Descriptive predictive result

These metrics passed their frozen thresholds but remain subordinate to the
failed primary verdict:

| Metric | Frozen threshold | Observed | Result |
|---|---:|---:|---|
| prediction coverage | at least 0.80 | 1.000 | pass |
| candidate-specific prediction fraction | at least 0.25 | 0.700 | pass |
| distinct prediction values | at least 2 | 9 | pass |
| Brier score | at most 0.30 | 0.21605 | pass |
| log loss | at most 0.85 | 0.62435 | pass |
| calibration error | at most 0.20 | 0.01257 | pass |
| predicted mean in empirical Wilson interval | required | yes | pass |
| game-cluster Brier improvement CI lower | at least -0.05 | +0.00626 | pass |

The model's mean prediction was `0.48743` against an observed mean of `0.500`.
Its Brier improvement over the action-only parent was `0.03453`; the frozen
2,000-sample game-clustered 95% interval was `[+0.00626, +0.10050]` across
four contributing game clusters. This favorable interval is descriptive only
because the prespecified sample-yield gates failed.

## Interpretation and next gate

Grounded route and source-state features transferred directionally and were
well calibrated on the observed selected moves. The bottleneck is the sparse
distribution of independent move episodes across games: only one third of the
confirmation games contributed any selected move lineage.

The next attempt must be a new, disjoint, prospectively sized replication. It
must preserve the fitted model, hierarchy, support levels, thresholds, label,
and scalar controller; use fresh seeds; and size the cohort from the observed
four-of-twelve contributing-game yield with an explicit safety factor. PR60's
reserved seeds remain excluded. A passing replication may permit only a
separate shadow readout-yield experiment. It would still establish no
counterfactual candidate value, policy authority, gameplay effect, score, or
win-rate claim.

Machine-readable evidence is in
`fdas-pr60-candidate-transition-calibration-confirmation.json`.
