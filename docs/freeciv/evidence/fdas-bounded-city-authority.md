# FDAS bounded city-stability authority

Date: 2026-08-02  
Branch: `experimental/functional-dependent-atomspace`  
Machine-readable evidence:

- `fdas-bounded-city-authority-replay.json`;
- `fdas-bounded-city-authority-engine-live.json`.

## Realized boundary

This increment realizes PR 13's first default-off authority seam without
claiming a new gameplay policy. The selected slice is city food stability,
because the proxy has an exact, packet-backed city-governor control contract.
Production-queue authority remains disabled: current FDAS production
continuity semantics do not yet establish that an arbitrary queue change
relieves a shield-throughput deficit.

The authority path is deliberately a pass-through:

1. the legacy controller selects a current `city_governor` action;
2. FDAS must bind that byte-identical action to a current
   `city-food-deficit` route;
3. the action must request a bounded food-surplus reserve, the complete
   governor state must be present, and the current food surplus must remain
   below that reserve;
4. a new one-candidate FDAS pressure readout must select the exact route;
5. the resource scheduler must reserve the city-worker assignment identity;
6. whole action and CPU packets must commit together;
7. `FDASCommitValidator` must revalidate the snapshot, legal-action digest,
   FDAS revision/build identity, exact supports, candidate identity, legal
   membership, causal firewall, and domain authority;
8. the existing `ExecutionGate` remains downstream and is the only component
   allowed to submit the action.

If any check fails, the readout emits a named fallback and the unchanged
legacy action path continues. FDAS cannot change the winner in this slice.

## Activation and rollback

The repository defaults remain unchanged and non-authoritative:

- `profile/dependent_atomspace.yaml` keeps the component disabled and all
  domain-authority flags false;
- `profile/fdas_manifest.json` remains `component-only` with policy authority
  false.

The bounded slice requires both explicit declarations:

- `profile/dependent_atomspace_city_stability_authority.yaml`;
- `profile/fdas_manifest_city_stability_authority.json`.

The harness accepts separate `FREECIV_FDAS_CONFIG_PATH` and
`FREECIV_FDAS_MANIFEST_PATH` overrides. Removing those overrides immediately
returns to the checked default legacy path; changing only one side fails
manifest validation rather than guessing.

## Captured replay

The acceptance runner verified the frozen capture corpus twice:

```bash
FREECIV_RULESET_ROOT=/path/to/freeciv/data \
python3 scripts/freeciv/run_fdas_bounded_authority_replay.py \
  --output docs/freeciv/evidence/fdas-bounded-city-authority-replay.json
```

Results:

| Measure | Result |
|---|---:|
| Unique captures / replayable captures | 47 / 38 |
| Explicit historical data gaps | 9 |
| Authorized pass-through actions | 4 |
| Explicit legacy fallbacks | 34 |
| Policy winner changes | 0 |
| Replay failures | 0 |
| Authority readout p50 / p95 | 0.046 / 1.585 ms |

All eleven acceptance gates passed. The two complete runs produced identical
semantic readouts. Every authorized action matched the legacy winner exactly,
was selected by the bounded authority pressure readout, received complete
resource/packet allocation, and passed exact FDAS commit validation. Every
commit record retained `execution_authority: false`, proving that the final
execution gate remains downstream.

The report hash is
`8e41a7db3dc9f8dee0483929c350069cb61217947d92065132bd6b9e688c7da4`;
its implementation digest is
`58fa0bb5d4f6c6d643ed5715cc8dcef22200bbc3d45c17e3a4ac93a1422bd9d0`.

The 34 fallbacks report
`legacy-winner-has-no-unique-fdas-food-route`. This is intentional: actions
outside the one accepted city-food route are not treated as causal merely
because they were legal or selected by the legacy controller.

## Fresh engine-live confirmation

The same bounded profile was then exercised for 160 turns on pinned seed
`4543804` from clean source commit
`7a857d2ba228ca197db1ad1258959f57811869f3`:

```bash
FREECIV_RULESET_ROOT=/path/to/freeciv/data \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_city_stability_authority.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_city_stability_authority.json \
python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --out artifacts/freeciv/fdas-city-stability-authority-live-160-v2 \
  --backend engine-live --workers 1 --base-port 6001 \
  --limit-seeds 1 --condition e_full_loop --main-only --no-resume

python3 scripts/freeciv/audit_fdas_authority_live.py \
  --game-dir artifacts/freeciv/fdas-city-stability-authority-live-160-v2/games/main/e_full_loop/4543804-00 \
  --output docs/freeciv/evidence/fdas-bounded-city-authority-engine-live.json
```

Results:

| Measure | Result |
|---|---:|
| Completed games / infrastructure failures | 1 / 0 |
| Turn horizon reached | 160 |
| Authority opportunities | 364 |
| Authorized city-governor pass-throughs | 28 |
| Explicit legacy fallbacks | 336 |
| Actions sent / action results | 367 / 367 |
| Rejected engine actions | 0 |
| Event records | 66,126 |

All seventeen engine acceptance gates passed. Every authorization retained the
exact bounded `city_governor` shape, matched the current snapshot and FDAS
revision through commit, ran every declared authority and commit check,
received an exact shadow resource schedule and a conserved non-authoritative
packet schedule, and had exactly one causally downstream `action_sent` plus an
accepted `action_result`. The terminal opportunity/action/fallback counters
match the event inventory exactly.

The 336 fail-closed readouts comprise 159 missing legacy decisions, 175 legacy
winners without a unique FDAS food route, and two actions outside the bounded
shape. This is live evidence that non-qualifying decisions continue through
the legacy path rather than being broadened into FDAS authority.

The engine report structural hash is
`2a0d0d56ff09364e36f11b69a2ec8156b4f7c2d7a4d9809afd932bd68b3d75f6`.
Its source event stream hash is
`d13333f6fb49144d7a276487336666cc7f45ca043398d521fdafed2ef441b266`.

## Verification

Focused authority, configuration, event-schema, runtime, and harness tests:

```text
170 passed in 306.28s
```

The complete FreeCiv regression passed after the versioned Phase-0 event
inventory was regenerated:

```text
1298 passed in 385.00s
```

The current complete FDAS subset passed 211 tests after the bounded defense
slice and generalized live auditor were added.

The authority-specific pressure suite passed 16 tests, including exact
pass-through, default-off rollback, different-winner fallback, stale-revision
fallback, missing-legacy-decision fallback, resource/packet accounting, and
commit revalidation. The deterministic engine evidence auditor adds two tests
covering accepted causal materialization and rejected-result failure.

## Claim boundary

This evidence supports one bounded, default-off, pass-through city-stability
authority slice. It does not support a score or win-rate improvement claim,
does not allow FDAS to change the selected action, and does not promote the
default manifest. The single engine game ended at score 124 versus 400; that
unpaired observation is recorded for completeness and is not an efficacy
estimate. A policy-divergent slice requires calibrated transition value,
decision-safe candidate readout, and fresh paired engine-backed outcome
evidence.
