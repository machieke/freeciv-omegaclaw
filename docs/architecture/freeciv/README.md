# PLN-FreeCiv architecture decisions

These records resolve the implementation choices required by Phase 0 of
`agent-instructions/pln-freeciv-implementation-plan.md`.

| ADR | Decision |
|---|---|
| 0001 | One compiled target rule with independently audited prerequisite edges |
| 0002 | Canonical-IR crisp proof service; generated Atomese remains auditable output |
| 0003 | Native FreeCiv test executable is the parity authority |
| 0004 | Deterministic bounded HTN planner, with an exact test oracle |
| 0005 | JSON Schema is the event wire source of truth |

The decisions may only be changed by a superseding ADR. Acceptance evidence belongs
in run artifacts and CI, not in these records.

