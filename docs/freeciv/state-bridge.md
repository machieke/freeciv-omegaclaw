# Authoritative state bridge

The target agent reads the `pln_authoritative` proxy format, the conditional
source-stability extension described by `contracts/freeciv-proxy/v5/contract.json`,
the spatial projection described by `contracts/freeciv-proxy/v6/contract.json`,
and the sustainability controls described by
`contracts/freeciv-proxy/v7/contract.json`. The grounded server-side city
governor is described by `contracts/freeciv-proxy/v8/contract.json`. Exact
stable-government transitions and post-revolution selection are described by
`contracts/freeciv-proxy/v9/contract.json`. Bounded rate transitions and the
optional city-local happiness template are described by
`contracts/freeciv-proxy/v10/contract.json`.
Resource-flow, building-inventory, and score observations are described by
`contracts/freeciv-proxy/v11/contract.json`.
Apply the tracked patch series to the pinned external checkout before starting
its container:

```bash
export FREECIV_LLM_ROOT=/path/to/freeciv-llm
scripts/freeciv/apply_proxy_patch.sh "$FREECIV_LLM_ROOT"
docker restart fciv-net
```

The patch series is pinned to upstream commit
`26ba7124249f34fd3050ef29bf191bd4d8808018`. It retains complete player, research, city
output, unit upkeep, buildability, and ruleset-ready packet data and adds a monotonic packet
sequence. The authoritative-state and spatial-projection patch SHA-256 values are,
respectively,
`48e416000bf36c3c7ce13c8c59bb51bc682a1f17ee8568e432a82f673a10df55` and
`a4eb88c827c7a2ea68db602aa2463c2aa53bb0c6156a71e1a5a5e7fc09908856`.
The sustainability-control patch is pinned at
`412f4b462afab900233793f192732317b7e00b42b165dee1c09056ca9d5a1827`;
the city-food-governor patch is pinned at
`33a10ec287297629d2383d494f4ac01ad60ad1d25167dec39753e9d8a131113f`;
the government-transition patch is pinned at
`1b3ecb9458559b0552f232e41804e545a94ccd4d2d774a0f0e6c90dac8dd013c`;
the disorder-recovery patch is pinned at
`e800adbe5a4f3a8e68e30a4e21019ef92dabbb272b28ecd50d90c64e7dcb417b`;
and the strategic-observability patch is pinned at
`9a768dda13455760f5d02a3e66ebc3eae564c3b37c8965c77c9e9565c3656e44`.
The ruleset-name sanitizer patch is pinned at
`09480dc463d3347d26db27e387a5a528c6b525fb65089aa1f6f5cd1fb999ce67`.
The ordered ten-patch series identity is
`464d96f39d91cfae59fdac5f74170cfcb45a89aa14a6840118fb05f26c7ecb00`.
Reapplying the script is idempotent; it refuses an unpatched checkout at another commit.

The v9 projection closes the stable-government initiation gap. The proxy now
advertises every exact packet-known, ruleset-requirements-satisfied alternative
government while the player is stable. It advertises none while a revolution
countdown is active, then exposes the exact legal selection set when the
revolution finishes. The canonical action preserves government ID and name
through validation and conversion to `PACKET_PLAYER_CHANGE_GOVERNMENT`.
Strategic preference remains outside the proxy: the planner chooses only its
configured preferred target, only while the horizon retains recovery runway,
and prioritizes the packet-declared intended target after revolution. Unknown
requirements, unknown identifiers, and ID/name mismatches fail closed.

The v10 projection preserves strict booleans and integer bounds from legal
action generation through normalization, sanitization, validation, exact legal
membership, and packet conversion. Rate actions move one ten-point increment,
keep tax/luxury/science in `0..60`, and always total 100. A disordered city can
advertise the audited `PACKET_WEB_CMA_SET` template with
`require_happy=true`. These are transport capabilities, not proxy policy.
Engine evidence showed that global luxury starved research and that the local
happiness template was infeasible in the examined city states, so both planner
selectors are disabled by default.

The v8 transport also projects `GameSession.game_is_over` into every player's
authoritative `game.is_over` value. This closes the observer-first endgame-report
race: legal actions become empty, the current terminal revision is consumable
without a nonexistent next-turn packet, and the harness records an absorbing
terminal outcome. Release configuration now validates bounded `victories` and
exact-boolean `endspaceship` settings; fixed-horizon runs keep `SPACERACE`
enabled but disable arrival termination.

The v8 projection preserves the complete packet-observed Freeciv citizen
manager state for each owned city. The legal set exposes only a bounded
`city_governor` food-reserve intent; packet conversion expands it to the
audited `PACKET_WEB_CMA_SET` template. That template forbids disorder,
keeps specialists available, prioritizes food while retaining shield, trade,
and science value, and sets the exact configured food-surplus floor. Arbitrary
CMA weights are not accepted, capability is absent until the server publishes
the complete parameter block, and an already active exact template is not
advertised again.

The v7 player projection separates owned-city gold surplus, the packet-declared
gold-upkeep style, exact own-unit gold upkeep, and ruleset-aware net cash flow.
City surplus already contains costs paid by the city, so City-style upkeep is
not subtracted twice. Mixed-style upkeep subtracts nation-paid unit upkeep once.
Nation-style net flow fails closed until exact building upkeep is projected.
Missing required upkeep makes the net rate unavailable
instead of optimistic. The legal set exposes at most one ten-point tax increase
and one return toward the configured 40/60 tax/science split, always inside the
60-percent bound shared by stock governments. `unit_home_city` retains the exact
owned co-located city ID; `unit_disband` remains actor exact. Normalization,
sanitization, validation, packet conversion, and canonical legal-action membership
all preserve those identifiers.

The v11 strategic projection closes the long-horizon accounting gaps. Effective
gold now equals structural operating flow plus exact Coinage conversion; both
components remain separately observable. Research emits gross beakers,
technology upkeep, and net beakers. Owned-city improvement bitvectors become a
named building inventory with ruleset upkeep, and packet player scores become
an own/opponent score table. These remain observations: the proxy does not infer
building effects, military policy, or the cause of a score change.

The v6 projection emits only player-known `PACKET_TILE_INFO` records. Every
record has a bounded tile index and coordinates derived from the authoritative
map width; terrain, knowledge state, owner, resource, worked-tile, and extras
fields are copied only when present. `TILE_KNOWN_SEEN` records also populate the
exact `visible_tiles` index list. `TILE_UNKNOWN`, malformed indexes, and
out-of-map records are omitted rather than turned into evidence. Own
city/unit coordinates and packet-visible foreign units remain in their
existing entity projection.

`ProxyStateDTO` independently validates positive dimensions, tile bounds,
coordinate/index agreement, duplicate indexes, and visibility bounds. The
immutable event projection labels map coverage as `complete`, `partial`, or
`dimensions_only`, emits both visible indexes and derived coordinate pairs,
and keeps packet-visible foreign units under `map.visible_enemy_units` rather
than authoritative `own_state`. Grounded plan steps copy exact action target
coordinates into `step.spatial`. Existing dimensions-only traces remain
readable and never acquire reconstructed terrain or fog.

The patch defaults the proxy logger to `INFO` and moves per-action payload,
normalization, sanitization, validation, and full state-summary diagnostics to
`DEBUG`. Successful action and extraction-performance logging is opt-in in
`llm_config.json`; state-query lifecycle INFO, rejection, security-warning,
warning, and error records remain visible. Enable the corresponding action and
performance flags and set
`FREECIV_PROXY_LOG_LEVEL=DEBUG` before starting the proxy when payload-level
diagnostics are required.

The same tracked external patch retains Publite2's five-second restart backoff
for nonzero exits and launch errors but reduces clean zero-exit restarts to
100 ms. The harness never treats this timer as readiness: it still requires a
distinct process ID and an exact listening socket before connection.

Cacheable non-PLN state-response formats include the game ID, player, format,
turn, and monotonic packet sequence in both cache-layer identities. Parallel
games and same-turn packet revisions therefore cannot collide. PLN
authoritative projections bypass both 4 KiB caches because their release
payloads consistently compress to approximately 4.2--4.3 KiB; v4/v5 conditional
stability is their exact-revision reuse path. This avoids serializing and
compressing every full projection twice only to reject both inserts. Incoming
authoritative packets still invalidate cached city and technology actions, and
player ID `0` remains an ordinary valid cache owner during targeted eviction.
See [the cache-bypass smoke](evidence/pln-cache-bypass-smoke.md).

The authoritative handler builds only the packet-backed PLN projection on its
successful path. It does not pre-build the generic full-state representation;
that representation remains lazy and is loaded exactly once if authoritative
extraction fails and the manual fallback is required. A larger cache was
measured and rejected because authenticated decompression was slower than
rebuilding these projections; see
[the construction smoke](evidence/pln-lazy-state-construction-smoke.md).

The typed snapshot also retains the sorted action-kind set while its DTO
normalizes the exact legal action documents. The LLM query-summary boundary
reads that derived tuple instead of decoding every canonical action document a
second time. Full action payloads remain opaque to the summary, and the exact
canonical JSON plus digest remain the execution gate.

For a unit with the exact ruleset Found City capability, a movement action may
also carry `settlement_site_eligible`. The proxy emits the boolean only when
the adjacent destination tile packet exists and evaluates it with the same
packet-known terrain, owner, and visible-city-spacing checks as current-site
founding. The DTO requires an exact boolean, preserves it in canonical legal
JSON and its digest, and leaves the field absent when the destination is
unknown. The action handler strips this planner evidence while normalizing the
actual move to unit ID and coordinates, so it cannot alter the wire order.

An authoritative WebSocket state query may supply a non-negative
`after_source_seq` together with a bounded `wait_timeout_ms` in `1..5000`.
When the current sequence has not advanced, the proxy waits on a packet-update
event and wakes only after packet dispatch and storage complete. Timeout returns
the ordinary current `state_response`; legacy queries remain immediate. The
harness uses this only to avoid rediscovering a known stale revision and still
requires its separately timed identical-snapshot stability sample. Consecutive
samples at initial, inter-turn, and accepted-action boundaries are separated by
50 ms and must match the complete decision fingerprint; any state,
visible-enemy, or exact legal-action-digest change restarts the count.

The v4 `accept_unchanged` option is valid only with a bounded authoritative
source wait. Packet mutation and full projection construction share one
CivCom lock. If the complete wait expires with the exact turn and source
sequence unchanged, the proxy returns a compact `state_unchanged` response;
otherwise it returns ordinary full state. The harness treats that acknowledgment
as the independent later sample of its retained atomic projection. The 50 ms
quiet interval is unchanged, and any packet revision still triggers full DTO
parsing and decision-fingerprint comparison.

The v5 `settle_quiet_ms` option extends that proof without weakening it. After
a newer revision is available, the proxy builds a full projection under the
packet/projection lock, waits the requested quiet interval on that exact
revision, and rebuilds if any packet arrives. Only a projection whose source
sequence is still exact after the wait receives the
`authoritative.stability` marker. Turn-boundary queries use this marker to
complete their two-sample proof in one request. Accepted-action refreshes do
not: delayed effect packets can change same-turn planning after the ordinary
decision state is quiet, so those refreshes retain the longer v4
post-projection sample.

State responses may also include a top-level, non-authoritative
`server_timing` diagnostic. It attributes time spent waiting for packet
revisions or turn start, building projections, and proving an exact revision
quiet. The harness consumes these values only as performance metrics; the
field remains outside `data`, is not parsed into `AuthoritativeSnapshot`, and
cannot affect a decision fingerprint. Query latency minus the server's
pre-serialization elapsed time is reported separately as delivery overhead,
which includes JSON serialization, WebSocket delivery, and client scheduling.
The client also measures received UTF-8 bytes and JSON decode time, allowing
that residual to be split into decode and serialization/socket scheduling
without adding a protocol request.

The serial engine-live harness disables WebSocket per-message deflate by
default. Its proxy and client share a host, and fresh attribution showed that
the proxy's level-9 compression cost exceeded the loopback bandwidth saving.
Set `FREECIV_PROXY_WEBSOCKET_COMPRESSION=true` to restore `deflate` for a
remote proxy where bandwidth is the dominant constraint.

The observer-backed `global_state_response` carries its own authoritative
`turn`. The harness rejects a populated but stale observer response until its
turn reaches the associated player snapshot. After the final `end_turn`, score
collection requires `final_turn + 1`; an exact terminal player-elimination
packet uses `final_turn` because that state has no next begin-turn. This
turn-bound gate replaces timing-based endgame settling.

The global observer is outside the planner's truth boundary. Scheduler-enabled
runs choose grounded actions solely from the player-visible authoritative
snapshot, so they do not refresh observer state between turns. They query it at
startup for paired identity/fidelity and after the horizon for scoring. Plain
test-driver conditions retain per-turn observer queries because their scout
driver explicitly consumes global unit positions.

`PACKET_PLAYER_INFO.is_alive` is retained as
`authoritative.player.is_alive` and typed as `AuthoritativeSnapshot.player_alive`.
An exact false value suppresses stale cached own cities, units, and legal actions and
bypasses the proxy's post-`end_turn` wait for a new begin-turn packet. Missing status
fails closed for active decisions; it is never inferred from asset collections. This
preserves living city-owned states with zero units while making player elimination a
terminal game loss rather than an infrastructure timeout.

The release proxy's legacy `requests_per_second` setting is implemented as a count over
`window_seconds`, not as a literal per-second rate. The pinned configuration therefore declares
600 messages per 60-second window (10/second sustained) and a 1,200-message burst budget. Limits
remain scoped by unique agent ID and reset on turn end. This accommodates authoritative-state
polling by isolated parallel workers while retaining a bounded abuse ceiling; a proxy contract
test asserts the effective release rate.

City-production advertisements prefer the current server-normalized buildability IDs over
legacy raw bitvectors. This prevents obsolete or otherwise non-buildable targets from being
presented as legal merely because the raw web packet field was not retained.

City-founding advertisements also mirror the active ruleset's packet-known terrain gate.
The proxy reads bit `1` (`NoCities`) from the exact `PACKET_RULESET_TERRAIN.flags`
bitvector for the founder's current `PACKET_TILE_INFO.terrain`; a matching flag removes
`unit_build_city` from the legal set. This covers non-ocean terrain such as Glacier and
ruleset-specific land that the earlier terrain-class-only check missed. Unknown tile or
terrain packets remain unavailable rather than being guessed to carry the flag.
The same gate carries the acting player ID and rejects a packet-known tile owner other than
the actor or the protocol's unclaimed sentinel (`255`). This mirrors the Found City
enablers' `CityTile Claimed`/non-`Foreign` requirements and prevents accepted-but-ineffective
founding orders inside foreign borders.

Production-name sanitization accepts the bounded punctuation present in the compiled runtime
rulesets, including the comma in `Aqueduct, River` and the apostrophe in
`Women's Suffrage`. Both input-validation layers use the same alphabet, while the converter
still requires the name to resolve to the advertised numeric production kind and value. Thus
an exact advertised target remains executable without weakening command-injection rejection.

Freeciv's `PACKET_RESEARCH_INFO.inventions` array is indexed by the exact zero-based
technology ID. The patch preserves that indexing when it materializes known technology
names; a focused proxy regression and the live cognitive-loop smoke both guard against the
former one-position shift.

Freeciv's pinned `unit_activity` network enum is also centralized at the proxy boundary.
Incoming unit packets and outgoing activity commands share the exact 0--17 mapping from
`freeciv/common/fc_types.h`; unknown values remain explicitly `unknown` rather than being
reported as idle. This fixes stale outgoing pollution (`1`, formerly `7`) and transform (`9`,
formerly `8`) encodings and prevents completed fortification (`4`) from being mislabeled as
irrigation. The engine-backed activity probe at
`artifacts/freeciv/impact-activity-enum-probe-104729-v2-20260720` observed the exact
`fortifying` to `fortified` transition, completed both 30-turn arms with zero rejected
actions, and passed every paired safety gate.

Non-native movement legality also distinguishes a unit type's static embark capability from
an executable move. An ocean move is advertised only when a packet-visible, owned transport
is present at the exact target, its ruleset cargo bitvector includes the passenger's exact
`unit_class_id`, and its current `carrying` count is below `transport_capacity`. Full,
incompatible, missing, or foreign transports fail closed. The proxy retains current cargo and
transport identity from unit packets so this check does not infer availability from unit names.

Plain movement also respects exact packet-visible occupancy. A destination containing a
non-allied unit or city is not advertised as an ordinary move; alliance status is read from
authoritative player/diplomacy state. This guard does not replace attack, city-action, or
transport action grounding, and it does not infer invisible occupancy.

Hut movement uses explicit protocol semantics. The converter reads the destination tile's
`extras` as a Freeciv byte bitvector, resolves each selected ruleset extra, and requires its
exact `EC_HUT` cause bit. It then resolves the actor's numeric unit type and a statically
enabled hut-entry or hut-frighten action in the pinned `90`--`97` range. With all facts
present, it emits `PACKET_UNIT_DO_ACTION` (`pid=84`) against the exact tile; otherwise it
keeps the ordinary movement encoding. The clean engine probe at
`artifacts/freeciv/impact-hut-action-probe-104729-v3-20260720` confirmed the known hut
through this path with zero engine rejection or model fallback and all release-audit gates
green.

The same exact extra-cause resolver publishes sorted `known_hut_tiles` in the authoritative
state. `ProxyStateDTO` types and hashes those IDs as `known_hut_tile_ids`; the impact planner
may therefore route an explorer only along advertised moves that strictly reduce distance to
a packet-known hut. The converter still revalidates the tile immediately before transport,
so stale remembered extras fail closed to ordinary movement. The engine-backed route probe at
`artifacts/freeciv/impact-known-hut-route-probe-104729-20260720` exercised the field from the
first snapshot and passed the complete release audit.

`ProxyStateDTO` validates and immediately converts transport data into an immutable
`AuthoritativeSnapshot`; it does not retain the raw response. The snapshot identity is
`(game_id, turn, source_seq, state_hash)`. `SnapshotStore.replace` projects a complete new
authoritative atom set before swapping both values under one lock. It never revises a removed
own-state fact into uncertainty.

Quantities are accessed only through `GroundedRegistry`, whose public names must exactly equal
the signatures generated by the ruleset compiler. A missing packet field returns a typed
unavailable check. The crisp atomspace constructor rejects quantitative predicate names.

`StateSummaryService` is the only target LLM state boundary. It returns selected query values
and diagnostics, not the DTO, snapshot, legal payloads, or map packet body. `ExecutionGate`
requires the current snapshot ID, legal-set digest, exact normalized server action, ready
ruleset, city buildability where relevant, and current grounded checks before invoking its
transport.

Verification commands:

```bash
python3 -m pytest -q Autotests/test_freeciv_state_bridge.py
python3 scripts/freeciv/run_state_parity.py --turns 100
python3 scripts/freeciv/run_live_state_parity.py \
  --game-id <game> --agent-id <agent> --port <port> --turns 100
docker exec -w /docker/freeciv-proxy fciv-net python3 -m pytest -q \
  tests/test_pln_authoritative_state.py tests/test_tech_research.py \
  tests/test_bitvector.py tests/test_input_validation.py \
  tests/test_llm_handler.py::TestMessageValidator
```
