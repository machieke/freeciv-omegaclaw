# PF-PLN category enumeration-invariance offline acceptance

Status: deterministic acceptance passed; engine evaluation pending

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

The predeclared `pressure_category_invariance_pilot_v1` uses 40 fresh
SHA-256-derived seed pairs in the range 2,800,000–2,899,999. It retains the
pressure-only two-key arm isolation, turn-60 horizon, and alternating 20/20
execution order. Its one-pair prefix must pass engine, schema, source, safety,
and exact-replay gates before the remaining pairs run.
