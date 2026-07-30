# Native Movement Route Foundation

Status: implementation and live engine cohort verified; policy gate remains closed
Scope: GDO-2A input foundation and GDO-4 multi-turn defender routes
Policy: opt-in experimental; default off

## Result

Pinned upstream patch
`scripts/freeciv/upstream/0013-pln-native-movement-routes.patch` adds an
explicit player-scoped route response to the existing Freeciv web-goto
request. The authoritative projection exposes only exact-current results for
own units to own-city destinations. The implementation also corrects the
server's route-cost accumulation to use each path position rather than
repeating the first edge.

Patch SHA-256:
`e2d2681acdeb53a2b3ace5fb519273d83e5acb20dcadfb2cc590fa16da4c023e`

Thirteen-patch series SHA-256:
`8f4244e66b8260fc29d553ee0ed9d7018e26f2a232c544cff5859bc3fd5e51dd`

## Safety boundary

- Route collection is requested only with `pln_authoritative` format.
- Requests are bounded to 64 current own-unit/own-city pairs.
- Cache identity includes unit, origin, movement points, transport state, turn,
  and response source sequence.
- Stale, malformed, foreign-unit, off-map, or state-mismatched routes fail
  closed in `ProxyStateDTO`.
- Adjacent legal actions receive a movement cost only when all current native
  routes sharing that first step agree on the first-edge cost.
- Transported routes do not authorize defender movement.
- The default flag is false; the GDO-4 profile explicitly enables it.

## Grounded behavior

`NativeMovementModel` emits `EXACT_AUTHORITATIVE` only when the advertised
adjacent move is the exact first step of a current native route. The estimate
retains route provenance and a `native-server-direct` parity status. Otherwise
the previous heuristic/abstention behavior remains intact.

`CityDefenseAnalyzer` uses a reachable current native route to create a
multi-turn `unit_move` operation whose arrival turn is the current turn plus
the server ETA. With no exact route, it retains the
`defender-route-eta-unavailable` abstention.

This is direct engine authority, not evidence that the repository-owned
clean-room solver has achieved parity. The randomized GDO-2A parity corpus and
the broader movement-rule supported subset remain open.

## Verification

- Clean pinned upstream proxy suites: 160 passed, 4 skipped.
- Freeciv packet generator: completed successfully for the modified packet
  schema and generated the new route response fields.
- Full Freeciv C container build and link: passed.
- Focused repository integration suites: passed.
- Python syntax compilation: passed for the modified harness, turn-cycle,
  runtime, state, and domain-model modules.
- Two fresh 160-turn engine-live games: completed at the fixed horizon with
  zero event-schema warnings or errors and zero rejected engine actions.
- Native route observations: 1,263/1,263 reachable for seed 104743 and
  9,699/9,825 reachable for seed 4543804.
- Mean route-response wait per state request was 2.31--16.21 ms at turn
  boundaries and 0.58--1.18 ms during action refreshes across the two games.
- Eight retained defence snapshots replayed deterministically with a 12.68 ms
  p95 compute time. After correcting enemy speed and deadline semantics, 7/13
  requirements have a timely action, while all 192 operation comparisons and
  all 13 requirements have decision-grounded positive or negative results.

The detailed cohort and replay evidence is in
`docs/evidence/gdo/gdo4_native_route_160_replay.md`. This evidence establishes
the route input and its measurable effect on candidate support. It is not a
score claim: the two seeds are not a paired policy comparison, the operation
readout is shadow-only, exact assignment still ties greedy, and counterfactual
operation outcomes remain unavailable.
