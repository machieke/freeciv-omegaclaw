# GDO-2 Grounded Movement and Combat Shadow Status

Status: partial implementation complete; native parity gate open
Policy effect: none; shadow-only and default-off
Implementation basis: `97ff07b` plus the changes documented here
Diagnostic artifact:
[`benchmarks/gdo/gdo2_shadow_diagnostic.json`](../../../benchmarks/gdo/gdo2_shadow_diagnostic.json)

## Implemented

- Movement and combat input-availability audits identify every current
  authoritative input, retained omission, and abstention boundary.
- Snapshot normalization retains map wrap flags and unit veteran, transport,
  carrier, cargo, and done-moving state. Numeric JSON visibility keys are
  normalized correctly.
- The immutable ruleset IR reaches domain-estimate requests.
- A candidate-invariant one-edge corridor contract records source,
  destination, visible-state classification, candidate next hop, and a stable
  digest.
- The movement shadow supports only an advertised, visible, adjacent edge with
  an explicit positive cost and explicit no-transport requirement. Everything
  else abstains with missing-field and reason-code evidence.
- An independently written, bounded finite-duel kernel conserves probability
  mass and reports terminal outcomes and expected material loss.
- The combat shadow accepts only an explicitly unmodified one-versus-one
  `unit_attack` context. Veteran modifiers, cities, effects, multiple
  defenders, bombardment, capture, transport state, and missing mechanics
  abstain.
- Both calculated movement and combat results remain `HEURISTIC` and
  non-live-eligible while parity is unverified.
- Model artifacts are emitted through the versioned event schema. Abstention
  events carry the actual missing-field list.
- `NativeGameplayOracle` defines a strict, identity-bound subprocess protocol.
  `scripts/run_gdo_gameplay_parity.py` deterministically compares a generated
  corpus and fails on any mismatch or an empty corpus.

## Test evidence

Focused model, oracle, event, and replay tests:

```text
PYTHONPATH=.:src:benchmarks pytest -q \
  Autotests/test_freeciv_grounded_movement.py \
  Autotests/test_freeciv_grounded_combat.py \
  Autotests/test_freeciv_native_gameplay_oracle.py \
  Autotests/test_freeciv_domain_estimate_shadow.py \
  Autotests/test_freeciv_events.py \
  Autotests/test_freeciv_gdo_replay.py

55 passed in 17.98s
```

The combat mechanics properties include 200 deterministic randomized cases,
material-loss bounds, edge damage, symmetry, probability-mass conservation,
and a terminal-distribution resource cap.

Complete FreeCiv regression:

```text
PYTHONPATH=.:src:benchmarks pytest -q Autotests/test_freeciv_*.py

841 passed in 328.24s
```

## 200-pair shadow diagnostic

Command:

```text
PYTHONPATH=.:src:benchmarks python3 scripts/run_gdo_replay.py \
  --iterations 200 \
  --warmup 20 \
  --output benchmarks/gdo/gdo2_shadow_diagnostic.json
```

Result:

| Measure | Result |
|---|---:|
| Candidates per batch | 34 |
| Candidate completion/coverage | 100% |
| Grounded movement rows | 31, all explicit abstentions |
| Legacy fallback rows | 3 |
| Action/order/schedule equality | byte-identical |
| Worker failures/capacity rejections | 0 / 0 |
| Baseline decision p95 | 12.695 ms |
| Shadow decision p95 | 12.214 ms |
| Paired decision-path p95 overhead | -3.786% |
| Shadow worker compute p95 | 21.119 ms |
| Shadow full-loop p95 | 33.483 ms |
| Full-loop p95 overhead | +163.747% |

The decision-path latency gate passes because observational work is dispatched
after the live artifact is materialized. The full-loop number remains
important: polling a completed observation is cheap, but computing 31
reason-coded abstentions is not free. This work remains off the authority path.

The replay fixture contains no combat candidate and lacks authoritative
movement edge costs and visible tile records. It therefore validates
fail-closed readout, determinism, coverage, and policy parity—not movement or
combat correctness.

## Open GDO-2 gates

GDO-2 is not complete and no gameplay or score claim is authorized:

1. No separately installed native movement/combat comparator is available.
2. No generated parity corpus with a reviewed engine and ruleset identity
   exists.
3. Roads, rails, terrain costs, zones of control, transport transitions,
   modifier-bearing combat, cities, capture, bombardment, and post-action risk
   remain unsupported.
4. Combat Brier score and log-loss baselines require engine-resolved outcomes.
5. Controller-inclusive latency must be measured again on a representative
   captured fixture set after those inputs exist.
6. Licensing reviewer sign-off remains pending.

Until those gates close, the correct behavior is explicit abstention or
heuristic shadow output. GDO-3 must not treat these estimates as approved
movement/combat authority.
