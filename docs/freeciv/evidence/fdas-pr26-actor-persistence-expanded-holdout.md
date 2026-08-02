# FDAS PR26 expanded attributed-defense holdout

Status: expanded held-out validation completed; all eight contextual proposals
demoted on untouched engine evidence; no promotion, authority, score, or
gameplay-improvement claim.

## Frozen design

This evaluation retained the PR25 training population, outcome target, feature
schema, miner, thresholds, and eight resulting proposal identities. It added
the complete predeclared three-seed extension (`104801`, `104803`, and
`104827`) to the existing untouched holdout seed `104789`. Collection did not
stop when the eight-sample floor was crossed.

All four held-out games completed the fixed 160-turn horizon from clean source.
Commit `846f426a` changes only evidence documentation relative to the original
`5dc84b89` cohort; every source records the identical implementation hash
`072f5dfed2b2d40289a9fb5e726867c5fd41c0538899c4c76230dd391a535d67`.
All event ledgers validated without errors or warnings, and all per-game
delayed-label audits passed.

| Partition | Seed | Resolved | Positive | Negative |
|---|---:|---:|---:|---:|
| Training | 104773 | 2 | 2 | 0 |
| Training | 104779 | 7 | 5 | 2 |
| Holdout | 104789 | 2 | 2 | 0 |
| Holdout | 104801 | 5 | 3 | 2 |
| Holdout | 104803 | 3 | 1 | 2 |
| Holdout | 104827 | 5 | 5 | 0 |
| **Holdout total** | — | **15** | **11** | **4** |

One late training label remained pending beyond the fixed horizon and correctly
abstained. All 15 held-out labels were resolved.

## Held-out verdict

The same eight proposals were mined deterministically from the frozen training
partition. None survived replay:

| Proposal family | Rules | Holdout activations | Brier improvement | Calibration improvement | Verdict |
|---|---:|---:|---:|---:|---|
| Actor type is Musketeers, alone or conjoined | 4 | 0 / 15 | 0.00000 | +0.10227 | Insufficient activations |
| City size band is 1, alone or conjoined | 4 | 4 / 15 | -0.00171 | -0.06061 | No out-of-sample improvement |

The Musketeer associations did not transfer to the held-out actor population.
The size-1-city associations did transfer syntactically, but their `0.8333`
prediction was worse than the `0.7273` training baseline on held-out outcomes.
This is evidence that the current small training cohort learned population-
specific correlations, not a durable predictive rule.

The gate report is accepted because the source, partition, target, persistence,
proposal, verdict, and authority-safety contracts all passed. All eight rules
were demoted; there were zero approvals and zero promoted rules. Truth, policy,
and readout authority remained false. The report structural hash is
`0cb683db4a7bf2a300c081afd71c1f00b31185c4bdaaab63f217f1bea41ade65`.
The machine-readable report is
[`fdas-pr26-actor-persistence-expanded-holdout-engine.json`](fdas-pr26-actor-persistence-expanded-holdout-engine.json).

## Scientific boundary and next step

The delayed induction path is now demonstrated end to end, including the most
important behavior: plausible training rules are rejected when they fail to
generalize. These candidates must remain quarantined and must not be retuned on
the same holdout.

Further induction quality work requires a new discovery cycle with a broader
training population and more causally relevant preregistered features, followed
by a new untouched confirmation cohort. That is separate from the FDAS
mechanism-completeness claim and cannot justify live readout or score authority
without its own safety and gameplay experiment.

## Reproduction

The machine-readable report records every input path and digest. Re-run
`scripts/freeciv/run_fdas_induction_holdout.py` with the two PR25 training
stores, all four holdout stores listed above, their paired
`fdas-induction-outcome-labels.json` stores, target
`durable-attributed-actor-city-defense/32-turn/1.0`, and the strict flags:

```text
--require-engine-source --require-horizon --require-proposal
```

The expected exit code is `0`: the mechanism gates pass while each proposal is
explicitly and safely demoted.
