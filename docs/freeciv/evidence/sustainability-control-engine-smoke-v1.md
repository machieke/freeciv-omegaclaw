# Sustainability-control engine smoke v1

Status: passed as a correctness smoke; not eligible for a score or win-rate
claim.

On 2026-07-27, adapter `grounded-impact-planner/1.19` completed one fresh
30-turn `e_full_loop` game with the `civ2civ3` ruleset and proxy patch-series
identity
`03a8cb9a385defe5f811165dd69136ac9e5dab5acee2c7967c432a998ad34e6b`.
The run is stored under
`artifacts/freeciv/pf-pln-30-turn-sustainability-control-v4-20260727`.

The engine reached turn 30 without infrastructure failure, terminal
elimination, or a rejected action. The trace contains 780 schema-valid events,
50 authoritative snapshots, 50 production-state events, 19 PF-PLN decisions,
and 50 accepted engine actions. Its event-log SHA-256 is
`a95793a6b350c3ac9459766d2faadcb4dd458a2bf78247da5e1fe716fe816600`.

The new mechanism was exercised rather than merely loaded:

- `production_food_stabilization` was selected twice;
- `city_defense` and `production_defense` were each selected once;
- all observed city food surpluses remained at or above the configured `+1`
  reserve;
- the authoritative economy reported `gold_upkeep_style: Mixed`, exact city
  gold surplus, exact unit upkeep, and a matching ruleset-aware net rate;
- both sustainability goals appeared in all 19 pressure fields, with food and
  treasury correctly marked safe in this seed;
- the only disappearance was the founder consumed by city founding, retained
  as inferred `city_founded` lifecycle evidence.

This single smoke verifies transport, telemetry, planner selection, PF-PLN
projection, event emission, and horizon completion. It cannot estimate an
effect size and does not alter any frozen score or win-rate claim.
