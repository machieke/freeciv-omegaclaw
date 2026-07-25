# PF-PLN Phase 7: pressure-triggered LLM gateway acceptance

Date: 2026-07-25 UTC

Implementation commit:
`d8fb9e2a717916cefaae33309a2d2274e4121d04`

Evidence artifact:
[pf-llm-gateway-phase-7.json](pf-llm-gateway-phase-7.json), structural
hash
`d481fcbc4ca2907b471ac5773d9d4b762c949846c37746f284cd903c848ca95b`.

## Implemented boundary

The retained constrained JSON proposer, symbol catalog, claim router, belief
sink, quarantine, goal grader, and safe fallback remain authoritative. Phase 7
adds the missing call-control boundary:

- a typed high-pressure gap request identifies the exact target, context,
  clone, known rules, unresolved premises, forbidden assumptions, action/time
  budgets, and validation plan;
- environment-originated text cannot enter those fields as instructions
  because every external value must pass the bounded identifier grammar;
- call quality is
  `expand_pressure * useful_probability * expected_relief /
  (latency_cost + token_cost + validation_cost)`;
- calls below expansion pressure or quality thresholds do not reach the model;
- the token ledger enforces idempotent per-turn, per-call, and total
  reservations, and conservatively charges the full reservation on failure or
  overflow;
- every response is stored in a low-confidence, `quarantined` proposal
  envelope with model, prompt hash, timestamp, typed context, token use, and
  explicit validation routes; and
- the end-to-end pressure-gated turn loop cannot grade or select a proposal
  before the existing claim verifier runs.

The strict `llm_call_scheduled` and `llm_gateway_result` events expose the
decision, operation, proposal authority, reservation state, token charge, and
causal ancestry.

## Deterministic ablation

Command:

```bash
python3 scripts/freeciv/run_pf_llm_gateway_benchmark.py \
  --out docs/freeciv/evidence/pf-llm-gateway-phase-7.json
```

The fixed 100-case structured corpus contains 40 high-expansion-pressure and
60 low-pressure gaps. Proposal parsing and claim validation use the real
`ConstrainedProposer` and `ClaimRouter`. The unconditional arm invokes all 100
cases; the pressure-gated arm invokes only admitted calls. Both arms use the
same deterministic UTF-8 token estimator, which is conservative local
scheduling evidence rather than provider billing telemetry.

Results:

- unconditional: 38 validated proposals / 50,062 tokens =
  `0.00075906` validated proposals per token;
- pressure-gated: 32 validated proposals / 25,838 tokens =
  `0.00123849` validated proposals per token;
- absolute rate improvement: `0.00047943`;
- relative rate improvement: `63.16%`;
- selected calls: 40 high-pressure, zero low-pressure;
- invalid gated claims quarantined: 8; and
- quarantine escapes: zero.

This passes the Phase 7 exit criterion on the deterministic corpus. It does not
claim that the model will achieve the same rate improvement in live gameplay;
that would require a separate provider-backed, predeclared cohort.

## Verification

```bash
pytest -q Autotests/test_freeciv_*.py
# 309 passed

cd apps/freeciv-observability
npm test -- --run
# 20 tests passed; fixtures, boundaries, typecheck, and production build passed

python3 scripts/freeciv/generate_event_types.py --check
# generated event types are current
```
