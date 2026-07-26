# PF-PLN expansion deadline recovery diagnostic v1

Status: complete; correctness mechanism activated; no score or win-rate
improvement supported

The claim-ineligible `expansion_deadline_recovery_diagnostic_v1` cohort
completed all 40 fresh paired seeds and 80 engine arms from clean, stable
commit `7141dcd`. Every paired initial state matched, arm order was exactly
balanced, and there were no infrastructure failures.

Both arms used target four, a 15-turn post-settlement runway, pressure,
conductance learning, and score alignment. The only effective difference was
`expansion_settlement_deadline_recovery_enabled`: false under baseline and
true under treatment.

## Outcome

Mean turn-60 score changed from 120.300 to 120.225. The paired difference was
**-0.075** with 95% paired-bootstrap interval **[-0.400, +0.250]** and exact
two-sided paired sign-flip `p=0.765625`. Three pairs improved, 33 tied, and
four declined. This does not support a score improvement.

| Outcome | Baseline | Treatment | Paired delta | 95% interval |
|---|---:|---:|---:|---:|
| Total score | 120.300 | 120.225 | -0.075 | [-0.400, +0.250] |
| Citizen component | 15.900 | 15.725 | -0.175 | [-0.450, +0.050] |
| Technology component | 102.100 | 102.100 | 0.000 | [0.000, 0.000] |
| Residual component | 2.300 | 2.400 | +0.100 | [-0.050, +0.350] |
| Score margin | -5.250 | -4.625 | +0.625 | [-0.350, +2.275] |

Fixed-horizon lead rate changed from 40.0% to 42.5%. Sixteen pairs led under
both arms, 23 under neither, none only under baseline, and one only under
treatment. Exact McNemar `p=1.0`; this does not support a lead-rate or
win-rate improvement.

The margin estimate is not a robust own-policy benefit. In the sole
treatment-only lead pair, seed `3852767`, own score increased by four but
opponent score fell by 25, producing a +29 margin swing. The margin interval
includes zero and the cohort was not eligible for a claim.

## Mechanism

Deadline recovery activated in 10 of 40 treatment games and no baseline game.
Treatment made 31 recovery-route attempts, 30 of which moved strictly closer
to an owned city. It attempted and completed 14 exact joins, restoring 28
population. This confirms that the engine adapter can salvage otherwise
non-score-bearing founders instead of leaving them on a late expansion route.

The lifecycle constraint also prevented four settlements:

- settlement completions changed from 111 to 107, a paired mean difference
  of -0.100 [-0.200, -0.025];
- cities gained changed from 107 to 104, a paired mean difference of -0.075
  [-0.150, 0.000]; and
- founder-production changes were identical, isolating the effect to
  existing-founder deadline handling.

All seven nonzero own-score pairs were among the 10 activated games. Within
those games, three improved, three tied, and four declined, for a net three
point loss. The restored late population and avoided late settlements
therefore approximately balance at turn 60. Adapter 1.6 is supported as a
bounded lifecycle-correctness regularizer, not as the next score-bearing
optimization.

## Correctness, safety, and replay

All 80 streams and 115,810 events pass schema, ordering, proof, provenance,
and causal validation with zero warnings. Exact replay covered every
treatment trace and all 2,985 pressure decisions. Selection and schedule
integrity reproduced with zero failures and unchanged sources. Pressure
differed from canonical grounded utility ordering in 185 decisions (6.20%).

Engine rejection and model fallback rates were zero in both arms. Every full
loop remained under 30 seconds, paired initial-state fidelity passed, and all
safety gates passed.

The aggregate byte SHA-256 is
`bee5421b093dd4803a60884180a5b44e461dbe8b474a2bc8896a48cfa47f8b7f`.
The replay structural artifact hash is
`88b6c5392371fbb7471cb822e32dffc67be1786963cac644ca4e1910eab61c56`,
its source-set hash is
`13b06c8327eb49e0a58dd6f3cfd9f3f4d7c4205ccbbe0f5c67377e60a820e5ca`,
and its byte SHA-256 is
`968b99db26b1a4dd93e61117220ddcb64abea15ef5d48134eae976deb3422d40`.

## Evidence boundary

This diagnostic was deliberately claim-ineligible. It cannot be pooled with
or revise the supported adapter-1.5 expansion-target claim of +2.66
[+2.00, +3.32]. The result shows that adapter 1.6 enforces its declared
settlement-runway invariant without a detected population-average score
regression; it does not establish score equivalence, score improvement,
margin improvement, or a win-rate effect.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-expansion-deadline-recovery-diagnostic-v1 \
  --backend engine-live \
  --cohort expansion_deadline_recovery_diagnostic_v1 \
  --workers 3 \
  --server-ports 6001,6002,6003 \
  --no-resume
```

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-expansion-deadline-recovery-diagnostic-v1/games/impact_pair/expansion_deadline_recovery_diagnostic_v1/treatment \
  --maximum-files 40 \
  --relative-to artifacts/freeciv/pf-expansion-deadline-recovery-diagnostic-v1 \
  --output artifacts/freeciv/pf-expansion-deadline-recovery-diagnostic-v1/pressure-replay-40.json
```

Machine-readable evidence is in
[`pf-expansion-deadline-recovery-diagnostic-v1.json`](pf-expansion-deadline-recovery-diagnostic-v1.json).
