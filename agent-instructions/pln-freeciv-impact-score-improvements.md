# FreeCiv impact-score improvement protocol

## Purpose

The completed 30-turn v4 cohort remains immutable historical evidence. Its
treatment-minus-baseline score estimate was `+0.13` with a bootstrap 95% CI of
`[+0.02, +0.27]` and an exact paired sign-flip `p=0.09375`. The result was too
sparse for a claim: 93 of 100 score pairs tied, and most treatment failovers
occurred too late to affect turn-30 production or scoring.

This hardening targets measurement fidelity and intervention timing before any
fresh confirmatory cohort is frozen. It does not reinterpret or extend v4.

## Implemented controls

1. Decision snapshots are accepted only after ruleset, research, economy, city
   buildability, legal release action, and movement data are ready. Two identical
   decision fingerprints are required, excluding packet source sequence.
2. Initial observer scores must be finite and populated for both the controlled
   player and an opponent. Missing score values no longer silently become zero.
3. Each arm records an initial-state fingerprint that combines stable decision
   inputs and both initial scores. Paired aggregation fails its safety gate when
   fingerprints are absent or differ.
4. Candidate enumeration is read-only. Exploration history is updated at stable
   turn boundaries, not from transient action-refresh packet cadence.
5. A production action counts as an effect only when the authoritative city
   target exactly matches the requested production kind and value. An unrelated
   state-hash change cannot create a false recovery.
6. Production changes require at least eight turns of scoring runway; founder
   production requires twelve. The thresholds are explicit policy settings, and
   the planner receives the cohort's actual fixed horizon.
7. Non-claim-eligible 60-turn pilot cohorts use disjoint, deterministically
   derived seed pairs. Their manifests use 60 turns for the engine, policy, and
   outcome declaration.
8. The first 60-turn pilot iteration exposed an accepted production order with
   no subsequent source-sequence update, two initial legal-action mismatches,
   and one over-budget turn. The hardened `pilot_horizon_60_v2` cohort therefore
   uses a bounded two-second action refresh, closes ambiguous unrefreshed scopes,
   requires five stable initial samples after a quiet period, and stops impact
   work before the whole-turn budget is exhausted.

## Evaluation sequence

Run a small engine-backed plumbing check first:

```bash
PYTHONPATH=src:benchmarks python scripts/freeciv/run_impact_evaluation.py \
  --backend engine-live \
  --cohort pilot_horizon_60_v2 \
  --limit-pairs 1 \
  --out artifacts/freeciv/impact-pilot-horizon60-v2-smoke
```

After the source is committed and clean, run the complete pilot without a pair
limit:

```bash
PYTHONPATH=src:benchmarks python scripts/freeciv/run_impact_evaluation.py \
  --backend engine-live \
  --cohort pilot_horizon_60_v2 \
  --out artifacts/freeciv/impact-pilot-horizon60-v2
```

The pilot must be used for mechanism and variance estimation only. Inspect
initial-state fidelity, score tie rate, treatment activation timing, exact
production effects, paired score variance, and safety gates. Then freeze a new,
disjoint confirmatory namespace and sample size before running any of its arms.

## Completed hardened pilot

The engine-backed `pilot_horizon_60_v2` run completed all 40 pairs on commit
`d43638439d069535d8dd0b4c429f7260d5921207`. One baseline engine attempt timed
out waiting for turn 12; resume mode archived that attempt and the exact arm then
completed successfully. The active cohort has 80 completed arms, zero active
failures, matching initial-state fingerprints for all pairs, zero rejected actions,
zero model fallbacks, and a 100% under-30-second full-loop rate.

The treatment-minus-baseline score estimate is `+0.20`, with bootstrap 95% CI
`[-0.05, +0.475]` and exact paired sign-flip `p=0.25`. The pilot is therefore not
a positive score claim. Thirty-five pairs tied, four favored treatment, and one
favored baseline. Treatment failover activated in 14/40 pairs, made 29 attempts,
and recorded 26 exact recoveries. Activated pairs averaged `+0.571` score while
non-activated pairs tied, which supports the intended mechanism but is a
post-treatment diagnostic subgroup rather than a claimable causal estimand.

The observed paired score SD is `0.8533`. A fresh score-only design is frozen as
`confirmatory_score_horizon_60_v1`: 200 turn-60 pairs, minimum detectable score
delta `0.20`, maximum planning SD `1.0`, 80% target power, and namespace
`pln-freeciv-impact-confirmatory-score-horizon60-v1`. The normal planning bound
requires 197 pairs. Its 200 seeds occupy `1400000..1699999`, disjoint from every
development, pilot, and prior confirmatory cohort. The previously exposed V4 score
cohort is retired from claim eligibility.

## Acceptance criteria for a future claim cohort

- Every predeclared pair completes under one clean committed implementation.
- Initial-state fingerprint mismatches and unavailable fingerprints are zero.
- Engine rejection and model safe-fallback rates are zero in both arms.
- The score endpoint uses the predeclared fixed horizon for every arm.
- The number of pairs is frozen from pilot variance for the declared minimum
  detectable effect; it is not adjusted after inspecting confirmatory outcomes.
- Score superiority requires both a bootstrap interval lower bound above zero
  and a two-sided exact paired sign-flip p-value at or below alpha.
- A meaningful score claim separately requires the same two gates above the
  predeclared meaningful margin. Its exact test is one-sided in the declared
  greater-than direction; a precise effect below the margin cannot pass because
  it is far from the margin in the wrong direction.
- Fixed-horizon score-lead rate remains hierarchically gated behind score
  superiority and is not described as an engine-reported terminal victory.

## Completed horizon-60 confirmation and next policy hardening

The engine-backed `confirmatory_score_horizon_60_v1` cohort completed all 200
pairs under the previously frozen implementation. Treatment minus baseline was
`+0.435` score, bootstrap 95% CI `[+0.24, +0.63]`, with exact two-sided paired
sign-flip `p=0.0000063`. This supports a positive fixed-horizon score claim for
that immutable implementation and cohort, but not the predeclared meaningful
`+2` point margin. There were 47 positive, 142 tied, and 11 negative pairs.

Post-confirmation diagnostics identified four improvement targets. Production
was the only failover family; authoritative production effects could arrive
after a generic refresh had already classified the action; production choice
ignored ruleset build cost and shield throughput; and lower city population was
the strongest observed downside mechanism. The following changes apply only to
future development and cohorts. They do not alter or re-aggregate the completed
confirmation:

1. Preserve `production_kind` and `production_value` from the server-advertised
   legal action through client normalization, input sanitization, name/ID
   cross-checking, and `PACKET_CITY_CHANGE` transport.
2. Wait for the submitted candidate's exact authoritative effect, rather than
   returning on the first unrelated packet update. Record confirmation latency
   and bounded confirmation timeouts.
3. Inject the compiled active-ruleset IR into the impact planner. Production
   projections now expose build cost, shield surplus, completion ETA, active
   horizon runway, population cost, and a conservative score-bearing value.
   Quantitative IR fields are decoded from their auditable `{value, source}`
   representation and both `building` and `unit` targets are supported.
4. Keep a current valid build when it completes in time and is at least as
   valuable as a proposed switch. Reject builds that cannot finish early enough
   to influence the declared horizon.
5. Protect expansion production: below the city target, if no founder exists,
   only a founder started before the configured cutoff, projected to settle by
   the horizon, and carrying positive score value is eligible. A failed founder
   request cannot fall through to economy or military production. Late
   population-costing founders are rejected; legal zero-population founders are
   preferred. Non-deficit military production is not churned for a fractional
   unit-score projection.
6. Emit separate citizen, technology, and residual score components, plus
   production ETA/value telemetry, so future paired reports identify which
   mechanism moved the score and whether the intervention completed in time.
7. Keep the primary zero-margin exact test two-sided. Test the meaningful
   positive margin with an exact one-sided greater-than sign-flip test and an
   explicit positive-direction guard.

For future paired development, transport and synchronization hardening applies
to both arms because it protects measurement fidelity. The policy contrast is
explicit: baseline freezes `production_strategy: static_priority`, matching the
pre-hardening priority list, while treatment uses
`production_strategy: horizon_score` plus bounded no-effect failover. Without
this arm-level distinction, better common transport would remove treatment
activation and the experiment would estimate only a shrinking failover effect.

The proxy patch identity for this hardening is
`26ba7124249f34fd3050ef29bf191bd4d8808018+patch-sha256:f2e4956d33d4ab896adf9eb4cd2ed52b89c70ee35849dbaaa85b3c4d021986c8`.
Any score estimate for this new policy requires a new disjoint development
cohort first; the completed 200-pair result remains the current claim and is not
evidence for the new policy.

## Engine-backed hardening smoke

The final one-pair development smoke is recorded at
`artifacts/freeciv/impact-score-policy-v5-smoke`. Both arms completed with no
active or historical infrastructure failures. Baseline (`static_priority`)
changed production three times (`Granary`, `Settlers`, `Granary`). Treatment
(`horizon_score`) made one change, to the legal zero-population `Engineers`
target. The exact production kind/value transport was confirmed, the treatment
ruleset-source rate was `1.0`, and its projection reported build cost `30`,
shield surplus `5`, ETA `6`, and population cost `0`. Confirmation-timeout,
citizen, technology, residual-score, and final-score deltas were all zero; both
arms scored `107` at turn 30.

This smoke verifies mechanics and demonstrates that the earlier one-citizen
regression is removed. A single tied pair is not an effect estimate and does not
support a new score or win-rate claim. The next statistical step is a disjoint
multi-pair development/pilot cohort at the intended 60-turn horizon, followed by
a newly frozen confirmation only if its mechanism diagnostics and variance
justify one.

## Completed horizon-policy v3 pilot

The disjoint engine-backed `pilot_horizon_60_v3` cohort completed all 40
predeclared pairs under clean commit
`cbd0a05bf6d1ca7da229f6a8b17cd0549bdf1870` and configuration hash
`75f3f7c2fe89009eafdded39ec68c8ee0dbd0eb077c313579f6b013c82fe57fc`.
Its namespace is
`pln-freeciv-impact-pilot-horizon60-v3`, with seeds derived only from
`1700000..1799999`. The order was balanced at 20 baseline-first and 20
treatment-first pairs. All paired initial-state fingerprints matched, both arms
had zero rejected actions and zero model fallbacks, and every full loop stayed
under 30 seconds. One treatment attempt timed out while waiting for authoritative
turn 3; resume mode retained that failure and the same manifest then completed
successfully. The final active cohort has 80 completed arms, zero active
infrastructure failures, and a stable source/implementation identity. The
historical failed attempt remains visible in the aggregate.

Treatment minus baseline score at turn 60 was `+0.175`, with bootstrap 95% CI
`[-0.65, +0.975]` and exact two-sided paired sign-flip `p=0.72484`. Eighteen
pairs favored treatment, nine tied, and thirteen favored baseline. The observed
paired score SD was `2.659`; at 40 pairs the detectable delta for 80% power was
approximately `1.178` points. The one-sided exact test above the predeclared
meaningful `+2` margin had `p=0.99998`. Fixed-horizon score-lead rate changed by
`-0.025` with interval `[-0.10, +0.05]`. This pilot is not claim eligible and
does not justify freezing a confirmation cohort for the new policy. A normal
planning approximation would require roughly 1,813 fresh pairs to detect the
observed `+0.175` mean at 80% power, so merely increasing the sample for the
unchanged policy is rejected.

The mechanism trace identifies a ruleset-capability error rather than a lack of
policy activation. Across all production changes, treatment selected
`Engineers` 39 times in 33/40 games, while baseline selected `Settlers` 43 times
in 36/40 games. Treatment then averaged 171.98 move actions and 1.28 city-build
attempts per game, versus 85.73 moves and 2.30 city-build attempts for baseline.
Across all treatment games, every
`unit_build_city` attempt was made by an existing `Settlers` unit; no produced
`Engineers` unit ever received that action. Consequently, treatment founded
`0.70` fewer cities per seed (95% CI `[-0.825, -0.55]`) while exploring 12.68
more positions and taking 4.0 fewer tactical actions. Its residual score
component moved `+0.25`, citizen score moved `-0.075`, and technology score did
not move. Twenty-eight pairs lost one treatment city. Those pairs averaged
`-0.143` score, whereas the 12 pairs with equal city counts averaged `+0.917`;
this subgroup contrast is diagnostic, not a causal claim.

The active `civ2civ3` ruleset explains the mismatch. Its `Found City` action
enabler requires the unit flag `Cities`. `Settlers` has that flag, but
`Engineers` and `Migrants` do not, even though all are workers with a
`Settlers` role. The planner's name-based `FOUNDER_TYPES` set incorrectly treats
those concepts as equivalent. The horizon projection therefore rewards a
zero-population Engineer as a founder, continuously produces it, and the movement
policy spends extra actions sending those workers toward settlement tiles they
cannot convert into cities.

Before another fresh cohort, founder eligibility must be compiled from the
ruleset action enabler and unit flags, or otherwise be demonstrated by the
server-advertised `unit_build_city` capability. Worker, city-founder, join-city,
and terrain-improvement roles must remain distinct. Production projections must
also model repeated output after completion and stop producing workers when no
score-bearing consumer exists. Acceptance requires a unit-capability test using
the real `civ2civ3` distinctions, a live smoke in which every selected expansion
unit can actually receive `unit_build_city`, and telemetry showing that extra
worker production does not inflate move/no-effect actions. Founder-produced,
settlement-attempted, settlement-completed, and founder-idle-turn telemetry must
distinguish production, routing, legality, and timing failures. Only then should
a new disjoint pilot be run. The immutable 200-pair `+0.435` confirmation
remains the current positive score claim for the prior implementation.

## Surplus-founder population recovery development result

The next development iteration closes a repeated-production score leak without
inventing a production action the server does not honor. Once the configured
three-city expansion target is complete, treatment may select a server-advertised
`unit_join_city` action for a co-located unit only when the compiled ruleset gives
that exact unit type both the `Cities` founder flag and a positive `pop_cost`.
The proxy now carries the exact target city ID through legal-action extraction,
normalization, sanitization, ownership/co-location validation, and packet
conversion; a missing target fails closed. Completion requires the founder to
disappear and the exact target city's size to rise by the ruleset population cost.

The engine-backed three-pair development run at
`artifacts/freeciv/impact-population-recovery-dev-3-20260720` completed all six
arms with zero engine rejection or infrastructure failure. Treatment-minus-
baseline score was `+2.0` with exploratory bootstrap interval `[0, 4]`; the
sample is intentionally too small and development-only, so this is not a revised
score claim. On regression seed `104759`, treatment completed five of five exact
population recoveries, recovered 10 cumulative population, increased final
citizens from 9 to 14 and score from 113 to 117, and reduced no-effect actions
from 23 to 14. The release audit, including the consolidated reversible upstream
patch, passed. A larger disjoint pilot is required before freezing any new
confirmatory cohort; the immutable 200-pair `+0.435` prior-policy claim remains
the current statistical claim.

## Authoritative revision and production-legality hardening

A follow-up trace showed that production retirement was being acknowledged by
the proxy without changing the engine city. Two independent proxy defects were
responsible for misleading the planner and its confirmation loop. State
responses were cached by player, format, and turn only, so a successful
same-turn action could reuse a pre-action snapshot for five seconds. Targeted
cache invalidation also treated valid player ID `0` as false. State cache keys
now include the monotonic server-packet sequence, every incoming authoritative
packet invalidates per-turn city/technology action caches, and player zero can
be evicted normally.

Fresh snapshots then exposed the underlying production rejection. The proxy
had normalized `PACKET_WEB_CITY_INFO_ADDITION` into
`city.buildability.unit_ids` and `improvement_ids`, but production action
generation consulted only absent legacy raw bitvectors and failed open to every
ruleset object. In the high-technology development game, obsolete Warriors ID
`4` was therefore advertised even though the server's current buildable list
excluded it; FreeCiv correctly ignored `PACKET_CITY_CHANGE`. Production
legality now gives the current normalized server buildability IDs precedence,
while retaining the legacy-bitvector path for older packet states.

The three-pair diagnostic run at
`artifacts/freeciv/impact-state-revision-dev-3-20260720` completed all six arms
without rejection or infrastructure failure. It made the false Warriors action
observable as a genuine no-effect and produced an exploratory treatment-minus-
baseline score delta of `+2.333` with bootstrap interval `[1, 4]`. This run
predates the final buildability filter and is diagnostic, not evidence for the
final policy.

The final engine-backed acceptance probe at
`artifacts/freeciv/impact-buildability-probe-104759-20260720` uses patch
identity
`26ba7124249f34fd3050ef29bf191bd4d8808018+patch-sha256:f2e4956d33d4ab896adf9eb4cd2ed52b89c70ee35849dbaaa85b3c4d021986c8`.
At turn 21, treatment selected server-buildable Musketeers (`kind=6`,
`value=9`) instead of unbuildable Warriors, and the next authoritative city
snapshot changed city 103 from `(6, 0)` to exactly `(6, 9)`. Baseline's
buildable Library change likewise applied as `(3, 17)`. Both arms completed
with no engine rejection or infrastructure failure. The single pair scored
`116` treatment versus `114` baseline and confirmed six population points
recovered, but it is a deliberately reordered development probe and cannot
revise the statistical score claim. The immutable 200-pair `+0.435` result
remains the current claim.

The probe also exposed the next optimization target: geometrically generated
unit moves and city-founding actions still produce many bounded confirmation
timeouts. Trace reconstruction showed that a timeout is not necessarily an
illegal action: early-turn founder moves and both city-founding orders became
visible at turn closure after exceeding the two-second wait. The planner now
uses a bounded deferred-confirmation ledger. Pending accepted actions retain
their closed actor/city scope, resolve on an exact later same-turn effect, and
otherwise resolve or expire on the first later-turn authoritative snapshot.
Recovered founder movement is fed back into route success, cardinal-corridor,
and observed route-ETA learning instead of being silently discarded. Telemetry
separates raw timeouts from deferred, recovered, expired, and pending outcomes.
A fresh engine-backed seed must confirm this mechanism before a multi-pair
policy cohort; stronger server-grounded tile/action legality remains the next
target for entries that genuinely expire unchanged.

The engine-backed development probe at
`artifacts/freeciv/impact-deferred-confirmation-probe-104729-20260720`
completed a fresh baseline/treatment pair on seed `104729` after reducing
post-action state polling from 10 Hz to 5 Hz. The first treatment attempt is
preserved as historical infrastructure evidence: 10 Hz polling exhausted the
proxy message quota and caused an `E429` on `end_turn`. The clean rerun had
zero infrastructure failures and zero rejected engine actions. Baseline
deferred 40 confirmations, recovered 28, expired 10, and ended with two
final-turn entries pending; treatment deferred 34, recovered 25, expired 9,
and ended with none pending. Candidate-specific effect rate was `70.73%`
baseline and `81.25%` treatment. Both arms learned three exact founder-route
successes and counted one settlement completion; the pre-ledger probe reported
zero route successes and zero settlement completions despite cities appearing.
Both arms scored `107`, so this single development pair validates accounting
and feedback correctness but provides no score-improvement claim.

The next fresh engine-backed pair at
`artifacts/freeciv/impact-failed-destination-probe-104729-20260720`
separated the remaining true failures by destination. Every treatment expiry
in the preceding trace was a Diplomat move whose actor remained stationary;
several destination tiles were retried from multiple adjacent sources. The
planner now preserves a single failure as transient, but prunes an exploration
destination for that unit type after stationary failures from two distinct
sources. Packet-visible enemy occupancy is excluded, and a later exact
traversal clears the evidence. Both fresh arms completed without rejection or
infrastructure failure and each pruned three repeated failed destinations.
Against the immediately preceding same-seed probe, baseline expirations fell
from 10 to 8 and candidate-specific effect rate rose from `70.73%` to `77.5%`;
treatment expirations fell from 9 to 7 and effect rate rose from `81.25%` to
`85.42%`. Both arms again scored `107`, founded one city, and learned three
founder-route successes. This validates the targeted efficiency/correctness
mechanism but does not change the score claim.

## Authoritative activity-enum hardening

The next correctness pass traced a live fortification effect that the proxy reported
as irrigation to the state boundary. The proxy carried an obsolete Freeciv activity
name table while its outgoing constants also encoded pollution cleanup and terrain
transformation with stale values. The tracked upstream patch now centralizes all 18
values from the pinned server's `unit_activity` network enum. Incoming packets and
outgoing commands use that single table, and unknown values remain explicit instead
of silently becoming idle.

The clean engine-backed pair at
`artifacts/freeciv/impact-activity-enum-probe-104729-v2-20260720` used patch identity
`26ba7124249f34fd3050ef29bf191bd4d8808018+patch-sha256:f8cde28288090c4f4479400864d5e6172c23b8500f33e0c792e3071fea0b98fb`.
Seven fortify orders across the two arms were accepted. Authoritative snapshots
observed one in-progress `fortifying` state and 128 completed `fortified` unit rows,
with none mislabeled as irrigation. Both 30-turn arms completed with zero rejected
actions, matching initial state, and every safety gate green. Baseline effect rate was
`83.72%` with seven expirations; treatment effect rate was `85.42%` with seven
expirations. Both arms scored `107`, so this validates planner feedback correctness
and action efficiency but does not revise the immutable 200-pair `+0.435` score claim.

## Target-grounded transport legality

Destination reconstruction of the activity-enum probe showed that six of seven
expirations in each arm targeted terrain ID `2`, ocean in the active ruleset. The
proxy's movement validator allowed these moves whenever the Diplomat unit type had
the static Embark action capability. That capability proves only that the unit may
be cargo; it does not prove an executable transport exists at the destination.

The proxy now retains `carrying` and `transported_by` from authoritative unit
packets and reads the exact ruleset `unit_class_id`. A non-native ocean move is
advertised only when an owned, packet-visible transport is on the exact target,
has spare `transport_capacity`, and its cargo bitvector includes the passenger's
unit class. Missing, foreign, full, or incompatible transports fail closed. Focused
tests cover all four cases without relying on unit names.

The clean engine-backed pair at
`artifacts/freeciv/impact-transport-legality-probe-104729-20260720` used patch
identity
`26ba7124249f34fd3050ef29bf191bd4d8808018+patch-sha256:3c7d199fbf2308037d3e66c0c2190e14667b55522365276342411ace23699005`.
Both arms completed 30 turns with matching initial state, zero rejected actions,
and every safety gate green. All six known ocean expirations per arm disappeared.
Baseline effect rate rose from `83.72%` to `90.00%` and expirations fell from seven
to four; treatment effect rate rose from `85.42%` to `93.75%` and expirations fell
from seven to two. The two arms explored 27 and 32 positions respectively, versus
26 and 31 in the preceding probe. Both scored `107`, so this validates legality and
action efficiency but does not revise the immutable 200-pair `+0.435` score claim.

## Target-stack effects and packet-visible occupancy

Combat effect attribution now follows both sides of an offensive action. The planner
captures the exact packet-visible enemy stack at the grounded target before transport;
an accepted attack is confirmed when either the actor changes or that target stack
changes. This correctly credits a defender removal when the attacking unit remains on
its source tile. An unchanged attacker and unchanged target stack still cannot count as
an effect.

The proxy and planner also exclude a plain move onto a packet-visible non-allied unit
or city. Alliance checks use exact player/diplomacy facts, and unknown occupancy is not
invented. Attack, city action, and transport-specific action paths remain separate from
plain movement. Focused regressions cover enemy-unit, enemy-city, allied, and empty-tile
cases at the proxy boundary, plus target-stack removal and unchanged-stack outcomes in
the planner.

The clean engine-backed development pair at
`artifacts/freeciv/impact-occupancy-effect-probe-104729-v2-20260720` completed with
matching initial state, zero rejection, zero fallback, and passing fidelity checks.
Baseline and treatment scored `107`; their candidate-specific effect rates were
`95.00%` and `93.75%`. The retained trace demonstrates correct combat attribution,
but the two remaining expirations per arm were ordinary Diplomat moves rather than
visible-occupancy conflicts, so this probe does not revise the score claim.

## Explicit packet-grounded hut entry

Freeciv hut entry is an explicit unit action, not always a successful plain move. The
proxy now reconstructs huts only when the exact destination tile's `extras` byte
bitvector selects a ruleset extra whose exact `causes` bitvector contains `EC_HUT`.
It resolves the actor's numeric unit type and chooses the first statically enabled hut
entry or frighten action in the pinned protocol range (`90`--`97`). Only then is a
grounded `unit_move` encoded as `PACKET_UNIT_DO_ACTION` (`pid=84`) against that exact
tile; absent any required packet fact, conversion falls back to ordinary movement.
Numbered action variants, inactive/non-hut extras, and the ordinary fallback all have
focused proxy regressions.

The first valid engine pair is retained at
`artifacts/freeciv/impact-hut-action-probe-104729-v2-20260720`, but is not interpretable
because its baseline arm had two cold-model fallbacks. The clean warm confirmation at
`artifacts/freeciv/impact-hut-action-probe-104729-v3-20260720` completed with matching
initial state, zero rejection, zero fallback, passing fidelity, and every release-audit
safety gate green. The known hut destination was sent through `pid=84` and succeeded.
Baseline scored `107` with a `95.12%` effect rate and one final pending action;
treatment scored `109` with a `97.92%` effect rate and no pending action. Each arm had
one expiry, down from two in the preceding same-seed probe. The remaining destination
was correctly encoded as an ordinary move because no packet-visible hut fact existed;
its obstruction remains a separate investigation.

The `+2` score delta is a one-pair development observation on an already exercised
seed. It is mechanism evidence only and does not revise the immutable disjoint
200-pair `+0.435` score claim or satisfy the predeclared paired inference gates.

## Exact hut routing and founder-horizon semantics

The authoritative proxy now exposes sorted tile IDs only when packet-retained tile
extras select a ruleset extra whose cause bitvector contains `EC_HUT`. The immutable
snapshot validates and hashes this field. Explorer-role units rank only advertised
one-step moves that strictly reduce wrapped map distance to a known hut, while the packet
converter independently repeats the exact extra-cause check before emitting a hut action.
No observer-only tile, terrain-name heuristic, or inferred hidden occupancy enters the
planner.

Founder horizon logic now gives `expansion_minimum_remaining_turns` one coherent meaning:
it is the minimum remaining horizon at which a new founder build may start. A new build
must also have positive projected value and an exact population/build/route ETA that
settles by the horizon. A founder already queued counts as capacity whenever its projected
settlement lands by the horizon; it is not incorrectly required to retain the start cutoff
again after settlement. Focused tests cover a population-delayed founder that settles in
time and the late-start rejection.

The clean engine pair at
`artifacts/freeciv/impact-known-hut-route-probe-104729-20260720` exercised packet-known hut
routing from turn 1 and reached its first two huts by turns 3 and 7. It passed initial-state
fidelity, all safety gates, and the complete release audit with no engine rejection or model
fallback. Its treatment-minus-baseline score delta was `-2`, entirely one technology, so it
is retained as counter-evidence that deterministic earlier hut collection changes a
stochastic reward trajectory but does not guarantee a better paired score. It does not
revise the immutable disjoint 200-pair `+0.435` claim.

## Repeated unit-production scoring

The pinned Freeciv server computes the unit-production score component as cumulative
`units_built / 10` (integer division), while the prior horizon policy projected only a
single completion and rejected every non-deficit military choice. The declared policy
now carries `unit_build_score_divisor: 10`. For zero-population, non-founder units, it
projects a conservative first completion and repeated completions at current shield
surplus and publishes fractional score progress. The units-built counter is
civilization-wide, so the policy compares the best exact legal batch across cities with
their current unit-production trajectory. It commits one member at a time only when the
batch guarantees at least ten additional zero-population, non-founder units; every member
must receive exact same-turn production confirmation before the next. A failure, deferred
effect, or turn change cancels the remainder, and a score-bearing non-unit current build
is not displaced. A redundant founder build may be repurposed earlier so it does not keep
consuming population after expansion capacity is complete. Zero shield surplus fails
closed, and the static-priority baseline is unchanged.

Focused tests cover a 14-unit/one-guaranteed-point projection, a sub-threshold redundant
founder retirement, preservation of the frozen baseline choice, zero-shield rejection,
and exclusion of population-bound founders from stationary-repeat telemetry. The clean
three-pair development cohort at
`artifacts/freeciv/impact-repeated-unit-production-dev-3-20260720` passed initial-state
fidelity and all safety gates with no failure, rejection, or fallback. Its paired score
deltas were `-2`, `0`, and `+1`; neither new production category activated at turn 30,
so those values are not an effect estimate for repeated-unit scoring. Seed `104759`
independently reconfirmed three population joins, six population recovered, and a
one-point citizen/score treatment gain.

The clean-source 60-turn probe at
`artifacts/freeciv/impact-repeated-unit-horizon60-activation-20260720` also left both new
categories dormant and recorded zero repeat-unit projections. It passed source freeze,
paired fidelity, all safety gates, and the full release audit. Treatment scored `112`
versus baseline `110` solely through four exact population joins and eight recovered
population. This falsified the single-city activation hypothesis; the `+2` is one pilot
pair and not a revised claim. Focused batch regressions now cover three cities contributing
four completions each, confirmation-ordered continuation, and cancellation when the first
member has no authoritative effect. A fresh engine probe must activate the batch before a
larger statistical cohort.

The batch implementation is memoized by snapshot, legal-action set, and founder-capability
set; a focused regression proves that repeated candidate enumeration does not recompute it.
A read-only reconstruction of exact buildable production actions then evaluated 1,718
authoritative snapshots from all 40 prior horizon-60 treatment games. It found zero
`production_repurpose` or `production_military_score` opportunities under the strict
incremental-ten-build and no-score-bearing-displacement rules. This is evidence that the
rule is a dormant correctness guard in the observed distribution, not the next score lever.
Do not enlarge a cohort for it without a newly observed activating state.

## Route surplus founders back for population recovery

The next distribution-supported lever is completion of the already validated population
recovery path. A read-only scan of the immutable 200-pair horizon-60 confirmation treatment
traces found 28 games (14%) that had reached the three-city target while at least one
`Settlers` unit remained away from every owned city. The old planner only joined a founder
that happened to be co-located with a city and otherwise made it inert.

Treatment must route such a unit only from exact compiled capability evidence: its unit type
must have both `Cities` and `AddToCity`, and its ruleset `pop_cost` must be positive. Every
selected action must be server-advertised and strictly reduce wrapped distance from the actor
to an owned city. This is routing evidence, not permission to infer a join. Once co-located,
the existing recovery rule must still require an exact advertised `unit_join_city` action and
must count a completion only when the actor disappears and that exact city's size rises by the
compiled population cost. The frozen static-priority baseline must never use the route.

Acceptance criteria:

- a focused planner regression chooses the uniquely distance-reducing advertised step and
  records its exact target city IDs and compiled population value;
- removing `AddToCity`, `Cities`, or positive `pop_cost` fails closed;
- a non-reducing move and the static-priority baseline remain ineligible;
- route attempts, exact-position successes, join attempts/completions, and recovered
  population are separately visible in events, aggregates, and the report;
- focused and full repository tests pass; and
- an engine-backed development cohort exercises the route or records its non-activation
  without changing the immutable score claim. Any observed development delta remains
  mechanism evidence until a fresh, disjoint, predeclared cohort passes the paired gates.

The first three-pair engine rerun recorded zero route attempts. It did reconfirm three
direct joins and six gross population recovered on seed `104759`; pair deltas were `-2`,
`0`, and `+6` (mean `+1.33`). One baseline model fallback failed the absolute safety gate,
while the complete 4,584-event release audit passed. This is a documented non-activation,
not a score update.

## Stop repeated population-costing founder production

The post-hoc horizon-60 seed-`1406156` replay falsified the assumption that a completed
join's compiled `pop_cost` is itself incremental impact. Treatment completed five joins
and reported ten gross population recovered, yet finished at 13 citizens and score 118;
baseline finished at 15 citizens and score 120. Exact snapshots showed that treatment
left its capital on repeated Settler production after expansion capacity was complete.
Each completion first deducted two population; joining the unit back restored gross
population but did not recover the disrupted natural-growth trajectory.

Treatment must retire a positive-population founder queue before another horizon-relevant
completion when capacity excluding that exact queue still meets the expansion target.
The calculation must not count the queue as evidence of its own redundancy. An emergency
mid-build switch is allowed only for this case; its replacement projection must assume
zero carried shield stock because switching may discard all accumulated shields. The
replacement must have exact compiled zero `pop_cost`, be a declared economy/defender
priority, and use a server-advertised action. A necessary founder queue, a founder that
cannot complete before scoring, ordinary mid-build production, and the frozen baseline
must remain untouched.

Acceptance criteria:

- a three-city state with a mid-build redundant Settler chooses
  `production_repurpose`, reports exact avoided population and discarded stock, and
  projects the replacement from zero shields;
- a queue that is itself required to reach the target is not called redundant;
- a queue unable to complete by the horizon does not justify shield loss;
- live events and paired reports expose repurpose count, avoided population cost,
  discarded shields, and replacement completion rate;
- all focused and full FreeCiv tests pass; and
- a same-seed horizon-60 engine rerun confirms that repeated Settler production stops
  without rejection/fallback before any larger cohort is considered.

The custom replay also exposed a harness consistency issue: configuration validation
accepts arbitrary declared cohort names while manifest generation previously used a
closed token table. Existing cohort IDs remain byte-for-byte stable; other valid names
now receive a deterministic hash-derived, identifier-safe token. This supports isolated
mechanism probes without making them claim eligible.

The clean confirmation at
`artifacts/freeciv/impact-population-recovery-stop-repeat-1406156-horizon60-v2-20260720`
met the acceptance criteria. Treatment emitted one `production_repurpose` on turn 17,
reported two population cost avoided and 24 shields conservatively discarded, completed
the Granary replacement, and emitted no join/rebuild cycle. Final treatment citizens/score
improved from 13/118 in the preceding replay to 14/119; the frozen baseline stayed at
15/120. Initial-state fidelity, zero rejection, zero fallback, clean source commit
`736c500`, and the full trace release audit all passed. This is a one-point causal
improvement on a reused post-hoc seed, not a score-claim update.

## Sequence growth before the final founder when runway is ample

After repeated production was stopped, seed `1406156` retained a one-citizen treatment
deficit. Exact initial state explains it: treatment queued the last required founder at
food/shield surplus 2/3, while baseline built Granary first. Treatment reached three cities
earlier but ended with capital size 4 instead of 5. This must not become an unconditional
Granary-first heuristic; exact combined runway remains the eligibility boundary.

For a deficit of exactly one founder, treatment may sequence Granary first only if the same
city advertises an exact founder production action and the conservative combined projection
fits all of these stages: Granary completion; founder build/population readiness from zero
carried shields and without credit for Granary food retention; founder route; and at least
`production_minimum_remaining_turns` remaining for the settlement to affect score. Existing
or necessary founder queues are not displaced, the static baseline is unchanged, and direct
founder production remains preferred when the combined runway is shorter.

Acceptance criteria:

- the slow-food 60-turn state projects Granary plus founder plus route at 42 turns and
  17 remaining settlement turns, selecting `production_preexpansion_growth`;
- a short-runway 30-turn fixture projects only six remaining settlement turns and continues
  to select `production_expansion` directly;
- the founder projection assumes zero post-Granary shield stock and does not invent a
  Granary food-retention effect;
- live metrics expose sequence selection, combined settlement ETA, and remaining runway;
- focused and full FreeCiv tests pass; and
- a clean same-seed horizon-60 confirmation exercises the sequence without rejection or
  fallback before the policy is considered for a larger development cohort.

The clean confirmation at
`artifacts/freeciv/impact-preexpansion-growth-1406156-horizon60-v3-20260720`
met these criteria. Treatment selected Granary on turn 1, the final founder on turn 25,
then retired the automatic repeat once capacity was complete. The live projection recorded
37 combined turns and 22 remaining settlement turns. Treatment and baseline both finished
with three size-5 cities, 15 citizens, and score 120. Across the three controlled replays,
treatment improved from 13/118 before repeat retirement to 14/119 after retirement and
15/120 after sequencing. There were no joins, rejected actions, or model fallbacks; source
commit `1f71c35`, paired initial state, and the full release audit passed. This is a
same-seed causal validation, not an independent effect estimate or claim update.

The clean boundary run at
`artifacts/freeciv/impact-preexpansion-fast-104759-horizon30-20260720` showed why live
evidence must remain part of the projection. After the starting founder's observed route,
the exact state projected 21 combined turns and eight settlement-runway turns, meeting the
configured boundary even though the earlier source snapshot fixture projected six. Treatment
therefore selected Granary-first, produced the required founder, retired its repeat, emitted
no join cycles, and still finished with 12 citizens and score 116—the same absolute treatment
outcome as the prior direct-founder run. Its clean baseline scored 115 for a `+1` paired
delta. Initial-state fidelity, zero rejection/fallback, clean commit `805a15b`, and the full
release audit passed. This confirms the boundary without changing the immutable claim.

## Founder route cycle escape

The clean two-pair targeted development run at
`artifacts/freeciv/impact-population-route-targeted-2-20260721` completed the current arms
with paired initial-state fidelity, zero active rejection/fallback, and score deltas `+3`
and `0`. The mean `+1.5` is mechanism evidence only. The first attempt's rejection of the
exact advertised name `Aqueduct, River` is retained as a historical failure; aligned bounded
punctuation validation and the final exact runtime name/kind/value check eliminated it in the
current attempt.

Neither seed activated surplus-population recovery because repeated-founder retirement had
already removed that cause. Seed `1491731` revealed the next bottleneck: the required founder
moved successfully but alternated between two tiles for turns 42--60 and never founded the
third city. The planner now records only confirmed actor-local founder positions and
suppresses a move to any recent route position only when another advertised, non-failed move
reaches a fresh position. It deliberately allows a revisiting edge when every grounded exit
revisits the bounded history. Acceptance covers synthetic two- and four-position cycles
choosing a fresh branch, only-exit traces retaining their backtrack/revisit, read-only
cycle-prune telemetry, and an engine-backed same-seed replay.

The clean confirmation at
`artifacts/freeciv/impact-founder-cycle-escape-1491731-20260721` met those criteria. On the
treatment route, the historical `(20,9)`/`(19,10)` loop ended on turn 42 with a move to
`(20,11)`; the founder traversed three further new positions and founded city three on turn
46. Treatment recorded eight distinct cycle prunes, two settlements, ten citizens, and score
115, improving its pre-fix trajectory of one settlement, seven citizens, and score 111. The
current baseline retained seven citizens and score 111, giving a `+4` paired delta. Both arms
had matching initial state, zero rejection/fallback, clean commit `3aff906`, and a passing
3,573-event release audit. This is a reused-seed mechanism confirmation, not a claim update.

The immutable 200-pair trace scan found founder two-tile cycles in 13 pairs and 23 arms
(10 baseline, 13 treatment). Twenty arms repeated at least six moves and 15 repeated at
least ten, so the defect was not seed-specific. A second clean confirmation at
`artifacts/freeciv/impact-founder-cycle-escape-1483352-20260721` targeted a historical
negative pair: its old scores were 111 baseline and 110 treatment, with treatment cycling
18 times. The current arms both founded three cities, ended with ten citizens and score 115,
and changed the paired delta from `-1` to `0`. Baseline/treatment reported ten/six distinct
cycle prunes, while treatment needed one founder build versus baseline's two. All safety and
initial-state gates plus the 2,641-event release audit passed. This is reused-seed directional
evidence, not a formal claim revision.

The third clean confirmation at
`artifacts/freeciv/impact-founder-cycle-escape-1463275-20260721` targeted a historical pair
whose treatment founder alternated between two tiles on turns 31--60. The old treatment
never completed city three and scored 114 versus baseline 116. The current treatment took
three non-repeating route steps, founded city three on turn 18, finished with 16 citizens,
and scored 119 versus the current baseline's 11 citizens and score 116. The paired delta
changed from `-2` to `+3`; current baseline/treatment recorded seven/four cycle prunes, two
settlements each, no route failures, and no rejected actions or fallbacks. Paired fidelity,
clean commit `01d1011`, stable implementation identity, and the complete 3,095-event release
audit passed. Across the three selected mechanism replays, historical-to-current paired
deltas changed `0` to `+4`, `-1` to `0`, and `-2` to `+3`. These seeds were selected using
old outcomes and cycle traces, so they validate the mechanism but cannot update the formal
effect estimate.

The next population-level checkpoint was predeclared as `pilot_horizon_60_v4`: 40 seeds
derived by `sha256-counter-v1` from namespace
`pln-freeciv-impact-pilot-horizon60-v4` in the disjoint `1800000..1899999` range. It is a
clean-source, pilot-only cohort and cannot update a claim. Its untouched five-pair prefix at
`artifacts/freeciv/impact-current-policy-pilot-v4-prefix5-20260721` produced score deltas
`+4, +1, 0, -1, 0`, mean `+0.8`, and paired-bootstrap interval `[-0.4, 2.4]`. All ten arms
completed from stable clean commit `fa510a4` with paired initial-state fidelity, zero
rejection/fallback, and a passing 14,704-event release audit. The interval is intentionally
not interpreted as reliable population evidence at `n=5`.

Fresh seed `1813833` revealed the next optimization target: treatment's second founder
repeated `(10,2) -> (11,2) -> (12,2) -> (11,3)` through turn 60, completed only one
settlement, and produced the sole negative delta. The immediate-backtrack guard is therefore
generalized to bounded recent-position revisits. A clean same-seed engine replay must show
the founder taking a fresh alternative without regressing dead-end behavior before running
more of the pilot prefix.

The clean same-seed confirmation at
`artifacts/freeciv/impact-founder-bounded-cycle-1813833-20260721` met that bar. Treatment
followed the old route through `(11,3)` on turn 26, took fresh exit `(12,4)` on turn 27,
reached `(13,5)`, and completed city three on turn 37. Its score rose from 114 in the pilot
prefix to 117 while the current baseline remained 115, changing the paired delta from `-1`
to `+2`. Treatment recorded two settlements, 15 route successes, seven cycle prunes, and
zero route failures. Both arms had matched initial state, zero rejection/fallback, clean
commit `130ee33`, stable implementation identity, and a passing 2,976-event release audit.
Because the seed was selected after inspecting the five-pair prefix, this is mechanism
confirmation only and cannot be folded back into that pilot estimate.

A bounded settlement re-entry retry was implemented at `5ecd095` and tested on the other
incomplete-expansion seed, `1874789`. The clean engine run at
`artifacts/freeciv/impact-settlement-reentry-1874789-20260721` activated one baseline and
four treatment retries, but did not add a settlement: completions remained three/two and
both arms still lacked city three at the horizon. Treatment scored 112 versus 113 in the
preceding replay. Safety, fidelity, source identity, and the 2,616-event release audit all
passed, making this a valid negative policy result. The implementation and metric were
removed by `5d21cfd`; do not restore them without new grounded evidence. Further work on
this trace must improve site selection or threat response rather than repeat ineffective
founding orders.

The early city loss has no grounded production quick win: the new city already auto-produced
the cheapest advertised defender, accumulated only six shields by turn 7, and was captured
on turn 8; moving the sole Alpine unit would leave the capital undefended. Freeze the next
evaluation slice before inspecting it as V4 indices 5--9, literal seeds
`1873237, 1884108, 1850973, 1850591, 1866769`. Report this post-fix pilot holdout separately
from the original prefix. It is an adaptive development checkpoint, cannot update a claim,
and must not be pooled with indices 0--4 as though one implementation generated all ten.

The fixed holdout at
`artifacts/freeciv/impact-current-policy-pilot-v4-holdout5-9-20260721` completed with deltas
`0, -2, 0, +3, +5`, mean `+1.2`, and paired-bootstrap interval `[-0.8, 3.6]`. All ten arms
used clean commit `0f8dd42`, matched initial state, had zero rejection/fallback, and passed
the complete 15,273-event release audit. This remains an underpowered adaptive pilot slice,
not a claim update.

The `-2` seed `1884108` exposed an incomplete pre-expansion sequence. Treatment's capital
founder queue stalled at size two with zero food surplus. City two selected Granary on turn
21, but the automatic target after Granary completion gained three shields before the next
planning boundary. The ordinary nonzero-stock guard therefore never installed the promised
founder; treatment ended with two cities and score 111 versus baseline's three cities and
score 113.

Persist an exact city/founder intent only after the Granary selection is confirmed. Permit
the followup founder switch only once Granary is no longer current, expansion remains
deficient, the founder still settles by the horizon, and discarded stock is no greater than
the city's current shield surplus. This bounds the exception to completion overflow or one
automatic production tick; a missed boundary cannot destroy a later trajectory. Expose
`production_preexpansion_founder_changes`, test exact target selection and the discard bound,
then require a clean seed-`1884108` activation before touching untouched seeds.

The clean activation replay at
`artifacts/freeciv/impact-preexpansion-followup-1884108-20260721` confirmed the production
mechanism but did not improve the outcome. City 109 selected Granary on turn 21, installed
the exact Settlers target on turn 30 with only one automatic shield tick discarded, and
subsequently completed founders 117 and 123. The dedicated growth/followup metrics each
recorded one activation. Both founders were destroyed on their outward route, however, so
treatment still completed one settlement and scored 111 versus baseline's two settlements
and score 113. Paired fidelity, zero rejection/fallback, clean source `96a6707`, and the full
2,740-event release audit passed. The persistent sequence is therefore retained as a
correctness hardening, but this selected-seed result is explicitly not evidence of score
improvement.

The next narrow route hardening learns founder attrition only from consecutive authoritative
observations: a founder must be present on a tile and later absent without a new city at that
tile or an increase in city count. A learned loss tile suppresses a future move only when the
same actor has another server-advertised route; the sole exit remains legal. Successful city
founding and post-target population recovery cannot create attrition evidence. Expose the
distinct `planner_founder_attrition_moves_pruned` metric and require both synthetic loss/site
tests and a clean seed-`1884108` engine replay before evaluating untouched pilot seeds.

The clean attrition replay at
`artifacts/freeciv/impact-founder-attrition-1884108-20260721` recorded one treatment prune
and changed the second replacement founder's route, while preserving a legal sole exit.
It did not change settlement count, citizens, or score: treatment again completed one
settlement with eight citizens and score 111 versus baseline's two settlements, ten citizens,
and score 113. Both arms were byte-count stable with the preceding replay, used clean commit
`b5b11d7`, had zero rejection/fallback, and passed the 2,740-event release audit. Retain the
bounded rule as route correctness hardening, but do not describe this selected-seed result as
a score gain.

The unchanged outcome exposes an earlier projection error. At turn 21 city 109 was already
size four, so the two-population Settler was immediately population-ready and direct production
was shield-bound: eight build turns plus route. Granary-first delayed that same founder until
turn 36 and exposed it to a later hostile corridor. Restrict `production_preexpansion_growth`
to the case it was designed for: the direct founder's authoritative population-readiness ETA
must be strictly greater than its shield-completion ETA. When the direct build is shield-bound,
select `production_expansion` immediately. Preserve the validated slow-growth case (population
ETA 25 versus shield ETA 10), expose both direct ETAs in the sequence projection, and require
a clean seed-`1884108` replay to recover the early-founder trajectory before proceeding.

The clean confirmation at
`artifacts/freeciv/impact-direct-founder-1884108-20260721` met the causal gate. Treatment
selected direct Settlers on turn 21, completed founder 115 on turn 28, followed the
baseline-proven route, and founded city three on turn 33. It finished with 13 citizens and
score 116 versus baseline's ten citizens and score 113. Relative to the inspected holdout
run, treatment improved from eight citizens/111 to 13/116 and the paired delta changed from
`-2` to `+3`. Both arms recorded two settlement completions, eight successful founder moves,
zero route failures/rejections/fallbacks, clean source `35a7bcc`, matched initial state, and
the complete 2,748-event release audit. This five-point selected-seed swing validates the
population-bound sequencing correction but cannot revise the formal claim.

Freeze the next untouched checkpoint as V4 indices 10--14, literal seeds
`1847487, 1825421, 1856447, 1859499, 1836213`, before inspecting any of their traces or
outcomes. Run them as one clean-source pilot slice under the current policy, report the five
paired deltas and interval separately, and do not pool them with V4 indices 0--9 because
different adaptive implementations generated those earlier slices. This remains development
evidence and cannot update the immutable confirmatory claim.

The frozen V4 indices 10--14 slice completed at
`artifacts/freeciv/impact-current-policy-pilot-v4-holdout10-14-20260721` with literal-seed
deltas `-2, +2, +5, +6, +3`. The mean was `+2.80` with paired-bootstrap interval
`[+0.20, +5.00]`; the exact two-sided paired sign-flip p-value was `0.1875`, and the
one-sided test above the declared two-point meaningful margin was `0.375`. All ten arms
completed with paired initial-state fidelity, zero rejection/fallback, required clean-source
stability at commit `8acaacb`, and a passing 14,255-event release audit. Four of five
treatment arms exercised the still-valid population-bound Granary sequence. The positive
interval is useful directional evidence, but `n=5`, adaptive slice history, and ineligible
cohort status mean it cannot revise the immutable formal claim or be pooled with V4 indices
0--9.

Seed `1847487` is the slice's sole negative pair and the only treatment arm with one rather
than two settlement completions. It may now be inspected as a post-hoc optimization target;
any same-seed replay is mechanism evidence only. Diagnose the missing settlement from exact
production, founder-route, and city-state events before changing policy. Do not weaken the
confirmed population-bound sequencing rule merely because one selected pair remained
negative.

Exact inspection of seed `1847487` found a route-evidence scope error. Founder 104's route
to city two proved edges traversable under the original one-city layout. After that city was
founded, treatment founder 116 received the same edge bonuses, followed the already-consumed
corridor, and attempted to found at `(6,8)`, exactly distance three from both existing cities.
The server advertised and accepted the order but no city appeared; the founder then moved
twice and was lost. Baseline's later founder instead went north and founded at `(6,2)`.

Keep exact traversability evidence, but scope its route-preference bonus to the authoritative
city layout under which it was observed. A city-layout change must remove the stale bonus;
within an unchanged layout, same- and cross-founder evidence remains available. Failed-edge,
cycle, sole-exit, legality, and execution-gate behavior are unchanged. Require a synthetic
changed-layout regression, the full suite, and a clean seed-`1847487` replay showing a fresh
outward route and a second settlement before considering another untouched slice.

The clean confirmation at
`artifacts/freeciv/impact-founder-layout-1847487-20260721` met that gate. Treatment founder
116 left the capital northward via `(7,4) -> (7,3) -> (6,2)` and founded city three on turn
27, instead of reusing the old southern corridor and making a no-effect attempt at `(6,8)`.
Treatment completed two settlements, ended with nine citizens and score 112, versus the
current baseline's two settlements, six citizens, and score 109. The current paired delta
was `+3`; the preceding untouched pair was `-2`, a five-point directional correction despite
baseline trajectory variation. Both arms had zero route failures/rejections/fallbacks,
required clean-source stability at `2e597d0`, paired initial-state fidelity, and a passing
2,996-event release audit. This selected-seed replay validates the route mechanism only.

Freeze the next untouched current-policy checkpoint as V4 indices 15--19, literal seeds
`1887134, 1818337, 1881562, 1825420, 1844064`. Execute all five pairs from one clean source
without mid-slice inspection-driven changes, report their deltas and interval separately,
and do not pool them with indices 0--14 or the immutable claim cohort.

The frozen V4 indices 15--19 slice completed at
`artifacts/freeciv/impact-current-policy-pilot-v4-holdout15-19-20260721` with deltas
`0, +1, 0, 0, 0`, mean `+0.20`, and paired-bootstrap interval `[0.00, 0.60]`. All ten arms
completed with paired initial-state fidelity, zero rejection/fallback, required clean-source
stability at `2e5f2b8`, and a passing 15,038-event release audit. The exact sign-flip and
meaningful-margin tests both had p-value `1.0`; this small adaptive slice is compatible with
non-regression, not a materially improved score claim, and remains separate from every prior
slice.

Seed `1881562` is the only asymmetric expansion case: baseline completed two settlements,
treatment one, while both scored 114. It may now be inspected post hoc for route correctness.
Seeds `1825420` and `1844064` had one settlement in both arms and are not treatment-specific
defects. Require exact evidence before changing policy, and treat any same-seed replay only as
mechanism confirmation.

Exact inspection found repeated cross-founder site reuse. Treatment founder 114 made an
accepted-but-no-effect attempt at `(4,10)` on turn 20. Replacement founder 119 returned to
that exact site and repeated the ineffective order on turn 35 before trying two other sites;
treatment recorded five attempts but only the initial settlement completed. This is distinct
from the rejected re-entry retry: the correction suppresses, rather than adds, an order.

Record a failed settlement site only after candidate-specific authoritative confirmation
shows no new city. Key it by founder type, wrapped map dimensions, exact position, and city
layout so another founder cannot repeat the same ineffective order while strategic state is
unchanged. A city-layout change makes the site eligible again, successful founding creates no
failure evidence, and movement/sole-exit legality is unaffected. Expose
`planner_failed_settlement_sites_pruned`, require a synthetic cross-founder/layout regression,
the full suite, and a clean seed-`1881562` replay. Do not reintroduce the previously rejected
settlement retry.

The clean confirmation at
`artifacts/freeciv/impact-failed-settlement-site-1881562-20260721` activated two treatment
prunes: the immediate same-actor retry after turn 20 and founder 119's cross-actor retry at
`(4,10)` on turn 35. Treatment settlement attempts fell from five in the untouched slice to
four, while settlement completion remained one and both current arms scored 114. The later
distinct attempts at `(6,10)` and `(7,11)` still had no effect, so exact failed-site memory
improved action efficiency but did not solve this map's broader site-selection problem.
Paired fidelity, required clean-source stability at `5a7be48`, zero rejection/fallback, and
the complete 2,715-event release audit passed. Retain the bounded anti-retry rule as
correctness hardening; it is not score evidence. Do not infer an unsafe regional blacklist
from adjacent failures without a server-grounded terrain/site-validity signal.

The clean current-policy replay at
`artifacts/freeciv/impact-failed-site-route-1825420-20260721` tested exact-site memory on the
other incomplete-expansion trace. Both arms again completed one settlement and scored 111;
each made eight distinct post-expansion attempts, while exact failed-site memory activated
only once. The founder remained in `(8..10, 10..13)`, and the snapshot exposed no typed map
tiles. The release audit passed across all 3,786 events, so this is a valid negative result:
do not generalize exact failure into a regional blacklist.

The transport boundary supplies a stronger causal correction. The pinned proxy's founding
legality checks terrain class and city spacing, but omits the engine/ruleset requirement that
`TerrainFlag NoCities` be absent. Add an exact `PACKET_TILE_INFO.terrain` to
`PACKET_RULESET_TERRAIN.flags` bitvector check in `can_city_be_founded_at`, using pinned
terrain flag ID `1`; when present, do not advertise `unit_build_city`. Preserve fail-open
behavior only when the packet terrain definition is genuinely unavailable. Require proxy
contract tests for flagged land and ordinary land, patch-digest/release-audit stability, the
full repository suite, and a clean seed-`1825420` engine replay. This is a legality fix first;
only a changed settlement or score outcome can count as selected-seed mechanism evidence.

The clean confirmation at `artifacts/freeciv/impact-nocities-1825420-20260721` exercised the
new proxy boundary. Each arm omitted founding at two packet-known `NoCities` sites and reduced
total attempts from nine to seven. Six other distinct attempts remained ineffective; each arm
completed one settlement, retained five citizens, and scored 110. Both games used clean source
`d0562f2`, matched initial state, had zero rejection/fallback, and passed the complete
3,692-event release audit. The exact terrain rule is retained as legal-action correctness
hardening, not score evidence. It also bounds the diagnosis: the remaining failures must not
be labeled `NoCities` without a new authoritative signal.

Freeze the next untouched current-policy checkpoint as V4 indices 20--24, literal seeds
`1838062, 1889362, 1842823, 1832144, 1824032`. Execute the five pairs from one clean source
with the updated proxy identity, report their deltas and interval separately, and do not pool
them with indices 0--19 or the immutable confirmatory claim. This remains adaptive
development evidence and cannot revise the formal score or win-rate claim.

The first execution at
`artifacts/freeciv/impact-current-policy-pilot-v4-holdout20-24-20260721` completed all ten
games with deltas `+1, +3, +4, 0, +2`, mean `+2.00`, paired-bootstrap interval
`[+0.80, +3.20]`, exact two-sided p-value `0.125`, and meaningful-margin p-value `0.625`.
Initial states matched, source stayed clean at `95f2fbb`, engine rejection remained zero,
and the 14,293-event trace audit passed. The aggregate is nevertheless safety-invalid: the
first baseline arm used bounded model fallback on turns 1 and 2, for a `3.33%` game-level
fallback rate and `0.67%` baseline-arm mean. Do not interpret or pool this favorable slice as
a clean policy checkpoint.

The failure exposed an operational mismatch: the pre-arm readiness probe generated only one
token through `/api/generate`, while timed proposals use `/api/chat` plus JSON decoding. Replace
that probe with a complete native chat asking for exact `{"ready":true}`, validate the decoded
object, and keep the existing 90-second readiness budget and 30-minute residency. The live
configured-model preflight must pass, the full repository suite must remain green, and then the
same fixed five-seed slice may be rerun only as an operational confirmation. Its exposed seeds
mean the rerun is not fresh evidence and still cannot revise the formal claim.

The operational rerun at
`artifacts/freeciv/impact-current-policy-pilot-v4-holdout20-24-chatready-rerun-20260721`
met every safety gate. Literal-seed deltas were `+2, +3, +4, 0, +2`, mean `+2.20`, with
paired-bootstrap interval `[+1.00, +3.20]`, exact two-sided p-value `0.125`, and
meaningful-margin p-value `0.5`. All ten games had zero model fallback and engine rejection,
matched initial states, clean stable source `06cbe5e`, and a passing 14,310-event release
audit. Compared with the invalid first execution, the two turn-1/2 baseline fallbacks became
zero and the affected seed's delta changed from `+1` to `+2`. This confirms the operational
hardening and positive direction, but the exposed rerun and `n=5` remain ineligible for a
formal score or win-rate claim.

## Current-policy confirmation cohort (frozen before execution)

The next claim-eligible evaluation is
`confirmatory_score_horizon_60_v2`. It contains 450 deterministic turn-60 seed pairs
derived with `sha256-counter-v1` from namespace
`pln-freeciv-impact-confirmatory-score-horizon60-v2-current-policy` in the disjoint
range `1900000..1999999`. It is score-only, requires a clean and stable source tree,
and permits neither a pair limit nor adaptive stopping.

The completed V1 cohort observed paired SD `1.4056`; the most recent clean five-pair
operational rerun observed similarly scaled variation around a substantially larger
mean. V2 conservatively declares maximum planning SD `1.5` and a 0.20-point minimum
detectable difference. At two-sided alpha 0.05 and 80% power this requires 442 pairs,
so the frozen 450-pair design is adequately powered with eight pairs of margin. The
same resolution is sufficient to test whether an effect near the operational
`+2.20` estimate clears the already declared two-point meaningful threshold.

Acceptance criteria:

- all 450 predeclared pairs and both arms complete from one clean, unchanged commit;
- paired initial-state fidelity passes for every seed;
- rejected-action and model-fallback rates are exactly zero in both arms;
- all full-loop turns remain within the declared bound;
- the release audit passes over every event, manifest, and aggregate;
- score improvement is claimed only when both its interval lower bound is above zero
  and its exact two-sided paired sign-flip p-value is at most 0.05;
- meaningful improvement is claimed only when the interval lower bound is above two
  and the predeclared one-sided margin test passes;
- any infrastructure failure is retried only as a fresh attempt, never converted into
  an observation, and any source/configuration drift invalidates the cohort.

### V2 retirement: unitless city-owned state

V2 completed 899 of 900 arms from clean source `d078114`. Treatment seed `1905459`
failed three fresh attempts at the same transition: its sole unit was destroyed by an
accepted turn-24 attack, `PACKET_BEGIN_TURN` and a packet-backed turn-25 state arrived,
and the player still owned two cities. The harness nevertheless required raw `units`
to be nonempty before parsing the state and separately treated an empty typed unit
collection as elimination. Proxy logs prove this was not a missing turn or unhealthy
server. The cohort is retired because repairing either assumption changes source
identity; its 899 arms must never be pooled with a corrected run.

Accept city-owned states with zero units, and define elimination as owning neither
cities nor units. Validate that contract synthetically and with the non-claim-eligible
turn-30 `diagnostic_unitless_city_v1` replay before freezing a fresh, disjoint V3
confirmation cohort.

The engine-backed diagnostic at
`artifacts/freeciv/impact-unitless-city-1905459-20260722` met this gate from clean
commit `eb20498`: treatment crossed the former boundary with two cities and zero
units at turns 25 and 30, both arms completed, rejection and fallback were zero,
paired initial state matched, source remained stable, and the complete 1,457-event
release audit passed.

Freeze the replacement as `confirmatory_score_horizon_60_v3`: 450 deterministic
turn-60 pairs from namespace
`pln-freeciv-impact-confirmatory-score-horizon60-v3-unitless-state` in the disjoint
range `2000000..2099999`. Preserve V2's 0.20-point detectable difference and 1.5
maximum planning SD. Do not inspect or reuse V2 outcomes in the V3 design or
inference. V3 must meet every source, completeness, safety, interval, and exact-test
acceptance criterion declared for V2.

### V3 operational-latency retirement and timed diagnosis

V3 was stopped after 38 of 900 arms, before any score, win, or paired outcome values were
inspected. Its immutable retirement reason is
`operational_latency_retirement_before_outcome_inspection`; its seeds and partial artifacts must
not be reused or pooled with a replacement cohort. The decision used controller timing only.

Eight completed turn-60 arms averaged 136.7 seconds per arm. Instrumented trace and lifecycle
timing attributed that mean as follows:

- 68.9 seconds (50.4%) to fixed two-second confirmation windows whose action effect was not yet
  visible;
- 21.1 seconds (15.4%) to confirmation polls that did observe an authoritative refresh;
- 20.0 seconds (14.6%) to next-turn synchronization;
- 7.4 seconds (5.4%) to startup, hard reset, and readiness;
- 6.4 seconds (4.7%) to a second hard reset after the arm;
- 2.4 seconds (1.8%) to action acknowledgements; and
- 10.5 seconds (7.7%) to planning, event persistence, aggregation, and other work.

Two tempting confirmation changes were rejected empirically. Action-specific 0.75-second
deadlines produced an engine rejection, and 100 ms stable-state polling with the original
two-second deadline also produced an engine rejection. The fixed two-second deadline and 200 ms
poll interval therefore remain correctness boundaries. The safe lifecycle optimization removes
only the post-arm reset: proxy termination still occurs after every arm and the next arm always
performs the authoritative pre-arm hard reset. A six-arm serial diagnostic completed without
failure in 493.87 seconds.

### Pair-preserving parallel controller

Independent seed pairs may run concurrently, but both arms of any pair remain serial and share
one dedicated worker/port. Pair order remains the predeclared baseline/treatment alternation, so
the 450-pair design has exactly balanced first-arm exposure. Claim-eligible cohorts must use their
predeclared `controller_workers`; concurrency is included in behavioral manifest identity because
local scheduling can affect when authoritative packet updates become visible.

The first three-worker diagnostic exposed two genuine proxy isolation limits before producing a
usable result. The state cache key omitted game ID, allowing equal player/turn/packet counters in
parallel games to collide, and the configured value named `requests_per_second: 100` was actually
enforced as 100 requests per 60 seconds. The pinned proxy now scopes state cache keys by game and
declares a tested 600-message/60-second sustained budget plus a 1,200-message burst budget per
agent. The corresponding proxy contract suite passes.

The hardened run at
`artifacts/freeciv/impact-timing-parity-v1-parallel3-cache-and-rate-scoped-20260722`
completed all three pairs and six arms with zero infrastructure failures, zero engine rejection,
zero model fallback, matched initial state within every pair, and every full-loop turn below 30
seconds. Wall time was 239.08 seconds versus 493.87 seconds serially: a measured 2.07x speedup and
51.6% reduction. Five of six normalized action trajectories and outcomes matched the serial run
exactly. One baseline arm received a fortify-state packet update during its confirmation window,
whereas two independent serial executions timed out on the preceding snapshot; that legal timing
difference changed its later route and score. The repeat serial pair completed in 99.32 seconds
and exactly reproduced the original serial trajectory. This evidence establishes safe isolation
and also proves that serial and concurrent artifacts must not be mixed as one execution protocol.

Freeze the replacement as `confirmatory_score_horizon_60_v4`: 450 fresh deterministic turn-60
pairs from namespace `pln-freeciv-impact-confirmatory-score-horizon60-v4-pair-parallel` in the
disjoint range `2100000..2199999`, with exactly three controller workers. Preserve the V3 score
design, all source/completeness/safety/statistical gates, and the no-adaptive-stopping rule. The
three-worker mode, pinned proxy identity, model configuration, and alternating pair order must
remain unchanged for the complete cohort. Based on observed turn-60 cost and removal of the
duplicate reset, the planning estimate is approximately 11 hours, subject to engine trajectory
variance.

### V4 retirement: packet-backed player elimination

V4 executed all 900 arm slots but completed 897 arms and 448 complete pairs. Three
active arms failed three deterministic attempts each after FreeCiv emitted “The Romans
are no more!”: baseline and treatment seed `2119913` stopped at turns 54 and 52, and
baseline seed `2146151` stopped at turn 49. Each retry reproduced the exact normalized
action sequence. The player-facing cache retained stale cities, so the asset-based
`not cities and not units` fallback missed elimination and waited for a next turn that
an eliminated player never receives.

Retire V4 at source `b59205c57a481bda657d7a71af9657fd014f87fb`. Its 897
old-code completions must not be combined with corrected arms. Carry the exact
`PACKET_PLAYER_INFO.is_alive` field through the authoritative proxy contract and typed
snapshot, suppress terminal actions and stale own assets, accept a terminal snapshot
without requiring turn advance, and preserve the valid city-owned/unitless state.
Predeclare early elimination as an absorbing authoritative terminal score carried to
the fixed horizon, with the observation turn and terminal reason retained. Validate
the exposed seeds only in non-claim cohort `diagnostic_terminal_elimination_v1` before
freezing any fresh confirmation cohort.

### Terminal-elimination correction confirmation

The correction was implemented and frozen at source
`224fb704e7aa731433a83bdf84553a3f82974196`. The packet-backed
`PACKET_PLAYER_INFO.is_alive` value now reaches the authoritative proxy response,
typed DTO, immutable snapshot, and live harness. A false value suppresses stale own
assets and legal actions, permits an exact terminal snapshot at the current turn,
blocks a post-elimination action, and records the predeclared absorbing terminal
score. Asset emptiness is no longer treated as proof of elimination, preserving the
valid city-owned/unitless state.

The engine-backed diagnostic at
`artifacts/freeciv/impact-terminal-elimination-v1-engine` completed all four arms and
both pairs. The three former timeout arms ended from the authoritative packet:

- baseline seed `2119913`: terminal at turn 54;
- treatment seed `2119913`: terminal at turn 52;
- baseline seed `2146151`: terminal at turn 49.

Treatment seed `2146151`, the paired control, reached the fixed turn-60 horizon.
Every arm completed without an active infrastructure failure, engine rejection, or
model fallback; paired initial-state fidelity, source freeze, and all safety gates
passed. All four event streams passed schema validation, and the release audit
passed with cognitive-trace enforcement. Aggregate SHA-256 is
`153d89970ef495175735486225ff09c174336b8a2b0fa96d59e5836cb85aa09f`.

The first diagnostic attempt retained two pregame port-recycle failures for seed
`2146151` as historical attempt evidence. Resuming on a healthy isolated port reused
the two manifest-identical completed arms and ran only the affected pair; the final
run summary reports four completed arms, zero active infrastructure failures, and two
resumed arms.

This diagnostic is deliberately claim-ineligible. Its two-pair score delta of `+8`
(`+2` to `+14` paired-bootstrap interval; exact paired randomization `p=0.5`) is
mechanism evidence only and must not update a score or win-rate claim. V4 remains
retired, and its 897 old-code completions remain unpooled.

## PF-PLN expansion-target confirmation

Subsequent PF-PLN optimization identified fixed expansion capacity as the
score-bearing bottleneck. Planner `grounded-impact-planner/1.5` added a
minimum post-settlement runway, with zero as its compatibility default. The
claim-ineligible `expansion_target_pilot_v1` held a conservative 15-turn
runway constant and changed only the city target from three to four. Its 40
fresh pairs estimated +2.025 score points with interval [+0.800, +3.250] and
exact paired p=0.002818.

The policy then remained unchanged for the separately frozen,
claim-eligible `expansion_target_confirmatory_v1`: 100 fresh turn-60 pairs,
score-only, on namespace `pf-pln-expansion-target-confirmatory-v1` in range
`3600000..3799999`. All 200 current arms completed from clean commit
`c7747db`; one pregame observer startup failure was replaced under
source-frozen resume and retained only as historical evidence.

Confirmation increased score from 117.11 to 119.77. The paired effect is
`+2.66`, 95% interval `[+2.00, +3.32]`, with exact two-sided paired sign-flip
`p=9.214e-12`. It added 0.82 settlements and 2.74 citizen-score points, while
technology was unchanged. All safety, source, initial-state, schema, and
exact-replay gates passed over 200 streams, 276,269 events, and 7,425
treatment decisions.

This supports the predeclared own-score claim for the frozen
`civ2civ3`/experimental-AI/turn-60 profile. It does not revise the earlier
cohorts by pooling, establish a win-rate effect, or support an effect strictly
greater than two points. Full evidence is
[`../docs/freeciv/evidence/pf-expansion-target-confirmatory-v1.md`](../docs/freeciv/evidence/pf-expansion-target-confirmatory-v1.md).

### Post-confirmation settlement-deadline hardening

Adapter 1.5 checked the 15-turn settlement runway only when founder production
began. Adapter 1.6 carries that invariant through an existing founder's
movement and settlement: exact-boundary settlement remains valid, late
settlement is rejected, and a founder that can no longer create a
runway-compliant city may route home for exact ruleset population recovery.
The path requires `Cities`, `AddToCity`, positive population cost, strict
distance progress, an advertised join action, actor consumption, and the exact
city-size increase. The zero-runway compatibility default and static policy
remain unchanged.

The change passed 200 combined planner, pressure, runtime, and harness tests.
Authoritative snapshot replay retained zero changed actions and categories.
This is post-confirmation correctness and action-efficiency evidence, not a
revision of the immutable +2.66 adapter-1.5 score claim. See
[`../docs/freeciv/evidence/pf-expansion-deadline-recovery-offline-acceptance.md`](../docs/freeciv/evidence/pf-expansion-deadline-recovery-offline-acceptance.md).
