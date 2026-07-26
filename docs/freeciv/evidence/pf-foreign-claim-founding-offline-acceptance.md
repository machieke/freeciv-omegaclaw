# PF-PLN foreign-claim founding offline acceptance

Status: implementation and offline proxy contract passed; selected engine
mechanism replay frozen

## Confirmed headroom

The immutable `expansion_target_confirmatory_v1` treatment reached four
cities in 72 of 100 games. Of the 28 incomplete games, 10 retained 15 live
founders at turn 60. Several of those traces made repeated accepted
`unit_build_city` requests that produced no city.

Seed `3674286` is the clearest selected mechanism trace. Its treatment made
nine founding attempts, completed one settlement, ended with two cities and
two live founders, and recorded 23 founder-route failures plus 15 unreachable
moves. The seed was selected after outcome inspection and can never update a
population score or win-rate estimate.

## Ruleset and proxy cause

The active `civ2civ3` Found City enablers divide sites into unclaimed and
domestic-claimed tiles. A claimed site additionally requires the tile not to
be foreign. `PACKET_TILE_INFO.owner` carries that exact packet-known fact,
using player ID for claimed tiles and protocol sentinel `255` for unclaimed
tiles.

The proxy's founding advertisement already checked movement, ruleset
`NoCities` terrain, ocean class, and visible-city spacing, but did not compare
the current tile owner with the acting player. It could therefore advertise a
founding action inside packet-known foreign borders. The transport accepted
the request while the engine correctly produced no city, leaving the planner
to blacklist only one exact site and continue searching the same foreign
region.

## Correction

The pinned authoritative-state patch now carries `player_id` into
`can_city_be_founded_at`. It rejects a packet-known owner other than the
actor or unclaimed sentinel `255` before advertising `unit_build_city`.
Unknown ownership is not reclassified as foreign. This is a direct
ruleset/action-enabler check, not a learned regional ban.

The patched proxy contract covers foreign rejection, own-territory
compatibility, unclaimed compatibility, and the existing `NoCities` gate.
All 69 focused proxy tests pass in the mounted Freeciv runtime. The patch
applies cleanly to pinned upstream commit
`26ba7124249f34fd3050ef29bf191bd4d8808018`; its new SHA-256 is
`4b63fa9890e129beeff4ffa7d49bf92fa263ab82499eca66570e3330369112be`.
All 101 repository harness and state-bridge tests also pass.

## Selected engine gate

`foreign_claim_founding_mechanism_v1` freezes a one-pair replay of selected
seed `3674286`. It declares the reuse of
`expansion_target_confirmatory_v1`, requires a clean source, and remains
claim-ineligible. Both arms retain pressure, learning, score alignment, a
15-turn runway, and adapter-1.6 deadline recovery; the arm difference remains
the historical three-versus-four city target.

Acceptance requires:

- both arms complete without rejection, fallback, or infrastructure failure;
- paired initial-state fidelity and source freeze pass;
- every event stream validates and the treatment trace replays exactly;
- treatment founding attempts, completions, live founders, route failures,
  and final cities are compared with the immutable historical trace;
- the trace confirms whether foreign-claim pruning creates a different
  grounded route or settlement; and
- score, margin, and lead are reported regardless of direction without
  updating any statistical claim.
