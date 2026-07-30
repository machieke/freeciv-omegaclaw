# GDO-4 fresh grounded 160-turn replay

Date: 2026-07-30

Branch: `experimental/pln-pressure–bridge–fluid`

Authority: disabled; engine capture and replay are diagnostic only

## Engine cohort

The retained harness profile is
`profile/freeciv_harness_gdo4_160_turn.yaml`. The successful capture used seed
`4543804`, the `civ2civ3` ruleset, the experimental built-in opponent, condition
`e_full_loop`, scalar PF-v2, packet/resource scheduling, and the city-defence
shadow analyzer:

```text
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness_gdo4_160_turn.yaml \
  --out artifacts/freeciv/gdo4-grounded-160-da91032-v2-20260730 \
  --backend engine-live --workers 1 --limit-seeds 1 \
  --main-only --condition e_full_loop --no-resume
```

The game completed all 160 requested turns with no infrastructure failure.
The aggregate trace contains 1,868 schema-valid events with no validator error
or warning. The diagnostic game ended as a loss with score 167, four cities
founded, one technology acquired, 174 impact actions, and no engine action
rejection. This single game is an input capture, not a gameplay cohort or score
claim.

## Retained replay inputs

All 13 snapshots associated with a city-defence proposal were retained under
`benchmarks/gdo/captured_snapshots/city_defense_grounded_160/`. Their immutable
manifest is
`benchmarks/gdo/captured_snapshots/city_defense_grounded_160_manifest.json`,
with manifest hash:

```text
66e460a5b598db5b02b9cd65e1ca1e13136714ecda9895c2f12d369bccc2d604
```

The fixtures cover turns 46, 48, 108, 130, 151, 152, 153, 157, and 158. They
retain full normalized legal actions and lossless own/enemy unit runtime
fields. The source proxy did not expose map-wrap flags, authoritative action
movement cost, transport state, or a native route oracle, so those fields
remain explicitly unavailable.

## Corrected replay result

The retained replay report is
`benchmarks/gdo/gdo4_city_defense_grounded_160_diagnostic.json`, with report
hash:

```text
fe997ec90ea29c0c0283f44600507c368803f213bae9dc3a6c03462051732994
```

| Metric | Result |
| --- | ---: |
| Threat-value coverage | 30 / 30 (100%) |
| Requirements with any legal candidate edge | 12 / 12 (100%) |
| Requirements with a grounded supported edge | 5 / 12 (41.7%) |
| Protected legal actions added to analysis | 2,891 |
| Multi-turn route-ETA abstentions | 160 |
| B1 covered / uncovered slots | 3 / 17 |
| B4 one-action readout covered / uncovered slots | 5 / 15 |
| B4 intent assignment covered / uncovered slots | 6 / 14 |
| B4 safety violations | 0 |
| Analyzer-plus-solver p95 | 13.02 ms |

The protected union therefore fixed candidate recall in this cohort. It did
not fix transition support: seven of twelve requirements still lack an
authoritative on-time operation edge, overwhelmingly because multi-turn route
ETA is unavailable.

The headline B3/B4 replay arms credit at most one current action per fixture,
matching the runtime adapter's current readout capacity. Full exact/greedy
assignments are retained separately as intent diagnostics and are not counted
as executed operations. Under this correction, B2, B3, and B4 have the same
5/15 covered/uncovered result. Exact B4 does not improve over greedy B3.

## Gate decision

The following mechanism checks pass:

- threat-value coverage is at least 90%;
- every requirement has a candidate edge;
- B4 has fewer uncovered slots than frozen B1 in this diagnostic replay;
- B4 is never worse than B3 at the intent-assignment layer;
- exact status is retained for every fixture;
- no actor, city-production, late-arrival, or sole-defender safety violation
  occurs;
- replay p95 is below 50 ms.

The GDO-4 pilot gate remains closed because:

- grounded operation-edge coverage is only 41.7%, below 90%;
- B4 does not beat B3 after the actual one-action readout boundary;
- selected operation steps are not yet revalidated and resolved to completed,
  failed, or expired outcomes;
- realized preventable city loss and positive operation-completion delta are
  unavailable;
- native movement/threat parity remains unproven;
- this is one diagnostic seed and not a disjoint pilot or confirmation cohort.

## Next implementation target

Do not add authority or retune assignment weights. The next vertical slice is
authoritative operation lifecycle resolution:

1. distinguish an exact intent assignment from the one operation step actually
   read out;
2. revalidate that step against the later authoritative snapshot;
3. emit completed, failed, expired, or unresolved outcomes with explicit reason
   codes;
4. release its identity/time resource claims on every terminal path;
5. compute realized completion and city-loss metrics;
6. retain fail-closed abstention until authoritative movement ETA or native
   parity supplies the missing multi-turn edges.
