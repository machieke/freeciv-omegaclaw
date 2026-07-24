# PF-PLN cross-goal opportunity-cost pilot v1

Status: complete, diagnostic pilot only

The predeclared `pressure_opportunity_cost_pilot_v1` cohort completed all 40
fresh paired seeds (80 engine arms) at turn 60. It had zero infrastructure
failures, exact 20/20 arm-order balance, matched initial states, passing safety
gates, and one clean source identity at commit `a31a3a6`.

Mean score was 118.20 for baseline and 118.375 for treatment. The paired score
delta was +0.175 with a 95% paired-bootstrap interval of [-0.175, 0.550] and
exact paired sign-flip p=0.450. Fixed-horizon lead rate was 25.0% for baseline
and 30.0% for treatment, a difference of +5.0 percentage points with interval
[0.0, 12.5]. Both discordant pairs favored treatment, but exact McNemar p was
0.5.

This is the first fresh pressure pilot with positive score and lead-rate point
estimates. It is still claim-ineligible and statistically inconclusive. The
score interval crosses zero, only two pairs inform the lead-rate difference,
and neither exact test rejects its null. No confirmatory claim is frozen.

## Semantic and replay acceptance

All 80 completed event files pass the v1 event schema. Exact read-only replay
covered all 40 treatment traces and 2,535 pressure decisions. All schedule
hashes and selected operations reproduced with zero integrity failures.
Pressure changed 135 decisions (5.33%).

All operations in one category received identical category priority and
cross-goal opportunity cost in every decision. There were zero cardinality
invariance violations. The scheduler emitted 453 finite, schema-valid
`safety_firewall` rejections across 107 decisions with an authoritative
survival deficit and a grounded survival operation. Every one of those
decisions selected a survival operation.

Survival grounding remained bounded: 2,022 decisions used the distant-safe
context, 499 used the radius-three proximate-threat context, and 14 used the
grounded production-defense-deficit context. The treatment emitted 2,866
idempotent v2 conductance updates: 2,028 effect-without-relief decays, 430
direct relief credits, 335 downstream relief credits, and 73 no-progress
updates.

## Outcome and remaining diagnosis

Settlement attempts changed by -0.075 with interval [-0.375, 0.150].
Settlement completions and cities founded changed by +0.025 with interval
[0.000, 0.075]. Production changes increased by +0.15 with interval
[0.025, 0.300]. Explored positions changed by -0.50 with interval
[-2.10, 1.025], meaningful action rate changed by -0.0304 actions/turn with
interval [-0.0871, 0.0196], and engine rejection remained zero in both arms.

The largest remaining substitutions were:

- 38 safe `city_defense` choices became `exploration_move`;
- 29 safe `tactical_move` choices became `exploration_move`;
- 15 `expansion_move` choices became safety-active `tactical_move`;
- 14 `exploration_move` choices became safety-active `tactical_move`; and
- 10 immediate `city_founding` choices became a safety operation.

Those routes follow the intended safety and relevance semantics. Six
non-safety direct opportunities still lost within or near their own goal:
four `city_founding` choices became `expansion_move`, one known-hut choice
became `exploration_move`, and one known-hut choice lost by one utility point
to `expansion_move`. They followed learned conductance differences rather than
category cardinality. Before another change, paired outcome heterogeneity and
these direct-relief traces should be audited to establish whether this is a
correct learnable failure response or an avoidable delay.

The paired score SD was 1.1742, making the approximate detectable effect at
40 pairs 0.5202 points. The harness's generic recommendation to freeze 30
pairs concerns a predeclared two-point effect, not the observed +0.175-point
signal. A similarly sized true effect would require hundreds of fresh pairs
for a precise two-sided claim. A larger cohort must be separately
predeclared; this pilot cannot be promoted or pooled.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-opportunity-cost-pilot-v1 \
  --backend engine-live \
  --cohort pressure_opportunity_cost_pilot_v1 \
  --workers 3 \
  --server-ports 6001,6002,6003
```

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-pressure-opportunity-cost-pilot-v1/games/impact_pair/pressure_opportunity_cost_pilot_v1/treatment \
  --maximum-files 40 \
  --output artifacts/freeciv/pf-pressure-opportunity-cost-pilot-v1/pressure-replay-40.json
```

Machine-readable results, source identities, configuration identity, and
artifact hashes are recorded in
[`pf-pressure-opportunity-cost-pilot-v1.json`](pf-pressure-opportunity-cost-pilot-v1.json).
