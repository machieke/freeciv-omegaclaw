# PF-PLN cross-goal opportunity-cost offline acceptance

Status: deterministic, retrospective replay, and fresh 40-pair engine/replay
acceptance passed

The grounded Impact adapter now treats the utility lost by choosing another
goal's best current action as an opportunity cost at scheduling time. All
operations serving one goal share that cost. This preserves category
enumeration invariance and leaves conductance free to choose or abandon routes
within the goal instead of locking the highest-utility category in place.

When an authoritative survival deficit is active and the legal set contains a
grounded survival operation, safety becomes lexicographic: non-survival
operations remain visible in the schedule with `reason=safety_firewall`, but
are inadmissible for that cycle. The opportunity-cost ceiling is then computed
only over the actionable safety goal. If there is no grounded survival
operation, the scheduler does not reject every available action.

Deterministic acceptance proves:

- a lower-value expansion action cannot displace a higher-value packet-known
  hut action merely because the two belong to independently normalized goals;
- adding dominated operations to either category does not change category
  pressure, category cost, or the selected category;
- grounded utility still chooses the best operation within a category;
- repeated authoritative no-progress feedback can still make the scheduler
  abandon one route for another route serving the same goal;
- a proximate visible threat makes the grounded survival operation
  lexicographically admissible over higher-value non-safety work; and
- rejected scores are finite, schema-valid, explicitly explained, and exactly
  replayable.

Run the deterministic gate with:

```bash
PYTHONPATH=src:benchmarks python3 -m pytest -q \
  Autotests/test_freeciv_pressure.py \
  Autotests/test_freeciv_impact.py \
  Autotests/test_freeciv_harness.py
```

## Retrospective scheduling counterfactual

A read-only counterfactual held the completed category-invariance pilot's
pressure fields, conductance values, grounded candidate sets, and
operation-value estimates fixed, then applied only the new scheduling cost and
safety admissibility. It covered all 40 treatment traces and 2,553 decisions.

The recorded scheduler changed 233 decisions from grounded utility order. The
counterfactual changes 151, removing 82 substitutions. Aggregate grounded
utility regret falls from 26,691.61 to 12,991.50, a 51.3% reduction. Safe
city-founding displacements fall from eight to zero, safe known-hut
displacements fall from 34 to zero, and expansion-to-exploration substitutions
fall from 29 to zero. The remaining 13 city-founding displacements and one hut
displacement all occur under an actionable safety deficit. All 407 such
decisions select a survival operation.

Reproduce the counterfactual with:

```bash
PYTHONPATH=src:benchmarks python3 \
  scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-pressure-category-invariance-pilot-v1/games/impact_pair/pressure_category_invariance_pilot_v1/treatment \
  --maximum-files 40 \
  --opportunity-counterfactual \
  --output artifacts/freeciv/pf-pressure-category-invariance-pilot-v1/opportunity-counterfactual-40.json
```

The counterfactual artifact SHA-256 is
`4d1f59e45e07ec606df6579306677fdd44e9d417f61b9e7009fc8e1d0ffbf36e`;
its source-set hash is
`d301314d9a1213f33546a93d9a72eadbb37fb535a5461901317e33c94b8395cc`.
This is scheduling evidence only. It cannot estimate downstream score or a
win rate, and it is not pooled with the completed pilot.

## Fresh empirical result

`pressure_opportunity_cost_pilot_v1` predeclares 40 fresh SHA-256-derived seed
pairs in the disjoint 2,900,000–2,999,999 range. It retains the turn-60
pressure-only arm isolation and alternating 20/20 execution order.

All 40 pairs subsequently completed with zero failures under clean commit
`a31a3a6`. Schema, source, safety, category-invariance, and exact-replay gates
passed. Score changed by +0.175 with interval [-0.175, 0.550], while
fixed-horizon lead rate changed by +5.0 percentage points with interval
[0.0, 12.5]. The positive directional result remains statistically
inconclusive and claim-ineligible. Full results are recorded in
[`pf-pressure-opportunity-cost-pilot-v1.md`](pf-pressure-opportunity-cost-pilot-v1.md).

The required follow-up audit subsequently found one candidate-scope defect:
failed settlement sites were pruned exactly and also penalized later distinct
sites through global category conductance. The isolated correction,
retrospective replay, and next fresh gate are recorded in
[`pf-direct-completion-offline-acceptance.md`](pf-direct-completion-offline-acceptance.md).
