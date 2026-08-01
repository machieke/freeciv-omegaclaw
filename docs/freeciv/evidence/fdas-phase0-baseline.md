# FDAS Phase 0 contract and baseline

Status: passed

Date: 2026-08-01

Branch: `experimental/functional-dependent-atomspace`

## Claim boundary

This is a behavior-invariant migration baseline. It establishes the semantic
contract, current projection/proof/candidate oracles, versioned catalogs, and
an explicit `not-built` capability declaration. It implements no dependent
store, changes no live candidate ordering, and grants no FDAS authority.

## Frozen source

The baseline uses all 13 retained, player-visible fixtures from
`city_defense_grounded_160_manifest.json`. Fixture canonical hashes are
revalidated before projection. The diagnostic records:

- all canonical legacy `build_atomspaces()` outputs;
- all 95 captured candidates and their historical source selections;
- current technology proof status, proof hash, frontier, and prerequisites;
- a reconstructed default scalar-v1 adapter graph and selection;
- legacy predicate, grounding, operation, resource, and event inventories; and
- volatile projection/adapter timing outside the semantic report hash.

## Result

| Metric | Result |
| --- | ---: |
| fixtures | 13 |
| captured candidates | 95 |
| canonical projected atoms across fixtures | 5,034 |
| projected atoms/fixture | 360–436 |
| legacy authoritative predicates | 9 |
| legacy visible predicates | 1 |
| legacy uncertain atoms | 0 |
| legacy grounded signatures | 9 |
| technology proofs reproduced | 13 / 13 |
| historical/current-default selection agreement | 10 / 13 |

All technology targets were currently researchable in their captured states,
so the existing oracle returned `PROVED` with no missing prerequisites in all
13 fixtures.

The three adapter-selection mismatches are retained rather than normalized.
The captures came from an earlier source/configuration context, while the
reconstruction deliberately uses the current default scalar-v1 adapter and a
minimal player-visible projection. This is baseline drift evidence, not an
FDAS result. Future differential reports must compare both the frozen
historical choice and the immediately preceding live comparator so ordinary
code/configuration drift is not attributed to FDAS.

The initial local measurements recorded a legacy projection mean of 0.367 ms
and maximum of 0.640 ms over three iterations per fixture. These numbers are
diagnostic and excluded from the canonical semantic hash.

## Acceptance

- the plan and materialized-view ADR are present;
- legacy predicate and grounding catalogs match the current code exactly;
- all FDAS manifest capabilities are `not-built`;
- the component and policy authority switches are false;
- the generator reproduces the canonical semantic hash;
- legacy quantitative values remain excluded from ordinary atoms;
- current state-bridge behavior remains unchanged; and
- 158 affected state, ruleset, belief, planning, and pressure tests pass.

## Reproduction

```bash
python3 scripts/run_fdas_phase0_baseline.py --iterations 3
python3 scripts/run_fdas_phase0_baseline.py --check --iterations 1
pytest -q \
  Autotests/test_freeciv_fdas_phase0.py \
  Autotests/test_freeciv_state_bridge.py \
  Autotests/test_freeciv_rulesets.py \
  Autotests/test_freeciv_beliefs.py \
  Autotests/test_freeciv_planning.py \
  Autotests/test_freeciv_pressure.py \
  Autotests/test_freeciv_pressure_v2.py
```

## Canonical Phase 0 hashes

These hashes identify the files as committed at the Phase 0 boundary. The
live capability manifest advances in later phases while the semantic baseline
and its report hash remain frozen.

```text
semantic report hash:
ef462b243f270363328db7004d14ab34eddc4a30832a1a3eb9aa9fb14f25ea84

baseline file SHA-256:
433fdc328d1a2aef25a27ed39ac15f930f9d3b66502a3aec76a3254cf0e121e5

catalog file SHA-256:
804bf279ee437591c180838afcc03579fc0cbed7b90c023f7bb75df83032e525

manifest file SHA-256:
4294d9bf0e7ea488233edaaa267a5931a0fb237975407f46bbe4f34cd87e1f82
```
