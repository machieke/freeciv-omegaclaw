# Unified PF-PLN flow advisory confirmation v1

Status: complete; preregistered score endpoint not met; no score, gameplay, or
win-rate claim

The untouched `unified_flow_advisory_confirmatory_v1` cohort completed all
100 predeclared pairs and 200 engine arms at turn 60 from clean commit
`f0c4299e9646f011f2b4915c3a268af74f509338`. The run used three controller
workers, configuration hash
`4420a536d4cedb84dc0bb2db627959e15e62ab668bed14e9127d10d4b182d54c`,
and implementation hash
`cb1601b736abd8023fddf7d1a4245e1ab729f2a52423523b5e9f9e9170ca9eca`.

This was the fresh, seed-disjoint, engine-backed confirmation frozen after
the claim-ineligible 40-pair pilot. It had no interim inspection, adaptive
stopping, seed replacement, parameter change, or pooling with the pilot.

## Preregistered result

Treatment-minus-baseline player score was `+0.05`, with paired-bootstrap 95%
interval `[-0.33, +0.43]`. The exact two-sided paired sign-flip p-value was
`0.839085`. Twenty-two pairs improved, 21 declined, and 57 tied. The
observed paired SD was `1.9456`.

The predeclared superiority gates both failed:

- the interval included zero; and
- the exact randomization test did not reject the null.

The separately reported two-point meaningful-effect checks also failed:
the lower interval did not exceed `+2.0`, and the exact one-sided
meaningful-margin p-value was `1.0`.

The cohort therefore has evaluator status `no_claim`. It does not confirm
the pilot's `+0.675` estimate and supports no positive score, gameplay,
score-lead, or win-rate statement.

## Outcome decomposition

| Fixed-horizon metric | Baseline | Treatment | Paired delta |
|---|---:|---:|---:|
| Player score | 116.72 | 116.77 | +0.05 [-0.33, +0.43] |
| Citizen score | 12.90 | 12.91 | +0.01 [-0.32, +0.33] |
| Technology score | 102.30 | 102.36 | +0.06 [-0.06, +0.20] |
| Residual score | 1.52 | 1.50 | -0.02 [-0.16, +0.11] |
| Technologies acquired | 0.15 | 0.19 | +0.04 [-0.02, +0.11] |
| Settlement completions | 1.22 | 1.18 | -0.04 [-0.10, +0.01] |
| Opponent score | 129.38 | 128.87 | -0.51 [-1.83, +0.79] |
| Score margin | -12.66 | -12.10 | +0.56 [-0.88, +1.99] |

Score deltas ranged from `-6` to `+7`: 43 pairs were nonzero and 57 were
zero. The wider observed SD implies that 119 pairs, rather than the
predeclared 100, would have been required for 80% paired-normal planning
power at a `0.5`-point effect. This does not rescue or invalidate the
completed test: the observed estimate is only `+0.05`, and collecting the
19 variance-adjustment pairs after inspecting the result would not be a
valid continuation of the frozen confirmatory cohort.

## Mechanism and failure analysis

Treatment emitted 4,468 healthy, accepted flow selections. It directly
disagreed with scalar-v2 205 times across 64 seeds:

- 165 disagreements replaced scalar city founding with founder movement;
- 32 selected a different movement;
- six selected different production;
- one replaced production with city-governor control; and
- one selected a different fortification operation.

All nonzero score deltas occurred in the 64 direct-disagreement seeds. Their
mean score delta was only `+0.078`: 22 improved, 21 declined, and 21 tied.
The 36 seeds without a direct disagreement were exactly score-equivalent.
This localizes both benefit and harm to the advisory choice rather than
unpaired initial state or unrelated runtime behavior.

The dominant disagreement exposes a semantic mismatch in the current
candidate-region rule. Flow overlap first selects a per-goal region at a
fixed 50% relative-overlap threshold; typed PF priority only ranks operations
inside that region. In all 165 city-founding disagreements:

- scalar-v2 selected an immediately legal `unit_build_city`;
- the founding operation was excluded from the flow region;
- founding overlap was 12.4% to 49.4% of the expansion goal's maximum
  overlap, with median 36.0%;
- the advisory selected `unit_move` to another tile already marked
  `settlement_site_eligible`; and
- the substitution delayed a terminal, score-bearing completion in favor of
  further location search.

All 12,258 recorded source-sink projections were numerically healthy. The
problem is therefore not solver convergence or conservation. It is an
uncalibrated semantic preference: intermediate corridor overlap can exclude
a legal terminal completion. The paired settlement-completion delta
`-0.04 [-0.10, +0.01]` is consistent with that diagnosis, while the
balanced 22-versus-21 score signs show that the extra movement is not a
reliable improvement.

The advisory failed closed to scalar-v2 741 times:

- 413 for unhealthy/low-confidence control;
- 319 for unhealthy, incomplete packet, and low confidence; and
- nine additionally because fallback admissibility disagreed.

These abstentions were visible and packet-safe. The accepted decisions still
reported `calibrated: false`, so they cannot satisfy limited-live transition
calibration even apart from the failed score endpoint.

## Safety, validity, and cost

- All 100 pairs and 200 arms completed with zero infrastructure failures.
- Source freeze passed with one clean commit and one implementation hash.
- Initial-state fidelity passed with zero mismatches.
- Engine rejected-action and model-safe-fallback rates were zero in both
  arms.
- Every turn met the 30-second full-loop gate.
- All 200 event streams passed independent schema and causal validation.
- Replay hardening had already produced exact same-seed action and flow
  summaries before the cohort was frozen.

Three-worker controller-inclusive means were:

| Metric | Baseline | Treatment | Paired delta |
|---|---:|---:|---:|
| Impact planning | 35.73 ms/turn | 255.48 ms/turn | +219.75 ms |
| Control decision | 19.37 ms/decision | 132.01 ms/decision | +112.64 ms |
| Decision-event emission | 17.35 ms/decision | 58.55 ms/decision | +41.20 ms |
| Full turn loop | 313.50 ms/turn | 605.06 ms/turn | +291.57 ms |

The Python reference remains inside the absolute operational budget, but it
adds substantial controller-inclusive cost without a confirmed gameplay
benefit.

## Gate decision

The live release gate is stopped for `unified_flow_advisory` v1:

- the fresh paired primary endpoint was not met;
- transition artifacts remain explicitly uncalibrated; and
- the controller is slower than the strong scalar-v2 fallback without a
  confirmed score benefit.

Following the implementation plan's scientific stop/simplification rule,
`scalar_v2` remains the supported live controller. Unified flow remains
available for offline, replay, shadow, and explicitly experimental advisory
work behind its existing flags. `unified_flow_live` must continue to fail
closed without eligible paired evidence and calibrated transitions. Native
flow acceleration is not justified by this result.

A future algorithm version must be treated as a new intervention. At
minimum, it must prevent uncalibrated transit overlap from displacing an
immediately legal terminal completion, pass fresh diagnostic and pilot
cohorts, freeze a new seed-disjoint confirmation, and repeat exact replay,
schema, safety, overhead, and endpoint checks. These data cannot be reused
as that confirmation.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3.8 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/unified-flow-advisory-confirmatory-v1-engine \
  --backend engine-live \
  --cohort unified_flow_advisory_confirmatory_v1 \
  --workers 3 \
  --server-ports 6001,6003,6004 \
  --no-resume
```
