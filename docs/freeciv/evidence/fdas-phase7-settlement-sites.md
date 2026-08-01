# FDAS Phase 7 settlement-site projection

Status: component-only, shadow-only, no policy authority.

This increment adds bounded `settlement-site` scopes for sites established by
current server-advertised legal actions. A site exists only when the current
legal-action packet contains either `unit_build_city` at the founder's current
tile or a typed `unit_move` action carrying the explicit
`settlement_site_eligible` witness. An ordinary move is not promoted into a
settlement claim.

The projection records the exact founder, site tile, legal action, and native
route corridor when one is available. A currently visible site is marked
`settlement-site-currently-uncontested` only from the closed current visible
enemy collection. Fog produces neither a safety claim nor an escort
requirement. A packet-visible enemy occupying the exact site instead produces
`settlement-site-contested-by` and `settlement-escort-required`.

The closed visible-enemy collection has an explicit membership dependency.
Consequently, a current-uncontested support is invalidated when an enemy is
added, even though that enemy had no per-entity dependency in the prior
revision. The focused tests verify incremental/cold equivalence for this
transition.

Boundaries of this increment:

- `currently-uncontested` is not a forecast and does not claim future safety;
- escort requirements cover exact site occupation only in this increment;
- reachable-threat envelopes and whether an escort can catch the founder are
  not yet projected;
- candidate ranking, population recovery, persistent settlement operations,
  and action selection remain outside this component;
- no FDAS authority flag is enabled.

Verification:

```text
pytest -q Autotests/test_freeciv_fdas_dependencies.py \
  Autotests/test_freeciv_fdas_settlement.py \
  Autotests/test_freeciv_fdas_corridor.py \
  Autotests/test_freeciv_fdas_phase0.py

24 passed
```
