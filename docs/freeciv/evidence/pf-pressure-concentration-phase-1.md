# PF-PLN Phase 1: goal-regression focus acceptance

Date: 2026-07-25 UTC

Implementation commit:
`84ccff5725eec47d863cd591d18da3b991bd4488`

Evidence artifact:
[pf-pressure-concentration.json](pf-pressure-concentration.json), benchmark
hash
`5f16234a31263be5db70368d9fed2b865cb070022248fc45854208e022999728`.

## Canonical exit gate

The canonical Phase 1 exit requires at least five times fewer rule
instantiations than plain backward chaining on a graph with one valid route and
many irrelevant subgraphs, without changing decision quality.

Command:

```bash
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/benchmark_pressure.py \
  --output docs/freeciv/evidence/pf-pressure-concentration.json
```

The deterministic depth-four graph contains one valid route and 256
low-conductance decoy routes. Plain exhaustive backward expansion instantiates
1,028 premise edges. The bounded expected-transport beam instantiates 128,
an `8.03125x` reduction (`87.5486%` fewer instantiations).

Decision quality is unchanged:

- the valid route is retained;
- relevant non-root pressure concentration is `99.5406%`;
- the pressure and exhaustive paths identify the same valid decision route;
- input truth is byte-unchanged; and
- a second execution produces the identical artifact.

The runner exits nonzero if the reduction falls below `5x`, equal decision
quality fails, or truth changes. The focused regression compares the generated
artifact byte-for-byte with the checked JSON.

The separate authoritative snapshot replay contains the complete advertised
legal set (134 actions and 35 grounded candidates in the actionable capture).
Later paired engine cohorts add exact replay over thousands of real pressure
decisions, including 6,726 treatment decisions in the 100-pair confirmation.
Those engine results establish integration and correctness but are not needed
to reinterpret the synthetic Phase 1 focus gate as a score claim.

## Verification

```bash
pytest -q Autotests/test_freeciv_pressure.py \
  -k pressure_concentrates_and_bounds_irrelevant_route_expansion
# 1 passed
```

Source identities:

- benchmark module SHA-256:
  `311d30051612690693896b28fbc948d2d1f5ba9bfd7711a381e2ad1b6f0a305d`;
- runner SHA-256:
  `9c9cc600ddb24148133f05a3b1cf794c8f4032630beb24b392bf503644b3f53b`;
- graph hash:
  `b9baa4921479ef0a3b6ce86d3c8bb343a90550eb9cb9affce51a1f8a53bd8da9`;
- pressure result hash:
  `a8c924edbcfb12d4090e1fe217f126a880ad4eff5a48de0a9f1a3d3cbd9ead64`.
