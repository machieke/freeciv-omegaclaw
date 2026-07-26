# PF-PLN expansion target confirmation v1

Status: complete; predeclared turn-60 score-improvement claim supported

The claim-eligible `expansion_target_confirmatory_v1` cohort completed all 100
fresh paired seeds and 200 current engine arms. It used clean, stable commit
`c7747db`, exact 50/50 arm-order balance, and matched every paired initial
state.

Both arms used planner `grounded-impact-planner/1.5`, pressure, conductance
learning, score-alignment v2, and the same minimum 15-turn post-settlement
runway. The only effective arm difference was `expansion_city_target`: three
under baseline and four under treatment.

## Confirmed outcome

Mean turn-60 score increased from 117.11 to 119.77. The paired difference was
**+2.66** with a 95% paired-bootstrap interval of **[+2.00, +3.32]**. The
predeclared exact two-sided paired sign-flip p-value was
**9.214e-12** across 87 nonzero pairs. All claim gates passed, so the
predeclared own-score improvement is supported.

The separate, claim-ineligible 40-pair pilot estimated +2.025
[+0.800, +3.250]. It was not pooled with this confirmation. The fresh
confirmation independently replicated the direction, magnitude, and
expansion-to-citizen-score mechanism.

| Outcome | Baseline | Treatment | Paired delta | 95% interval |
|---|---:|---:|---:|---:|
| Total score | 117.11 | 119.77 | +2.66 | [+2.00, +3.32] |
| Citizen component | 12.54 | 15.28 | +2.74 | [+2.25, +3.20] |
| Technology component | 102.24 | 102.24 | 0.00 | [-0.10, +0.10] |
| Residual component | 2.33 | 2.25 | -0.08 | [-0.43, +0.26] |
| Score margin | -9.96 | -8.06 | +1.90 | [-0.49, +4.24] |
| Opponent score | 127.07 | 127.83 | +0.76 | [-1.16, +2.76] |

Seventy-five pairs improved, 13 tied, and 12 declined. The paired median was
+3 and the total paired score gain was 266 points. Observed paired SD was
3.418. The 100-pair design had estimated 99.2% power for its predeclared
1.5-point effect and an achieved variance-based detectable delta of 0.958.

The separate one-sided test against the predeclared two-point meaningful
margin had p=0.0300, but the interval lower bound was exactly +2.00 rather
than strictly above it. Because both gates were required, an effect strictly
greater than two points is not claimed.

Fixed-horizon lead rate changed from 23% to 24%, a paired +1 percentage point
with interval [-7, +9] percentage points. Fifteen pairs led under both arms,
68 under neither, eight only under baseline, and nine only under treatment;
exact McNemar p=1.0. Win/lead was not a declared endpoint. This result does
not support a win-rate claim.

## Mechanism

The treatment changed the intended score-bearing path:

- founder-production changes increased by +0.84
  [+0.73, +0.95];
- settlement completions and cities founded increased by +0.82
  [+0.72, +0.92];
- cities gained increased by +0.78
  [+0.68, +0.88];
- projected production score value increased by +0.173
  [+0.014, +0.330]; and
- citizen score increased by +2.74
  [+2.25, +3.20].

Treatment gained three cities in 72 games, two in 22, one in five, and none
in one. Baseline gained two cities in 88 games, one in 11, and none in one.
Technology was unchanged, and the residual score interval included zero.
The observed score gain is therefore aligned with the predeclared
expansion-to-citizen-score mechanism.

The 12 negative pairs were retained. Eight did not gain an extra city, one
gained fewer cities, and three gained an extra city but lost residual or
citizen score. This heterogeneity limits per-map guarantees but does not
invalidate the population-average paired claim.

## Correctness, safety, and replay

All 200 current streams and 276,269 events pass schema, ordering, proof,
provenance, and causal validation with zero warnings. Exact replay covered
all 100 treatment traces and 7,425 pressure decisions. Every selection and
schedule hash reproduced with zero integrity failures and unchanged sources.
Pressure differed from canonical grounded utility ordering in 417 decisions
(5.62%).

The score-alignment guard emitted 15,188 candidate rejections across 2,813
decisions, the deadline guard emitted 123 rows across 24 decisions, and the
safety firewall emitted 2,178 rows across 473 decisions. Every
safety-firewall decision selected a grounded survival category. Engine
rejection and model safe-fallback rates were zero in both arms, and every
full loop remained under 30 seconds.

One baseline startup attempt for seed `3784419` failed before gameplay because
the observer global state was not populated. The source-frozen resume skipped
all 199 successful arms and replaced only that attempt. The final cohort has
200 current completed arms and zero active infrastructure failures; the
original startup failure remains historical audit evidence.

The replay structural artifact hash is
`cfeccc25f856f2375f64147d27ba19d04799045c9284590bc9d1c4d0815b5696`;
its source-set hash is
`b2677c245fafcd24b85ea218076c0271de9b1e90ef1c653535fae311437a6917`.
The aggregate byte SHA-256 is
`a5c5f22a7a3a872f9d474b07b258c5f0026af39a6f7fc927a508d87b53deba34`;
the replay byte SHA-256 is
`7ed16a00d241b65168b787bb2d72fc0872d959515f17b2c6484d6283f403fc6e`.

## Claim boundary

The supported claim is:

> On 100 fresh paired `civ2civ3` games against the configured experimental
> Freeciv AI, at turn 60, raising the grounded planner's expansion target
> from three to four cities while retaining a 15-turn settlement runway
> increased own score by 2.66 points on average, with a 95% paired-bootstrap
> interval of [2.00, 3.32] and exact paired p=9.214e-12.

This is not a general Freeciv win-rate claim, a strict effect-greater-than-two
claim, or evidence for other rulesets, opponents, horizons, planner settings,
or unpaired execution. The pilot and confirmation remain separate.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-expansion-target-confirmatory-v1 \
  --backend engine-live \
  --cohort expansion_target_confirmatory_v1 \
  --workers 3 \
  --server-ports 6001,6002,6003
```

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-expansion-target-confirmatory-v1/games/impact_pair/expansion_target_confirmatory_v1/treatment \
  --maximum-files 100 \
  --relative-to artifacts/freeciv/pf-expansion-target-confirmatory-v1 \
  --output artifacts/freeciv/pf-expansion-target-confirmatory-v1/pressure-replay-100.json
```

Machine-readable evidence is in
[`pf-expansion-target-confirmatory-v1.json`](pf-expansion-target-confirmatory-v1.json).
