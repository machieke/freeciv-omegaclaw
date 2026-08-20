# Scalability v1 high-entity engine-shadow preregistration

**Frozen before engine execution:** 2026-08-20  
**Phase:** G8 — engine-backed shadow confirmation  
**Scenario:** `scalability-v1-high-entity-he1`  
**Claim boundary:** integration correctness, achieved scale, and overhead only;
no gameplay, score, or win-rate claim

## Design

This cohort uses a fixed 30-turn FreeCiv scenario with fog disabled and the
release-game start-unit string `ccccxxxxxxxxdddddddd`: four founders, eight
explorers, and eight defenders. The larger initial entity set is intended to
materialize more cities, units, spatial scopes, legal actions, simultaneous
goals, and grounded candidates than the accepted three-pair reference cohort.
Configured budgets are not treated as achieved scale.

Twenty fixed seeds are paired. Each seed runs first as a control with the
Functional Dependent AtomSpace (FDAS) disabled, then as a read-only FDAS shadow
with identical effective gameplay configuration. Protected bridge and
source-sink flow execute in `unified_flow_advisory` mode in both arms;
`pressure_flow_live_enabled` and all FDAS policy/domain authority remain false.
The scalar controller therefore remains the effective policy.

Each arm is launched in a fresh single-worker Python process so the status
ledger records an arm-local Linux process high-water RSS. Shadow seed 8850005
uses full AtomRecord/support telemetry. The remaining 19 shadow seeds use
aggregate, support-free telemetry. The control uses selected-support telemetry.

## Frozen seeds

The seeds were generated before profile construction using
`sha256-counter-v1`, namespace
`freeciv-scalability-v1-high-entity-engine-shadow-v1`, inclusive range
8,800,000–8,899,999, with duplicate rejection. They are:

```text
8850005, 8801478, 8852936, 8857184, 8844422,
8803438, 8810578, 8826840, 8807954, 8807688,
8849668, 8881509, 8888493, 8818470, 8893336,
8895576, 8869887, 8883283, 8810456, 8852047
```

No seed appears in the existing harness profiles at freeze time.

## Frozen comparator

The accepted reference is
`artifacts/freeciv/fdas-engine-shadow-cohort-20260802-v8/report.json`, SHA-256
`7fe0b0dfdcd89a55efd556f9a6ef2abd26f8bf3206affcb70bd8c1a98c287e94`.
Its natural maxima establish strict lower bounds, not target values:

| Measurement | Reference maximum |
|---|---:|
| Concurrent atoms | 1,196 |
| Supports | 659 |
| Scopes | 12 |
| Cities | 3 |
| Units | 5 |
| Legal actions | 297 |
| Concurrent goals | 2 |
| Grounded candidates | 9 |
| Region scopes | 2 |

Every listed value must be exceeded by the new shadow cohort for the
high-entity expansion check to pass.

## Acceptance and measurements

The paired audit fails G8 if an arm is incomplete, its event ledger is
invalid, source identity is dirty or mismatched, effective non-FDAS manifests
differ, ordered actions or action-result statuses differ, or completion
summaries differ. It also fails on an authority-eligible decision, stale/legal
binding failure, missing legacy candidate, safety downgrade, cold-verification
failure, detail omission, unhealthy flow solve, unexplained controller
fallback, absent bridge/flow execution, absent full-detail sample, missing RSS
sample, atom-budget breach, or failure to exceed any frozen volume lower bound.

The audit publishes achieved concurrent atoms/supports/scopes; cities, units,
regions, and legal actions; natural PLN chain depth and proof-tree size;
concurrent goals and grounded candidates; pressure control nodes/edges;
bridge-node and flow-iteration maxima; FDAS projection/shadow/controller p50,
p95, and maximum latency; and arm-process RSS p50, p95, and maximum. The old
150 ms FDAS and 500 ms controller thresholds remain visible historical labels
but are report-only in this G8 cohort because the experiment plan did not
preregister them as G8 acceptance gates.

The synthetic-to-engine transfer readout is fixed as follows. At the achieved
natural maximum atom count, select the nearest measured canonical held-out
AtomSpace work tier (local topology, 1% churn, one support, no retention).
Publish:

1. engine-shadow FDAS projection p95 divided by that tier's synthetic
   incremental-update p95; and
2. engine-shadow controller-process RSS p95 divided by that tier's isolated
   synthetic-process RSS p95.

The selected tier, work values, sample counts, and whether the engine point is
inside the synthetic work range must be included. These are descriptive
shape/integration ratios, not workload equivalence or a pass/fail gate.

## Execution

The source commit and implementation digest are frozen in every run manifest.
Execution refuses a dirty tree and aborts if the source changes during the
cohort.

```bash
PYTHONPATH=src:benchmarks python3 \
  scripts/freeciv/run_scalability_engine_shadow.py \
  --root artifacts/freeciv/scalability-v1/heldout/engine

PYTHONPATH=src:benchmarks python3 \
  scripts/freeciv/audit_scalability_campaign.py \
  --root artifacts/freeciv/scalability-v1 \
  --output docs/freeciv/evidence/scalability-v1.json \
  --bootstrap-resamples 10000
```

Infrastructure retries must retain the same manifest identity and archive the
failed attempt. No scenario, seed, lower bound, telemetry assignment, transfer
definition, or acceptance rule may be changed after the first engine arm is
entered. Negative and null outcomes remain reportable results.
