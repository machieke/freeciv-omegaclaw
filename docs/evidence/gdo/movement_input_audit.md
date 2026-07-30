# GDO-2A Movement Input Audit

Status: blocking audit complete; model support not yet approved
Policy effect: none
Audited repository commit: `97ff07b`

## Decision

The current boundary can identify an advertised one-step `unit_move`, its
actor, source, target, and current snapshot validity. It cannot yet reconstruct
Freeciv movement cost, multi-step reachability, ETA, native-terrain rules,
roads/rails, zones of control, or transport transitions safely.

The first movement model must therefore abstain outside a deliberately small
declared subset. No movement authority is permitted by this audit.

## Available authoritative inputs

| Source | Present | Usable now | Limitation |
|---|---:|---:|---|
| Snapshot/turn/source identity | yes | yes | Estimate is valid only for that exact revision and turn |
| Legal-action digest and canonical action bytes | yes | yes | Establishes that the exact first action was advertised |
| `unit_move` actor, direction, target x/y | yes | yes | Describes only one adjacent advertised step |
| Own unit ID/type/type ID/tile/x/y | yes | yes | Type-to-class rules are not in the snapshot |
| Own `moves_left` | yes | yes | Protocol movement fragments are present, but edge cost is not |
| Unit HP/activity | yes | partly | HP can affect movement in some rulesets; the applicable rule is absent |
| Map width/height/wrap flags | yes | yes | Retained after the audit correction |
| Known tile records | optional | partly | Captured GDO fixture currently has zero tile records |
| Tile terrain/extras/owner/known | optional raw fields | partly | Terrain/extra IDs lack a snapshot-carried ruleset mapping |
| Exact current visibility | yes | yes | It must gate risk/blocker claims; absence is not evidence of emptiness |
| Packet-visible foreign units | yes | yes | Hidden occupancy must remain unknown |
| Current own cities | yes | yes | Foreign city records are not retained in the snapshot |

`ProxyStateDTO` validates map tile identity and preserves packet fields.
`AuthoritativeSnapshot` now also retains `wrap_x` and `wrap_y`. The current
grounded subset uses those flags only to validate one-edge adjacency; it does
not infer a complete Freeciv topology from them.

## Inputs present upstream but lost at this boundary

The packet projection supplied to this repository can contain:

- `veteran`;
- `transported`;
- `transported_by`;
- `carrying`;
- `done_moving`.

The audit correction now retains all five fields in `UnitState`. Missing
packet values remain explicit `None`. The packet-side process also has ruleset
terrain, extra, and unit-class packets, but the authoritative response exposes
only a ruleset-ready marker. This repository must not assume those omitted
packet values.

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

## Initially supportable subset

The following facts can be emitted as deterministic diagnostics for an exact
advertised adjacent move:

- canonical legal first action;
- actor and target identity;
- source/target coordinates;
- stable one-edge corridor digest;
- whether the target is currently visible;
- packet-visible occupancy and threat features.

Movement cost, moves remaining, ETA, and deterministic completion are supported
only when an authoritative action or tile record explicitly supplies the edge
cost and every required topology/transport modifier is present. No current
captured fixture meets that stricter subset, so current live candidates must
abstain rather than receive fabricated precision.

## Correction status before parity work

1. Pass the immutable `RulesetIR` through `DomainEstimateRequest`: complete.
2. Retain topology flags and packet-visible unit transport/veteran fields:
   complete.
3. Add typed corridor identity independent of candidate ordering: complete for
   the one-edge subset.
4. Add a movement model with explicit missing-field reason codes: complete in
   shadow mode.
5. Add ruleset terrain/class/extra accessors or require authoritative
   precomputed edge cost: explicit edge cost is supported; broader rule access
   remains open.
6. Add a separately installed native parity adapter; do not copy GPL
   implementation code: process boundary and runner complete; native
   executable/corpus pending.
7. Capture generated visible movement fixtures with engine/ruleset identities.

## Exit status

The audit and conservative one-edge shadow implementation are complete. The
GDO-2A parity gate remains open. Even a synthetic explicit-cost result is
labelled `HEURISTIC` and is not live-eligible until a native corpus passes.
Current captured moves lack authoritative edge cost and therefore abstain.
