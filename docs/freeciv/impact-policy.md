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

One unit-scoped strategic action and one production change per city are allowed per
turn. A successful fortification is not reissued on every later turn. These bounds
prevent stale proxy action lists or effect-free orders from consuming the action
budget.

## Impact telemetry

The harness now aggregates these paired metrics with the same bootstrap method as
the existing score and latency metrics:

- `planned_engine_actions` and `meaningful_actions_per_turn`;
- `decision_impact_actions` and `decision_impact_turn_rate`;
- `decision_effect_observed_rate` and `decision_no_effect_actions`;
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

This is a development smoke, not evidence of a statistically reliable score or win
improvement. The next release comparison must rerun paired seeds for every condition;
100 paired seeds is the recommended first power-estimation run before choosing the
final sample size from the observed effect.

## Operational note

On the recorded CPU host, a cold load of `qwen3-coder-next:latest` took 41.6 seconds,
which exceeds the configured 28-second generation budget. Preload the model with a
long keep-alive before a timed release run, then verify `model_safe_fallback_rate=0`.
Cold-start failures remain valid fail-closed behavior and must not be silently removed
from benchmark artifacts.
