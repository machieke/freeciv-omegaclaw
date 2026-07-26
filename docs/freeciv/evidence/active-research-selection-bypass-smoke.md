# Active-research selection bypass smoke

Date: 2026-07-26

Status: focused policy coverage, two independent two-seed engine treatments,
exact-behavior replay, and release validation passed. This is a
model-selection and loop-throughput result, not a gameplay-score or win-rate
claim.

## Root cause and invariant

The constrained planner invoked goal selection on every turn even when the
exact proxy legal-action set advertised no executable research choice. While a
research target is active, that target is the only mechanically relevant
continuation goal. Selecting between unrelated future technologies cannot
produce an engine action on that turn.

The existing `canonical-singleton-bypass-v1` policy now constructs the active
research goal as its single constrained catalog target only when:

1. the authoritative snapshot names an active research target;
2. the exact legal-action set contains no new research selection; and
3. the active name resolves to a non-disabled compiled ruleset technology.

The proposal still passes through the strict constrained parser, symbol
catalog, goal grader, dependency oracle, and scheduler. A turn with two or more
executable research choices still calls `qwen3-coder-next:latest`.

## Engine comparison

All cohorts used seeds 104729 and 104743, a serial 30-turn topology, the
retained proxy digest
`72813abbb7c45be3cc357592dd0bba33ca3537178cd7c34482f5c5033c5e5dd5`,
and otherwise identical configuration:

- control: `artifacts/freeciv/receive-attribution-20260726-a`;
- treatments: `artifacts/freeciv/active-research-bypass-20260726-a` and
  `artifacts/freeciv/active-research-bypass-20260726-b`.

The treatment column is the mean of both independent treatment cohorts.

| Measure | Control | Treatment mean | Change |
|---|---:|---:|---:|
| Logical model-selection call rate | 1.000 | 0.033 | -96.67% |
| Selection-call avoided rate | 0.000 | 0.967 | +0.967 |
| Cognitive latency | 108.681 ms/turn | 100.721 ms/turn | -7.32% |
| Complete full-turn work | 252.238 ms/turn | 248.415 ms/turn | -1.52% |
| Mean turn loop | 408.916 ms/turn | 404.780 ms/turn | -1.01% |

The verified-response cache had already made repeated identical prompts
zero-generation fast paths, so reported generation latency did not decrease:
each first game still made the one necessary selection call. The retained gain
comes from removing 29 redundant per-turn proposal/cache lookup, parsing,
grading, and alternate-goal planning paths.

## Behavioral acceptance

All four treatment games retained, relative to the control:

- exact ordered canonical action payloads;
- scores and margins 107/-2 and 112/-3;
- 48/70 total engine actions and 18/40 planned actions;
- one/two completed settlements;
- zero rejected actions and zero model fallback;
- one necessary selection call and 29 canonical avoidances per game; and
- unchanged authoritative-state and 50 ms stability behavior.

## Verification

- Complete repository FreeCiv lane: 356 passed.
- Focused selection, catalog, and configuration lane: 4 passed.
- Both two-game treatment cohorts completed without infrastructure failures.
- Four treatment traces passed all 13 top-level release-audit checks.
- Exact ordered-action comparison was empty for both seeds in both cohorts.
- Static compilation and whitespace checks passed.
