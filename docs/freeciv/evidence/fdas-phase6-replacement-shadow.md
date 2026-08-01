# FDAS Phase 6 evidence: coordinated defender replacement

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Capability: `unit_domain_projection=component-only`  
Policy authority: disabled

## Realized scope

This increment adds the exact structural prerequisite that was missing between
protected-garrison safety and coordinated reinforcement:

- `city-replacement-defender-available(city, replacement)` identifies a spare
  persistent defender with a current native route into a protected source city;
- `unit-coordinated-replacement-for(replacement, protected, city)` links that
  spare defender to the exact critical defender it can replace;
- the relation requires an exact server-pathfinder route, current route/ETA
  dependencies, and a byte-identical legal first movement step;
- `defense.removal-deficit` must prove that moving the replacement creates no
  deficit at its own current assignment;
- the protected unit's positive removal deficit remains in the witness, so the
  relation represents a replacement route rather than erasing the constraint;
- all policy, city-count, unit/removal, route, ETA, and legal-action inputs are
  dependency-backed and retract with a same-turn source-sequence update.
- `CandidateOperationFactory` can consume the replacement and target
  reinforcement atoms to assemble a persistent two-part operation: the spare
  defender occupies the protected source city first, then the formerly
  critical defender reinforces the deficit city;
- the current replacement move is byte-identical legal, while the second move
  is explicitly a future step that must be refreshed on its later snapshot;
- current and conditional-future unit resources remain separate, and atom plus
  support identities are carried into candidate provenance.

## Verification

The deterministic fixture establishes one critical defender in Rome and one
spare defender outside a city. With an exact native route and matching legal
first step, both replacement relations are projected with route and
legal-action dependencies. The relations are absent when:

- the legal first step is removed; or
- the proposed replacement is itself the critical defender of another city.

A second fixture combines a source replacement route with an exact target
reinforcement route and verifies participant roles, ordered step targets,
current/future resource identities, legal first-step binding, causal
atom/support provenance, and disabled authority.

The complete FDAS and city-defense regression is run before commit.

## Claim boundary

This increment assembles a shadow operation schema but does not activate its
lifecycle, reserve either unit, execute either step, waive the source-garrison
invariant, or grant policy authority. The compiled ruleset still reports the
movement effect as unknown, so the candidate retains its existing
`uncompiled-action-effect` blocker.
