# PR100 retained-capacity transition confirmation

Date: 2026-08-06

## Result

The fixed, disjoint 301-game PR100 cohort confirms the exact frozen PR99
retained-capacity transition model under every preregistered mechanics,
diversity, coverage, calibration, Brier, non-inferiority, and selected-bin
gate. The model was loaded from its canonical artifact and was not refitted.

All 301 engine games completed from clean source commit
`41fb72e372e1584308521c3ef8c0c758e6e379bb`, with zero resume and zero
infrastructure failure. No seed was replaced, retried, or appended. Two
complete four-worker audits are byte-identical.

- Confirmation structural hash:
  `4f977bc166836202fe70273fbb7ded843f2500bfc39992e22ddd52654264d829`
- Confirmation query/episode dataset hash:
  `6eae3fc1fefbe4ab9916618a7d9a731a13f0ccfa08a7f282083ba0a731c7c0ff`
- Serialized confirmation report SHA-256:
  `5587d5a9fd14c87b690a627d56886768b43decee9ca092da8546782c47b8b2a3`
- Frozen PR99 model hash:
  `909e8170d9dc797f69b71337243633ddd5fd5e007a7627c44e150d0a05439a6f`

All six cohort mechanics checks, all eight nested query/episode gates, all
eight independent diversity checks, and all twelve calibration checks pass.
Truth mutation, learning write-through, calibrated authority, candidate
readout, policy, and action authority remain disabled.

## Independent outcome recurrence

| Measure | Count |
|---|---:|
| Fixed confirmation games | 301 |
| Games with a query | 115 |
| Terminal-bearing games | 115 |
| Query rows | 167 |
| Terminal rows | 166 |
| Right-censored rows | 1 |
| Zero-query games | 186 |
| `no-effect-observed` episodes / games | 103 / 85 |
| `effect-without-goal-relief` episodes / games | 32 / 28 |
| `goal-relief-observed` episodes / games | 31 / 30 |

Every status exceeds the frozen minimum of 10 episodes and 10 independent
games. The cohort also exceeds the 30-terminal-row and 20-terminal-game gates.
The one censored row remains explicit and does not enter target metrics.

## Out-of-sample calibration

Metrics are unweighted means of per-game means over the 115 terminal-bearing
games. Intervals use the frozen 10,000-resample game-cluster bootstrap. All 166
terminal rows receive a numerical prediction for both targets, giving 100%
out-of-sample numerical coverage.

| Target | Brier score (95% interval) | Mean predicted − observed (95% interval) |
|---|---:|---:|
| Exact product effect | 0.2173 (0.1955 to 0.2394) | +0.0133 (-0.0641 to +0.0903) |
| Durable goal relief | 0.1547 (0.1176 to 0.1948) | +0.0049 (-0.0621 to +0.0671) |

Both Brier scores are below the frozen `0.25` ceiling. Both calibration
intervals lie completely inside the equivalence band `[-0.10, +0.10]`.

## Frozen-root comparison

Negative model-minus-root Brier differences favor the hierarchy.

| Target | Model − root Brier (95% interval) | Result |
|---|---:|---|
| Exact product effect | -0.01428 (-0.02749 to -0.00131) | Improvement interval entirely below zero |
| Durable goal relief | -0.00181 (-0.00738 to +0.00387) | Point improvement; non-inferior within +0.02 margin |

The hierarchy provides a statistically resolved Brier improvement for exact
product effect. Durable goal relief meets the preregistered point-improvement
and non-inferiority gates, but its interval includes zero; PR100 therefore does
not claim a statistically resolved relief-Brier advantage over the root-only
model.

## Selected-bin stability

Four selected target/bin groups recur in at least 20 independent confirmation
games. All four absolute point calibration differences are no greater than
`0.15`, and all four confirmation outcome means lie inside their frozen PR99
intervals.

The two Alpine Troops groups show the largest positive prediction bias:
`+0.1286` for exact product effect and `+0.0950` for durable relief. Both remain
inside the preregistered point-error bounds and both observed means remain
inside their frozen intervals. The two early-phase Riflemen groups have point
calibration differences of `+0.0119` and `+0.0226`.

## Reproducibility and claim boundary

Both confirmation audits independently replay every corrected PR95 parent
chain, join every query, load and roundtrip the exact PR99 model, predict every
query without fitting, and calculate the frozen game-cluster metrics. Literal
byte comparison and SHA-256 comparison pass. The versioned JSON report is one
of those exact outputs and retains the complete game, row, prediction, bin,
metric, check, source, and authority provenance.

PR100 confirms out-of-sample calibration and bounded Brier performance for the
exact PR99 model on this retained-capacity query domain. It does not establish
causal action value, safe candidate displacement, gameplay impact, score
improvement, or win rate. The model remains shadow-only. A separately
preregistered decision-safe candidate-readout comparison is required before
any authority can be considered.
