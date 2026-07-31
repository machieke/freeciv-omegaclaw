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

## Pilot v1 result

The complete frozen pilot
`/data/freeciv/gdo4-city-defense-operation-authority-pilot-v1` did **not**
pass its mechanism gate:

- 60/60 games and 30/30 pairs completed with zero infrastructure failures;
- source commit `eb848707cbe1df44600e15fae2dfb3d68b994710` remained clean;
- 1,696,020 events validated with zero errors and zero warnings;
- treatment activated 260 operations: 206 defender moves and 54 in-place
  fortifications;
- completion per selected unique operation improved by 12.48 percentage
  points;
- raw own-city identity losses increased from 20 to 27;
- preparation p95 was 149.02 ms, above the frozen 50 ms ceiling;
- full-loop p95 ratio was 1.1129 and remained below the 1.15 ceiling;
- the paired score delta was -4.9 with interval `[-10.0333, 0.3]`.

The self-hashed pilot audit is
`benchmarks/gdo/gdo4_city_defense_engine_pilot.json`, report hash
`e56a3a43e43322139a87eb24f8b676553ed0f87992981df9bf3fd8a279889d86`.

The original observation counter also counted two
`operation_step_selected` events for some one-snapshot selections: one from
synchronous preparation and one from the policy-selection event. On unique
`(snapshot_id, target_city_id)` observations, uncovered responses were 567
for baseline and 330 for treatment. This correction is diagnostic only and
does not retroactively pass pilot v1.

The new selected-at-risk loss diagnostic identified 4 baseline and 6
treatment city disappearances by the applicable response deadline. It agrees
with the adverse direction of the original conservative 20-versus-27 raw
city-loss gate.

The two `operation_failed` events were accepted legal actions whose later
participants or city targets disappeared. They are adverse lifecycle
outcomes, not engine legality rejections. The engine rejection gate itself
passed with zero rejected actions in both arms.

The substantive failure remains. The move readout used threat priority times
defensive strength while charging only ten percent of a defender's local
strength as opportunity cost. It therefore granted 206 move activations
without calibrated transition value for the source city's economy, attack
role, or later defensive exposure. Faster routing would amplify that error.

## Frozen corrective pilot v2

`city_defense_immediate_fortify_authority_pilot_v2` is predeclared on 30
unused paired seeds in the disjoint 6.8M range. It makes one narrow,
decision-safe change:

- live authority is limited to `fortify_existing_defender`;
- defender moves remain fully observable in asynchronous shadow analysis but
  cannot alter the live winner;
- only a deadline at most one turn away is eligible;
- a defender with a currently legal interception against the supported city
  threat falls back to exact B1 instead of being forced to fortify;
- synchronous analysis builds only fortify and protected-hold operations and
  emits only the selected proposal plus hold constraints;
- build, event-emission, total preparation, and full-loop latency remain
  separately observable.

Schema 1.1 freezes two measurement corrections before execution:

- uncovered response opportunities are unique selected
  `(snapshot_id, target_city_id)` observations minus unique activations;
- the primary safety loss is disappearance, by the response deadline, of a
  city identified by a supported selected at-risk response. Raw city identity
  loss remains a diagnostic.

Lifecycle failure is reported separately from actual engine action rejection.
The v2 pilot still requires every GDO-4 exit gate and remains ineligible for a
score or win-rate claim.

## Corrective pilot v2 result

The frozen v2 cohort
`/data/freeciv/gdo4-city-defense-immediate-fortify-authority-pilot-v2`
completed 60/60 games and 30/30 pairs from clean source commit
`de4a1da92bf665f1369b7f3c9dc7447292cfd6a2`, with zero game or
infrastructure failures. The audit validated 1,819,644 events with zero errors
and zero warnings.

The self-hashed report is
`benchmarks/gdo/gdo4_city_defense_immediate_fortify_engine_pilot.json`,
report hash
`2268b6c03b5f41680eca0a9e5275fbcd7e0f31727298a7e51c0baec16bcc6add`.

The conservative policy passed every non-latency mechanism gate:

| Metric | B1 baseline | Fortify authority | Delta |
| --- | ---: | ---: | ---: |
| Unique selected city/snapshot observations | 471 | 34 | — |
| Unique activations | 0 | 23 | — |
| Uncovered unique observations | 471 | 11 | −460 |
| Completion / selected unique operation | 0% | 2.94% | +2.94 pp |
| Selected-at-risk city losses | 4 | 0 | −4 |
| Raw own-city identity losses | 42 | 39 | −3 |
| Hard-current conflicts | 0 | 0 | 0 |
| Sole-defender violations | 0 | 0 | 0 |
| Engine-rejected actions | 0 | 0 | 0 |

All 23 authority activations were declared
`fortify_existing_defender` operations issuing `unit_fortify`. Typed coverage
for winner-changing selections was 100%; unsupported states retained B1.
Controller-inclusive full-loop p95 ratio was 1.0688, below 1.15.

The pilot nevertheless failed its conjunction because synchronous preparation
p95 was 132.69 ms, above the frozen 50 ms ceiling. Phase metrics localize the
cost:

- terrain/operation build p95: 99.16 ms;
- selected/hold event emission p95: 12.08 ms;
- total preparation p95: 132.69 ms.

The paired score delta was -2.1 with interval `[-7.4, 3.4]`. The cohort was
predeclared claim-ineligible, and no score or win-rate claim is made.

## Frozen latency confirmation v3

RCA found that `_known_native_corridor` rebuilt the complete known/native
terrain index for every visible enemy–city edge even though the projection is
invariant within a snapshot and unit class. The correction caches that
projection once per snapshot/class and leaves corridor search, threat support,
assignment, authority scope, and all gate thresholds unchanged.

On a dense deterministic 400-edge synthetic graph, mean analyzer time changed
from 961.16 ms to 78.00 ms, a 12.32× speedup. This is a performance diagnostic,
not engine evidence.

`city_defense_immediate_fortify_authority_pilot_v3` freezes an otherwise
identical 30-pair pilot on unused seeds in the disjoint 6.9M range. It must
pass the same complete gate conjunction, including 50 ms synchronous
preparation p95 and 1.15 full-loop p95 ratio. It remains ineligible for a score
claim regardless of outcome direction.

## Latency confirmation v3 result

The frozen v3 cohort
`/data/freeciv/gdo4-city-defense-immediate-fortify-authority-pilot-v3`
completed 60/60 games and 30/30 pairs from clean source commit
`330f346417ae0bef529a0a8461b5770e9507e83f`, with zero game or
infrastructure failures. The audit validated 1,820,989 events with zero errors
and zero warnings.

The self-hashed report is
`benchmarks/gdo/gdo4_city_defense_immediate_fortify_latency_confirmation.json`,
report hash
`35b410b028c533a91a268bb324a446e347853a4f5a398e09e7c210c6b3c697c6`.

The cohort again failed the complete conjunction:

| Metric | B1 baseline | Fortify authority | Delta |
| --- | ---: | ---: | ---: |
| Unique selected city/snapshot observations | 485 | 66 | — |
| Unique activations | 0 | 39 | — |
| Uncovered unique observations | 485 | 27 | −458 |
| Completion / selected unique operation | 0% | 0% | 0 pp |
| Selected-at-risk city losses | 2 | 0 | −2 |
| Raw own-city identity losses | 30 | 25 | −5 |
| Hard-current conflicts | 0 | 0 | 0 |
| Sole-defender violations | 0 | 0 | 0 |
| Engine-rejected actions | 0 | 0 | 0 |

All authority actions remained fortifications, typed winner-changing coverage
was 100%, and full-loop p95 ratio was 1.0319. Preparation p95 was still
137.63 ms: build p95 was 103.50 ms and event-emission p95 was 12.82 ms.
The terrain cache therefore improved a synthetic dense graph but did not
remove the production bottleneck. The paired score delta was -0.23 with
interval `[-4.43, 3.67]`; no score or win-rate claim is made.

Production traces exposed two independent measurement and performance
defects:

- high-latency snapshots had up to 551 advertised legal actions, while the
  synchronous policy slice needed only fortification plus immediate
  interception actions; irrelevant candidates and JSON actions were still
  analyzed;
- accepted Freeciv fortify commands appeared in authoritative state as
  `fortifying`, while lifecycle resolution recognized only `fortify` and
  `fortified`, making successful command effects look incomplete.

## Frozen action-scope and lifecycle confirmation v4

`city_defense_immediate_fortify_authority_pilot_v4` is predeclared on 30
unused paired seeds in the disjoint 7.0M range. The policy and all original
gate thresholds remain unchanged. The implementation only:

- filters synchronous candidates and legal-action decoding to declared
  fortification actions plus the attack actions required by the conservative
  immediate-interception fallback;
- retains the complete advertised legal-action digest and membership set for
  exact commit validation;
- reports both input and actually analyzed candidate counts;
- recognizes the authoritative `fortifying` activity as the observed effect
  of an accepted fortify step.

On a deterministic 501-action diagnostic, narrowed analyzer p95 changed from
9.18 ms to 0.85 ms, a 10.81× speedup, while reducing analyzed candidates from
501 to one. This is synthetic performance evidence only. V4 must still pass
the complete 50 ms preparation, 1.15 full-loop, completion, safety, coverage,
and fallback conjunction. It remains claim-ineligible regardless of gameplay
score direction.
