# FDAS Phase 7 evidence: exact route-corridor scopes

Date: 2026-08-01
Branch: `experimental/functional-dependent-atomspace`
Capability: `route_corridor_projection=component-only`
Policy authority: disabled

## Realized scope

This increment introduces the route-corridor scope foundation used by later
expansion, escort, transport, and combat operations:

- one bounded, snapshot-retained scope is opened per current reachable native
  server-pathfinder result;
- the scope exposes actor, origin, destination, selected first step,
  reachability, and visibility class;
- numeric route length, directions, ETA, and movement cost remain in the exact
  support witness instead of leaking into ordinary symbolic atom terms;
- a current legal-step relation exists only when exactly one byte-identical
  advertised unit move reaches the server-selected first-step tile;
- route supports depend on the complete route identity, current unit revision,
  and source sequence; the legal relation additionally depends on the exact
  legal-action fingerprint;
- unreachable pathfinder results open no positive corridor scope, and a route
  without a legal current step remains reachable but non-actionable;
- same-turn legal-action retraction invalidates only affected support and is
  cold/incremental equivalent.

## Verification

The focused fixture verifies the full seven-predicate route view, exact tile
identities, server/derived authority boundary, bounded scope budgets, route and
legal dependencies, absent legal-step behavior, unreachable omission,
same-turn retraction, cold/incremental equality, catalog parity, and manifest
declaration.

The complete FDAS regression is run before commit.

## Claim boundary

Corridor atoms are exact structural inputs. They do not select a settlement,
infer unseen path safety, reserve movement points, authorize an action, or
establish transport/combat feasibility by themselves.
