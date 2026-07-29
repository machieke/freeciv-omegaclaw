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

### Stage S4 flow reference and Gate G4

Stage S4 adds Python reference contracts for robust unit normalization,
typed semantic/probe requested currents, explicit open-path and accounting
closures, gauge-fixed source-sink projection, provenance-typed
multi-commodity capacities, conservative asymmetric two-dye advection,
continuous location eligibility with whole-packet execution, and a
truth-preserving health/fallback ladder.

The flow path retains the following authority boundary:

```text
overlap location
  -> grounded operation
  -> typed PF value and risk
  -> whole-packet reservation
  -> complete RequirementSet
  -> exact current-state revalidation
  -> commit or packet return
```

Overlap, current, congestion duals, and fractional mass never become proof,
truth, or action progress. Resource-return edges remain accounting-only.
Measured, allocated, and shaping capacities produce different permitted
responses, and an unconverged dual is never reported as an economic price.

The independent reference model lives under `research/flow_control/`. Run
the full scientific-risk gate with:

```bash
python3 scripts/freeciv/run_pf_unified_baseline.py \
  g4-sandbox \
  --train-seeds-per-family 32 \
  --heldout-seeds-per-family 64 \
  --timing-repetitions 10 \
  --out docs/freeciv/evidence/pf-unified-g4-flow-sandbox.json
```

The recorded
[G4 flow evidence](evidence/pf-unified-g4-flow-sandbox.json) covers 512
training and 1,024 seed-disjoint held-out cases across 16 graph, packet,
capacity, dynamic-failure, and evidence-selection families. It evaluates 12
named baselines, the complete 15-arm implementation/ablation sequence
(including corrected and uncorrected probe arms), an exact small packet
oracle, 256 stability settings, and corridor lengths from 4 through 128.

On that synthetic held-out cohort, the strong smoothed scalar comparator
completed 107/1,024 packets (10.45%), bridge scoring without flow completed
536/1,024 (52.34%), bridge plus the scalar packet scheduler completed
756/1,024 (73.83%), and the full controller completed 930/1,024 (90.82%).
The full-versus-scalar paired completion lift was +0.8037 with a bootstrap
95% interval of `[+0.7793, +0.8281]`; the full-versus-bridge-packet lift was
+0.1699 with `[+0.1475, +0.1934]`. Packet completion correlated 0.9661 with
realized synthetic value, compared with 0.4898 for relaxed mass.

The reference controller took 2.57 microseconds per synthetic case versus
1.54 microseconds for the scalar comparator. Conservative transport ranged
from 3.0 microseconds per length-4 run to 2.13 milliseconds per length-128
run on the recorded machine. The stability map publishes 228 recovering and
28 false-corridor fixed-point settings; the selected neighborhood recovered
in all four packet-quantum/corridor-length variations.

Gate G4 therefore permits **shadow live integration**, not live authority.
Its verification hash is
`11afc9143ddd86f76f69555d6bfca50fa83524bf4946c492ad7ce02446e4dcee`.
These are synthetic controller results, not a FreeCiv score, gameplay, or
win-rate claim. Engine-backed shadow and paired confirmation remain required
before any such claim.

### Stage S5 engine integration

The Python reference controller is now connected to
`GroundedImpactPlanner` through a versioned `ControlQuery` and
`ControlDecision` adapter. The legacy and scalar-v2 paths remain available;
`unified_shadow` cannot change the live action, and
`unified_flow_advisory` can reorder only an authoritative grounded candidate
after whole-packet completion, health checks, and exact current-state
revalidation. Every failure follows the explicit flow-to-scalar fallback
chain. Belief, attention, and action explanations use separate ledgers.

Flow overlap has one declared use: it selects a bounded per-goal candidate
region. Typed PF priority then scores concrete operations within that region.
The controller records the flow selection, scalar comparator, region
threshold, packet state, signal-use ledger, and later authoritative outcome.
It never multiplies overlap into PF value.

The first two-pair engine diagnostic found a structural no-op in the initial
adapter: every positive-overlap candidate was retained and then sorted by the
unchanged scalar score, so all 282 executed actions matched. A corrected
four-pair diagnostic completed without failures or safety violations and
produced 13 direct disagreements. Its paired score deltas were
`[0, -2, +7, 0]`, for a diagnostic mean of `+1.25` with interval
`[-1.50, +5.25]`; the score-lead-rate delta was `+0.25 [0.00, +0.75]`.

The subsequent event-performance replay exposed that transport `source_seq`
was leaking into topology IDs and the stochastic probe seed. The hardened
controller separates strict commit identity from versioned probe semantic
identity. Two independent engine replays from the same clean hardened commit
then produced identical 98-action treatment streams and identical flow
summaries. On the reused `4752647` seed, treatment became action-equivalent
to baseline and scored `117` rather than the earlier `124`. The four-pair
diagnostic is therefore implementation-debugging history, not directional
evidence for the hardened controller and not a gameplay, score, or win-rate
claim.

The untouched 40-pair `unified_flow_advisory_pilot_v1` cohort completed all
80 arms without a failure from the deterministic hardened implementation.
Player score changed by `+0.675 [+0.20, +1.20]` with exact paired sign-flip
`p=0.0144`; 15 pairs improved, seven declined, and 18 tied. Treatment made
86 direct flow-versus-scalar disagreements across 27 seeds. Every nonzero
score delta occurred in that subset. Score-lead rate moved `-0.05
[-0.125, 0.00]`, so the pilot supports a score confirmation but not a
lead-rate claim.

The pilot remains claim-ineligible. Its paired SD of `1.6391` freezes a
seed-disjoint 100-pair score confirmation with conservative planning SD
`1.75` and minimum detectable delta `0.5`; the declared calculation requires
97 pairs. Controller parameters are unchanged. Live authority remains gated
because the current one-step transition artifact is explicitly uncalibrated
and the fresh confirmation has not yet completed.

Run the diagnostic or pilot with:

```bash
FREECIV_RULESET_ROOT=/path/to/freeciv/data \
PYTHONPATH=src:benchmarks python3.8 \
  scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/unified-flow-advisory-pilot-v1-engine \
  --backend engine-live \
  --cohort unified_flow_advisory_pilot_v1 \
  --workers 3 \
  --server-ports 6001,6003,6004 \
  --no-resume
```

Detailed diagnostic evidence is recorded in
[v1](evidence/pf-unified-flow-advisory-diagnostic-v1.md) and
[v2](evidence/pf-unified-flow-advisory-diagnostic-v2.md). The hardened
same-commit action replay and post-optimization timing are recorded in the
[determinism replay](evidence/pf-unified-flow-advisory-determinism-replay-v1.md).
The complete pilot and frozen confirmation design are recorded in the
[pilot evidence](evidence/pf-unified-flow-advisory-pilot-v1.md).
