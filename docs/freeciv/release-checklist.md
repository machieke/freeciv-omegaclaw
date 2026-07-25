# PLN-FreeCiv release checklist

Date: 2026-07-25 UTC

Branch: `experimental/pln-pressure`

This is the P12.A5 evidence index. Every acceptance criterion in the original
M0-M7 agent specification and V0-V5 observability specification is listed with a
repeatable command, retained artifact/evidence report, and explicit result. An
empirical result that does not meet a prediction is marked `NOT MET`; it is not
waived, hidden, or relabeled as an infrastructure pass.

## Command bundles

| ID | Repeatable command |
|---|---|
| C-M0 | `FREECIV_RULESET_ROOT=... pytest -q Autotests/test_freeciv_rulesets.py` plus two `scripts/freeciv/compile_ruleset.py` runs per ruleset |
| C-M1 | `python3 scripts/freeciv/run_engine_parity.py --ruleset-root "$FREECIV_RULESET_ROOT" --states 50 --seed 20260717 --out artifacts/freeciv/m1-parity` and `python3 scripts/freeciv/run_oracle_properties.py --ruleset-root "$FREECIV_RULESET_ROOT" --pairs 100 --seed 20260717` |
| C-M1-PERF | `python3 scripts/freeciv/benchmark_oracle.py --ruleset-root "$FREECIV_RULESET_ROOT" --ruleset civ2civ3 --rounds 5` |
| C-M2 | `python3 scripts/freeciv/run_live_state_parity.py --ws-url "$FREECIV_PROXY_WS" --api-token "$FREECIV_API_TOKEN" --game-id pln-state-parity --agent-id pln-state-parity --port 6001 --turns 100 --seed 613 --events artifacts/freeciv/state-parity/events.jsonl` |
| C-M3 | `pytest -q Autotests/test_freeciv_planning.py` and `python3 scripts/freeciv/analyze_live_eta.py --events artifacts/freeciv/m3-live-eta/events.jsonl --events artifacts/freeciv/m3-live-eta/continuation/events.jsonl --events artifacts/freeciv/m3-live-eta/continuation-2/events.jsonl --out artifacts/freeciv/m3-live-eta/eta-report.json` |
| C-M4 | `pytest -q Autotests/test_freeciv_beliefs.py Autotests/test_freeciv_oracle.py` plus C-M7-ENGINE calibration aggregation |
| C-M5 | `pytest -q Autotests/test_freeciv_monitoring.py Autotests/test_freeciv_state_bridge.py` plus C-M7-ENGINE zombie-action audit |
| C-M6 | `pytest -q Autotests/test_freeciv_llm.py Autotests/test_freeciv_harness.py` and `python3 scripts/freeciv/test_ollama_proposer.py` |
| C-M6-200 | `python3 scripts/freeciv/run_harness.py --config profile/freeciv_harness_200_turn.yaml --out artifacts/freeciv/m6-engine-200-turn --backend engine-live --workers 1 --limit-seeds 1 --main-only --condition e_full_loop` |
| C-M7 | `python3 scripts/freeciv/run_harness.py --out artifacts/freeciv/m7-representative-current --backend representative --workers 3 --no-resume` followed by the same output with `--aggregate-only` |
| C-M7-ENGINE | `python3 scripts/freeciv/run_harness.py --out artifacts/freeciv/m7-engine-release-current-20260718 --backend engine-live --workers 3` followed by the same output with `--aggregate-only` |
| C-V0 | `python3 scripts/freeciv/generate_synthetic_log.py --all --overwrite --out artifacts/freeciv/v0-synthetic-v2` and `pytest -q Autotests/test_freeciv_events.py` |
| C-UI | `npm --prefix apps/freeciv-observability test` |
| C-V5 | `pytest -q Autotests/test_freeciv_events.py` and `apps/freeciv-observability/node_modules/.bin/vite-node apps/freeciv-observability/scripts/compare-live-replay.ts --events artifacts/freeciv/v5-live-200/events.jsonl --output artifacts/freeciv/v5-live-200/equivalence.json` |
| C-PF-RELEASE | `python3 scripts/freeciv/audit_pf_pln.py --workers 4 --output artifacts/freeciv/pf-pln-release-audit/report.json` |
| C-RELEASE | `python3 scripts/freeciv/audit_release.py --ruleset-root "$FREECIV_RULESET_ROOT" --freeciv-llm-root "$FREECIV_LLM_ROOT" --events artifacts/freeciv/m7-engine-release-current-20260718/games/main/e_full_loop/104729-00/events.jsonl --events artifacts/freeciv/m6-engine-200-turn/games/main/e_full_loop/104729-00/events.jsonl --require-cognitive-trace --output artifacts/freeciv/release-audit-final/report.json` |

## Agent acceptance criteria (M0-M7)

| Criterion | Result | Command | Artifact and recorded result |
|---|---|---|---|
| M0 A0.1 rule/edge parity | PASS | C-M0 | [Phase 2](evidence/phase-2-m0.md): civ2civ3 216 targets/317 edges and classic 209/292, zero mismatch |
| M0 A0.2 20-tech/20-unit antecedent audit | PASS | C-M0 | [Phase 2](evidence/phase-2-m0.md): exact independent-reference equality for both rulesets |
| M0 A0.3 deterministic hashes | PASS | C-M0 | [Phase 2](evidence/phase-2-m0.md): two fresh runs byte-identical; all output hashes retained |
| M0 A0.4 zero handwritten game rules | PASS | C-M0, C-RELEASE | [Phase 2](evidence/phase-2-m0.md): legacy rulebase removed; repository scan passes |
| M1 A1.1 native engine parity | PASS | C-M1 | [Phase 3](evidence/phase-3-m1.md), [civ2civ3 artifact](../../artifacts/freeciv/m1-parity/civ2civ3-parity.json), [classic artifact](../../artifacts/freeciv/m1-parity/classic-parity.json): 4,350 comparisons each, zero mismatch |
| M1 A1.2 unsatisfied-leaf correctness | PASS | C-M1 | [Phase 3](evidence/phase-3-m1.md): 100 pairs/269 native checks, zero failures |
| M1 A1.3 typed unreachable | PASS | C-M1 | [Phase 3](evidence/phase-3-m1.md): disabled/missing goals return `UNREACHABLE` frontier |
| M1 A1.4 latency/regression threshold | PASS | C-M1-PERF | [Phase 3](evidence/phase-3-m1.md): 90.18 ms max; 180.36 ms 2x gate |
| M2 A2.1 100-turn state fidelity | PASS | C-M2 | [Phase 4](evidence/phase-4-m2.md): 100 live authoritative turns, zero field/atom/grounded mismatch |
| M2 A2.2 no stale-state engine actions | PASS | C-M2 | [Phase 4](evidence/phase-4-m2.md): 99 stale attempts blocked locally, zero engine rejection |
| M2 A2.3 no arithmetic by inference | PASS | C-M0, C-RELEASE | [Phase 4](evidence/phase-4-m2.md): denylist/static/runtime audits pass |
| M3 A3.1 ETA +/-1 for >=95% of 30 goals | PASS | C-M3 | [Phase 6](evidence/phase-6-m3.md), [ETA artifact](../../artifacts/freeciv/m3-live-eta/eta-report.json): 34/34 within one turn |
| M3 A3.2 10,000 ledgers, zero double-spend | PASS | C-M3 | [Phase 6](evidence/phase-6-m3.md): deterministic property run, zero violations |
| M3 A3.3 schedule <=5% over optimum | PASS | C-M3 | [Phase 6](evidence/phase-6-m3.md): 20/20 sampled goals equal optimum |
| M3 A3.4 200-turn engine legality | PASS | C-V5 | [Phase 12](evidence/phase-12-v5.md), [soak report](../../artifacts/freeciv/v5-live-200/report.json): 400 planned actions, zero rejection |
| M4 A4.1 calibration over >=50 fixed-opponent games | PASS | C-M4, C-M7 | [Phase 8](evidence/phase-8-m4.md), [representative aggregate](../../artifacts/freeciv/m7-representative-current/aggregate.json): every populated bucket passes or is explicitly insufficient-sample; pooled/per-opponent counts retained |
| M4 A4.2 idempotent observation replay | PASS | C-M4 | [Phase 8](evidence/phase-8-m4.md): double replay byte-identical to single replay |
| M4 A4.3 provenance path independence | PASS | C-M4 | [Phase 8](evidence/phase-8-m4.md): three paths equal single-provenance value |
| M4 A4.4 >=80% high-confidence abduction truth | PASS | C-M4 | [Phase 8](evidence/phase-8-m4.md): threshold exceeded; no unseen claim becomes crisp |
| M4 A4.5 decay and re-scout | PASS | C-M4 | [Phase 8](evidence/phase-8-m4.md): belief crosses configured threshold and policy re-scouts |
| M5 A5.1 chokepoint invalidation <=1 turn | PASS | C-M5 | [Phase 9](evidence/phase-9-m5.md): same-turn named revision/invalidation |
| M5 A5.2 subtree-local repair | PASS | C-M5 | [Phase 9](evidence/phase-9-m5.md): only broken subtree re-derived; unaffected hashes reused |
| M5 A5.3 zero zombie actions over 50 adversarial games | PASS | C-M5, C-M7 | [Phase 9](evidence/phase-9-m5.md): 50 adversarial attempts blocked, no invalid-plan transport |
| M5 A5.4 repair under 2 s at 50 steps | PASS | C-M5 | [Phase 9](evidence/phase-9-m5.md): recorded latency below 2 s |
| M6 A6.1 40 false claims, zero write-through | PASS | C-M6 | [Phase 10](evidence/phase-10-m6-v4.md): 40/40 quarantined with evidence, zero write-through |
| M6 A6.2 >=95% goal translation | PASS | C-M6 | [Phase 10](evidence/phase-10-m6-v4.md): evaluation set meets threshold; bounded correction/typed failure |
| M6 A6.3 graded behavior improves win/score | NOT MET | C-M7, C-M7-ENGINE | [Phase 11](evidence/phase-11-m7-v4.md): representative deltas were zero; engine win point delta is +0.0333 with interval including zero and score delta is zero. A conclusive improvement is not claimed |
| M6 A6.4 >=95% of a real 200-turn game under 30 s | PASS | C-M6-200 | [Phase 10](evidence/phase-10-m6-v4.md), [events](../../artifacts/freeciv/m6-engine-200-turn/games/main/e_full_loop/104729-00/events.jsonl): 200/200 under 30 s, max 5.72 s, zero rejects |
| M7 A7.1 all conditions/same seeds/one command | PASS | C-M7-ENGINE | [Phase 11](evidence/phase-11-m7-v4.md), [aggregate](../../artifacts/freeciv/m7-engine-release-current-20260718/aggregate.json): 250/250; five conditions x30, induction x20, grading x30 |
| M7 A7.2 marginal metrics with CIs, n>=30 | PASS | C-M7-ENGINE | Final engine aggregate contains every declared estimate/bound/count and paired marginal delta at n=30 |
| M7 A7.3 oracle vs induction tested | PASS | C-M7-ENGINE | Oracle score delta 0.0; induction accuracy delta +0.45 [0.35, 0.50]; `prediction_assumed=false` |
| M7 A7.4 equal-fidelity negative results | PASS | C-M7-ENGINE | Final report retains losses/nulls/negative effects; 13 first-pass exclusions retain raw attempt evidence under `attempt-history/first-pass` |

## Observability acceptance criteria (V0-V5)

| Criterion | Result | Command | Artifact and recorded result |
|---|---|---|---|
| V0 A1.1 shared schema/unknown preservation | PASS | C-V0, C-UI | [Phase 1](evidence/phase-1-v0.md): Python and AJV validate; unknown types preserved raw |
| V0 A1.2 200-turn causal completeness | PASS | C-V0 | [Phase 1](evidence/phase-1-v0.md), [performance log](../../artifacts/freeciv/v0-synthetic-v2/performance-200-turns.jsonl): zero orphan action |
| V0 A1.3 200-turn UI load under 10 s | PASS | C-UI | [Phase 5](evidence/phase-5-v1-v2.md): measured below 10 s |
| V1 A2.1 scrub >=10 turns/s | PASS | C-UI | [Phase 5](evidence/phase-5-v1-v2.md): indexed scrub performance passes |
| V1 A2.2 50-cursor as-of equality | PASS | C-UI | [Phase 5](evidence/phase-5-v1-v2.md): all independent folds match |
| V1 A2.3 exact deep-link restore | PASS | C-UI | [Phase 5](evidence/phase-5-v1-v2.md): view/cursor/entity/filter round-trip passes |
| V1 A3.1 why-action workflow <=5 interactions | PASS | C-UI | [Phase 5](evidence/phase-5-v1-v2.md): scripted workflow uses four interactions |
| V2 A3.2.1 200-node proof under 300 ms | PASS | C-UI | [Phase 5](evidence/phase-5-v1-v2.md): repeated DOM performance assertion passes |
| V2 A3.2.2 confidence bug found via formula | PASS | C-UI | [Phase 5](evidence/phase-5-v1-v2.md): offending step exposed within usability limit |
| V2 A3.3.1 50 atoms x 20 cursors | PASS | C-UI | [Phase 5](evidence/phase-5-v1-v2.md): independent fold equality passes |
| V2 A3.3.2 50k search under 200 ms | PASS | C-UI | [Phase 5](evidence/phase-5-v1-v2.md): indexed search passes |
| V3 A3.4.1 visible decay below threshold | PASS | C-UI | [Phase 7](evidence/phase-7-v3.md), [fixture](../../artifacts/freeciv/v0-synthetic-v2/decay-rescout.jsonl): as-of fade verified |
| V3 A3.5.1 same-tick invalidation/locality | PASS | C-UI | [Phase 7](evidence/phase-7-v3.md), [fixture](../../artifacts/freeciv/v0-synthetic-v2/invalidation-repair.jsonl): cause and reused/re-derived sets visible |
| V4 A3.6.1 quarantine and alarm | PASS | C-UI | [Phase 10](evidence/phase-10-m6-v4.md), [40-claim fixture](../../artifacts/freeciv/v0-synthetic-v2/quarantine-40.jsonl): 40 rows/zero alarm; corrupt log alarms |
| V4 A3.7.1 UI metrics equal harness | PASS | C-UI | [Phase 11](evidence/phase-11-m7-v4.md), [aggregate events](../../artifacts/freeciv/m7-representative-current/aggregate-events.jsonl): estimates/bounds/counts match exactly |
| V5 live/replay 200-turn equivalence | PASS | C-V5 | [Phase 12](evidence/phase-12-v5.md), [equivalence](../../artifacts/freeciv/v5-live-200/equivalence.json): 201 cursors, zero divergence |

## PF-PLN acceptance criteria

`C-PF-RELEASE` replays the default deterministic benchmark for every canonical
phase, verifies the checked evidence fingerprint, checks each self-hash where
present, confirms phases 0-9 are complete in the phase map, and rejects stale
generated event types. `C-RELEASE` embeds the same audit as the
`pf-pln-phase-readiness` invariant.

| Phase | Result | Evidence and recorded result |
|---|---|---|
| PF 0 executable semantics | PASS | [Phase 0](evidence/pf-executable-semantics-phase-0.md): capital-defense propagation and scheduling are deterministic, typed pressure reaches observation/action operations, and truth is unchanged |
| PF 1 goal regression | PASS | [Phase 1](evidence/pf-pressure-concentration-phase-1.md): 8.03x fewer instantiations at equal decision quality and 99.54% relevant pressure concentration |
| PF 2 provenance/contradiction | PASS | [Phase 2](evidence/pf-provenance-contradiction-phase-2.md): zero overlap errors over 8,192 duplicate paths and 256/256 cycles rejected |
| PF 3 observation/simulation | PASS | [Phase 3](evidence/pf-observation-voi-phase-3.md): 256 exhaustive rankings match and selection gains 0.365 bits over uniform random |
| PF 4 conductance learning | PASS | [Phase 4](evidence/pf-conductance-learning-phase-4.md): learned conductance abandons the infeasible branch after five attempts; the fixed prior does not abandon it within 12 |
| PF 5 lifecycle clones | PASS | [Phase 5](evidence/pf-clone-lifecycle-phase-5.md): clone conditioning improves planning success from 50% to 82% and mean log likelihood by 0.368 nats |
| PF 6 induction/analogy | PASS | [Phase 6](evidence/pf-induction-analogy-phase-6.md): held-out calibration improves without more contradictions and the overgeneralized rule is demoted |
| PF 7 LLM gateway | PASS | [Phase 7](evidence/pf-llm-gateway-phase-7.md): validated proposals per token improve 63.16%, with zero low-pressure calls and quarantine escapes |
| PF 8 differentiable execution | PASS | [Phase 8](evidence/pf-differentiable-phase-8.md): 1,444 smooth comparisons match finite differences within 4.97e-11 and discrete boundaries remain non-gradient |
| PF 9 multi-goal field | PASS | [Phase 9](evidence/pf-multi-goal-phase-9.md): joint scheduling wins 64/64 conflicting scenarios and retains per-goal explanations |

## Implementation-plan phase gates

| Phase | Result | Evidence |
|---|---|---|
| P0 foundation | PASS | [Phase 0](evidence/phase-0.md) |
| P1 V0 contract | PASS | [Phase 1](evidence/phase-1-v0.md) |
| P2 M0 compiler | PASS | [Phase 2](evidence/phase-2-m0.md) |
| P3 M1 oracle/parity | PASS | [Phase 3](evidence/phase-3-m1.md) |
| P4 M2 state bridge | PASS | [Phase 4](evidence/phase-4-m2.md) |
| P5 V1/V2 UI | PASS | [Phase 5](evidence/phase-5-v1-v2.md) |
| P6 M3 scheduler | PASS | [Phase 6](evidence/phase-6-m3.md) |
| P7 V3 plan/map | PASS | [Phase 7](evidence/phase-7-v3.md) |
| P8 M4 beliefs | PASS | [Phase 8](evidence/phase-8-m4.md) |
| P9 M5 monitoring/repair | PASS | [Phase 9](evidence/phase-9-m5.md) |
| P10 M6/V4 | PASS | [Phase 10](evidence/phase-10-m6-v4.md): real 200-turn Qwen gate passes 200/200 under budget |
| P11 M7/V4 | PASS | [Phase 11](evidence/phase-11-m7-v4.md): canonical engine aggregate passes 250/250 and deterministic re-aggregation |
| P12 V5/release | PASS | [Phase 12](evidence/phase-12-v5.md): soak, live/replay equivalence, documentation, and final cognitive-trace audit pass |
