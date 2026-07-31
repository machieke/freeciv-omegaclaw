# GDO-4 city-defense engine diagnostic

Date: 2026-07-31

Branch: `experimental/pln-pressure–bridge–fluid`

Authority: bounded city-defense operation authority in the treatment arm only

Claim status: diagnostic mechanism evidence; no pilot, score, or win-rate
claim

## Retained cohort

The retained output
`/data/freeciv/gdo4-city-defense-operation-authority-scenario-diagnostic-v3`
contains three completed pairs from
`city_defense_operation_authority_scenario_diagnostic_v2`.

- 160-turn `civ2civ3` high-contact scenario;
- baseline and treatment differed only in
  `pressure_city_defense_operation_authority_enabled`;
- source commit
  `1a27d9cb73418fa5dfb5157b1c4e0ed2d372b394`;
- 6/6 arms and 3/3 pairs completed;
- zero game or infrastructure failures;
- paired initial-state fidelity and generic safety gates passed;
- 296,016 events validated with zero errors and zero warnings.

The self-hashed repository audit is
`benchmarks/gdo/gdo4_city_defense_engine_diagnostic.json`, report hash
`f3878194bb4382343b31e6159683785575bd5cf6f13b788f15c448721916b431`.

## Measurement boundary

An uncovered threat-turn is measured as a selected current defense-response
step observation that did not activate. Concretely, the count is
`operation_step_selected` observations minus `operation_activated`
observations. The unit is a response opportunity at an authoritative
snapshot, not a unique operation identity.

City loss is deliberately conservative: an own-city identity present in one
authoritative state snapshot and absent in the next counts as a loss. The
audit does not infer a counterfactual cause.

A sole-defender violation requires all of the following in one exact
snapshot:

1. the actor is marked by `hold_sole_defender` or
   `protected-sole-defender`;
2. a bounded-authority operation activates for that actor;
3. the activated legal action is `unit_move`.

## Result

| Metric | B1 baseline | City-defense authority | Delta |
| --- | ---: | ---: | ---: |
| Selected response observations | 97 | 128 | — |
| Activated response observations | 0 | 41 | — |
| Uncovered threat-turns | 97 | 87 | −10 |
| Selected unique operations | 38 | 70 | — |
| Completion / selection | 0% | 11.43% | +11.43 pp |
| Observed own-city losses | 0 | 0 | 0 |
| Hard-current conflicts | 0 | 0 | 0 |
| Sole-defender violations | 0 | 0 | 0 |
| Winner-changing typed coverage | no authority | 15 / 15 | 100% |

All 41 treatment activations were declared city-defense operations:

- 33 `move_defender_to_city` operations issuing `unit_move`;
- 8 `fortify_existing_defender` operations issuing `unit_fortify`.

No unsupported proposal received policy authority. The baseline had no
operation activation and every unsupported state retained the ordinary B1
decision path.

## Timing

Controller-inclusive `turn_full_loop_latency_ms` p95 was:

- B1 baseline: 11,659.07 ms;
- city-defense authority: 12,390.78 ms;
- treatment/baseline ratio: 1.0628.

The observed increase is 6.28%, below the 15% bound later frozen for the
pilot. This old cohort did not emit a slice-only synchronous preparation
latency, so it cannot pass the new 50 ms slice gate retroactively.

## Gameplay boundary

The three-pair score estimate was exactly zero with paired interval
`[-1, +1]`. This sample is too small and was predeclared diagnostic-only.
The evidence supports a mechanism direction—more grounded defense responses
executed and completed with no observed safety regression—not a gameplay
claim.

## Fresh pilot predeclaration

`city_defense_operation_authority_pilot_v1` is frozen before execution:

- 30 paired seeds in the disjoint 6.6M range;
- the same isolated 160-turn scenario and authority flag;
- authority limited to `fortify_existing_defender` and
  `move_defender_to_city`;
- lower uncovered threat-turns than B1;
- no increase in observed own-city loss;
- zero legality, hard-current conflict, and sole-defender violations;
- positive completion-rate delta;
- synchronous city-defense preparation p95 at most 50 ms;
- controller-inclusive full-loop p95 ratio at most 1.15;
- at least 90% typed coverage for winner-changing selections;
- unsupported states retain exact B1 ordering.

The cohort remains ineligible for a score claim regardless of score direction.
