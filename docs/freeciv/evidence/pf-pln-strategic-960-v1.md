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
| v19 | adapter 1.27, counterfactual Coinage release and funded treasury-building hold | 472 / 4594 | 5 | 457.0 s | accepted queue/economy hardening; no score superiority |
| v20 | adapter 1.28, noncombat-role exclusion and funded ruleset-defender hold | 240 / 4890 | 5 | 406.1 s | rejected reserve-breach starvation |
| v21 | adapter 1.29, immediate reserve-breach Coinage override and authoritative research-stall detection | 441 / 4630 | 5 | 435.9 s | accepted research-continuity hardening; no score superiority |
| v24 | first bounded luxury bridge and local happiness-building lifecycle | 373 / 4799 | 5 | 497.6 s | rejected score regression; retained as mechanism evidence |
| v32 | adapter 1.30 player-rate effect confirmation, bridge enabled, no tax-floor hysteresis | 359 / 4474 | 5 | 568.9 s | rejected rate oscillation |
| v33 | adapter 1.30 material-state tax floor, bridge enabled | 371 / 4452 | 5 | 445.0 s | accepted correctness mechanism; rejected as default score policy |
| v34 | adapter 1.30 material-state tax floor, bridge disabled | 453 / 4280 | 5 | 526.6 s | accepted selected-seed control; no score claim |
| v35 | ten-turn tax-restore stability window, bridge disabled | 362 / 4424 | 5 | 454.4 s | rejected score regression |
| v36 | any ruleset land unit with nonzero defense may fill an emergency garrison | 177 / 807 at elimination | 0 | 123.1 s | rejected; Cannon entered the garrison path and the player was eliminated on turn 265 |
| v37 | only the most durable currently buildable ruleset defender may fill an emergency garrison | 177 / 1557 at elimination | 0 | 215.7 s | rejected; Marines displaced the stable legacy trajectory and the player was eliminated on turn 412 |

Artifacts:

- historical: `artifacts/freeciv/pf-pln-960-turn-live-tail-20260728`
- rejected overexpansion: `artifacts/freeciv/pf-pln-strategic-960-v4`
- five-city recovery: `artifacts/freeciv/pf-pln-strategic-960-v5`
- original hardened diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v7`
- reproducibility check: `artifacts/freeciv/pf-pln-strategic-960-v8`
- rejected infrastructure diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v17`
- first-completion diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v18`
- accepted treasury diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v19`
- rejected reserve-breach diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v20`
- reserve-breach recovery diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v21`
- initial bounded happiness diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v24`
- exact rate-effect diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v32`
- tax-floor happiness diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v33`
- bridge-disabled adapter-1.30 control: `artifacts/freeciv/pf-pln-strategic-960-v34`
- rejected tax-stability-window diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v35`
- rejected generic ruleset-garrison diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v36`
- rejected durability-gated ruleset-garrison diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v37`

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

V19 then corrected a second counterfactual error: a replacement queue had been
evaluated against effective cash flow that still included the current city's
Coinage capitalization, even though the proposed switch would remove that
income. Adapter 1.27 subtracts the city's bounded packet-grounded contribution
before testing the replacement runway and holds a funded structural treasury
building through completion.

Against v18 on the same diagnostic seed, v19 reduced defense selections from
123 to 36 and treasury-stabilization selections from 119 to 31. Engine actions
fell from 1519 to 1432 and meaningful actions from 559 to 472. The
Factory/Coinage and defender/treasury turn-by-turn queue cycles were absent.
Gameplay runtime remained effectively flat at 457.0 versus 456.4 seconds.

The stronger construction continuity produced two Triremes, an Ironclad, and a
Destroyer; the Ironclad and Destroyer were later removed with exact
`combat_defender_lost` attribution. It also completed Mech. Infantry on turn
894 and retained one at the horizon. Final research flow rose from 15 gross /
5 upkeep / 10 net beakers per turn in v18 to 44 / 14 / 30 in v19. Final
effective cash flow rose from -12 to +8 gold per turn and final treasury from
40 to 69. The fixed-horizon score nevertheless remained flat at 472 versus
473, with the opponent at 4594 versus 4566.

Unit removal attribution was complete in the v4 engine trace: 41 removals were
`combat_defender_lost` and six were `city_founded`; there were no unattributed
food-loss removals. Building removals remained observations, not invented
causal claims.

## Remaining boundary

The completed arms do **not** prove score improvement. The best new arm scored
479 and the final adapter 1.27 arm scored 472 versus the historical 495;
opponent scores also differed. One selected seed cannot establish a reliable
effect.

V19 proves that naval pressure can cause several real combat vessels and an
advanced conventional land unit to complete. It does not prove naval parity,
durable force modernization, or score improvement. Conventional
land modernization now routes a packet-visible same-domain capability deficit
to survival pressure without relying on opponent score visibility, and the
Marines defensive route has unit coverage. V19 selected Marines once and
completed Mech. Infantry, but ordinary Alpine Troops still supplied most
replacement garrisons.

V19 exposes the next type-safety boundary. The generic modernization path
selected Engineers once as `production_defense` after the conventional force
ceiling had collapsed; five Engineers were later lost in combat. Ruleset worker
roles must be excluded from persistent combat modernization, and a funded
ruleset-derived defensive queue should not be replaced by a legacy defender.
Adapter 1.28 implemented both constraints, and v20 selected no worker as
modernization.

V20 nevertheless rejected the initial hold boundary. Authoritative gold fell
to 1 on turn 784 and 0 on turn 785 while two cities already ran Coinage. The
planner retained a funded Destroyer, Alpine Troops, and Supermarket because
reported effective cash flow was zero. On turn 786 FreeCiv forcibly removed a
Courthouse, treasury jumped to 60, and Communism research progress froze at
776 through turn 960 even though the projected research flow remained 41 net
beakers per turn. The old telemetry incorrectly continued to report
`researching`.

Adapter 1.29 therefore permits an **immediate Coinage** switch to preempt those
funded queues only after authoritative gold is already below the configured
reserve; it does not permit a long treasury building to do so. Technology
observability now labels unchanged progress across successive turns
`research_progress_not_advancing` even when projected beakers remain positive.
V20 is rejection evidence for the boundary, not support for adapter 1.29 or a
stronger score claim.

V21 completed all 960 turns with zero rejected engine actions. Gold never
reached zero (minimum 3, final 255), authoritative research acquired seven
technologies, and the final Refining counter remained live at 660/1200 with
8 net beakers per turn. No worker-role unit was selected or completed as force
modernization. These results accept the narrow research-continuity and
modernization-type-safety corrections.

They do not establish treasury or score success. FreeCiv still removed five
buildings after low-gold boundaries, the final structural operating balance
was -27 gold per turn, and Coinage reduced the effective deficit only to -8.
The trace also contains 1,022 disordered city samples. City102 ended at size 15
in disorder, suppressing 24 trade and all shield, gold, and science output.
Twelve attempted treasury production changes had exact candidate-specific
no-effect confirmation before the first forced sale. The proxy transport
acknowledgement therefore remains distinct from authoritative execution, as
the harness correctly records. Adapter 1.29 is a bounded safety recovery, not a
claim that the structural economy or production-delivery lifecycle is solved.

Adapter 1.30 corrects a cross-layer player-rate confirmation defect. A
`player_rates` action carries player ID `0`, but the old generic effect path
looked up that ID as a unit. Every accepted rate change was consequently
reported as no effect. The retry grounding also omitted the current economy,
so an exact target could remain suppressed after tax, science, and luxury had
changed. Adapter 1.30 confirms the authoritative
`(tax, science, luxury)` tuple and includes the current tuple in retry
grounding. A material-state tax floor retains the next known-safe packet
boundary until population, buildings, Coinage state, government, or supported
unit upkeep changes.

The bounded happiness experiment now requires three consecutive disorder
turns, a city of at least size ten, zero shield output, and a packet-buildable
Temple, Cathedral, or Amphitheater. It raises luxury one legal increment at a
time, preserves the local remedy through completion, re-probes after each
material happiness change, and has a forty-turn expiry. V33 reduced disordered
city samples from 1,022 in v21 to 261 and ended with zero disorder. It
nevertheless scored 371, versus 453 for the v34 bridge-disabled control.
Population/technology/residual score components were `35/116/220` in v33 and
`38/128/287` in v34. The bridge therefore remains disabled in every live
profile.

V34 completed 960 turns with zero rejected actions and scored 453, twelve
points above v21 but nineteen below v19. It ended with 46 buildings, 38
citizens, 13 acquired technologies, 33 net beakers per turn, and no current
disorder; its trace still contained 1,858 disordered city samples. This is one
selected development seed and does not revise a score or win-rate claim.

The v35 stability-window ablation reduced rate churn but scored 362. That
window was removed. The accepted implementation retains exact rate effects and
the material-state tax floor, not a fixed elapsed-turn hold.

V36 and v37 tested whether the emergency garrison lifecycle could also solve
the advanced-unit gap. V36 admitted every persistent ruleset land unit with
nonzero defense and selected Cannon as a defender; the player was eliminated
on turn 265. V37 required the maximum ruleset-derived defensive durability
among the currently buildable alternatives, excluded Cannon, and selected
Marines five times before turn 279. It still changed the early survival
trajectory enough for elimination on turn 412. Both variants were fully
reverted. Advanced offensive modernization must remain a separate bounded
lifecycle rather than changing the semantics or timing of mandatory local
garrisons.

Any score claim still requires a preregistered paired-seed cohort with the
historical five-city policy held fixed. The current evidence supports contract,
mechanism, queue-efficiency, and runtime claims only.
