# PF-PLN threat-relevance offline acceptance

Status: deterministic acceptance passed; engine evaluation pending

The grounded goal-relief pilot showed that the largest pressure substitutions
sent expansion and exploration units into tactical movement. Survival truth
was fully unsatisfied whenever any opponent was visible, even when that
opponent was distant from every owned city.

The corrected survival predicate uses only authoritative coordinates and map
dimensions. A visible opponent activates survival pressure when its wrapped
Chebyshev distance to an owned city is at most the configured radius (3 by
default). If the player has no city, owned units become the conservative
fallback anchors. A grounded `city_defense` or `production_defense` candidate
still activates survival pressure independently of opponent proximity.
Missing coordinates fail safe and retain threat activation.

Deterministic acceptance proves:

- no visible opponent leaves survival satisfied;
- a visible opponent 20 tiles from an owned city leaves survival satisfied;
- a visible opponent at x=99 is one wrapped tile from a city at x=0 on a
  width-100 map and activates survival pressure;
- distant visibility cannot preempt score-bearing production;
- a proximate threat still selects the grounded tactical route;
- a grounded defense deficit remains urgent without a proximate opponent;
- the radius is explicitly bounded to 1..12; and
- all prior pressure, impact, and harness regressions remain green.

Run the offline gate with:

```bash
PYTHONPATH=src:benchmarks python3 -m pytest -q \
  Autotests/test_freeciv_pressure.py \
  Autotests/test_freeciv_impact.py \
  Autotests/test_freeciv_harness.py
```

This establishes goal-grounding behavior only. The predeclared
`pressure_threat_relevance_pilot_v1` uses 40 fresh SHA-256-derived seeds in
the range 2,600,000–2,699,999. Its one-pair prefix must pass engine and exact
replay gates before the remaining pairs run.
