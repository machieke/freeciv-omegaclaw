# FDAS captured rich-shadow replay

Date: 2026-08-02
Branch: `experimental/functional-dependent-atomspace`
Machine scope: local diagnostic replay
Machine-readable report: `fdas-captured-shadow-replay.json`
Report hash: `7eea020650511ef3c67a07e1fbc6ff0f788d561bef85539d1e4a62fcb6549fd3`

## Corpus and strictness

The replay runner deduplicated all checked captured-snapshot manifests by path
and verified every fixture structural hash before parsing it. Of 47 unique
captures, 38 (80.85%) carry the modern grounded legal-action fields required
for strict snapshot reconstruction. Nine older captures are retained as named
data gaps; they are not silently treated as passes. There were zero parse,
projection, evaluation, or comparison failures among replayable snapshots.

The schema-1.1 acceptance profile independently enables the full rich
projector set, leaves all authority flags false, and sets cold verification to
100%. Thirty-seven
incremental transitions were each compared with an independently rebuilt cold
revision; all 37 were canonically equivalent.

## Results

| Measurement | Result |
|---|---:|
| Cold projection p50 / p95 / max | 201.30 / 396.63 / 433.57 ms |
| Shadow readout p50 / p95 / max | 17.97 / 187.79 / 211.83 ms |
| Combined cold FDAS p50 / p95 / max | 257.33 / 543.77 / 603.03 ms |
| Strict incremental plus cold verification p50 / p95 / max | 499.21 / 924.66 / 1,057.23 ms |
| Incremental recomputation ratio mean / p50 / p95 | 0.779 / 0.755 / 0.888 |
| Maximum atoms / scopes / supports | 2,610 / 80 / 1,388 |
| Maximum dependency keys | 2,002 |
| Local goals / FDAS candidates | 116 / 855 |
| Relevant legacy candidates | 139 |
| Exact action overlap / explained missing | 87 / 52 |
| Optional unprotected candidates omitted by budget | 339 |
| Illegal FDAS bindings | 0 |
| Authority-eligible candidates / violations | 0 / 0 |
| Safety downgrades | 0 |

The 500 ms production-safe gate is a p95 gate. Cold projection alone remains
below it at 396.63 ms, but projection plus shadow readout is 543.77 ms p95 and
therefore does not pass the controller-inclusive gate in this stress corpus.
The proposed 150 ms ordinary FDAS contribution target is also not met here.
The evidence supports bounded diagnostic shadow operation, not unrestricted
activation or authority.

The strict incremental timing is diagnostic rather than a live-controller
timing: every transition prepares an incremental revision and a second,
independent cold revision before publishing the already-verified incremental
revision. All 37 transitions were equivalent. The sparse corpus changes most
domain roots between captures, so it recomputes 77.9% of records on average.
It records three region and four combat-projector cache hits whose reused
outputs are empty. Entity sharding additionally reuses 81 non-empty
city/economy records across five partial projector updates: city 101 four
times, city 109 four times, city 127 twice, city 131 three times, and city 182
once.

A separate same-turn full-rich fixture provides the positive ordinary-update
check. It reused city/economy, region, combat, and population-recovery output,
including 11 non-empty rich records; recomputed 7 of 30 total records; matched
the independent cold revision; and completed the strict two-build check in
24.32 ms. In a focused two-city fixture, a city-surplus mutation recomputes the
empire and changed-city shards, reuses two non-empty records from the unchanged
city, recomputes 11 of 30 total records, and remains cold-equivalent.

## Candidate interpretation

The native FDAS readout caps optional alternatives per active goal. Every
legacy candidate action is placed in a protected union before that cap. Legacy
categories with a matching active FDAS deficit are projected as explicit
comparison routes; when no compiled effect proves the transition, they carry
`legacy-shadow-control-route-uncompiled` and cannot receive action authority.

The 52 missing legacy candidates are not legal-action loss. Their captured
categories had no corresponding active strict FDAS deficit in that snapshot:

- 31 proactive food-production routes;
- 12 production-repurpose routes without a production-stalled deficit;
- 4 expansion-production routes, for which this local goal factory has no
  expansion goal;
- 2 defense-production routes without a current garrison deficit;
- 2 tax-restoration routes without a current treasury deficit;
- 1 governor route without a current food deficit.

This is the required differential explanation rather than a fabricated goal.
Any future authority slice must define and validate the missing lifecycle or
predictive goal semantics before treating these candidates as causal.

## Performance changes validated by this run

- Grounding wildcard dependencies use a snapshot-local sorted prefix index
  instead of repeatedly sorting and scanning the entire fingerprint map.
- Economy supports depend on the exact selected aggregate/fallback fields and
  narrow per-unit upkeep paths rather than every unit field.
- Route corridors parse and index the canonical move catalog once per snapshot.
- Grounded candidate operation identity includes an optional stable action
  binding, preventing collisions between simultaneous legal alternatives.
- Optional candidates are capped per goal while protected legacy comparison
  bindings remain lossless and omission counts remain observable.
- Rich projectors declare conservative snapshot-root and durable-source
  dependencies. The component cache reuses output only when its complete input
  digest and scope set match, refreshes exact revision validity, and otherwise
  recomputes fail-closed.
- Root and durable-kind digests are indexed once and boundedly cached, avoiding
  repeated serialization of overlapping dependency maps. Reuse/recompute
  projector IDs, record counts, and the recomputation ratio are emitted in
  materialization metrics and captured by this report.
- City/economy output is split into exclusive empire and per-city shards with
  conservative prefix/kind fingerprints. Runtime access, support dependencies,
  scope ownership, and cold equivalence are checked fail-closed; shard IDs are
  included in per-snapshot and aggregate replay metrics.

## Non-claims

This diagnostic replay does not measure game score, win rate, action quality,
or outcome improvement. It does not promote the capability manifest beyond
`component-only`, authorize an FDAS candidate, close the nine historical data
gaps, or prove the 150 ms aspirational contribution target. The separately
recorded engine smoke validates live integration at one seed only.
