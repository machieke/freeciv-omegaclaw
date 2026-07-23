# PF-PLN category enumeration-invariance pilot v1

Status: complete, diagnostic pilot only

The predeclared `pressure_category_invariance_pilot_v1` cohort completed all
40 fresh paired seeds (80 engine arms) at turn 60. It had zero infrastructure
failures, exact 20/20 arm-order balance, matched initial states, passing safety
gates, and one clean source identity at commit `d2e1971`.

Mean score was 116.10 for baseline and 115.875 for treatment. The paired score
delta was -0.225 with a 95% paired-bootstrap interval of [-0.800, 0.325] and
exact paired sign-flip p=0.507. Fixed-horizon lead rate was 25.0% for baseline
and 22.5% for treatment, a difference of -2.5 percentage points with interval
[-7.5, 0.0]. The only discordant pair favored baseline (exact McNemar p=1.0).

This is no evidence of a score or lead-rate improvement. The pilot is
claim-ineligible and does not justify a fresh confirmatory cohort.

## Semantic and replay acceptance

All 80 completed event files pass the v1 event schema. Exact read-only replay
covered all 40 treatment traces and 2,553 pressure decisions. All schedule
hashes and selected operations reproduced with zero integrity failures.
Pressure changed 233 decisions (9.13%).

Every operation in the same category received exactly the same category-level
priority in all 2,553 decisions. There were zero enumeration-invariance
violations. Compared with the preceding seed-disjoint defense-relevance pilot,
`expansion_move -> exploration_move` substitutions fell from 66 to 29. This
accepts the adapter correction: legal action count no longer dilutes a
category during cross-goal comparison.

Survival grounding remained intact: 2,067 decisions used the distant-safe
context, 473 used the radius-three proximate-threat context, and 13 used the
grounded production-defense-deficit context. The treatment emitted 2,861
idempotent v2 conductance updates: 1,981 effect-without-relief decays, 410
direct relief credits, 310 downstream relief credits, and 160
candidate-specific no-progress updates.

## Outcome diagnosis

The correction removed one source of arbitrary selection without improving
outcomes. Settlement attempts changed by -0.20 with interval [-0.575, 0.0].
Settlement completions and cities founded both changed by -0.025 with interval
[-0.075, 0.0]. Explored positions changed by -0.30 with interval
[-3.475, 2.425]. Meaningful action rate changed by -0.005 actions/turn with
interval [-0.0854, 0.0658], and engine rejection remained zero in both arms.

The dominant changed routes expose the next scheduler-adapter problem:

- 42 safe `city_defense` choices became `exploration_move`;
- 42 `tactical_move` choices became `exploration_move`;
- 32 high-utility `hut_exploration` choices became `expansion_move`;
- 29 `expansion_move` choices became `exploration_move`;
- 20 `expansion_move` choices became `tactical_move`; and
- 21 immediate `city_founding` choices became another category.

Category pressure is now invariant, but absolute grounded action value is
normalized independently inside each goal before the categories are compared.
For example, a 937-utility packet-grounded hut move had priority 0.063 while
an 859-utility expansion move had priority 0.172. A 1,000-utility immediate
city founding action could similarly lose to a 640-utility exploration move.
The operation scheduler therefore sees goal pressure but not the opportunity
cost already encoded by the grounded Impact planner.

The next target is cross-goal opportunity-cost integration. It must preserve
the category-invariance result and urgent safety selection, while counting
absolute grounded action value exactly once at scheduling. It must not tune
goal weights against this cohort. A deterministic gate should prove that
equivalent-category cardinality remains irrelevant, high-value immediate
actions are not displaced by lower-value non-safety actions solely because
they belong to different goals, and a grounded proximate survival threat can
still preempt them.

The paired score SD was 1.7901, making the approximate detectable effect at 40
pairs 0.7930 points. The observed negative estimate, its interval, and the
one-sided lead loss provide no positive pilot signal, so the generic power
recommendation to freeze confirmation is rejected.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-category-invariance-pilot-v1 \
  --backend engine-live \
  --cohort pressure_category_invariance_pilot_v1 \
  --workers 3 \
  --server-ports 6001,6002,6003
```

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-pressure-category-invariance-pilot-v1/games/impact_pair/pressure_category_invariance_pilot_v1/treatment \
  --maximum-files 40 \
  --output artifacts/freeciv/pf-pressure-category-invariance-pilot-v1/pressure-replay-40.json
```

Machine-readable results, source identities, configuration identity, and
artifact hashes are recorded in
[`pf-pressure-category-invariance-pilot-v1.json`](pf-pressure-category-invariance-pilot-v1.json).
