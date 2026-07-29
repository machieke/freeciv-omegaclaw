# Unified PF-PLN flow advisory pilot v1

Status: complete, pilot only; confirmation justified

The untouched `unified_flow_advisory_pilot_v1` cohort completed all 40
predeclared pairs and 80 engine arms at turn 60 from clean commit
`6fd290a9ce28835d23f75f17d59eeae48d9a489f`. The run used three controller
workers, configuration hash
`92628a53b3f21414c9585460b5d6f455378590b425c16b9db2bff63e8f5e9b57`,
and implementation hash
`cb1601b736abd8023fddf7d1a4245e1ab729f2a52423523b5e9f9e9170ca9eca`.

This cohort is preregistered but claim-ineligible. It estimates effect
direction, paired variance, controller mechanism, safety, and overhead. It
cannot support or be pooled into a score, gameplay, or win-rate claim.

## Fixed-horizon outcomes

Treatment-minus-baseline player score was `+0.675`, with paired-bootstrap
95% interval `[+0.20, +1.20]`. The exact two-sided paired sign-flip p-value
was `0.0143723`. Fifteen pairs improved, seven declined, and 18 tied; the
observed paired SD was `1.6391`.

The score movement decomposed primarily into:

- citizen score delta `+0.50 [+0.075, +1.025]`;
- technology score delta `+0.15 [0.00, +0.35]`;
- settlement completions `+0.025 [-0.05, +0.10]`; and
- technologies acquired `+0.075 [0.00, +0.175]`.

Opponent score changed by `-0.45 [-2.275, +1.55]`, and score margin changed
by `+1.125 [-0.95, +3.20]`.

Fixed-horizon score-lead rate moved in the opposite direction:
`-0.05 [-0.125, 0.00]`. There were four both-lead pairs, 34 both-non-lead
pairs, two baseline-only leads, and no treatment-only leads; exact McNemar
`p=0.5`. In both discordant pairs treatment raised its own score, but the
opponent score rose more. The pilot therefore supports a fresh score
confirmation only, not a lead-rate or win-rate confirmation.

## Mechanism

Treatment emitted 1,925 healthy, accepted flow selections. It directly
disagreed with scalar-v2 86 times across 27 seeds:

- 85 disagreements selected a movement action and one selected production;
- the scalar comparator in those cases preferred city founding 73 times,
  movement 12 times, and production once;
- 28 pairs changed their turn-level action stream, spanning 1,013 changed
  turns after game-state propagation;
- all 15 positive and all seven negative score deltas occurred in the 27
  direct-disagreement seeds; and
- the 13 seeds without direct disagreement all had zero score delta.

The mean score delta was `+1.00` among direct-disagreement seeds and `0.00`
without direct disagreement. This is a mechanism association inside a pilot,
not a separately randomized subgroup claim.

One zero-delta seed changed its action stream without a recorded direct
selection disagreement. The first difference was an additional same-turn
scalar action in baseline after identical earlier actions and state, while
treatment incurred controller-inclusive compute. It had no score effect, but
it demonstrates why full-loop cost must remain part of the treatment rather
than being removed from analysis.

The advisory failed closed to scalar-v2 335 times:

- 180 for unhealthy/low-confidence control;
- 148 for unhealthy, incomplete packet, and low confidence; and
- seven additionally because fallback admissibility disagreed.

These abstentions were visible, packet-safe, and did not count as flow
disagreements.

## Safety, validity, and cost

- All 40 pairs and 80 arms completed with zero infrastructure failures.
- Initial-state fidelity passed with zero mismatches.
- Engine rejected-action and model-fallback rates were zero in both arms.
- Every turn met the 30-second full-loop gate.
- Source freeze passed with one clean commit and one implementation hash.
- All 80 event streams passed schema and causal validation.

Three-worker controller-inclusive means were:

| Metric | Baseline | Treatment | Paired delta |
|---|---:|---:|---:|
| Impact planning | 42.98 ms/turn | 280.07 ms/turn | +237.09 ms |
| Control decision | 21.89 ms/decision | 139.28 ms/decision | +117.39 ms |
| Decision-event emission | 22.44 ms/decision | 61.94 ms/decision | +39.50 ms |
| Full turn loop | 364.67 ms/turn | 652.74 ms/turn | +288.06 ms |

The pilot measures the deployed Python reference under concurrent engine
workers. It includes factorization, probes, projection, transport, packets,
revalidation, logging, and CPU contention. The overhead is substantial but
remains below the declared operational ceiling.

## Frozen confirmation design

No controller threshold or algorithm parameter is changed after this pilot.
The seed-disjoint `unified_flow_advisory_confirmatory_v1` cohort compares the
same isolated scalar-v2 and unified-flow advisory policies at turn 60.

The pilot paired SD `1.6391` is rounded upward to a maximum planning SD of
`1.75`. A two-sided alpha-0.05 design with 80% target power and
`0.5`-point minimum detectable score delta requires 97 pairs under the
predeclared paired-normal calculation. The confirmation freezes 100 pairs
from namespace `pf-pln-unified-flow-advisory-confirmatory-v1` in the disjoint
range `4900000..4999999`. The three extra pairs are design margin; there is
no interim inspection, adaptive stopping, seed replacement, or pooling.

The confirmation endpoint is player score only. It can support a positive
score claim if and only if every source, completeness, safety, interval, and
exact-randomization gate passes. It is not designed to claim a two-point
meaningful effect, a lead-rate improvement, or an engine-reported victory.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3.8 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/unified-flow-advisory-pilot-v1-engine \
  --backend engine-live \
  --cohort unified_flow_advisory_pilot_v1 \
  --workers 3 \
  --server-ports 6001,6003,6004 \
  --no-resume
```
