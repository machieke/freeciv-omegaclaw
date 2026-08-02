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

## Fresh paired confirmation and latency closure

The semantic repair was committed before execution. Two clean 50 ms cohorts
confirmed the capability result but missed the 500 ms full-controller p95
target in both arms. Latency decomposition identified the accepted-action
authoritative refresh barrier, repeated three or four times on multi-action
turns, as the dominant avoidable cost. The barrier retained its exact
source-sequence lock, proxy-settled marker, two-sample equivalence,
candidate-specific effect predicate, and fail-closed retry while its quiet
interval was reduced from 50 ms to 20 ms.

The clean confirmation cohort used source commit
`f80b307d4e97623bce03cadb9761b2689d2e60af`, pinned seed `104729`, the
corrected proxy patch-series identity
`d8f586ad5741106beb23b24c3e5f599fd74cb8e1b0f0a33961f2c966e66fe7d4`,
and this command shape:

```bash
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_transport_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_transport_shadow.json \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/fdas-transport-capability-shadow-live-30-v5 \
  --config profile/freeciv_harness.yaml --backend engine-live \
  --workers 1 --server-ports 6001 \
  --cohort fdas_transport_shadow_diagnostic_v1 --no-resume

PYTHONPATH=src:benchmarks python3 scripts/freeciv/audit_fdas_transport_live.py \
  --cohort-root artifacts/freeciv/fdas-transport-capability-shadow-live-30-v5 \
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
| FDAS projection p50 / p95 | 25.59 / 30.43 ms | 26.91 / 31.56 ms |
| FDAS shadow p50 / p95 | 1.91 / 18.27 ms | 1.91 / 3.08 ms |
| Full-controller p50 / p95 | 132.91 / 412.68 ms | 131.51 / 449.86 ms |
| FDAS authority events / actions | 0 / 0 | 0 / 0 |
| Transport operation events | 0 | 0 |

All capability, state-contract, engine-safety, source-freeze, cold-parity, and
FDAS contribution gates passed. The audit requires the seat-resource and
seat-available record counts to equal the number of materialized transport
scopes, and it rejects an at-capacity contradiction for this empty ferry.

Both arms now meet the branch-wide 500 ms full-controller p95 target. Against
the two preceding 50 ms cohorts, full-controller p95 moved from
508.59/706.50 ms and 669.81/586.80 ms to 412.68/449.86 ms. Median controller
latency fell from roughly 166--173 ms to 132 ms, while FDAS projection p95
remained stable near 30--32 ms. This is evidence that the improvement came
from the authoritative refresh path, not from suppressing FDAS work. All 150
action results remained accepted and all four sampled cold checks remained
equivalent.

The deterministic report structural hash is
`205e15978199aa035e4ea648f6e496b47c9dc30c5bde03493b8ca3f8a6a4fb3d`.
The tracked report file SHA-256 is
`0fad19ca6cc50a7d1b5a714437ba8209ad7d51792ab5c58e64b5e44792a391ca`.

## Claim boundary and next gate

This is a mechanism, semantic-correctness, preservation, and bounded-FDAS-
latency result. The paired cohort was deliberately claim-ineligible and does
not support a score or win-rate claim.

Transport operation activation remains separate. It requires a grounded
intent source, exact current embark/disembark legal-action bindings, seat and
participant claims, durable partner-locked lifecycle state, effect-based
completion, replay safety cases, rollback, and fresh engine evidence. None of
those are inferred from an empty compatible ferry alone.
