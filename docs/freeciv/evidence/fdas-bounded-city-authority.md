# FDAS bounded city-stability authority

Date: 2026-08-02  
Branch: `experimental/functional-dependent-atomspace`  
Machine-readable evidence: `fdas-bounded-city-authority-replay.json`

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
| Authority readout p50 / p95 | 0.045 / 1.602 ms |

All eleven acceptance gates passed. The two complete runs produced identical
semantic readouts. Every authorized action matched the legacy winner exactly,
was selected by the bounded authority pressure readout, received complete
resource/packet allocation, and passed exact FDAS commit validation. Every
commit record retained `execution_authority: false`, proving that the final
execution gate remains downstream.

The report hash is
`7df235aaea42cf06d56b23a898543689100fb9848da0bc6f483b0f84687a17d5`;
its implementation digest is
`ef94d3e15ad0ca278f3608500fe62a729403c7489d0a443113993e6c95409db2`.

The 34 fallbacks report
`legacy-winner-has-no-unique-fdas-food-route`. This is intentional: actions
outside the one accepted city-food route are not treated as causal merely
because they were legal or selected by the legacy controller.

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

The complete FDAS subset passed 200 tests.

The authority-specific pressure suite passed 15 tests, including exact
pass-through, default-off rollback, different-winner fallback, stale-revision
fallback, resource/packet accounting, and commit revalidation.

## Claim boundary

This evidence supports one bounded, default-off, pass-through city-stability
authority slice. It does not support a score or win-rate improvement claim,
does not allow FDAS to change the selected action, and does not promote the
default manifest. A policy-divergent slice requires calibrated transition
value, decision-safe candidate readout, and fresh engine-backed outcome
evidence.
