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

The escort extension adds a bounded visible-threat policy. Exact occupation is
a distance-zero threat even when map topology is unavailable. A nonzero threat
radius is used only when width, height, and both wrap flags are explicit. Each
threat produces an escort requirement. The requirement becomes actionable
only when a current persistent defender has an exact native route and unique
legal first step that can reach the founder within the bounded catch window.
Moving the sole persistent defender out of an owned city is excluded. If no
such escort exists, the site receives `settlement-site-blocked-by-threat`
instead of a fabricated escort action.

The closed visible-enemy collection has an explicit membership dependency.
Consequently, a current-uncontested support is invalidated when an enemy is
added, even though that enemy had no per-entity dependency in the prior
revision. The focused tests verify incremental/cold equivalence for this
transition.

Boundaries of this increment:

- `currently-uncontested` is not a forecast and does not claim future safety;
- threat reachability is a bounded current visible-distance policy, not an
  enemy path forecast;
- escort catchability covers the current founder rendezvous window; it is not
  a multi-turn escort operation;
- candidate ranking, population recovery, persistent settlement operations,
  and action selection remain outside this component;
- no FDAS authority flag is enabled.

Verification:

```text
pytest -q Autotests/test_freeciv_fdas_dependencies.py \
  Autotests/test_freeciv_fdas_settlement.py \
  Autotests/test_freeciv_fdas_corridor.py \
  Autotests/test_freeciv_fdas_phase0.py

26 passed
```
