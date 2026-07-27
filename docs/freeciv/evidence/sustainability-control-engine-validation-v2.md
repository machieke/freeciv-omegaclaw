# Sustainability-control 480-turn engine validation v2

Status: passed as a fixed-horizon correctness and mechanism validation; not
eligible by itself for a score or win-rate claim.

On 2026-07-27, adapter `grounded-impact-planner/1.20` completed one fresh,
non-resumed 480-turn `e_full_loop` game with seed `4543804`, the `civ2civ3`
ruleset, `qwen3-coder-next:latest`, and proxy patch-series identity
`90cf26d4da2c4452f5e1e22a23a24fcaf24517cfe33c80ec78aa680ccf3aa2f3`.
The run is stored under
`artifacts/freeciv/pf-pln-480-turn-sustainability-confirmation-v12-20260727`.

The engine reached turn 480, obtained its authoritative post-horizon score, and
reported zero infrastructure failures, rejected actions, model corrections, or
turn-boundary recovery attempts. The trace contains 8,890 schema-valid events;
its SHA-256 is
`52dddf5e708d19b1fea5c5c6a487cedac33c1fe6dc898c3fa4be33a5545fab68`.
The cross-cutting release audit, including all PF-PLN phase replays and the
pinned external patch check, passed and is recorded in
`docs/freeciv/evidence/release-audit-latest.json`.

## Fixed-horizon correction

The preceding attempts repeatedly stopped after turn 475. Proxy logs proved the
cause was not a lost end-turn: the Korean spaceship arrived and Freeciv ended
the game. Fixed-horizon games now retain `SPACERACE` mechanics while setting
`endspaceship` disabled and excluding allied/culture victory conditions. The
successful run logged the spaceship arrival at turn 475, advanced to turn 476,
and ended only after the declared turn-480 limit. A one-shot authenticated
force-end-turn fallback remains available for a genuinely lost phase-done
packet, but it was not used in this run.

The authoritative state contract also projects the cross-connection
`GameSession.game_is_over` flag and removes legal actions after a genuine
terminal report. The harness accepts that current-turn terminal revision and
scores it as an absorbing terminal outcome instead of misclassifying it as
infrastructure timeout.

## Sustainability and observability results

One final production-state observation per turn gives the following results:

- The controller founded four cities, reaching the five-city target.
- It submitted 74 city-governor actions, 56 production changes, two bounded
  rate changes, nine research selections, four city-founding actions, and 14
  fortifications.
- Negative-food exposure fell from 115 city-turns in the earlier
  `sustainability-control-v1` diagnostic trace to 37, and famine-marked
  city-turns fell from 12 to 4. All five final cities had food surplus 0 or
  +1. The reserve governor was active for 170 city-turns; Harbor was selected
  three times and Supermarket nine times as direct food-output recovery.
- The treasury reached a minimum of 0 gold and ended at 144 gold with exact
  net flow −19/turn and immediate unit upkeep 1. This is intentionally a
  reserve/runway policy, not a permanently positive-income policy. Eight
  Coinage changes and the two rate actions show that recovery was exercised.
- Eight technologies were acquired, versus one in the earlier diagnostic
  control. The final target was Flight at 481/1500 with 41 beakers/turn and
  25-turn ETA. No observed turn was classified as stalled.
- All 14 unit disappearances were attributed: four founders consumed by city
  founding and ten exact combat-defender losses. There were zero
  `engine_removed` or otherwise unattributed disappearances.
- Defensive production was exercised across all five cities: Alpine Troops
  was selected six times and Riflemen nine times. Ten exact combat losses
  nevertheless left units co-located with only two of five cities at the
  horizon. The trace therefore validates defense demand, production, and loss
  attribution, but does not prove durable full-map garrison coverage against
  this stronger opponent.

## Score interpretation

The controller score was 319, up from 196 in the earlier diagnostic control,
and it acquired seven more technologies. The opponent score also changed from
1,281 to 2,412, and the final margin was −2,093. These are single-run
diagnostics under an evolved controller and corrected horizon configuration,
not a paired randomized comparison. They do not change the formal score or
win-rate claim.
