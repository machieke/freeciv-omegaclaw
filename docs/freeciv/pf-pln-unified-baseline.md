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

## Scalar-v2 and teleological gates

Stage S1 adds an opt-in scalar-v2 controller with separated achievement and
epistemic demand, signed pressure rails, distributional risk, requirement
sets, whole packets, and a strict runtime/artifact contract. Verify it with:

```bash
python3 scripts/freeciv/run_pf_unified_baseline.py v2-verify
python3 scripts/freeciv/run_pf_unified_baseline.py v2-timing --repetitions 1000
```

Stage S2 adds first-class goal loss, expected transitions, cost-to-go,
leverage, typed pre-cost advantage, composite reverse operators, cross-goal
value-of-computation arbitration, engine-live observation/simulation and LLM
packet contracts, selection coverage, shadow structural operations, and
context-qualified control calibration. The live Impact integration is opt-in
through `ImpactPressureRankerV2(teleological_enabled=True)` so scalar-v1 and
the archived v1 corpus remain unchanged.

The teleological artifact exposes one reconstructable chain per operation:

```text
goal loss
  -> expected post-operation transition
  -> cost-to-go
  -> signed leverage
  -> typed pre-cost advantage
  -> post-cost schedule score
```

Expected state relief enters `TypedAdvantage`; operation cost is subtracted
only by the scheduler. Distributional risk remains a separate scheduler term,
so it is not counted again inside the advantage. The strong smoothed scalar
comparator consumes the same `TypedAdvantage` values through
`bid_from_typed_operation`, subtracting operation cost exactly once and
setting bridge contribution to zero.

Verify G2 and measure its controller-inclusive live-Impact overhead with:

```bash
python3 scripts/freeciv/run_pf_unified_baseline.py g2-verify
python3 scripts/freeciv/run_pf_unified_baseline.py g2-timing --repetitions 100
```

The recorded G2 evidence is in
`docs/freeciv/evidence/pf-unified-g2-verification.json` and
`docs/freeciv/evidence/pf-unified-g2-controller-timing.json`. G2 is an
implementation and parity gate, not a gameplay claim. Its category/horizon
relief [plot](evidence/pf-unified-g2-relief-calibration.svg) uses a
deterministic contract fixture and is explicitly
claim-ineligible; a held-out engine cohort must replace that fixture before
claiming empirical calibration or score improvement.

### Stage S3 bridge experiment

Run the seed-disjoint synthetic conductance-versus-bridge experiment with:

```bash
python3 scripts/freeciv/run_pf_unified_baseline.py \
  g3-bridge-experiment \
  --train-seeds-per-family 64 \
  --heldout-seeds-per-family 64 \
  --timing-repetitions 20
```

Run the final semantic and controller-inclusive G3 gates with:

```bash
python3 scripts/freeciv/run_pf_unified_baseline.py \
  g3-verify \
  --train-seeds-per-family 64 \
  --heldout-seeds-per-family 64
python3 scripts/freeciv/run_pf_unified_baseline.py \
  g3-live-timing \
  --repetitions 20 \
  --controller-budget-ms 500
```

The experiment covers all nine preregistered graph failure families and ten
arms, including context-conditioned conductance, explicit bridge geometry,
fusion, forward/backward shuffle controls, bridge without typed PF scoring,
oracle reachability, and a learned forward predictor. The strong smoothed
scalar controller is checked for first-step selection equivalence on every
independent held-out query.

The recorded
[G3 bridge evidence](evidence/pf-unified-g3-bridge-experiment.json) supports
incremental forward-reachability value on held-out synthetic packet
completion. It is deliberately not a FreeCiv gameplay score claim. The final
G3 gate also verifies live captured-snapshot legality, exact replay, one
conserved action/CPU packet, non-evidential probes, single-use bridge signals,
and scalar-v2 fallback under injected or unvalidated disagreement. The full
bridge path takes 239.0 ms mean and 245.0 ms p95 on the recorded machine,
versus 22.1 ms for teleological scalar-v2, and remains within the
preregistered 500 ms per-query controller budget.
