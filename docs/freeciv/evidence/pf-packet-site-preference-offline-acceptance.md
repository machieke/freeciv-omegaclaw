# PF-PLN packet-grounded settlement-site preference

Status: implementation and offline contracts passed; selected engine
mechanism cohort frozen

## Goal

The foreign-claim gate removed accepted-but-ineffective founding requests but
did not add a city on selected seed `3674286`. The remaining trace spent
founder movement on a broad frontier search until the 15-turn settlement
runway expired. Adapter 1.7 tests whether an immediately reachable, valid site
can be selected from exact packet and ruleset evidence before that deadline.

## Grounded boundary

The proxy evaluates adjacent destinations only for unit types with the
ruleset's Found City capability. When the destination tile packet exists, it
uses the current founding preconditions:

- the tile is unclaimed or claimed by the acting player;
- terrain lacks the `NoCities` flag and is not ocean; and
- packet-visible city spacing satisfies `citymindist`.

The resulting `settlement_site_eligible` field is an exact boolean. A missing
destination tile packet emits no field, so unknown does not become false or
true. The DTO type-checks and preserves the field in the canonical legal
action and digest. Transport normalization consumes only the unit and
coordinates.

## Planner rule

When `expansion_packet_site_preference_enabled` is true and at least one legal
move for a founder has an explicit true site signal, adapter 1.7 ranks that
move at utility 990 and caps the other moves for that actor at 980. An
already-advertised founding action retains utility 1000. Failed-edge, cycle,
attrition, deadline, pressure, one-unit-action, exact legal membership, and
post-action effect checks remain active. Alternatives are retained rather
than pruned, so a failed preferred edge cannot manufacture a dead end.

With the setting false, or with no explicit true signal, the adapter applies
no site-preference utility. The new canonical evidence field is nevertheless
part of the legal action identity; both mechanism arms receive the same field,
so the frozen ablation isolates only the preference switch.

## Offline acceptance

- 150 focused proxy contract tests pass, with four environment-dependent
  skips. The new cases cover true unclaimed, false foreign-claimed, absent
  unknown, and normalized action propagation.
- Planner tests cover preference, the disabled ablation, absent-evidence
  compatibility, current-site founding precedence, and exact post-move
  telemetry.
- DTO tests cover raw proxy `params` propagation and fail-closed boolean
  typing.
- The tracked external patch applies cleanly from pinned upstream commit
  `26ba7124249f34fd3050ef29bf191bd4d8808018`, reverse-checks the mounted
  runtime, and has SHA-256
  `48e416000bf36c3c7ce13c8c59bb51bc682a1f17ee8568e432a82f673a10df55`.

## Selected engine gate

`packet_site_preference_mechanism_v1` reuses ten outcome-selected seeds from
the immutable expansion confirmation. Each prior treatment ended below the
four-city target with a live Settlers unit; seed `3674286` is excluded because
it already drove the foreign-claim mechanism replay. Both arms use target
four, the 15-turn runway, deadline recovery, pressure, learning, and score
alignment. The sole difference is the packet-site preference switch.

This is a claim-ineligible mechanism cohort. Acceptance requires:

- all 10 pairs and 20 arms complete with source, initial-state, safety, and
  schema gates passing;
- treatment records at least one packet-site preference attempt and exact
  successful traversal;
- paired settlement completions, cities gained, live founders, recovery,
  route failures, score, margin, and lead are reported regardless of
  direction;
- exact replay reproduces treatment decisions without integrity failure; and
- no result is pooled with or used to revise the frozen +2.66 score claim.
