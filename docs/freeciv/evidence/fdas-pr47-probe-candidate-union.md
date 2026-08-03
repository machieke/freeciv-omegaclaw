# PR47 corrected-probe candidate-union confirmation result

## Decision

PR47 **passes** every preregistered mechanical and progression gate. Healthy
corrected forward/backward probes recurrently recalled one candidate beyond
the frozen calibrated union on fresh engine games, without changing scalar
ranking, action selection, truth, policy/readout authority, advection, or
capacity allocation.

## Cohort

- source commit:
  `997ad95e940bf597196c908eb0cc52874dd3b0e0`;
- seeds: `105337`, `105341`, `105359`, `105361`, `105367`, `105373`,
  `105379`, `105389`;
- all eight games reached turn `160`;
- infrastructure failures: `0`; and
- rejected actions: `0`.

## Frozen gate results

| Measure | Result | Gate |
|---|---:|---:|
| probe-union events | 445 | at least 300 |
| candidate reachability readouts | 949 | at least 500 |
| healthy evaluations | 445 | all |
| incomplete factor graphs | 0 | 0 |
| probe fallbacks | 0 | 0 |
| mixed-action unions | 47 | at least 8 |
| additions beyond calibrated union | 161 | at least 8 |
| games with additions | 8/8 | at least 4/8 |
| observed game addition rate | 1.0 | descriptive |
| Wilson 95% interval | `[0.6756, 1.0000]` | lower at least 0.10 |
| action-selection changes | 0 | 0 |

Every probe event reproduced its result and signal-ledger hashes, exact
snapshot and revision, calibrated-union parent hash and membership, scalar
winner, one-region bound, positive corrected-overlap selection, and frozen
probe configuration. All event ledgers validated without warnings or errors.

Per-game event/readout/addition counts were:

| Seed | Union events | Readouts | Additions |
|---:|---:|---:|---:|
| 105337 | 38 | 59 | 7 |
| 105341 | 47 | 105 | 17 |
| 105359 | 85 | 217 | 38 |
| 105361 | 86 | 130 | 14 |
| 105367 | 36 | 95 | 16 |
| 105373 | 21 | 23 | 1 |
| 105379 | 65 | 172 | 41 |
| 105389 | 67 | 148 | 27 |

The canonical report is
`docs/freeciv/evidence/fdas-pr47-probe-candidate-union.json`, with report hash
`fad3de1c888ff87fab1968dd6a88e2c93e214a5c1671ab5f91cf27af861d3ef5`.

## Supported claim

> On the frozen defense choice surface, a healthy two-stream corrected-probe
> readout with a one-region cap recurrently adds bounded candidate membership
> beyond the frozen calibrated union on fresh engine games while preserving
> scalar action selection.

This result establishes candidate recall, not candidate precision or value.
It does not identify censored counterfactual outcomes, prove that the added
candidate was better, improve gameplay, change score, or support a win-rate
claim.

## Next bounded step

Freeze scalar PF-v2, the calibrated union, and corrected probes as the
baseline. The next cheap comparator is path persistence without fluid
transport: smoothed corridor momentum and dwell time may affect protected
candidate membership only. Advection, capacity solving, and source-sink flow
remain disabled until that comparator is implemented and independently
validated.
