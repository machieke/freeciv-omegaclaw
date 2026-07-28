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
| v8 | reproducibility check of the v7 policy | 477 / 4616 | 5 | 424.4 s | exact selected-seed score reproduction |
| v17 | first-completion naval queue hold without a general infrastructure runway | 375 / 4643 | 5 | 493.4 s | rejected infrastructure/treasury oscillation |
| v18 | adapter 1.26, first-completion naval hold, output recovery hold, and structural runway for all long infrastructure | 473 / 4566 | 5 | 456.4 s | accepted mechanism hardening; no score superiority |

Artifacts:

- historical: `artifacts/freeciv/pf-pln-960-turn-live-tail-20260728`
- rejected overexpansion: `artifacts/freeciv/pf-pln-strategic-960-v4`
- five-city recovery: `artifacts/freeciv/pf-pln-strategic-960-v5`
- original hardened diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v7`
- reproducibility check: `artifacts/freeciv/pf-pln-strategic-960-v8`
- rejected infrastructure diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v17`
- final completed diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v18`

All listed completed diagnostics completed 1/1 jobs with zero gameplay or
infrastructure failures. Interrupted integration diagnostics are intentionally
excluded.

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

The v7/v8 strategic policy selected naval response 11 times, commerce
infrastructure 7, research infrastructure 2, coastal defense 6, and
industrialization 5. Its exact naval targets included Trireme, Ironclad,
Transport, and Submarine.

Those targets did not survive queue competition long enough to complete. The
adapter 1.26 policy therefore:

- ranks combat sea units by combat capability rather than allowing transport
  capacity to dominate the power score;
- holds the first selected instance of a sea-unit type through zero stock,
  disorder, defense pressure, and multi-city treasury pressure;
- allows a directly productive food-recovery building to preempt a vessel, but
  then holds that funded recovery building through completion;
- releases the sea hold as soon as an owned instance of that type is observed,
  preventing automatic repeat production; and
- applies the structural treasury runway to every long-lived infrastructure
  category, not only commerce.

V18 selected a Trireme on turn 83 and completed it on turn 90. It selected a
Destroyer on turn 232 and completed it on turn 274 after food recovery; the
Destroyer disappeared on turn 279 with exact
`combat_defender_lost` attribution. The final trace retained the Trireme and
ended with three Alpine Troops and two Riflemen. It also selected an Ironclad
and Cruiser, but correctly released those queues for direct food recovery and
later survival work before completion.

The rejected v17 arm made 106 industrialization and 38 research-infrastructure
selections alongside 188 treasury selections, producing a Factory/Coinage
cycle and 159 expired confirmations. V18 made no industrialization or
research-infrastructure selections while structural cash flow could not fund
their construction runway. Actions fell from 1646 to 1519, meaningful actions
from 686 to 559, expired confirmations from 159 to 119, and runtime from 493.4
to 456.4 seconds. Its selected-seed score recovered from 375 to 473.

During integration, the generic upstream name sanitizer rejected the legitimate
ruleset technology `Labor Union` as if it were a standalone SQL `UNION`
keyword. Patch 0010 narrows that guard: `Labor Union` is accepted, while the
explicit `UNION SELECT` injection pattern remains rejected. The release audit
pins the resulting ten-patch series and passes against the v18 cognitive trace.

Unit removal attribution was complete in the v4 engine trace: 41 removals were
`combat_defender_lost` and six were `city_founded`; there were no unattributed
food-loss removals. Building removals remained observations, not invented
causal claims.

## Remaining boundary

The completed arms do **not** prove score improvement. The best new arm scored
479 and the final adapter 1.26 arm scored 473 versus the historical 495;
opponent scores also differed. One selected seed cannot establish a reliable
effect.

V18 proves that naval pressure can cause a real advanced combat vessel to
complete, but the single Destroyer was lost five turns later. It does not prove
naval parity, durable force modernization, or score improvement. Conventional
land modernization now routes a packet-visible same-domain capability deficit
to survival pressure without relying on opponent score visibility, and the
Marines defensive route has unit coverage. This route did not activate in v18:
the observed engine trajectory kept selecting Alpine Troops to replace local
garrison losses.

V18 also exposes the next queue-efficiency boundary. The structural runway
removed the Factory/Coinage loop, but prolonged combat losses drove 123 defense
and 119 treasury-stabilization selections, including repeated alternation
between an Alpine Troops queue and Coinage or commerce recovery. Final research
flow was 15 gross, 5 upkeep, and 10 net beakers/turn; final operating cash flow
was -30 gold/turn, partly offset by 18 Coinage gold/turn. A follow-up policy
should preserve funded defensive replacements across transient treasury
pressure without permitting unsupported repeat-unit production.

Any score claim still requires a preregistered paired-seed cohort with the
historical five-city policy held fixed. The current evidence supports contract,
mechanism, queue-efficiency, and runtime claims only.
