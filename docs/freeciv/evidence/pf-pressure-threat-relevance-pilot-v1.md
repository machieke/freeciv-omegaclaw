# PF-PLN threat-relevance pilot v1

Status: complete, diagnostic pilot only

The predeclared `pressure_threat_relevance_pilot_v1` cohort completed all 40
fresh paired seeds (80 engine arms) at turn 60. It had zero infrastructure
failures, exact 20/20 arm-order balance, matched initial states, passing safety
gates, and one clean source identity at commit `edbf71f`.

The treatment changed mean score by +0.10 points with a 95% paired-bootstrap
interval of [-0.725, 1.050]. Mean score was 115.725 for baseline and 115.825
for treatment. The exact paired sign-flip p-value was 0.897. This is no
evidence of a score improvement.

Fixed-horizon lead rate was 17.5% for baseline and 15.0% for treatment, a
difference of -2.5 percentage points with interval [-12.5, 7.5]. Five pairs
were discordant: three favored baseline and two favored treatment (exact
McNemar p=1.0). The pilot is not eligible for a performance claim and does not
justify a fresh confirmatory cohort.

## Semantic and replay acceptance

All 80 completed event files pass the v1 event schema. Exact read-only replay
covered all 40 treatment traces and 2,748 pressure decisions. All schedule
hashes and selected operations reproduced with zero integrity failures.

Pressure changed 229 decisions (8.33%), down from 282/2,856 (9.87%) in the
preceding grounded goal-relief pilot. Survival grounding was observed in all
three predeclared contexts:

- 1,924 distant-safe decisions used
  `authoritative:no-proximate-visible-threat-or-defense-deficit`;
- 609 decisions used the grounded radius-three proximate-threat context; and
- 215 decisions used the grounded defense-deficit context.

The treatment emitted 3,061 idempotent v2 conductance updates: 2,166
effect-without-relief decays, 425 direct relief credits, 325 downstream relief
credits, and 145 candidate-specific no-progress updates.

## Outcome diagnosis

The proximity gate behaved as intended. Compared with the preceding
seed-disjoint diagnostic pilot, `expansion_move -> tactical_move`
substitutions fell from 58 to 16 and
`exploration_move -> tactical_move` substitutions fell from 47 to 27.
Exploration improved by +2.10 positions with interval [0.05, 4.725].

That behavioral improvement did not become a score improvement. Settlement
attempts changed by -0.10 with interval [-0.225, 0.0], settlement completions
and cities founded both changed by -0.025 with interval [-0.075, 0.0], and
one treatment seed founded one fewer city. Meaningful action rate changed by
+0.0329 actions/turn with interval [-0.0383, 0.1013]. Engine rejection stayed
at zero in both arms.

The dominant remaining substitutions expose a separate semantic problem:

- 43 `expansion_move` choices became `exploration_move`;
- 29 `production_preexpansion_growth` choices became `city_defense`;
- 27 `exploration_move` choices became `tactical_move`;
- 22 `tactical_move` choices became `exploration_move`; and
- 17 `production_economy` choices became `city_defense`.

In total, 81 baseline choices became `city_defense`. Candidate presence
currently makes survival fully unsatisfied whenever either a
`production_defense` or `city_defense` candidate exists. But a
`city_defense` candidate means a sole combat unit is already on the city tile
and may legally fortify; it does not establish that the city lacks a defender.
This conflates a fortification opportunity with an actual defense deficit and
lets routine fortification preempt score-bearing production even without a
proximate threat.

The next semantic target is therefore defense-relevance grounding:
`production_defense` may continue to ground a real count deficit, while
`city_defense` should activate survival pressure only in the presence of a
grounded proximate threat. This is a truth-grounding correction, not weight
tuning against the observed scores.

The paired score SD was 2.8983, making the approximate detectable effect at 40
pairs 1.2838 points. The generic power recommendation to freeze confirmation
is rejected because the observed score effect is only +0.10, its interval
includes harm, and the lead-rate estimate is negative.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-threat-relevance-pilot-v1 \
  --backend engine-live \
  --cohort pressure_threat_relevance_pilot_v1 \
  --workers 3 \
  --server-ports 6001,6002,6003
```

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-pressure-threat-relevance-pilot-v1/games/impact_pair/pressure_threat_relevance_pilot_v1/treatment \
  --maximum-files 40 \
  --output artifacts/freeciv/pf-pressure-threat-relevance-pilot-v1/pressure-replay-40.json
```

Machine-readable results, source identities, configuration identity, and
artifact hashes are recorded in
[`pf-pressure-threat-relevance-pilot-v1.json`](pf-pressure-threat-relevance-pilot-v1.json).
