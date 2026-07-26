# PF-PLN expansion target pilot v1

Status: complete; positive score pilot, unchanged confirmation required

The predeclared `expansion_target_pilot_v1` cohort completed all 40 fresh
paired seeds and 80 engine arms at turn 60 in one pass. The run used clean,
stable commit `c44b664`, balanced arm order 20/20, matched every paired initial
state, and had zero infrastructure failures.

Both arms used planner `grounded-impact-planner/1.5`, pressure, conductance
learning, score-alignment v2, and a minimum 15-turn post-settlement runway.
The only effective difference was `expansion_city_target`: three under
baseline and four under treatment.

## Outcome

Mean turn-60 score increased from 116.775 to 118.800. The paired delta was
**+2.025** with a 95% paired-bootstrap interval of **[+0.800, +3.250]**.
The exact two-sided paired sign-flip p-value was **0.002818** across 36
nonzero pairs.

There were 26 positive pairs, four ties, and ten negative pairs. The median
paired delta was +3 and total paired score increased by 81 points. The
predeclared test of an effect strictly greater than the two-point meaningful
margin had p=0.5 because the estimate was only 0.025 above that boundary.
That test does not negate superiority over zero; it prevents claiming an
effect greater than two points from this pilot.

| Outcome | Baseline | Treatment | Paired delta | 95% interval |
|---|---:|---:|---:|---:|
| Total score | 116.775 | 118.800 | +2.025 | [+0.800, +3.250] |
| Citizen component | 12.425 | 14.950 | +2.525 | [+1.625, +3.525] |
| Technology component | 102.100 | 102.100 | 0.000 | [0.000, 0.000] |
| Residual component | 2.250 | 1.750 | -0.500 | [-1.175, +0.125] |
| Score margin | -10.775 | -12.475 | -1.700 | [-6.150, +2.600] |
| Opponent score | 127.550 | 131.275 | +3.725 | [+0.300, +7.350] |

Fixed-horizon lead rate was 22.5% in both arms. Seven pairs led in both arms,
29 led in neither, two led only under baseline, and two led only under
treatment; exact McNemar p=1.0. This pilot supports an own-score mechanism,
not a lead-rate, score-margin, or win-rate improvement.

The observed paired score standard deviation was 3.997. Forty pairs had
estimated 88.6% power for the predeclared two-point target and a detectable
delta of 1.770 at this variance. The result is nevertheless
claim-ineligible and is not pooled with confirmation.

## Mechanism

The treatment changed the intended score-bearing path:

- founder-production changes increased by +0.875;
- settlement completions increased by +0.900;
- cities gained increased by +0.875;
- projected production score value increased by +0.305; and
- citizen score increased by +2.525.

Thirty-one treatment games finished with four cities, six with three, one
with two, and two with one. Baseline finished with three cities in 33 games,
two in five, and one in two. Treatment therefore reached the fourth-city
target in 77.5% of pairs without making the seven shared low-expansion maps
look artificially successful.

The first trace divergence was
`production_preexpansion_growth -> production_expansion` in 28 pairs, whose
score deltas summed to +58. Three
`exploration_move -> production_preexpansion_growth` first divergences summed
to +15, and three `production_repurpose -> expansion_move` divergences summed
to +12. These are post-outcome mechanism diagnostics, not separate tests.

Ten pairs lost score. Five still gained an extra city; their citizen gains
were partly or wholly offset by residual-score loss. Three negative pairs
failed to gain a city and lost population, exposing route/settlement
heterogeneity. These cases should remain in confirmation rather than being
removed or used to tune the already successful pilot.

## Correctness and replay

All 80 streams and 114,207 events pass schema, ordering, proof, provenance,
and causal validation with zero warnings. Exact replay covered all 40
treatment traces and 2,920 pressure decisions. Every selection and schedule
hash reproduced with zero integrity failures and unchanged sources.

Pressure differed from canonical grounded utility ordering in 140 decisions
(4.79%). The score-alignment guard emitted 6,132 candidate rejections across
1,197 decisions, the deadline guard emitted 33 rows across eight decisions,
and the safety firewall emitted 529 rows across 138 decisions. Every
safety-active decision selected a grounded survival category. Engine
rejection and model safe-fallback rates were zero, and every loop remained
under 30 seconds.

The replay structural artifact hash is
`98ad92a27dabea3e2109bf4f5982a7cb2cd7ec9faa6afd0f09bc77c6b0c9a676`;
its source-set hash is
`11f2e20cb2333b7a6e9c05a08eff92671f047dc9c2bacc137ac9bb0cab78047e`.
The aggregate byte SHA-256 is
`3a260690c469594b90e5855fb34acdc742528aab594839b8a6bcd43747d6dbba`;
the replay byte SHA-256 is
`1184d64dbd6fca5d734068d4273b689606ab5fba96b1540a456befdc9fbb5d97`.

## Confirmation

`expansion_target_confirmatory_v1` freezes the implementation and policies
unchanged on 100 fresh pairs from namespace
`pf-pln-expansion-target-confirmatory-v1`, range
`3600000..3799999`. It is score-only and powered for a 1.5-point paired effect
with planning SD up to 5.0. It does not pool the pilot, inspect outcomes
early, exclude negative pairs, or retune the 15-turn runway.

The confirmation must complete all 100 pairs on one clean source identity,
pass every correctness and safety gate, validate all 200 event streams, and
replay every treatment decision exactly before its score claim is evaluated.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-expansion-target-pilot-v1 \
  --backend engine-live \
  --cohort expansion_target_pilot_v1 \
  --workers 3 \
  --server-ports 6001,6002,6003
```

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-expansion-target-pilot-v1/games/impact_pair/expansion_target_pilot_v1/treatment \
  --maximum-files 40 \
  --relative-to artifacts/freeciv/pf-expansion-target-pilot-v1 \
  --output artifacts/freeciv/pf-expansion-target-pilot-v1/pressure-replay-40.json
```

Machine-readable evidence is in
[`pf-expansion-target-pilot-v1.json`](pf-expansion-target-pilot-v1.json).
