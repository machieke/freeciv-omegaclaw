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

## Action-scope and lifecycle confirmation v4 result

The frozen v4 cohort
`/data/freeciv/gdo4-city-defense-immediate-fortify-authority-pilot-v4`
completed 60/60 games and 30/30 pairs from clean source commit
`b63e9a25474c9b6a6eea52638c61d282c96f10cd`, with zero failures,
zero resumes, and stable implementation hash
`9ded4f533e32d3e0e3b997df205effdb5b7a3c8ce0b4a727f9c9a67bc3c15153`.
The audit validated 1,646,250 events with zero errors and zero warnings.

The self-hashed report is
`benchmarks/gdo/gdo4_city_defense_immediate_fortify_action_scope_confirmation.json`,
report hash
`d75dfb9174be76e2f4dd0ff33dc348cc49e185ec7880d1bca6b26fbcd1769443`.

V4 corrected the lifecycle defect and passed every gate except the absolute
preparation-latency ceiling:

| Metric | B1 baseline | Fortify authority | Delta |
| --- | ---: | ---: | ---: |
| Unique selected city/snapshot observations | 502 | 46 | — |
| Unique activations | 0 | 33 | — |
| Uncovered unique observations | 502 | 13 | −489 |
| Completion / selected unique operation | 0% | 71.74% | +71.74 pp |
| Selected-at-risk city losses | 2 | 0 | −2 |
| Raw own-city identity losses | 45 | 40 | −5 |
| Hard-current conflicts | 0 | 0 | 0 |
| Sole-defender violations | 0 | 0 | 0 |
| Engine-rejected actions | 0 | 0 | 0 |

All 33 activated operations completed from the authoritative fortifying
effect, with zero adverse activated outcomes. Typed winner-changing coverage
was 100%; unsupported states had zero authority. Full-loop p95 ratio was
1.0456, below 1.15.

Preparation p95 remained 120.90 ms, with build p95 85.74 ms and event p95
12.04 ms. The generic, claim-ineligible score delta was directionally positive
at +1.97 with interval `[-1.37, 5.73]`, with one treatment-only win, but no
score or win-rate claim is made. Because the 50 ms gate failed, live policy
authority remains ineligible.

Production RCA linked the remaining build tail to snapshots with more than
500 advertised legal actions. The bounded fortify slice still retained every
attack, capture, and conquer variant as an operation candidate solely to
derive a boolean immediate-interception guard. An exact retained 577-action
snapshot with no visible enemy analyzed 298 such candidates even though no
city-defence requirement or authority was possible. Across v4, 2,689 of 9,741
treatment preparations had no visible enemy; their build p95 was 92.25 ms.

## Frozen visible-threat and legal-context confirmation v5

`city_defense_immediate_fortify_authority_pilot_v5` is predeclared on 30
unused paired seeds in the disjoint 7.1M range. Policy scope, lifecycle
semantics, start state, worker count, and every gate threshold remain
unchanged. The correction only:

- returns the exact no-authority artifact before legal-action decoding when
  the fortify-only slice has no player-visible enemy;
- keeps attack actions as legal context for the immediate-interception guard,
  but does not canonicalize or assemble them as fortification candidates;
- derives interception legality directly from the advertised legal-action
  context;
- reuses already resolved own-unit ruleset specifications when building
  defender profiles.

On exact retained production snapshots, end-to-end assignment-artifact p95
was 0.08 ms for the 577-action/no-enemy state and 4.57 ms for a
478-action/one-enemy state; the latter retained the exact B1 interception
fallback. This is replay performance evidence only. V5 must pass the same
complete mechanism, safety, coverage, fallback, 50 ms preparation, and 1.15
full-loop conjunction. It remains claim-ineligible regardless of score
direction.

## Visible-threat and legal-context confirmation v5 result

The frozen v5 cohort
`/data/freeciv/gdo4-city-defense-immediate-fortify-authority-pilot-v5`
completed 60/60 games and 30/30 pairs from clean source commit
`19e29426eec549df7ec811291c80540164a4160e`, with zero failures,
zero resumes, stable implementation hash
`a2d4a05adb0a260a99a4e8350adc589be5970d666d1d75b2089e9c6b41157a2e`,
and configuration hash
`e8c108760c628bd768e4965323a9e95378a0a7909f867fec456dec9a7e5a2981`.
The independent audit validated 1,871,906 events with zero errors and zero
warnings.

The self-hashed report is
`benchmarks/gdo/gdo4_city_defense_immediate_fortify_visible_threat_confirmation.json`,
report hash
`d93b852125277d7c6224b1231a958d810f245e1b4e4b8c43109ee07d1012f922`.

V5 passed every mechanism, authority, safety, coverage, source-freeze, trace,
and full-loop-ratio requirement, but again failed the absolute 50 ms
preparation ceiling:

| Metric | B1 baseline | Fortify authority | Delta |
| --- | ---: | ---: | ---: |
| Selected unique operations | 269 | 47 | — |
| Unique activations | 2 | 28 | +26 |
| Uncovered unique observations | 472 | 19 | −453 |
| Completion / selected unique operation | 0% | 59.57% | +59.57 pp |
| Selected-at-risk city losses | 4 | 1 | −3 |
| Raw own-city identity losses | 31 | 26 | −5 |
| Hard-current conflicts | 0 | 0 | 0 |
| Sole-defender violations | 0 | 0 | 0 |
| Engine-rejected actions | 0 | 0 | 0 |

All 28 activated authority operations completed, with zero adverse activated
outcomes. Typed winner-changing coverage was 100%; unsupported states had
zero authority. Treatment full-loop p95 was 10,158.11 ms versus 10,185.75 ms
for baseline, a ratio of 0.9973.

Preparation p95 improved from v4's 120.90 ms to 83.30 ms but remained above
50 ms. Across all 9,356 treatment preparations:

| Phase | p50 | p95 | p99 |
| --- | ---: | ---: | ---: |
| Assignment-artifact build | 5.76 ms | 45.48 ms | 79.75 ms |
| Lifecycle event emission | 0.18 ms | 10.39 ms | 30.41 ms |
| Post-phase preparation overhead | 3.99 ms | 39.53 ms | 73.12 ms |
| Total preparation | 13.41 ms | 83.20 ms | 144.49 ms |

Of 1,289 preparations above 50 ms, 854 had more than 20 ms of post-phase
overhead. The high-latency rows had median build, event, and post-phase costs
of 35.16, 5.43, and 27.34 ms respectively. The controller workers execute as
Python threads in one process, so unrelated planner and telemetry work can
hold the GIL while the wall-clock preparation timer continues.

The cohort's natural worker-bucket exhaustion supplied an attributable
concurrency diagnostic. The final treatment game ran after the other two
worker buckets had ended and recorded preparation p95 9.23 ms, build p95
8.67 ms, post-phase p95 0.48 ms, and zero samples above 50 ms. The immediately
preceding treatment game, partly overlapping other workers, recorded
preparation p95 34.94 ms. This agrees with exact replay timings and isolates
the remaining production tail to controller-process contention rather than
city-defence semantics.

The generic, claim-ineligible paired score delta was again directionally
positive at +1.93 with interval `[-1.33, 5.93]`; fixed-horizon win-rate
difference was 0.00 with interval `[-0.10, 0.10]`. No score or win-rate claim
is made. Because the complete GDO-4 conjunction still failed, live authority
remains ineligible.

## Frozen process-isolation confirmation v6

V5 demonstrated that the bounded city-defence artifact is fast when it owns a
Python process, but its wall-clock preparation tail is inflated when three
controller games share one interpreter and contend for the GIL. This is an
evaluation/runtime isolation defect: each engine already has a dedicated
server port, while controller computation was still multiplexed through
threads.

`city_defense_immediate_fortify_authority_pilot_v6` freezes process-per-worker
controller execution on 30 unused paired seeds in the disjoint 7.2M range.
Both arms use the same three isolated processes, deterministic pair-to-worker
assignment, serial arm order within a pair, dedicated engine ports, and
cross-process model-readiness locking. Existing cohorts retain threaded
execution by default.

The policy, city-defence analyzer, candidate scope, lifecycle, start state,
worker count, and every mechanism and latency threshold are unchanged. V6
must still pass the full conjunction, including 50 ms preparation p95 and
1.15 treatment/baseline full-loop p95 ratio. It remains claim-ineligible
regardless of score direction.

The completed v6 audit is
`benchmarks/gdo/gdo4_city_defense_immediate_fortify_process_isolation_confirmation.json`
with self-hash
`65b3f0c005e3bd971e1826ab246d7d86ce416195fa587f4df5624aef40fd2fa2`.
It contains 30/30 complete pairs, 1,783,128 schema-valid events, zero event
errors or warnings, exact source identity
`e605f9fb5a2e439304f2332c0424e1b7cae26f4e`, and passes the complete
predeclared pilot gate.

Process isolation removed the preparation-latency failure decisively:
treatment preparation p95 fell from 83.30 ms in v5 to 8.76 ms in v6, with
p50 3.30 ms over 9,583 samples. Treatment/baseline full-loop p95 was
3,082.25/3,082.92 ms, a ratio of 0.9998 against the 1.15 ceiling. Typed
winner-changing coverage remained 100%, and unsupported states received zero
policy authority.

The mechanism result also passed. Treatment activated and completed 22 of 36
unique selected operations, while baseline completed none. Unique uncovered
city/snapshot observations fell from 403 to 14, a delta of -389. Selected
at-risk city losses fell from two to zero; raw city losses were unchanged at
25 per arm. There were no legality, hard-reservation, or sole-defender
violations.

The first execution pass recorded five observer-global-state timeouts. A
later trace-level audit corrected the initial startup hypothesis: every failed
attempt contains complete gameplay through turn 160 and stops after the final
turn metric, before `run_completed`. The failure is therefore in final score
readout, not server startup. The engine was configured to stop at turn 160
while the non-terminal fixed-horizon readout required observer turn 161. The
server exposes that post-horizon revision intermittently at the max-turn
boundary. All five failed attempts were archived, and an exact-source resume
completed the cohort 60/60 with zero current infrastructure failures.

The generic paired score delta was -2.27 with interval `[-5.40, 0.60]`;
fixed-horizon win-rate difference was 0.00. The cohort was predeclared
claim-ineligible, so neither gameplay endpoint supports a score or win-rate
claim. The supported conclusion is the bounded city-defence mechanism and
safety result, not a general game-score improvement.

## Frozen hard-recycle confirmation v7

`city_defense_immediate_fortify_authority_pilot_v7` is the fresh operational
confirmation of the passing v6 mechanism. It retains the v6 controller,
policy, start state, three process-isolated workers, 160-turn horizon, and all
mechanism, safety, coverage, and latency thresholds. Its 30 paired seeds are
derived from the unused disjoint 7.3M range.

The only runtime change is predeclared
`server_recycle_mode: hard_per_arm`. Every arm must kill the currently
listening civserver process and observe a different listening PID before
connecting; no process-local clean-successor shortcut is permitted. The mode
is part of behavioral manifest identity, is emitted in engine results, and is
bound to city-defence mechanism design schema 1.5. Invalid modes and a schema
that does not bind hard recycling to process isolation fail configuration
validation.

V7 is successful only if the initial, no-resume pass completes 60/60 with
zero infrastructure failures and the same full GDO-4 conjunction passes.
Like v6, it is claim-ineligible regardless of score direction.

V7 completed 59/60 arms and 29 complete pairs on its initial source-frozen
pass. All 59 successful arms reported `hard_per_arm` and
`kill-then-listener`, proving that successor reuse was eliminated. The single
failed arm, baseline seed 7332356, again contains complete gameplay through
turn 160 and failed only while waiting for observer turn 161. Hard recycling
therefore excludes server reuse as the cause but does not correct the
post-horizon readout contract. V7 is retained as a negative operational
diagnostic and is not audited as a passing pilot.

## Frozen finalization-turn confirmation v8

`city_defense_immediate_fortify_authority_pilot_v8` retains the v7 controller,
policy, hard-per-arm server isolation, start state, 160-turn decision horizon,
worker count, and all mechanism and latency thresholds. It uses 30 fresh
paired seeds from the disjoint 7.4M range.

The only new behavior is predeclared `engine_finalization_turns: 1`. The agent
still takes exactly 160 decision turns, but the civserver maximum is 161 so
the existing final score query always has a legal post-horizon revision to
observe. This preserves one score semantic across arms; it does not mix
turn-160 fallback scores with turn-161 scores. The finalization window is part
of manifest identity and is bound to city-defence mechanism design schema
1.6.

V8 is successful only if its initial pass completes 60/60 with zero
infrastructure failures, every manifest proves `engine_max_turns ==
turn_limit + 1`, and the complete GDO-4 pilot conjunction passes. It remains
claim-ineligible regardless of score direction.
