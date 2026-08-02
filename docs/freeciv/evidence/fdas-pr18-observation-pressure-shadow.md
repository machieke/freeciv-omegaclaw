# FDAS PR18 observation-pressure shadow evidence

## Scope

This slice wires the existing value-of-information planner into the real
engine loop for one bounded opponent-presence decision. It is deliberately
shadow-only. It proves that a real uncertain belief can create epistemic
pressure, pass an explicit counterfactual decision-sensitivity gate, reserve
whole CPU and observation packets, and produce auditable selection artifacts
without executing an observation or modifying evidence.

It does not claim observation-action authority, authoritative evidence return,
gameplay improvement, or score improvement.

## Implemented boundary

The planner no longer accepts a free-form decision-relevance declaration for
this path. `BoundedDecision` enumerates the action below and at/above a declared
probability threshold. Each possible test outcome is evaluated with Bayes'
rule, and decision sensitivity is the total probability of outcomes that
change that bounded action readout. A test that cannot cross the decision
boundary is omitted before scheduling.

The real opponent-presence belief is represented with its uncertain truth
value and routed through `PressureEngineV2`. The target strength is kept equal
to current belief strength, so achievement demand is exactly zero; only the
confidence gap creates epistemic demand. The chosen diagnostic requires one
CPU packet and one observation packet, which are committed atomically in the
shadow schedule.

The emitted causal chain is:

```text
real opponent-presence observation/revision
  -> FDAS belief rematerialization
  -> pressure_propagated (achievement/uncertainty split)
  -> operation_scored (bounded diagnostic candidate)
  -> packet_reserved (whole CPU + observation packets, shadow-only)
  -> fdas_observation_pressure_latency_ms
```

The packet event records the prior and posterior decision readouts, expected
information gain, simulator identity and confidence cap, deterministic unknown
propensity, the configured selection-effect discount, and evidence-store hashes
before and after planning. The engine raises if planning changes either the
evidence count or belief-store artifact hash.

## Fresh engine-backed cohort

The predeclared diagnostic cohort
`fdas_observation_pressure_shadow_diagnostic_v1` ran at a 30-turn horizon on
seed `314159`. Both arms used the same FDAS observation-pressure shadow; their
legacy production policies differ, so the pair is mechanism evidence rather
than an FDAS treatment-effect comparison.

The source was clean commit
`80cf43b0d5c27fc57a99cb191509c0edd5b1bb1b`, implementation SHA-256
`9c2913603f46c69c66ed6d4f7faf6224067d08ec1da0b03911521a1b262de8e6`,
FDAS declaration hash
`d5cd60f81db3c5bf2f752da74279cd1fb733db5b8ddc274d36d7394499dc3ad8`,
and cohort configuration hash
`b0dd679586a63232eb2a49bcf62758d42a201b27e8bdf385941489a48dd77323`.

| Measure | Baseline | Treatment |
| --- | ---: | ---: |
| Horizon reached | yes | yes |
| Engine actions / accepted results / rejects | 72 / 72 / 0 | 63 / 63 / 0 |
| Observation-pressure decisions | 1 | 1 |
| Atomic packet commits | 1 | 1 |
| CPU packets consumed | 1 | 1 |
| Observation packets consumed | 1 | 1 |
| Counterfactual decision-change probability | 0.14 | 0.14 |
| Raw information gain, bits | 0.115243 | 0.115243 |
| Decision-weighted information gain | 0.016134 | 0.016134 |
| Evidence write-throughs | 0 | 0 |
| FDAS/policy authority actions | 0 | 0 |
| Observation-pressure latency | 3.91 ms | 2.42 ms |
| Event-schema errors / warnings | 0 / 0 | 0 / 0 |

The one-step likelihood model is
`fdas-visible-presence-refresh/1.0`, hash
`6cbc6dda6e544ba42ff9e10c696a16875325baa82981af0cf48b74d2e93b5160`.
It is explicitly inexact, scoped to `civ2civ3`, opponent presence, and one
step, and capped at confidence `0.6`. The live prior probability was `0.95`;
the test was selected because an outcome crosses the `0.8` retention threshold
with probability `0.14`.

The deterministic audit accepted every per-arm and paired check. Its structural
hash is
`efa66278c31a71f4d9e0dcdecc5b703edf21ab29387d6c701c9928c497427967`.
The machine-readable report is
[`fdas-pr18-observation-pressure-engine.json`](fdas-pr18-observation-pressure-engine.json).

## Reproduction

```bash
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_observation_pressure_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_observation_pressure_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_impact_evaluation.py \
  --config profile/freeciv_harness.yaml \
  --out artifacts/freeciv/fdas-observation-pressure-live-30-v2 \
  --backend engine-live --workers 1 --server-ports 6001 \
  --cohort fdas_observation_pressure_shadow_diagnostic_v1 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_observation_live.py \
  --cohort-root artifacts/freeciv/fdas-observation-pressure-live-30-v2 \
  --output docs/freeciv/evidence/fdas-pr18-observation-pressure-engine.json
```

The environment must also supply the existing FreeCiv proxy URL/WebSocket,
server container, ruleset root, Ollama OpenAI-compatible base URL, and API token.

## Claim boundary and continuation

This closes the Phase 8 shadow-live observation-selection mechanism for a real
belief and bounded decision. It does not close an FDAS authority path. The
later [`fdas-pr20-observation-return.md`](fdas-pr20-observation-return.md)
increment closes the non-authorizing execution firewall for a separate
visibility-frontier test: it binds only to a byte-identical legacy-selected
move, exact-revalidates it, and accepts fresh visibility evidence through
`ObservationEvidenceGate`, with explicit no-write censoring when the move
cannot be proven at the endpoint.

PR20 does not treat visibility expansion as direct opponent-presence evidence
and does not let FDAS choose the move. PR21 subsequently exercised conflict
and complete quarantine with an independent player-visible lineage and a
capped diagnostic prior; see
[`fdas-pr21-belief-conflict.md`](fdas-pr21-belief-conflict.md). It remains
non-authorizing and deliberately does not establish model quality. Broader
decision gaps or an FDAS-selected observation action need separate
calibration, safety, and activation evidence.
