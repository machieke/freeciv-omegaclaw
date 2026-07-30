# GDO-4 city-defence shadow foundation

Date: 2026-07-30

Branch: `experimental/pln-pressure–bridge–fluid`

Authority: disabled; diagnostic shadow only

## Result

This checkpoint establishes the first bounded GDO-4 city-defence mechanism:

- visible-enemy-to-city threat records with explicit confidence and residual
  unknown mass;
- city response requirements with threat deadlines;
- defender profiles with effective defensive contribution and current-city
  opportunity cost;
- protected `HOLD_SOLE_DEFENDER` constraints;
- operations for fortifying, moving, intercepting, and emergency production;
- stable operation identity and actor, movement, and city-production claims;
- legal-candidate membership checks;
- late-arrival and late-production rejection;
- deterministic identity-aware greedy assignment;
- deterministic bounded-exact coverage-first assignment;
- default-off asynchronous execution inside the GDO-3 resource worker;
- exact fallback to the frozen B1 action path;
- versioned `operation_proposed` and `operation_step_selected` events;
- no policy authority and no change to live ordering.

The runtime flag is `pressure_city_defense_operations_enabled`. Startup rejects
this flag unless `pressure_resource_scheduler_enabled` is also active. Both
remain disabled by default.

## Synthetic B1/B3/B4 diagnostic

The retained report is
`benchmarks/gdo/gdo4_city_defense_diagnostic.json`.

The diagnostic enumerates all 64 subgraphs of a synthetic graph with three
defenders and two one-slot city requirements. It compares:

- `B1`: a deliberately limited one-action proxy for scalar PF-v2;
- `B3`: typed identity-aware greedy assignment;
- `B4`: typed bounded-exact assignment.

Across 128 possible threat slots:

| Arm | Covered | Uncovered | Uncovered-loss proxy |
| --- | ---: | ---: | ---: |
| B1 proxy | 63 | 65 | 6500 |
| B3 greedy | 105 | 23 | 2300 |
| B4 exact | 109 | 19 | 1900 |

The exact solver improved coverage in four graphs and improved objective value
at equal coverage in seven more. It matched an independent brute-force oracle
on all 64 graphs and never covered fewer slots than greedy. No arm produced an
actor conflict.

Synthetic timing over 6,400 schedules:

| Scheduler | p50 | p95 | p99 |
| --- | ---: | ---: | ---: |
| B3 greedy | 0.0034 ms | 0.0046 ms | 0.0057 ms |
| B4 exact | 0.0229 ms | 0.0407 ms | 0.0713 ms |

The report hash is
`f6105bcd3b054275124d11bdc519bf9df047e621d5063efba0f2a3ab471ed0cd`.

## Correctness and safety evidence

The focused tests cover:

- explicit threat confidence, unknown mass, and deadlines;
- sole-defender protection;
- legal-action fail-closed behavior;
- missing-ruleset abstention;
- late emergency-build exclusion;
- stable typed operation claims;
- input-permutation invariance;
- deterministic node-budget fallback;
- the known greedy coverage counterexample;
- exact agreement with brute force on every small graph;
- valid attributable operation events;
- byte-identical live action ordering with the feature enabled in shadow.

The complete FreeCiv regression command:

```text
python3 -m pytest -q Autotests/test_freeciv_*.py
```

Result: `886 passed in 328.20s`.

## Limits and unsatisfied GDO-4 gates

This is not a completed GDO-4 pilot and does not support a score or win-rate
claim.

The current threat and defender ETA is conservative visible-state geometry. It
does not yet have authoritative native path parity for terrain, zone of
control, transports, or future occupancy. Such cases must remain shadow-only
or abstain.

The repository still lacks a retained, diverse captured replay cohort with
immediate city threats and multiple cities competing for defenders. Therefore
the following exit gates remain unproven:

- lower uncovered threat-turns than real B1 on disjoint Freeciv replays;
- no increase in realized preventable city loss;
- positive operation-completion delta;
- at least 90% typed support for winner-changing defence comparisons;
- controller-inclusive latency on a representative defence corpus;
- exact B1 fallback on every unsupported engine state;
- a fresh bounded live pilot.

The next implementation step is to capture or construct engine-derived defence
replays, add grounded movement ETA/parity to assignment edges, resolve selected
operations at their threat deadline, and compute replay B1/B2/B3/B4 mechanism
metrics before considering any authority.

The first captured replay and its semantic hardening are documented in
`docs/evidence/gdo/gdo4_captured_replay_hardening.md`. That replay localized the
remaining blocker to grounded threat/defender ETA and representative earlier
warning states; it did not establish a B4 improvement over B1.

The next fresh 160-turn engine trace is documented in
`docs/evidence/gdo/gdo4_grounded_160_replay.md`. It closes candidate recall for
the retained defence requirements and shows a diagnostic one-action readout
delta versus B1, while leaving the movement-ETA and realized-outcome gates
closed.
