# Unified PF-PLN scalar baseline

Stage S0 freezes the implementation at commit
`3586a00ab40e0ea5b08ff83675d4b312447b1d62` as the scalar-v1 scientific
control. It remains the production fallback while scalar-v2, bridge, and flow
controllers are developed.

The manifest is
`benchmarks/freeciv/pf_unified/baseline_manifest.yaml`. Its source identity is
derived from the Git object, not the current working tree. It pins:

- the complete target-agent, benchmark, and schema source digest;
- byte hashes for replay states, the 2,000-turn harness profile, and event
  schemas;
- FreeCiv ruleset compiler, source, IR, and Atomese identities;
- runtime and pressure artifact schemas;
- pressure engine, scheduler, live adapter, and strong scalar solver
  identities;
- a fixed seed declaration and platform profile;
- byte hashes for every v1 golden artifact.

## Golden coverage

The v1 corpus in `benchmarks/freeciv/pf_unified/golden/v1/` freezes:

1. capital-defense reverse pressure propagation and truth firewall;
2. pressure concentration over 256 decoy routes;
3. proof-DAG conversion and scheduling;
4. observation-versus-action cost-aware scheduling;
5. multi-goal Impact ranking over both byte-exact state snapshots;
6. successful, duplicate, and no-progress conductance replay;
7. the engine-live and representative runtime activation matrix;
8. deterministic event bytes, causal ordering, validation, and hashes;
9. the stateful smoothed scalar controller trace.

Every golden file declares its artifact type, source commit, baseline identity,
configuration hash, fixture hash, seed, payload hash, and artifact hash.
Golden generation reads fixtures but never writes truth, snapshots, or live
planner state.

## Commands

Verify the archived source, fixture bytes, and committed golden bytes:

```bash
python3 scripts/freeciv/run_pf_unified_baseline.py verify
```

Regenerate all artifacts in memory and require byte-exact hashes:

```bash
python3 scripts/freeciv/run_pf_unified_baseline.py replay
```

Capture the deterministic corpus to a temporary review directory:

```bash
python3 scripts/freeciv/run_pf_unified_baseline.py capture --out /tmp/pf-golden
```

Compare two manifests:

```bash
python3 scripts/freeciv/run_pf_unified_baseline.py compare LEFT.yaml RIGHT.yaml
```

The comparison exits with an identity error if source, fixtures, ruleset,
runtime, or solver identity differs. `--allow-cross-version` permits an
explicit descriptive comparison, but the result remains marked
`comparable: false`; it does not turn unlike measurements into a direct score
claim.

Measure controller-inclusive wall time:

```bash
python3 scripts/freeciv/run_pf_unified_baseline.py timing --repetitions 200
```

The first recorded measurements are in
`docs/freeciv/evidence/pf-unified-s0-controller-timing.json`. They include
validation, ranking, allocation, and artifact serialization. They are a local
performance baseline, not a cross-machine speed claim.

## Strong scalar comparator

`SmoothedScalarController` is deliberately separate from the live PF-v1
scheduler. It accepts an instantaneous route score plus PF advantage and bridge
estimate, then adds:

- exponential smoothing;
- route-score momentum;
- minimum dwell and switch-margin hysteresis;
- a persistent-route dwell bonus;
- a bounded allocation floor for exactly one admissible backup route.

The controller has deterministic route-ID tie breaking, rejects non-finite or
invalid configuration, releases an inadmissible current route immediately,
and can reset to replay a trace exactly. It does not change live selection in
Stage S0. Later packet scheduling can consume its selected and backup
allocations through the controller's stable `1.0` identity.

## G0 interpretation

G0 establishes reproducibility, not gameplay improvement. A later result may
claim improvement only if it:

- passes the identity guard or explicitly labels a cross-version comparison;
- uses the same controller-inclusive resource accounting;
- replays semantic artifacts without truth or legal-action mutation;
- compares against both scalar-v1 and this smoothed scalar controller;
- reports held-out paired engine evidence under the benchmark protocol.
