# PF-PLN Phase 4 conductance-learning acceptance

The branch-abandonment exit criterion now has a standalone deterministic
ablation:

```bash
python3 scripts/freeciv/run_pf_conductance_benchmark.py
```

With the Phase 1 fixed prior, the higher-utility infeasible economy route
remains selected for all 12 attempts. With identical candidates and grounded
no-progress feedback, learned conductance abandons that route after five
attempts and selects the military-score alternative. The learned state contains
only route feedback and conductance; it has no truth or belief channel.

The checked machine-readable result is
[`pf-conductance-learning-phase-4.json`](pf-conductance-learning-phase-4.json).
Its structural artifact hash is
`51d1d193c7b9ca84dab03a2373bb0eda7250d600e1dca289f96e6b2364ee4cd7`.
