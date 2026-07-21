# Grounded gameplay impact policy

## Purpose

The M7 release matrix proved legality, safety, parity, and latency, but the scheduler
selected only one cognitive engine action in a 30-turn game. The grounded impact
planner makes scheduler-enabled conditions act on more of FreeCiv's authoritative
legal-action surface without moving inference into a heuristic policy or weakening
the execution gate.

The planner consumes only an `AuthoritativeSnapshot` and its canonical
`legal_action_json`. Every result is a one-step `Plan` tied to the current snapshot
ID and legal-action digest. `ExecutionGate` still revalidates the plan, snapshot,
legal digest, server membership, and monitor status immediately before transport.

## Declared policy

`profile/freeciv_harness*.yaml` records all behavioral controls:

```yaml
impact_policy:
  max_actions_per_turn: 8
  expansion_city_target: 3
  settle_min_distance: 3
  horizon_turn: 30
  production_minimum_remaining_turns: 8
  expansion_minimum_remaining_turns: 12
  foodbox_percent: 100
  unit_build_score_divisor: 10
  no_effect_retry_limit: 1
  max_no_effect_failovers_per_scope: 4
  preserve_city_defenders: true
```

The deterministic priority order is:

1. Attack only a packet-visible unit at the advertised target.
2. Found a city only below the city target and at the declared minimum spacing.
3. Move only a ruleset-declared founder outward while expansion is incomplete,
   preferring city-network separation and grounded traversability evidence.
4. Fill a grounded city-defense deficit and preserve the sole garrison.
5. Select one founder, defender, or growth/economy production per city without
   switching away from accumulated shields or a useful current production.
6. Route diplomats, spies, caravans, and explorers toward the nearest exact
   packet-known hut whenever an advertised move strictly reduces that distance.
7. Otherwise explore with those units only when the advertised destination has not
   already been observed.
8. Move a non-garrison unit tactically only when the advertised destination strictly
   reduces distance to a packet-visible opponent. Targetless frontier movement is
   not an impact candidate.

Founder and worker roles come from source-provenanced ruleset traits. The FreeCiv
`Cities` flag denotes city-founding capability; the broader `Settlers` flag denotes
terrain workers and does not make Migrants, Workers, or Engineers founders. A
server-advertised `unit_build_city` action corroborates and caches a founder type.

Expansion demand is capacity-based: current cities, legal founder units, and founder
builds already queued with an exact projected settlement no later than the horizon each
count toward `expansion_city_target`.
This permits one founder to be pipelined while an earlier founder is routing, but stops
additional cities from selecting redundant settlers once the target is covered.

Founder completion ETA is the maximum of shield completion and population readiness.
Population readiness uses the compiled active-ruleset `granary_food_ini` and
`granary_food_inc` parameters, the pinned runtime `foodbox_percent`, and authoritative
city size, food stock, and food surplus. No unobserved food retention is assumed.
`expansion_minimum_remaining_turns` is a founder-production start cutoff, not a second
post-settlement runway. A new founder candidate must start while at least that many turns
remain, have positive projected score value, and complete its minimum-distance route no
later than the horizon. This rejects late settlers that would consume population and
movement without reaching a score-bearing settlement while allowing a population-delayed
build that still settles in time.

Founder routing is feedback-driven in the horizon-score policy. On the first step from
a city, aggregate distance from the complete city network breaks minimum-distance ties
in favor of open expansion space. A move target becomes a proven traversable edge only
when the authoritative post-action actor position exactly equals that target; transport
acceptance or movement-point consumption alone is insufficient. Exact failed edges are
pruned for the unchanged actor and penalized, but not prohibited, for another founder
because occupancy can be transient. Failed actor edges are scoped to the unchanged city
layout so a newly established city can reopen routing choices. The observed
success/failure ratio also inflates later founder settlement ETA instead of continuing to
assume one successful tile per turn after the engine has shown otherwise. No directional
momentum is inferred from a diagonal step: engine-backed evaluation showed that a
diagonal-heading preference can overshoot a productive legal city site when the terrain
corridor bends. An exact successful horizontal or vertical step may bias one matching
step while the founder remains inside minimum settlement spacing. A failed matching move,
a settlement attempt, changed city layout, or reaching minimum spacing clears that bias.
Static-priority paired baselines keep their frozen movement ranking.

The pinned server scores cumulative unit production in groups of
`unit_build_score_divisor` (10 for this engine). Horizon-score projections therefore
model the first completion plus conservative repeated completions at the current shield
surplus. Because the engine counter is civilization-wide, the planner compares the
optimized batch across all losslessly switchable cities with their current production
trajectory. It commits one member at a time, waits for exact authoritative confirmation,
and proceeds only when the batch guarantees at least ten additional completions. A failed,
deferred, or next-turn member cancels the remaining batch. Score-bearing non-unit builds
are never displaced by this calculation. A founder build made redundant by completed
expansion may be retired earlier to avoid further population cost. Zero shield surplus
cannot project a completion. Static-priority baselines retain their frozen one-target
production behavior.

The three-pair development cohort at
`artifacts/freeciv/impact-repeated-unit-production-dev-3-20260720` completed with
matched initial state, zero infrastructure failure, rejection, or model fallback, and
all safety gates green. No arm selected `production_repurpose` or
`production_military_score` at the 30-turn horizon, so the observed score deltas
(`-2`, `0`, `+1`) do not estimate this new mechanism. Seed `104759` did independently
reconfirm three population joins, six recovered population, and a one-point treatment
citizen/score gain. Repeat-unit telemetry excludes founders and other population-bound
units because their production cadence is not stationary.

The subsequent clean-source 60-turn pair at
`artifacts/freeciv/impact-repeated-unit-horizon60-activation-20260720` also selected no
repeat-unit category and recorded zero projected unit completions. It passed source freeze,
fidelity, all safety gates, and the full release audit; treatment scored `112` versus
baseline `110` through four exact population joins and eight recovered population instead.
This falsified the single-city activation hypothesis and motivated civilization-wide batch
accounting. The `+2` remains one pilot pair and is not a revised claim.

A read-only replay then reconstructed exact production choices for 1,718 authoritative
snapshots across all 40 prior horizon-60 treatment games. The civilization-wide rule found
zero eligible batch or repurpose decisions. Batch membership is memoized once per snapshot
and legal-action set to avoid quadratic work across large buildable lists. This establishes
the rule as a dormant correctness guard for the observed distribution, not a current score
improvement target; no live statistical cohort is warranted for it.

One successful unit-scoped strategic action and one successful production change per
city are allowed per turn. After a no-effect action, up to
`max_no_effect_failovers_per_scope` alternative exact actions may use the same scope,
within the global `max_actions_per_turn` budget. A successful fortification is not
reissued on every later turn. These bounds prevent stale proxy action lists or
effect-free orders from consuming the action budget.

Accepted transport is feedback, not proof that an order changed the game. After an
accepted action produces no authoritative state-hash change, the planner records the
exact action and a local grounding signature for its actor, city, visible target, and
city layout. The action is suppressed after `no_effect_retry_limit` attempts while
that signature remains unchanged. A material local change makes it eligible again;
turn advancement and movement-point refresh alone do not. When another advertised
non-unit action exists for the same scope, it can be selected immediately in the same
turn. The first alternative that produces an authoritative change closes that scope
for the rest of the turn.

Transport-accepted terminal actions close their actor scope immediately even if the
first refreshed packet has not caught up. This prevents a delayed city-founding or
suicide-attack effect from creating a stale follow-up action against an actor the
engine has already consumed.

An accepted unit action also counts as an observed local effect when the authoritative
actor position, activity, health, existence, or movement points change, even if the
proxy's broader state hash remains unchanged. This closes the successful actor scope
before another same-turn order can spend already-consumed movement points.

The actor scope also closes conservatively when an accepted unit order has no visible
effect in the first refreshed snapshot, including when civserver emits no newer
authoritative sequence before the bounded refresh deadline. Live confirmatory
preflight showed that the engine can consume movement points while the proxy continues
to publish stale actor position and movement values, or acknowledges a mechanically
legal order that produces no packet until turn closure. A missed bounded wait now enters
a deferred-confirmation ledger rather than being mislabeled as no effect. Any later
same-turn snapshot can prove the exact candidate effect; the first later-turn snapshot
either recovers that effect or expires the entry as a grounded no-effect outcome. The
scope remains closed while confirmation is pending, so deferred accounting cannot send
a stale second unit order. Non-unit actions still require candidate-specific evidence.

## Impact telemetry

The harness now aggregates these paired metrics with the same bootstrap method as
the existing score and latency metrics:

- `planned_engine_actions` and `meaningful_actions_per_turn`;
- `decision_impact_actions` and `decision_impact_turn_rate`;
- `decision_effect_observed_rate` and `decision_no_effect_actions`;
- confirmation latency/timeouts plus deferred, recovered, expired, and still-pending
  confirmation counts, which distinguish a bounded wait from an actual failed action;
- `decision_no_effect_retries_blocked` for exact actions rejected by grounded
  no-effect feedback;
- `decision_no_effect_failover_attempts`, `decision_no_effect_failover_recoveries`,
  and `decision_no_effect_failover_recovery_rate` for bounded same-turn recovery;
- `action_type_diversity`, `positions_explored`, and `tactical_actions`;
- `cities_gained`, exact `cities_founded`, `technologies_acquired`,
  `production_changes`, and `score_gain`;
- `founder_production_changes`, `settlement_attempts`, and
  `settlement_completions`;
- `planner_founder_capable_unit_types`,
  `planner_capability_pruned_worker_moves`, and
  `planner_nonprogress_moves_pruned`, plus repeated failed exploration
  destinations pruned after distinct-source confirmation;
- `population_recovery_route_attempts`, route successes/rate, exact join
  attempts/completions, and `population_recovered` for ruleset-valued
  surplus-founder return and recovery after the expansion target is complete;
- `planner_founder_unreachable_moves_pruned`, founder route successes, failures,
  success rate, cardinal-corridor attempts/successes, and observed-evidence route ETA;
- population-ready, settlement ETA/runway, founder-deficit, and compiler-source
  production projection metrics, plus population cost avoided, conservative
  shield stock discarded, and replacement horizon-completion rate when retiring
  a repeated founder queue;
- repeated unit completions, cumulative unit-score progress, civilization-wide batch
  increments, and guaranteed whole units-built score points for treatment production;
- `model_safe_fallback_rate` and `model_corrections_per_turn`.

The seed-104729 engine-backed deferred-confirmation probe recovered 28 of 40
baseline timeouts and 25 of 34 treatment timeouts. Both arms then learned three
exact founder-route successes and one settlement completion; the earlier
timeout-as-failure accounting reported neither. Reducing confirmation polling
from 10 Hz to 5 Hz also eliminated an observed proxy `E429` without changing
the two-second confirmation deadline or the two-identical-snapshot stability gate.

Exploration destinations also gain conservative cross-source failure evidence.
One failed move remains retryable because occupancy and tactical obstructions can
be transient. After the same unit type remains stationary while targeting the
same destination from two distinct adjacent sources, that destination is pruned
from exploration choices. A later exact successful traversal clears the evidence,
and packet-visible enemy occupancy is never recorded as terrain evidence.

On the fresh seed-104729 failed-destination probe, both arms pruned three such
destinations. Compared with the preceding same-seed probe, baseline confirmation
expirations fell from 10 to 8 and effect rate rose from 70.73% to 77.5%; treatment
expirations fell from 9 to 7 and effect rate rose from 81.25% to 85.42%. Both arms
still scored 107, founded one city, and learned three founder-route successes.

The next same-seed trace classified six of the remaining seven expirations in each
arm as moves onto ocean terrain. The proxy had treated the Diplomat type's static
Embark action capability as proof that a transport existed. Movement advertisement
now requires an owned, packet-visible transport on the exact target, compatible
ruleset cargo bits, and spare authoritative cargo capacity. In the clean
`artifacts/freeciv/impact-transport-legality-probe-104729-20260720` pair, those
ocean attempts disappeared. Baseline effect rate rose from 83.72% to 90.00% and
expirations fell from seven to four; treatment effect rate rose from 85.42% to
93.75% and expirations fell from seven to two. Both arms passed every safety gate
and again scored 107, so this remains mechanism evidence rather than a score claim.

## Capability and movement-progress smoke evidence

The paired development smokes at
`artifacts/freeciv/impact-founder-capability-smoke-20260720` and
`artifacts/freeciv/impact-movement-progress-smoke-20260720` use the same seed and
30-turn engine configuration. They are mechanism checks, not claim-eligible cohorts.
The refined planner observed exactly one founder-capable civ2civ3 unit type in each
arm and completed both settlement attempts without rejection.

On the treatment arm, requiring grounded movement progress reduced impact actions
from 70 to 38, no-effect actions from 30 to 19, and retry suppressions from 132 to
42. All 29 targetless `frontier_move` selections disappeared. The score remained
107, cities founded remained one, initial-state fidelity passed, and every absolute
safety gate remained green. The engine recorded 54 distinct non-progress move
candidates pruned in the treatment arm and 14 in baseline; baseline selected-action
volume was unchanged because those candidates had not won its ranking.

Transport acceptance and observed state effect are intentionally separate. An action
can be legal and accepted without changing the authoritative state; the report must
not count that distinction as proven gameplay value.

## Founder-routing development evidence

The five-pair engine-backed development cohort at
`artifacts/freeciv/impact-founder-routing-dev-3-v4-20260720` evaluates the final
first-step-only city-separation policy. All ten games completed, initial fingerprints
matched, and engine rejection, model fallback, and turn-latency safety gates passed.
Treatment minus baseline founder-route failures fell by `2.8 [-5.2,-0.4]`, route
success rate rose by `0.181 [0.032,0.338]`, no-effect actions fell by
`3.0 [0.4,6.6]`, and retry suppressions fell by `17.8 [2.4,34.0]` per game (intervals
are paired bootstrap intervals; decreases are written here as positive reductions).

On diagnostic seed `104759`, the earlier treatment needed three stagnant turns before
the second founder entered the usable corridor and founded on turn 14. The final policy
moved through `(20,10)`, `(20,11)`, and `(20,12)` on turns 8--10 and founded on turn 11:
six exact founder-route successes, zero failures, 13 rather than 23 no-effect actions,
and score 114 in both treatment versions. Across the five matched pairs, score delta
remained `+1.0 [0.2,1.8]` with exact sign-flip `p=0.25`; score-lead-rate delta remained
zero. This dirty-source development cohort is mechanism evidence, not a statistical
score or win-rate claim.

## Development smoke evidence

The engine-backed one-seed smoke is retained at
`artifacts/freeciv/impact-smoke-20260718-final`. With the configured Qwen model warm,
the 30-turn full loop completed with:

- 80 accepted actions and zero engine rejection;
- 50 planned non-end actions, compared with one in the prior same-seed release trace;
- six non-end action types: research, movement, city founding, city production,
  fortification, and packet-visible attack;
- one net new city, 12 newly visited unit positions, and score 106 (`+3` during the
  run), versus score 104 in the prior same-seed release trace;
- 30/30 turns under 30 seconds, maximum 3.714 seconds and mean 0.325 seconds;
- zero model fallback and zero corrective retry.

This is a development smoke, not evidence of a statistically reliable score or
fixed-horizon lead-rate improvement. The hardened track uses 40 fresh pilot pairs to
estimate nuisance variance and discordance without making a claim, followed by a
separate predeclared confirmatory cohort. Sample size is never chosen from a favorable
observed treatment effect.

The retained trace also exposed 28 accepted actions with no immediate effect: 26
repeated diplomat moves toward one unchanged unreachable tile and two repeated city
founding attempts from one unchanged site. Replaying the new retry rule against those
unchanged local signatures would block 26 repeats after their first failed attempt,
reducing that trace from 49 to 23 impact attempts while retaining all 21 observed
effects. This is a trace-derived expectation (91.3% effect-observed rate), not a
replacement for a new engine-backed paired run.

## No-effect feedback smoke evidence

The follow-up real-engine run is retained at
`artifacts/freeciv/no-effect-feedback-engine-smoke`. It used the same seed, opponent,
model, and 30-turn limit as the earlier smoke and completed with:

- 49 impact actions and 50 total planned non-end actions, with 28 immediate effects
  (`57.1%`, up from `42.9%`) and 21 no-effect actions;
- 60 unchanged exact candidates blocked before transport, while other grounded legal
  actions remained eligible;
- 19 newly visited unit positions (up from 12), one net new city, six non-end action
  types, and score 106 (`+3` during the run);
- 80 accepted actions, zero engine rejection, zero model fallback, and 30/30 full
  turns below 30 seconds (maximum 8.349 seconds);
- a passing 787-event cognitive-trace release audit, trace SHA-256
  `642c06ef7510f88a2e6985693a2c77efd7e120ec9d7fc6c040b57a63bdb375fc`.

The same score with broader exploration and fewer ineffective decisions is evidence
that the feedback mechanism works on this seed, but it is still not a statistically
reliable win/score improvement. The declared paired-seed experiment remains the next
measurement gate.

## Same-turn failover smoke evidence

The bounded-failover run is retained at
`artifacts/freeciv/same-turn-failover-engine-smoke-final`. Against the same seed and
30-turn configuration it completed with:

- 58 impact actions, 45 immediate effects, and 13 no-effect actions (`77.6%`
  effect-observed rate, up from `57.1%`);
- 11 same-turn failover attempts, seven authoritative recoveries, and a `63.6%`
  failover recovery rate;
- 36 newly visited unit positions (up from 19) and nine tactical actions (up from
  two), while retaining one net new city, six action types, and score 106 (`+3`);
- 89 accepted actions, zero engine rejection, zero model fallback, and 30/30 turns
  below 30 seconds (maximum 5.324 seconds);
- a passing 838-event cognitive-trace release audit, trace SHA-256
  `c0a254a1ab10221c11f17094bd000f99855c2d672c6e11476aa8b7e211c32242`.

The first validation attempt is retained at
`artifacts/freeciv/same-turn-failover-engine-smoke`. It exposed a delayed-state race:
the engine accepted city founding before the refreshed packet removed the settler,
and a stale follow-up move was rejected. That run remains an infrastructure failure;
the terminal-action scope guard was added from its evidence, and the final rerun had
zero rejection. As with the preceding smokes, this is behavioral evidence on one
seed, not a conclusive score or win-rate result.

The next measurement gate is executable through the hardened paired track described
in [paired-impact-evaluation.md](paired-impact-evaluation.md). Previously exercised
seeds are development-only. Fresh pilot and confirmatory cohorts require a clean,
stable source commit; the baseline disables same-turn failover while retaining every
other policy setting, and treatment uses the declared four-failover bound. The binary
endpoint is explicitly a score lead at the fixed horizon, not an engine-reported
terminal victory. A confirmatory score claim requires both a paired confidence
interval excluding zero and an exact paired sign-flip randomization test at the
predeclared alpha; the stronger two-point claim repeats both gates at that margin.

## Surplus-founder population recovery evidence

The development run at
`artifacts/freeciv/impact-population-recovery-dev-3-20260720` validates an
immediate score-preservation path for repeated Settler output after the three-city
target is complete. Treatment selects only an exact server-advertised
`unit_join_city` action whose actor is a ruleset `Cities` founder with positive
`pop_cost`, is co-located with the owned target city, and carries that city's
numeric ID through the proxy. The effect is counted only when the actor disappears
and that exact city's size rises by the compiled population cost.

All three pairs completed without infrastructure failure or engine rejection.
The exploratory mean score delta was `+2.0` with bootstrap interval `[0, 4]`.
On seed `104759`, five joins recovered 10 cumulative population; final citizens
rose from 9 to 14, final score from 113 to 117, and no-effect actions fell from
23 to 14. This is mechanism and development evidence, not a new statistical
claim. A disjoint, adequately sized pilot remains necessary.

Historical treatment traces from the immutable 200-pair horizon-60 confirmation
(`impact-confirmatory-score-horizon60-v1-engine-1ca6b35-v1`) show that immediate
co-location was too restrictive: 28 of 200 games (14%) reached the three-city target
while retaining at least one `Settlers` unit away from every owned city. The planner
previously made those founders inert. Treatment now considers an advertised unit move
only when the compiled unit has all three exact properties needed by this path:
`Cities`, `AddToCity`, and positive `pop_cost`. It accepts only a step that strictly
reduces wrapped map distance to an owned city. At arrival, the existing independent
join rule still requires an exact server-advertised `unit_join_city` action and confirms
both unit consumption and the target city's exact population gain. The static-priority
baseline is unchanged. Route attempts and exact-position successes are reported
separately from completed joins so movement cannot be mistaken for score impact.

The clean three-pair development rerun at
`artifacts/freeciv/impact-population-recovery-route-dev-3-20260720` did not activate
the return route, but seed `104759` completed three already-co-located joins and
reported six gross population recovered. Pair score deltas were `-2`, `0`, and `+6`
(mean `+1.33`); one baseline model fallback failed the absolute safety gate. The full
release audit still passed across all 4,584 events. These are development diagnostics,
not evidence for a revised claim.

A post-hoc horizon-60 replay of historical seed `1406156` then exposed a more important
accounting error. Treatment completed five exact joins and reported ten gross population
recovered, but ended with 13 citizens and score 118 versus baseline's 15 citizens and
score 120. The city had remained on automatic repeated Settler production after the
expansion target, paying population before joining those units back. Gross join recovery
therefore is not an incremental population gain. Treatment now retires such a queue even
with nonzero shield stock only when the current founder would complete by the horizon and
city, existing-founder, and other projected-settler capacity still meets the target after
excluding that exact queue. Replacement ETA assumes zero carried shields. A necessary
queue, a queue that cannot complete by the horizon, and the static baseline remain
unchanged.

The clean same-seed confirmation at
`artifacts/freeciv/impact-population-recovery-stop-repeat-1406156-horizon60-v2-20260720`
activated one repurpose on turn 17. It reported two population cost avoided, charged all
24 accumulated shields as discarded, completed the Granary replacement by the horizon,
and eliminated the five prior Settler join/rebuild cycles. Treatment citizens improved
from 13 to 14 and its score from 118 to 119; the unchanged baseline remained at 15
citizens and score 120. Both arms had zero rejection/fallback, matched initial state,
used clean commit `736c500`, and passed the complete cognitive-trace release audit. The
one-point causal improvement on a reused post-hoc seed validates the mechanism but is not
a statistical estimate or revised score claim.

The remaining same-seed citizen gap came from the initial build order rather than repeated
production. Treatment started the last required Settler immediately; baseline completed a
Granary first. A universal Granary-first rule would discard the observed `+6` citizen/score
result on the fast-food 30-turn seed `104759`, so sequencing is conditional. For a deficit
of exactly one founder, treatment may select Granary first only when an exact legal founder
choice exists in that city and a deliberately conservative sequence still fits: Granary
completion, then the founder from zero shields, then the observed/default route ETA, followed
by at least `production_minimum_remaining_turns` of active settlement runway. The projection
grants no food-retention benefit from the Granary. Slow-food seed `1406156` retains 17 runway
turns and qualifies; fast 30-turn seed `104759` retains only six and continues to build the
founder directly. Sequence selection count, settlement ETA, and remaining runway are reported
separately.

## Combat attribution, occupancy, and hut-entry hardening

Offensive actions retain an exact pre-action fingerprint of the packet-visible enemy
stack at their grounded target. An accepted attack is now confirmed when either its
actor-local state or that target stack changes, so removing a defender counts even
when the attacker remains stationary. An unchanged actor and unchanged target remain
a no-effect result. Plain movement separately excludes an exact packet-visible
non-allied unit or city at the destination; allied and unoccupied targets are not
discarded.

The proxy also distinguishes a Freeciv hut action from ordinary movement. It converts
the move to `PACKET_UNIT_DO_ACTION` only when the exact destination tile's extras,
the referenced ruleset extra's `EC_HUT` cause, the actor unit type, and a statically
enabled hut action (`90`--`97`) are all packet-grounded. Missing or conflicting facts
fall back to the ordinary move path rather than guessing from terrain or names.

The clean warm engine pair at
`artifacts/freeciv/impact-hut-action-probe-104729-v3-20260720` passed all safety and
fidelity gates with zero rejection or model fallback. The exact hut move succeeded;
baseline scored `107` at a `95.12%` candidate-effect rate and treatment scored `109`
at `97.92%`. Expirations fell from two per arm in the preceding probe to one per arm.
The remaining expiry had no hut fact and is correctly still ordinary movement. The
observed `+2` delta is one development pair on a reused seed, not a revised claim;
the immutable disjoint 200-pair result remains `+0.435` until a fresh predeclared
cohort passes both paired inference gates.

The authoritative bridge now also publishes the exact tile IDs whose packet-retained
extras resolve to `EC_HUT`. Explorer-role movement ranks only advertised steps that
strictly reduce wrapped map distance to one of those tiles; it never derives a hut from
terrain, a name, or observer-only state. The destination converter independently repeats
the exact tile-extra and ruleset-cause check before selecting the explicit hut action.

The clean development pair at
`artifacts/freeciv/impact-known-hut-route-probe-104729-20260720` exercised this route from
turn 1, reached the first two packet-known huts by turns 3 and 7, passed paired initial-state
fidelity and every release-audit safety check, and had zero engine rejection or model
fallback. Baseline scored `109` and treatment `107`; the `-2` delta came entirely from one
technology and demonstrates that faster hut collection can alter a stochastic reward and
action trajectory without guaranteeing a better paired score. This is correctness and
mechanism evidence only, not a revised score claim.

## Operational note

On the recorded CPU host, a cold load of `qwen3-coder-next:latest` took 41.6 seconds,
which exceeds the configured 28-second generation budget. The runner now handles this
operationally with a native `/api/generate` readiness request before every engine arm,
using the declared 90-second readiness timeout and 30-minute keep-alive. Verify
`model_safe_fallback_rate=0` before interpreting a confirmatory result. Readiness or
cold-start failures remain visible infrastructure failures; claim-eligible arms also
fail closed on any in-game model fallback and must be retried as fresh attempts rather
than silently counted as completed evidence.
