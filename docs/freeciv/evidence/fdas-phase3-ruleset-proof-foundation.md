# FDAS Phase 3 ruleset and proof foundation evidence

Status: passed, component-only

Date: 2026-08-01

Branch: `experimental/functional-dependent-atomspace`

## Claim boundary

FDAS now has a deterministic static ruleset/capability projection and a
bounded generic technology proof path. Both remain component-only. The
specialized dependency oracle remains authoritative; no goal, candidate,
pressure, policy, or execution path consumes this work.

## Implemented

- Ruleset IR 2.0 retains the existing rules and quantitative fields while
  adding typed requirement expressions, capabilities, exact ruleset effects,
  action schemas, grounding declarations, provenance, and coverage counters.
- The compiler covers technology, unit, building, game, government, terrain,
  action, and effect inputs. Included effect sources that cannot yet be
  compiled are source-hashed and exposed as unknown rather than guessed.
- Negative requirement expressions carry explicit completeness contracts.
- Every supported proxy action schema requires current legal binding. Its
  unavailable generic action outcome is represented by an explicit unknown
  effect with no exact grounding.
- The independent audit validates semantic references, provenance,
  completeness, legal-binding requirements, and coverage totals.
- Static ruleset atoms are typed, numeric-free, ruleset-exact, support-backed,
  compiler-provenanced, and valid only for their complete ruleset digest.
- The generic engine uses typed bindings, indexed conclusion lookup,
  deterministic proof/support hashes, bounded recursion/binding/rule-fire
  budgets, and an explicit `UNKNOWN` outcome on exhaustion.

## Civ2civ3 results

| Check | Result |
| --- | ---: |
| compatibility prerequisite rules | 216 |
| requirement expressions | 1,032 |
| capability bindings | 660 |
| exact ruleset effects | 495 |
| explicit unknown effects | 11 |
| action schemas | 11 |
| typed grounding declarations | 9 |
| final static atom records | 4,834 |
| final static supports | 5,245 |
| technology targets compared | 87 |
| empty-state status/closure parity | 87 / 87 |
| prerequisite-complete status/closure parity | 87 / 87 |
| ruleset audit | passed |
| cross-digest atom reuse | zero |
| policy authority | false |

The compiled IR and static projection are canonical across repeated builds.
Budget exhaustion is tested as `UNKNOWN` with an explicit truncation blocker,
not as false or unreachable.

## Performance

Measured on the local acceptance host over eight cold builds and fifty
all-technology proof passes:

| Measurement | Samples | Mean | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Ruleset IR compilation | 8 | 220.56 ms | 238.88 ms | 239.46 ms |
| Static ruleset projection | 8 | 3,215.31 ms | 3,271.48 ms | 3,283.47 ms |
| Proof of all 87 technologies | 50 | 145.63 ms | 149.08 ms | 154.84 ms |

The static compilation/projection cost occurs once per ruleset digest and is
outside ordinary-turn snapshot materialization. Ordinary-turn FDAS remains at
the Phase 2 measured 16.2 ms mean / 18.5 ms p95. Static projection latency is
recorded as an optimization target before this component is used on a live
startup path.

## Reproduction

```bash
export FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data
python3 -m pytest -q \
  Autotests/test_freeciv_fdas_ruleset.py \
  Autotests/test_freeciv_fdas_dependencies.py \
  Autotests/test_freeciv_fdas_core.py \
  Autotests/test_freeciv_fdas_phase0.py \
  Autotests/test_freeciv_state_bridge.py \
  Autotests/test_freeciv_rulesets.py \
  Autotests/test_freeciv_oracle.py \
  Autotests/test_freeciv_beliefs.py \
  Autotests/test_freeciv_planning.py \
  Autotests/test_freeciv_pressure.py \
  Autotests/test_freeciv_pressure_v2.py
python3 scripts/run_fdas_phase0_baseline.py --check --iterations 1
```

## Activation state

```text
ruleset_domain_projection = component-only
generic_rule_execution = component-only
specialized technology authority = unchanged
component_enabled = true
policy_authority = false
all city/unit/region/operation/pressure/episode capabilities = not-built
```
