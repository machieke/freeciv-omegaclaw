# Calibrated transition value and decision-safe readout research plan

Status: complete — stopped after adverse CT4 pilot; CT5 entry gate remained closed
Frozen predecessor: `242fd25` (`experimental/pln-pressure–bridge–fluid`)
Supported live baseline: scalar PF-v2 plus whole-operation packets
Primary question: can better grounded transition value and candidate recall
improve FreeCiv score without granting uncalibrated bridge or flow signals
decision authority?

## 1. Scientific contract

The preceding unified PF-v2 experiment is a valid negative result. Bridge and
fluid mechanisms changed routing in synthetic graphs, but the confirmatory
FreeCiv cohort did not improve score. The dominant observed defect was
semantic: a fixed overlap readout excluded an immediately useful grounded
terminal action, while an uncalibrated transition estimate preferred a
reversible but less valuable action.

This track therefore freezes scalar PF-v2 plus packets and changes one
decision mechanism at a time. It does not retune the full flow controller.
Every stage must preserve:

- authoritative legal actions as the only executable candidates;
- truth/control separation and the evidence write-through firewall;
- deficit/uncertainty separation, signed pressure, explicit risk,
  RequirementSets, and whole-operation packet conservation;
- exact terminal-action and safety protection;
- deterministic replay for an identical model snapshot, query, and seed;
- paired, seed-matched engine evaluation;
- a fail-closed fallback to the frozen scalar PF-v2 decision whenever a new
  estimate is unsupported, stale, unhealthy, or too uncertain.

No development, pilot, diagnostic, and confirmatory cohort may be pooled.
No source-sink flow stage may start merely because an earlier stage is
implemented.

## 2. Ablation ladder

### CT0 — freeze and reproduce the comparator

Goal: preserve a byte-identifiable scalar PF-v2-plus-packets comparator.

Requirements:

- record the predecessor commit and effective controller configuration;
- reproduce deterministic captured-snapshot decisions;
- retain whole-operation packet and exact legality gates;
- keep bridge, probes, advection, and capacity projection out of authority.

Acceptance criteria:

- identical selected candidate and admissibility ordering on the frozen
  captured-snapshot corpus;
- zero packet, legality, truth-write, or replay violations;
- a machine-readable baseline identity is included in later reports.

### CT1 — calibrated scalar transition value

Goal: estimate realized goal relief for a grounded candidate and use it only
when category- and lifecycle-qualified evidence supports a narrow confidence
interval.

Requirements:

- learn from authoritative selected-action outcomes, not acceptance alone;
- pair predicted and realized relief with stable, idempotent record IDs;
- condition the primary calibration key on action category, lifecycle state,
  and goal;
- report sample count, mean correction, variance, confidence interval,
  coverage source, model identity, and abstention reason;
- keep selection propensity explicit and prohibit implicit off-policy
  correction;
- never update truth, evidence confidence, bridge height, or legal actions;
- preserve the uncalibrated scalar estimate exactly when the model abstains;
- separate data collection from decision authority;
- support a frozen read-only model snapshot for evaluation.

Acceptance criteria:

- duplicate outcome records do not change model state;
- context/lifecycle mismatches do not gain exact-key authority;
- insufficient support, wide intervals, invalid provenance, and stale model
  identity all abstain;
- held-out calibration improves realized-relief error and interval coverage
  relative to the raw transition estimate;
- scalar ordering is unchanged while authority is disabled or any compared
  estimate abstains;
- an authority-enabled disagreement is allowed only when every candidate
  capable of changing the winner has a calibrated estimate.

### CT2 — protected deterministic-bridge candidate union

Goal: test bridge-informed candidate recall without probes, current
construction, projection, advection, or capacity solving.

Requirements:

- form a bounded union containing the scalar winner, scalar top-K, every
  relevant terminal candidate, every active safety candidate, and the top
  deterministic-message bridge candidates per goal;
- bridge height may add a candidate to the union but may not alter its final
  score;
- final ordering uses only the CT1 calibrated transition value and existing
  typed costs/risk;
- if calibrated final readout is unavailable, return the scalar decision;
- record protected candidates, bridge additions, recall, and exclusion
  reasons.

Acceptance criteria:

- scalar, terminal, and safety protections cannot be excluded by any bridge
  threshold;
- changing bridge magnitude without changing membership cannot change final
  ordering;
- the prior city-founding exclusion replay retains the founding candidate;
- synthetic/captured-snapshot recall improves over scalar top-K before any
  score claim is considered;
- controller-inclusive latency remains within the preregistered budget.

### CT3 — corrected-probe reachability

Goal: determine whether corrected probes add candidate recall beyond
deterministic messages.

Requirements:

- use behavior/reference likelihoods, clipping diagnostics, ESS, and separate
  forward/backward legality;
- probes can add candidates to the protected union only;
- raw probe count, path count, or probe amplitude cannot score candidates or
  scale decision current;
- unhealthy probe batches fall back to the CT2 union;
- probe success creates no evidence token and promotes no epistemic claim.

Acceptance criteria:

- held-out recall improves beyond CT2 by a preregistered margin;
- no terminal/safety protection regression;
- ESS, clipping, diversity, and fallback reasons are complete in telemetry;
- final ranking is invariant to duplicated identical probe paths;
- no gameplay pilot if recall or latency gate fails.

### CT4 — path persistence without fluid transport

Goal: test the strongest cheap temporal comparator before numerical flow.

Requirements:

- smooth candidate/corridor value across turns using stable semantic route
  identity;
- use bounded dwell time and a switch margin;
- expire state on actor disappearance, lifecycle change, topology generation,
  illegality, terminal completion, or material grounding change;
- persistence may break calibrated near-ties but cannot retain an unsafe,
  illegal, terminally dominated, or uncalibrated action;
- record retained-by-dwell, retained-by-hysteresis, expiry, and switch cause.

Acceptance criteria:

- deterministic replay and bounded memory;
- fewer reversible oscillations without increased no-effect, rejection,
  terminal-delay, or safety events;
- better or equal held-out score direction than CT3 at materially lower cost
  than source-sink flow;
- no source-sink stage if persistence already fails its gameplay gate.

### CT5 — source-sink flow

Goal: add numerical transport only after transition calibration and cheap
readouts have earned their roles.

Entry gates:

- CT1 held-out calibration and decision-safety gates pass;
- either CT2 or CT3 materially improves candidate recall;
- CT4 has completed a paired engine diagnostic;
- the remaining error is demonstrably route-allocation error rather than
  transition-value or readout error.

Requirements:

- retain the protected union;
- source-sink projection and conservative two-dye transport cannot remove
  protected candidates;
- flow may allocate bounded compute/attention but not directly score the final
  grounded action;
- capacity and normalization identity changes invalidate calibration;
- all existing conservation, CFL, staleness, and packet checks remain active.

Acceptance criteria:

- incremental held-out value over the best CT1–CT4 comparator after
  controller-inclusive latency;
- positive paired engine pilot direction without safety or terminal delay;
- only then freeze a seed-disjoint confirmatory cohort.

## 3. Evaluation sequence

Each stage follows the same sequence:

1. semantic and invariant unit tests;
2. deterministic captured-snapshot replay;
3. held-out transition/recall evaluation;
4. claim-ineligible, seed-matched engine diagnostic;
5. claim-ineligible pilot only after the diagnostic passes;
6. power calculation and frozen, seed-disjoint confirmation only after a
   positive pilot.

The primary gameplay endpoint remains paired player score at the fixed
horizon. Secondary diagnostics include settlement completion, goal-relief
error, candidate recall, terminal delay, action rejection, no-effect rate,
oscillation/switch rate, controller latency, and absolute safety failures.

## 4. Stop rules

Stop and simplify when any of the following occurs:

- the calibrated model cannot obtain sufficient exact category/lifecycle
  support without leakage or uncontrolled off-policy assumptions;
- candidate recall does not improve beyond the next simpler protected union;
- a stage worsens terminal completion or an absolute safety gate;
- a stage adds material latency without held-out or engine direction;
- a fresh confirmatory primary endpoint fails.

On a stop, retain diagnostics and replay support, revoke decision authority,
and keep the best simpler controller as the supported baseline.

## 5. Deliverables

- typed transition-value observation, model, estimate, and frozen snapshot;
- outcome plumbing from authoritative planner relief to the model;
- confidence-aware scalar fallback and complete telemetry;
- protected deterministic bridge union;
- corrected-probe union ablation;
- bounded path-persistence comparator;
- source-sink entry gate rather than automatic activation;
- tests, captured replays, evaluator reports, events, observability coverage,
  and a results/status document recording positive and negative findings.
