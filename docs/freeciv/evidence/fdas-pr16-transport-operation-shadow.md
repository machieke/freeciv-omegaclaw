# FDAS PR 16: founder/ferry operation shadow activation

Date: 2026-08-02
Branch: `experimental/functional-dependent-atomspace`
Status: transport operations declared `shadow-live`; policy authority disabled
Machine-readable evidence: `fdas-pr16-transport-operation-shadow-engine.json`

## Acceptance boundary

This increment promotes the grounded founder/ferry lifecycle from component
tests into the engine-live FDAS projection. It does not let FDAS propose,
select, commit, or execute an action. A manifest-pinned intent exists only to
exercise the mechanism on one known `startunits: csdf` diagnostic seed. The
legacy controller still chooses every action, and the existing exact legal-set
and execution gates remain authoritative.

The live seam now provides:

- strict, canonical parsing of a seed-specific diagnostic intent with
  `policy_authority: false`;
- grounded partner-locked assembly over authoritative founder/ferry state,
  compiled transport capabilities, and a server-native ferry corridor;
- one `RequirementSet` covering founder, ferry, pickup, landing, settlement,
  deadline, and escort policy premises;
- exact action-budget, current/future actor, move-point, tile-occupancy, and
  transport-seat claims;
- durable operation, assembly, repair-budget, and retention state protected by
  persistence identity and structural digest;
- restart reconstruction of current reservations and legal bindings from the
  authoritative current snapshot rather than persisted stale claims;
- operation projection and causal lifecycle events that remain explicitly
  non-authorizing; and
- fail-closed resolution when a required participant is no longer present.

## Fresh paired confirmation

The final cohort ran from clean source commit
`c4cb94c1591f7604edada573dd9dcac627ef38d6`, implementation SHA-256
`5820731c2eb90b5293f02272bf318820fb1d27f908fe470dbf7ab06a136c8fc3`,
FDAS declaration hash
`fbbcf152766fdd47ffad47e1822d51dbae26cc9fa6f132587e808a65b8c30d2b`,
and configuration hash
`861e1c439cbe7a4df082374917de644e879a8045304b097e89a633413be4708b`.

```bash
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_transport_operation_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_transport_operation_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_impact_evaluation.py \
  --config profile/freeciv_harness.yaml \
  --out artifacts/freeciv/fdas-transport-operation-shadow-live-30-v4 \
  --backend engine-live --workers 1 --server-ports 6001 \
  --cohort fdas_transport_operation_shadow_diagnostic_v1 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_transport_operation_live.py \
  --cohort-root artifacts/freeciv/fdas-transport-operation-shadow-live-30-v4 \
  --output docs/freeciv/evidence/fdas-pr16-transport-operation-shadow-engine.json
```

Results:

| Measure | Baseline | Treatment |
| --- | ---: | ---: |
| Engine actions / accepted results / rejects | 74 / 74 / 0 | 77 / 77 / 0 |
| Durable operations | 1 | 1 |
| Operation reservations | 1 | 1 |
| Same-step grounded re-estimates | 7 | 6 |
| Fail-closed abandonments | 1 | 1 |
| Exact legacy-action matches | 0 | 0 |
| Step commits / completions | 0 / 0 | 0 / 0 |
| Total lifecycle reconciliations | 9 | 8 |
| FDAS projection p50 / p95 | 79.18 / 139.10 ms | 83.30 / 130.56 ms |
| Full-controller p50 / p95 | 198.72 / 582.65 ms | 205.58 / 748.46 ms |
| FDAS / operation authority actions | 0 / 0 | 0 / 0 |

Both arms assembled the deterministic operation ID
`operation-cbab632a9679037fe0c6e50b0b239c4b`. The initial current step was an
exact server-advertised move for ferry `107` from tile `512` to pickup tile
`487`. Its resource contract contained all five required resource kinds:
action budget, actor, move points, tile occupancy, and transport seat. The
operation and all of its structural atoms were projected into the same FDAS
revision.

The legacy controller did not choose that ferry action. It moved founder `102`
over land and founded a city on turn 5 or 6. On the next authoritative rich
snapshot, the lifecycle observed that the required founder unit no longer
existed and resolved the unrelated transport operation as `abandoned` with
reason `required-founder-removed`. It did not reinterpret city creation as
transport completion and did not retain a stale reservation.

The audit passed every mechanism, persistence, projection, resource,
causality, source-freeze, non-authority, and FDAS p95 gate. The complete
controller p95 exceeded the observational 500 ms target in both arms. That
target is reported but is not attributed to this shadow slice because both
arms ran the identical FDAS mechanism and this one-pair diagnostic has no
no-FDAS timing control. The preceding transport-capability cohort remains the
clean latency-isolation result.

The deterministic report structural hash is
`b88e492421816603a3d98ce17d9e41915523537dbe5b7892fec34bf9d4b0d9ad`.
The tracked report file SHA-256 is
`14f4026e8ab40d9b40f7893acfaf7fc683b4131fc57029d2fe95ad1feed0151f`.

## Diagnostic corrections

The first attempted engine run used an invalid worker port and produced no
game. The next attempt reached lifecycle emission and correctly failed the
closed event schema because an undeclared `transport_phase` property was
present. The corrected emitter uses only schema-supported `mechanism`,
`step_index`, and `reason_code` fields and maps all eleven lifecycle
dispositions to their semantically matching operation event states. A
closed-schema regression test now exercises every disposition before engine
execution.

## Claim boundary and next gate

This is evidence for configured founder/ferry assembly, durable FDAS
projection, a complete resource contract, current-snapshot re-estimation, and
fail-closed participant invalidation. It is not evidence for an action match,
embark/disembark execution, settlement completion, policy quality, score, or
win rate.

The next transport authority gate needs a deterministic embark-capable replay
or engine scenario in which the exact current ferry action is selected through
a separately declared bounded control path, followed by authoritative
embark/disembark effects, settlement retention, negative safety cases,
rollback evidence, and fresh multi-seed confirmation. Those claims must not be
inferred from this non-authorizing diagnostic.
