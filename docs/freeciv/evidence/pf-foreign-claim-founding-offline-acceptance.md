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

## Selected engine result

The frozen replay completed both arms from clean commit `c624a96`, with no
active infrastructure failure, engine rejection, model fallback, initial-state
mismatch, source drift, schema failure, or replay-integrity failure. The
configuration hash is
`83e676f9aaf9bdd1bdca0a81b832f3a7b487fe8c85594453fd4a646606a067e1`
and the implementation hash is
`25eaf1e4a702817f90867ae5b6c96bf868c1bc882c4fae1c63f14d6e0f4175f9`.

The corrected treatment made one founding attempt and completed one
settlement. Its immutable pre-correction treatment trace made nine attempts,
completed one settlement, and retained two live founders. The correction
therefore removed eight accepted-but-ineffective founding requests and,
together with adapter 1.6 recovery, left no stranded founder. It did not add a
settlement or city: both current arms gained one city and ended with two.
Treatment recovered four population points through two verified joins.

The selected pair scored 116 under baseline and 118 under treatment, while the
opponent score increased enough for margin to change from +4 to +2. The
historical pre-correction treatment scored 115 with margin -1. These
single-selected-seed differences diagnose behavior only. They are neither
randomized evidence for the correction nor a score or win-rate estimate.

All two event streams and 3,344 events validate. Exact replay reproduced all
135 treatment decisions with zero integrity failure; 22 decisions (16.3%)
changed under replay instrumentation while the source set remained unchanged.
The aggregate SHA-256 is
`8d0c52f8b9ba99f40d2e8ccadfb423b56e54f1ff967c13dc0bf690f2527e2dd1`
and the replay artifact hash is
`27228a88c8fa5ca6bc9e87eb105f8eee8fc8fa917229b528c34c9c1ca92fcf2a`.

## Decision

Retain the packet-grounded foreign-owner gate as correctness and
action-efficiency hardening. Do not promote it as a score improvement and do
not spend a fresh population cohort on the same retry mechanism. The trace
shows the next bottleneck is choosing a reachable valid frontier before the
runway deadline, so the next optimization must use exact packet-known
settlement eligibility during founder movement rather than another regional
retry rule.
