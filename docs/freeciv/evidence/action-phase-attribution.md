# Action-phase latency attribution

Date: 2026-07-26

Status: complete two-seed engine attribution with exact action replay. This is
diagnostic evidence for selecting the next host-side optimization, not a
gameplay-score, win-rate, or end-to-end latency claim.

## Instrumentation

The live harness now separates the action phase into:

- authoritative state-refresh time, including every refresh performed after a
  submitted action;
- grounded impact-planner time, including every planner decision call; and
- the remaining non-refresh action time, which contains impact planning,
  action submission and acknowledgement, event/effect bookkeeping, and
  control-plan work.

The counters are normalized both per executed turn and, where applicable, per
refresh or planner call. They are diagnostic only and do not affect scheduling,
grounding, selection, or execution.

## Engine attribution

The fresh serial 30-turn cohort
`artifacts/freeciv/action-phase-attribution-20260726-a` used seeds 104729 and
104743, completed both games without infrastructure failures, and retained the
proxy patch digest
`72813abbb7c45be3cc357592dd0bba33ca3537178cd7c34482f5c5033c5e5dd5`.

| Measure | Two-seed mean | Share of action phase |
|---|---:|---:|
| Complete action phase | 136.301 ms/turn | 100.0% |
| Authoritative action refreshes | 82.984 ms/turn | 60.9% |
| Grounded impact planning | 27.999 ms/turn | 20.5% |
| Residual after refresh and impact planning | 25.317 ms/turn | 18.6% |
| End-turn submission | 12.487 ms/turn | 9.2% |

The cohort performed 0.967 action refreshes per turn at 84.316 ms per refresh.
It made 1.933 impact-planner calls per turn at 14.372 ms per call. The
non-refresh action residual before subtracting impact planning was
53.317 ms/turn.

The per-seed split was:

| Seed | Action | Refresh | Non-refresh | Impact planning |
|---:|---:|---:|---:|---:|
| 104729 | 85.353 ms/turn | 48.171 ms/turn | 37.181 ms/turn | 21.603 ms/turn |
| 104743 | 187.249 ms/turn | 117.797 ms/turn | 69.452 ms/turn | 34.395 ms/turn |

The refresh path is the largest component, but earlier receive and query
experiments showed that its synchronization waits are correctness-bounded.
The 14.372 ms local impact-planner call is therefore the next independently
optimizable target. The residual 25.317 ms/turn is the subsequent target once
planner internals are attributed.

## Behavioral acceptance

Relative to `artifacts/freeciv/summary-action-kinds-reuse-20260726-b`, both
games retained:

- exact ordered canonical action payloads;
- scores and margins 107/-2 and 112/-3;
- one necessary model selection and 29 canonical avoidances per game; and
- zero infrastructure failures.

## Verification

- Complete repository FreeCiv lane: 357 passed.
- Focused active-research continuation and canonical-singleton tests: 2 passed.
- Fresh two-game engine attribution cohort: 2 completed, 0 infrastructure
  failures.
- Both traces passed all 11 applicable top-level release-audit checks at
  `artifacts/freeciv/action-phase-attribution-release-audit-20260726/report.json`.
- Exact ordered-action comparison was empty for both seeds.
- Static compilation and whitespace checks passed.
- The repository-prescribed `just check` entry point was unavailable because
  `just` is not installed in the execution environment; the complete direct
  FreeCiv test lane above passed instead.
