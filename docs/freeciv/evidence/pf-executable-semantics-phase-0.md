# PF-PLN Phase 0 executable-semantics acceptance

The deterministic capital-defense graph now has a standalone release replay:

```bash
python3 scripts/freeciv/run_pf_semantics_benchmark.py
```

The run propagates typed pressure from the survival goal through the defense
routes, offers observation and action operations to the scheduler, and selects
`observe-treasury`. Repeating both propagation and scheduling is byte-stable.
The survival dependency is 48.0, action pressure reaches `buy-archer`,
observation pressure reaches `treasury`, and the graph's truth records are
unchanged before and after the reverse pass.

The checked machine-readable result is
[`pf-executable-semantics-phase-0.json`](pf-executable-semantics-phase-0.json).
Its structural artifact hash is
`d1b6bb9c91626be48dff329ce387d89e3c71968d04e9b5ff1c6317e187c4da05`.
