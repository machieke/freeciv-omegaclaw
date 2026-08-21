# Larger AtomSpace, deeper inference, and bridge/fluid scalability report

**Campaign:** `scalability-v1`  
**Finalized:** 2026-08-21  
**Frozen engine source:** `9e5e2887e82fcafb216666b6342158d4eef15df1`  
**Claim boundary:** scalability, boundedness, correctness, and performance
only; no FreeCiv gameplay, score, or win-rate claim

## Executive result

The experiment produced a useful mixed result rather than a blanket
scalability pass.

- Exact deep-proof behavior scales predictably through P3 (depth 96 and up to
  100,000 relevant proof records in the synthetic construction).
- Conservative fluid transport remains numerically correct and scales within
  the preregistered exponent bound through F3 (10 million edge updates).
- Forty captured FreeCiv amplification pairs preserve the source subgraph and
  stay within the preregistered 2x synthetic-transfer envelope.
- AtomSpace and bridge canonical scaling exponents pass through their measured
  non-stretch ranges, but higher-tier resource stops and absolute latency
  failures prevent whole-surface passes.
- The combined-load gate is incomplete because the frozen design omitted an
  isolated comparator for the repeated C16 center, not because an eligible
  interaction exceeded 2x.
- All 40 engine-backed control/shadow arms complete safely, but six of 20
  pairs lose exact action parity and the scenario fails to materialize the
  required explicit region scopes. G8 therefore fails.

The strongest defensible conclusion is tier-specific: the frozen Python
FDAS/control implementation has exact, predictably scaling proof and fluid
surfaces at the reported tiers; selected lower AtomSpace/bridge tiers are
bounded or operationally usable; and captured transfer works within 2x. It is
not valid to generalize this to unrestricted PLN, distributed
OpenCog/Hyperon AtomSpaces, or better FreeCiv gameplay.

## Method and accounting

The campaign independently scales concurrent FDAS work, proof work, protected
bridge graphs, and source-sink/two-dye fluid work. It then measures a frozen
combined factorial, captured FreeCiv snapshots, and a paired engine-backed
shadow cohort. Synthetic data structures and PLN execution use the repository's
Python implementation; PeTTa is not the AtomSpace or PLN executor in this
campaign.

Discovery and held-out phases remain separate. Claim-eligible timing uses one
benchmark process at a time. Each primary synthetic trial has a 16 GiB RSS
limit and a 120 s wall limit. Stops remain results and are never dropped from
the report.

| Accounting surface | Result |
|---|---:|
| Held-out planned/accounted rows | 12,061 / 12,061 |
| Held-out completed / stopped | 11,179 / 882 |
| Full audit rows | 16,119 |
| Full audit completed / stopped / failed | 14,858 / 1,259 / 2 |
| Historical semantic failures retained | 1 |
| Engine control/shadow pairs | 20 |
| Engine arms completed | 40 / 40 |
| Audit identity or reconstruction errors | 0 |

The retained discovery failure is a path-persistence `bridge_separated`
case. Its corrective fallback is covered by later trials; the original row is
still present so the campaign does not rewrite its history.

## Gate decisions

| Gate | Decision | Evidence-backed reason |
|---|---|---|
| G0 baseline | **Pass** | Semantic identities, counts, host provenance, production defaults, and disabled policy authority are frozen. |
| G1 generators/oracles | **Pass** | Exact-count generators, independent expected-result evaluators, schema/replay coverage, synthetic authority isolation, and declared failure modes pass. |
| G2 AtomSpace | **Fail / bounded** | Canonical exponents pass, but 92 A4 rows stop and A2/A4 absolute latency labels fail. |
| G3 proof | **Pass** | All 2,320 held-out rows complete with exact semantics; relevant and distractor exponent gates pass. |
| G4 bridge | **Fail / bounded** | H3 passes through B3 and B1 is live-capable, but 789 B4 rows stop and B3 misses its absolute label. |
| G5 fluid | **Pass** | All 1,320 held-out rows complete with exact numerical invariants and H4 passes through F3. |
| G6 combined | **Fail / incomplete** | Eligible interactions pass; one row stops and 40 repeated center rows lack the preregistered isolated comparator. |
| G7 captured | **Pass** | All 40 timing pairs preserve captured semantics and stay within the 2x transfer bound. |
| G8 engine shadow | **Fail** | All arms complete safely, but six pairs lose exact action parity and explicit region expansion is absent. |
| G9 audit/claim | **Pass** | Raw artifacts reconstruct, all cells are classified, the manifest is frozen, and negative/null results remain visible. |

## G2 — concurrent Functional Dependent AtomSpace

The canonical local-churn result scales within its preregistered relative
bounds:

- incremental-time exponent: **1.115**, clustered-bootstrap 95% CI
  **[1.103, 1.126]**, against a maximum of 1.35;
- peak-RSS exponent: **0.855**, 95% CI **[0.855, 0.856]**, against a maximum
  of 1.15; and
- no completed held-out row has a semantic mismatch.

The overall gate fails because 92 A4 stress rows hit their declared resource
stop. Absolute performance also misses both labels: A2 is 3.458 s p95 versus
500 ms, and A4 is 11.511 s p95 versus 2 s. The frozen manifest consequently
limits `correct-at-scale` to A0–A3 and grants no interactive or
research-usable FDAS label.

## G3 — deeper and broader inference

All 2,320 held-out proof trials complete correctly. The relevant-work exponent
is **1.054**, 95% CI **[1.041, 1.064]**, against a 1.50 bound. The indexed but
unreachable distractor exponent is **0.008**, 95% CI **[-0.184, 0.163]**,
against a 1.10 bound. Cycle, alternate-path, and explicit budget-exhaustion
semantics remain deterministic.

P2 earns the 10k research-usable label at **1.627 s p95** (2 s threshold).
P3 remains correct and predictably scaling but narrowly misses its stress label
at **15.984 s p95** (15 s threshold).

## G4 — protected bridge readout

The canonical edge-work exponent is **1.405**, 95% CI **[1.396, 1.416]**,
inside the 1.50 H3 bound through B3, with no completed-row semantic error.
B1 earns the live-capable label at **430 ms p95**. B3 does not earn its
research-usable label: **9.114 s p95** versus 2 s.

The surface gate remains fail/bounded because 789 B4 rows hit the frozen
resource rules. Probe behavior is kept separate from deterministic bridge
correctness, and all budget/topology failures use an explicit fallback.

## G5 — source-sink and two-dye fluid transport

All 1,320 held-out rows complete with exact numerical and legal-edge
invariants. The edge-update exponent is **1.064**, 95% CI
**[1.058, 1.073]**, inside the 1.25 bound through F3. F3 nevertheless misses
the absolute research-usable label at **45.714 s p95** versus 5 s. This is a
relative scaling pass, not a live-performance claim.

## G6 — combined factorial

All 679 completed rows preserve semantic invariants. Among 639 eligible
isolated-stage pairs, the maximum combined/isolated timing ratio is **1.532**
and p95 is **1.043**, both below the 2x interaction bound.

G6 remains fail/incomplete: one C07 row stops, and the 40 repeated C16-center
rows have no frozen `proof:center` isolated comparator. Adding a comparator
after observing the results would violate preregistration, so those rows remain
unpaired rather than being reinterpreted.

## G7 — captured FreeCiv transfer

All 40 claim-eligible CA2/CA4 pairs preserve the captured source ledger,
original subgraph, proof/candidate behavior, and clone quarantine. The maximum
timing ratio is **1.953** and the maximum RSS ratio is **1.066**, within the
frozen 2x transfer bound. These are amplified captured snapshots, not
engine-observed states.

## G8 — engine-backed shadow confirmation

### Completion and safety

All 20 fixed-seed pairs and all 40 arms reach turn 30 with valid event ledgers
on clean source. The shadows record 527 controller decisions, 1,349 bridge
events, 1,349 flow events, 4,412 flow projections, and 654 revisions. One pair
uses full-detail telemetry.

No shadow decision is authority-eligible. The audit finds no authority
violation, legal-binding failure, unsupported/stale atom, sampled detail
omission, safety downgrade, unhealthy flow, or unexplained fallback. All 931
controller fallbacks have declared explanations.

### Why the gate fails

Six fixed seeds lose exact control/shadow action parity:

| Seed | First divergence | Consequence |
|---:|---|---|
| 8803438 | turn 10, different destination for unit 136 | action counts/results and completion trace diverge |
| 8807688 | turn 9, different unit ID for the same destination | ordered action trace diverges only |
| 8826840 | turn 2, shadow moves unit 102 before control ends turn | action counts/results and completion trace diverge |
| 8852047 | turn 3, different destination for unit 107 | action counts/results and completion trace diverge |
| 8852936 | turn 5, different destination for unit 110 | action counts/results and completion trace diverge |
| 8883283 | turn 11, different unit ID for the same destination | ordered action trace diverges only |

Every first split is a unit-movement readout difference, not selection by an
authority-eligible PF-v2 decision. The evidence is consistent with shadow
instrumentation changing the timing of engine-facing state/readout, but this
campaign does not establish the lower-level causal mechanism. Exact parity was
the frozen contract, so this remains a correctness failure rather than being
dismissed as benign nondeterminism.

Natural volume exceeds the old reference on eight of nine required dimensions.
It reaches 2,107 atoms, 1,456 supports, 45 scopes, five cities, 21 units, nine
concurrent goals, 27 candidates, and 654 legal actions. It materializes **zero
explicit region scopes**, below the required reference of two. Other scope
kinds are not retroactively relabelled as regions.

### Natural scale and overhead

| Metric | Achieved maximum or distribution |
|---|---:|
| Atoms / supports / scopes | 2,107 / 1,456 / 45 |
| Cities / units / explicit region scopes | 5 / 21 / 0 |
| Concurrent goals / grounded candidates / legal actions | 9 / 27 / 654 |
| Proof chain depth / tree size | 1 / 4 |
| Control nodes / edges | 129 / 120 |
| Bridge nodes / flow iterations | 434 / 44 |
| Controller latency p50 / p95 / max | 1.688 s / 9.657 s / 17.014 s |
| FDAS turn contribution p50 / p95 / max | 0.311 s / 0.789 s / 1.638 s |
| Controller-process peak RSS p50 / p95 / max | 171.5 / 216.0 / 217.7 MiB |

The nearest synthetic tier begins at 2,500 atoms, so the 2,107-atom engine
point lies outside the synthetic work range. Projection-latency and RSS ratios
of 2.506 and 3.227 are therefore descriptive shape/integration comparisons,
not transfer acceptance tests.

## Frozen claim decision

The machine-readable manifest authorizes these positive labels:

- `correct-at-scale`: AtomSpace A0–A3; proof P0–P3; fluid F0–F3; captured CA2
  and CA4; and the explicitly listed completed combined tiers;
- `scales-predictably`: proof and fluid only;
- `research-usable`: P2 at 10k relevant proof records only; and
- `live-capable`: bridge B1 only.

It does not authorize whole-surface predictable-scaling labels for AtomSpace,
bridge, captured, or combined work. It does not authorize an engine parity
claim, a score/win-rate claim, a PeTTa performance comparison, or a conclusion
about distributed AtomSpaces.

## Reproducibility and evidence

- Machine-readable audit: `docs/freeciv/evidence/scalability-v1.json`
- Frozen claim manifest:
  `artifacts/freeciv/scalability-v1/claim-manifest.json`
- Engine cohort report:
  `artifacts/freeciv/scalability-v1/heldout/engine/report.json`
- Engine preregistration:
  `docs/freeciv/evidence/scalability-v1-engine-shadow-preregistration.md`
- Implementation plan and checkpoints:
  `agent-instructions/larger-atomspace-inference-depth-bridge-fluid-experiment-plan.md`
- Observability: Scale Lab reads the same audit and claim artifacts and shows
  G2–G9, natural engine volume, performance, mechanisms, transfer, parity, and
  claim boundaries.

The final audit command is:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/audit_scalability_campaign.py \
  --root artifacts/freeciv/scalability-v1 \
  --output docs/freeciv/evidence/scalability-v1.json \
  --bootstrap-resamples 10000
```
