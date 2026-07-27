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

On the `experimental/pln-pressure` branch, the harness enables the
[PF-PLN control layer](pf-pln.md). Candidate enumeration and legality remain
unchanged; goal-indexed pressure replaces the final global utility sort and emits
its own causal trace before `plan_created`.

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
  expansion_minimum_settlement_runway_turns: 0
  expansion_settlement_deadline_recovery_enabled: true
  expansion_packet_site_preference_enabled: true
  expansion_escort_retention_enabled: false
  expansion_escort_threat_gating_enabled: false
  expansion_escort_route_threat_memory_enabled: false
  expansion_final_settlement_escort_enabled: false
  foodbox_percent: 100
  unit_build_score_divisor: 10
  no_effect_retry_limit: 1
  max_no_effect_failovers_per_scope: 4
  preserve_city_defenders: true
```

The deterministic priority order is:

1. Attack only a packet-visible unit at the advertised target.
2. Found a city only below the city target, at the declared minimum spacing,
   and while its declared post-settlement runway remains available.
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
`expansion_minimum_remaining_turns` is the founder-production start cutoff.
`expansion_minimum_settlement_runway_turns` is the distinct minimum active
runway that must remain after projected settlement. A new founder candidate
must satisfy both bounds and retain positive projected score value. Adapter
1.6 carries the runway invariant through the existing founder's lifecycle:
immediate settlement is valid at the exact deadline, but a founder that still
requires movement at that boundary routes toward exact ruleset population
recovery instead. Late settlement is rejected. The default runway of zero
preserves historical cohort behavior.
`expansion_settlement_deadline_recovery_enabled` is the explicit adapter-1.6
lifecycle switch. The live harness enables it; a false value exists only to
isolate the rule in a controlled diagnostic and does not disable the
independent founder-production runway gate.

Adapter 1.7 adds an optional packet-grounded destination preference for
founders. For a unit with the ruleset's `Cities` capability, the proxy checks
each adjacent packet-known move target against the same terrain,
foreign-owner, and visible-city-spacing preconditions used to advertise Found
City. It attaches `settlement_site_eligible` only when the destination tile
packet exists; a missing tile remains unknown. When at least one move for the
same founder is explicitly true,
`expansion_packet_site_preference_enabled` ranks that move ahead of further
frontier travel while keeping all alternatives available. This cannot
preempt an already advertised founding action and does not classify an
unknown or false destination as impassable.

Adapter 1.8 introduced the opt-in `expansion_escort_retention_enabled` retention
guard. A packet-legal Found City action without a co-located grounded combat
unit is deferred, and the founder holds its exact site while a spare combat
unit follows only legal moves that strictly reduce distance. A sole defender
occupying an existing city is never repurposed as an escort. Once an escort is
co-located, the existing founding, runway, spacing, failure-learning, and exact
effect checks apply unchanged. If the runway expires first, adapter 1.6
population recovery still takes precedence. The switch defaults false pending
engine mechanism evidence.

The selected adapter-1.8 replay rejected the initial escort classifier because
it ran before explorer exclusion. Adapter 1.9 requires the escort actor to
belong to the grounded combat set. When a directly foundable founder is
unescorted and every combat unit is a required city defender, the condition
also grounds a `production_defense` candidate. A population-costing founder
queue may be lossily repurposed into a declared defender, preventing repeated
founder replacement while exact legal sites wait for real defense capacity.

The selected ten-pair generalization showed that unconditional co-location
waits too broadly: founders deferred 46.1 snapshots on average, founded 0.9
fewer cities, and lost 1.9 citizen-score points. Adapter 1.10 therefore adds
the independently opt-in `expansion_escort_threat_gating_enabled` rule. When
both switches are true, an unescorted legal site waits only while an exact
packet-visible opponent is within `pressure_survival_threat_radius` of that
founder. A safe site founds immediately; a threatened site retains the
combat-only escort and production-defense path. The existing settlement
runway remains the hard deadline. Threat-gated deferrals and safe unescorted
settlements are exported separately.

The adapter-1.10 selected replay showed that same-snapshot visibility is too
narrow: the rival founder was observed during approach but had disappeared by
the exact Found City snapshot. Adapter 1.11 therefore adds the independently
opt-in `expansion_escort_route_threat_memory_enabled` correction. Exact
founder-local threat observations persist only for that founder's lifetime
and are cleared on verified settlement, verified population recovery, or
actor disappearance. They do not become global map danger or transfer to
another founder. Escort remains required only while the founder is still
inside the configured radius of exact last-seen opponent geometry. When no
production or escort action is ready, a legal move that strictly increases
distance from that geometry can relocate the founder to a safe site. A
persisted contested route can also ground an empty-stock declared defender
build when no spare combat unit exists; accumulated non-founder production is
not discarded. Observation count, persisted-threat deferrals, avoidance
traversals, and the existing exact production/escort counters expose the full
chain.

The selected adapter-1.11 replay recorded no founder-local observation inside
the three-tile boundary and therefore made no behavioral change. The trace
instead exposed a deterministic preparation gap: a completed founder left 57
shields in unit production, the planner crossed to an improvement and lost 25
shields, and the eventual final city was captured with its local Riflemen
queue at 21 of 30 shields. Adapter 1.12 adds the independently opt-in
`expansion_final_settlement_escort_enabled` rule. Once active and queued
founders cover every remaining expansion slot, it may retain exact same-kind
unit shield carry-over for one declared defender. Only the newest active
founder assigned to the final slot becomes its route target, and only the city
that completes `expansion_city_target` requires co-location. Earlier safe
sites continue to found immediately. A defender queue already projected to
complete inside the observed founder route ETA suppresses duplicate
preparation. Final preparation production, route traversal, deferral, and
settlement completion are exported independently.

The adapter-1.12 selected replay installed the defender and improved own score
by eight, but did not complete the mechanism: the one-tile-per-turn defender
followed the one-tile-per-turn final founder 18 times without closing their
initial separation. Adapter 1.13 corrects that coordination defect. When an
assigned final founder has an available spare combat escort, it suppresses
only that founder's ordinary expansion moves until first co-location.
Population recovery and exact remembered-threat avoidance retain priority.
After co-location, founder and escort alternate legal route moves so the
escort can rejoin after every founder step. Dedicated rendezvous-hold
snapshots expose the correction independently.

The adapter-1.13 ten-seed generalization showed that nominal spare capacity is
not sufficient: two founders waited without any legal escort traversal.
Adapter 1.14 requires at least one exact authoritative unit move that strictly
reduces a non-garrison combat unit's distance to the assigned founder before
creating a rendezvous hold. Without such a move, ordinary founder routing
remains eligible and
`planner_founder_final_escort_rendezvous_no_progress_snapshots` records the
bypass.

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
  production projection metrics, plus deadline-expired population-recovery
  reasons and pre-expansion growth/founder handoffs,
  population cost avoided, conservative
  shield stock discarded, and replacement horizon-completion rate when retiring
  a repeated founder queue;
- repeated unit completions, cumulative unit-score progress, civilization-wide batch
  increments, and guaranteed whole units-built score points for treatment production;
- `model_safe_fallback_rate` and `model_corrections_per_turn`;
- `model_selection_call_rate` and `model_selection_call_avoided_rate`, which
  distinguish turns that enter model-backed goal selection from constrained
  singleton turns resolved by the versioned canonical necessity gate.

The seed-104729 engine-backed deferred-confirmation probe recovered 28 of 40
baseline timeouts and 25 of 34 treatment timeouts. Both arms then learned three
exact founder-route successes and one settlement completion; the earlier
timeout-as-failure accounting reported neither. Reducing confirmation polling
from 10 Hz to 5 Hz also eliminated an observed proxy `E429`. A later two-arm,
60-turn engine trace observed 54 two-second timeouts, all recovered on the next
authoritative turn with zero expirations. The historical 0.5-second deadline
permitted the required two identical samples at 5 Hz; effects that outlive it
remain in the deferred ledger rather than being mislabeled as failures.
The same-seed development replay preserved both scores and all audited action
outcomes while reducing mean arm wall time by 45.5%; see
[the non-claim engineering evidence](evidence/confirmation-timeout-500ms-smoke.md).

The next refresh optimization replaced known-stale client polling with the v3
proxy source-sequence wait and versioned a 50 ms two-sample stability interval.
The fingerprint now includes the exact legal-action digest as well as
authoritative state projections. In a clean two-seed 200 ms/50 ms engine
comparison, canonical actions and outcomes were identical while mean gameplay
latency fell 5.29% and mean confirmation latency fell 10.15%. This remains
engineering evidence rather than a general performance claim; see
[the source-wait smoke](evidence/source-sequence-wait-50ms-smoke.md).

The accepted two-seed traces then showed a bimodal refresh distribution:
same-turn confirmations completed within 248 ms, while 55 actions across the
two seeds produced no same-turn snapshot and consumed the complete 500 ms
window before later recovery. Categories overlapped both groups, so a
category-specific bypass was rejected. The release profile instead uses a
300 ms bound, retaining margin above the observed successful maximum while
preserving deferred reconciliation. A clean two-seed 500 ms/300 ms comparison
preserved exact canonical action sequences and outcomes while reducing mean
gameplay time by 13.39%; see
[the 300 ms confirmation smoke](evidence/confirmation-timeout-300ms-smoke.md).

After the extractor cache was corrected to include packet sequence, the
remaining inter-turn boundary cost averaged 308.8 ms. Applying the already
accepted 50 ms identical-sample interval to initial and inter-turn readiness,
instead of the former 100 ms default, preserved exact canonical actions and
outcomes on both engine seeds. Mean boundary cost fell to 260.1 ms and mean
gameplay time fell 5.03%; see
[the turn-boundary smoke](evidence/turn-boundary-50ms-smoke.md). This is
engineering latency evidence, not a score or population-wide performance
claim.

Final score collection formerly slept 250 ms and then accepted any populated
observer response. It now polls at 50 ms and requires the observer's
authoritative post-horizon turn. In a clean two-seed replay, the gate settled
in 82.5 ms on average, exact canonical actions and outcomes were preserved, and
mean gameplay time fell another 1.61%; see
[the observer-turn smoke](evidence/final-global-turn-smoke.md). The primary
acceptance is stronger score-observation correctness; the latency result
remains engineering evidence.

Engine preflight was then dominated by Publite2's unconditional five-second
restart backoff. Clean zero-exit games now restart after 100 ms, while error
paths retain five seconds, and the harness accepts only the distinct listening
successor of a recorded successful predecessor. Two independent two-seed
engine runs preserved exact behavior while mean preflight fell from 5,253.8 ms
to 423.9 ms and 398.9 ms; see
[the clean-successor recycle smoke](evidence/clean-successor-recycle-smoke.md).
This is operational throughput evidence and does not alter the gameplay score
claim.

The accepted clean-successor path still queried the container process table
twice before checking its listening socket. Reusing the first distinct PID
removes one Docker round trip without weakening either acceptance condition.
Two exact-behavior repeats reduced clean-successor preflight from 311/315 ms to
191/210 ms, a 35.9% mean reduction; see
[the single-probe recycle smoke](evidence/single-probe-server-recycle-smoke.md).

PID discovery and listener verification still required separate Docker
executions. A single container-side snapshot now identifies the exact
`freeciv-web --port` process and reads both TCP listener tables, while the host
retains all distinct-PID, listener, timeout, and failed-predecessor gates. Two
exact-behavior repeats reduced clean-successor preflight by another 35.1% and
kill/recycle preflight by 12.8%; see
[the unified recycle inspection smoke](evidence/unified-server-inspection-smoke.md).

Engine JSONL persistence formerly issued an fsync for each of 758--941 records
per smoke game. The engine writer now retains atomic immediate appends but
fsyncs at completed-turn checkpoints and `run_completed`; per-event durability
remains the default for other callers. Two independent exact-behavior cohorts
reduced mean gameplay time by 8.42% and 9.25%; see
[the turn-durability smoke](evidence/turn-durable-event-writer-smoke.md).

The grounded impact planner never consumes observer-global state. Removing 29
unused inter-turn observer queries from scheduler runs, while retaining initial
identity and fail-closed final scoring, reduced mean gameplay by 2.29% and
3.24% in independent exact-behavior cohorts. See
[the scheduler observer-boundary smoke](evidence/scheduler-observer-boundary-smoke.md).

Authoritative PLN queries also no longer build and discard the generic full
state before constructing their packet-backed projection. Generic state is
loaded lazily only for non-PLN formats or the established extraction-error
fallback. Two independent exact-behavior cohorts bracketed the prior control
within engine variance; the accepted benefit is the deterministic removal of
unused work, not a latency claim. See
[the lazy state-construction smoke](evidence/pln-lazy-state-construction-smoke.md).

Phase-level profiling then showed that authoritative state gating consumed
96.5% of the remaining turn boundary. The v4 conditional stability response
retains atomic construction, an independent 50 ms sample, and exact
turn/source matching while avoiding a second full projection transfer when no
packet changed. Independent exact-behavior cohorts reduced boundary state time
by 10.40% and 10.07%, and gameplay time by 3.65% and 6.10%. See
[the conditional stability smoke](evidence/conditional-state-stability-smoke.md).

Full-turn profiling then separated cognition, non-terminal actions and
confirmation, and end-turn submission. It also exposed two failed 4 KiB cache
compression attempts on every full authoritative response. Bypassing those
ineligible PLN cache operations, while retaining caches for other formats and
the v4 exact-revision path, reduced boundary state time by 5.65% and 4.41% and
gameplay time by 1.60% and 1.74% in independent exact-behavior cohorts. See
[the cache-bypass smoke](evidence/pln-cache-bypass-smoke.md).

The v5 settled-projection path then combined the turn boundary's full
projection and exact-revision quiet proof into one request. It retained the
50 ms wait and left action-effect confirmation on v4 after an action-scoped
trial changed same-turn action ordering. In two accepted exact-behavior
cohorts, boundary state queries fell from 2.0 to 1.0 per turn, boundary state
time fell by 3.44% and 4.93%, gameplay time fell by 3.55% and 2.19%, and every
boundary returned an accepted exact-revision marker. See
[the settled turn-boundary smoke](evidence/settled-turn-boundary-smoke.md).

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

Adapter 1.6 generalizes the same exact recovery mechanism to a second
non-score-bearing condition: an existing founder below the city target whose
configured post-settlement runway is exhausted. City founding remains legal
at the exact boundary, while any founder that still requires movement routes
strictly closer to an owned city. The path still requires compiled `Cities`
and `AddToCity` flags, a positive population cost, an advertised join action,
unit consumption, and the exact city-size gain. Offline acceptance is in
[`evidence/pf-expansion-deadline-recovery-offline-acceptance.md`](evidence/pf-expansion-deadline-recovery-offline-acceptance.md).
It does not revise the immutable expansion-target score confirmation.
The fresh 40-pair engine ablation activated the path in 10 treatment games,
completed 14 joins, restored 28 population, and prevented four late
settlements. Paired score was -0.075 [-0.400, +0.250], exact `p=0.765625`;
the mechanism is a correctness regularizer rather than a supported score or
win-rate improvement. See
[`evidence/pf-expansion-deadline-recovery-diagnostic-v1.md`](evidence/pf-expansion-deadline-recovery-diagnostic-v1.md).

The next packet-boundary correction rejects Found City on a
`PACKET_TILE_INFO.owner` other than the acting player or unclaimed sentinel
`255`. The `civ2civ3` action enablers permit unclaimed and domestic-claimed
sites but not foreign-claimed ones. Omitting that check caused accepted
requests with no city effect and repeated founder search inside foreign
borders. Offline acceptance and the selected mechanism gate are in
[`evidence/pf-foreign-claim-founding-offline-acceptance.md`](evidence/pf-foreign-claim-founding-offline-acceptance.md).

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
Granary first. Sequencing remains conditional rather than a fixed build order. For a deficit
of exactly one founder, treatment may select Granary first only when an exact legal founder
choice exists in that city and a deliberately conservative sequence still fits: Granary
completion, then the founder from zero shields, then the observed/default route ETA, followed
by at least `production_minimum_remaining_turns` of active settlement runway. The projection
grants no food-retention benefit from the Granary. A synthetic six-runway state remains on
direct founder production; live route evidence can make an otherwise similar state qualify.
Sequence selection count, settlement ETA, and remaining runway are reported separately.

The clean v3 replay at
`artifacts/freeciv/impact-preexpansion-growth-1406156-horizon60-v3-20260720`
selected Granary on turn 1, the required founder on turn 25, and one later repurpose
before automatic repetition. Its live conservative sequence projection was 37 turns with
22 settlement-runway turns. Treatment ended with the same three size-5 cities, 15 total
citizens, and score 120 as baseline, improving the same treatment trajectory from 13/118
before repeated-founder retirement to 14/119 after retirement and finally 15/120 after
sequencing. It recorded zero joins, rejection, or fallback; initial-state fidelity, clean
commit `1f71c35`, and the full release audit passed. This closes the targeted mechanism
deficit on one reused seed but remains post-hoc development evidence, not a revised claim.

The clean 30-turn boundary check at
`artifacts/freeciv/impact-preexpansion-fast-104759-horizon30-20260720` used live route
evidence and projected 21 combined turns with exactly eight runway turns, so it correctly
qualified rather than matching the more conservative six-runway unit fixture. It eliminated
all previous join/rebuild cycles and treatment still scored 116 with 12 citizens, the same
absolute treatment outcome as the earlier direct-founder run. The clean baseline scored 115,
giving a one-pair `+1` delta. Initial state, zero rejection/fallback, clean commit `805a15b`,
and the full release audit passed. This boundary validation is still reused-seed development
evidence, not a score estimate.

The clean two-pair targeted run at
`artifacts/freeciv/impact-population-route-targeted-2-20260721` used historical
stranded-founder seeds `1425299` and `1491731` after production-name transport was
hardened. Both current attempts matched initial state and completed with zero rejection or
fallback; their paired score deltas were `+3` and `0` (development-only mean `+1.5`). No
population-recovery route activated because repeated-founder retirement prevented the old
surplus units. Seed `1491731` instead exposed a route-efficiency defect: founder `126`
alternated between `(20,9)` and `(19,10)` on every turn from 42 through 60, leaving the
required third city unbuilt.

Founder routing now retains a bounded actor-local history of confirmed positions. An exact
move to any recently visited position is suppressed only when another server-advertised,
actor-reachable move leads to a fresh position. This covers both immediate reversals and
longer bounded loops. If every grounded exit revisits the recent route, the move remains
eligible; this allows a founder to leave an actual dead end without pruning every option.
`planner_founder_cycle_moves_pruned` reports the distinct suppressed legal actions, while
candidate projections distinguish immediate backtracks from longer route-cycle lengths.

The clean engine replay at
`artifacts/freeciv/impact-founder-cycle-escape-1491731-20260721` confirmed the escape on
the exact reused seed. Treatment followed the old route through `(20,9)` and `(19,10)`,
then selected `(20,11)` instead of returning to `(20,9)`, traversed three more new positions,
and founded city three on turn 46. It recorded eight distinct cycle moves pruned, two settlement
completions, ten citizens, and score 115, compared with the pre-fix treatment's one settlement,
seven citizens, and score 111. The current baseline remained at seven citizens and score 111,
so the paired delta was `+4`. Both arms had zero rejection/fallback, matched initial state, used
clean commit `3aff906`, and passed the complete 3,573-event release audit. This is one reused
development seed and does not revise the immutable score claim.

An offline scan of the immutable 200-pair cohort found founder two-tile cycles in 13 pairs
(23 arms: 10 baseline and 13 treatment); 20 arms repeated for at least six moves and 15 for
at least ten. The second clean replay at
`artifacts/freeciv/impact-founder-cycle-escape-1483352-20260721` targeted an old asymmetric
case. The former pair scored 111 baseline versus 110 treatment while treatment cycled 18
times. With cycle escape, both arms founded all three cities, finished with ten citizens and
score 115, and the paired delta improved from `-1` to `0`. Baseline and treatment reported
ten and six distinct cycle prunes respectively; treatment used one founder build versus
baseline's two. Initial state, zero rejection/fallback, clean implementation identity, and
the complete 2,641-event release audit passed. This supports broad correctness and removes
one reused negative outcome, but is still not an independent estimate.

A third clean confirmation at
`artifacts/freeciv/impact-founder-cycle-escape-1463275-20260721` targeted the strongest
historical treatment-only cycle in that scan. The old treatment alternated founder `113`
between `(10,22)` and `(11,22)` on turns 31--60, never founded its third city, and scored
114 against the old baseline's 116. With cycle escape, treatment routed that founder through
three non-repeating moves and founded city three on turn 18. It finished with 16 citizens
and score 119, while the current baseline finished with 11 citizens and score 116; the
paired delta therefore changed from historical `-2` to current `+3`. The current arms
recorded seven/four distinct cycle prunes, two settlement completions each, zero route
failures, and zero rejection/fallback. Paired initial state, clean commit `01d1011`, stable
implementation identity, and the complete 3,095-event release audit passed. Together, the
three deliberately selected replays show that cycle escape removes the observed defect and
improves all three historical asymmetric outcomes (`0` to `+4`, `-1` to `0`, and `-2` to
`+3`). Selection on prior trace behavior means those deltas cannot estimate population-wide
impact and do not revise the immutable score claim.

The next population-level checkpoint was predeclared as the disjoint
`pilot_horizon_60_v4` namespace: 40 seeds deterministically derived in the committed
`1800000..1899999` range. Its untouched five-pair prefix ran at clean commit `fa510a4` in
`artifacts/freeciv/impact-current-policy-pilot-v4-prefix5-20260721`. Paired deltas were
`+4, +1, 0, -1, 0`, for mean `+0.8` and a wide paired-bootstrap interval `[-0.4, 2.4]`.
All ten arms completed with stable source identity, matched paired initial states, zero
rejection/fallback, and a passing 14,704-event release audit. This small pilot is directional
and cannot revise the formal claim.

The prefix exposed the next route defect without selecting on old outcomes. Treatment seed
`1813833` completed only one settlement while a founder repeated the four-position route
`(10,2) -> (11,2) -> (12,2) -> (11,3)` through turn 60. The generalized recent-revisit guard
must choose a grounded fresh exit in a synthetic four-position trace, preserve a revisiting
edge when it is the only exit, and pass a clean same-seed engine replay before the prefix is
expanded. Stopping or expanding this pilot does not convert it into confirmatory evidence.

The clean same-seed confirmation at
`artifacts/freeciv/impact-founder-bounded-cycle-1813833-20260721` met that acceptance bar.
Treatment followed the former loop through `(11,3)` on turn 26, selected the fresh exit
`(12,4)` on turn 27, reached `(13,5)`, and completed city three on turn 37. It finished at
score 117 versus baseline 115, changing this pair from the prefix's `-1` to `+2`; the current
baseline remained at 115. Treatment recorded two settlement completions, 15 successful
founder moves, seven cycle prunes, and no route failures. Both arms matched initial state,
had zero rejection/fallback, used clean commit `130ee33`, and passed the complete 2,976-event
release audit. This confirms the generalized mechanism on a fresh defect-discovery seed but
is post-pilot reuse, so it does not revise the prefix estimate or formal claim.

An attempted follow-up on seed `1874789` tested whether a confirmed departure and re-entry
should permit one retry of an accepted-but-no-effect founding order. The implementation at
`5ecd095` passed 236 tests and activated in
`artifacts/freeciv/impact-settlement-reentry-1874789-20260721`, but the causal result was
negative: baseline used one re-entry retry and treatment used four, while settlement
completions remained three and two respectively. Treatment score fell from 113 in the
preceding bounded-cycle replay to 112, and neither arm ended with the third city. All safety
gates and the 2,616-event release audit passed, so this was a policy result rather than an
infrastructure failure. Commit `5d21cfd` removes the retry and its telemetry. This rules out
extra retries as the next efficiency win; the remaining trace needs better grounded site
selection or threat handling, not more orders at previously ineffective sites.

No defensive-production quick win was available in that trace: the turn-5 expansion city
already auto-produced the cheapest advertised defender, but accumulated only six shields
before capture on turn 8; the sole existing Alpine unit was required in the capital. The
next non-selected check is frozen as V4 seed indices 5--9:
`1873237, 1884108, 1850973, 1850591, 1866769`. None was executed or inspected before this
declaration. They form a post-fix pilot holdout and must be reported separately from the
original five-pair prefix; the adaptive split is not claim evidence and the two slices must
not be pooled into a confirmatory estimate.

That fixed holdout completed at
`artifacts/freeciv/impact-current-policy-pilot-v4-holdout5-9-20260721`. Its paired deltas
were `0, -2, 0, +3, +5`, mean `+1.2`, with a deliberately wide paired-bootstrap interval
`[-0.8, 3.6]`. All ten arms completed from clean commit `0f8dd42` with matched initial state,
zero rejection/fallback, stable implementation identity, and a passing 15,273-event release
audit. The positive direction does not overcome `n=5` uncertainty and does not update the
immutable claim.

The sole negative holdout seed, `1884108`, exposed an incomplete Granary-first sequence.
Treatment's capital queued a founder but stalled permanently at size two with zero food
surplus. A second city correctly selected Granary on turn 21, but after completion the
server's automatic next target immediately accumulated three shields. The ordinary lossless
switch guard then prevented the promised founder handoff for the rest of the horizon;
treatment ended with two cities and score 111 versus baseline's three cities and score 113.

A confirmed pre-expansion selection now persists its exact city and founder target. Once
Granary is no longer current, the handoff may discard automatic completion overflow or at
most one current shield-surplus tick, and only while expansion is still deficient and the
exact founder still projects settlement by the horizon. Missing that boundary does not
authorize a later destructive switch. `production_preexpansion_founder_changes` reports the
followup separately from growth selection. Acceptance requires synthetic proof of the exact
handoff and discard bound, the full FreeCiv suite, and a clean seed-`1884108` replay before
any untouched evaluation.

The first clean engine replay confirmed that the persisted handoff itself worked but did not
improve seed `1884108`: two late replacement founders were destroyed, leaving treatment at
score 111 versus baseline 113. A bounded authoritative attrition guard then activated once
without changing that outcome; it is retained as route correctness hardening, not as score
evidence. The upstream projection was the material defect: at turn 21 city 109 was already
population-ready for the two-population founder, so Granary-first delayed a shield-bound
build by eight turns. Pre-expansion growth is now eligible only when the direct founder's
population-readiness ETA is strictly greater than its shield-completion ETA.

The clean corrected replay at
`artifacts/freeciv/impact-direct-founder-1884108-20260721` selected Settlers on turn 21,
completed the founder on turn 28, and founded city three on turn 33. Treatment ended with
13 citizens and score 116 versus baseline's ten citizens and score 113, changing the reused
seed's paired delta from `-2` to `+3`. Both arms had two settlements, eight successful route
moves, zero route failures/rejections/fallbacks, clean source `35a7bcc`, matched initial
state, and a passing 2,748-event release audit. This is selected-seed mechanism evidence,
not a revised formal estimate.

Before inspecting further outcomes, the next untouched pilot checkpoint is frozen as V4
indices 10--14: `1847487, 1825421, 1856447, 1859499, 1836213`. It must be reported as its
own adaptive five-pair slice and not pooled with indices 0--9 or the immutable confirmatory
cohort.

That frozen slice completed at
`artifacts/freeciv/impact-current-policy-pilot-v4-holdout10-14-20260721` with paired score
deltas `-2, +2, +5, +6, +3`, mean `+2.80`, and paired-bootstrap interval
`[+0.20, +5.00]`. The exact two-sided sign-flip p-value was `0.1875` at five pairs. All ten
arms passed initial-state fidelity, rejection/fallback safety, required clean-source stability
at `8acaacb`, and the full 14,255-event release audit. This is positive development evidence
but remains underpowered, adaptive, and claim-ineligible; it is neither pooled with earlier
V4 slices nor used to revise the immutable formal estimate. Seed `1847487`, the sole negative
pair and sole treatment arm missing the second settlement, is the next post-hoc diagnostic
target.

That trace showed the next route-boundary issue. Exact edges learned while the civilization
had one city were still receiving a positive corridor bonus after city two changed the
expansion geometry. The replacement founder therefore followed the already-consumed route,
made an accepted-but-no-effect founding attempt between the existing cities, and was later
lost. Traversability bonuses are now keyed by both exact edge and authoritative city layout.
They remain reusable by another founder while the layout is unchanged, but cannot override
fresh city-network separation after a city is founded. A clean same-seed replay is required
before this post-hoc hardening is treated as causal mechanism evidence.

The clean replay at `artifacts/freeciv/impact-founder-layout-1847487-20260721` confirmed the
mechanism. The treatment founder took the fresh northward route `(7,4) -> (7,3) -> (6,2)`,
founded city three on turn 27, and finished at score 112 versus the current baseline's 109.
Both arms completed two settlements with zero route failures/rejections/fallbacks, paired
fidelity, required clean source `2e597d0`, and a passing 2,996-event release audit. The
current `+3` pair replaces a prior `-2` directional result on this selected seed, but does
not revise a population estimate.

Before further outcome inspection, V4 indices 15--19 are frozen as the next untouched
current-policy checkpoint: `1887134, 1818337, 1881562, 1825420, 1844064`. This adaptive
five-pair slice remains separate from all earlier V4 slices and from the immutable claim.

That slice completed at
`artifacts/freeciv/impact-current-policy-pilot-v4-holdout15-19-20260721` with deltas
`0, +1, 0, 0, 0`, mean `+0.20`, and interval `[0.00, 0.60]`. All ten arms passed paired
fidelity, zero rejection/fallback, required clean-source stability at `2e5f2b8`, and the
15,038-event release audit. The result is non-regressive but small, adaptive, and
claim-ineligible. Seed `1881562` is the only treatment-specific missing-settlement case and
is the next post-hoc route diagnostic; two other one-settlement pairs affected both arms.

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

Seed `1881562` then showed an exact failed-site reuse: founder 114's accepted order at
`(4,10)` created no city, and replacement founder 119 later repeated the same order at the
same site under the same city layout. The planner now remembers candidate-confirmed failed
settlement sites across founder actors, scoped by founder type, map, position, and city
layout. It suppresses the repeated order while leaving movement available; a changed layout
restores eligibility. `planner_failed_settlement_sites_pruned` exposes activation. This is
deliberate anti-retry hardening and does not restore the previously rejected retry policy.

The clean replay at
`artifacts/freeciv/impact-failed-settlement-site-1881562-20260721` recorded two treatment
prunes and removed both the immediate retry and the later cross-founder order at `(4,10)`.
Attempts fell from five to four, but treatment still completed one settlement and the pair
remained 114–114. Clean source `5a7be48`, paired fidelity, zero rejection/fallback, and the
2,715-event release audit passed. This confirms bounded efficiency/correctness impact, not a
score gain; adjacent failed sites are not generalized into an unsupported regional ban.

A separate clean replay of V4 seed `1825420` at
`artifacts/freeciv/impact-failed-site-route-1825420-20260721` showed why regional failure
memory would be the wrong abstraction. Each arm tried eight distinct post-expansion sites in
the compact `(8..10, 10..13)` area; exact-site memory activated once, but both still completed
one settlement and scored 111. The proxy advertised founding after checking only ocean class
and city spacing, while the active ruleset also requires the current terrain not to carry
`NoCities`. The pinned proxy patch now evaluates that exact packet bit before advertising
`unit_build_city`. A clean same-seed engine replay is required before treating this as more
than legal-action correctness hardening.

The clean confirmation at `artifacts/freeciv/impact-nocities-1825420-20260721` removed the
founding orders at two packet-known `NoCities` sites in each arm, reducing attempts from nine
to seven. Six other distinct sites still had no effect, both arms completed one settlement,
and both scored 110. Clean source `d0562f2`, paired initial-state fidelity, zero
rejection/fallback, and the complete 3,692-event release audit passed. Retain the exact
terrain legality check, but do not count this selected-seed efficiency result as a score gain
or infer that the remaining failures share the same terrain cause.

V4 indices 20--24 first produced deltas `+1,+3,+4,0,+2`, but that execution is invalid as a
clean checkpoint because the first baseline arm fell back on turns 1 and 2. After replacing
the one-token readiness probe with validated full-chat readiness, the fixed operational rerun
at `artifacts/freeciv/impact-current-policy-pilot-v4-holdout20-24-chatready-rerun-20260721`
completed with deltas `+2,+3,+4,0,+2`, mean `+2.20`, and paired-bootstrap interval
`[+1.00,+3.20]`. The exact two-sided p-value was `0.125`; both arms had zero fallback and
rejection, paired initial states matched, source stayed clean at `06cbe5e`, and the complete
14,310-event release audit passed. This confirms operational stability and positive
development direction only: the five seeds were already exposed by the invalid first run,
`n=5` is underpowered, and the result cannot revise the immutable claim.

## Operational note

On the recorded CPU host, a cold load of `qwen3-coder-next:latest` took 41.6 seconds,
which exceeds the configured 28-second generation budget. The runner handles this
operationally with the versioned `chat-once-expiry-aware-resident-v2` policy and
the declared 90-second readiness timeout plus 30-minute keep-alive. The first
preflight for an exact endpoint/model/think tuple validates `{"ready":true}`
through native `/api/chat`, exercising model load, chat routing, and JSON decoding
outside the timed turn budget. Later arms check the exact model row from `/api/ps`
under the same lock. A valid timezone-qualified expiry with at least 300 seconds
remaining is reused directly; an absent, invalid, or near-expiry row uses an empty
`/api/generate` request to refresh the model without generating completion tokens.
Failed refreshes fall back to the complete chat validation. Verify
`model_safe_fallback_rate=0` before interpreting a confirmatory result. Readiness or
cold-start failures remain visible infrastructure failures; claim-eligible arms also
fail closed on any in-game model fallback and must be retried as fresh attempts rather
than silently counted as completed evidence.
