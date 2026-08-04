# FDAS PR89 grounded replacement-capacity production result

Date: 2026-08-04

## Result

PR89 passes its preregistered mechanics and recurrence gates. All 16 fixed
fresh-seed games completed from clean source commit
`f46fffc2d1347f432d4c1751aa275610ba180b4f`, with zero infrastructure
failures, zero resumes, and zero rejected engine actions. Fifteen games reached
turn 160; one ended at the genuine absorbing endpoint of player elimination on
turn 159.

The strict cohort audit accepted every game and reproduced byte-for-byte on a
second full pass.

| Measure | Result |
|---|---:|
| Games | 16/16 completed |
| Shadow evaluations | 996 |
| Replacement-capacity deficit goals | 1,153 |
| Capacity production candidates | 1,857 |
| Grounded delayed production operations | 1,857 |
| Grounded-operation games | 16/16 |
| Production-model abstentions | 0 |
| Event rows | 329,122 |
| Rejected engine actions | 0 |

Every emitted capacity production candidate was grounded to the exact
ruleset/state production model. Each carried a two-step queue-selection plus
authoritative-product-observation operation, a complete six-premise
RequirementSet identity, at least one exact current/future resource claim, and
a completion interval inside the declared 64-turn observation horizon. Every
candidate remained shadow-only and explicitly blocked by
`delayed-production-completion-unobserved`; queue selection contributed no
immediate capacity relief.

## Audit hardening

The first aggregate pass exposed one audit-only defect: the oldest replacement
lifecycle audit accepted only `horizon_reached=true`, even though the harness
and later audits use fixed-horizon-or-genuine-absorbing-terminal completion.
Seed `111253` was cleanly eliminated on turn 159, so its new production audit
passed while that parent audit rejected the endpoint. The parent audit was
hardened to require matching status and terminal-event evidence for game-over
or player-elimination endpoints, and a regression test was added. No event,
counter, seed, gameplay result, or mechanism output was altered. The corrected
full audit then passed twice identically.

## Evidence identity

- Cohort report structural hash:
  `98e70d6a25f92e146e2200311e0deccfd0d49aa5f77df19d9e1d9ed0a3300d5a`
- Cohort report SHA-256:
  `28de3405cbcdcf9a8299ca0d8cebb8e722ca2cd4c893480861656172c6b5b0bf`
- Run-summary SHA-256:
  `2c72874a7795efd6ded5a38fa134c45e95cbad08c31801a004de165c814f700d`
- Implementation regression suite before launch: 152 passed.
- Audit-hardening focused regression: 3 passed.

The machine-readable report is
`docs/freeciv/evidence/fdas-pr89-replacement-capacity-production.json`; the
immutable generated run root is
`artifacts/freeciv/fdas-pr89-replacement-capacity-production-v1`.

## Claim boundary

This confirms that the PR88 capacity bottleneck transfers into recurrent,
ruleset-grounded delayed defender-production candidate mechanics on real engine
games. It does not show that the existing policy selects those queues, that a
new defender is observed, that a safe replacement relation becomes available,
or that score or win rate improves. The next bounded step is lifecycle/outcome
observation for matched legacy-selected queue actions, followed only later by a
separately preregistered authority comparison.
