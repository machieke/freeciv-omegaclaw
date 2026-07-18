# Phase 9 / M5 evidence

Date: 2026-07-18 UTC

Plans record assumption atom, threshold, prior TV, provenance, proof/subtree hash,
and affected step IDs. `PlanMonitor` indexes these dependencies, batches simultaneous
revisions into one transaction, invalidates atomically, and guards execution.
`LocalRepairer` invokes only the broken subtree, preserves immutable unaffected
hashes, and returns an explicit no-plan on failure/timeout. Real engine conditions
`d` and `e` attempt the invalid step through the execution gate and prove it is
blocked before executing the repaired replacement.

## Acceptance results

- P9.A1: the chokepoint test invalidates in the same turn, names the exact atom and
  revision, and immediately blocks execution.
- P9.A2: instrumentation calls only the broken subtree and records all unaffected
  hashes as reused.
- P9.A3: 50 adversarial executions send zero actions from invalid plans. Real engine
  full-loop smoke records one blocked zombie attempt and zero rejected engine actions.
- P9.A4: a 50-step repair completes below two seconds on the recorded dev profile.
- P9.A5: simultaneous failures yield one deterministic invalidation transaction.
- P9.A6: the same real event types feed replay; V3 assertions show exact broken atom,
  reused/re-derived hashes, and no future-state leakage.

## Repeatable command

```bash
pytest -q Autotests/test_freeciv_monitoring.py Autotests/test_freeciv_state_bridge.py
```

Result: all monitor, repair, and execution-gate tests passed.
