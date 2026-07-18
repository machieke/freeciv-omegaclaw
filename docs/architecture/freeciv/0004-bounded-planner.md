# ADR 0004: Use a deterministic bounded HTN planner

- Status: accepted
- Date: 2026-07-17
- Decision owner: PLN-FreeCiv implementation
- Applies to: M3

## Context

M3 needs fast topological technology schedules and production-interleaved plans over a
horizon of at most 30 turns. Pulling a large solver into the base runtime would expand the
container and make deterministic behavior dependent on a native third-party build.

## Decision

Implement a small deterministic hierarchical task network planner in Python for the
production-interleaved portion. It performs bounded branch-and-bound search over typed
tasks and a linear resource ledger, uses canonical tie-breaking, and returns an explicit
timeout or `NO_PLAN_WITHIN_HORIZON` result.

Tests use an independent exhaustive enumerator for compact instances as the optimality
oracle. Technology-only planning uses the specified greedy topological scheduler and is
compared with exhaustive optimum on sampled goals.

## Consequences

- No new native solver dependency is required.
- Search state, bound, branch selection, and timeout are inspectable plan events.
- The implementation must remain domain-specific and bounded; it is not a generic cron
  scheduler and does not perform logical inference.

## Reversal condition

Adopt a pinned CP-SAT/ILP backend only if the HTN implementation cannot satisfy the
30-turn scenario coverage or latency gates. A replacement must preserve deterministic
tie-breaking and typed failure results.

