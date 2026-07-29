# Unified PLN pressure-bridge-fluid implementation status

Status date: 2026-07-29

Plan:
`agent-instructions/freeciv_unified_pln_pressure_bridge_fluid_implementation_plan.md`

Branch: `experimental/pln-pressure–bridge–fluid`

## Executive decision

The implementation plan has been executed through its scientific decision
gates. The resulting supported architecture is:

```text
authoritative grounded candidates
  -> scalar PF-v2 typed semantics
  -> whole RequirementSet packets
  -> exact current-state revalidation
  -> execution
```

Bridge and conserved-flow implementations remain available for benchmarks,
offline replay, shadow, and explicitly experimental advisory operation. They
are not supported as live authority.

This is the plan's intended falsifiable outcome, not an unfinished attempt to
force every proposed layer into production:

- G0 through synthetic G4 passed their scoped acceptance gates.
- Stage-S5 integration, replay, safety, observability, and rollback
  infrastructure are implemented.
- The fresh engine-backed S5 score endpoint did not replicate the pilot.
- The dominant terminal-delay defect was corrected and verified, but the
  remaining reversible advisory behavior still supplied no directional
  benefit.
- The S5 live release gate is therefore stopped.
- Conditional Stage S6 native acceleration is not entered.

The default and rollback controller remains scalar-v2. No score, gameplay,
score-lead, or win-rate claim is made for unified-flow advisory.

## Stage and gate status

| Stage | Implementation result | Gate decision | Evidence |
|---|---|---|---|
| S0 | Immutable scalar-v1 source, fixture, ruleset, runtime, solver, and golden identities; strong smoothed scalar comparator | G0 passed | `docs/freeciv/pf-pln-unified-baseline.md`, `benchmarks/freeciv/pf_unified/baseline_manifest.yaml` |
| S1 | Scalar PF-v2 achievement/uncertainty split, signed channels, risk, RequirementSets, whole packets, compatibility and deterministic replay | G1 passed | `docs/freeciv/evidence/pf-unified-g1-verification.json` |
| S2 | Explicit loss, transition, cost-to-go, leverage, typed advantage, metacontrol, outcome pairing, calibration ledgers, and component-live packet contracts | G2 implementation/parity passed; not a gameplay claim | `docs/freeciv/evidence/pf-unified-g2-verification.json` |
| S3 | Separate forward/backward bridge semantics, corrected/holdout probes with ESS, signal-use firewall, conductance equivalence, live legality/replay/fallback | G3 passed on its preregistered held-out synthetic/captured-snapshot scope | `docs/freeciv/evidence/pf-unified-g3-bridge-experiment.json` |
| S4 | Python source-sink projection, provenance capacities, two-dye conservative transport, bounded candidate readout, packets, diagnostics, repair/fallback | G4 passed for shadow integration on 1,024 held-out synthetic cases | `docs/freeciv/evidence/pf-unified-g4-flow-sandbox.json` |
| S5 | Versioned adapter/query/decision, semantic epochs, exact revalidation, shadow/advisory/live gates, explanations, bounded-staleness support, events, rollback, deterministic replay, paired engine evaluation | Infrastructure complete; live release stopped because fresh primary endpoint failed and transitions remain uncalibrated | flow advisory evidence listed below |
| S6 | Python remains semantic oracle; native boundary was not frozen or implemented | Correctly skipped: successful Python live subset and algorithmic-value entry criteria were not met | plan Sections 15 and 21.10 |

## Realized semantic and safety requirements

The implementation preserves the plan's non-negotiable boundaries:

- epistemic truth is separate from pressure, bridge, flow, congestion, and
  resource state;
- achievement deficit and epistemic uncertainty are separate;
- signed demands aggregate commutatively;
- AND coalitions retain complete RequirementSet demand;
- operations consume whole typed packets;
- cost, risk, deadline urgency, bridge, and flow signals each have declared
  single-use positions;
- forward and backward legality are distinct;
- accounting edges cannot become proof or causal evidence;
- capacity dual interpretation follows measured, allocated, or shaping
  provenance;
- the mutable FlowView is non-authoritative and has semantic replay identity;
- only authoritative grounded candidates can be selected;
- exact current-state revalidation precedes commit;
- every failure degrades through the declared scalar fallback ladder;
- legacy v1 artifacts and modes remain readable;
- explanation products separately answer belief, consideration, and action;
  and
- LLM/induction proposals remain quarantined until their existing validation
  gates pass.

The runtime rejects invalid controller combinations. `unified_flow_live`
requires explicit live enablement, commit revalidation, scoped eligible paired
evidence, calibrated transitions, bounded rejection/latency, packet
conservation, and allowed category/context. Those requirements currently fail
closed by design.

## Scientific gate results

### G3 bridge

The nine-family bridge experiment used 576 held-out cases and a strong
smoothed scalar comparator. It found incremental forward-reachability and
packet-completion value within that synthetic scope. Captured-snapshot checks
also passed legality, exact replay, single-use signal, packet conservation,
and injected fallback tests. The recorded full bridge path remained below its
500 ms per-query controller budget.

This supports bridge component/shadow work. It is not a FreeCiv gameplay
claim.

### G4 conserved flow

The held-out flow sandbox covered 1,024 cases, 15 implementation/ablation
arms, 12 named baselines, 256 stability settings, corridor lengths 4–128,
dynamic failures, capacity provenance, fallback injection, and exact packet
comparison.

Recorded packet completion was:

- strong smoothed scalar: 107/1,024;
- bridge scoring without flow: 536/1,024;
- bridge plus scalar packet scheduling: 756/1,024; and
- full controller: 930/1,024.

The full-versus-scalar lift was `+0.8037 [+0.7793, +0.8281]`; the
full-versus-bridge-packet lift was
`+0.1699 [+0.1475, +0.1934]`. Packet completion correlated `0.9661` with
realized synthetic value. G4 therefore authorized shadow integration only.

### S5 engine confirmation

After replay hardening, a claim-ineligible 40-pair pilot estimated player
score `+0.675 [+0.20, +1.20]`. It froze a seed-disjoint 100-pair confirmation
without parameter changes.

The confirmation completed all 200 engine arms from one clean source identity
with zero failures:

- player score delta: `+0.05 [-0.33, +0.43]`;
- exact paired sign-flip `p=0.839085`;
- 22 improved, 21 declined, and 57 tied;
- settlement completion delta: `-0.04 [-0.10, +0.01]`;
- all safety, legality, initial-state, source-freeze, turn-budget, replay, and
  event-validation gates passed.

The result is valid and negative. It does not support the pilot direction or
any live score claim.

Mechanism analysis localized the result to 205 direct disagreements across 64
seeds. In 165 cases, the fixed 50% overlap region excluded scalar-v2's
immediately legal city founding and selected further movement to another
settlement-eligible tile. All 12,258 projections were healthy; this was an
uncalibrated semantic preference, not numerical failure.

### Terminal-action correction

The v2 advisory guard now abstains when an uncalibrated controller disagrees
with scalar-v2 on either side of an actor-consuming terminal action.

A fresh ten-pair diagnostic:

- guarded five terminal disagreements;
- retained `unit_build_city` on every affected turn;
- accepted no terminal displacement;
- made settlement completions exactly equal;
- left four reversible disagreements;
- produced nine score ties and one one-point decline; and
- passed all safety/source/event gates.

The diagnostic score delta was `-0.10 [-0.30, 0.00]`. It closes the known
correctness defect but provides no reason to start another pilot.

A subsequent same-seed engineering replay proved that compact events retain
and causally link the flow-proposed candidate, effective fallback candidate,
terminal flags, disposition, transport readout, and exact guard reason.

## Stop and simplification decision

The following explicit plan stop conditions are met:

- flow advisory does not beat the next simpler tuned controller after
  controller-inclusive overhead in fresh engine evaluation;
- empirical transition calibration has not transferred to live authority;
- the layer adds roughly 220–230 ms/turn of impact planning and roughly
  266–292 ms/turn of full-loop time without confirmed score value; and
- after the terminal correctness fix, the remaining complexity still has no
  positive diagnostic direction.

Consequences:

1. Scalar-v2 plus packet scheduling is the supported live subset.
2. Unified flow remains inspectable and replayable, but experimental.
3. `unified_flow_live` retains no eligible evidence object and cannot activate.
4. Pilot and confirmation results are not pooled.
5. No post-result seed extension or parameter retuning is represented as
   confirmation.
6. Native/CeTTa/MORK acceleration is not used to rescue a negative algorithmic
   result.
7. Negative results remain in tracked documentation.

## Verification closeout

Final host verification on the branch:

- `PYTHONPATH=.:src:benchmarks pytest -q Autotests/test_freeciv_*.py`:
  **771 passed, 0 failed**;
- `python3.8 scripts/freeciv/run_pf_unified_baseline.py verify`:
  archived source, fixtures, and goldens valid with original baseline identity;
- `PYTHONPATH=src:benchmarks python3.8 scripts/freeciv/audit_pf_pln.py
  --workers 4`: every canonical PF-PLN phase 0–9 and runtime-boundary check
  passed;
- v1 confirmation event validation: **200/200 valid**;
- v2 terminal-guard diagnostic event validation: **20/20 valid**; and
- guarded event replay validation: **4/4 valid**.

The baseline verifier reads S0 fixture bytes from the frozen Git source commit
rather than mutable live schema paths. Current committed goldens remain
working-tree verified. This preserves the archived identity as later event
schemas evolve.

## Evidence index

- `docs/freeciv/pf-pln-unified-baseline.md`
- `docs/freeciv/evidence/pf-unified-g1-verification.json`
- `docs/freeciv/evidence/pf-unified-g2-verification.json`
- `docs/freeciv/evidence/pf-unified-g3-bridge-experiment.json`
- `docs/freeciv/evidence/pf-unified-g4-flow-sandbox.json`
- `docs/freeciv/evidence/pf-unified-flow-advisory-diagnostic-v1.md`
- `docs/freeciv/evidence/pf-unified-flow-advisory-diagnostic-v2.md`
- `docs/freeciv/evidence/pf-unified-flow-advisory-determinism-replay-v1.md`
- `docs/freeciv/evidence/pf-unified-flow-advisory-pilot-v1.md`
- `docs/freeciv/evidence/pf-unified-flow-advisory-confirmatory-v1.md`
- `docs/freeciv/evidence/pf-unified-flow-advisory-terminal-guard-diagnostic-v2.md`

## Final acceptance statement

The implementation plan is realized as a gated scientific program and a safe
software architecture. It does not establish that unified PF-PLN flow is
better in FreeCiv. It establishes:

- the proposed semantics, bridge, flow, packet, adapter, safety, replay,
  observability, and evaluation machinery exist and are verified;
- bridge/flow value exists in the declared synthetic regimes;
- unified flow v1 does not improve the fresh engine score endpoint;
- the discovered terminal-action defect is corrected;
- the corrected residual advisory still does not justify further activation;
  and
- the repository safely retains the strongest proven subset instead of
  escalating unproven complexity.
