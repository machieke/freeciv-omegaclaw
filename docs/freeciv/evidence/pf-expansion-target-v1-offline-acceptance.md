# PF-PLN expansion target v1 offline acceptance

Status: implementation, offline opportunity audit, fresh pilot, and
claim-eligible confirmation passed

## Score-bearing bottleneck

The score-alignment v2 pilot made 144 local treatment decisions differ from
canonical grounded ordering, but score changed by -0.025 with interval
[-0.275, 0.250]. Its decision changes mostly rearranged movement and
fortification. They did not create a new population, technology, or residual
score path.

Turn-60 score was dominated by 102.25 technology points already present at
the randomized start, while the controllable citizen component averaged
12.975. Both arms founded 1.9 cities on average and 36/40 baseline games
finished with the configured three-city target. No treatment changed the city
count. The next mechanism therefore moves upstream from pressure tie-breaking
to a grounded population-producing operation.

## Read-only opportunity audit

The immutable 40 baseline traces from
`pressure_score_alignment_pilot_v2` were scanned without changing their
recorded outcomes. For each authoritative state at three cities, the audit
reconstructed only ruleset-backed `city_production` alternatives from each
city's exact `buildable` list and evaluated horizon-score production with a
four-city target.

The reconstruction found a positive projected founder path in 30/40 seeds and
187 snapshots. In 18 seeds the first such path retained at least 15 projected
turns after settlement. These are opportunities, not counterfactual engine
outcomes: old event streams retain the legal-action digest and exact city
buildability but not the complete legal-action set needed to replay every
actor and downstream state.

The observed three-city traces provide a conservative boundary check. Four
new cities were first observed with 15–19 turns remaining. They finished at
sizes 2, 2, 4, and 5. After the ruleset's two-citizen founder cost, every
observed case was non-negative in citizen count at the horizon. This small,
post hoc sample selects a safety boundary for a fresh test; it is not a score
estimate.

## Implementation

`grounded-impact-planner/1.5` adds
`expansion_minimum_settlement_runway_turns`. Horizon-score production can
start a founder only when its exact ruleset shield/population ETA plus the
grounded route ETA leaves at least that many turns after settlement.
Granary-first founder sequences apply the same boundary to their combined
build and settlement ETA.

The default is zero, preserving every historical cohort and direct planner
consumer. The fresh cohort sets the gate to 15 in both arms. It does not
change city-founding legality, the execution gate, route pruning, safety,
pressure, conductance learning, the utility uncertainty band, or model
behavior.

Deterministic acceptance proves:

- a founder with exactly 15 projected post-settlement turns remains eligible;
- the same founder one turn later is rejected;
- a Granary-first sequence below the boundary cannot bypass the gate;
- boolean, negative, non-integral, and over-bounded settings fail closed;
- the fresh arms differ only in `expansion_city_target`; and
- pressure snapshot replay remains exact under adapter identity `1.5`.

The focused pressure, impact, harness, runtime, and event suites pass all 222
tests. The checked snapshot replay artifact hash is
`63d0db5ec8e19cce911c69d56b3e1a3a98bcc49828460eeb00c840b5701cf8a3`.

## Fresh gate

`expansion_target_pilot_v1` predeclares 40 fresh pairs from namespace
`pf-pln-expansion-target-pilot-v1` in range `3500000..3599999`. Both arms use
turn 60, pressure, conductance learning, score alignment v2, and the same
15-turn settlement runway. Baseline targets three cities; treatment targets
four. `expansion_city_target` is the only effective arm difference.

Acceptance requires:

- 40 complete pairs and 80 current arms on one clean, stable source identity;
- balanced arm order and exact paired initial-state fidelity;
- zero engine rejection and model safe-fallback rates;
- every event stream schema-valid;
- exact replay of every treatment pressure decision;
- no safety-category selection violation;
- treatment exposure reported through founder production, settlement, city,
  and citizen-component deltas; and
- paired score, margin, and lead estimates reported regardless of direction.

The pilot completed all 40 pairs and 80 arms on clean commit `c44b664`, with
zero failures and every correctness and safety gate passing. Score changed by
+2.025 with interval [+0.800, +3.250] and exact paired p=0.002818. Treatment
added 0.90 settlements and 2.525 citizen points on average. Technology was
unchanged. Full evidence is in
[`pf-expansion-target-pilot-v1.md`](pf-expansion-target-pilot-v1.md).

The pilot is claim-ineligible and is not pooled with any prior cohort. Its
direction, interval, exact test, and aligned mechanism diagnostics justify the
separately frozen `expansion_target_confirmatory_v1` cohort: 100 fresh,
score-only pairs, powered for a 1.5-point effect at paired SD up to 5.0. The
confirmation retains the implementation and every policy value unchanged.

The confirmation completed 100/100 fresh pairs on clean commit `c7747db`.
Mean score increased by +2.66 with interval [+2.00, +3.32] and exact paired
p=9.214e-12. Treatment added 0.82 settlements and 2.74 citizen-score points
on average. All 200 current event streams, every safety gate, and exact replay
of all 7,425 treatment decisions passed. This supports the predeclared
turn-60 own-score claim. It does not support a win-rate claim or an effect
strictly greater than two points. Full evidence is in
[`pf-expansion-target-confirmatory-v1.md`](pf-expansion-target-confirmatory-v1.md).

After committing the implementation:

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-expansion-target-pilot-v1 \
  --backend engine-live \
  --cohort expansion_target_pilot_v1 \
  --workers 3 \
  --server-ports 6001,6002,6003
```
