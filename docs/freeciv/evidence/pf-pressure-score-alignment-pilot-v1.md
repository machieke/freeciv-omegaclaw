# PF-PLN score-alignment pilot v1

Status: complete; mechanism rejected because it reduced score

The predeclared `pressure_score_alignment_pilot_v1` cohort completed all 40
fresh paired seeds and 80 current engine arms at turn 60. The run used one
clean, stable source identity at commit `c2226c8`, matched every paired initial
state, and passed every absolute safety gate.

One treatment arm initially failed before gameplay because observer global
state was not populated. Source-frozen resume archived that attempt, skipped
all 79 completed arms, and completed only the failed arm. The final cohort has
40 complete pairs and zero active infrastructure failures. The historical
startup failure remains visible in the aggregate rather than being erased.

## Outcome

Mean turn-60 score was 117.35 for legacy pressure and 116.65 for score-aligned
pressure. The paired delta was **-0.70** with a 95% paired-bootstrap interval
of **[-1.45, -0.15]**. The exact two-sided paired sign-flip p-value was
0.02246 across 11 nonzero pairs.

There were two positive pairs, 29 ties, and nine negative pairs. Seed
`3324283` contributed a -12 outlier, but removing it post hoc still leaves a
-0.410 mean across the other 39 pairs. That sensitivity check is diagnostic
only and does not replace the predeclared result.

Score components localize the loss:

| Component | Paired delta | 95% interval |
|---|---:|---:|
| Citizen score | -0.40 | [-0.725, -0.125] |
| Technology score | 0.00 | [0.00, 0.00] |
| Residual score | -0.30 | [-0.825, 0.05] |
| Total score | -0.70 | [-1.45, -0.15] |

Turn-60 score margin changed by -2.50 with interval [-5.175, -0.625].
Opponent score increased by 1.80 with interval [0.30, 3.925]. Fixed-horizon
lead rate changed from 12.5% to 15.0%, a +2.5 percentage-point estimate with
interval [0.0, 7.5]. Only one pair was discordant and it favored treatment, so
exact McNemar p=1.0. The sparse lead result does not offset the negative
primary score result.

This pilot is claim-ineligible, but the correct design conclusion is stronger
than “inconclusive”: do not confirm or deploy the v1 mechanism as a score
improvement.

## Correctness and replay acceptance

All 80 current event streams pass schema validation. Exact replay covered all
40 treatment traces and 2,338 pressure decisions. Every selected operation and
schedule hash reproduced, with zero integrity failures.

Pressure selected a different operation from grounded utility ordering in 74
decisions (3.17%). The largest transitions were:

- 22 `exploration_move -> tactical_move`;
- 14 `city_defense -> tactical_move`;
- 8 `expansion_move -> tactical_move`;
- 6 `city_founding -> tactical_move`; and
- 4 `hut_exploration -> production_defense`.

The aligned treatment emitted 6,853 `score_alignment_guard` candidate
rejections across 1,447 decisions and 31 explicit deadline rejections across
seven decisions. The safety firewall emitted 503 candidate rejections across
146 decisions. Every safety-active decision selected a survival category.
Engine rejection and model safe-fallback rates were zero in both arms, and
every loop remained under 30 seconds.

The exact replay artifact hash is
`ea9ee6a6462ca7cd2f87224cc26f9b5ef3fe8221b024a951581c4a58ba0b228c`;
its source-set hash is
`7bea34f202a1e2231ada8ad0eb591a9c911fcd8d02f709105035800b5482ae08`.

## Root cause

The v1 guard treated small differences in the Impact planner's heuristic
utility as calibrated score evidence. They are not calibrated score units.
When two movement candidates were close, the guard rejected a pressured
exploration route and forced the nominal utility leader even when that leader
had zero operational pressure.

The three pairs whose first divergent decision was
`exploration_move -> tactical_move` all lost score: -12, -3, and -2. Their
utility gaps were only 12, 3, and 6 points on utilities near 650-690. Together
they account for -17 of the cohort's -28 total paired score points.

One additional pair first changed `production_expansion` at utility 939.5 to
`production_preexpansion_growth` at 960.0 and lost four score points. This
shows the same ordering problem on a different goal: a small heuristic utility
gap suppressed grounded expansion pressure.

Within the safety tier, all grounded responses were also treated as
interchangeable. Six pairs first changed `city_defense -> tactical_move` and
had a combined -5 score delta. Preserving the safety firewall was correct, but
letting a much lower-utility tactical response replace local fortification was
not.

The assumption that fog-free exploration has no gameplay value was too
narrow. Even without terrain information gain, exploration movement changes
position, future legal actions, hut access, opponent contact, and survival.
Treatment explored 1.675 fewer positions on average with interval
[-3.60, -0.075], performed 3.975 fewer tactical actions on average, and
executed 0.0675 fewer meaningful actions per turn. Those are downstream
diagnostics, not independent causal estimates, but they agree with the
first-divergence evidence.

Conductance learning was not the isolated change. Both arms enabled the same
learning policy; the only manifest difference was
`pressure_score_alignment_enabled`.

## Required next mechanism

A replacement must not reuse these seeds or promote this pilot. A fresh,
predeclared v2 should:

- keep exploration pressure active for grounded positional value;
- use an explicit utility-uncertainty band instead of treating tiny heuristic
  differences as certain;
- apply that band within the safety tier so a materially worse tactical action
  cannot replace a better grounded safety response;
- retain exact deadline and guaranteed-score evidence;
- preserve the lexicographic safety firewall; and
- isolate the revised score-alignment flag on a new seed namespace.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-score-alignment-pilot-v1 \
  --backend engine-live \
  --cohort pressure_score_alignment_pilot_v1 \
  --workers 3 \
  --server-ports 6001,6002,6003
```

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-pressure-score-alignment-pilot-v1/games/impact_pair/pressure_score_alignment_pilot_v1/treatment \
  --maximum-files 40 \
  --relative-to artifacts/freeciv/pf-pressure-score-alignment-pilot-v1 \
  --output artifacts/freeciv/pf-pressure-score-alignment-pilot-v1/pressure-replay-40.json
```

Machine-readable summary evidence is in
[`pf-pressure-score-alignment-pilot-v1.json`](pf-pressure-score-alignment-pilot-v1.json).
