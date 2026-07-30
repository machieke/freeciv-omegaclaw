# GDO-6 transport input and capacity audit

Status: authoritative seat capacity, current-step transition model, and
shadow operation/lifecycle slice implemented; fresh ferry/founder opportunity
remains open

Date: 2026-07-30

Branch: `experimental/pln-pressure–bridge–fluid`

## Claim boundary

The current proxy, immutable snapshot, ruleset IR, and identity scheduler can
represent the exact number of free seats on a visible own transport for the
current turn. The shadow GDO-6 slice can also bind one founder to one compatible
ferry, derive current rendezvous ETAs from native routes, reserve and
revalidate one exact legal step at a time, and resolve settlement retention at
a fixed horizon.

These results are synthetic and contract-level. They do not establish live
embark or disembark execution, completed engine-backed settlement, lower
rendezvous latency, or gameplay benefit.

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

## Founder/ferry operation slice

`FounderTransportOperationAssembler` adds an immutable, partner-locked
operation over seven phases:

1. founder moves toward the pickup edge;
2. ferry moves to the pickup tile;
3. founder embarks on the locked ferry;
4. ferry follows a native route to the landing corridor;
5. founder disembarks at the declared landing tile;
6. founder follows a native route to the settlement target;
7. founder submits the advertised city-building action.

The slower rendezvous participant moves first, which is a deterministic
critical-path rule rather than generic path persistence. Every movement
readout requires a current native route whose first edge is the exact
server-advertised move. Embark requires the declared ferry to be the only
compatible carrier with a free seat on the pickup tile. A carrier-identity
change abandons the operation rather than silently switching partners.

The operation's `RequirementSet` binds:

- founder identity and compiler-backed city-founding capability;
- ferry identity, cargo compatibility, and current free capacity;
- known pickup, carrier-landing, disembark, and settlement tiles;
- native rendezvous routes that fit the explicit deadline;
- the current conservative escort policy.

Visible enemy occupation of any declared critical tile causes abstention
until a grounded escort-survival estimator exists. Supplying an escort without
that estimator also abstains. No unconditional escort persistence is enabled.

## Resource and lifecycle semantics

Only the current step receives hard claims:

- the acting unit;
- exact movement points when applicable;
- one controller action slot;
- the locked ferry during embark/disembark;
- one exact seat during embark.

Founder, ferry, seat, pickup, landing, and settlement identities after the
current turn are `CONDITIONAL_FUTURE` claims. They affect operation identity
and diagnostics but do not manufacture future authority. The lifecycle
releases the current claims after every accepted step and requires a new
snapshot, route/action readout, schedule, and reservation before continuing.

Synthetic lifecycle regressions now cover:

- initial partner locking and deterministic operation identity;
- rendezvous deadline rejection;
- incompatible or full ferry rejection;
- ambiguous compatible ferries at pickup;
- one-seat/two-founder non-overallocation;
- exact embark, ferry leg, disembark, settlement leg, and city creation
  readout;
- carrier partner-switch abandonment;
- stale-snapshot commit rejection and claim release;
- blocked-step repair only after a new grounded route appears;
- one bounded replacement ferry/corridor when its grounded bid clears an
  explicit replacement margin;
- settlement identity and ownership at a fixed retention horizon.

The runtime flag `pressure_transport_operations_enabled` is default-off. It
requires scalar-v2 semantics, grounded estimates, RequirementSets, identity
resources, operation lifecycle, commit revalidation, and native movement
routes. Enabling native routes for this slice no longer requires enabling
city-defence operations.

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

The remaining gate is a captured and then fresh engine-backed ferry/founder
sequence. The retained corpus cannot be used to fabricate it: there is still
no observed embark or transported-founder state. Once such an opportunity is
available, the replay must demonstrate exact action attribution, zero seat
over-allocation, bounded partner switching, claim release, and retained
settlement observation. Generic path persistence and bridge or fluid authority
remain disabled.
