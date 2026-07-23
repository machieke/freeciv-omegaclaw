# PF-PLN pressure ablation pilot v2

Status: complete, diagnostic pilot only

The predeclared `pressure_ablation_pilot_v2` cohort completed all 40 fresh
paired seeds (80 engine arms) at turn 60. There were no infrastructure
failures, the 20/20 arm-order balance was exact, all paired initial states
matched, every safety gate passed, and all runs used clean source commit
`c2ad56391ab20ebff9d2bcfda4eb3790edc52840`.

The treatment changed mean score by +0.075 points with a 95%
paired-bootstrap interval of [-0.125, 0.300]. The exact paired sign-flip
p-value was 0.654. The fixed-horizon lead/win rate was 7.5% for baseline and
10.0% for treatment, but only one pair was discordant (exact McNemar p=1).
These results do not support a meaningful score or win-rate claim, and the
cohort is deliberately claim-ineligible.

The paired score SD fell from 3.0875 in v1 to 0.6938 in v2. The correction
therefore removed the behavior instability that motivated v2, but it also made
clear that the present pressure policy is close to outcome-equivalent to
canonical ordering. The upper score-effect interval is 0.300 points, far below
the predeclared two-point meaningful effect. Freezing a confirmatory cohort
would not be justified.

## Semantic acceptance

Exact read-only replay covered all 40 treatment traces and 2,803 pressure
decisions. All schedule hashes and selected operations reproduced, with zero
integrity failures. Every decision recorded four nonempty goal-grounding
contexts and initial conductance 1.0.

Pressure changed 289 decisions (10.31%), down from 18.49% in the separate v1
pilot. Canonical ordering exposed an immediately legal city-founding action in
16 changed v2 decisions, down from 230 in v1. Because v1 and v2 use different
seeds, those reductions are implementation diagnostics rather than paired
effect estimates.

Three v2 decisions selected another `expansion_move` instead of city founding.
Each occurred after exactly four grounded no-progress outcomes for the
city-founding route. The recorded conductance was therefore lower because of
observed route failure, not because an untried route began below a frequently
exercised movement route. This satisfies the branch-abandonment acceptance
check for the observed engine cases.

## Outcome and next target

V2 reduced the action-rate overhead to +0.017 actions/turn with interval
[-0.031, 0.071], and loop-latency overhead to +7.7 ms with interval
[-67.0, 57.3]. Engine rejection remained zero in both arms.

The next improvement should not tune the same weights against this pilot.
Pressure credit and expected relief need to be tied to authoritative
downstream goal progress, rather than only to the immediate local effect of an
accepted action. That change requires offline replay acceptance and another
fresh, seed-disjoint pilot before any confirmatory design.

## Reproduction

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-ablation-pilot-v2 \
  --backend engine-live \
  --cohort pressure_ablation_pilot_v2 \
  --workers 3 \
  --server-ports 6001,6002,6003
```

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-pressure-ablation-pilot-v2/games/impact_pair/pressure_ablation_pilot_v2/treatment \
  --maximum-files 40 \
  --output artifacts/freeciv/pf-pressure-ablation-pilot-v2/pressure-replay.json
```

Machine-readable results, source identities, configuration identity, and
artifact hashes are recorded in
[`pf-pressure-ablation-pilot-v2.json`](pf-pressure-ablation-pilot-v2.json).
