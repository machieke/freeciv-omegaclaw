# FDAS PR63 candidate-transition calibration confirmation

Date: 2026-08-03

## Verdict

The preregistered PR63 confirmation **passes** every mechanics, outcome-yield,
and predictive-validation gate. The frozen PR60 grounded move-transition model
is confirmed as a held-out selected-action predictor under feature audit 2.0.

This permits a separate, default-off shadow readout-yield experiment. It does
not permit action authority and does not identify outcomes for censored
alternatives.

## Immutable execution

- source commit: `bd6fe7b`
- games: 30/30 completed, zero infrastructure failures, zero resumes, zero
  rejected actions
- endpoints: 28 games at observed turn 161; two authoritative terminal
  eliminations at turns 147 and 150
- events: 707,408
- aggregate SHA-256:
  `64db854a053fd24bd58229ee1f23e8524f3ba1542a60c340391c2b39e9987631`
- confirmation JSON SHA-256:
  `aa9fc4b5b675be4847a2a7ffca65f220f29024bce00bdbf0109e15f56be61fef`
- report hash:
  `eb15aabe1d2e11eac71f4aaf31939854798445a50fbc76c1e7df32c35326ae42`
- feature-audit hash:
  `fcd91fa715e563545172cbc514e76626c87cb6cbda10096c150bccbe3bf4741d`
- model result hash:
  `edca977ffc87f9e731e00d5b5bacf3be03e1d5f28887e51e86966cb975ee3aa5`

Audit 2.0 passed all per-game row invariants, cohort opportunity mechanics,
parent PR58 mechanics, exact source, seed, endpoint, and non-authority checks.

## Yield

| Measure | Required | Observed | Result |
|---|---:|---:|---|
| observed move outcomes | 12 | 70 | pass |
| positive move outcomes | 3 | 38 | pass |
| negative move outcomes | 8 | 32 | pass |
| observed move lineages | 8 | 26 | pass |
| games with an observed move | 6 | 12 | pass |
| selected transition signatures | 6 | 25 | pass |
| diverse multi-move choice sets | 12 | 742 | pass |

Sequential rows were collapsed to durable game-local candidate lineages before
validation. No censored alternative was treated as a negative outcome.

## Predictive validation

| Metric | Frozen threshold | Observed | Result |
|---|---:|---:|---|
| prediction coverage | at least 0.80 | 1.000 | pass |
| held-out lineages | at least 12 | 26 | pass |
| candidate-specific fraction | at least 0.25 | 0.8462 | pass |
| distinct prediction values | at least 2 | 18 | pass |
| Brier score | at most 0.30 | 0.22194 | pass |
| log loss | at most 0.85 | 0.65501 | pass |
| calibration error | at most 0.20 | 0.02676 | pass |
| predicted mean in empirical interval | required | yes | pass |
| clustered Brier-improvement CI lower | at least -0.05 | -0.00494 | pass |

The model's mean prediction was `0.46522` against observed `0.43846`. Brier
score improved by `0.01645` over the action-only parent. The frozen 2,000-
sample game-clustered 95% interval was `[-0.00494, +0.03319]` across 12 game
clusters. This establishes noninferiority, not predictive superiority.

## Permitted next step and non-claims

The next implementation may load the confirmed model only into a new shadow-
only candidate readout. It must preserve scalar action authority, retain model
intervals and abstention, bind both model and confirmation hashes, emit no
selection change, and first measure whether candidate-specific estimates ever
produce decision-safe interval separation under exact grounded
noninferiority.

This result is selected-action observational calibration. It establishes no
counterfactual alternative value, candidate ranking quality, action-policy
improvement, gameplay effect, score improvement, or win rate.

Machine-readable evidence is in
`fdas-pr63-candidate-transition-calibration-confirmation.json`.
