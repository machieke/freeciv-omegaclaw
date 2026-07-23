# PF-PLN defense-relevance offline acceptance

Status: deterministic acceptance passed; engine evaluation pending

The threat-relevance pilot removed most pressure-induced tactical diversion
from distant visible opponents but found 81 substitutions into
`city_defense`. The survival truth adapter treated any legal fortification
opportunity as a defense deficit, even though that candidate is generated
only when a combat unit already occupies its city.

The corrected predicate distinguishes two authoritative facts:

- `production_defense` is generated from a grounded combat-unit/city count
  deficit and may activate survival without a visible enemy; and
- `city_defense` is a fortification opportunity, not missing coverage, and
  activates survival only when an opponent is within the configured wrapped
  threat radius.

Deterministic acceptance proves:

- safe and distant-threat fortification cannot preempt score-bearing economy
  production;
- a proximate threat still selects the legal fortification action;
- a grounded production defense deficit remains urgent without a visible
  opponent;
- the survival context explicitly identifies a grounded production defense
  deficit; and
- all pressure, impact, and harness regressions remain green.

Run the offline gate with:

```bash
PYTHONPATH=src:benchmarks python3 -m pytest -q \
  Autotests/test_freeciv_pressure.py \
  Autotests/test_freeciv_impact.py \
  Autotests/test_freeciv_harness.py
```

The predeclared `pressure_defense_relevance_pilot_v1` uses 40 fresh
SHA-256-derived seed pairs in the range 2,700,000–2,799,999. It retains the
same pressure-only two-key arm isolation, turn-60 horizon, and alternating
20/20 execution order as the preceding pilots. Its one-pair prefix must pass
engine, schema, source, safety, and exact-replay gates before the remaining
pairs run.
