# Phase 5 / V1-V2 evidence

Date: 2026-07-18 UTC

## Implemented surface

`apps/freeciv-observability` is a strict TypeScript React application whose only
domain input is the v1 event schema. Incremental JSONL parsing preserves unknown
events and quarantines malformed records. `foldEvents` implements a strict global
`(turn, seq)` cursor; URL state captures view, cursor, selection, search, and channel.
The timeline exposes causal ancestry, the proof explorer renders selectable AND/OR
nodes and formula inputs, and the atom view renders logged truth values/provenance.
Proof branches collapse after depth four but expose mouse and keyboard expansion;
proofs and atom tables page through bounded 500-row DOM windows without making later
records unreachable.
Missing event data produces a logging-gap diagnostic instead of reconstruction.

The source-boundary command reports nine production TS/TSX files and zero forbidden
agent, oracle, planner, belief, monitor, execution, or harness imports.

## Acceptance results

- P5.A1/P5.A9: the representative 200-turn, 50,000-atom fold completes below 10 s
  and predicate/argument search below 200 ms.
- P5.A2: cursor folds are indexed and the 200-turn scrub interaction test remains
  comfortably above 10 cursor changes/s on the recorded dev profile.
- P5.A3/P5.A8: independent folds match for 50 random cursors and 50 atoms.
- P5.A4: view, cursor, selected entity, search, and channel round-trip through a URL;
  a fresh render restores the linked proof node.
- P5.A5: the turn/action ancestry reaches its proposal and proof in four clicks.
- P5.A6: a 200-node proof DOM render is measured below 300 ms.
- P5.A7: the formula inspector exposes the exact confidence-producing step.
- P5.A10: boundary analysis is clean and logging-gap tests prove no view-side
  inference.

## Repeatable commands

```bash
npm --prefix apps/freeciv-observability test -- --run
npm --prefix apps/freeciv-observability run build
node apps/freeciv-observability/scripts/check-boundaries.mjs
```

Result: 18 UI tests passed and the production build completed. The real-engine
proof/paging ProofShot bundle is
`proofshot-artifacts/2026-07-18_10-07-09_verify-deep-proof-expansion-and-bounded`;
it contains three screenshots and video with zero console or server errors. The
Phase 12 ProofShot artifact also covers timeline, plan/map/audit/metrics views.
