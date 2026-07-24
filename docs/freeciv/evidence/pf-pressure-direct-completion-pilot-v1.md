# PF-PLN candidate-scoped direct-completion pilot v1

Status: complete, diagnostic pilot only

The predeclared `pressure_direct_completion_pilot_v1` cohort completed all 40
fresh paired seeds (80 engine arms) at turn 60. It had zero infrastructure
failures, exact 20/20 arm-order balance, matched initial states, passing
safety gates, and clean source commit `4fb7032`.

Mean score was 117.650 for baseline and 118.125 for treatment. The paired
score delta was +0.475 with a 95% paired-bootstrap interval of
[0.075, 0.975]. The exact paired sign-flip p-value was 0.046875 across nine
nonzero pairs.

This is the first fresh pressure cohort whose directional score interval does
not cross zero. It remains a claim-ineligible semantic pilot and is not
promoted, pooled, or reported as a confirmed score improvement. Its exact
test is supported by only nine nonzero pairs and the policy was selected after
earlier diagnostic cohorts.

Fixed-horizon lead rate changed by +2.5 percentage points with interval
[-5.0, 10.0]. Two treatment-only and one baseline-only lead produced exact
McNemar p=1.0. The pilot provides no win/lead-rate claim.

## Semantic acceptance

All 80 event files pass the v1 schema. Exact replay covered all 40 treatment
traces and 2,766 pressure decisions. Every selected operation and schedule
hash reproduced, with zero integrity failures. Pressure changed 181 decisions
(6.54%) from grounded utility ordering.

Candidate-scoped optimism applied in 44 decisions: 28 city-founding contexts
and 16 exact known-hut contexts. The floored category was selected in 42
decisions. The other two were correctly preempted by the lexicographic safety
firewall. Preparatory hut routes did not receive the floor.

The scheduler emitted safety-firewall rejections in 147 decisions. Every one
selected a survival category. Survival grounding comprised 2,055
distant-safe contexts, 698 proximate-threat contexts, and 13 grounded
production-defense deficits. Engine rejection remained zero in both arms.

The treatment emitted 3,120 idempotent v2 conductance updates: 2,174
effect-without-relief decays, 477 direct goal-relief credits, 361 downstream
credits, and 108 no-progress updates.

## Secondary outcomes and next design

Cities founded and settlement completions each changed by +0.025 with interval
[0.000, 0.075]. Settlement attempts changed by +0.175 with interval
[0.000, 0.500]. Production changes were unchanged. Explored positions changed
by +1.825 with interval [-0.100, 3.975], and meaningful action rate changed by
+0.0404 actions/turn with interval [-0.0279, 0.1121].

The paired score SD was 1.4498. A fresh score-only confirmatory cohort of 100
pairs is predeclared as
`pressure_direct_completion_confirmatory_v1`, with a 0.5-point minimum
detectable delta and maximum planning SD 1.5. It uses a disjoint
SHA-256-derived 3,100,000–3,299,999 seed range, clean-source enforcement,
three workers, and the same isolated pressure-off/pressure-on arms.

The confirmatory cohort must be committed before execution and must run
without pair limiting. Its result stands alone; the pilot is not pooled.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-direct-completion-pilot-v1 \
  --backend engine-live \
  --cohort pressure_direct_completion_pilot_v1 \
  --workers 3 \
  --server-ports 6001,6002,6003
```

```bash
PYTHONPATH=src:benchmarks python3 \
  scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-pressure-direct-completion-pilot-v1/games/impact_pair/pressure_direct_completion_pilot_v1/treatment \
  --maximum-files 40 \
  --relative-to artifacts/freeciv/pf-pressure-direct-completion-pilot-v1 \
  --output artifacts/freeciv/pf-pressure-direct-completion-pilot-v1/pressure-replay-40.json
```

Machine-readable results and artifact identities are recorded in
[`pf-pressure-direct-completion-pilot-v1.json`](pf-pressure-direct-completion-pilot-v1.json).
