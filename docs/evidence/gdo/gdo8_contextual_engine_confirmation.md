# GDO-8 contextual engine confirmation

Status: frozen prediction gate passed; gameplay claim not established

## Design

Two predeclared 60-turn engine cohorts were run from clean commit `8a05a23`:

| Cohort | Pairs | Arms | Seed range | Purpose |
|---|---:|---:|---|---|
| `contextual_transition_training_diagnostic_v1` | 30 | 60 | 5,600,000–5,699,999 | mutable v2 outcome collection |
| `contextual_transition_holdout_diagnostic_v1` | 30 | 60 | 5,700,000–5,799,999 | disjoint frozen evaluation |

The seed derivations are checked into `profile/freeciv_harness.yaml`. Both
cohorts are claim-ineligible diagnostics, require clean source, and use three
controller workers. The only paired-arm difference is whether the contextual
v2 collector is enabled. Authority, bridge, flow, and path persistence remain
disabled.

All 120 arms completed with zero gameplay failure, infrastructure failure, or
rejected engine action. The fitter independently requires every contributing
trace to be complete, clean-source, and claim-ineligible before reading an
outcome.

## Frozen result

The training traces produced 1,587 contextual outcomes. The resulting
read-only model has 38 supported keys among 43 observed training keys. No
duplicate or unknown outcome was used.

The untouched holdout produced 1,831 eligible outcomes:

| Gate metric | Result | Requirement |
|---|---:|---:|
| Coverage | 100% | at least 80% |
| Raw Brier | 0.267491 | comparator |
| Contextual Brier | 0.041237 | lower is better |
| Mean Brier improvement | 0.226254 | positive |
| 95% bootstrap interval | [0.210036, 0.242391] | lower bound above zero |
| High-volume context regression | none | at most 0.02 |
| Evaluation updates | zero | required |

The approval result is `authority_approved: true`. Its report hash is
`a983c1448ceed76e30a4100253579a3ce47cff703f68a35b814ca0a308a65e84`.
The aggregate engine-audit hash is
`860a182aed67a67a1a06246b5dd04dc74cf0cded2253b0aaa12e075a1acc9d4c`.

## Reproduction

The two engine commands use the same environment:

```sh
FREECIV_PROXY_WS=ws://127.0.0.1:8002/llmsocket/8002 \
FREECIV_API_TOKEN=test-token-fc3d-001 \
FREECIV_RULESET_ROOT=/path/to/freeciv/data \
FREECIV_SERVER_CONTAINER=fciv-net \
OLLAMA_OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/gdo8-contextual-training-v1 \
  --config profile/freeciv_harness.yaml \
  --backend engine-live --workers 3 \
  --server-ports 6001,6003,6004 \
  --cohort contextual_transition_training_diagnostic_v1
```

Replace the output and cohort with
`gdo8-contextual-holdout-v1` and
`contextual_transition_holdout_diagnostic_v1` for holdout collection.

Fit and evaluate only after both cohorts complete:

```sh
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/fit_contextual_transition_value_model.py fit \
  --artifacts artifacts/freeciv/gdo8-contextual-training-v1 \
  --out docs/freeciv/evidence/gdo8-contextual-transition-training-v1-model.json \
  --identity gdo8-contextual-transition-training-v1 \
  --cohort contextual_transition_training_diagnostic_v1 \
  --report docs/freeciv/evidence/gdo8-contextual-transition-training-v1-report.json

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/fit_contextual_transition_value_model.py evaluate \
  --artifacts artifacts/freeciv/gdo8-contextual-holdout-v1 \
  --model docs/freeciv/evidence/gdo8-contextual-transition-training-v1-model.json \
  --out docs/freeciv/evidence/gdo8-contextual-transition-holdout-v1-approval.json \
  --identity gdo8-contextual-transition-training-v1 \
  --cohort contextual_transition_holdout_diagnostic_v1

python3 scripts/run_gdo_contextual_engine_audit.py
```

## Claim boundary

This establishes engine-backed calibration of factual selected-action
goal-relief prediction. The deterministic policy did not randomize alternative
actions, so the result is not an off-policy causal value estimate. Collection
arms ran without contextual authority and therefore do not establish score,
win-rate, or policy-ordering benefit.

## Fresh authority diagnostic

The approved model was then loaded read-only in a fresh, disjoint,
claim-ineligible 10-pair engine diagnostic. The authority path was requested,
fully supported, and active in all 514 treatment decisions, with no fallback,
rejected action, safety-gate failure, or infrastructure failure.

The readout changed action payloads in 4 of 10 pairs. It did not change player
score in any pair:

| Diagnostic delta | Estimate | Paired interval |
|---|---:|---:|
| player score | 0.00 | [0.00, 0.00] |
| win rate | 0.00 | [0.00, 0.00] |
| score margin | +0.10 | [0.00, +0.30] |
| Impact planning latency | +4.93 ms/turn | [-4.34, +14.84] |
| full-loop latency | +23.71 ms/turn | [-3.54, +59.20] |

This closes the runtime-load and complete-support diagnostic, but it does not
pass a gameplay-benefit gate. Contextual authority remains default-off and is
not recommended for general live use from this result. The canonical retained
summary is
`benchmarks/gdo/gdo8_contextual_authority_diagnostic.json`.
