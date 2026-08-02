# FDAS captured rich-shadow replay

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Machine scope: local diagnostic replay  
Machine-readable report: `fdas-captured-shadow-replay.json`  
Report hash: `8d40c308a2edeb4fae0be153907388961b27f816ebd4735a1b9ad23ca880ae90`

## Corpus and strictness

The replay runner deduplicated all checked captured-snapshot manifests by path
and verified every fixture structural hash before parsing it. Of 47 unique
captures, 38 (80.85%) carry the modern grounded legal-action fields required
for strict snapshot reconstruction. Nine older captures are retained as named
data gaps; they are not silently treated as passes. There were zero parse,
projection, evaluation, or comparison failures among replayable snapshots.

The acceptance profile enables the full rich projector set, leaves all
authority flags false, and sets cold verification to 100%. Thirty-seven
incremental transitions were each compared with an independently rebuilt cold
revision; all 37 were canonically equivalent.

## Results

| Measurement | Result |
|---|---:|
| Cold projection p50 / p95 / max | 150.74 / 314.69 / 411.37 ms |
| Shadow readout p50 / p95 / max | 17.54 / 146.02 / 165.39 ms |
| Combined cold FDAS p50 / p95 / max | 181.16 / 410.16 / 504.80 ms |
| Maximum atoms / scopes / supports | 2,610 / 80 / 1,388 |
| Maximum dependency keys | 2,002 |
| Local goals / FDAS candidates | 116 / 855 |
| Relevant legacy candidates | 139 |
| Exact action overlap / explained missing | 87 / 52 |
| Optional unprotected candidates omitted by budget | 339 |
| Illegal FDAS bindings | 0 |
| Authority-eligible candidates / violations | 0 / 0 |
| Safety downgrades | 0 |

The 500 ms production-safe gate is a p95 gate: combined captured p95 is
410.16 ms. The single worst capture is 504.80 ms and the proposed 150 ms
ordinary FDAS contribution target is not met across this stress corpus. The
evidence therefore supports bounded shadow operation, not unrestricted
activation or authority.

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

## Non-claims

This diagnostic replay does not measure game score, win rate, action quality,
or outcome improvement. It does not promote the capability manifest beyond
`component-only`, authorize an FDAS candidate, close the nine historical data
gaps, or prove the 150 ms aspirational contribution target. The separately
recorded engine smoke validates live integration at one seed only.
