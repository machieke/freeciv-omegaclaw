# Unified PF-PLN flow advisory determinism replay v1

Status: complete, reused-seed engineering validation; claim-ineligible

Two independent engine-backed replays ran the first exposed
`unified_flow_advisory_diagnostic_v2` pair (seed `4752647`) from clean commit
`29ec8c52140334d697153435ea0f009c93496fe3`. Both used two controller workers,
ports `6001,6003`, the frozen diagnostic configuration hash
`92628a53b3f21414c9585460b5d6f455378590b425c16b9db2bff63e8f5e9b57`,
and turn 60.

This is an engineering replay over an exposed seed. It cannot support or be
pooled into a score, gameplay, or win-rate claim.

## Defect and correction

The event-hash performance replay exposed that identical authoritative state
content could receive a different transport `source_seq`. Query IDs and flow
boundary IDs incorporated that commit-local identity, and the corrected probe
estimator seeded its RNG from the complete serialized `FlowView`. A harmless
polling difference could therefore remap stochastic probe paths and select a
different authoritative action.

The hardened controller now separates:

- **commit identity**, which retains the exact snapshot ID, source sequence,
  semantic epoch, topology generation, context digest, and candidate grounding
  required for stale-plan rejection; and
- **probe semantic identity**, which hashes legal actions, stable semantic
  nodes and edges, traversal legality, control weights, candidate bindings,
  frontiers, and materialization policy without transport/provenance metadata.

Forward, goal, and bounded-frontier stable IDs now use semantic inputs rather
than query or snapshot IDs. Probe RNG uses the versioned semantic hash.

## Replay results

- Both runs completed both arms with zero infrastructure failures.
- Source identity remained clean and stable.
- Initial-state fidelity and every absolute safety gate passed.
- Baseline replay A and B each sent the same 98 authoritative actions,
  byte-for-byte after JSON decoding and in the same turn/order.
- Treatment replay A and B also sent the same 98 authoritative actions.
- All 32 treatment `flow_candidate_selected` summaries were exactly equal
  between replays, including candidate regions, overlap readouts, selected
  operation, scalar comparator, confidence, and typed advantage.
- Both replays ended at player score `117`, opponent score `126`, margin `-9`,
  and score-lead value `0` in both arms.
- The treatment made zero direct flow-versus-scalar disagreements on this
  seed; its complete action sequence equaled baseline.

The earlier diagnostic-v2 result for this seed was baseline `117` versus
treatment `124`. That difference does not reproduce after removing the
transport-sequence leak. The four-pair diagnostic was already underpowered and
claim-ineligible; its `+1.25` directional estimate must now also be treated as
implementation-debugging history rather than evidence about the hardened
controller.

One replay emitted one fewer operational `metric_sample` event. This was
wall-clock instrumentation only: authoritative actions, flow selection
summaries, outcomes, and all safety results were identical.

## Controller-inclusive cost

The means below average the per-game means from replay A and B:

| Metric | Baseline | Treatment | Delta |
|---|---:|---:|---:|
| Impact planning | 9.33 ms/turn | 50.27 ms/turn | +40.94 ms |
| Control decision | 5.77 ms/decision | 31.10 ms/decision | +25.32 ms |
| Decision-event emission | 1.85 ms/decision | 8.32 ms/decision | +6.47 ms |
| Full turn loop | 106.28 ms/turn | 155.90 ms/turn | +49.62 ms |

The original diagnostic-v2 treatment decision-event mean was `144.24`
ms/decision. Computing the large decision hash once per event chain therefore
removes the identified repeated-hash bottleneck. The remaining planning and
event costs are measurable but stay far below the 30-second absolute turn
gate.

## Reproduction

Run the command twice with different output directories:

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks python3.8 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/unified-flow-advisory-determinism-replay-a \
  --backend engine-live \
  --cohort unified_flow_advisory_diagnostic_v2 \
  --workers 2 \
  --server-ports 6001,6003 \
  --limit-pairs 1 \
  --no-resume
```
