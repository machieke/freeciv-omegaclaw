# GDO-4 player-known terrain and route-refresh confirmation

Status: diagnostic mechanism gates pass; live policy authority remains disabled

Date: 2026-07-30

Branch: `experimental/pln-pressure–bridge–fluid`

## Question

The preceding GDO-4 replay left two apparent coverage gaps:

1. a visible Sea-class threat had no player-safe proof that it could or could
   not approach one city; and
2. two defender/city operation comparisons lacked a current native route
   result even though a same-key route existed in the proxy cache.

This increment tests whether packet-known terrain semantics and exact route
revision validation resolve those gaps without consulting hidden map state or
granting city-defence policy authority.

## Grounding changes

Upstream proxy patch `0014-pln-known-terrain-semantics.patch` exposes the
public map topology and enriches only player-known tiles with public ruleset
terrain name, land/ocean class, and native unit-class membership. Its SHA-256
is:

```text
c6b813be4dd6b7c2f2679f8aa2444f0fffb36597e23fb403ee1201d497ffdd81
```

The independently written reachability analyzer uses those facts in Freeciv
native coordinates. It can prove a positive player-known native corridor, a
known non-native source, a locally closed non-native city approach, or a
closed known component. Any open boundary remains `unknown`.

Upstream patch `0015-pln-route-refresh-validity.patch` fixes the second gap.
The bounded route wait now treats a response as complete only when it matches
the current unit origin, movement allowance, transport state, destination,
and turn. A stale route with the same unit/destination key can no longer
masquerade as a fresh response. Its SHA-256 is:

```text
594fee9fd8cf07237cfc83036842aba1e0171d3ac1f01b99ea93b43618bea7e7
```

The ordered 15-patch series identity is:

```text
5a8cf967816ac6e692c27fae0cce59755ce27ea23e184c452a2aae0da767974e
```

The release audit verified all patch digests, the pinned upstream commit
`26ba7124249f34fd3050ef29bf191bd4d8808018`, and the applied series.
The complete FreeCiv regression selection passed 926 tests; the proxy
authoritative-state and release-configuration selection passed 69 tests.

## Fresh engine cohort

The retained command was:

```text
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness_gdo4_160_turn.yaml \
  --out artifacts/freeciv/gdo4-known-terrain-160-20260730 \
  --backend engine-live --workers 1 --limit-seeds 2 \
  --main-only --condition e_full_loop
```

Both seeds completed 160 turns with zero gameplay failures, zero
infrastructure failures, and zero rejected engine actions. The configuration
hash is:

```text
a0809267bcf0f3b2c7ef3f95d420c591411dfe90cd08155f1f2c7578892b4d7b
```

| Seed | Own score | Opponent score | Raw event SHA-256 |
| ---: | ---: | ---: | --- |
| 104743 | 127 | 244 | `d5b6c4804a8334c37f031ef817f52c4e87ed476d36971b31ceb0904111bb0379` |
| 4543804 | 168 | 363 | `29c35c7f04a1dd69c8e1b9f871c212f57ec29a6f060ed6135680f007af487dfb` |

These scores reproduce the prior shadow-policy cohort. They are not a score
comparison because the new analyzer still has no action-selection authority.

The two-game means were 9.03 ms of native route wait per turn-boundary state
request, 0.77 ms per action-refresh request, and 257.63 ms for the complete
action loop. The corrected freshness check therefore did not create a
material route-query regression.

## Retained replay

Every scored defense snapshot from seed 4543804 was retained, including
multiple same-turn state revisions:

- 17 fixtures in
  `benchmarks/gdo/captured_snapshots/city_defense_known_terrain_160/`;
- manifest structural hash
  `676f72f66a91ec216271ede5ebbd3e680c41b6dc9f3f367402f28be53ae6b20b`;
- manifest file SHA-256
  `0239c3ceededaa58ef2c70963be82359fa2c36ed25209fb34bab95a01c2ed91e`;
- report structural hash
  `aae6e27a969eed223a92f12ce7bff037a6389602ef0aca7b046d3b2f362278a4`;
- report file SHA-256
  `452744f9f0a96ac9f81b8cf024bc707afa3c6f119080537ce16de73c1aa37c0f`.

The corrected replay has five threat/city comparisons. Four are reachable and
one is a grounded negative: every city-approach tile known to the player is
non-native for the visible Ironclad. This distinction matters: supported
threat-value coverage remains 4/5 because an unreachable threat has no
positive threat value, while decision-resolved reachability is 5/5.

| Diagnostic | Result |
| --- | ---: |
| Threat decisions grounded, positive or negative | 5 / 5 |
| Requirements decision-resolved | 1 / 1 |
| Operations grounded, positive or negative | 14 / 14 |
| Candidate-edge requirement coverage | 1 / 1 |
| B1 covered / uncovered current-action slots | 0 / 2 |
| B4 covered / uncovered current-action slots | 1 / 1 |
| B4 covered / uncovered full intent slots | 2 / 0 |
| Assignment safety violations | 0 |
| Replay compute p95 | 10.68 ms |

All diagnostic mechanism gates now pass. Exact B4 is no worse than
identity-aware greedy B3, but it ties B3 on this small instance; this cohort
does not claim an optimizer advantage.

## Authority decision

`gdo4_exit_gate_passed` remains false and
`pressure_city_defense_operations_enabled` remains disabled. The retained
fixtures do not provide complete native movement metadata on every snapshot,
the visible-enemy ETA is still a conservative player-known lower bound rather
than a native enemy-route parity result, and factual source-run outcomes are
not counterfactual B1/B2/B3/B4 outcomes.

The defensible result is therefore narrower:

- player-known topology and terrain semantics close the observed threat
  reachability ambiguity without hidden information;
- exact route revision validation closes the observed defender-operation
  ambiguity;
- the typed defense readout improves the replay mechanism metric over frozen
  B1 with zero observed safety violations;
- no live gameplay, score, or win-rate improvement has yet been established.

The next implementation stage may use this fully grounded diagnostic boundary
to build GDO-5 multi-unit combat operations in shadow mode. It must not infer
that GDO-4 has earned live authority.
