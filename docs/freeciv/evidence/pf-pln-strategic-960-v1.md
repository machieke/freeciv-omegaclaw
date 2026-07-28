# PF-PLN strategic 960-turn diagnostic

Date: 2026-07-28

This is selected-seed mechanism evidence, not a score or win-rate claim. All
arms used seed `4543804`, `e_full_loop`, the experimental built-in opponent,
and a 960-turn fixed horizon. The opponent trajectory is policy-dependent, so
the raw same-seed scores are diagnostic rather than a paired causal estimate.

## Iteration results

| Arm | Material change | Player / opponent score | Cities | Runtime | Result |
|---|---|---:|---:|---:|---|
| prior long run | adapter 1.24, five-city policy, no v11 strategic telemetry | 495 / 4431 | 5 | 421.7 s | historical reference |
| v4 | eight-city target plus initial strategic policy | 371 / 4420 | 7 | 926.9 s | rejected overexpansion |
| v5 | five-city target; hidden-score and missile hardening | 479 / 4491 | 5 | 582.6 s | overexpansion regression recovered |
| v7 | current-frontier research, canonical selection, structural commerce runway | 477 / 4616 | 5 | 425.8 s | accepted mechanism hardening; no score superiority |

Artifacts:

- historical: `artifacts/freeciv/pf-pln-960-turn-live-tail-20260728`
- rejected overexpansion: `artifacts/freeciv/pf-pln-strategic-960-v4`
- five-city recovery: `artifacts/freeciv/pf-pln-strategic-960-v5`
- final completed diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v7`

Both v4 and v7 completed 1/1 jobs with zero gameplay or infrastructure
failures. Interrupted integration diagnostics are intentionally excluded.

## What was confirmed

Patch 0009 populated the real engine stream with:

- produced, consumed, and net city resource vectors;
- structural operating cash, Coinage capitalization, and effective cash;
- gross beakers, technology upkeep, and net beakers;
- exact building inventory, upkeep, completion, and removal transitions;
- own/opponent score values when packet-visible, with hidden `-1` normalized to
  unknown; and
- attributed unit lifecycle events.

The initial v4 run selected naval response 4 times, commerce infrastructure 57,
research infrastructure 24, industrialization 37, coastal defense 72, and
modernization 141. It completed factories, power plants, universities, banks,
markets, a stock exchange, harbors, and defensive infrastructure. It also
proved two defects: 24 founders appeared and disappeared while only six new
cities survived, and all 141 modernization selections targeted the one-shot
`Nuclear` missile.

The five-city v7 arm removed that behavior:

- founder appearances/disappearances returned to five/five, with four
  `city_founded` removals after the initial founder;
- missile modernization selections were zero;
- model research-selection calls fell from 10 in v5 to zero, with 960 canonical
  singleton bypasses;
- total city queue changes fell from 1044 in v5 to 232 in v7 (`-77.8%`);
- actions fell from 2251 to 1453 (`-35.5%`);
- runtime fell from 582.6 to 425.8 seconds (`-26.9%`);
- final research improved from 8 net beakers/turn in v5 to 23; and
- final engine state exposed `30` gross beakers, `7` technology upkeep, `-28`
  structural gold/turn, `+20` Coinage capitalization, and `-8` effective
  gold/turn without conflating those values.

The v7 strategic policy selected naval response 11 times, commerce
infrastructure 7, research infrastructure 2, coastal defense 6, and
industrialization 5. Its exact naval targets included Trireme, Ironclad,
Transport, and Submarine.

Unit removal attribution was complete in the v4 engine trace: 41 removals were
`combat_defender_lost` and six were `city_founded`; there were no unattributed
food-loss removals. Building removals remained observations, not invented
causal claims.

## Remaining boundary

The completed arms do **not** prove score improvement. The best new arm scored
479 and the final hardened arm 477 versus the historical 495; opponent scores
also differed. One selected seed cannot establish a reliable effect.

V7 researched Amphibious Warfare and Flight but did not complete a conventional
advanced unit. The trace showed why: opponent scores remained hidden, leaving
ordinary modernization's score goal inactive. Post-v7 hardening therefore adds
`production_threat_modernization`: a packet-visible same-domain capability
deficit routes sustainable conventional modernization to survival pressure
without relying on opponent score visibility. This last routing correction has
unit/replay coverage but is not included in the completed v7 engine outcome.

Any score claim still requires a preregistered paired-seed cohort with the
historical five-city policy held fixed. The current evidence supports contract,
mechanism, queue-efficiency, and runtime claims only.
