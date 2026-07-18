# Phase 10 / M6 and V4 evidence

Date: 2026-07-18 UTC

## Implementation

The model receives a typed M2 `StateSummary`, plan status/invalidation context, a
mechanically generated symbol catalog, and budgets. The v1 proposal parser rejects
unknown predicates/entities and performs bounded correction. Every factual claim is
routed to believe, disbelieve, or quarantine; quarantine is not a belief API. Valid
goals pass through oracle grading and scheduler costing as separate fields. Whole-turn
timeouts emit verification/logging-gap events and a safe `end_turn` rather than
bypassing the gate.

The real backend calls Ollama `/api/chat` with `qwen3-coder-next:latest`, temperature
zero, and explicit `think: false`; all three values are recorded in the manifest. The
final single-worker release soak is retained at
`artifacts/freeciv/m6-engine-200-turn`. Its manifest configuration hash is
`d32a072417f15f1930d44f838ed33e50ef5182d3603bd1e5f22dd6af6c9bf8c8`.
It completed all 200 real engine turns with all six capabilities enabled, 229 engine
actions, one scheduler-selected planned action, one invalid-plan attempt blocked,
zero engine rejects, and zero confabulation write-through. All 200 full-loop samples
were below 30 seconds; maximum was 5,719.28 ms and p95 was 154.16 ms. The 4,126-event
trace validates without errors and has SHA-256
`a9cf20de0cbc93907789ba7f0dcd2728bd0b64d67665d0d25ef3faaf484374ba`.

An initial pre-turn startup attempt was explicitly classified as infrastructure
failure (`authoritative state did not reach turn 1`) and retained under
`artifacts/freeciv/m6-engine-200-turn/attempt-history`; an identical retry saw the
same empty cached turn-0 state. Neither contributed gameplay or latency samples. The
unchanged third attempt received authoritative turn 1 and completed the acceptance
run.

## Acceptance results

- P10.A1: 100 seeded proposals containing 40 known-false claims produce all 40
  quarantines and zero belief/authoritative write-through.
- P10.A2: the 100-case evaluation set translates at least 95%; all rejects use bounded
  correction or a typed failure.
- P10.A3: the common M7 harness runs 30 graded and 30 ungraded games and retains the
  result independent of effect sign.
- P10.A4: the real FreeCiv/Ollama game is 200/200 full-loop samples under 30 seconds
  (100%, exceeding the 95% gate), with zero engine rejects.
- P10.A5: UI tests render all 40 quarantines with zero alarm and make a corrupted
  nonzero write-through prominent.
- P10.A6: raw state, unknown atoms, and quarantine injection fail dependency/security
  tests.
- P10.A7: the causal validator traces every sent action to proposal or monitor roots.

The local model is serialized across engine workers to avoid CPU oversubscription.
Lock-queue time and generation time share the same per-turn deadline; exhausting
either path emits the verified safe end-turn fallback while retaining the two-second
execution reserve. The harness regression suite exercises this contention path.

## Repeatable commands

```bash
pytest -q Autotests/test_freeciv_llm.py Autotests/test_freeciv_harness.py
python3 scripts/freeciv/test_ollama_proposer.py
npm --prefix apps/freeciv-observability test -- --run
FREECIV_RULESET_ROOT=... FREECIV_LLM_ROOT=... PYTHONPATH=src:benchmarks \
  python3 scripts/freeciv/run_harness.py \
    --config profile/freeciv_harness_200_turn.yaml \
    --out artifacts/freeciv/m6-engine-200-turn \
    --backend engine-live --workers 1 --limit-seeds 1 \
    --main-only --condition e_full_loop
```
