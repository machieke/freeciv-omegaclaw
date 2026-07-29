# Scalar PF-v2 semantics

Scalar PF-v2 is an opt-in experimental controller layer. Scalar-v1 remains the
engine-live default and the byte-frozen fallback. V2 repairs semantic defects
needed before teleological bridge or flow experiments can be interpreted.

## Demand separation

`TruthAssessment` keeps state strength and epistemic confidence independent.
`GoalDemand` serializes four named components:

- achievement demand from the absolute state-strength gap;
- epistemic demand from decision sensitivity and uncertainty;
- deadline demand;
- safety demand.

V2 action pressure is derived from achievement demand. Confidence changes
observation and inference pressure but cannot create action demand unless an
explicit precautionary policy enables that route. The v1
`supported_strength` property remains available for display and replay but is
not used by v2 achievement allocation.

## Signed channel rails

Each pressure channel carries independent positive and negative magnitude.
Addition is component-wise, commutative, and associative. `net(channel)`
reports direction while `conflict(channel)` reports contested mass. Projecting
back into scalar-v1 requires the explicit `conflict_policy="net"` argument and
fails if different channels have incompatible directions.

Clone persistence declares `pressure_schema_version: "2.0"` when signed rails
are stored. V1 clone serialization is unchanged.

## Distributional risk

Goals receive a `RiskProfile`; the existing `risk_sensitivity` is the
compatibility alias for profile aversion. Operations can carry goal-specific
`RiskEstimate` values containing expected loss, variance, upper quantile,
CVaR, confidence, and provenance.

Low confidence widens the loss distribution but does not change expected harm.
The scheduler applies goal-specific smooth CVaR penalties. A hard veto requires
all of:

- a safety goal;
- an exceeded declared loss threshold;
- an explicit hard-gate policy;
- an irreversible or externally consequential operation.

Reversible work remains eligible with a soft penalty. `RiskHysteresis`
separates plan adoption and retention thresholds.

## Deadline semantics

`DeadlineState` distinguishes current turn, deadline, expected completion,
variance, and slack. `DeadlineFit` records completion probability,
deadline-only urgency, calibration method, and hard-gate reason.

Known completion after the configured horizon is rejected. Otherwise the
scheduler uses only completion probability. Deadline urgency remains a
separate trace value so goal urgency is not multiplied twice.

## AND coalitions and whole packets

An AND rule materializes one lazy `RequirementSet`, never a power set.
`FactorDemand` retains the full parent demand independent of arity.
`PremiseSupportRequest` distributes a bounded attention share without erasing
any required premise. Completion requires the entire declared prerequisite
vector.

`PacketScheduler` operates on integer commodities:

`cpu`, `exact_rule`, `observation`, `simulation`, `action`, `expansion`,
`llm_token`, and `memory`.

Reservations are atomic across resources. Fractional softmax allocation is
diagnostic only and cannot commit an operation. Incomplete RequirementSets,
insufficient packets, abandoned reservations, and expiry remain visible.
Every schedule reports consumed and stranded quanta, conservation, relaxed
value, committed value, and integrality gap. The smoothed scalar comparator
uses this same packet scheduler.

## Version and activation

V2 artifacts declare:

```text
pressure_artifact_schema: 2.0
pressure_representation: signed-channel-rails/1.0
teleology_semantics: achievement-uncertainty-split/1.0
coalition_semantics: requirement-set/1.0
scheduler_identity: pf-pln-packet-scheduler/2.0
```

The separate controller activation schema retains historical phase
declarations. Its initial flags are:

```yaml
pressure_enabled: true
pressure_controller_mode: legacy_scalar
pressure_semantics_version: v1
pressure_packet_scheduler_enabled: false
pressure_distributional_risk_enabled: false
pressure_requirement_sets_enabled: false
pressure_bridge_enabled: false
pressure_flow_enabled: false
pressure_scalar_fallback_enabled: true
```

Bridge requires packet scheduling. Flow requires bridge and packet scheduling.
V2 features cannot be enabled under v1 semantics or while pressure is disabled.
Invalid combinations fail closed.

The experimental bridge-scalar mode is declared explicitly:

```yaml
pressure_enabled: true
pressure_controller_mode: bridge_scalar
pressure_semantics_version: v2
pressure_packet_scheduler_enabled: true
pressure_bridge_enabled: true
pressure_flow_enabled: false
```

It combines teleological scalar-v2 operation scoring, query-local bridge
geometry, corrected probes, strong smoothed scalar selection, and whole
packets. Unhealthy or unvalidated bridge decisions fall back to scalar-v2.

## Verification

Run semantic, compatibility, and snapshot replay gates:

```bash
python3 scripts/freeciv/run_pf_unified_baseline.py v2-verify
```

Run controller-inclusive timing:

```bash
python3 scripts/freeciv/run_pf_unified_baseline.py v2-timing --repetitions 1000
```

The initial eight-premise measurement found scalar-v2 transport at about
2.38 times scalar-v1 and v2 plus whole-packet scheduling at about 3.39 times
scalar-v1. Absolute local means were 0.35 ms for v1, 0.83 ms for v2, and
0.35 ms for packet scoring/reservation. These are local engineering baselines,
not gameplay or cross-machine speed claims.

The byte-exact v1 corpus still reproduces. The two byte-real FreeCiv snapshots
remain unmodified; the playable snapshot retains the same legal
`city_founding` selection under v1 and v2. No live default changes at G1.
