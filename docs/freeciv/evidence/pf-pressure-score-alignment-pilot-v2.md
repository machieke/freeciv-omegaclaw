# PF-PLN score-alignment pilot v2

Status: complete; v1 harm corrected, score-improvement mechanism not supported

The predeclared `pressure_score_alignment_pilot_v2` cohort completed all 40
fresh paired seeds and 80 current engine arms at turn 60. The run used one
clean, stable source identity at commit `9cb2115`, balanced arm order 20/20,
matched every paired initial state, and passed every correctness and absolute
safety gate.

One treatment arm initially failed before gameplay because observer global
state was not populated. Source-frozen resume retained all 79 completed arms
and completed only seed `3424413`. The final cohort has 40 complete pairs and
zero active infrastructure failures. The historical startup failure remains
visible in the aggregate.

## Outcome

Mean turn-60 score was 117.400 for legacy pressure and 117.375 for v2
score-aligned pressure. The paired delta was **-0.025** with a 95%
paired-bootstrap interval of **[-0.275, 0.250]**. The exact two-sided paired
sign-flip p-value was **1.0** across six nonzero pairs.

There were two positive pairs, 34 ties, and four negative pairs. The six
nonzero deltas were `-1, +4, +1, -1, -1, -3`, summing to -1 point. The
predeclared test for a meaningful improvement greater than two points also
failed, with p approximately 1.0.

| Outcome | Baseline | Treatment | Paired delta | 95% interval |
|---|---:|---:|---:|---:|
| Total score | 117.400 | 117.375 | -0.025 | [-0.275, 0.250] |
| Citizen component | — | — | -0.075 | [-0.200, 0.000] |
| Technology component | — | — | +0.050 | [0.000, 0.150] |
| Residual component | — | — | 0.000 | [-0.225, 0.175] |
| Score margin | -8.700 | -9.100 | -0.400 | [-2.100, 0.925] |
| Opponent score | 126.100 | 126.475 | +0.375 | [-0.675, 1.850] |

Fixed-horizon lead rate changed from 25.0% to 20.0%, a -5 percentage-point
estimate with interval [-12.5, 0.0]. Eight pairs led in both arms, 30 led in
neither, two led only under baseline, and none led only under treatment.
Exact McNemar p=0.5. The sparse lead endpoint does not establish a win-rate
difference.

The observed paired score standard deviation was 0.862. Under the harness
normal approximation, 40 pairs had adequate power for the predeclared
two-point minimum effect and an estimated detectable delta of 0.382 at this
variance. The near-zero result is therefore evidence that this isolated
mechanism does not have a practically large score effect under the tested
horizon, rather than evidence that the v1 harm should be accepted as noise.

V1 and v2 use disjoint seeds and are not pooled. The v2 estimate is 0.675
points higher than the v1 estimate as a cross-cohort diagnostic only. The
supported conclusion is that the uncertainty band removed the observed harm;
it is not evidence of superiority over legacy pressure.

## Correctness and replay acceptance

All 80 current event streams and 117,019 events pass schema, ordering, proof,
provenance, and causal validation with zero warnings. Exact replay covered all
40 treatment traces and 3,143 pressure decisions. Every selected operation
and schedule hash reproduced, with zero integrity failures and unchanged
sources.

Pressure selected a different operation from canonical grounded utility
ordering in 144 decisions (4.58%). The largest transitions were:

- 41 `tactical_move -> exploration_move`;
- 26 `exploration_move -> tactical_move`;
- 14 `city_defense -> tactical_move`;
- 12 `expansion_move -> tactical_move`; and
- 10 `city_defense -> exploration_move`.

The treatment emitted 6,013 `score_alignment_guard` candidate rejections
across 1,056 decisions and 55 explicit deadline rejections across 11
decisions. Its safety firewall emitted 667 candidate rejections across 207
decisions. Every safety-active decision selected a grounded survival
category. Engine rejection and model safe-fallback rates were zero in both
arms, paired initial-state fidelity passed, and every full loop remained
under 30 seconds.

The exact replay structural artifact hash is
`6dda6fa1100a3bb7a92980e71ffc48087ad9f4a5a18f4f202cee0ff4d64bfe1e`;
its source-set hash is
`92a98e172db23d35ec31be4635cffac9eddd4d0687c75a61b3d312243219930b`.
The byte SHA-256 values are
`3f46e504aeb06ef82ded6e6813c651977b2711e320316b99fe18bf6392ccaaa5`
for the replay and
`7385b1881534474ceda79a20dd324a6259ca10cfde8a1a32eb801c1c0b78870d`
for the aggregate.

## Mechanism diagnosis

V2 fixed the specific v1 regressions:

- explored positions changed by +0.20 rather than v1's -1.675;
- meaningful actions per turn changed by +0.0258 rather than declining;
- the v1 first-divergence pattern
  `exploration_move -> tactical_move` no longer carried a negative score sum;
  and
- materially lower-utility safety choices remained blocked.

The mechanism was active, but its new choices were mostly score-neutral.
Seven pairs had identical decision traces. Of the 33 pairs with a trace
divergence, 26 first changed from baseline exploration to treatment city
defense. Those 26 pairs had a combined score delta of exactly zero: two
improved, three declined, and 21 tied. The remaining first-divergence groups
were small; only `expansion_move -> city_founding` had a nonzero group sum,
at -1 in one pair.

This localizes the remaining limitation. The score-alignment layer is now a
safe regularizer around heuristic utility, but it mostly rearranges movement
and fortification choices that do not affect the turn-60 score components.
It does not add new score-bearing operations, improve the projected value of
production or settlement, or learn a calibrated outcome advantage among
candidates inside the uncertainty band. More time alone would narrow the
interval around a near-zero effect; it would not make this mechanism
meaningfully positive.

Do not promote v2 as a score improvement and do not spend a confirmatory
cohort on the same isolated flag. The next optimization should target a
grounded score-bearing bottleneck upstream of pressure ranking, with an
offline causal/replay gate and a new seed namespace before another engine
pilot.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-score-alignment-pilot-v2 \
  --backend engine-live \
  --cohort pressure_score_alignment_pilot_v2 \
  --workers 3 \
  --server-ports 6001,6002,6003
```

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-pressure-score-alignment-pilot-v2/games/impact_pair/pressure_score_alignment_pilot_v2/treatment \
  --maximum-files 40 \
  --relative-to artifacts/freeciv/pf-pressure-score-alignment-pilot-v2 \
  --output artifacts/freeciv/pf-pressure-score-alignment-pilot-v2/pressure-replay-40.json
```

Machine-readable summary evidence is in
[`pf-pressure-score-alignment-pilot-v2.json`](pf-pressure-score-alignment-pilot-v2.json).
