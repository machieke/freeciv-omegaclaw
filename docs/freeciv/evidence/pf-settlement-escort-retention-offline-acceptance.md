# PF-PLN settlement escort retention

Status: adapter 1.8 mechanism rejected; adapter 1.9 mechanism passed but
selected ten-seed own-score target rejected

## Goal

Packet-site preference proved that founders could reach exact legal sites, but
seed `3746776` also exposed a retention failure. Treatment founded a fourth
city by turn 35 without a combat unit on that tile, lost it by turn 52, and
finished seven own-score points below its paired baseline. Adapter 1.8 tests a
bounded correction: delay that exact settlement until a grounded combat
escort is co-located, or recover the founder when the settlement runway
expires.

## Rule

`expansion_escort_retention_enabled` defaults false. When true:

- a legal Found City actor with no co-located combat unit is deferred;
- the founder holds its exact packet-legal site rather than resuming frontier
  search;
- a combat unit may become a `founder_escort_move` candidate only when its
  legal destination strictly reduces distance to an unescorted, directly
  foundable founder;
- a sole combat unit occupying an existing city remains protected by the
  existing defender-preservation rule;
- founding resumes only when at least one grounded combat unit occupies the
  founder tile; and
- deadline recovery, site failure learning, legal membership, pressure safety,
  one-actor scheduling, and exact post-action confirmation remain unchanged.

Telemetry independently records unique deferral snapshots, escort move
attempts and exact traversals, and escorted founding attempts and exact
completions.

## Offline acceptance

The unit contract covers the disabled compatibility path, unescorted
deferral, preservation of a sole city defender, a spare unit's strictly
distance-reducing escort move, exact move success, co-located founding, and
exact escorted-settlement completion. Configuration rejects non-boolean
values and predeclares a single isolated switch.

The claim-ineligible `settlement_escort_retention_mechanism_v1` cohort reuses
seed `3746776` from both the expansion confirmation and packet-site diagnostic.
Both arms retain target four, the 15-turn runway, packet-site preference,
deadline recovery, pressure, learning, and score alignment. Only the escort
retention switch differs. This outcome-selected one-pair replay can establish
mechanism behavior and diagnose city retention, but it cannot update any score
or win-rate claim.

Acceptance requires both arms to complete from one clean source, all safety
and initial-state gates to pass, all event streams to validate, and exact
decision replay to report zero integrity failures. Deferral, escort movement,
escorted settlement, city retention, recovery, own score, opponent score,
margin, and lead must be reported regardless of direction.

## Adapter 1.8 engine result

The first selected replay completed both arms from clean commit `99c48d1`
with every source, initial-state, safety, schema, and exact-replay gate
passing. The treatment activated 53 deferral snapshots and recorded eight
nominal escort moves, but completed no escorted settlement. It founded zero
cities and recovered 16 population, compared with three founding completions
and no recovery in baseline. Own score declined from `112` to `107`; margin
improved from `-36` to `-19` only because opponent score diverged downward.

Trace inspection rejected the mechanism. All eight nominal escort moves were
made by the Diplomat: escort routing ran before the explorer exclusion. The
sole real Alpine Troops defender correctly stayed in the capital, so no
genuine escort became available. Meanwhile, the unescorted legal site did not
interrupt founder production. Recovered founders were repeatedly replaced,
and every settlement was deferred. Machine-readable evidence is
[`pf-settlement-escort-retention-mechanism-v1.json`](pf-settlement-escort-retention-mechanism-v1.json).

## Adapter 1.9 correction

Adapter 1.9 admits an escort move only when the actor is in the grounded combat
set. An unescorted, directly foundable founder with no spare combat unit now
creates a production-defense deficit. If a population-costing founder is
already queued, the planner may discard its accumulated shields and switch to
a horizon-completing declared defender; this is the same bounded population
preservation exception used for redundant founder production. Exact
production installation is counted separately before that defender can move.

`settlement_escort_retention_mechanism_v2` freezes the same isolated switch and
selected seed on a fresh adapter-1.9 source. Adapter-1.8 arms cannot be reused
or pooled. In addition to the original acceptance fields, V2 must report exact
escort-defense production attempts/completions and verify that no Diplomat,
Spy, Caravan, or Explorer action is classified as an escort.

## Adapter 1.9 engine result

The source-fresh V2 pair completed from clean commit `c1a517e` with zero
infrastructure failures. Treatment installed two exact escort-defense
production switches, made six true combat escort moves with six exact
traversals, and completed both escorted settlements. The Diplomat continued
ordinary exploration and accounted for zero escort actions. Both treatment
settlements survived through turn 60.

Baseline founded three cities but retained two net additions, with final sizes
`2, 3, 5`. Treatment founded two escorted cities, retained both, and finished
at sizes `3, 4, 5`. Own score improved from `112` to `115` through two citizen
points and one residual point; technology was unchanged. Opponent score
diverged from `148` to `128`, so the `+23` margin change cannot be attributed
only to own play.

Both event streams and 2,478 events validate. Exact replay covered 53
treatment decisions with zero integrity failure and unchanged sources. All
source, initial-state, rejection, fallback, and latency gates pass.
Machine-readable evidence is
[`pf-settlement-escort-retention-mechanism-v2.json`](pf-settlement-escort-retention-mechanism-v2.json).
The one outcome-selected pair proves the corrected mechanism and rejects the
adapter-1.8 failure mode; it does not support a score or win-rate claim.

`settlement_escort_retention_generalization_v1` therefore freezes the same
isolated adapter-1.9 switch across all ten previously selected packet-site
seeds. It remains claim-ineligible and must report every retention, score,
opponent, margin, and lead outcome without pooling with either one-pair replay.

## Adapter 1.9 selected-seed generalization

The generalization cohort completed all 10 pairs and 20 arms from clean commit
`fd3784f`, with zero infrastructure, source-freeze, initial-state, rejection,
fallback, or latency-gate failures. All 20 streams and 28,677 events validate.
Exact replay covered all 10 treatment files and 792 decisions with zero
integrity failures and unchanged sources.

The corrected mechanism activated consistently: treatment averaged 1.3 exact
defender-production switches, 6.6 exact combat escort moves, and 1.4 escorted
settlements. However, it also averaged 46.1 deferral snapshots. Founding fell
from 2.3 to 1.4 cities and net additions fell from 2.0 to 1.4. Seed `3696266`
deferred 86 snapshots and completed no settlement.

Own score changed by `-1.0`, interval `[-4.2, +2.1]`, exact paired sign-flip
`p=0.6171875`. Five pairs declined, four improved, and one tied. The citizen
component fell by 1.9 points while technology was unchanged. Opponent score
fell by 12.1 and margin improved by 11.1, but this does not rescue the
predeclared own-score target and should not be attributed wholly to our policy.
The five discordant lead pairs split three baseline-only versus two
treatment-only, exact McNemar `p=1.0`.

Machine-readable evidence is
[`pf-settlement-escort-retention-generalization-v1.json`](pf-settlement-escort-retention-generalization-v1.json).
The cohort is outcome-selected and claim-ineligible. It proves that true
escorts and defender production generalize, but rejects unconditional
co-location as a score-bearing policy. The feature remains disabled by
default. The next correction must bound waiting cost and require an escort
only where grounded threat makes retention risk exceed the expansion delay.

## Adapter 1.10 founder-local threat gate

`expansion_escort_threat_gating_enabled` defaults false and has no effect
unless escort retention is also enabled. When both are true, an unescorted
legal site is deferred only if an exact packet-visible opponent is within the
existing `pressure_survival_threat_radius` of that founder. The predicate uses
authoritative unit and map geometry with wrapped distance. Missing enemy
coordinates do not invent a threat. An unthreatened site immediately remains
a normal founding candidate and records a separate safe-bypass
attempt/completion; threat-caused deferral snapshots are also counted
separately.

The one-pair, claim-ineligible
`settlement_escort_threat_gating_mechanism_v1` cohort reuses exposed seed
`3746776`. Both arms enable corrected combat-only escort retention; treatment
alone enables founder-local threat gating. This isolates the gating rule
against unconditional adapter 1.9 behavior. Acceptance requires a safe
settlement to bypass waiting, the historically contested approach to activate
the threat predicate, every activated escort to remain combat-grounded, and
all source, safety, schema, and exact-replay gates to pass. All own-score,
opponent, margin, settlement, retention, and recovery outcomes must be
reported regardless of direction. This selected mechanism replay cannot
update a score or win-rate claim.

## Adapter 1.10 engine result

The source-fresh selected pair completed from clean commit `3cd384d` with
zero infrastructure, source-freeze, initial-state, rejection, fallback, or
latency-gate failures. Both streams and 2,487 events validate. Exact replay
covered all 60 treatment decisions with zero integrity failure and unchanged
sources.

Instantaneous threat gating did not recognize the exposed retention risk.
Treatment bypassed all three settlements as safe, recorded zero threat
deferrals, produced no escort defense, and made no escort move. It reproduced
the unguarded trajectory: three founding completions but only two retained
additions, final sizes `2, 3, 5`, and score `112`. Unconditional escort
retention completed two guarded settlements, retained both at final sizes
`3, 4, 5`, and scored `115`.

Machine-readable evidence is
[`pf-settlement-escort-threat-gating-mechanism-v1.json`](pf-settlement-escort-threat-gating-mechanism-v1.json).
The negative result rejects a same-snapshot threat predicate. The rival
founder was observed during site approach but was no longer visible on the
exact founding snapshots; the city-local threat appeared only immediately
before capture. The next bounded correction must carry exact founder-local
threat evidence across that route, scoped to the founder's lifetime, rather
than broadening the radius or treating every site as dangerous.

## Adapter 1.11 route-lifetime contestation

`expansion_escort_route_threat_memory_enabled` defaults false and has effect
only with both escort retention and founder-local threat gating enabled.
While a founder exists, exact packet-visible opponents inside its configured
radius are retained as actor-scoped route evidence. Escort is required only
while the founder remains within that radius of an exact last-seen opponent
position. The evidence is cleared on verified settlement, verified population
recovery, or disappearance of that founder. It is not copied to another
founder and does not change the global survival threat predicate.

When a remembered contested founder reaches a legal site after its opponent
leaves visibility, it remains escort-required and records a separate
persisted-threat deferral. If no spare combat unit exists, a declared defender
may be selected from an empty production stock. A positive non-founder shield
stock remains protected; the existing population-founder repurpose exception
remains separately identified. If neither an escort nor production candidate
is ready, a legal founder move may be selected only when it strictly increases
distance from the remembered opponent geometry. Attempt and exact traversal
are reported independently.

The claim-ineligible
`settlement_escort_route_threat_memory_mechanism_v1` cohort reuses seed
`3746776`. Both arms enable escort retention and instantaneous threat gating;
treatment alone enables route memory. Acceptance requires a founder-local
observation during approach, a later persisted-threat deferral after current
visibility clears, then combat-only escort, exact threat-avoidance relocation,
or exact population recovery before the runway expires, and all source,
safety, schema, and exact-replay gates. Every score, opponent, margin,
settlement, retention, production, escort, avoidance, and recovery result must
be reported regardless of direction.

The source-fresh cohort passed its source, initial-state, execution-safety,
schema, and exact-replay gates, but the mechanism did not activate. Both
1,243-event streams validate, and exact replay covered all 60 treatment
decisions with zero integrity failure and unchanged sources. Treatment
recorded zero founder-route threat observations, zero deferrals, zero
defender-production switches, zero escort moves, and zero avoidance moves. It
therefore matched the instantaneous-gate baseline exactly: three safe
bypasses and three founding completions, two net cities gained, score `112`,
opponent score `148`, and margin `-36`.

Machine-readable evidence is
[`pf-settlement-escort-route-threat-memory-mechanism-v1.json`](pf-settlement-escort-route-threat-memory-mechanism-v1.json).
The result rejects the configured three-tile observation boundary as a way to
activate route memory on this trace; it does not reject actor-scoped memory
after an observation. The wrapped Chebyshev distance implementation is
correct, but no packet-visible opponent entered that founder-local radius
while the founder existed. Any follow-up must use a separate, explicitly
bounded founder warning radius and must leave the global survival-pressure
radius unchanged.

A deeper inspection showed that the recorded observation events omit enemy
coordinates, so widening the founder boundary cannot be justified from this
artifact alone. It also exposed a deterministic preparation opportunity:
after completing a founder on turn 22, Roma retained 57 shields in unit
production. The planner crossed to Granary production and retained only 32.
The later fourth city was captured after eight turns with its local Riflemen
at 21 of 30 shields. The next mechanism therefore targets exact production
and route timing rather than an ungrounded radius increase.

## Adapter 1.12 final-settlement escort preparation

`expansion_final_settlement_escort_enabled` defaults false and requires escort
retention to have any effect. When active and the combination of active and
queued founders covers every remaining city slot, the planner may repurpose a
redundant population-costing founder queue into a declared defender. Carried
shield stock is retained in the projection only when the authoritative
current production kind and advertised target kind are equal; cross-kind
switches keep the conservative zero-stock assumption. A defender queue
already projected to finish within the observed founder-route ETA prevents a
duplicate switch.

Once every remaining slot has an active founder, only the newest founder is
assigned the final slot. A spare combat unit may follow that actor through
strictly distance-reducing legal moves before Found City is advertised. Safe
earlier founders remain governed by instantaneous threat gating. Co-location
becomes mandatory only when the current city count is exactly one below
`expansion_city_target`. Existing sole-city-defender preservation, settlement
runway recovery, exact legal membership, effect confirmation, and failure
suppression are unchanged.

The claim-ineligible
`final_settlement_escort_preparation_mechanism_v1` cohort reuses seed
`3746776`. Both arms enable adapter-1.11 route memory; treatment alone enables
final-slot preparation. Acceptance requires exact early defender-production
installation, no duplicate preparation, final-founder-only route targeting,
an exact escorted final settlement or bounded runway recovery, and all
source-freeze, initial-state, rejection, fallback, latency, schema, and
exact-replay gates. Production stock assumptions, route moves, deferrals,
settlement retention, score, opponent score, and margin must be reported
regardless of direction.

The source-fresh V1 run passed every source-freeze, initial-state, safety,
schema, and exact-replay integrity gate, and activated the intended early
production path. Treatment retained the 57 same-kind unit shields, installed
one Riflemen target, completed it, and made 18 exact combat escort moves.
Own score improved from `112` to `120`, opponent score fell from `148` to
`131`, and margin improved from `-36` to `-11`. The own-score difference
comprised `+3` citizen, `+2` technology, and `+3` residual points.

The mechanism nevertheless failed its final-chain acceptance criterion.
Treatment founded two cities rather than three, recorded six final-slot
deferrals, and recorded neither a final escorted settlement attempt nor a
population recovery attempt. Trace inspection showed the reason: the final
founder and its pursuing escort both moved one tile per turn, so the escort
followed 18 times without closing the initial separation. The positive
`+8` result is one outcome-selected, claim-ineligible pair and is not a score
or win-rate claim.

Machine-readable evidence is
[`pf-final-settlement-escort-preparation-mechanism-v1.json`](pf-final-settlement-escort-preparation-mechanism-v1.json).
The next source-fresh correction must hold only the assigned final founder
until its prepared spare combat unit first co-locates, then permit the pair to
route together. It must leave earlier founders, threat avoidance, runway
recovery, and city-garrison preservation unchanged, and separately count
those rendezvous holds.

## Adapter 1.13 final-founder rendezvous

Adapter 1.13 retains the adapter-1.12 switch and preparation logic but
corrects same-speed pursuit. If the assigned final founder is unescorted and
a non-required grounded combat unit is available, ordinary expansion moves
for only that founder are suppressed until co-location. Exact population
recovery and remembered-threat avoidance are evaluated first. Earlier
founders remain unaffected. After rendezvous, the founder can advance and
the escort can use the next refreshed legal-action set to rejoin it.

`planner_founder_final_escort_rendezvous_hold_snapshots` counts unique
snapshot/founder holds independently from legal-site deferrals. The
claim-ineligible `final_settlement_escort_preparation_mechanism_v2` cohort
reuses seed `3746776` and isolates the same public switch on source-fresh
adapter-1.13. Acceptance requires at least one rendezvous hold followed by
exact co-location and either a confirmed final escorted settlement or bounded
population recovery. All V1 outcomes remain immutable and unpooled.

The source-fresh V2 run met that acceptance criterion and passed every
source, initial-state, safety, schema, and exact-replay integrity gate.
Treatment recorded 12 rendezvous holds, eight of eight exact combat approach
moves, and one of one confirmed final escorted settlements. All three founded
cities remained owned at turn 60, compared with two of three in baseline.
The final owned city sizes were `3, 3, 5, 5` in treatment and `2, 3, 5` in
baseline.

Two distinct production installations succeeded: the turn-22 capital
Riflemen preparation and a turn-27 defender target in the newly founded third
city after the first approaching combat unit became that city's sole
garrison. These were not repeated attempts against one unchanged queue. A
second automatically completed capital Riflemen then became the spare unit
that closed the final rendezvous.

Treatment scored `118` versus `112`, entirely through `+6` citizen score.
Opponent score was `147` versus `148`, so margin improved from `-36` to
`-29`. Neither arm led at the horizon. This one outcome-selected pair accepts
the mechanism but cannot support a score or win-rate claim.

Machine-readable evidence is
[`pf-final-settlement-escort-preparation-mechanism-v2.json`](pf-final-settlement-escort-preparation-mechanism-v2.json).
The next gate is a frozen selected-seed generalization of the unchanged
adapter-1.13 switch. It must report activation and non-activation separately
and retain all safety and replay gates; V1 and V2 selected-pair outcomes
remain unpooled.

The predeclared, claim-ineligible
`final_settlement_escort_preparation_generalization_v1` cohort freezes the
unchanged adapter-1.13 switch across all ten outcome-selected packet-site
seeds. It isolates only
`expansion_final_settlement_escort_enabled`; both arms retain route memory,
threat gating, packet-site preference, settlement-runway recovery, pressure,
learning, and score alignment. It must report activation and non-activation
separately, including production installations, rendezvous holds, exact
escort moves, final settlement or recovery, founded and retained cities,
score components, opponent score, margin, and lead. As reused-seed diagnostic
evidence, it cannot revise a score or win-rate claim regardless of direction.

The generalization completed all ten pairs without infrastructure failure and
passed every source, initial-state, safety, schema, and exact-replay integrity
gate. Treatment activated in all ten seeds through preparation, rendezvous,
or escort behavior. It averaged 1.6 successful production installations,
11.5 rendezvous holds, 9.6 successful escort moves, and 0.3 final escorted
settlements. Founding was unchanged at 2.2 per game; retained additions
improved from 2.0 to 2.2.

Own score changed by `+1.9`, with bootstrap interval `[-0.4, +4.2]` and exact
paired `p=0.19140625`. Citizen and residual components changed by `+1.0` and
`+0.9`; technology was unchanged. Opponent score changed by `-3.7`, margin by
`+5.6`, and lead rate was unchanged: one discordant pair favored each arm.
This is positive but inconclusive selected-seed evidence, not a new claim.

Two traces localize avoidable waiting. Seeds `3696266` and `3790239` recorded
10 and 17 rendezvous holds but zero escort moves. The latter lost one retained
city and four score relative to baseline. Adapter 1.13 currently holds when a
nominal non-garrison combat unit exists, even when the authoritative
legal-action set contains no distance-reducing escort traversal. The next
source-fresh correction must require an exact currently legal progress step
before creating a rendezvous hold; otherwise the founder must retain its
ordinary route candidate. It must preserve the accepted seed-`3746776`
rendezvous and separately count blocked no-progress holds.

Machine-readable evidence is
[`pf-final-settlement-escort-preparation-generalization-v1.json`](pf-final-settlement-escort-preparation-generalization-v1.json).

## Adapter 1.14 legal-progress rendezvous

Adapter 1.14 retains all preparation, final-founder assignment, recovery, and
threat-avoidance rules. Before suppressing an ordinary founder move, it now
requires the current authoritative action set to advertise at least one
non-garrison combat move whose target strictly reduces wrapped distance to
that founder and does not enter a visible enemy stack. A nominal spare unit
without such a move cannot cause a hold.

`planner_founder_final_escort_rendezvous_no_progress_snapshots` counts unique
snapshot/founder bypasses, separately from actual rendezvous holds. The
claim-ineligible `final_settlement_escort_legal_progress_mechanism_v1` cohort
freezes exposed seed `3790239` and accepted positive-control seed `3746776`.
The former must eliminate its 17 futile holds without losing ordinary founder
routing; the latter must preserve its confirmed final escorted settlement.

If that two-pair gate passes,
`final_settlement_escort_preparation_generalization_v2` repeats the unchanged
correction across the ten selected packet-site seeds. Both cohorts isolate
only `expansion_final_settlement_escort_enabled`, reuse historical seeds, and
cannot revise the score or win-rate claim.
