# PF-PLN production-recovery hardening

Date: 2026-07-29

## Scope and accepted claim

This evidence covers the long-horizon production-stall correction in
`grounded-impact-planner/1.34`. It supports a correctness, mechanism, and
queue-efficiency claim on one selected engine seed. It does **not** support a
population score or win-rate claim.

The final source-frozen confirmation is:

- artifact:
  `artifacts/freeciv/pf-pln-production-recovery-2000-v66`;
- engine condition: `e_full_loop`;
- seed: `4543804`;
- ruleset: `civ2civ3`;
- turn horizon: `2,000`;
- implementation SHA-256:
  `168a3d1433bac5c3703fa8d97e8b8cfbdc24c053cdc53bc6fa722d47a7a51338`;
- event SHA-256:
  `40481f05e8cf9b910dbb992f80f802ae27f464de8404454948d8f00c924fb4a9`;
- aggregate SHA-256:
  `3380939e0ce89070d783c02810a858c66469e9e720fdf58c42b9b3e1a61f21ce`;
- release-audit SHA-256:
  `13841aad9c8b702a012c161988984b747078f9de3140e7a3385d6fab170260d0`.

## Root cause

The earlier same-seed diagnostic at
`artifacts/freeciv/pf-pln-strategic-2000-v60` exposed two different failure
modes that looked like one production stall.

First, expansion reservation used the existence of a city-count deficit rather
than the existence of an executable founder build. When a replacement founder
was unsafe, unaffordable, or temporarily blocked after route attrition, the
planner rejected the founder action but continued suppressing unrelated
productive queues. This created a deadlock: expansion could not materialize,
yet recovery, research, defense, and economy work could not use the reserved
production capacity.

Second, after a replacement founder died on the settlement route, automatic
city production could immediately rebuild it. The former attrition check
depended on a currently visible enemy near the producer and did not model a
city-loss recovery lifecycle. A route loss away from the city was therefore
forgotten at the producer. Repeating production caused 187 founder queue
starts, but only 10 founder completions, including a late run of repeatedly
discarded queues.

Coinage then hid the remaining stall. It was treated as an indefinite safe
queue. Effective gold could appear non-negative only because Coinage converted
shields to cash, while structural operating cash remained negative. There was
no bounded bridge age, no explicit productive-exit goal, and no pressure
artifact when every candidate was blocked. Research throughput and unresolved
goals consequently became invisible precisely when the planner had nothing it
could execute.

## Correction

The correction keeps all decisions grounded in the current legal action set and
authoritative state:

1. Founder production is considered viable only when the same predicate used
   for materialization proves:

   - a legal ruleset-backed founder target;
   - positive fixed-horizon value and sufficient settlement runway;
   - the required city garrison during city-loss recovery;
   - one surplus local defender when a packet-visible local threat exists;
   - treasury reserve at both projected completion and settlement;
   - immediate removal of the producing city's Coinage contribution; and
   - ruleset-declared founder upkeep between completion and settlement.

2. Expansion reserves other production only if at least one founder action
   passes that complete predicate. A blocked founder therefore cannot deadlock
   research, defense, economy, or recovery production.

3. Owned-city loss opens an explicit replacement lifecycle. Founder attrition
   before that loss does not consume the new lifecycle's retry allowance.
   Attrition during recovery starts an exponential bounded backoff of
   `20, 40, 80, ...` turns, capped at 200. Route loss remains evidence during
   that backoff even if the responsible enemy is no longer locally visible.

4. A recent founder loss can interrupt an automatically repeating founder
   queue into Coinage. The replacement is retried only after the backoff and the
   exact garrison and financing gates pass.

5. Coinage is now a bounded 20-turn bridge. Once expired, a productive
   ruleset-backed exit is exposed as `production_continuity` when treasury
   reserve permits it. If operating cash remains negative and Coinage alone
   masks the loss, treasury pressure remains unresolved instead of being
   reported safe.

6. Research sustainability is its own pressure goal. It activates when net
   beakers are non-positive or technology upkeep consumes at least 25% of gross
   beakers, and its grounding includes gross, upkeep, net, and observed stall
   duration.

7. Pressure propagation now emits a stranded artifact even when there are no
   candidates. This distinguishes “no problem” from “known goals with no legal,
   safe materialization.” The aggregate exposes stranded events per turn and
   stranded goals per decision.

## Same-seed mechanism result

| Measure | V60 before | V66 after | Change |
| --- | ---: | ---: | ---: |
| Founder production changes | 187 | 9 | -178 (-95.2%) |
| Founder completions | 10 | 9 | all 9 selected queues completed |
| Production changes | 466 | 103 | -363 (-77.9%) |
| Decision impact actions | 734 | 355 | -379 (-51.6%) |
| Decision impact turn rate | 0.2780 | 0.1045 | -0.1735 (-62.4%) |
| Terminal score | 455 | 475 | +20 |
| Score gain from turn 1 | 352 | 372 | +20 |
| Game win | 0 | 0 | unchanged |

The V66 founder queue starts occurred on turns
`1, 26, 45, 78, 576, 633, 698, 758, 851`. Their corresponding founder
completions occurred on turns
`30, 33, 51, 81, 581, 637, 702, 762, 854`. There were no selected founder
queues discarded before completion.

The initial founder established a city on turn 4, and three produced founders
established cities on turns 35, 38, and 84. Replacement founders were lost on
turns 583, 639, 704, 764, and 856. After the turn-764 loss, the next retry was
delayed to turn 851, an 87-turn interval that satisfies the 80-turn lifecycle
guard. No further founder was queued after the turn-856 loss because the
backoff, financing, and garrison preconditions did not jointly become
executable.

V66 exactly reproduced the behavioral metrics and lifecycle turns of the
preceding V65 diagnostic, while adding the final telemetry-volume correction.
Interrupted V62, V63, and V64 diagnostics are excluded; they did not complete
the horizon and were used only to expose intermediate gating defects.

## Terminal unresolved state

The fix prevents churn and makes the stall causal state visible; it does not
pretend that the losing position became solvable. At turn 2,000 the player had
one retained city, score 475, and a score gap of `-9,382`. Roma was size 6 and
producing Coinage with:

- food surplus: `0`;
- shield surplus: `11`;
- city gold surplus: `-10`;
- operating gold: `-11`;
- Coinage capitalization: `+11`;
- effective gold: `0`;
- treasury: `2`;
- gross research: `6`;
- technology upkeep: `4`;
- net/effective research: `2`.

The terminal pressure artifact had no materialized operation traces, but it
retained positive dependency pressure for:

- expansion: `1.28`, grounded by owned-city-loss recovery at `1-of-5`;
- food sustainability: `1.75`, grounded by city 101's reserve deficit;
- production continuity: `1.25`, grounded by expired Coinage, with city 101
  correctly marked treasury-blocked;
- research sustainability: `1.55`, grounded by gross 6, upkeep 4, and net 2;
- score: `3.50`, grounded by the `-9,382` gap;
- survival: `1.50`, grounded by bounded visible naval-threat memory; and
- treasury sustainability: `1.65`, grounded by Coinage masking operating
  gold `-11` as effective gold `0`.

This is the intended failure behavior: unsafe work is not fabricated, and each
unrelieved dependency remains inspectable.

## Validation

V66 completed one of one requested games with no infrastructure failure and no
resume. It emitted 40,133 valid events, with:

- zero schema errors;
- zero validation warnings;
- zero rejected engine actions;
- zero incomplete cognitive actions;
- 368 planned cognitive actions with complete ancestry;
- 18 of 18 required confidence declarations; and
- all 10 release-audit checks passing.

The post-game calibration flush originally caused the V65 release audit to fail
the 5 MiB/turn volume gate. It emitted 13,479 repeated samples for only 69
belief atoms. The harness now retains the latest terminal prediction per atom.
V66 emitted exactly 69 calibration samples for 69 unique atoms, reducing the
maximum turn volume from 6,353,469 bytes to 2,613,052 bytes, below the
5,242,880-byte budget.

The canonical Python 3.8 FreeCiv lane passed 479 tests before the telemetry
correction. The impacted harness, planner, and pressure lane then passed 280
tests after that correction, and its dedicated deduplication regression passed
independently. The only emitted test warning was pytest-asyncio's notice that
its future default fixture loop scope will change.

## Claim boundary

The `+20` same-seed score difference is diagnostic only. V60 and V66 are
adaptive development executions from different implementation snapshots, the
sample size is one, the opponent still led by 9,382 points, and both runs were
losses. No score superiority, win-rate improvement, confidence interval, or
population generalization is claimed.

The accepted result is narrower and directly observed: production no longer
thrashes on non-materializable founder recovery, every selected founder queue
completed, blocked goals remain visible, and the complete 2,000-turn
engine-backed trace passes the release contract.
