# PF-PLN Phase 9: conflicting-goal scheduling acceptance

Date: 2026-07-25 UTC

Implementation commit:
`c4bd6ad6b884c9883b39701fceb2777900357c39`

Evidence artifact:
[pf-multi-goal-phase-9.json](pf-multi-goal-phase-9.json), structural hash
`c6e4e612a2fb55fc7f222417f3189e0775daf2f02ff9e2f34898e194f1c0b0f7`.

## Canonical exit gate

The canonical Phase 9 exit requires multi-goal scheduling to beat independent
per-goal scheduling on conflicting-goal scenarios while preserving an
explanation for each goal.

Command:

```bash
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_pf_multi_goal_benchmark.py \
  --out docs/freeciv/evidence/pf-multi-goal-phase-9.json
```

Each of the 64 deterministic scenarios has two goals sharing a one-operation
budget:

- each goal in isolation selects its own specialist;
- either specialist helps its own goal but harms the other;
- a balanced operation provides smaller isolated relief but higher combined
  relief; and
- the full scheduler receives both per-goal pressure/effect rows and applies
  cross-goal conflict penalties once.

The independent baseline resolves its incompatible recommendations by the
declared deterministic isolated-priority/operation-ID coordinator. The
multi-goal scheduler selects the balanced operation in 64/64 scenarios and
beats that baseline in combined normalized goal relief in 64/64. Mean joint
relief gain is `0.34`.

Every selected score contains separate `GoalEffect` explanations for `left`
and `right`, including incoming pressure, normalized relief, declared effect,
and weighted effect. Repeating the benchmark produces the identical artifact.

This operator benchmark complements the later engine-backed safety,
opportunity-cost, category-invariance, and exact-replay evidence. It is not a
new score or win-rate claim.

## Verification

```bash
pytest -q Autotests/test_freeciv_pressure_multi_goal.py
# 1 passed
```

Source identities:

- benchmark module SHA-256:
  `236bf2c707712eb7ea9d194f50c12937e2073c2cd19083b3590503d8cc4eea55`;
- runner SHA-256:
  `38a7e579790f8f9a9f7d48321f75efda6f3b0dbaf76ab0b2624ae17b5425ec65`;
- graph hash:
  `5e1a2d6184987b42ad2494187d6de1fed23fc71f18735cbd81bf5119b9e4b5c9`.
