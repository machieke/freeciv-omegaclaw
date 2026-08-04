# FDAS PR79 coordinated-replacement fresh recall cohort

Date: 2026-08-04

## Result

The preregistered primary audit fails. All 16 fixed fresh-seed games completed
from clean commit `ace3fe4734bbb2ba4cf271996b57937efd9ed76d` without
resume or infrastructure failure, and all sources were clean and commit-bound.
Seven independent games produced at least one grounded replacement pair, so
the fresh-game recall-opportunity gate passed. One zero-opportunity game,
seed `109607`, was eliminated at turn 147 and therefore failed the inherited
PR77 requirement to reach the complete 160-turn horizon. The failed game is
retained in the denominator and is not replaced.

The descriptive game-level opportunity result is:

- 7 of 16 games with one or more grounded safe-chain pairs;
- opportunity-game rate 0.4375;
- Wilson 95% interval 0.23099 to 0.66821; and
- 806 grounded pair rows in total.

The contributing seeds are `109619`, `109627`, `109631`, `109633`, `109637`,
`109639`, and `109647`. Pair rows are not independent observations: seed
`109633` contributed 729 of 806 rows (90.4%). The positive result is therefore
the seven-game recall count, not the raw row total.

The deterministic cohort report is
`fdas-pr79-coordinated-replacement-readout-fresh-cohort.json`, structural hash
`f35b2b92ee1b4508a6021141fc128a1a0d08b6316981f048a6ece0791250ae02`.
Its primary acceptance value remains `false`.

## Mechanical failure interpretation

Seed `109607` completed normally through a legitimate terminal state rather
than an infrastructure error: player elimination occurred at turn 147 after
204 accepted engine actions and zero rejected actions. It emitted 9,173 valid
events and no replacement opportunity. The cohort failure is specifically the
predeclared full-horizon contract inherited from the lifecycle audit; it is
not evidence of malformed replacement state or readout rows.

This result does not justify silently changing that contract. A later,
explicitly labelled sensitivity analysis may treat legitimate terminal player
elimination as a completed observation, while leaving this primary result
unchanged.

## Operational finding

The cohort exposed a separate efficiency defect in seed `109633`. That game
reached the horizon but produced 208 persistent replacement operations, 729
pair rows, and 508,032 events. Its event ledger is approximately 511 MB and
engine gameplay took 1,595.06 seconds, compared with a cohort median of 379.95
seconds. The other 15 games together produced 315,891 events.

The lifecycle correctly deduplicates active operations, but it can propose the
same logical replacement chain again immediately after an earlier operation
expires. Terminal records then accumulate in the durable store and are
reprojected into each later AtomSpace revision. The next hardening step must
bound terminal-chain reproposal while retaining terminal evidence and current
safe-chain recall.

## Claim boundary

PR79 provides descriptive evidence that grounded coordinated-replacement
opportunities transfer to multiple fresh games. Because the preregistered
primary audit failed, it is not a full mechanical-transfer pass. It estimates
no chain transition value and establishes no preference, action, causal goal
relief, score, or win-rate improvement.
