# PF-PLN defense-relevance offline acceptance

Status: deterministic acceptance and 40-pair engine evaluation passed

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

The predeclared `pressure_defense_relevance_pilot_v1` then completed 40 fresh
SHA-256-derived seed pairs in the range 2,700,000–2,799,999. All engine,
schema, safety, source, and exact-replay gates passed. Substitutions into
`city_defense` fell from 81 to 4, accepting the correction operationally. The
score delta was +0.05 with interval [-0.300, 0.475], so no performance claim
or confirmatory cohort is warranted. Full results and the next
enumeration-invariance target are recorded in
[`pf-pressure-defense-relevance-pilot-v1.md`](pf-pressure-defense-relevance-pilot-v1.md).
