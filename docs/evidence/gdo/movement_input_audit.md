# GDO-2A Movement Input Audit

Status: native route foundation implemented; clean-room parity gate open
Policy effect: opt-in experimental diagnostics and city-defence operation input
Audited repository commits: `bcfd8a6` (native route boundary) and `08f0900`
(replay retention)

## Decision

The pinned Freeciv boundary now exposes an opt-in, player-scoped native route
query from an exact own-unit state to each own-city tile. It reports explicit
reachability, first step and first-edge cost, total movement fragments, ETA,
remaining movement points, directions, and initial transport state. The proxy
caches results only for the exact turn, source revision, origin, movement
points, and transport state that produced them.

This closes the consequential live-input gap for city-defence routes without
claiming that the repository-owned clean-room movement model has achieved
parity. A matching native first edge is `EXACT_AUTHORITATIVE` because it is a
direct server result. The older explicit-cost one-edge inference remains
`HEURISTIC`, and unsupported or stale cases still abstain. No native route
result enables general movement-policy authority.

## Available authoritative inputs

| Source | Present | Usable now | Limitation |
|---|---:|---:|---|
| Snapshot/turn/source identity | yes | yes | Estimate is valid only for that exact revision and turn |
| Legal-action digest and canonical action bytes | yes | yes | Establishes that the exact first action was advertised |
| `unit_move` actor, direction, target x/y | yes | yes | The exact advertised first step can be matched to a native route |
| Own unit ID/type/type ID/tile/x/y | yes | yes | Type-to-class rules are not in the snapshot |
| Own `moves_left` | yes | yes | Included in the native-route cache key and response |
| Unit HP/activity | yes | partly | HP can affect movement in some rulesets; the applicable rule is absent |
| Map width/height/wrap flags | yes | yes | Retained after the audit correction |
| Native own-unit-to-own-city route | opt-in | yes | Direct server result; bounded to 64 requests and current exact unit state |
| Tile terrain/extras/owner/known | optional raw fields | partly | Terrain/extra IDs lack a snapshot-carried ruleset mapping |
| Exact current visibility | yes | yes | It must gate risk/blocker claims; absence is not evidence of emptiness |
| Packet-visible foreign units | yes | yes | Hidden occupancy must remain unknown |
| Current own cities | yes | yes | Foreign city records are not retained in the snapshot |

`ProxyStateDTO` validates map tile identity and preserves packet fields.
`AuthoritativeSnapshot` now also retains `wrap_x` and `wrap_y`. The current
grounded subset uses those flags only to validate one-edge adjacency; it does
not infer a complete Freeciv topology from them.

## Inputs present upstream and retained for fresh replays

The packet projection supplied to this repository can contain:

- `veteran`;
- `transported`;
- `transported_by`;
- `carrying`;
- `done_moving`.

The audit correction retains all five fields in `UnitState`. Fresh
`state_snapshot` events now also carry a versioned `grounded_context` containing
the complete normalized legal-action set, map-wrap flags, and lossless own and
visible-enemy unit movement/transport fields. Missing packet values remain
explicit `None`; the extraction report measures each input family separately
and never treats key presence as a grounded value. Historical v1 events remain
readable and are explicitly marked incomplete.

The packet-side process also has ruleset
terrain, extra, and unit-class packets, but the authoritative response exposes
only a ruleset-ready marker. Those omitted values still cannot be assumed by
the clean-room model. The native route endpoint is an explicit server-derived
result, not a reconstruction from omitted packets.

## Ruleset IR availability

The current clean-room ruleset compiler provides unit:

- `move_rate`;
- class name;
- flags;
- cargo classes;
- transport capacity;
- fuel.

It does not compile:

- terrain movement cost or terrain-class identity;
- road/rail movement rules;
- extra IDs and movement effects;
- unit-class movement flags;
- damage-slowing details;
- zones of control;
- topology;
- veterancy movement modifiers;
- action enablers or effect tables.

The GDO adapter now passes its immutable ruleset IR into every domain request.
Callers that do not supply an IR still produce `None` and force any dependent
model to abstain.

## Transport availability

The legal-action set can advertise `unit_board` and `unit_embark`, including
invalid reasons in the raw proxy response. Only valid actions survive snapshot
canonicalization. The snapshot now retains transported state, carrier identity,
and carried count, but lacks class-compatible seat and route data. Exact embark,
disembark, and transport-required path claims therefore remain unsupported.

## Hidden-information rule

A missing enemy, city, transport, or blocker on a non-visible tile is unknown,
not absent. A path may use known terrain outside current vision for geometric
analysis, but it may not claim current occupancy safety there. Future
occupancy, diplomacy, and enemy zones of control retain residual unknown mass.

## Supported native subset

When `pressure_native_movement_routes_enabled` is true, the live harness asks
for native routes only in `pln_authoritative` snapshots. The route result is
usable only when:

- its actor is a current own unit;
- its origin, movement points, transport state, turn, and source revision match
  the snapshot exactly;
- its destination is an own-city tile;
- its reachable/unreachable shape is internally valid;
- a reachable first step is also present in the current legal-action set.

For a non-transported matching route, the movement model emits an exact
first-edge transition and the city-defence analyzer may construct a multi-turn
defender operation using the server ETA. Transported routes are retained for
diagnostics but do not authorize defender movement.

## Clean-room subset

The following facts can be emitted as deterministic diagnostics for an exact
advertised adjacent move:

- canonical legal first action;
- actor and target identity;
- source/target coordinates;
- stable one-edge corridor digest;
- whether the target is currently visible;
- packet-visible occupancy and threat features.

Without a matching native result, movement cost, moves remaining, ETA, and
deterministic completion are supported only when an authoritative action or
tile record explicitly supplies the edge cost and every required
topology/transport modifier is present. Such explicit-cost inference remains
heuristic until the clean-room parity corpus passes.

## Correction status before parity work

1. Pass the immutable `RulesetIR` through `DomainEstimateRequest`: complete.
2. Retain topology flags and packet-visible unit transport/veteran fields:
   complete.
3. Add typed corridor identity independent of candidate ordering: complete for
   the one-edge subset.
4. Add a movement model with explicit missing-field reason codes: complete in
   shadow mode.
5. Add ruleset terrain/class/extra accessors or require authoritative
   precomputed edge cost: native route and first-edge values are now available;
   broader clean-room rule access remains open.
6. Add a separately installed native parity adapter; do not copy GPL
   implementation code: process boundary and runner complete; native
   executable/corpus pending.
7. Capture generated visible movement fixtures with engine/ruleset identities:
   complete for eight route-enabled city-defence snapshots; the randomized
   clean-room parity corpus remains pending.
8. Retain full legal actions, wrap topology, runtime unit fields, and exact
   native routes in fresh event replay artifacts: implementation complete;
   fresh engine replay capture complete.

## Exit status

The audit, conservative one-edge model, direct native route foundation, and
fresh engine replay capture are complete. Focused packet/proxy and repository
tests pass. The GDO-2A clean-room parity gate remains open: the required
randomized roads, rails, zone-of-control, impassable-terrain, transport, and
tie-breaking corpus has not been captured. Synthetic explicit-cost results
therefore remain `HEURISTIC`; only an exact, current server route match is
labelled `EXACT_AUTHORITATIVE`.
