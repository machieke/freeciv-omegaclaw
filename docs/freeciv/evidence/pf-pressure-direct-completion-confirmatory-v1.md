# PF-PLN candidate-scoped direct-completion confirmation v1

Status: complete; predeclared score claim not supported

The claim-eligible `pressure_direct_completion_confirmatory_v1` cohort
completed all 100 predeclared paired seeds (200 engine arms) at turn 60.
There were zero infrastructure failures, exact 50/50 arm-order balance,
matched initial states, passing safety gates, and one clean source identity at
commit `a709921`.

Mean score was 116.54 for baseline and 116.57 for treatment. The paired score
delta was +0.03 with a 95% paired-bootstrap interval of [-0.25, 0.31]. The
exact paired sign-flip p-value was 0.8912 across 34 nonzero pairs. The
predeclared score superiority claim failed and no win/lead endpoint was
declared.

The result does not replicate the preceding claim-ineligible pilot's +0.475
point estimate. The confirmatory interval excludes the predeclared +0.5 point
effect and is also below the achieved 0.403-point variance-based detectable
delta. The correct claim is therefore: candidate-scoped direct-completion
semantics passed correctness and safety validation but did not demonstrate a
material score improvement at turn 60.

## Validation and replay acceptance

All 200 event files pass the v1 schema. Exact replay covered all 100 treatment
traces and 6,726 pressure decisions. Every selected operation and schedule
hash reproduced with zero integrity failures. Pressure changed 384 decisions
(5.71%) from grounded utility ordering.

Category priority, cross-goal opportunity cost, and scalar scheduling cost
were invariant within every category in every decision. There were zero
invariance violations.

Candidate-scoped optimism applied in 83 decisions: 31 city-founding contexts
and 53 exact known-hut contexts, with both categories present in one decision.
The floored category was selected in 76 decisions. Five non-selections were
lexicographic safety preemptions; the remaining two selected other grounded
work. Preparatory routes were not marked as direct completions.

The safety firewall was active in 369 decisions and every one selected a
survival category. Survival grounding comprised 5,563 distant-safe contexts,
1,129 proximate-threat contexts, and 34 grounded production-defense deficits.
Engine rejection remained zero in both arms.

The treatment emitted 7,525 idempotent conductance updates: 5,433
effect-without-relief decays, 1,043 direct goal-relief credits, 818 downstream
credits, and 231 no-progress updates.

## Secondary diagnostics

Cities founded and settlement completions each changed by +0.03 with interval
[-0.02, 0.08]. Settlement attempts changed by -0.13 with interval
[-0.41, 0.05]. Production changes changed by -0.03 with interval
[-0.17, 0.11]. Explored positions changed by +0.12 with interval
[-1.57, 1.84], meaningful action rate changed by +0.0135 actions/turn with
interval [-0.0442, 0.0772], and loop latency changed by +7.3 ms with interval
[-51.7, 58.9].

The paired score SD was 1.4387. The 100-pair cohort achieved 93.5% planning
power for its 0.5-point target and a 0.403-point detectable delta. Failure to
confirm is not attributable to the planned sample being smaller than required.

No further cohort should repeat this same pressure-only hypothesis. Future
score work requires a materially different, predeclared gameplay mechanism;
the completed pilot and confirmation must not be pooled or selectively
reinterpreted.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-direct-completion-confirmatory-v1 \
  --backend engine-live \
  --cohort pressure_direct_completion_confirmatory_v1 \
  --workers 3 \
  --server-ports 6001,6002,6003
```

```bash
PYTHONPATH=src:benchmarks python3 \
  scripts/freeciv/replay_pressure_decisions.py \
  artifacts/freeciv/pf-pressure-direct-completion-confirmatory-v1/games/impact_pair/pressure_direct_completion_confirmatory_v1/treatment \
  --maximum-files 100 \
  --relative-to artifacts/freeciv/pf-pressure-direct-completion-confirmatory-v1 \
  --output artifacts/freeciv/pf-pressure-direct-completion-confirmatory-v1/pressure-replay-100.json
```

Machine-readable results and artifact identities are recorded in
[`pf-pressure-direct-completion-confirmatory-v1.json`](pf-pressure-direct-completion-confirmatory-v1.json).
