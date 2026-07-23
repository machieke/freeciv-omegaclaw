# PF-PLN pressure ablation pilot v1

Status: complete, diagnostic pilot only

The predeclared `pressure_ablation_pilot_v1` cohort completed all 40 paired
seeds (80 engine arms) at turn 60. There were no infrastructure failures, the
20/20 arm-order balance was exact, all initial paired states matched, every
safety gate passed, and all runs used clean source commit
`e790316817441dc2c0ca17a4d843ce09ae0d8d58`.

The treatment changed mean score by -0.175 points with a 95% paired-bootstrap
interval of [-1.05, 0.825]. The exact paired sign-flip p-value was 0.789. The
fixed-horizon lead/win rate was 17.5% for baseline and 22.5% for treatment, a
paired difference of 5 percentage points with interval [-5, 15] and exact
McNemar p=0.625. These results do not support a positive score or win-rate
claim, and the cohort is deliberately claim-ineligible.

The paired score standard deviation was 3.0875. Under the predeclared
normal-approximation design, a fresh cohort of 30 pairs would provide at least
80% power for a two-point score effect. A confirmatory cohort is not frozen
yet: the neutral pilot exposed semantic issues that must be corrected and
re-piloted first.

## Diagnostic finding

Exact read-only replay covered all 40 treatment traces and 3,061 pressure
decisions. All schedule hashes and selected operations reproduced, with zero
integrity failures. Pressure changed 566 decisions (18.49%). In 230 changed
decisions, canonical policy had an immediately legal city-founding action;
pressure selected another expansion move in 139 of those cases.

This identifies two coupled problems in the v1 adapter:

1. An untried category starts with conductance 0.5, while frequently successful
   movement categories approach 1.0. Local movement effects can therefore
   displace a rarer, higher-value direct goal-completion action.
2. Survival, score, and exploration truth strengths are constant rather than
   derived from the current authoritative snapshot, leaving cross-goal pressure
   active after its grounded deficit is resolved.

The next implementation must use an optimistic prior for server-advertised
untried routes and snapshot-derived goal strengths. It requires a fresh,
seed-disjoint pilot; v1 cannot be pooled with the revised policy.

## Reproduction

The engine cohort used:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-ablation-pilot-v1 \
  --backend engine-live \
  --cohort pressure_ablation_pilot_v1 \
  --workers 3 \
  --server-ports 6001,6002,6003
```

The exact treatment replay used:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-pressure-ablation-pilot-v1/games/impact_pair/pressure_ablation_pilot_v1/treatment \
  --maximum-files 40 \
  --output artifacts/freeciv/pf-pressure-ablation-pilot-v1/pressure-replay.json
```

Machine-readable results, dependency versions, source identity, configuration
identity, and artifact hashes are recorded in
[`pf-pressure-ablation-pilot-v1.json`](pf-pressure-ablation-pilot-v1.json).
