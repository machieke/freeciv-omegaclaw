# PF-PLN grounded goal-relief pilot v1

Status: complete, diagnostic pilot only

The predeclared `pressure_goal_relief_pilot_v1` cohort completed all 40 fresh
paired seeds (80 engine arms) at turn 60. The completed cohort had zero active
infrastructure failures, exact 20/20 arm-order balance, matched paired initial
states, passing safety gates, and clean source commit `38cc3f9`.

The treatment changed mean score by -0.05 points with a 95% paired-bootstrap
interval of [-0.775, 0.600]. The exact paired sign-flip p-value was 0.946.
Mean score was 118.55 for baseline and 118.50 for treatment. This is no
evidence of a score improvement.

Fixed-horizon lead rate was 32.5% for baseline and 25.0% for treatment, a
difference of -7.5 percentage points with interval [-17.5, 0.0]. Only three
pairs were discordant and all three favored baseline (exact McNemar p=0.25),
so this is not a statistically reliable win-rate degradation, but it is a
clear reason not to freeze a confirmatory cohort.

The first launch created two historical preflight failures because
`FREECIV_RULESET_ROOT` was absent. The same predeclared seed was rerun after
supplying the pinned ruleset path. The final 80-arm runner summary reports zero
infrastructure failures and stable source identity; the historical attempts
are excluded from all paired estimates.

## Semantic and replay acceptance

All 80 completed event files pass the v1 event schema. Exact read-only replay
covered all 40 treatment traces and 2,856 pressure decisions. All schedule
hashes and selected operations reproduced with zero integrity failures.
Every decision recorded four nonempty grounded goal contexts and initial
conductance 1.0.

Pressure changed 282 decisions (9.87%). The new learning path emitted 3,232
idempotent v2 conductance updates:

- 2,243 locally successful effects without measurable goal relief;
- 492 direct authoritative goal-relief updates;
- 390 downstream same-goal route credits; and
- 107 candidate-specific no-effect updates.

Direct and downstream relief never decreased conductance. Goal-neutral effects
received only the declared one-quarter no-progress decay, while actual
no-effect outcomes received full decay. This satisfies the implementation
gate: local action execution no longer manufactures positive teleological
credit, and a later authoritative goal change can credit a pending category
route once.

## Outcome diagnosis

The paired score SD was 2.2412, making the approximate detectable effect at 40
pairs 0.993 points. The score interval's upper bound is only 0.600 and its
lower bound is -0.775. The generic power report's suggestion to freeze a
confirmatory sample is therefore rejected: statistical precision without a
positive pilot signal is not a reason to spend fresh confirmatory seeds.

City founding was exactly unchanged in every pair. Action-rate delta was
+0.0067 actions/turn with interval [-0.0875, 0.1004], loop-latency delta was
-6.1 ms with interval [-52.7, 41.7], and engine rejection remained zero in
both arms. The correction is operationally safe but outcome-neutral.

The dominant changed routes reveal the next semantic problem:

- 58 `expansion_move` choices became `tactical_move`;
- 47 `exploration_move` choices became `tactical_move`;
- 39 `expansion_move` choices became `exploration_move`; and
- 22 `production_preexpansion_growth` choices became `city_defense`.

The seven negative-score pairs averaged 1.71 fewer citizen score points and
7.86 fewer explored positions. All three lead losses included tactical or
defense substitutions. The current survival goal becomes fully unsatisfied
when any opponent is packet-visible, regardless of distance or relevance to
an owned city. That coarse truth grounding explains why distant opponents can
redirect score-bearing expansion, exploration, and production.

The next implementation target is threat-relevant survival grounding:
packet-visible opposition should activate the safety goal only when a
grounded proximity or direct-threat predicate connects it to owned assets.
This is a semantic correction, not weight tuning against the pilot.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-goal-relief-pilot-v1 \
  --backend engine-live \
  --cohort pressure_goal_relief_pilot_v1 \
  --workers 3 \
  --server-ports 6001,6002,6003
```

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-pressure-goal-relief-pilot-v1/games/impact_pair/pressure_goal_relief_pilot_v1/treatment \
  --maximum-files 40 \
  --output artifacts/freeciv/pf-pressure-goal-relief-pilot-v1/pressure-replay-40.json
```

Machine-readable results, source identities, configuration identity, and
artifact hashes are recorded in
[`pf-pressure-goal-relief-pilot-v1.json`](pf-pressure-goal-relief-pilot-v1.json).
