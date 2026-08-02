# FDAS PR 16: transport capability shadow activation

Date: 2026-08-02
Branch: `experimental/functional-dependent-atomspace`
Status: transport capability declared `shadow-live`; transport operations remain `component-only`
Machine-readable evidence: `fdas-pr16-transport-capability-shadow-engine.json`

## Acceptance boundary

This increment promotes only the static/current-state transport capability
projection into engine-live shadow execution. It does not assemble a
founder/ferry operation, reserve a seat, select an embark action, or grant FDAS
policy authority. The legacy controller selected and sent every action in both
arms.

The paired diagnostic used the normal baseline and treatment planners with the
same FDAS transport profile in both arms. The predeclared `startunits: csdf`
override supplied one own Trireme and founder so transport capability was
observable without inventing a route or embark action.

## Corrected state contract

The first engine diagnostic exposed a semantic defect rather than a missing
ruleset capability. FreeCiv's `PACKET_UNIT_INFO.carrying` field identifies a
trade-goods type; it is not the number of carried units. Treating `-1` as a
passenger count caused the projector to abstain from seat capacity, so the
first run produced compatibility atoms but no `transport-seat-resource` or
`transport-seat-available` atoms.

The corrected immutable state now retains `carrying` only as goods metadata
and derives `cargo_count` from the complete authoritative own-unit relation
set:

```text
cargo_count(carrier) = count(
  own unit where transported=true and transported_by=carrier.id
)
```

A zero count is exact only when every own unit has a complete transport
relation. An incomplete relation set leaves the count unknown and omits seat
capacity. A future explicit `cargo_count` is accepted only when nonnegative
and, when relations are complete, equal to the derived count. The ruleset and
proxy legality checks use the same relation semantics. Regression coverage
includes empty, partially loaded, full, contradictory, and incomplete states.

## Fresh paired confirmation

The semantic repair was committed before execution. The clean cohort used
source commit `e79d6fa6c02d97c9895ec72338db99f957941b8d`, pinned seed `104729`,
the corrected proxy patch-series identity
`d8f586ad5741106beb23b24c3e5f599fd74cb8e1b0f0a33961f2c966e66fe7d4`,
and this command shape:

```bash
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_transport_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_transport_shadow.json \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/fdas-transport-capability-shadow-live-30-v3 \
  --config profile/freeciv_harness.yaml --backend engine-live \
  --workers 1 --server-ports 6001 \
  --cohort fdas_transport_shadow_diagnostic_v1 --no-resume

PYTHONPATH=src:benchmarks python3 scripts/freeciv/audit_fdas_transport_live.py \
  --cohort-root artifacts/freeciv/fdas-transport-capability-shadow-live-30-v3 \
  --output docs/freeciv/evidence/fdas-pr16-transport-capability-shadow-engine.json
```

Results:

| Measure | Baseline | Treatment |
| --- | ---: | ---: |
| Actions / accepted results / rejects | 75 / 75 / 0 | 75 / 75 / 0 |
| Transport scopes | 31 | 31 |
| Seat-resource projections | 31 | 31 |
| Seat-available projections | 31 | 31 |
| Sampled cold verifications / failures | 1 / 0 | 3 / 0 |
| FDAS projection p50 / p95 | 25.48 / 29.39 ms | 27.18 / 30.76 ms |
| FDAS shadow p50 / p95 | 1.93 / 18.36 ms | 1.91 / 3.11 ms |
| Full-controller p50 / p95 | 165.59 / 508.59 ms | 166.44 / 706.50 ms |
| FDAS authority events / actions | 0 / 0 | 0 / 0 |
| Transport operation events | 0 | 0 |

All capability, state-contract, engine-safety, source-freeze, cold-parity, and
FDAS contribution gates passed. The audit requires the seat-resource and
seat-available record counts to equal the number of materialized transport
scopes, and it rejects an at-capacity contradiction for this empty ferry.

The branch-wide 500 ms full-controller p95 target was not met in this short
pair. FDAS itself remained well inside its 150 ms contribution budget; the
controller observation is retained as an open performance item rather than
being hidden inside capability acceptance. A later ordinary-latency cohort or
optimization must close that global definition-of-done item.

The deterministic report structural hash is
`6822bb5b1b17455f4d53d1c0075877384882869b1b6aa972d716e881a96231d3`.
The tracked report file SHA-256 is
`5735eafc43e99650776a86c79fe5c1fd7e4492e27c7acecfa656a319ecc239a6`.

## Claim boundary and next gate

This is a mechanism, semantic-correctness, preservation, and bounded-FDAS-
latency result. The paired cohort was deliberately claim-ineligible and does
not support a score or win-rate claim.

Transport operation activation remains separate. It requires a grounded
intent source, exact current embark/disembark legal-action bindings, seat and
participant claims, durable partner-locked lifecycle state, effect-based
completion, replay safety cases, rollback, and fresh engine evidence. None of
those are inferred from an empty compatible ferry alone.
