# FDAS Phase 6 evidence: exact defender removal deficit

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Capability: `unit_domain_projection=component-only`  
Policy authority: disabled

## Realized scope

This increment replaces the candidate factory's one-defender shortcut with an
exact, typed opportunity-cost boundary:

- `defense.removal-deficit(unit, policy-limit)` computes the unit's current
  source city, current policy-qualified defender count, required count,
  remaining count after removal, and whether removal creates a factual deficit;
- the grounding depends on exact current city/unit fields, the policy limit
  supplied as a typed input, and the compiled defender catalog;
- requirements reproduce the existing disorder and observed martial-law/mood
  policy branches rather than assuming every city needs exactly one unit;
- every local defender whose removal would violate the policy receives a
  deterministic `unit-critical-garrison(unit, city)` relation;
- garrison reinforcement candidates now consume the same grounding and retain
  the existing `protected-source-garrison` blocker when it reports a deficit;
- grounding unavailability creates an explicit opportunity-cost blocker rather
  than silently permitting removal.

## Verification

The focused unit-defense suite passed:

```text
10 passed in 16.17s
```

One regression fixture sets a size-three source city to disorder with two
defenders. The prior `count <= 1` shortcut would have permitted one defender to
leave; the grounded policy requires three, proves that the remaining count of
one is deficient, and blocks the move.

## Claim boundary

This grounding is an exact safety/opportunity-cost constraint, not a utility
estimate. It does not choose a reinforcement, reserve the unit, authorize a
move, or establish gameplay improvement.
