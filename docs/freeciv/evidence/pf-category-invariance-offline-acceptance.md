# PF-PLN category enumeration-invariance offline acceptance

Status: deterministic acceptance and 40-pair engine evaluation passed

The defense-relevance pilot removed routine fortification overactivation but
showed that expansion often lost to exploration because expansion exposed
more legal move alternatives. The grounded Impact adapter represented legal
operations as OR premises and scored pressure at each premise, so category
pressure was divided by action count before operations from different goals
were compared.

The corrected adapter preserves the generic PF-PLN OR graph and its complete
candidate provenance, but attaches each grounded legal operation to its
actionable category atom for cross-goal scoring. Every operation that resolves
one category therefore receives the same category pressure. Deterministically
ordered grounded action utility selects the operation within that category.

Deterministic acceptance proves:

- expansion beats exploration when each exposes one legal operation;
- adding eight dominated expansion alternatives does not change the winning
  category or the pressure assigned to any expansion operation;
- the highest-utility grounded expansion operation remains selected even when
  it is not supplied first;
- survival pressure and learned category conductance still change the winning
  category when authoritative state or feedback changes;
- generic PF-PLN OR pressure allocation is unchanged; and
- all pressure, impact, and harness regressions remain green.

Run the offline gate with:

```bash
PYTHONPATH=src:benchmarks python3 -m pytest -q \
  Autotests/test_freeciv_pressure.py \
  Autotests/test_freeciv_impact.py \
  Autotests/test_freeciv_harness.py
```

The predeclared `pressure_category_invariance_pilot_v1` then completed 40
fresh SHA-256-derived seed pairs in the range 2,800,000–2,899,999. All engine,
schema, safety, source, and exact-replay gates passed, and all 2,553 treatment
decisions preserved category-level priority invariance. The score delta was
-0.225 with interval [-0.800, 0.325], so no performance claim or confirmatory
cohort is warranted. Full results and the next cross-goal opportunity-cost
target are recorded in
[`pf-pressure-category-invariance-pilot-v1.md`](pf-pressure-category-invariance-pilot-v1.md).
