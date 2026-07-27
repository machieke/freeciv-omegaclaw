# FreeCiv domain observability

The Decision Observatory now has dedicated Technology, Economy & Production,
and Unit Lifecycle views. These views consume typed events; they do not decode
generic state arrays or reconstruct game logic in the browser.

## What the historical runs establish

The non-destructive observability-v2 copies of the July 27 runs show:

| Run | Target at end | Progress | Rate | Consecutive stall | Conclusion |
|---|---|---:|---:|---:|---|
| 240 turns | Industrialization | 1115 / 1140 | 0 beakers/turn | 42 turns | 25 beakers short; more turns do not converge under the unchanged economy |
| 480 turns | The Corporation | 107 / 1200 | 0 beakers/turn | 228 turns | 1093 beakers short; the target is stalled |

The turn-1 `missing-tech` proof was not emitted 240 times. It remained selected
because the Proof Explorer used index zero. The view now defaults to the newest
proof at the cursor and labels manual older selections as historical.

In a PLN frontier, `missing-tech` means the required technology is absent but
its direct prerequisites are satisfied, so it is currently researchable. A
technology whose own prerequisites are absent is shown as `blocked`, with those
prerequisites named.

## Production coverage

`production_state` names the FreeCiv six-yield vector
`food, shield, trade, gold, luxury, science` before it reaches the UI. Each
event also includes city food/shield stock, size, current production target,
buildable count, and player economy allocation.

The view keeps three evidence domains separate:

1. authoritative current city/economy values;
2. explicit `city_production` action decisions and snapshot-matched completed
   units;
3. PF-PLN candidate projections emitted in `operation_scored`, including build
   cost, completion ETA, shield surplus, population cost, and horizon output.

If no `buildable` PLN query occurred, the view says so. Production can affect
PF-PLN grounded candidate scoring without having appeared in a PLN proof.

## Unit disappearance evidence

Every lifecycle transition has one of three evidence qualities:

- `exact`: first-snapshot presence or packet-backed combat/city evidence;
- `inferred`: an explicit snapshot/action correlation, such as a founder
  disappearing after founding a city or a new unit matching a city's prior
  queue;
- `unattributed`: the unit disappeared between authoritative snapshots but the
  trace did not preserve a root-cause packet.

Historical 240-turn disappearance counts are 4 inferred city founders, 2
inferred attacker losses, and 67 unattributed turn-boundary removals. The
480-turn run has 4, 2, and 126 respectively. Those unknowns are not silently
called combat losses.

For future runs, proxy patch `0003-pln-unit-lifecycle.patch` journals bounded
`PACKET_UNIT_COMBAT_INFO` zero-HP outcomes and correlates them with
`PACKET_UNIT_REMOVE`. The engine harness turns that journal into typed
`unit_lifecycle` events. A removal packet without a combat cause remains
`engine_removed / unattributed`.

## Enriching an existing trace

The source file is never changed:

```bash
python3 scripts/freeciv/enrich_observability_trace.py \
  path/to/source/events.jsonl \
  path/to/observability-v2/events.jsonl
```

The output is schema- and causality-validated. Historical action correlations
remain marked `inferred`; the command cannot manufacture packet evidence that
was not logged.

## Validation

```bash
pytest -q Autotests/test_freeciv_domain_observability.py \
  Autotests/test_freeciv_events.py

cd apps/freeciv-observability
npm test
```

The proxy contract tests run inside the configured FreeCiv container:

```bash
docker exec -w /docker/freeciv-proxy fciv-net \
  pytest -q tests/test_pln_authoritative_state.py
```
