# Phase 7 / V3 evidence

Date: 2026-07-18 UTC

The Plan Board renders event-provided status, goal, source proof, steps,
predicted/actual turns, grade, cost, ledger, assumptions, and subtree-locality data.
The map renders only logged map/visibility/unit/uncertain-marker state and selected
plan spatial data; it never calculates paths. All views share one cursor and entity
selection.

## Acceptance results

- P7.A1: `decay-rescout.jsonl` fades the uncertain marker to the logged 0.30 opacity
  at its as-of cursor; no future revision is read.
- P7.A2: `invalidation-repair.jsonl` names `chokepoint-clear` in the same turn and
  displays `reused 1 / re-derived 1`.
- P7.A3: DOM assertions match logged predicted/actual turns, ledger rows, feasibility
  grade, and cost without UI arithmetic.
- P7.A4: plan-step, proof, action, and inspector navigation retains the global cursor.
- P7.A5: keyboard-addressable buttons/treeitems are covered by interaction tests.
  Proofshot captured the Plan Board and map overlay at 1280x720 with no browser or
  server errors.

## Evidence command

```bash
npm --prefix apps/freeciv-observability test -- --run
```

Visual report:
`apps/freeciv-observability/proofshot-artifacts/2026-07-18_09-23-22_verify-freeciv-decision-observatory-repl/SUMMARY.md`.
