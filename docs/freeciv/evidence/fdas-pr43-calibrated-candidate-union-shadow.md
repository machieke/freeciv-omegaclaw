# PR43 calibrated candidate-union shadow

## Outcome

The held-out-confirmed PR40 calibration model is now available to the live
engine as a bounded, revision-current candidate-union diagnostic. It does not
rank candidates, alter pressure, select an action, mutate truth, enable
advection, or invoke a capacity solver.

The protected union retains the scalar winner and may add at most one
confidence-bounded candidate from each of the two frozen defense action
families. A prediction is eligible only when its frozen Wilson interval width
is at most `0.55`. Both unsupported predictions and wider intervals are
recorded as explicit calibrated-recall abstentions.

## Frozen dependencies

- calibration artifact hash:
  `b990cb2ce5dd973c4ded876b114986f3f54d52a358ed57d4f8e1078958d787d9`;
- calibration model hash:
  `9d2af28d765e75cfe3a0aade43be9d5f0a251904f605dd79394db93363a2562a`;
- held-out confirmation hash:
  `f1bd991a6d78a2554d1ed73f4e67c56c87f1b299c4e4f71db9ef26cc73ec9cc8`;
- scalar protection: top `1` candidate;
- calibrated additions: at most `1` per action family; and
- maximum union size: `3`.

The engine fails closed if the discovery artifact, nested model, confirmation
wrapper, nested validation, authority flags, model binding, or discovery and
confirmation source disjointness differ.

## Engine smoke evidence

Two same-seed engineering runs at seed `105071` diagnosed and corrected a
recall-floor saturation issue.

| Measure | top-3 diagnostic | protected top-1 |
|---|---:|---:|
| completed horizon | 160 | 160 |
| union events | 84 | 84 |
| candidate readouts | 164 | 164 |
| union members | 160 | 85 |
| calibrated additions | 0 | 1 |
| uncertainty abstentions | not yet correctly counted | 157 |
| selection changes | 0 | 0 |
| engine action count | 336 | 336 |
| final score | 123 | 123 |

The top-3 floor already contained nearly every candidate and therefore could
not measure recall. The corrected top-1 floor recalled one supported fortify
candidate from scalar rank `3` at turn `57`; the rank-1 move remained the
scalar winner. The complete 336-action traces of the two runs were identical,
and both event ledgers validated without warnings or errors.

This is engineering evidence only. It establishes that the mechanism can add
a supported candidate without changing behavior in one game. It is not a
candidate-recall population claim and makes no gameplay, score, or win-rate
claim.

## Retrospective design-yield estimate

Applying the frozen top-1 union rule outcome-blind to the eight earlier PR42
choice stores yielded 22 additions across 6 of 8 games, from 608 choice sets
and 48 mixed-action sets. These already-used games are excluded from the PR44
confirmation population and are used only to set its thresholds.
