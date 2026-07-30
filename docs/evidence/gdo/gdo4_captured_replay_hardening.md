# GDO-4 captured replay semantic hardening

Date: 2026-07-30

Branch: `experimental/pln-pressure–bridge–fluid`

Authority: disabled; captured replay is diagnostic only

## Decision

The first nine-snapshot engine replay exposed two false-deficit bugs before it
exposed an assignment-solver problem:

1. a city with an already sufficient garrison was still charged one uncovered
   response slot when a fortify action was absent;
2. any ruleset unit with a stat record could be treated as an attacker or
   defender, including `NonMil` and zero-attack units.

The analyzer now:

- retains ruleset unit class, flags, and roles in its local unit specification;
- rejects `NonMil` and zero-attack units as supported visible threats;
- rejects `NonMil` and zero-defense units as effective city defenders;
- materializes requirements only from supported threats;
- materializes only a real garrison deficit, not a redundant “respond anyway”
  slot;
- considers any advertised `unit_move` that reduces distance to a threatened
  city, independently of the legacy candidate category;
- supports a move arrival only when the advertised current action reaches the
  city now;
- emits `defender-route-eta-unavailable` for a multi-turn route whose arrival
  time is not grounded by the captured state.

Unsupported threats remain visible in the analysis with confidence zero and
unknown mass one. They do not silently become assignment demand.

## Before and after

The retained report is
`benchmarks/gdo/gdo4_city_defense_replay_diagnostic.json`, with report hash
`afd7f0fef8bd09e92e79f161d28f53c77432fb232b8f20eb6874f23be8ef283b`.

| Metric | Initial replay | Hardened replay |
| --- | ---: | ---: |
| Visible typed threats | 53 | 53 |
| Materialized city requirements | 25 | 6 |
| Required response slots | 27 | 8 |
| Requirements with any legal candidate edge | not separated | 5 / 6 |
| Requirements with a supported on-time edge | 3 / 25 | 1 / 6 |
| B1/B4 uncovered slots | 24 | 7 |
| B4 safety violations | 0 | 0 |
| B4 improvement over B1 | none | none |

The reduction from 27 to 8 response slots is a correctness repair, not a
performance gain. It removes demands from cities whose existing garrison
already met the declared threshold.

## Bottleneck localization

Candidate assembly is not the dominant remaining blocker in this cohort:
five of six real deficit requirements have at least one legal candidate edge.
Only one has a supported edge. Across all generated operations:

- 23 are move-to-city edges;
- 4 are protected sole-defender holds;
- 22 move edges abstain with `defender-route-eta-unavailable`;
- 5 operations are supported, of which 4 are non-action hold constraints.

The cohort contains 31 Sea-class and 22 Land-class threat records. The selected
crisis snapshots are mostly already at or past a naval threat deadline. They
are useful safety fixtures, but they do not form a mechanism-discriminating
assignment cohort: B1, B2, B3, and B4 all cover the same single actionable
slot.

The next blocking input is therefore grounded threat/defender ETA plus earlier
warning snapshots, not a more sophisticated exact solver or broader
category-based readout.

## Verification

Focused city-defence tests now cover:

- non-military threat rejection;
- satisfied-garrison deficit suppression;
- category-independent direct defensive moves;
- fail-closed multi-turn ETA;
- the existing exactness, legality, resource, invariance, event, and safety
  cases.

The focused result is `16 passed`. Replay validation passes, B4 has zero actor,
city-production, late-arrival, and sole-defender violations, and replay
analyzer-plus-solver p95 is approximately 4.20 ms over 900 samples.

## Claim boundary

This evidence makes no gameplay, score, or win-rate claim. The replay omits the
complete legal-action set, map-wrap metadata, movement runtime fields, native
movement/threat parity, and counterfactual outcomes. The GDO-4 live-pilot gate
remains closed.
