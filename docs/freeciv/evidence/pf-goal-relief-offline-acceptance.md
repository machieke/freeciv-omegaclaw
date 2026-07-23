# PF-PLN grounded goal-relief offline acceptance

Status: deterministic acceptance passed; engine outcome evaluation pending

This gate corrects the conductance semantics identified by the completed
pressure-ablation v2 pilot. Immediate action execution is no longer treated as
goal relief.

The deterministic sequence covers a founder movement followed by city
founding:

1. The authoritative actor position changes, so the move has a local effect.
2. Owned city count does not change, so realized expansion relief is zero.
3. The movement route receives one-quarter no-progress decay and no positive
   teleological credit.
4. A later, candidate-specific city-founding effect increases bounded
   authoritative expansion truth by one third.
5. The city-founding route receives direct monotonic credit.
6. Exactly one pending `expansion_move` category route receives downstream
   credit causally linked to the founding feedback ID.
7. A second drain returns no updates, proving that the goal event cannot
   multiply route credit.

Additional acceptance checks prove that:

- positive relief without an observed candidate effect is rejected;
- relief without a nonempty authoritative source is rejected;
- replaying a feedback ID is idempotent;
- downstream credit does not count the original local effect twice;
- defense production routes to the survival goal;
- population-recovery actions route to the score goal;
- legacy v1 feedback and event payloads remain valid;
- new v2 conductance payloads pass the existing event schema; and
- pressure feedback changes no truth value or engine state.

Run the offline gate with:

```bash
PYTHONPATH=src:benchmarks python3 -m pytest -q \
  Autotests/test_freeciv_pressure.py \
  Autotests/test_freeciv_impact.py
```

This is a semantic and replay claim only. It does not establish a score or
win-rate improvement. A fresh engine smoke must validate event provenance and
exact decision replay before a new seed-disjoint paired pilot is predeclared.
