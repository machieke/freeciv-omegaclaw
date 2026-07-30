# Native Movement Route Foundation

Status: implementation verified; live engine cohort pending
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

- Clean pinned upstream proxy suite: 49 passed.
- Freeciv packet generator: completed successfully for the modified packet
  schema and generated the new route response fields.
- Focused repository integration suite: 51 passed.
- Python syntax compilation: passed for the modified harness, turn-cycle,
  runtime, state, and domain-model modules.

A host-native Freeciv C build was not available because the host lacks the ICU
development dependency. The next verification step is to apply the pinned
series to the configured engine checkout, rebuild its container image, capture
a fresh route-enabled GDO-4 cohort, and replay the resulting exact routes.
