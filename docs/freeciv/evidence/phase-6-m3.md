# Phase 6 / M3 evidence

Date: 2026-07-18 UTC

## Implementation

`src/freeciv_agent/planning` defines immutable plans, steps, assumptions, branch
scores, and ledgers. The scheduler consumes only an M1 proof and M2 numeric snapshot,
topologically orders prerequisites, uses declared research rates/progress/costs,
keeps feasibility grade separate from scheduler cost, and emits typed non-plans on
missing data, timeout, or horizon exhaustion. Every step carries snapshot and legal
action digests for immediate pre-execution validation.

## Acceptance results

- P6.A1: `artifacts/freeciv/m3-live-eta/eta-report.json` contains 34 completed live
  research trials across three 100-turn logs; all 34 have zero turn error (100%
  within +/-1, required 95%).
- P6.A2: the deterministic 10,000-tree property run records zero resource
  double-spends.
- P6.A3: 20 sampled `civ2civ3` sequential tech schedules equal the exhaustive
  optimum, within the required 5%.
- P6.A4: the 200-turn V5 engine soak submitted 400 versioned planned actions with
  zero engine rejection and blocked 199 deliberately stale attempts locally.
- P6.A5: grade and cost are distinct dataclass/schema/event fields and the test
  rejects combining them.
- P6.A6: identical proof, snapshot, and configuration serialize byte-identically.
- P6.A7: missing rate/cost, bounded-solver timeout, and horizon exhaustion return
  typed `NonPlan` values and cannot reach execution.

## Repeatable commands

```bash
pytest -q Autotests/test_freeciv_planning.py
python3 scripts/freeciv/analyze_live_eta.py \
  --events artifacts/freeciv/m3-live-eta/events.jsonl \
  --events artifacts/freeciv/m3-live-eta/continuation/events.jsonl \
  --events artifacts/freeciv/m3-live-eta/continuation-2/events.jsonl \
  --out artifacts/freeciv/m3-live-eta/eta-report.json
```

Result: eight planner tests passed; the live ETA report passed P6.A1.
