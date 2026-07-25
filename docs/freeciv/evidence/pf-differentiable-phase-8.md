# PF-PLN Phase 8: delimited differentiable execution acceptance

Date: 2026-07-25 UTC

Implementation commit:
`e06fb88522f570f5c54ac9aab3479fdf7d1f04e3`

Evidence artifact:
[pf-differentiable-phase-8.json](pf-differentiable-phase-8.json),
structural hash
`00e17230c8660f881935114b9d693fb8a3502fbf99557165b3fd539d500dc1f5`.

## Delimited subset

Phase 8 adds a small reverse-mode scalar tensor engine rather than replacing
the production crisp or uncertain reasoners. The differentiable boundary is:

- strength and confidence components of `TensorTruth`;
- smooth product-AND and probabilistic-OR truth functions;
- reverse goal-pressure adjoints over those smooth computation paths; and
- bounded rule-parameter calibration by reverse-mode MSE.

The following remain explicitly outside automatic differentiation:

- symbolic prerequisite allocation;
- intervention and coalitional counterfactuals;
- threshold and other discontinuous actions;
- clone split/merge and lifecycle transitions;
- alternative-proof selection; and
- discrete operation scheduling.

Goal-pressure adjoints and parameter-learning gradients are separate result
types and entry points. Neither is accepted as truth evidence. A parameter
update is backtracked until calibration loss is non-increasing, remains inside
declared bounds, and emits a strict `rule_parameter_updated` event.

## AND and threshold characterization

Command:

```bash
python3 scripts/freeciv/run_pf_differentiable_benchmark.py \
  --out docs/freeciv/evidence/pf-differentiable-phase-8.json
```

On 1,444 premise-pressure comparisons across the active product-AND and
probabilistic-OR grids, reverse-mode adjoints match centered finite differences
with maximum absolute error `4.9703e-11`. Adjoint pressure is therefore
sufficient as a local leverage estimate on these smooth active paths.

At the dead product gate `AND(0, 0)`:

- conclusion pressure is `1.0`;
- pure adjoint pressure is `0.0` for both premises;
- symbolic requirement pressure is `0.5` for each premise;
- either individual intervention still has zero gain; and
- the joint intervention has counterfactual gain `1.0`.

This is the multiple-missing-prerequisite case where the adjoint is
insufficient and requirement plus coalitional counterfactual pressure are
necessary.

The resource threshold sweep marks every threshold row as outside the
differentiable subset. At value `4` for threshold `5`, requirement deficit is
`1.0` and the achievable one-unit intervention has counterfactual gain `1.0`;
a local derivative cannot represent that discontinuous crossing.

The bounded reliability parameter moves from `0.2` to `0.791766` over 20
updates and reduces calibration MSE from `0.173700` to `0.0000327`.

## Verification

```bash
pytest -q Autotests/test_freeciv_*.py
# 315 passed

cd apps/freeciv-observability
npm test -- --run
# 20 tests passed; fixtures, boundaries, typecheck, and production build passed

python3 scripts/freeciv/generate_event_types.py --check
# generated event types are current
```

The artifact characterizes operator sufficiency on the required host-side
benchmarks. It is not a gameplay score claim and does not enable learned truth
parameters in the live profile.
