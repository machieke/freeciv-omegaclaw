# FDAS PR42 candidate-calibration confirmation result

## Result

The preregistered held-out confirmation passed every mechanical, yield, and
predictive gate. The frozen PR40 action/lifecycle model provides useful
out-of-sample selected-action calibration. This permits implementation of a
protected candidate-union readout in shadow, but it does not authorize
candidate ranking or establish lifecycle-model superiority.

All eight games completed 160 turns from clean commit
`424103df5575ea343aeaf63f7155da21716970bf`. The cohort contains 203,909
valid events with no warnings, rejected actions, infrastructure failures, or
resume. Every confirmation store is independent of the ten discovery stores.

## Yield

The held-out surface produced:

- 608 opportunity sets and 1,234 exact candidates;
- 346 multi-candidate and 48 mixed move/fortify sets;
- 62 selected actions and 55 observed delayed outcomes;
- 32 positive and 23 negative observed outcomes;
- ten selected and six observed durable move lineages; and
- 39 selected and 37 observed durable fortification lineages.

The evaluator collapsed repeated rows to 43 effective observed lineages and
produced an outcome-blind estimate for all of them.

## Frozen predictive gates

All gates passed:

| Metric | Held-out result | Frozen gate |
|---|---:|---:|
| Prediction coverage | 1.000 | at least 0.95 |
| Overall Brier score | 0.200 | at most 0.25 |
| Overall log loss | 0.585 | at most 0.75 |
| Overall calibration error | 0.023 | at most 0.15 |
| Move calibration error | 0.236 | at most 0.25 |
| Fortify calibration error | 0.064 | at most 0.25 |
| Lifecycle Brier improvement | +0.0069 | descriptive |
| Game-clustered improvement 95% interval | [-0.0267, +0.0296] | lower at least -0.05 |

Both action-stratum predicted means lie inside their empirical Wilson 95%
intervals. Overall observed persistence was `0.674`, compared with predicted
`0.652`.

## Important limitation

Move remains the weak stratum. It has only six held-out lineages, observed
persistence `0.333`, predicted `0.569`, Brier `0.275`, and lifecycle
conditioning worsens its action-only Brier by `0.0128`. The preregistered
action calibration and empirical-interval gates pass, but the uncertainty is
substantial. Fortify has 37 lineages, observed `0.730`, predicted `0.665`, and
Brier `0.188`.

Lifecycle conditioning is confirmed noninferior overall, not superior: the
game-clustered interval crosses zero. The next protected readout must therefore
use calibration only to form a shadow candidate union, retain same-action
backoff and interval metadata, abstain below support, and grant no action or
ranking authority. No censored alternative has an observed outcome, so this
result cannot identify a better unselected action.

## Claim boundary

This establishes held-out predictive calibration for selected actions under
the exact observational surface. It does not establish counterfactual
calibration for alternatives, decision improvement, gameplay impact, score
improvement, or win rate.

## Evidence

- Confirmation report:
  `docs/freeciv/evidence/fdas-pr42-candidate-calibration-confirmation.json`
- Confirmation report hash:
  `f1bd991a6d78a2554d1ed73f4e67c56c87f1b299c4e4f71db9ef26cc73ec9cc8`
- Nested validation hash:
  `d2799cedc5d3c081247452f29a48b97ec94957e155beb5e92425d164f407cc71`
- Confirmation file SHA-256:
  `b9b3e52173bf3c18de2d27a9bc2f513e1be607ce921767c5211ba1187e8c67df`
- Yield report:
  `docs/freeciv/evidence/fdas-pr42-candidate-calibration-confirmation-yield.json`
- Yield report hash:
  `76e09a7f7003dea83dfbea49618e17697f2815cb74030e5eef669fce54cf021a`
- Yield file SHA-256:
  `9da96b8da3b1a9be1ca91c2688fd3dc878edcddcda0ed5f24e2bf63da2fe8c43`
- Frozen model hash:
  `9d2af28d765e75cfe3a0aade43be9d5f0a251904f605dd79394db93363a2562a`
