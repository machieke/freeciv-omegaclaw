# PF-PLN settlement escort retention

Status: adapter 1.8 mechanism rejected; adapter 1.9 selected mechanism passed;
selected ten-seed generalization replay frozen

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
