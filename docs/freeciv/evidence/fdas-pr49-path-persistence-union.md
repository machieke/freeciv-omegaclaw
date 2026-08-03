# PR49 path-persistence candidate-union confirmation result

## Decision

PR49 **passes** every preregistered mechanical and progression gate. Bounded
temporal corridor persistence recurrently retained one current legal candidate
beyond the frozen corrected-probe union on fresh engine games, while preserving
scalar ranking and action selection.

## Cohort

- source commit:
  `fa4bdc074a0f53f4088ce9083e5deb17ff72e3c2`;
- seeds: `105397`, `105401`, `105407`, `105437`, `105449`, `105467`,
  `105491`, `105499`;
- all eight games reached turn `160`;
- infrastructure failures: `0`;
- rejected actions: `0`; and
- cumulative engine runtime: 989.2 seconds.

## Frozen gate results

| Measure | Result | Gate |
|---|---:|---:|
| persistence-union events | 654 | at least 300 |
| persistence readouts | 1,613 | at least 500 |
| protected members | 1,050 | descriptive |
| temporal retentions | 162 | at least 8 |
| temporal additions beyond probes | 105 | at least 8 |
| smoothing retentions | 155 | descriptive |
| dwell retentions | 6 | descriptive |
| hysteresis retentions | 1 | descriptive |
| regret-gate reanchors | 91 | at least 1 |
| expired routes | 130 | at least 1 |
| games with temporal additions | 7/8 | at least 4/8 |
| observed game addition rate | 0.875 | descriptive |
| Wilson 95% interval | `[0.5291, 0.9776]` | lower at least 0.10 |
| persistence fallbacks | 0 | 0 |
| action-selection changes | 0 | 0 |

Every persistence event reproduced its result and signal-ledger hashes, exact
snapshot/revision and corrected-probe parent binding, scalar winner and order,
bounded membership, exact computed reachability regret, regret reanchoring,
and controller state continuity. All event ledgers validated without warnings
or errors. No temporal signal gained scalar-score, truth, policy/readout,
advection, capacity, source--sink-flow, or action-selection authority.

Per-game counts were:

| Seed | Unions | Readouts | Retentions | Additions | Regret reanchors | Expiries |
|---:|---:|---:|---:|---:|---:|---:|
| 105397 | 65 | 206 | 20 | 14 | 9 | 17 |
| 105401 | 31 | 48 | 4 | 3 | 2 | 7 |
| 105407 | 155 | 486 | 44 | 27 | 24 | 46 |
| 105437 | 74 | 122 | 15 | 7 | 12 | 5 |
| 105449 | 31 | 31 | 0 | 0 | 0 | 2 |
| 105467 | 40 | 56 | 3 | 1 | 3 | 4 |
| 105491 | 166 | 527 | 65 | 46 | 34 | 33 |
| 105499 | 92 | 137 | 11 | 7 | 7 | 16 |

The canonical report is
`docs/freeciv/evidence/fdas-pr49-path-persistence-union.json`, with report hash
`7bae153ff5769e94da47a7922df5623b87ce325b23380a1d0079d95e053b86d9`.

## Auditor correction

Audit version 1.0 initially rejected two semantically valid events because it
required every retained route to have strictly positive instantaneous regret.
One event used dwell while the retained route was also the instantaneous best;
one used smoothing as the deterministic tie-break between equal instantaneous
reachability values. Neither case violates the preregistered maximum-regret
gate.

The initial rejected report is preserved in commit `c2db912`, with report hash
`2af88b667e1793093b25b411c1240c9ff38ddd6c71bdabbc64c57a4b67bebe26`.
Audit version 1.1 removes only the unpreregistered positive-regret assumption
and strengthens the correct invariants: it recomputes exact route regret,
checks the deterministic smoothing route choice, verifies regret reanchoring,
and requires dwell/hysteresis to preserve the previously selected route. The
cohort, source, seeds, controller, thresholds, and progression gates were not
changed.

## Supported claim

> On the frozen defense choice surface, bounded smoothing, momentum, dwell,
> hysteresis, expiry, and reachability-regret gating recurrently add protected
> temporal candidate membership beyond the corrected-probe union on fresh
> engine games while preserving scalar action selection.

This establishes temporal candidate recall, not candidate precision or value.
Because the layer is shadow-only, it does not change gameplay and cannot
support a score or win-rate claim. The historical CT4 adverse ranking-authority
result remains controlling evidence against granting temporal signals scoring
or action authority.

## Next bounded step

PR49 closes the path-persistence-without-fluid comparator. Source--sink flow
may now be considered only as a separately declared, shadow-only numerical
layer. It must first show incremental candidate recall or useful route
allocation beyond the frozen calibrated, probe, and persistence unions; it
must not receive ranking or action authority without a separate candidate-value
and gameplay confirmation program.
