# FDAS PR40 candidate-calibration discovery result

## Result

The preregistered ten-game discovery cohort passed every mechanical and
progression gate. A lineage-aware, action/lifecycle calibration artifact was
fit from its selected-only outcomes. The model remains descriptive,
non-authorizing, and ineligible for candidate ranking until a disjoint
confirmation gate passes.

All ten games completed 160 turns from clean commit
`7210f2cce0a58edc03a08d7a893c3f917327bf2d`. The cohort contains 268,617
valid events with no warnings, rejected actions, or infrastructure failures.
The first execution attempt was discarded before fitting after it exposed an
episode transition bug; its partial artifacts are segregated and were neither
pooled nor used. The corrected cohort was restarted from seed one, with all
ten games sharing the same clean implementation identity.

## Frozen-gate outcome

The discovery surface produced:

- 741 opportunity sets and 2,291 exact candidates;
- 486 multi-candidate and 311 mixed move/fortify sets;
- 90 selected actions and 73 observed delayed outcomes;
- 46 positive and 27 negative observed outcomes;
- 16 selected and 11 observed durable move lineages;
- 44 selected and observed durable fortification lineages; and
- 75 selected actor/context signatures.

Every candidate carries the preregistered game/participants/target/action
lineage. The fit collapses 29 observed move rows to 11 effective lineages, so
sequential route steps cannot manufacture precision. Fortification has 44
rows and 44 independent lineages.

## Discovery estimates

| Stratum | Raw rows | Effective lineages | Positive mass | Estimate | Wilson 95% interval | Width |
|---|---:|---:|---:|---:|---:|---:|
| Move, all lifecycle states | 29 | 11 | 6 | 0.534 | [0.280, 0.787] | 0.507 |
| Fortify, all lifecycle states | 44 | 44 | 32 | 0.709 | [0.582, 0.837] | 0.255 |

Move lifecycle bins contain only two to four effective lineages and therefore
remain very wide. The `96+` move bin is below the frozen lifecycle minimum and
will back off to the action-level estimate. Fortification lifecycle bins at
`0-31` and `32-63` have 20 and 16 lineages; later bins have only three and
five. The artifact preserves those uncertainty differences and abstains if
even action-level support is absent.

## What this permits

This result permits preregistration of a disjoint confirmation cohort for:

- outcome-blind prediction coverage;
- action-stratified calibration in the large;
- lineage- and game-clustered Brier/log-loss evaluation;
- lifecycle-model comparison against action-only backoff; and
- a later protected candidate-union readout only if the frozen confirmation
  gates pass.

It does not establish out-of-sample calibration, a causal effect for censored
alternatives, candidate ranking safety, gameplay impact, score improvement,
or win rate. The ten discovery seeds and all earlier PR34-PR38 seeds remain
excluded from confirmation.

## Evidence

- Yield report:
  `docs/freeciv/evidence/fdas-pr40-candidate-calibration-discovery-yield.json`
- Yield report hash:
  `13ce9122be7ece13b81147ed810d5c3acd32c37d4592ffcf29c5bfba7f6b393f`
- Yield file SHA-256:
  `416c406549cc292c0b5fab4670397f93e166b02ff1ebad43a3074bb29a72adcb`
- Calibration artifact:
  `docs/freeciv/evidence/fdas-pr40-candidate-calibration-discovery.json`
- Calibration report hash:
  `b990cb2ce5dd973c4ded876b114986f3f54d52a358ed57d4f8e1078958d787d9`
- Model result hash:
  `9d2af28d765e75cfe3a0aade43be9d5f0a251904f605dd79394db93363a2562a`
- Calibration file SHA-256:
  `2d49de2097239d50a25bbbe2a59e2ebcc3910909eb0cf56ae491debad4345334`
