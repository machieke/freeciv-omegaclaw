# PF-PLN candidate-scoped direct-completion offline acceptance

Status: deterministic, retrospective replay, and fresh 40-pair engine/replay
acceptance passed

## Diagnosed scope defect

The completed opportunity-cost pilot had 28 zero-score pairs, nine positive
pairs, and three negative pairs. Its nonzero paired score deltas were seven
`+1`, one `+2`, one `+5`, two `-3`, and one `-1`.

Four of the five safe direct-completion displacements were concentrated in
the two `-3` pairs:

- seed `2924762` deferred the same currently legal city-founding action on
  turns 30, 31, and 32. The city was finally founded on turn 33. Relative to
  baseline, the treatment retained the same city count but lost two citizen
  score points and one residual score point at the turn-60 horizon.
- seed `2957349` selected an untried generic exploration move instead of a
  move onto an exact packet-known hut on turn 15. The treatment gained two
  technology score points but lost five residual score points.

The fourth city-founding displacement occurred in a positive `+1` pair at
seed `2923300`, so this retrospective association is not causal score
evidence. The remaining `-1` pair had no direct-completion displacement.

The exact turn traces nevertheless demonstrate a semantic scope defect. Four
failed settlement sites had reduced the run-global `city_founding`
conductance to `0.6703200460`. The planner had already excluded those exact
failed sites before pressure ranking, but their category-wide penalty then
demoted a newly legal build-city action at three distinct subsequent sites.
Candidate/site failure was therefore counted once by authoritative pruning
and again outside its grounding by category conductance.

The known-hut audit also separates direct completion from preparation. The
`2957349` action entered an exact packet-known hut and is a direct completion.
The other safe hut-related displacement, at seed `2923300` turn 19, only
reduced distance from two tiles to one. It remains a learnable preparatory
route and is deliberately unchanged.

## Correction

A candidate-scoped optimistic floor now applies only when:

1. the current legal set contains a `unit_build_city` candidate, or a
   `hut_exploration` move whose grounded projection says
   `target_is_known_hut=true`;
2. that direct-completion category has the highest grounded action utility
   among categories serving the same goal; and
3. its learned category conductance is below the configured initial
   conductance.

The correction uses the initial prior for that decision without mutating the
learned ledger. Preparatory expansion and hut approaches retain their learned
conductance. A higher-valued move toward a demonstrably better settlement
site also remains preferred. Unchanged failed actions, exact failed
settlement sites, and repeated failed destinations continue to be suppressed
before pressure ranking.

Every pressure decision now records, per present category, learned and
effective conductance, whether the floor applied, and the authoritative
direct-completion source under `conductance_state.decision_routes`.

## Deterministic and replay acceptance

The pressure and Impact suites prove:

- a failed site cannot penalize a newly legal settlement completion;
- failures on other hut approaches cannot penalize an exact known-hut entry;
- preparatory hut routes remain conductance-learnable;
- the floor cannot override a higher-valued same-goal action;
- recorded pre-correction semantics can be reconstructed exactly; and
- emitted pressure, schedule, conductance, and event artifacts remain
  deterministic and schema-valid.

A read-only counterfactual reconstructed all 2,535 opportunity-cost treatment
decisions from their recorded grounded goals, candidate sets, utilities,
pressure configuration, and learned conductance. The pre-correction selection
matched in all 2,535 decisions, with zero integrity failures.

The correction changes five decisions (0.1972%): four
`expansion_move -> city_founding` decisions and one
`exploration_move -> hut_exploration` decision. Grounded selected utility
increases by 415 points across those local decisions. It leaves the
higher-valued settlement move and the preparatory hut approach unchanged.

Reproduce the counterfactual with:

```bash
PYTHONPATH=src:benchmarks python3 \
  scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-pressure-opportunity-cost-pilot-v1/games/impact_pair/pressure_opportunity_cost_pilot_v1/treatment \
  --maximum-files 40 \
  --direct-completion-counterfactual \
  --relative-to artifacts/freeciv/pf-pressure-opportunity-cost-pilot-v1 \
  --output artifacts/freeciv/pf-pressure-opportunity-cost-pilot-v1/direct-completion-counterfactual-40.json
```

The artifact SHA-256 is
`9b57bd6744f4e3e156b2b0d3177be4376450c308d463dfb8ee985c11c74b2602`;
its structural artifact hash is
`b1795f6dc6be9180e1d15da8256cc677b2ca337a86c07d29ec548c2f3d79c0e2`,
and its source-set hash is
`d8de8ff6e65e28b14d2fc4683dfff8cc5d4367a7044d7593c0ecc2a421f8f636`.

This counterfactual is decision-local. Once the first revised action executes,
later states and candidate sets may diverge, so the three successive
`2924762` rows are not three independent expected engine changes. Replay
cannot estimate score or win rate.

## Fresh empirical gate

`pressure_direct_completion_pilot_v1` predeclares 40 fresh paired seeds
derived by `sha256-counter-v1` under namespace
`pf-pln-pressure-direct-completion-pilot-v1`, bounded to the disjoint
3,000,000–3,099,999 range. It retains turn 60, exact pressure-only arm
isolation, clean-source enforcement, and three controller workers.

This cohort subsequently completed all 40 pairs and passed source,
initial-state, arm-isolation, safety, event-schema, decision-provenance, and
exact-replay gates. Score changed by +0.475 with interval [0.075, 0.975] and
exact sign-flip p=0.046875. Lead rate changed by +2.5 points with only three
discordant pairs and McNemar p=1.0.

The result was directionally strong enough to justify the separately
predeclared, score-only `pressure_direct_completion_confirmatory_v1` cohort,
but remained a claim-ineligible pilot and was not pooled. That 100-pair
confirmation subsequently completed with a +0.03 score delta, interval
[-0.25, 0.31], and exact sign-flip p=0.8912. It did not support a score
improvement claim. Full evidence is in
[`pf-pressure-direct-completion-pilot-v1.md`](pf-pressure-direct-completion-pilot-v1.md)
and
[`pf-pressure-direct-completion-confirmatory-v1.md`](pf-pressure-direct-completion-confirmatory-v1.md).
