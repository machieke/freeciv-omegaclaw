# Unified PF-PLN terminal-action guard diagnostic v2

Status: complete; mechanism corrected; no pilot justified; claim-ineligible

The fresh `unified_flow_advisory_terminal_guard_diagnostic_v2` cohort
completed all ten predeclared pairs and 20 engine arms at turn 60 from clean
commit `a8f26fbd8e7d0349d52c4afe3405be762b22a086`. The run used three
controller workers, configuration hash
`a50e15df16075ff15316deba4c179a0030fdfe8b941c065ad6ff13dd39de51b5`,
and implementation hash
`8c2d318789eafa01b9614d4f4dadbd6d4366c3d8dc31ecfa2eef0ec870745435`.

The seeds were derived from the untouched, disjoint `5000000..5099999`
namespace. This diagnostic tests the correction motivated by the failed v1
confirmation. It is not claim-eligible and cannot be pooled into a score,
gameplay, or win-rate claim.

## Intervention

The v1 confirmation showed that uncalibrated flow overlap could exclude an
immediately legal terminal action and replace city founding with more
movement. V2 adds an explicit advisory policy:

```text
protect_uncalibrated_terminal_actions: true
```

When flow and scalar-v2 disagree and either proposal consumes its actor as a
terminal action, an uncalibrated advisory must abstain. The exact scalar-v2
decision is returned through the normal packet-safe fallback. Calibrated
controllers remain eligible for the existing advisory and limited-live gates;
reversible disagreements remain available for experimental evaluation.

## Mechanism result

The guard fired five times across four treatment seeds. On every guarded
turn, the effective action stream retained scalar-v2's `unit_build_city`:

- seed `5031457`, turn 4;
- seed `5077101`, turns 4 and 13;
- seed `5002371`, turn 4; and
- seed `5004987`, turn 11.

No terminal displacement was accepted. Settlement completions were exactly
equal between arms: `1.20` per game in baseline and treatment, paired delta
`0.00 [0.00, 0.00]`.

Treatment recorded 486 accepted flow selections. Only four accepted
flow-versus-scalar disagreements remained:

- three selected a different movement; and
- one selected different city production.

Those disagreements changed three paired action streams. Two affected pairs
tied on score; one lost one citizen point.

## Diagnostic outcomes

Treatment-minus-baseline player score was `-0.10 [-0.30, 0.00]`: no pair
improved, one declined by one point, and nine tied. The exact paired sign-flip
p-value was `1.0`.

| Fixed-horizon metric | Paired delta |
|---|---:|
| Player score | -0.10 [-0.30, 0.00] |
| Citizen score | -0.10 [-0.30, 0.00] |
| Technology score | 0.00 [0.00, 0.00] |
| Settlement completions | 0.00 [0.00, 0.00] |
| Technologies acquired | 0.00 [0.00, 0.00] |
| Opponent score | +0.10 [0.00, +0.30] |
| Score margin | -0.20 [-0.60, 0.00] |

The cohort is deliberately too small for a score claim, but it answers the
mechanism question: the known terminal-delay defect is closed, while the
remaining reversible advisory behavior provides no directional reason to
spend on another pilot.

## Safety, validity, and cost

- All ten pairs and 20 arms completed with zero infrastructure failures.
- Source freeze passed with one clean commit and one implementation hash.
- Initial-state fidelity passed with zero mismatches.
- Engine rejected-action and model-safe-fallback rates were zero in both
  arms.
- Every turn met the 30-second full-loop gate.
- All 20 event streams passed independent schema and causal validation.

Three-worker controller-inclusive means were:

| Metric | Baseline | Treatment | Paired delta |
|---|---:|---:|---:|
| Impact planning | 42.59 ms/turn | 270.98 ms/turn | +228.40 ms |
| Control decision | 21.04 ms/decision | 128.39 ms/decision | +107.36 ms |
| Decision-event emission | 20.62 ms/decision | 59.13 ms/decision | +38.52 ms |
| Full turn loop | 358.92 ms/turn | 624.92 ms/turn | +266.00 ms |

## Observability finding

The run exposed one telemetry limitation: a guarded fallback recorded the
gate reason but discarded the nested flow proposal, so proposed and effective
candidate identities could not be reconstructed from that event alone.
The post-diagnostic correction retains the target artifact only for genuine
disagreements and emits:

- flow-proposed candidate key;
- effective candidate key;
- `shadow-only`, `guarded-fallback`, or accepted disposition;
- fallback and advisory candidate keys; and
- terminal-action flags.

This is an observability-only hardening after the recorded cohort. It requires
a same-seed engineering replay before relying on the new fields, and it does
not alter this diagnostic's outcome.

## Decision

The v2 correction closes the identified correctness defect, but it does not
earn incremental gameplay value over scalar-v2. Per the implementation plan's
stop/simplification rule:

- do not start a v2 pilot or confirmation;
- keep `scalar_v2` as the supported live controller;
- keep unified flow restricted to offline, replay, shadow, and explicitly
  experimental advisory use;
- retain eligible-paired-evidence and transition-calibration requirements for
  `unified_flow_live`; and
- do not begin native flow optimization.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3.8 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/unified-flow-advisory-terminal-guard-diagnostic-v2-engine \
  --backend engine-live \
  --cohort unified_flow_advisory_terminal_guard_diagnostic_v2 \
  --workers 3 \
  --server-ports 6001,6003,6004 \
  --no-resume
```
