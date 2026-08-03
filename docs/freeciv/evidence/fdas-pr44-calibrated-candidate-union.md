# PR44 calibrated candidate-union confirmation result

## Decision

PR44 is **mechanically rejected** under its preregistration. It cannot support
the protected candidate-recall claim, even though every frozen progression
gate passed.

Seed `105173` ended in genuine player elimination at turn `137`. The run
completed without infrastructure failure, but the preregistered mechanical
gate required every game to reach turn `160`. The seed was not replaced, the
cohort was not extended, and no earlier evidence was pooled into the result.

## Frozen cohort result

| Measure | Result | Gate |
|---|---:|---:|
| exact seeds | 8/8 | 8/8 |
| clean identical source | yes | required |
| infrastructure failures | 0 | 0 |
| event/union semantic errors | 0 | 0 |
| turn-160 horizons | 7/8 | 8/8 |
| calibrated-union events | 329 | at least 300 |
| candidate readouts | 776 | descriptive |
| eligible readouts | 135 | at least 50 |
| uncertainty abstentions | 641 | descriptive |
| mixed-action unions | 43 | at least 8 |
| calibrated additions | 20 | at least 8 |
| games with additions | 6/8 | at least 4/8 |
| game addition rate | 0.75 | descriptive |
| Wilson 95% lower bound | 0.4093 | at least 0.10 |
| action-selection changes | 0 | 0 |

All six progression gates passed. The sole failed game gate was
`completed_horizon_without_infrastructure_failure` for seed `105173`.

The canonical rejected report is
`docs/freeciv/evidence/fdas-pr44-calibrated-candidate-union.json`, with report
hash
`34550a65803ad9fb9eb878b61fdca5dde9fc38ed0eeb1aa93e6dd6471c9e2d6b`.

## Interpretation

The mechanism evidence is strong enough to justify a fresh confirmation, but
PR44 itself does not establish the claim because its completion rule was
mis-specified for a game engine with genuine absorbing terminal states. A
player elimination is neither an infrastructure failure nor a censored live
process: no later candidate opportunities can exist after elimination.

PR45 therefore keeps every yield and authority threshold unchanged, uses a
wholly new seed population, and preregisters completion as either the fixed
horizon or a genuine engine-reported game-over/player-elimination endpoint.
That rule is frozen before any PR45 game is run.
