# FDAS Phase 6 evidence: exact reinforcement routes

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Capability: `unit_domain_projection=component-only`  
Policy authority: disabled

## Realized scope

This increment extends the Phase-6 defense substrate with native FreeCiv route
evidence:

- `movement.shortest-route(unit, destination-tile)` and
  `movement.arrival-eta(unit, destination-tile)` are typed `server_exact`
  groundings over the proxy's validated `freeciv-server-pathfinder` result;
- route results carry exact source-sequence and field-level movement-route
  dependencies, and the result cache remains snapshot/dependency bound;
- a missing route remains unavailable/unknown;
- an explicit unreachable server result retains its exact dependency witness,
  but cannot prove a positive route or instantiate a move candidate;
- a reachable route to a city with a factual garrison deficit produces a
  `unit-reinforcement-route(unit, city)` relation with first-step, path-length,
  and arrival-ETA evidence;
- multi-turn candidate regression accepts only a current legal `unit_move`
  whose target is either the city itself or the native route's selected first
  step;
- actor revision, route authority/schema, route reachability, turn,
  source-sequence, and origin tile are rechecked during candidate matching;
- source-city garrison protection is unchanged and remains an independent
  blocker.

The implementation intentionally does not infer an enemy arrival deadline from
visible distance. Until an exact threat-ETA source exists, the route ETA is
evidence about friendly arrival only. Action effects are still uncompiled, so
all reinforcement candidates remain expansion-only with zero act pressure.

## Verification

The focused FDAS unit/config/operation/pressure slice passed:

```text
27 passed in 17.12s
```

The route fixtures additionally prove:

1. an exact two-step server route projects a reinforcement relation;
2. the current eastward legal action is accepted as the byte-identical first
   step toward a city two tiles away;
3. a second source-city defender removes the protected-garrison blocker;
4. an explicit unreachable route remains unavailable, produces no positive
   atom, and instantiates no move operation.

## Claim boundary

This is component-only causal evidence. It does not establish operation
persistence, deadline satisfaction, defense authority, gameplay improvement,
or a score/win-rate claim.
