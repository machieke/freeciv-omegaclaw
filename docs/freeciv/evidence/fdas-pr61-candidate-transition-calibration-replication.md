# FDAS PR61 candidate-transition calibration replication

Date: 2026-08-03

## Primary verdict

The preregistered PR61 replication is **rejected**. All frozen outcome-yield
and predictive-validation gates passed, but feature audit 1.0 failed its
per-game opportunity requirements in four mechanically valid sparse games.
Because that audit version was frozen before collection, the favorable model
metrics cannot override the overall failure and the model remains excluded
from live readout.

## Immutable execution

- source commit: `b2f18f7`
- games: 30/30 completed, zero infrastructure failures, zero resumes, zero
  rejected actions
- endpoints: 27 games at observed turn 161; three authoritative terminal
  eliminations at turns 49, 129, and 129
- events: 702,403
- aggregate SHA-256:
  `2ad27593a23825fad45e797d2c05d01d4d78af0329bfbc21492737723d590b0f`
- result SHA-256:
  `865c5f1bda8a36972f6ccc34f74f06fd990b3fa13f87834e6545a7b50807b2d4`
- report hash:
  `15e00c27241d0d66a91a371089f8f0db7acd95b1cccd5dec41164cec007d8968`
- model result hash:
  `edca977ffc87f9e731e00d5b5bacf3be03e1d5f28887e51e86966cb975ee3aa5`

The parent PR58 audit passed, all expected seeds were present, and all terminal
endpoints satisfied the existing terminal-aware mechanics contract.

## Passed yield and predictive gates

The prospectively enlarged cohort solved PR60's independent-yield problem:

| Measure | Required | Observed |
|---|---:|---:|
| observed move outcomes | 12 | 75 |
| positive outcomes | 3 | 40 |
| negative outcomes | 8 | 35 |
| move lineages | 8 yield / 12 validation | 32 |
| games with observed moves | 6 | 14 |
| selected transition signatures | 6 | 24 |
| diverse multi-move choice sets | 12 | 640 |

Every frozen predictive gate also passed:

| Metric | Threshold | Observed |
|---|---:|---:|
| prediction coverage | at least 0.80 | 1.000 |
| candidate-specific fraction | at least 0.25 | 0.750 |
| distinct predictions | at least 2 | 20 |
| Brier score | at most 0.30 | 0.24292 |
| log loss | at most 0.85 | 0.67903 |
| calibration error | at most 0.20 | 0.05898 |
| predicted mean in empirical interval | required | yes |
| clustered Brier-improvement CI lower | at least -0.05 | -0.00241 |

The model improved Brier score over its action-only parent by `0.00466`; the
2,000-sample game-clustered interval was `[-0.00241, +0.01386]`. That passes
the frozen noninferiority rule but does not establish superiority.

## Feature-audit RCA

Across the cohort, feature audit 1.0 observed:

- 2,951 move choices, all with complete transition grounding;
- zero incomplete or imputed move groundings;
- 2,951 byte-identical frozen-model compatibility checks;
- 221 summed per-game transition signatures;
- 803 multi-move choice sets, including 640 with distinct signatures; and
- a passing parent decision-safe audit.

Four individual games failed only opportunity-presence gates:

- seed `108413`: 77 complete move rows but no multi-move set;
- seed `108463`: 33 complete move rows but no multi-move set;
- seed `108533`: two fortify rows and no move opportunity; and
- seed `108541`: 15 complete move rows but no multi-move set.

There were no feature errors in any of those games. Audit 1.0 nevertheless
requires every game to contain a multi-move choice and at least two grounded
signatures. Those are cohort-yield properties, not per-game feature
invariants; absence of an opportunity cannot make a present row malformed.

## Next gate

PR61 remains the primary failed result. The correction must be prospective and
versioned: retain store validity, schema completeness when a move is present,
zero imputation, frozen-prediction identity, and parent mechanics as per-game
requirements; evaluate move presence, multi-candidate competition, and
signature diversity over the complete cohort. A new disjoint replication is
required after that correction is committed and preregistered. PR61 may be
re-audited only as an explicitly post-hoc diagnostic and cannot become the
confirmation used for activation.

Machine-readable primary evidence is in
`fdas-pr61-candidate-transition-calibration-replication.json`.

Audit 2.0 was subsequently implemented and passes a post-hoc sensitivity over
this immutable cohort. That verifies the correction but does not change this
primary verdict; see `fdas-pr62-transition-feature-cohort-audit.md`.
