# PF-PLN score-alignment v2 offline acceptance

Status: implementation and retrospective acceptance passed; fresh pilot pending

## Mechanism

The v1 fresh pilot rejected strict score alignment: score changed by -0.70
with interval [-1.45, -0.15]. Root-cause analysis showed that the guard treated
small differences in bounded heuristic utility as calibrated score evidence,
disabled positional exploration pressure, and left materially different
safety responses interchangeable.

`grounded-impact-planner/1.4` replaces those assumptions with:

- a 5% relative uncertainty band around the best grounded utility;
- zero category opportunity cost inside that band and cost only for utility
  loss beyond it;
- pressure eligibility for candidates inside the band;
- positional exploration pressure even when fog is disabled;
- the same uncertainty guard among safety-compatible candidates; and
- unchanged guaranteed-score, explicit-deadline, threat-binding, causal, and
  lexicographic safety firewalls.

The 5% band covers the observed movement gaps of 3, 6, and 12 points on
utilities near 650-690, and the 20.5-point expansion gap near 960. It does not
cover the harmful safety substitutions from utility 680 to 592 or 628.
This is an explicit uncertainty declaration for heuristic values, not a fitted
score coefficient.

Direct planner consumers retain a zero-tolerance default. The engine profile
declares `pressure_score_alignment_utility_tolerance: 0.05` and
`pressure_exploration_information_enabled: true`.

## Retrospective replay

Read-only v2 replay over all 2,338 immutable v1 treatment decisions changes 66
recorded choices. It restores:

- 25 `tactical_move -> exploration_move` decisions;
- 16 `tactical_move -> city_defense` decisions; and
- 4 `production_preexpansion_growth -> production_expansion` decisions.

The restored set includes the first harmful
`exploration_move -> tactical_move` divergence in seeds `3324283`, `3337005`,
and `3389347`, the first harmful `city_defense -> tactical_move` divergence in
seed `3349799`, and the first harmful
`production_expansion -> production_preexpansion_growth` divergence in seed
`3371220`.

The replay artifact hash is
`358af80728a7321885915a56004f1ac4264a8e65795287541797c73334772028`.
It reduces guard rejections from 6,853 recorded v1 candidate rows to 4,244
recomputed rows while retaining all 31 explicit deadline rejections.

Replay holds the recorded state and candidate set fixed. It cannot evolve the
engine after the first changed operation, and old artifacts lack enough actor
geometry to reproduce live threat binding exactly. These results establish
mechanism targeting only; they do not estimate a v2 score effect.

Reproduction:

```bash
PYTHONPATH=src:benchmarks python3 \
  scripts/freeciv/replay_pressure_decisions.py \
  --score-alignment-counterfactual \
  --exploration-information-enabled \
  --score-alignment-utility-tolerance 0.05 \
  artifacts/freeciv/pf-pressure-score-alignment-pilot-v1/games/impact_pair/pressure_score_alignment_pilot_v1/treatment \
  --maximum-files 40 \
  --relative-to artifacts/freeciv/pf-pressure-score-alignment-pilot-v1 \
  --output artifacts/freeciv/pf-pressure-score-alignment-pilot-v1/score-alignment-v2-counterfactual-40.json
```

## Fresh gate

`pressure_score_alignment_pilot_v2` predeclares 40 fresh pairs from the
seed-disjoint namespace `pf-pln-pressure-score-alignment-pilot-v2` in range
`3400000..3499999`. Both arms enable the same pressure, conductance learning,
positional exploration, and 5% tolerance configuration. The only effective
arm difference is `pressure_score_alignment_enabled`.

V1 explicitly pins no-information exploration and zero tolerance in both arms,
so its historical design remains reproducible.

Acceptance requires:

- 40 complete pairs and 80 current arms on one clean, stable source identity;
- paired initial-state fidelity and exact within-pair ordering;
- zero engine rejection and model safe-fallback rates;
- every event stream schema-valid;
- exact replay of every treatment decision with zero integrity failures;
- safety-active decisions selecting only grounded survival categories;
- intervention and first-divergence diagnostics; and
- paired score and lead estimates reported regardless of direction.

The v2 pilot remains claim-ineligible. It cannot be pooled with v1, stopped
early, or promoted without a separately predeclared confirmation.

After committing the implementation:

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-score-alignment-pilot-v2 \
  --backend engine-live \
  --cohort pressure_score_alignment_pilot_v2 \
  --workers 3 \
  --server-ports 6001,6002,6003
```
