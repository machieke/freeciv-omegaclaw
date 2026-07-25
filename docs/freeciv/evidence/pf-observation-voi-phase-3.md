# PF-PLN Phase 3 observation and simulation pressure acceptance

Status: complete

Implementation commit: `d5428ac`

Phase 3 implements exact one-step expected information gain for bounded
discrete hypothesis sets. Each test supplies a complete conditional outcome
table. The evaluator enumerates every outcome, calculates posterior entropy,
and ranks the resulting expected entropy reduction. Information value is then
combined with typed observation pressure and vector cost by the shared
scheduler, so observation and action operations remain directly comparable.

An active Phase 2 conflict can be converted into a goal whose desired
conflict strength is zero. Its candidate observations must target that conflict
atom. Scheduling retains the conflict truth unchanged and records the
goal-conditioned observation policy in the operation payload.

Every simulated test and observation carries an immutable simulator ID,
version, model hash, exactness flag, and confidence cap. Inexact simulator
evidence is rejected if it exceeds either the model's declared cap or the
configured global cap of 0.60. A `source=simulator` event without model
provenance fails stream validation.

Goal-selected evidence records its sampling policy. Known propensity scales
its confidence conservatively. Unknown propensity uses the declared 0.50
discount, widening uncertainty instead of allowing selection pressure to
silently increase certainty.

## Exhaustive and random-selection benchmark

The deterministic FreeCiv-style abduction benchmark evaluated two hypotheses
(`attack` and `transit`) and four possible tests per case over 256 prior
configurations:

- 1,024 tests evaluated;
- 256 of 256 complete rankings matched an independent exhaustive enumerator;
- zero ranking errors;
- the destination-scout test was selected in all 256 fixtures;
- selected mean information gain was 0.5623866374 bits;
- uniform-random expected mean information gain was 0.1974573664 bits;
- the absolute margin was +0.3649292710 bits;
- relative lift over uniform random was 184.814%.

The benchmark structural artifact hash is
`4c3a36497168c5fb3ec10d121bc1e0bae38b03525233d04cec1e8806098b33f2`.
The rendered artifact SHA-256 is
`c38d7f63442252dc7e6a3a9745b0cc97879e155a9be907ee5d780a046ab0b864`.
Machine-readable evidence is in
[`pf-observation-voi-phase-3.json`](pf-observation-voi-phase-3.json).

## Regression acceptance

Validation completed with:

- 292 passing Python FreeCiv tests;
- 20 passing observability unit tests;
- 11 valid UI fixtures containing 140 events;
- zero UI boundary violations;
- passing TypeScript typecheck and production build;
- current generated event types and a clean diff check.

## Reproduction

```bash
PYTHONPATH=src python3 scripts/freeciv/run_pf_voi_benchmark.py \
  --out artifacts/freeciv/pf-voi-phase-3.json
```

```bash
pytest -q Autotests/test_freeciv_*.py
```

```bash
cd apps/freeciv-observability
npm test
```

This is observation-policy correctness evidence, not a gameplay score or
win-rate claim. The approximation is deliberately myopic; multi-step
information plans remain an explicit research limitation.
