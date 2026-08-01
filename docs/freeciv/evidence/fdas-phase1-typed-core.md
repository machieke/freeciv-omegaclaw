# FDAS Phase 1 typed core and compatibility evidence

Status: passed, component-only

Date: 2026-08-01

Branch: `experimental/functional-dependent-atomspace`

## Claim boundary

The typed FDAS core, full-build revision store, validation transaction, and
legacy compatibility facade are implemented. This phase changes no projected
semantics, candidate construction, ranking, action validation, or execution.
FDAS has no policy authority.

The dependency engine is not part of this claim. Reverse indexes, transitive
invalidation, incremental updates, generic derivations, scoped queries, and
coordinated snapshot replacement begin in Phase 2.

## Implemented contract

- ordinary atom terms are typed `EntityRef` or `SymbolRef` values; numeric
  arguments fail closed;
- all ten legacy predicates have registered arity, argument-kind, namespace,
  scope, completeness, export, and schema contracts;
- atom keys, direct projection supports, materialization keys, and revisions
  have deterministic length-delimited SHA-256 identities;
- every projected record carries an authority class, snapshot/turn/source
  validity, dependency fingerprint, witness, and provenance identity;
- deterministic world and empire scopes impose namespace and atom-count
  bounds;
- the transaction rejects unknown predicates, invalid arity/kinds,
  cross-namespace writes, invalid authority, unknown scopes, stale snapshot
  validity, collisions, and atom-budget violations before publication;
- revisions are immutable and become visible only after a complete successful
  commit; and
- `state.atoms.build_atomspaces()` returns the legacy view reconstructed from
  the committed typed revision.

## Compatibility and determinism results

| Metric | Result |
| --- | ---: |
| captured fixtures | 13 / 13 |
| typed projection records | 5,034 |
| legacy-view equality | 13 / 13 |
| frozen Phase 0 semantic hash reproduced | yes |
| repeated revision/build identity equality | 13 / 13 |
| invalid schema/namespace/kind/numeric cases rejected | yes |
| policy authority | false |

The unchanged frozen semantic report hash is:

```text
ef462b243f270363328db7004d14ab34eddc4a30832a1a3eb9aa9fb14f25ea84
```

## Captured-snapshot latency

After warming all fixtures, 20 passes over the 13-fixture cohort produced 260
measurements on the implementation host:

| Stage | Mean | p95 | Maximum |
| --- | ---: | ---: | ---: |
| frozen legacy projector | 0.448 ms | 0.401 ms | 10.301 ms |
| typed full build and legacy readout | 21.083 ms | 29.823 ms | 32.556 ms |
| measured FDAS delta | 20.635 ms | 29.423 ms | — |

The legacy maximum is a single scheduler outlier; percentile results are used
for the plan gate. The typed full-build p95 is below the initial 30 ms target
for snapshot delta and base projection. Incremental-update latency is not yet
claimed.

## Reproduction

```bash
python3 scripts/run_fdas_phase0_baseline.py --check --iterations 1
pytest -q \
  Autotests/test_freeciv_fdas_core.py \
  Autotests/test_freeciv_fdas_phase0.py \
  Autotests/test_freeciv_state_bridge.py \
  Autotests/test_freeciv_rulesets.py \
  Autotests/test_freeciv_beliefs.py \
  Autotests/test_freeciv_planning.py \
  Autotests/test_freeciv_pressure.py \
  Autotests/test_freeciv_pressure_v2.py
```

## Activation state

`profile/fdas_manifest.json` enables only the compatibility component:

```text
dependent_atomspace_core = component-only
component_enabled = true
policy_authority = false
all later capabilities = not-built
```
