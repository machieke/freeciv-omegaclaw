# PF-PLN defense-relevance pilot v1

Status: complete, diagnostic pilot only

The predeclared `pressure_defense_relevance_pilot_v1` cohort completed all 40
fresh paired seeds (80 engine arms) at turn 60. It had zero infrastructure
failures, exact 20/20 arm-order balance, matched initial states, passing safety
gates, and one clean source identity at commit `29a0b9c`.

Mean score was 117.50 for baseline and 117.55 for treatment. The paired score
delta was +0.05 with a 95% paired-bootstrap interval of [-0.300, 0.475] and
exact paired sign-flip p=0.907. Fixed-horizon lead rate was 22.5% in both
arms, a difference of 0.0 percentage points with interval [-7.5, 7.5]. Two
pairs were discordant, one in each direction (exact McNemar p=1.0).

This is no evidence of a score or lead-rate improvement. The pilot is
claim-ineligible and does not justify a fresh confirmatory cohort.

## Semantic and replay acceptance

All 80 completed event files pass the v1 event schema. Exact read-only replay
covered all 40 treatment traces and 2,708 pressure decisions. All schedule
hashes and selected operations reproduced with zero integrity failures.
Pressure changed 220 decisions (8.12%).

The corrected defense grounding was exercised as declared:

- 2,202 decisions used the distant-safe context;
- 498 decisions used the radius-three proximate-threat context;
- 8 decisions used
  `authoritative:grounded-production-defense-deficit`; and
- zero decisions emitted the retired generic defense-deficit context.

Only four baseline choices became `city_defense`, down from 81 in the
preceding seed-disjoint threat-relevance pilot. This 95.1% reduction accepts
the semantic correction: a routine legal fortification opportunity no longer
manufactures survival pressure, while actual production coverage deficits and
proximate threats remain grounded.

The treatment emitted 3,025 idempotent v2 conductance updates: 2,171
effect-without-relief decays, 409 direct relief credits, 319 downstream relief
credits, and 126 candidate-specific no-progress updates.

## Outcome diagnosis

Settlement attempts changed by +0.05 with interval [-0.05, 0.175];
settlement completions and cities founded both changed by +0.025 with interval
[-0.05, 0.125]. Explored positions changed by +0.80 with interval
[-1.70, 3.30]. Meaningful action rate changed by -0.0079 actions/turn with
interval [-0.0808, 0.0629], and engine rejection remained zero in both arms.
These are all operationally safe, statistically neutral estimates.

The dominant changed routes expose the next adapter-level correctness issue:

- 66 `expansion_move` choices became `exploration_move`;
- 44 safe `city_defense` choices became `exploration_move`;
- 43 `tactical_move` choices became `exploration_move`;
- 20 `exploration_move` choices became `tactical_move`; and
- 9 `hut_exploration` choices became `expansion_move`.

Within a category, candidate actions are represented as OR premises. Reverse
pressure is therefore divided across every legal alternative before operations
from different goals are compared. In captured decisions, seven expansion
moves competing with five exploration moves gave the best expansion operation
priority 0.0091 and the best exploration operation 0.0106, even though the
expansion goal had greater declared utility and the baseline expansion action
had greater grounded action utility. Adding equivalent legal alternatives can
therefore change the winning goal without changing authoritative state,
category conductance, or the best action in either category.

The next semantic target is category-level enumeration invariance: every
operation that resolves the same category should receive the category's
pressure, while grounded utility chooses the operation within that category.
Candidate cardinality must not dilute a goal during cross-category selection.
This is an adapter correction; generic PF-PLN OR pressure transport remains
unchanged.

The paired score SD was 1.2598, making the approximate detectable effect at 40
pairs 0.5581 points. The observed +0.05 effect and its interval provide no
positive pilot signal, so the generic power recommendation to freeze
confirmation is rejected.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-defense-relevance-pilot-v1 \
  --backend engine-live \
  --cohort pressure_defense_relevance_pilot_v1 \
  --workers 3 \
  --server-ports 6001,6002,6003
```

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-pressure-defense-relevance-pilot-v1/games/impact_pair/pressure_defense_relevance_pilot_v1/treatment \
  --maximum-files 40 \
  --output artifacts/freeciv/pf-pressure-defense-relevance-pilot-v1/pressure-replay-40.json
```

Machine-readable results, source identities, configuration identity, and
artifact hashes are recorded in
[`pf-pressure-defense-relevance-pilot-v1.json`](pf-pressure-defense-relevance-pilot-v1.json).
