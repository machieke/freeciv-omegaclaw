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
  no_effect_retry_limit: 1
  max_no_effect_failovers_per_scope: 4
  preserve_city_defenders: true
```

The deterministic priority order is:

1. Attack only a packet-visible unit at the advertised target.
2. Found a city only below the city target and at the declared minimum spacing.
3. Move a founder outward while expansion is incomplete.
4. Fill a grounded city-defense deficit and preserve the sole garrison.
5. Select one founder, defender, or growth/economy production per city without
   switching away from accumulated shields or a useful current production.
6. Explore with diplomats, spies, caravans, and explorers; non-garrison military
   units may advance toward visible opponents or the frontier.

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
action exists for the same actor, it can be selected immediately in the same turn.
The first alternative that produces an authoritative change closes that actor/city
scope for the rest of the turn.

Transport-accepted terminal actions close their actor scope immediately even if the
first refreshed packet has not caught up. This prevents a delayed city-founding or
suicide-attack effect from creating a stale follow-up action against an actor the
engine has already consumed.

## Impact telemetry

The harness now aggregates these paired metrics with the same bootstrap method as
the existing score and latency metrics:

- `planned_engine_actions` and `meaningful_actions_per_turn`;
- `decision_impact_actions` and `decision_impact_turn_rate`;
- `decision_effect_observed_rate` and `decision_no_effect_actions`;
- `decision_no_effect_retries_blocked` for exact actions rejected by grounded
  no-effect feedback;
- `decision_no_effect_failover_attempts`, `decision_no_effect_failover_recoveries`,
  and `decision_no_effect_failover_recovery_rate` for bounded same-turn recovery;
- `action_type_diversity`, `positions_explored`, and `tactical_actions`;
- `cities_founded`, `technologies_acquired`, `production_changes`, and `score_gain`;
- `model_safe_fallback_rate` and `model_corrections_per_turn`.

Transport acceptance and observed state effect are intentionally separate. An action
can be legal and accepted without changing the authoritative state; the report must
not count that distinction as proven gameplay value.

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

## Operational note

On the recorded CPU host, a cold load of `qwen3-coder-next:latest` took 41.6 seconds,
which exceeds the configured 28-second generation budget. Preload the model with a
long keep-alive before a timed release run, then verify `model_safe_fallback_rate=0`.
Cold-start failures remain valid fail-closed behavior and must not be silently removed
from benchmark artifacts.
