# GDO-6 transport input and capacity audit

Status: authoritative current-seat capacity and current-step transition model
implemented; operation assembly and fresh ferry/founder opportunity remain open

Date: 2026-07-30

Branch: `experimental/pln-pressure–bridge–fluid`

## Claim boundary

The current proxy, immutable snapshot, ruleset IR, and identity scheduler can
represent the exact number of free seats on a visible own transport for the
current turn. This is a prerequisite result only. It does not establish
rendezvous feasibility, embark or disembark execution, founder/ferry partner
locking, settlement completion, retention, or gameplay benefit.

## Authoritative input path

| Required fact | Source | Current status |
| --- | --- | --- |
| ferry identity and position | authoritative own-unit packet | available |
| current cargo count | authoritative `carrying` field | available in grounded snapshot |
| transported state and carrier identity | authoritative `transported` and `transported_by` fields | available in grounded snapshot |
| ferry capacity | compiled unit rule `quantitative.transport_cap` | available |
| accepted cargo classes | compiled unit trait `cargo` | available |
| founder capability | compiled unit flag `Cities` | available |
| legal embark edge | advertised `unit_move` with `transport_required=true` | supported by proxy, no retained live occurrence yet |
| legal disembark edge | advertised current action after embark | must be observed and audited |
| multi-turn ferry route | native route projection | transport subset currently abstains |

The proxy patch also checks for a compatible transport with remaining capacity
before advertising a land unit's move onto ocean. The client does not need to
invent embark legality.

## Corrected capacity contract

`ResourceCapacityExtractor` previously looked only for a synthetic
`transport_capacity` quantitative key. The actual ruleset compiler projects
the Freeciv field as `transport_cap`. Consequently, real Triremes with exact
`carrying` state produced a `transport-rules-missing` omission instead of a
`TRANSPORT_SEAT` capacity.

The extractor now treats `transport_cap` as canonical and retains
`transport_capacity` only as a compatibility alias. The regression compiles
the pinned `civ2civ3` ruleset, gives a visible Trireme one passenger, and
requires exactly one remaining seat with authority
`derived-ruleset-and-unit-state`.

This capacity is current-turn only. It does not promise that the ferry, seat,
pickup tile, or movement points will exist next turn.

## Grounded current-step model

`GroundedTransportTransitionModel` covers a deliberately narrow subset:

- the exact action bytes are server-advertised in the current snapshot;
- the actor and target are visible and the movement cost is explicit;
- embark has exactly one compatible own carrier at the destination;
- the compiler-backed cargo class accepts the actor's class;
- exact cargo count leaves at least one seat;
- disembark names an existing co-located carrier through authoritative
  `transported_by`;
- target occupancy is visibly clear.

For that subset the model emits a candidate-invariant, probability-one
current-step transition and the exact carrier seat delta. Ambiguous carriers,
full carriers, missing rules, missing carrier identity, hidden targets, stale
action bytes, or incompatible cargo classes abstain. This estimate remains a
standalone GDO-6 foundation and has not been registered as live authority.

## Observed opportunity boundary

Repository event traces contain visible empty Triremes with exact grounded
`carrying=0`, but the retained corpus currently contains no
`transport_required=true` advertised move and no own unit with
`transported=true`. A ferry/founder operation assembled solely from those
traces would therefore fabricate an embark transition.

GDO-6 must stay default-off while the next evidence step obtains a
player-visible engine snapshot containing:

1. one founder and one compatible ferry with exact identities;
2. an advertised embark move;
3. exact current free-seat capacity;
4. a native route or explicit abstention for the pickup and landing legs;
5. a post-embark snapshot that exposes carrier identity;
6. an advertised disembark move and subsequent settlement action.

## Next implementation gate

The first `FounderTransportOperationAssembler` should accept only that fully
grounded subset. Missing carrier identity, cargo compatibility, seat count,
or an advertised current step must yield explicit abstention. Future seats and
movement points must be conditional claims and converted to hard claims only
after the next authoritative snapshot. Generic path persistence and bridge or
fluid authority remain disabled.
