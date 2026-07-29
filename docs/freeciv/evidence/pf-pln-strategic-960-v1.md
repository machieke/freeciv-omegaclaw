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
| v38 | city-local defense-first ruleset role for strategic selection; adapter still declared 1.30 | 455 / 4274 | 5 | 530.5 s | accepted behavior diagnostic; identity not suitable for release audit |
| v40 | adapter 1.31 plus defense-first role applied to all queue-retention boundaries | 335 / 4296 | 5 | 468.8 s | rejected; productive and military continuity regressed |
| v41 | adapter 1.31 selection-only role boundary with proven queue continuity restored | 455 / 4274 | 5 | 530.5 s | accepted engine confirmation; exact v38 reproduction, no score claim |
| v42 | empty-land-force survival route for balanced offensive units | 452 / 4274 | 5 | 529.0 s | rejected; no surviving force recovery and a three-point regression |
| v48 | adapter 1.32 corrected government state, grounded controller retries, funded land-capability retention, and settled refresh | 602 / 4443 | 5 | 402.6 s | accepted mechanism and efficiency hardening; selected-seed score diagnostic only |
| v51 | loose Coinage-financed structural-commerce runway | 416 / 4602 | 5 | 442.5 s | rejected; reserve-edge construction caused forced building removals and maintenance oscillation |
| v52 | self-financing structural commerce with a doubled reserve | 470 / 4565 | 5 | 414.5 s | rejected; 30-60 turn projects remained too expensive in production opportunity cost |
| v53 | adapter 1.33 self-financing, doubled-reserve, maximum-20-turn structural commerce | 605 / 4437 | 5 | 409.3 s | accepted mechanism boundary; selected-seed score diagnostic only |
| v56 | adapter 1.33 extended to a 2,000-turn horizon | 653 / 9375 | 5 | 916.2 s | completed diagnostic; rejected as long-horizon correctness evidence because captured-city ownership remained stale |

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
- pre-version selection-role diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v38`
- rejected queue-role narrowing diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v40`
- adapter-1.31 confirmation: `artifacts/freeciv/pf-pln-strategic-960-v41`
- rejected empty-land-force recovery diagnostic: `artifacts/freeciv/pf-pln-strategic-960-v42`
- adapter-1.32 strategic-loop confirmation:
  `artifacts/freeciv/pf-pln-strategic-960-v48`
- rejected loose structural-commerce diagnostic:
  `artifacts/freeciv/pf-pln-structural-economy-960-v51`
- rejected self-financing structural-commerce diagnostic:
  `artifacts/freeciv/pf-pln-structural-economy-960-v52`
- adapter-1.33 bounded structural-commerce confirmation:
  `artifacts/freeciv/pf-pln-structural-economy-960-v53`
- adapter-1.33 2,000-turn lifecycle diagnostic:
  `artifacts/freeciv/pf-pln-strategic-2000-v56`

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

Adapter 1.31 instead narrows only the strategic selection boundary. A
ruleset-derived alternative outside the explicit defender list must be a
persistent land combat unit with nonzero defense and defense at least attack
before a city-local deficit can route it to `production_defense`. The emitted
projection records the current and required local garrison plus whether the
role came from the explicit list or from ruleset attack/defense values.
Offensive Armor remained `production_modernization`; it did not inherit
emergency-defense pressure.

V38 completed 960 turns with zero rejected actions and scored 455 against
4274. It selected Partisan as a ruleset-derived local defender twice, on turns
845 and 910, while all other defense selections remained the proven Alpine
Troops/Riflemen path. Because that trace still declared adapter 1.30, it is
behavior evidence only.

V40 tested the stronger interpretation in which the defense-first role also
controlled every queue-continuity boundary. It completed the horizon but
regressed to 335 against 4296. Citizens remained 39, while technology and
residual score fell to 118 and 178; meaningful actions fell from 1,075 to 707,
and effect-confirmation timeouts rose from zero to 13. Marines, Submarine, and
Cruiser no longer appeared. That extension was fully reverted: a queued combat
unit can still contribute actual defense even when its selection role is
offensive.

V41 reran the accepted selection-only policy with the correct adapter 1.31
identity. It exactly reproduced v38: score 455 against 4274, score components
`38/130/287`, 2,035 accepted actions, 1,075 meaningful actions, fourteen
acquired technologies, and zero effect-confirmation timeouts. The exact
reproduction supports mechanism stability and accepts the role-classification
correction. The two-point selected-seed difference from v34 is not a
statistically reliable score improvement.

V42 tested a separate bounded recovery route after the owned land-combat domain
became empty. It required a negative score gap, an actionable authoritative
defense deficit, horizon completion, and a balanced ruleset unit whose defense
was at least half its attack; this admitted Marines and Armor while excluding
Cannon. The route selected Marines on turns 845 and 917 and Armor on turn 875.

The trace did not establish a surviving recovery unit. In both Marines cycles,
city 131 advanced from 58 of 60 shields to zero while retaining Marines as its
target, but no Marines instance was present in the next authoritative snapshot.
This grounds a production-boundary reset, not the unobserved unit's intervening
lifecycle or removal cause. Armor reached 72 of 90 shields before the treasury
controller switched to an immediately completing Marketplace on turn 911:
authoritative gold was 15, effective cash was `-6` per turn, and retaining the
queue could not preserve the five-gold reserve through its remaining ETA.

V42 finished with score 452 against the same opponent score 4274. Its
`36/130/286` components regressed from v41's `38/130/287`; actions fell from
2,035 to 2,023 and meaningful actions from 1,075 to 1,063. The experiment was
fully reverted. It shows that lifting the safety firewall after complete force
loss is too late: the only buildable recovery city is already exposed to
same-boundary attrition, while its two-shield production rate and treasury
runway cannot reliably deliver Armor.

V43 tested only a six-city expansion target, leaving the accepted adapter 1.31
logic otherwise unchanged. It founded the sixth city on turn 93 and led v41 at
the turn-160, turn-260, and turn-360 checkpoints, but the advantage reversed
late. It finished at 381 against 4576 with components `48/124/209`, versus
v41's 455 against 4274 and `38/130/287`. It acquired eleven technologies rather
than fourteen. Mobile Warfare reached 1449/1590 on turn 746, then declined on
151 later turn boundaries and finished at 957/1590 while the proxy still
reported 57 net beakers per turn. The six-city target was reverted to five.
This is selected-seed rejection evidence, not a claim that expansion is
generally harmful.

V44 was intentionally interrupted at turn 70 after the first implementation of
observed research throughput revealed that repeated same-turn snapshots could
increment `stalled_turns` more than once. It is excluded from outcome evidence.
The emitter now increments elapsed stall duration only at a newly crossed turn
boundary, with a regression test covering repeated same-turn refreshes.

V45 tested a broader construction-runway gate on the accepted five-city
profile. It completed 960 turns with zero infrastructure failures, but scored
368 against 4338, acquired ten technologies, and produced components
`38/122/208`. Meaningful actions fell to 506 (0.527 per turn), versus v41's
1,075 (1.120 per turn). The generic gate suppressed productive work rather than
merely preventing unsafe queue churn and was fully reverted; adapter identity
remains 1.31.

V46 reran the exact accepted adapter 1.31 profile with the corrected research
observability contract. It reproduced v41 exactly: score 455 against 4274,
components `38/130/287`, fourteen acquired technologies, 1,075 meaningful
actions (1.120 per turn), zero engine rejections, and zero effect-confirmation
timeouts. The authoritative counter exposed 63 negative research boundaries.
Four occurred while the proxy projection was still positive: Refining on turn
434, Combustion on turns 652 and 654, and Flight on turn 724. This accepts the
telemetry as behavior-neutral diagnostic evidence; it does not revise the score
claim.

V48 validates adapter 1.32 against the same seed, initial-state fingerprint,
condition, opponent class, five-city target, and 960-turn horizon as v46. A
v47 launch without `FREECIV_RULESET_ROOT` failed during preflight before a game
was created and is excluded from mechanism and outcome evidence. V48 completed
1/1 jobs, reached the fixed horizon, had zero engine rejections, zero
effect-confirmation timeouts, and passed the complete release audit including
all PF-PLN phase replays and cognitive ancestry validation.

The upstream government-state correction removed a false transition lifecycle.
V46 reported revolution on 215 unique turns although only 25 were actual
Anarchy turns, then issued 27 government selections, including 19 Federation
selections. V48 reported revolution on exactly the seven turns whose current
government was Anarchy and issued no government selection after authoritative
Despotism became stable. The observability stall reason now follows the same
boundary, so a stale completion-turn marker cannot masquerade as active
Anarchy.

The retry and treasury changes reduced maintenance loops without weakening the
engine boundary:

- player-rate actions fell from 268 to 25 (`-90.7%`);
- food-governor actions fell from 294 to 94 (`-68.0%`);
- treasury queue selections fell from 122 to 23;
- Coinage occupancy fell from 2,022 to 1,696 city-turns (`-16.1%`);
- disordered city samples fell from 799 to 180 (`-77.5%`);
- deferred confirmations fell from 290 to 54 and expired confirmations from
  270 to 54, with zero timeouts in both arms; and
- meaningful actions fell from 1,075 to 375 (`-65.1%`) while the city count,
  technology count, and fixed horizon were preserved.

The action refresh now accepts the proxy's exact source-sequence quiet marker
as a settled full transfer. Queries per refresh fell from 2.207 to exactly
1.000, settled-marker and settled-response rates rose from zero to one, and
refresh wire traffic per turn fell from about 251 KB to 62 KB (`-75.2%`).
Refresh latency per turn fell from 136.5 ms to 47.8 ms (`-65.0%`). Combined
with fewer maintenance actions, engine gameplay time fell from 531.7 to 402.6
seconds (`-24.3%`), total actions from 2,035 to 1,335, and emitted events from
23,186 to 16,429.

The funded land-capability continuity boundary did not need its new dedicated
`production_land_capability` selection route in this trajectory: an ordinary
grounded garrison deficit selected Mech. Infantry first. The shared retention
boundary then allowed that unit to complete. V48 finished with three Alpine
Troops, two Riflemen, two Triremes, and one Mech. Infantry, versus two Triremes
and no land combat unit in v46. All 39 combat removals in v48 were exactly
attributed to `combat_defender_lost`; the four founder removals were exactly
attributed to `city_founded`.

V48 scored 602 against 4443, with components `47/130/425`, versus v46's 455
against 4274 and `38/130/287`. It retained the same fourteen acquired
technologies, ended with 47 citizens instead of 38, and had progressed 932
beakers into Mass Production rather than 152. This is a `+147` (`+32.3%`)
selected-seed player-score diagnostic, not a causal score claim: the opponent
also gained 169 points and the final score margin changed from `-3819` to
`-3841`. Both arms remain losses.

The structural economy is more stable but is not solved. V48 ended at
`-20` operating gold and `+20` Coinage capitalization for zero effective cash,
and structural operating cash was negative on 863 turns versus 845 in v46.
Coinage still occupied 1,696 of 4,800 city-turns. Adapter 1.32 therefore proves
that the controller no longer oscillates on Coinage-funded cash or restores tax
against an unfunded projection; it does not prove positive structural cash
flow, a superior government policy, or a win-rate improvement.

Adapter 1.33 tests a bounded escape from permanent Coinage capitalization. The
first v51 gate allowed construction to consume treasury principal as long as
the configured reserve survived. Its first Marketplace projected `-1`
gold/turn during construction and only six gold after the post-completion
runway, exactly the minimum reserve. Five commerce projects completed, but four
of those buildings were later forcibly removed. Treasury-stabilization
selections rose from 23 to 83, food-stabilization selections rose from 14 to
75, known technologies fell from 65 to 59, population fell from 47 to 36, and
score fell to 416. That gate is rejected.

V52 required nonnegative post-switch cash flow and twice the ordinary reserve.
It eliminated the reserve-edge failure but still selected seven projects,
including Marketplaces with 30- and 60-turn completion times. Five completed
commerce buildings were later removed, and the arm scored 470. This proves
that treasury safety alone does not price the production opportunity cost.

The accepted v53 boundary additionally requires completion within 20 turns.
It selected five short projects from turn 634 onward: a Marketplace, two Banks,
a Courthouse, and a Stock Exchange. Every selected instance completed and none
was removed. Relative to v48:

- score was 605 versus 602 and score margin was `-3832` versus `-3841`;
- known technologies were 67 versus 65 and final net research was 35 versus
  25 beakers/turn;
- Coinage occupied 1,615 versus 1,696 city-turns;
- population was 43 versus 47 and surviving units were six versus eight;
- meaningful actions were 414 versus 375; and
- gameplay runtime was 409.3 versus 402.6 seconds.

The `+3` score and `+9` margin are selected-seed diagnostics, not evidence of
superiority. The accepted claim is narrower: the controller can complete
short, self-financing structural repairs without reproducing the forced-removal
cascade observed in v51 and v52.

The government counterfactual was separately tested at 240 turns. With a
declared six-gold operating gain, the gate initiated exactly one Monarchy
transition at turn 102, observed one Anarchy turn, and remained in Monarchy.
It scored 201 against the matched bounded-policy Despotism control's 202; its
margin was `-430` versus `-381`. Although final net research was 26 versus six
beakers/turn, population was 34 versus 35. The mechanism is retained as opt-in,
but `preferred_government` and `government_economic_gate_enabled` remain
disabled in every live profile. Artifacts:
`artifacts/freeciv/pf-pln-government-gate-240-v54` and
`artifacts/freeciv/pf-pln-government-gate-240-control-v55`.

V56 extended the same selected seed and adapter to a 2,000-turn policy and
engine horizon. It completed all 2,000 turns with zero rejected actions, no
infrastructure failure, 37,190 validated events, and a passing 10-check release
audit. Engine gameplay took 916.2 seconds; total backend time, including a
48.8-second cold model-readiness call, was 965.5 seconds. Live event streaming
remained responsive throughout.

The extended trajectory is rejection evidence for long-horizon correctness.
At turn 960 it had only 59 known technologies and a score of 420, versus v53's
67 and 605. By turn 2,000 it had acquired only two additional technologies
(`Flight` and `Automobile`), reached 991/1,590 progress toward
`Mobile Warfare`, and scored 653 against 9,375. Operating cash ended at -21
gold/turn, temporary Coinage capitalization at +16, effective cash at -5, and
treasury at eight gold.

More importantly, three cities' Alpine Troops shield stocks stopped changing
at turns 415, 458, and 461, respectively. The terminal relay projection still
listed cities 109, 127, and 131 as player-owned with those unchanged queues.
The terminal observer packets instead reported all three city IDs as owned by
the opponent. The relay therefore retained captured cities as authoritative
own cities. After turn 960, the stale queues occupied 3,120 apparent
city-turns; the two actually retained cities spent 2,060 city-turns on
Coinage. No unit appeared after turn 453, and the planner made no impact
selection between turns 891 and 1,800.

The unit-removal journal itself remained attributable: 18 disappearances were
exact packet-backed combat losses and four were inferred founder consumption,
with no unattributed removal. The failure is city ownership/lifecycle
reconciliation, not unit-removal attribution. Until captured cities are
removed or re-owned in the relay projection and score/population components
are derived from that corrected set, a 2,000-turn score comparison would
measure stale state as well as policy behavior.

Any score claim still requires a preregistered paired-seed cohort with the
historical five-city policy held fixed. The current evidence supports contract,
mechanism, queue-efficiency, and runtime claims only.

V58 confirms the captured-city correction on the same 2,000-turn seed,
condition, opponent class, policy horizon, and engine horizon. A v57 launch
without `FREECIV_RULESET_ROOT` failed during preflight before creating a game
and is excluded. V58 used pinned proxy patch-series identity
`cbc47dc57bd8457ee12a76e3bb60d187dd485c4d7bf4534bed6fd2add401cc57`,
completed all 2,000 turns, emitted 40,431 validated events, had zero rejected
actions and zero infrastructure failures, and passed all ten release-audit
checks including cognitive-trace ancestry. Engine gameplay took 919.4 seconds
and total backend time took 921.1 seconds.

The engine trajectory exercised all three ownership transitions that v56
misrepresented:

- city 127 was present in authoritative production state through turn 414 and
  absent from turn 415 onward;
- city 131 was present through turn 1006 and absent from turn 1007 onward; and
- city 109 was present through turn 1009 and absent from turn 1010 onward.

The terminal observer packets reported cities 109, 127, and 131 as opponent
owned. The terminal agent projection contained only the actually retained
cities 101 and 182. By contrast, v56 retained all three captured cities in
every production snapshot through turn 2,000. The corrected proxy now handles
`PACKET_CITY_SHORT_INFO`, replaces a captured city's cached full record with
its public foreign-city fields, invalidates both owners' wonder caches, and
therefore prevents stale production, economy, and buildability data from
entering own-city planning.

V58 scored 717 against 9,172, versus v56's 653 against 9,375. Its terminal
components were 10 citizen, 130 technology, and 577 residual points. Those
numbers are a selected-seed post-correction diagnostic, not a causal score
improvement claim: the corrected ownership changes the agent's later action
trajectory, this is one game, and both runs remain losses. The accepted claim
is that captured-city ownership and own-city planning state now agree with the
engine through a full 2,000-turn run.
