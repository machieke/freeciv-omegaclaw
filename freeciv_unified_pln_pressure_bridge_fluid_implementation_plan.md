# Unified PF-PLN Implementation Plan for FreeCiv OmegaClaw

## Pressure, Value, Bridge, and Resource Flow

**Target repository:** `machieke/freeciv-omegaclaw`
**Target branch:** `experimental/pln-pressure`
**Reviewed snapshot:** commit `9b1c2c8ec071a3d1db18f67a8e5c8b709737c46e`
**Plan date:** 2026-07-29
**Document status:** implementation plan, design-gated
**Primary theory source:** *Pressure, Value, and Flow: A Unified Theory and Architecture for Goal-Directed Inference Control* (July 2026)
**Existing PF-PLN source:** *Pressure-Field Probabilistic Logic Networks: A Unified Formalism for Uncertain Inference, Goal-Directed Attention, Lifecycle Dynamics, and Resource-Bounded Action*
**Code-review scope:** the pressure package, PF runtime declaration, PF integration document, pressure test suite, and grounded FreeCiv impact-planner integration at the reviewed snapshot.

**Reading note:** code fragments are interface sketches. Their syntax should be adapted to the repository's supported Python version and style without weakening the stated contracts.




## Contents

- [1. Executive decision](#1-executive-decision)
- [2. Scope](#2-scope)
- [3. Source-of-truth hierarchy](#3-source-of-truth-hierarchy)
- [4. Terminology and runtime types](#4-terminology-and-runtime-types)
- [5. Current implementation inventory](#5-current-implementation-inventory)
- [6. Target architecture](#6-target-architecture)
- [7. Normative invariants](#7-normative-invariants)
- [8. Delivery strategy and gates](#8-delivery-strategy-and-gates)
- [9. Stage S0 - Freeze the current scalar baseline](#9-stage-s0-freeze-the-current-scalar-baseline)
- [10. Stage S1 - Scalar PF-v2 semantic repairs](#10-stage-s1-scalar-pf-v2-semantic-repairs)
- [11. Stage S2 - Explicit teleology and selected component-live integration](#11-stage-s2-explicit-teleology-and-selected-component-live-integration)
- [12. Stage S3 - Explicit bridge geometry and the conductance-equivalence experiment](#12-stage-s3-explicit-bridge-geometry-and-the-conductance-equivalence-experiment)
- [13. Stage S4 - Python source-sink flow and conservative attention transport](#13-stage-s4-python-source-sink-flow-and-conservative-attention-transport)
- [14. Stage S5 - Live FreeCiv integration](#14-stage-s5-live-freeciv-integration)
- [15. Stage S6 - Conditional native, MORK, and CeTTa acceleration](#15-stage-s6-conditional-native-mork-and-cetta-acceleration)
- [16. Proposed repository layout](#16-proposed-repository-layout)
- [17. Detailed data and API contracts](#17-detailed-data-and-api-contracts)
- [18. File-by-file change map](#18-file-by-file-change-map)
- [19. Event, telemetry, and explanation plan](#19-event-telemetry-and-explanation-plan)
- [20. Comprehensive test plan](#20-comprehensive-test-plan)
- [21. Benchmark and experimental protocol](#21-benchmark-and-experimental-protocol)
- [22. Migration, compatibility, and rollout](#22-migration-compatibility-and-rollout)
- [23. Risk register](#23-risk-register)
- [24. Pull-request and issue sequence](#24-pull-request-and-issue-sequence)
- [25. Definition of done](#25-definition-of-done)
- [26. First vertical slice](#26-first-vertical-slice)
- [27. Appendix A - Reference unified controller pseudocode](#27-appendix-a-reference-unified-controller-pseudocode)
- [28. Appendix B - Example controller configuration](#28-appendix-b-example-controller-configuration)
- [29. Appendix C - Coding-agent work order template](#29-appendix-c-coding-agent-work-order-template)
- [30. Appendix D - Review checklist](#30-appendix-d-review-checklist)
- [31. Appendix E - Anti-patterns](#31-appendix-e-anti-patterns)
- [32. Appendix F - Source basis and interpretation boundaries](#32-appendix-f-source-basis-and-interpretation-boundaries)
- [33. Final implementation decision](#33-final-implementation-decision)

---

## 1. Executive decision

The current branch should be treated as a **valuable scalar PF-PLN baseline**, not discarded or rewritten wholesale. It already has several properties that the unified theory requires:

- truth and control are type-separated;
- pressure remains goal-indexed until scheduling;
- infer, observe, act, expand, and retain are distinct channels;
- associative or diagnostic routes cannot authorize external action;
- safety goals can veto harmful operations;
- route conductance is learned from grounded outcomes without changing truth;
- deterministic traces and structural hashes support replay;
- the live adapter operates only over authoritative snapshots and server-advertised legal candidates;
- component acceptance is explicitly distinguished from engine-live activation.

The branch does **not** yet implement the complete pressure-value-bridge-flow controller. The most important missing or incorrect semantics are:

1. `TruthState.supported_strength = strength * confidence` is used as if it were achieved state. This conflates **state deficit** with **epistemic uncertainty**.
2. `GoalState.risk_sensitivity` is declared but does not affect scheduler priority.
3. `PressureVector.plus()` is order-dependent when equally strong opposing directions are combined.
4. AND-rule demand is divided among premises without retaining full demand on the prerequisite coalition.
5. `PressureScheduler.allocate()` returns fractional scalar shares, while inference, observations, simulations, LLM calls, and external actions require whole typed operation packets.
6. Cost-to-go, local leverage, and typed expected relief are not represented as distinct first-class objects.
7. There is no explicit forward reachability factor, backward usefulness factor, bridge height, probe estimator, effective-sample-size diagnostic, or single-use correlated-signal contract.
8. There is no query-local resource-flow graph, source-sink accounting, capacity provenance, congestion dual, conservative advection, or two-dye overlap.
9. Several accepted components remain component-only rather than engine-live: provenance/contradiction, observation/simulation pressure, lifecycle clones, induction/analogy, the LLM gateway, and differentiable execution.

The implementation strategy is therefore:

> **Repair the scalar semantics first, make discrete execution real, expose Bellman-style teleological objects, test whether an explicit bridge adds information beyond conductance, and implement fluid transport only if it beats a strong scalar baseline after controller overhead.**

This plan deliberately preserves a safe fallback ladder:

1. unified PF + bridge + source-sink flow + packet scheduler;
2. PF + bridge + packet scheduler, without advection;
3. scalar PF-v2 + packet scheduler;
4. existing scalar PF-v1 compatibility mode;
5. canonical Impact planner without PF control.

A failed bridge estimator or flow solver must reduce optimization quality, never logical or action correctness.

---

## 2. Scope

### 2.1 In scope

This plan covers:

- semantic corrections to the existing scalar PF-PLN implementation;
- first-class goal loss, cost-to-go, leverage, expected relief, and risk;
- coalition-aware AND semantics;
- integer typed resource packets and reservations;
- live integration of currently component-only PF capabilities where supported by authoritative FreeCiv data;
- an explicit bridge estimator and a falsifiable conductance-versus-bridge experiment;
- cheap forward/backward probes with behavior/reference separation;
- a Python reference implementation of query-local source-sink flow;
- conservative forward/backward attention transport;
- operation readout, exact revalidation, and safe commitment;
- event schemas, telemetry, deterministic replay, and visual diagnostics;
- staged FreeCiv integration and controller-inclusive benchmarks;
- optional native or CeTTa/MORK-oriented acceleration only after scientific gates pass.

### 2.2 Non-goals

The first implementation cycle will not:

- replace the authoritative FreeCiv state bridge, legal-action enumeration, execution gate, or engine;
- permit pressure, bridge estimates, probes, currents, or flow mass to modify truth confidence;
- treat LLM proposals as evidence;
- materialize every possible prerequisite coalition;
- implement a global incompressible flow over the bare semantic proof graph;
- freeze a C ABI before the Python reference and scale contract are stable;
- pursue GPU acceleration before the algorithm beats a tuned scalar baseline;
- claim gameplay score improvement from synthetic control-path success;
- enable all component-only phases merely because their standalone tests pass;
- maximize PLN expressiveness at the expense of the project’s actual objective: efficient global control and multi-path aggregation in OmegaClaw.

---

## 3. Source-of-truth hierarchy

Implementation and review decisions should use the following authority order:

1. **Authoritative FreeCiv state and legal-action protocol.** This determines what is currently true, legal, and executable.
2. **Verified evidence and committed rule applications.** These determine epistemic state.
3. **Typed PF-PLN semantics and invariants.** These determine how goal relevance is calculated and transported.
4. **Bridge and flow state.** These determine where scarce compute is routed.
5. **Learned conductance, motif, and value predictors.** These are calibrated control aids, never epistemic authority.
6. **LLM-generated structure.** This remains quarantined until verified.

When sources disagree, higher levels prevail. A high-flow route to a stale or illegal action is rejected. A high-pressure LLM proposal that lacks evidence stays a proposal. A learned conductance route that contradicts current authoritative state is invalidated or context-split.

---

## 4. Terminology and runtime types

The implementation must stop using one overloaded term for several different quantities.

| Concept | Recommended type | Meaning | May alter truth? |
|---|---|---|---:|
| Epistemic state | `TruthState` / `EvidenceState` | Strength, uncertainty, evidence, provenance | Only through verified epistemic operations |
| Goal loss | `GoalLoss` | Current or expected undesirability under one goal | No |
| Cost-to-go | `CostToGoEstimate` | Expected remaining goal loss under an admissible policy | No |
| Teleological leverage | `LeverageEstimate` | Marginal or counterfactual effect of changing a state coordinate | No |
| Typed expected relief | `TypedAdvantage` | Expected reduction in cost-to-go from infer/observe/act/expand/retain | No |
| Dependency demand | `DependencyDemand` | Backward request placed on an atom, factor, or requirement set | No |
| Operational eligibility | `OperationEligibility` | Continuous readiness for a concrete operation | No |
| Bridge state | `PotentialEstimate` | Forward reachability and backward usefulness | No |
| Requested current | `RequestedCurrent` | Desired direction and rate of resource motion | No |
| Feasible current | `FeasibleCurrent` | Resource motion after balance and capacity constraints | No |
| Congestion pressure | `CongestionDual` | Dual price of enforcing resource feasibility | No |
| Attention mass | `AttentionMass` | Accounted compute/sensing/action resource | No |
| Packet reservation | `PacketReservation` | Integer resource commitment toward a discrete operation | No |
| Verified commitment | existing plan/execution artifacts | Actual inference, observation, graph edit, or external action | Yes, through existing verified paths only |

### 4.1 Required naming rule

No public field named only `pressure` may be introduced unless its exact kind is encoded by its type and serialized schema. Existing `PressureVector` remains supported during migration, but new code should distinguish:

- `dependency_demand`;
- `typed_advantage`;
- `requested_current`;
- `congestion_dual`;
- `scheduled_packets`.

### 4.2 One graph, several legal transition sets

The same semantic region may support several distinct transitions:

- forward truth dependency;
- backward teleological dependency;
- legal forward probe transition;
- legal backward probe transition;
- causal planning transition;
- associative or similarity transition;
- operation invocation;
- lifecycle transition;
- graph expansion;
- resource return or accounting.

These must be separate edge kinds. In particular, resource-return edges may carry budget but may never be traversed as implications or included in evidence ancestry.

---

## 5. Current implementation inventory

### 5.1 Existing modules to preserve

| Existing module | Current role | Plan |
|---|---|---|
| `pressure/model.py` | Immutable truth views, goals, pressure vectors, rules, operations, costs, config | Retain; add versioned v2 semantic types and compatibility adapters |
| `pressure/engine.py` | Deterministic reverse demand transport, route and premise shares, action-route gating | Retain as scalar baseline; refactor into factor-level and coalition-aware transport |
| `pressure/scheduler.py` | Multi-goal score, safety firewall, cost scalarization, fractional allocation | Retain score compatibility; add risk-aware packet scheduler and deprecate fractional commitment |
| `pressure/adapters.py` | Proof-DAG and grounded Impact adapter | Retain; migrate to structured demand, risk, packets, bridge inputs, and v2 artifacts |
| `pressure/learning.py` | Persistent grounded conductance credit | Retain; add context/frontier conditioning, uncertainty, and bridge-ablation features |
| `pressure/provenance.py` | Evidence tokens, overlap, conflict, observation policy | Retain; make live selection-propensity and coverage outputs available to the controller |
| `pressure/observation.py` | Bounded one-step value of information | Retain; integrate into shared packet and risk scheduler |
| `pressure/lifecycle.py` | Clone posterior, split/merge, visible truth/pressure | Retain; support versioned data-driven lifecycle schemas and live flow views |
| `pressure/induction.py` | Pattern, analogy, expansion proposal, replay gate | Retain; expose as `expand` operations with packets and quarantine |
| `pressure/differentiable.py` | Smooth adjoint/counterfactual/requirement operators | Retain; plug into a composite reverse-operator interface |
| `pf_runtime.py` | Machine-readable phase support and activation | Extend with controller-layer versioning without erasing historical phase claims |
| `planning/impact.py` | Live legal candidate generation and PF ranking integration | Keep authoritative; integrate through a narrow, versioned controller adapter |
| `Autotests/test_freeciv_pressure.py` | Broad acceptance coverage | Preserve; split new v2, bridge, and flow tests into focused files |

### 5.2 Existing behavior that becomes the scalar baseline

The current scalar baseline is approximately:

```text
goal truth gap × utility × urgency × commitment
  -> damped reverse rule transport
  -> conductance × compatibility × residual
  -> route share and premise share
  -> channel resolvability
  -> expected relief / scalarized cost
  -> safety and causal firewalls
  -> selected legal Impact candidate
  -> unchanged execution gate
```

This baseline must remain runnable and benchmarked throughout the project. Every new layer must prove incremental value against it and against a stronger smoothed scalar baseline with route momentum and hysteresis.

### 5.3 Current defects to encode as failing tests before repair

The first implementation PR should add explicit regression tests for:

- low confidence causing observation/inference demand without automatically causing equivalent action demand;
- goal risk sensitivity changing risky-operation priority monotonically;
- pressure addition being commutative and associative within numerical tolerance;
- AND-rule coalition demand remaining stable as premise count grows;
- a rule firing or action requiring complete typed packets;
- a useful-but-unreachable bridge node receiving low final eligibility;
- a reachable-but-irrelevant node receiving low final eligibility;
- virtual resource edges being rejected by proof and causal traversal;
- controller artifacts never mutating truth or evidence.

The tests should initially fail under v2 mode and pass under explicit v1 compatibility assertions where historical behavior is intended.

---

## 6. Target architecture

```text
Authoritative snapshot + verified evidence + active goals
                         |
                         v
        +-------------------------------------+
        | Epistemic control plane             |
        | truth, evidence, provenance,        |
        | contexts, clones, legal rules       |
        +-------------------------------------+
                         |
                         v
        +-------------------------------------+
        | Teleological layer                  |
        | GoalLoss, CostToGo, Leverage,       |
        | TypedAdvantage, RequirementSet      |
        +-------------------------------------+
                         |
                         v
        +-------------------------------------+
        | Bridge layer                        |
        | forward f, backward g, H=log f+log g|
        | corrected/holdout probes, ESS       |
        +-------------------------------------+
                         |
                         v
        +-------------------------------------+
        | Resource layer                      |
        | requested current, projection,      |
        | capacities, congestion duals,       |
        | forward/backward attention mass     |
        +-------------------------------------+
                         |
                         v
        +-------------------------------------+
        | Packet scheduler                    |
        | whole typed operation packets,      |
        | reservations, coalition gates       |
        +-------------------------------------+
                         |
                         v
        +-------------------------------------+
        | Exact revalidation and commitment   |
        | current IDs, legal bindings, safety,|
        | provenance, resource preconditions  |
        +-------------------------------------+
                         |
                         v
         Existing plan and FreeCiv execution gate
                         |
                         v
          realized outcome, relief, cost, calibration
```

### 6.1 Two nested loops

**Semantic loop**

1. ingest authoritative and evidence events;
2. revise truth and provenance;
3. update goals and cost-to-go approximations;
4. materialize or retire semantic factors and operation candidates;
5. propagate teleological messages;
6. enumerate concrete typed operations;
7. revalidate and commit selected operations;
8. measure realized relief and update calibrated control models.

**Resource loop**

1. update forward and backward factors;
2. emit cheap probes;
3. update corrected bridge estimates;
4. deposit path currents;
5. build normalized requested currents;
6. solve balance and capacity constraints;
7. advect attention mass;
8. accumulate packet reservations at operation gates;
9. emit a bounded candidate set to the semantic loop.

The resource loop may run several microsteps per semantic commitment. It may be approximate or boundedly stale. The commitment path may not be stale.

---

## 7. Normative invariants

Every work package and code review must preserve the following invariants.

### I-01. Epistemic firewall

Pressure, utility, bridge factors, probe success, flow mass, congestion duals, and scheduler scores may select an epistemic operation. They may not directly alter a truth value or evidence weight.

### I-02. Typed identity

Propositions, rule factors, requirement sets, operations, lifecycle states, boundaries, reservoirs, frontier stubs, and shard portals are distinct runtime types.

### I-03. Legal-transition separation

Forward truth, backward demand, causal planning, probes, associative similarity, operation invocation, and resource return have independent legality flags.

### I-04. Per-goal traceability

Goal-conditioned demand remains attributable to its source goal until an explicit shared-capacity or packet-allocation decision. Aggregation retains enough data to explain each goal’s contribution.

### I-05. State deficit is not confidence deficit

Action pressure is driven by estimated need to change the world. Observation and inference pressure are driven by decision-relevant uncertainty. Low confidence alone does not imply that the world should be changed.

### I-06. Smooth risk, explicit commitment gates

Risk estimation is continuous and distribution-sensitive. Hard thresholds are policy and commitment boundaries, especially for safety-class or irreversible actions.

### I-07. Coalition integrity

An AND factor retains full demand at a `RequirementSet`. Premise-level shares allocate supporting effort but do not imply that partial satisfaction has completed the rule.

### I-08. Discrete execution

Truth-bearing or externally effective operations consume whole typed packets and satisfy their threshold. Fractional eligibility mass cannot be interpreted as partial proof, observation, simulation, LLM call, or action.

### I-09. Resource accounting

For each resource commodity, active mass plus reservations plus in-flight mass plus reservoir mass equals the declared budget to tolerance, except at explicit source, sink, stimulus, conversion, or forgetting events.

### I-10. Capacity provenance

Measured physical capacities, policy allocations, and shaping regularizers are separate types. Only measured-capacity duals may automatically justify structural optimization such as caching, compilation, replication, or additional workers.

### I-11. Single-use bridge signals

Bridge height may steer probes and current construction. Transport overlap may select locations. Typed PF advantage may score concrete operations. Correlated raw signals are not multiplied together again unless a held-out residual model proves incremental value.

### I-12. Selection propensity

Every active evidence-acquisition operation records its selection propensity or an explicit deterministic-policy reason. Coverage and audit-observation diagnostics remain available.

### I-13. Commit freshness

Every durable inference, graph mutation, observation, LLM-derived rule acceptance, or external action is revalidated against the current semantic epoch and authoritative state.

### I-14. Fallback correctness

An invalid bridge estimator, nonconverged flow solve, stale topology generation, failed numerical guard, or missing optional dependency must fall back to a simpler safe controller.

### I-15. Deterministic replay

Given fixed semantic input, config, seed, patch sequence, precision policy, and worker count, the controller supports deterministic or explicitly bounded-nondeterministic replay.

### I-16. Scientific gate discipline

Native infrastructure and production claims are not allowed to outrun ablation evidence. Negative results lead to simplification, not infrastructure escalation.

---

## 8. Delivery strategy and gates

The project is divided into seven implementation stages and five scientific go/no-go gates, followed by separate live-release and native-performance gates.

| Stage | Result | Gate |
|---|---|---|
| S0 | Freeze and reproduce current scalar baseline | G0: baseline reproducibility |
| S1 | Scalar PF-v2 semantic repairs and packet execution | G1: semantic correctness |
| S2 | Explicit teleology and selected component-live integration | G2: calibration and live parity |
| S3 | Bridge estimator and conductance-equivalence experiment | G3: bridge incremental value |
| S4 | Python source-sink flow and conservative transport | G4: flow earns overhead |
| S5 | Live FreeCiv bridge/flow integration | release safety and replay gate |
| S6 | Optional native/CeTTa/MORK acceleration | performance gate only |

The critical policy is:

> If G3 fails, retain scalar PF-v2 and packet scheduling and do not force an independent bridge layer. If G4 fails, retain bridge scoring with a scalar packet scheduler and do not build native fluid infrastructure.

---

## 9. Stage S0 - Freeze the current scalar baseline

### 9.1 Objective

Create a reproducible control and benchmark snapshot before changing semantics. The current scalar engine is both a production fallback and the primary scientific baseline.

### 9.2 Work package S0.1 - Snapshot identity

Add a generated baseline manifest containing:

```yaml
repository: machieke/freeciv-omegaclaw
branch: experimental/pln-pressure
commit: 9b1c2c8ec071a3d1db18f67a8e5c8b709737c46e
pf_runtime_schema: "1.0"
live_adapter: grounded-impact-planner/1.33
pressure_solver: pf-pln-pressure-scheduler/1.0
python_version: ...
platform_profile: ...
fixture_hashes: ...
```

Recommended file:

`benchmarks/freeciv/pf_unified/baseline_manifest.yaml`

The benchmark runner must refuse to compare results when source, fixtures, ruleset, or solver identity differs without an explicit cross-version flag.

### 9.3 Work package S0.2 - Golden artifacts

Capture golden outputs for:

- `_capital_graph()` pressure propagation;
- the 256-decoy pressure-concentration fixture;
- proof-DAG conversion;
- observation versus action scheduling;
- multi-goal Impact ranking on the byte-exact snapshot replay fixture;
- conductance update and replay;
- the current runtime activation matrix;
- current event validation and structural hashes.

Store golden artifacts under:

```text
benchmarks/freeciv/pf_unified/golden/v1/
```

Each artifact should include the source commit, config hash, fixture hash, random seed, and whether it is a semantic or performance artifact.

### 9.4 Work package S0.3 - Strong scalar baseline

The unified theory requires comparison against more than the existing memoryless softmax allocation. Implement a separate baseline controller without changing live behavior:

```python
class SmoothedScalarController:
    """Strong cheap baseline for bridge and flow ablations."""

    def update_route_score(
        self,
        route_id: str,
        instantaneous_score: float,
        route_momentum: float,
        dwell_bonus: float,
        diversity_floor: float,
    ) -> float:
        ...
```

It should support:

- exponential score smoothing;
- route-level momentum;
- minimum dwell time or hysteresis;
- a backup-route diversity floor;
- the same PF advantages and bridge estimates that later controllers receive;
- the same integer packet scheduler used by PF-v2.

Recommended file:

`src/freeciv_agent/pressure/scalar_baseline.py`

This controller is not necessarily a live default. It is the baseline that flow must beat.

### 9.5 Gate G0 - Baseline reproducibility

Proceed only when:

- current unit and integration tests pass unchanged;
- v1 artifacts reproduce byte-for-byte where deterministic;
- replay tools reproduce selected operations and hashes;
- controller-inclusive timing is measured;
- the strong scalar baseline has its own golden traces;
- no new type or event name is introduced without a schema version.

---

## 10. Stage S1 - Scalar PF-v2 semantic repairs

Stage S1 fixes the known semantic defects before introducing bridge or flow complexity.

### 10.1 Work package S1.1 - Split state deficit from epistemic uncertainty

#### Problem

The current engine computes premise unmetness as:

```python
1.0 - atom.truth.supported_strength
```

where `supported_strength = strength * confidence`. This makes low confidence look like low world-state attainment. As a result, uncertainty can propagate into action pressure even when the proposition is likely already true.

#### Target model

Introduce explicit state and epistemic quantities:

```python
@dataclass(frozen=True)
class TruthAssessment:
    strength: float
    confidence: float
    posterior_variance: float | None = None

    def signed_state_gap(self, target_strength: float) -> float:
        return target_strength - self.strength

    def achievement_deficit(self, target_strength: float) -> float:
        return abs(self.signed_state_gap(target_strength))

    def epistemic_uncertainty(self) -> float:
        if self.posterior_variance is not None:
            return self.posterior_variance
        return 1.0 - self.confidence
```

Keep `TruthState.supported_strength` for compatibility and display, but prohibit v2 control code from using it as an achievement measure.

Introduce:

```python
@dataclass(frozen=True)
class GoalDemand:
    achievement: float
    epistemic: float
    deadline: float
    safety: float
    direction: float
    source_goal_id: str
```

Recommended default decomposition:

```text
achievement demand = utility × urgency × commitment × |target - strength|
epistemic demand   = decision sensitivity × uncertainty
deadline demand    = urgency transform derived from remaining slack
safety demand      = tail-risk or constraint deficit for safety goals
```

#### Channel routing

Use the following default mapping:

| Demand component | infer | observe | act | expand | retain |
|---|---:|---:|---:|---:|---:|
| achievement deficit | conditional | conditional | primary | conditional | low |
| epistemic uncertainty | primary | primary | only through precaution policy | conditional | low |
| missing representation | low | low | none | primary | conditional |
| expected future reuse | low | low | none | low | primary |

The actual magnitude remains modulated by `Resolvability` and rule semantics.

#### Files

- modify `pressure/model.py`;
- modify `pressure/engine.py`;
- modify `pressure/adapters.py`;
- update `pressure/observation.py` to return decision-relevant uncertainty;
- add `Autotests/test_freeciv_pressure_v2.py`.

#### Required tests

```text
test_equal_strength_different_confidence_has_equal_action_deficit
test_low_confidence_increases_observation_pressure
test_low_confidence_does_not_automatically_increase_action_pressure
test_precautionary_action_requires_explicit_risk_policy
test_supported_strength_is_not_used_as_v2_achievement_deficit
```

#### Acceptance

- action priority is invariant to confidence when strength, risk, and all action-relevant facts are fixed;
- observation or inference priority rises with decision-relevant uncertainty;
- v1 compatibility mode reproduces historical behavior;
- serialized artifacts distinguish `achievement_demand` and `epistemic_demand`.

---

### 10.2 Work package S1.2 - Replace scalar direction with commutative signed channel pressure

#### Problem

`PressureVector.plus()` selects the direction of the operand with larger total pressure and retains the left operand’s direction on a tie. Aggregation is therefore order-dependent and loses opposing demand.

#### Target model

Use positive and negative mass per channel:

```python
@dataclass(frozen=True)
class PressureMagnitude:
    infer: float = 0.0
    observe: float = 0.0
    act: float = 0.0
    expand: float = 0.0
    retain: float = 0.0

@dataclass(frozen=True)
class SignedPressureVector:
    positive: PressureMagnitude = PressureMagnitude()
    negative: PressureMagnitude = PressureMagnitude()

    def plus(self, other: "SignedPressureVector") -> "SignedPressureVector":
        return SignedPressureVector(
            positive=self.positive.plus(other.positive),
            negative=self.negative.plus(other.negative),
        )

    def net(self, channel: str) -> float:
        return self.positive.value(channel) - self.negative.value(channel)

    def conflict(self, channel: str) -> float:
        return min(
            self.positive.value(channel),
            self.negative.value(channel),
        )
```

The representation preserves:

- net direction;
- total contested demand;
- exact commutativity;
- the ability to report goal conflict rather than silently choosing one direction.

#### Compatibility

Provide:

```python
PressureVector.from_signed(...)
SignedPressureVector.from_v1(...)
```

Do not silently change old artifact hashes. Version them.

#### Files

- modify `pressure/model.py`;
- modify `pressure/engine.py`;
- modify `pressure/lifecycle.py` clone pressure serialization;
- modify `pressure/scheduler.py` conflict handling;
- modify `pressure/__init__.py` exports.

#### Required tests

```text
test_signed_pressure_addition_is_commutative
test_signed_pressure_addition_is_associative
test_equal_opposing_pressure_preserves_conflict_mass
test_clone_pressure_projection_preserves_signed_channels
test_v1_pressure_artifact_round_trip_is_explicitly_versioned
```

#### Acceptance

- aggregation order cannot change selected operation under fixed tie-breaking;
- safety conflicts are visible by channel and goal;
- no global scalar `direction` is required by v2 code.

---

### 10.3 Work package S1.3 - Implement goal-specific risk semantics

#### Problem

`GoalState.risk_sensitivity` is validated but not used. `CostVector.risk` is currently one scalar cost component with global weights. This cannot express a risk-neutral score goal and a risk-averse survival goal evaluating the same operation differently.

#### Target types

```python
@dataclass(frozen=True)
class RiskProfile:
    aversion: float = 0.0
    tail_alpha: float = 0.10
    max_expected_loss: float | None = None
    max_tail_loss: float | None = None
    hard_gate: bool = False
    hysteresis_enter: float | None = None
    hysteresis_exit: float | None = None

@dataclass(frozen=True)
class RiskEstimate:
    expected_loss: float
    variance: float
    upper_quantile: float
    cvar: float
    confidence: float
    provenance: tuple[str, ...] = ()
```

`GoalState.risk_sensitivity` may remain as a compatibility alias for `RiskProfile.aversion` during migration.

#### Scheduler semantics

For goal `j` and operation `o`:

```text
risk-adjusted value_j(o)
  = expected_relief_j(o)
  - risk_aversion_j × tail_risk_j(o)
```

A recommended default is:

```text
tail_risk = CVaR_alpha(loss) when a loss distribution is available
          = expected_loss + uncertainty_premium otherwise
```

Use smooth penalties during deliberation. Apply hard gates only when:

- a safety-class goal declares a maximum tail loss;
- an operation is irreversible or externally consequential;
- a policy contract requires a threshold;
- an existing FreeCiv safety gate is stricter.

Use hysteresis for persistent plans:

```text
adopt below R_enter; retain until risk rises above R_exit
```

#### Risk is not confidence

Confidence affects uncertainty in the loss estimate. It is not itself the loss. The pipeline is:

```text
truth uncertainty -> outcome distribution uncertainty
                  -> risk distribution
                  -> smooth priority penalty
                  -> optional hard commitment gate
```

#### Files

- add `pressure/risk.py`;
- modify `pressure/model.py` operation and goal types;
- modify `pressure/scheduler.py`;
- modify `pressure/adapters.py` to derive FreeCiv operation risk from authoritative candidate projections;
- update event serialization and tests.

#### Required tests

```text
test_goal_risk_sensitivity_monotonically_penalizes_risky_operation
test_same_operation_has_different_risk_value_for_survival_and_score_goals
test_low_confidence_widens_risk_without_becoming_harm_probability
test_safety_tail_risk_hard_vetoes_commitment
test_reversible_low_cost_operation_uses_soft_risk_gate
test_plan_risk_hysteresis_prevents_threshold_chatter
```

#### Acceptance

- changing only `risk_sensitivity` changes risky-operation priority;
- risk traces identify mean loss, tail loss, confidence, provenance, and gate reason;
- safety firewalls remain lexicographically dominant;
- risk is never added to truth strength or confidence.

---

### 10.4 Work package S1.4 - Make deadline semantics executable

#### Problem

`GoalState.deadline` exists, but most live behavior is encoded through adapter-specific `deadline_fit`. The model should distinguish goal deadline, predicted completion time, slack, and deadline miss risk.

#### Target types

```python
@dataclass(frozen=True)
class DeadlineState:
    current_turn: int
    deadline_turn: int | None
    expected_completion_turn: float | None
    completion_variance: float = 0.0

    @property
    def slack(self) -> float | None:
        ...
```

Define `DeadlineFit` as a calibrated estimate, not just a Boolean unless the candidate is known to complete after the horizon.

Recommended semantics:

```text
deadline_fit = P(completion <= deadline)
urgency      = bounded monotonic function of negative slack and goal importance
```

Keep the current hard rejection for projections explicitly known to finish after the configured horizon. Use probabilistic fit only when completion is uncertain.

#### Files

- add `pressure/time.py` or place types in `teleology.py`;
- modify `GoalState`, `Operation`, and adapter serialization;
- update `ImpactPressureRanker._deadline_fit()` to return a structured estimate in v2 mode.

#### Acceptance

- `deadline` is either used by the controller or explicitly absent;
- urgency and deadline fit are not double-counted;
- traces show predicted completion, slack, and hard/soft gate status.

---

### 10.5 Work package S1.5 - Add coalition-aware AND semantics

#### Problem

The current `_premise_shares()` conserves parent demand by normalizing it across premises. This is a reasonable attention split, but it loses the semantic fact that all prerequisites may be required. As arity grows, each necessary premise receives less pressure even though the coalition remains fully blocking.

#### Target representation

```python
@dataclass(frozen=True)
class RequirementSet:
    requirement_set_id: str
    rule_id: str
    premise_ids: tuple[str, ...]
    role_ids: tuple[str, ...]
    context_digest: str
    completion_policy: str = "all"
    packet_thresholds: tuple[tuple[str, int], ...] = ()
```

The reverse operator becomes:

```text
parent demand
  -> full demand on rule factor / RequirementSet
  -> supporting allocation among premises
  -> completion only when the requirement vector is satisfied
```

Premise allocation may use:

- blocker criticality;
- temporal critical path;
- positive marginal relief;
- bounded sampled Shapley approximation;
- declared role weights;
- uniform fallback.

The power set must never be enumerated. A coalition is materialized only when:

- a rule explicitly declares all-premise completion;
- single-premise marginal value is insufficient;
- a threshold or lifecycle transition requires coordinated state;
- an experiment or trace shows repeated partial-allocation starvation.

#### Engine changes

Split factor-level demand from premise support:

```python
@dataclass(frozen=True)
class FactorDemand:
    goal_id: str
    factor_id: str
    amount: float
    residual: float
    conductance: float
    compatibility: float

@dataclass(frozen=True)
class PremiseSupportRequest:
    requirement_set_id: str
    premise_id: str
    share: float
    requested_amount: float
```

The `PressureResult` should expose both.

#### Files

- add `pressure/coalitions.py`;
- modify `pressure/model.py`, `engine.py`, `scheduler.py`, and `adapters.py`;
- update proof-DAG conversion to preserve premise roles;
- add tests in `test_freeciv_pressure_v2.py` and `test_freeciv_packets.py`.

#### Required tests

```text
test_and_requirement_set_retains_full_parent_demand
test_and_total_coalition_demand_is_arity_invariant
test_premise_support_shares_sum_to_at_most_one
test_partial_and_completion_cannot_fire_rule
test_lazy_coalition_generation_never_enumerates_power_set
test_temporal_critical_path_gets_more_support_without_erasing_other_requirements
```

#### Acceptance

- an eight-premise AND does not look eight times less important than a one-premise dependency;
- no rule is committed from one funded prerequisite when all are required;
- traces explain coalition demand and premise allocation separately.

---

### 10.6 Work package S1.6 - Implement whole typed operation packets

#### Problem

`PressureScheduler.allocate()` currently distributes a floating-point budget by softmax. This is valid as continuous eligibility, but not as operation execution.

#### Resource types

Start with explicit commodities:

```python
class ResourceKind(str, Enum):
    CPU = "cpu"
    EXACT_RULE = "exact_rule"
    OBSERVATION = "observation"
    SIMULATION = "simulation"
    ACTION = "action"
    EXPANSION = "expansion"
    LLM_TOKEN = "llm_token"
    MEMORY = "memory"
```

The exact set can be configured, but packet identity must be explicit.

#### Core types

```python
@dataclass(frozen=True)
class PacketCost:
    resource: ResourceKind
    quanta: int

@dataclass(frozen=True)
class PacketBudget:
    resource: ResourceKind
    available: int

@dataclass(frozen=True)
class PacketReservation:
    operation_id: str
    costs: tuple[PacketCost, ...]
    reserved: tuple[PacketCost, ...]
    state: str  # pending, complete, returned, committed, expired

@dataclass(frozen=True)
class PacketSchedule:
    reservations: tuple[PacketReservation, ...]
    committed_operation_ids: tuple[str, ...]
    stranded_quanta: tuple[PacketCost, ...]
    integrality_gap: float
```

#### Scheduling algorithm

For the first implementation, use a deterministic bounded greedy or knapsack scheduler:

1. filter inadmissible operations;
2. compute risk-adjusted expected relief per resource packet;
3. apply lexicographic safety constraints;
4. prioritize operations that can complete with current packets;
5. reserve packets atomically across resource types;
6. respect RequirementSet completion gates;
7. keep a bounded backup-route reservation floor;
8. return expired or abandoned reservations;
9. log relaxed versus packet-feasible value.

Do not attempt a general integer program in the first live version. A small exact solver may be used in synthetic tests to measure regret.

#### OR semantics

An OR route should generally concentrate enough packets to complete one route rather than fractionalizing all alternatives. Preserve exploration with:

- one primary route;
- zero or one backup route under a diversity budget;
- route temperature or hysteresis;
- explicit reservation expiration.

#### Files

- add `pressure/packets.py`;
- modify `pressure/scheduler.py`;
- extend `Operation` with `packet_costs`, `packet_threshold`, and `reservation_policy`;
- modify `adapters.py`, `observation.py`, `induction.py`, and LLM gateway integration;
- add packet events and tests.

#### Required tests

```text
test_fractional_eligibility_cannot_commit_operation
test_multi_resource_operation_reserves_atomically
test_and_gate_requires_complete_prerequisite_packet_vector
test_or_routes_concentrate_packets_on_a_complete_candidate
test_abandoned_reservation_returns_packets
test_packet_accounting_is_conserved
test_packet_scheduler_is_deterministic
test_integrality_gap_is_reported
```

#### Acceptance

- every committed operation names the integer packets it consumed;
- continuous allocations remain diagnostic only;
- packet starvation and stranded budget are visible;
- the existing execution gate receives only complete, admissible operations.

---

### 10.7 Work package S1.7 - Version artifacts and runtime activation

Do not silently reinterpret v1 fields.

#### Artifact versions

Introduce:

```text
pressure_artifact_schema: 2.0
scheduler_identity: pf-pln-packet-scheduler/2.0
teleology_semantics: achievement-uncertainty-split/1.0
risk_semantics: distributional-risk/1.0
coalition_semantics: requirement-set/1.0
```

#### `pf_runtime.py`

Preserve historical phase declarations. Add a separate controller-layer declaration:

```python
CONTROLLER_LAYER_SPECS = (
    {"layer": "scalar_pf_v1", "support": "engine-live"},
    {"layer": "scalar_pf_v2", "support": "experimental"},
    {"layer": "packet_scheduler", "support": "experimental"},
    {"layer": "teleological_cost_to_go", "support": "component-only"},
    {"layer": "bridge", "support": "component-only"},
    {"layer": "source_sink_flow", "support": "component-only"},
    {"layer": "native_flowpack", "support": "not-built"},
)
```

Use a schema version that can still decode and validate v1 declarations. Old replay artifacts remain readable.

#### Feature flags

Recommended initial flags:

```yaml
impact_policy:
  pressure_enabled: true
  pressure_semantics_version: v1
  pressure_packet_scheduler_enabled: false
  pressure_distributional_risk_enabled: false
  pressure_requirement_sets_enabled: false
  pressure_bridge_enabled: false
  pressure_flow_enabled: false
  pressure_scalar_fallback_enabled: true
```

V2 features should be individually switchable for ablation, but invalid combinations must fail closed. For example, `pressure_flow_enabled` requires packet scheduling and a bridge policy.

---

### 10.8 Gate G1 - Scalar-v2 semantic correctness

Proceed to explicit cost-to-go and bridge work only when:

- all v1 tests pass under compatibility mode;
- all new v2 semantic tests pass;
- action demand is separated from confidence deficit;
- `risk_sensitivity` has a measured monotonic effect;
- pressure aggregation is commutative;
- AND coalition demand and completion are correct;
- no fractional operation commits;
- event and replay tools validate both v1 and v2 artifacts;
- controller overhead of scalar-v2 is reported;
- targeted FreeCiv snapshot replay shows no safety or legality regression.

---

## 11. Stage S2 - Explicit teleology and selected component-live integration

Stage S2 upgrades the repaired scalar controller from a truth-gap heuristic to an explicit, inspectable approximation of Bellman-style teleological control. It also connects the already implemented component-only modules to the same typed operation and packet interfaces. This stage still uses a scalar scheduler; there is no bridge or fluid transport yet.

### 11.1 Work package S2.1 - Introduce first-class teleological state

#### Objective

Represent the following as different artifacts rather than aliases of one pressure scalar:

- immediate goal loss;
- approximate cost-to-go;
- local signed leverage;
- typed pre-cost advantage;
- post-cost operation value;
- backward dependency demand;
- operation eligibility;
- scheduled packets.

#### New module

Add:

`src/freeciv_agent/pressure/teleology.py`

Recommended public types:

```python
@dataclass(frozen=True)
class GoalLoss:
    goal_id: str
    immediate_loss: float
    uncertainty_penalty: float
    deadline_penalty: float
    safety_penalty: float
    total: float
    semantics_version: str

@dataclass(frozen=True)
class CostToGoEstimate:
    goal_id: str
    expected_loss: float
    lower_bound: float
    upper_bound: float
    horizon: int | None
    estimator_id: str
    feature_digest: str
    calibrated: bool

@dataclass(frozen=True)
class LeverageEstimate:
    goal_id: str
    target_id: str
    signed_leverage: float
    method: str  # adjoint, requirement, counterfactual, information
    confidence: float
    assumptions: tuple[str, ...]

@dataclass(frozen=True)
class TypedAdvantage:
    goal_id: str
    target_id: str
    mode: str
    expected_relief: float
    relief_variance: float
    information_gain: float
    option_value: float
    predicted_latency: float
    predicted_resource_use: tuple[tuple[str, float], ...]
    estimator_id: str
```

`GoalLoss` and `CostToGoEstimate` use goal-loss units. `LeverageEstimate` uses loss per state unit. `TypedAdvantage` is predicted relief before operation cost. `OperationScore` remains the post-cost scheduling artifact.

#### Initial cost-to-go implementation

Do not start with reinforcement learning or a large learned value network. Implement a hierarchy of estimators:

1. **Exact terminal estimator** for goals whose terminal state and horizon are explicitly known.
2. **One-step model estimator** using the existing candidate projection and grounded effect model.
3. **Bounded dynamic-programming estimator** for small synthetic graphs and short FreeCiv horizons.
4. **Calibrated heuristic estimator** wrapping current category utilities, deadlines, and conductance.
5. **Fallback immediate-loss estimator** equivalent to scalar PF-v2.

Every estimate carries `estimator_id` and calibration status. The controller must never imply that a heuristic value is an exact Bellman solution.

#### Goal-loss contract

A default goal loss may be expressed as:

```text
L_j = utility_j × urgency_j × achievement_loss
      + uncertainty_weight_j × decision_relevant_uncertainty
      + deadline_penalty_j
      + safety_tail_penalty_j
```

Cross-goal normalization occurs only in the outer budget arbiter. One goal’s declared loss scale must not be silently compared with another goal’s scale inside rule propagation.

#### Files

- add `pressure/teleology.py`;
- modify `pressure/model.py` to carry estimator references rather than duplicating fields;
- modify `pressure/adapters.py` to construct `GoalLoss` and `CostToGoEstimate` artifacts;
- modify `pressure/scheduler.py` to consume `TypedAdvantage` where present;
- export new types from `pressure/__init__.py`;
- add `Autotests/test_freeciv_teleology.py`.

#### Required tests

```text
test_immediate_loss_and_cost_to_go_are_distinct_types
test_cost_to_go_fallback_matches_scalar_v2_ordering
test_typed_advantage_is_pre_cost
test_operation_score_applies_cost_exactly_once
test_cross_goal_loss_scales_are_not_silently_normalized_in_engine
test_uncalibrated_estimator_is_labeled_in_artifact
```

#### Acceptance

- traces can reconstruct the path `goal loss -> cost-to-go -> leverage -> typed advantage -> score -> packets`;
- no cost, urgency, or utility term is counted twice;
- the fallback estimator reproduces scalar-v2 selection on golden fixtures;
- all estimates declare their method and uncertainty.

---

### 11.2 Work package S2.2 - Add expected transition models

#### Objective

Make operation value depend on predicted post-operation state, not only a static relief scale.

#### Core interface

```python
@dataclass(frozen=True)
class PredictedOutcome:
    outcome_id: str
    probability: float
    next_truth_summaries: tuple
    next_goal_features: tuple
    resource_delta: tuple
    completion_turn: float | None
    adverse_loss: float
    provenance: tuple[str, ...]

@dataclass(frozen=True)
class ExpectedTransition:
    operation_id: str
    outcomes: tuple[PredictedOutcome, ...]
    residual_probability: float
    model_id: str
    calibration_group: str

    def expected_cost_to_go(self, goal_id: str) -> float:
        ...
```

The sum of modeled outcome probability may be less than one only when `residual_probability` explicitly represents unknown outcomes. Unknown mass receives a risk-aware fallback loss rather than disappearing.

#### FreeCiv source mapping

Use current grounded candidate data before adding new predictors:

- candidate `projection` fields;
- guaranteed-horizon score calculations;
- production completion estimates;
- route and movement consequences;
- local actor effect detection;
- candidate goal-relief measurements;
- known action preconditions and resource changes.

The initial implementation should wrap existing data instead of duplicating the large `GroundedImpactPlanner` domain model.

#### Model registry

Add a deterministic registry:

```python
class TransitionModelRegistry:
    def register(self, operation_kind: str, model: TransitionModel) -> None:
        ...

    def predict(self, snapshot, operation) -> ExpectedTransition:
        ...
```

Models should be small and category-specific. A missing model returns a conservative declared fallback; it must not fabricate precision.

#### Calibration

Log predicted and realized:

- success probability;
- completion turn;
- goal-loss relief;
- resource use;
- adverse loss;
- information gain.

Maintain reliability curves by operation category, horizon, context, and risk class.

#### Tests

```text
test_expected_transition_probabilities_and_residual_sum_to_one
test_unknown_outcome_mass_receives_conservative_loss
test_transition_model_does_not_mutate_snapshot
test_realized_outcome_calibrates_control_model_not_truth
test_missing_model_uses_declared_fallback
```

---

### 11.3 Work package S2.3 - Unify reverse operators behind a composite interface

#### Objective

Use the existing differentiable, requirement, counterfactual, and information-value machinery through one rule-local interface.

#### New module

Add:

`src/freeciv_agent/pressure/reverse_operators.py`

```python
class ReverseOperator(Protocol):
    operator_id: str

    def evaluate(
        self,
        rule: PressureRule,
        incoming: FactorDemand,
        graph: PressureGraph,
        context: ReverseContext,
    ) -> ReverseOperatorResult:
        ...

@dataclass(frozen=True)
class ReverseOperatorResult:
    premise_requests: tuple[PremiseSupportRequest, ...]
    rule_request: float
    requirement_sets: tuple[RequirementSet, ...]
    information_requests: tuple
    assumptions: tuple[str, ...]
    numerical_health: str
```

Provide operator implementations:

- `AdjointReverseOperator` using `differentiable.adjoint_pressure()` when smooth and valid;
- `RequirementReverseOperator` using symbolic requirement semantics;
- `CounterfactualReverseOperator` using achievable intervention changes;
- `InformationReverseOperator` using expected decision value of resolving uncertainty;
- `CompositeReverseOperator` with declared nonnegative mixture weights.

#### Selection rules

The mixture is not arbitrary. Use operator-family defaults:

| Rule situation | Primary operator | Secondary |
|---|---|---|
| smooth product AND or probabilistic OR | adjoint | counterfactual audit |
| hard AND or zero-gradient prerequisite | requirement | counterfactual |
| threshold or lifecycle transition | counterfactual/requirement | none |
| observation-dependent branch | information | counterfactual |
| alternative routes | counterfactual | requirement |
| graph expansion | information/option value | requirement |

A differentiable result must pass finite-difference or local consistency checks in test mode. When an operator is invalid or numerically unhealthy, the rule falls back to symbolic requirement semantics.

#### Double-counting protection

A composite operator returns one normalized premise request. The scheduler must not separately add adjoint, requirement, and counterfactual requests as independent evidence. The artifact retains component contributions for diagnosis.

#### Tests

```text
test_smooth_rule_uses_adjoint_when_audit_passes
test_dead_and_uses_requirement_not_zero_gradient
test_threshold_uses_counterfactual_or_requirement
test_operator_components_are_normalized_before_mixing
test_failed_adjoint_audit_falls_back_safely
test_reverse_operator_result_never_updates_truth
```

---

### 11.4 Work package S2.4 - Add a slow value-of-computation budget arbiter

#### Objective

Allocate integer packets not only among operations inside one goal, but among goals and cognitive activity classes.

#### New module

Add:

`src/freeciv_agent/pressure/budget_arbiter.py`

```python
@dataclass(frozen=True)
class ActivityBid:
    goal_id: str
    activity: str  # probe, estimate, infer, observe, simulate, act, expand, retain
    resource: ResourceKind
    next_packet_value: float
    uncertainty: float
    minimum_packets: int
    maximum_packets: int
    safety_class: bool

@dataclass(frozen=True)
class BudgetDecision:
    allocations: tuple
    metacontrol_cost: tuple[PacketCost, ...]
    exploration_floor: tuple
    fallback_used: bool
```

Use a bounded greedy marginal-value rule first. Safety-class minimums are allocated lexicographically. Then allocate guaranteed base-level progress and exploration packets. Remaining packets are assigned by calibrated marginal value of computation.

#### Recursion limit

The arbiter must not recursively spend unbounded compute deciding how to spend compute. Configure:

- maximum metacontrol budget fraction;
- one-step or short-horizon value estimates;
- slower update cadence than within-goal scheduling;
- static fallback allocation;
- mandatory base-level progress.

#### Tests

```text
test_budget_arbiter_respects_resource_budgets
test_safety_minimum_is_lexicographic
test_metacontrol_has_hard_budget_cap
test_exploration_floor_survives_high_value_dominant_goal
test_static_fallback_is_used_when_value_calibration_is_unhealthy
```

---

### 11.5 Work package S2.5 - Make observation and simulation pressure engine-live

#### Objective

Connect `pressure/observation.py` to the common operation, packet, risk, and provenance interfaces instead of leaving it as a separate accepted component.

#### Integration rules

- observation pressure is driven by expected decision value, not uncertainty alone;
- a test with high entropy reduction but no effect on any active decision may receive low priority;
- simulator outputs carry simulator identity, validity scope, and confidence cap;
- an observation creates evidence only after the authoritative result returns;
- selection propensity is logged before execution;
- observation packets and simulator packets are distinct resources;
- repeated correlated observations are discounted through evidence-overlap semantics.

#### Adapter changes

Extend the Impact adapter to enumerate observations only where the authoritative interface supports them. Examples include:

- treasury or rate-state query already available in the snapshot;
- bounded simulation of candidate completion within the existing projection code;
- threat-state refresh where packet-visible information may be stale;
- route validation for settlement or tactical movement;
- exact legal-action refresh before an irreversible commitment.

Do not invent sensors FreeCiv does not expose. A state read that is already present in the authoritative snapshot has zero observation packet cost inside that snapshot; a network or server refresh may have nonzero latency cost.

#### Tests

```text
test_decision_irrelevant_uncertainty_does_not_dominate_observation_budget
test_observation_result_updates_evidence_only_after_authoritative_return
test_simulator_identity_and_confidence_cap_are_serialized
test_repeated_overlapping_observation_is_discounted
test_observation_selection_propensity_is_logged
```

---

### 11.6 Work package S2.6 - Activate provenance, contradiction, and selection-coverage monitoring

#### Objective

Preserve the current evidence-token firewall while making its risk and selection-bias outputs available to live scheduling.

#### Required additions

Extend `pressure/provenance.py` with control-facing, read-only summaries:

```python
@dataclass(frozen=True)
class EvidenceRiskSummary:
    overlap_weight: float
    conflict_severity: float
    lineage_depth: int
    independent_source_count: int
    quarantine_required: bool

@dataclass(frozen=True)
class SelectionExposure:
    region_id: str
    pressure_exposure: float
    observation_count: int
    evidence_update_weight: float
    audit_coverage: float
```

Add a `SelectionBiasMonitor` that records:

- which region or hypothesis family received pressure;
- which evidence-acquisition operations were selected;
- their selection propensities;
- which evidence actually updated beliefs;
- low-pressure regions receiving audit observations;
- correlation between historical pressure exposure and belief-update coverage.

#### Firewall

These summaries can suppress or redirect scheduling. They cannot revise truth. Inverse-propensity weighting, where used, is for calibration audits and must declare its assumptions.

#### Tests

```text
test_probe_or_pressure_exposure_never_registers_evidence_token
test_overlap_risk_suppresses_duplicate_proof_operation
test_audit_observation_budget_reaches_low_pressure_region
test_selection_coverage_metric_is_context_stratified
test_deterministic_selection_records_reason_instead_of_fake_probability
```

---

### 11.7 Work package S2.7 - Activate pressure-gated LLM expansion through typed packets

#### Objective

Connect the existing `PressureLLMGateway` to the scalar-v2 controller in shadow mode, then selectively engine-live mode.

#### Admission contract

An LLM call requires all of the following:

- material expansion demand on a frontier stub or missing rule factor;
- low expected relief from retrieval, known-rule instantiation, observation, and simulation alternatives;
- a typed schema for the requested output;
- a validation plan;
- available whole `LLM_TOKEN` and validation packets;
- context and forbidden-assumption constraints;
- a declared maximum initial confidence and quarantine policy.

The controller should score the complete compound operation:

```text
LLM proposal + validation effort + expected rejection cost + token cost
```

not the proposal call in isolation.

#### Output handling

Every proposal remains in a quarantine store with:

- model identity;
- prompt digest and sanitized context;
- requested schema;
- proposal content digest;
- initial confidence cap;
- validation route;
- evidence dependencies;
- expiration and retry policy.

A probe may test whether the proposal would create a bridge, but probe success cannot promote it. Only existing verifier/grader or exact rule/observation pathways may do so.

#### Tests

```text
test_llm_call_requires_expansion_and_validation_packets
test_llm_proposal_remains_quarantined_after_probe_success
test_prompt_contains_typed_gap_and_forbidden_assumptions
test_low_pressure_request_is_not_admitted
test_token_reservation_is_atomic_and_settled
test_rejected_proposal_does_not_change_truth_or_conductance_as_if_verified
```

---

### 11.8 Work package S2.8 - Integrate lifecycle clones and induction as shadow operations

#### Objective

Allow lifecycle split/merge and inductive expansion proposals to compete for typed packets without immediately making them live structural mutations.

#### Lifecycle operations

Represent:

- `propose_clone_split` as an `expand` operation;
- `evaluate_clone_split` as an inference/simulation packet bundle;
- `commit_clone_split` as a durable graph mutation requiring exact validation;
- `propose_clone_merge` and `commit_clone_merge` similarly;
- clone-specific action recommendations as separate context-bearing operations.

A split requires the existing predictive-gain, complexity, cap, successor, lineage, and merge gates. Flow or pressure may make the proposal salient but may not bypass these gates.

#### Induction and analogy operations

Represent pattern mining, analogy transfer, and rule promotion as distinct operations:

- mining consumes compute packets;
- proposal creation consumes expansion packets;
- held-out replay consumes simulation packets;
- promotion consumes a durable mutation packet and validator approval;
- demotion or retirement is explicit and auditable.

Start in shadow mode. Record which structural operation would have been selected and its later realized usefulness before enabling commits.

#### Tests

```text
test_clone_split_pressure_cannot_bypass_predictive_gain_gate
test_inductive_proposal_requires_heldout_validation_packets
test_analogy_uncertainty_is_preserved_in_typed_advantage
test_structural_operation_uses_current_clone_generation_at_commit
test_shadow_structural_operation_writes_no_durable_semantics
```

---

### 11.9 Work package S2.9 - Calibrate credit and conductance against realized relief

#### Objective

Separate the following learned quantities:

- epistemic calibration of a rule or observation model;
- teleological resolvability;
- route conductance;
- operation success probability;
- cost and latency estimate;
- motif usefulness;
- bridge predictor reliability.

`ConductanceLearner` currently provides bounded grounded credit and no-progress decay. Preserve that behavior, but move to a richer record:

```python
@dataclass(frozen=True)
class ControlCalibrationRecord:
    context_signature: str
    rule_or_operation_id: str
    predicted_relief: float
    realized_relief: float
    predicted_success: float
    success: bool
    predicted_cost: tuple
    realized_cost: tuple
    selection_propensity: float | None
    update_targets: tuple[str, ...]
```

A single outcome may update several control models, but each update is typed and logged. Realized reward is not evidence for unrelated propositions.

#### Hebbian conductance compatibility

Retain the original Hebbian intuition as a route-learning prior:

```text
successful repeated co-activation and verified relief -> higher conductance
failed or no-progress route under comparable context -> decay
```

However, conductance must carry context, frontier, and generation metadata when it is later compared with an explicit bridge. Generic category conductance and query-specific reachability are not assumed identical.

#### Tests

```text
test_credit_updates_only_declared_control_targets
test_no_progress_decays_route_without_changing_truth
test_context_mismatch_prevents_unqualified_conductance_reuse
test_calibration_record_pairs_predicted_and_realized_relief
test_selection_propensity_is_available_for_offpolicy_audit
```

---

### 11.10 Gate G2 - Teleological calibration and live parity

Proceed to the bridge experiment only when:

- scalar-v2 remains safe and replayable in the live Impact path;
- cost-to-go and typed-advantage artifacts are emitted and calibrated;
- operation cost, utility, urgency, deadline, and risk are each counted exactly once;
- observation and LLM operations use whole packets and preserve the evidence firewall;
- component-only lifecycle and induction operations run in shadow mode without durable side effects;
- predicted-versus-realized relief plots exist by category and horizon;
- the strong scalar baseline can consume the same teleological features;
- controller-inclusive cost is reported;
- no bridge or flow claim is needed to explain scalar-v2 results.

---

## 12. Stage S3 - Explicit bridge geometry and the conductance-equivalence experiment

Stage S3 answers the central research question raised during the design discussion: **does a separate forward/backward bridge field add useful information beyond the existing utility, pressure, conductance, compatibility, and resolvability fields?** The implementation must make that question measurable rather than settle it terminologically.

### 12.1 Work package S3.1 - Create a query-local factor graph package

#### New package

Add:

```text
src/freeciv_agent/flow_control/
    __init__.py
    model.py
    builder.py
    topology.py
    normalization.py
    potentials.py
    probes.py
    cycles.py
    candidate_selector.py
    diagnostics.py
    controller.py
```

Stage S3 does not yet require projection or advection modules. It uses bridge estimates with the packet-capable scalar scheduler.

#### Flow-node kinds

```python
class FlowNodeKind(str, Enum):
    PROPOSITION = "proposition"
    RULE_FACTOR = "rule_factor"
    REQUIREMENT_SET = "requirement_set"
    OPERATION = "operation"
    LIFECYCLE = "lifecycle"
    FORWARD_BOUNDARY = "forward_boundary"
    BACKWARD_BOUNDARY = "backward_boundary"
    RESERVOIR = "reservoir"
    FRONTIER_STUB = "frontier_stub"
    SHARD_PORTAL = "shard_portal"
```

For Stage S3, reservoir and shard-portal nodes may be present in schemas but inactive.

#### Edge kinds and legality

```python
class FlowEdgeKind(str, Enum):
    FORWARD_TRUTH = "forward_truth"
    BACKWARD_DEMAND = "backward_demand"
    PROBE_FORWARD = "probe_forward"
    PROBE_BACKWARD = "probe_backward"
    ASSOCIATIVE = "associative"
    OPERATION_INVOKE = "operation_invoke"
    LIFECYCLE = "lifecycle"
    RESOURCE_RETURN = "resource_return"
    SHARD_TRANSFER = "shard_transfer"
    SPLICE = "splice"
    EXPANSION = "expansion"
```

Each edge has process-specific legality bits. Backward legality is constructed explicitly rather than obtained by negating forward edges.

#### Stable identity

Local dense IDs are ephemeral. Every node and edge records:

- stable semantic identity, when one exists;
- semantic generation;
- topology generation;
- context digest;
- clone generation;
- source/provenance;
- born and retired generation.

No local array position may appear in a durable candidate or event without stable identity and generation.

---

### 12.2 Work package S3.2 - Deepen the FreeCiv factorization

#### Problem

The current `ImpactPressureRanker` largely creates a shallow structure from active goals to category-level atoms and grounded candidates. In such a graph, a sophisticated bridge estimator has little depth on which to improve routing.

#### Target factorization

For each grounded candidate, materialize only the relevant bounded factors. A candidate route may contain:

```text
active goal
  <- desired outcome factor
  <- effect model factor
  <- operation factor
  <- requirement set
       <- legal action is still advertised
       <- actor exists and is available
       <- target or destination remains valid
       <- resource/gold/upkeep precondition
       <- path or movement feasibility
       <- production/completion deadline
       <- threat or opportunity context
       <- required observation/simulation result
       <- safety and provenance guards
```

The graph must not manufacture legality. Candidate operation nodes are created only from the authoritative legal candidate set or from quarantined proposals that are explicitly noncommittable.

#### Boundedness

Use a materialization budget per goal and category. Preserve frontier stubs for:

- deeper production consequences;
- additional route alternatives;
- simulator calls;
- retrieval or rule generation;
- latent context refinement;
- LLM expansion.

A stub may receive expansion demand but is not treated as a fact.

#### Candidate identity

Every candidate node records:

```python
CandidateGrounding(
    snapshot_id=...,
    legal_action_digest=...,
    semantic_epoch=...,
    topology_generation=...,
    actor_id=...,
    target_digest=...,
    category=...,
)
```

This record is used later for commit revalidation.

#### Tests

```text
test_flow_builder_only_materializes_authoritative_legal_actions
test_candidate_factorization_preserves_premise_roles
test_forward_and_backward_legalities_are_distinct
test_frontier_stub_is_not_a_proposition_or_evidence
test_local_ids_are_rejected_after_generation_change
test_factorization_budget_is_enforced_deterministically
```

---

### 12.3 Work package S3.3 - Implement forward and backward potential estimators

#### Core semantics

For goal `j` and local node `i`, maintain:

```text
f_j(i) > 0  : reachability from current evidence/frontier
g_j(i) > 0  : usefulness or continuation desirability toward the goal
phi_j(i) = log f_j(i)
psi_j(i) = log g_j(i)
H_j(i) = phi_j(i) + psi_j(i)
```

These are control estimates, not truth probabilities unless a specific calibrated estimator explicitly gives them probabilistic meaning.

#### Estimator interface

```python
@dataclass(frozen=True)
class PotentialEstimate:
    goal_id: str
    node_id: str
    forward_factor: float
    backward_factor: float
    log_forward: float
    log_backward: float
    bridge_height: float
    forward_uncertainty: float
    backward_uncertainty: float
    estimator_policy: str
    effective_sample_size: float | None
    clipped_weight_fraction: float | None
    estimator_id: str

class PotentialEstimator(Protocol):
    def estimate(self, view, goal_bundle, budget) -> tuple[PotentialEstimate, ...]:
        ...
```

#### Initial estimator families

Implement in this order:

1. bounded deterministic forward/backward message passing;
2. shortest or minimum-cost meet heuristics on synthetic graphs;
3. Monte Carlo meet-probability estimates;
4. cached estimates from related queries;
5. learned predictors only after labels and calibration exist.

Potential estimates must expose uncertainty. A low-support bridge ridge should not masquerade as a precise corridor.

#### Reference versus behavior process

Every estimator declares whether `f` and `g` describe:

- the current steered behavior process;
- a fixed reference process;
- a holdout-calibrated approximation;
- a learned predictor of one of those processes.

This distinction is part of artifact identity.

---

### 12.4 Work package S3.4 - Implement corrected forward and backward probes

#### Probe record

```python
@dataclass(frozen=True)
class ProbePath:
    path_id: str
    side: str
    start_node_id: str
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    total_cost: float
    met_opposite_frontier: bool
    meet_node_id: str | None
    novelty: float
    evidence_risk: float
    reliability: float
    behavior_log_probability: float
    reference_log_probability: float
    importance_weight: float
    topology_generation: int
    rng_substream: int
```

#### Behavior proposal

Use standardized local advantage, cost, congestion placeholder, risk, and current-following terms. During Stage S3, the current-following term is zero or scalar-route momentum.

Forward and backward probes use separate legal edge sets and reference kernels. Never define a backward probe as simply the negative of the forward proposal.

#### Bias correction

Support two modes:

1. **Importance-corrected probes** with clipped behavior/reference likelihood ratio and effective sample size.
2. **Two-stream probes** where steered probes discover routes and a smaller reference stream calibrates factors.

Default to the two-stream design if importance weights become unstable.

#### Health policy

Low ESS, high clipped-weight fraction, or collapsed path diversity triggers:

- more reference probes;
- higher temperature;
- weaker route-momentum gain;
- increased diffusion/exploration in later stages;
- reliance on deterministic messages;
- a visible unhealthy-estimator status.

#### Tests

```text
test_probe_behavior_and_reference_likelihoods_are_recorded
test_importance_weight_and_ess_match_reference_calculation
test_low_ess_triggers_declared_fallback
test_backward_probe_cannot_traverse_forward_only_edge
test_probe_success_does_not_create_evidence
test_fixed_seed_probe_replay_is_deterministic
```

---

### 12.5 Work package S3.5 - Enforce the single-use bridge-signal contract

#### Default contract

1. `H` steers probes and contributes to requested route direction.
2. Corrected successful probes update route-current or route-momentum state.
3. Forward/backward meeting or overlap selects candidate regions.
4. `TypedAdvantage` scores concrete operations.
5. Raw `H`, raw probe count, raw route momentum, and operation PF value are not multiplied together as if independent.

#### Implementation

Add a signal-use ledger to every decision artifact:

```python
@dataclass(frozen=True)
class SignalUse:
    signal_name: str
    stage: str
    transformation: str
    used_in_final_score: bool
    residualized: bool
```

The candidate selector validates that a signal is not reused in a prohibited stage. Experimental learned fusion must use held-out data and residualized features.

#### Tests

```text
test_bridge_height_is_not_reapplied_after_overlap_readout
test_raw_probe_count_cannot_scale_current_amplitude
test_signal_use_ledger_rejects_duplicate_uncalibrated_feature
test_residualized_bridge_feature_requires_heldout_model_id
```

---

### 12.6 Work package S3.6 - Run the conductance-versus-bridge experiment

#### Research question

Does explicit forward reachability provide ranking information not already contained in:

- backward goal demand;
- learned conductance;
- contextual compatibility;
- rule residual;
- resolvability;
- success probability;
- deadline fit;
- route cost;
- scalar route momentum?

#### Experimental arms

Use identical candidate sets, packet scheduler, and operation scorer. Compare:

1. scalar PF-v2 with generic conductance;
2. scalar PF-v2 with context/frontier-conditioned conductance;
3. explicit `f × g` bridge score;
4. calibrated fusion of conductance and bridge;
5. bridge with shuffled forward factors;
6. bridge with shuffled backward factors;
7. conductance with shuffled learned values;
8. bridge-only without PF typing;
9. oracle forward reachability on synthetic graphs;
10. learned forward predictor on held-out graph families.

#### Required graph families

- useful but unreachable prerequisite;
- reachable but irrelevant branch;
- long corridor with distractors;
- AND coalition with one unreachable member;
- OR alternatives with different forward feasibility;
- dynamic edge failure;
- hidden observation that unlocks reachability;
- context-specific route where generic Hebbian conductance transfers incorrectly;
- repeated FreeCiv production or settlement route with historical conductance but changed current legality.

#### Primary metrics

- complete operation packets before deadline;
- verified goal-loss relief at fixed controller-inclusive compute;
- expensive rule or simulator calls;
- false-corridor allocation;
- candidate invalidation rate;
- bridge calibration and ESS;
- incremental mutual information or held-out ranking lift of `f` after conditioning on existing fields;
- wall time and memory.

#### Decision rule

Treat the bridge as an independent maintained field only if it produces a repeatable held-out improvement after conditioning on conductance and after estimator overhead. If not:

- retain `f` as an optional diagnostic or local reachability feature;
- derive bridge-like ranking from context-conditioned conductance;
- keep the simpler scalar-v2 architecture;
- do not proceed to fluid transport solely to preserve the theory’s four-field form.

This gate is deliberately allowed to simplify the theory.

---

### 12.7 Work package S3.7 - Add the bridge-scalar controller and fallback

#### Controller mode

Add:

```text
pressure_controller_mode: bridge_scalar
```

The mode uses:

- scalar-v2 teleology;
- explicit potentials and corrected probes;
- route-level bridge overlap or meet score;
- strong smoothed scalar scheduling;
- whole typed packets;
- no conserved attention mass or hydraulic pressure.

#### Candidate score

Use a calibrated additive or convex-combination model such as:

```text
location eligibility = corrected bridge overlap × compatibility
operation score      = typed PF advantage - cost - risk
```

Do not use raw multiplication of all signals.

#### Fallback

If bridge health is poor, the controller uses scalar-v2 for that query and emits `bridge_fallback` with reason, ESS, path diversity, and estimator generation.

---

### 12.8 Gate G3 - Bridge incremental value

Proceed to source-sink flow only if all of the following hold:

- explicit bridge estimates are calibrated and replayable;
- behavior/reference semantics and ESS are surfaced;
- probe telemetry remains outside evidence;
- useful-but-unreachable and reachable-but-irrelevant fixtures are correctly separated;
- bridge-scalar improves at least one preregistered held-out regime against context-conditioned conductance and the strong smoothed scalar baseline;
- improvement is measured at fixed controller-inclusive compute;
- false-corridor lock-in has a visible recovery policy;
- the single-use signal contract passes all tests;
- bridge failure safely falls back to scalar-v2.

If the bridge provides no incremental value, stop here and ship scalar-v2 plus packets.

---

## 13. Stage S4 - Python source-sink flow and conservative attention transport

Stage S4 implements the resource-flow layer in a transparent Python/NumPy/SciPy reference. No native ABI is frozen at this stage. The purpose is to test whether explicit conservation, capacity duals, and persistent edge currents improve verified operation completion enough to justify their cost.

### 13.1 Work package S4.1 - Freeze the normalization and units contract

#### Objective

Prevent raw semantic scores, probe path counts, and learned current motifs from being added at incompatible scales.

#### New module

Expand:

`src/freeciv_agent/flow_control/normalization.py`

```python
@dataclass(frozen=True)
class NormalizationContract:
    contract_id: str
    goal_loss_scales: tuple
    robust_scale_policy: str
    clipping_ranges: tuple
    scale_update_cadence: int
    semantic_metric: str
    probe_metric: str
    turnover_fraction: float
    packet_quanta: tuple
    capacity_policy: str
    precision_policy: str
```

#### Required behavior

For every active view and commodity, maintain robust scales for:

- edge cost;
- bridge-height difference;
- typed advantage;
- congestion dual;
- risk;
- probe deposit energy.

Normalize semantic and probe directions separately under the same declared metric. Mix only normalized directions. A separate turnover policy sets velocity amplitude. Probe count changes variance, not current magnitude.

#### Scientific identity

A change to normalization, turnover, packet quantum, sign convention, or capacity provenance invalidates calibration even if topology and code are unchanged. Include contract hash in all decision artifacts and benchmark manifests.

#### Tests

```text
test_raw_probe_count_does_not_change_requested_current_amplitude
test_normalization_contract_hash_changes_on_scale_policy_change
test_missing_scale_uses_declared_fallback
test_semantic_and_probe_directions_are_unit_normalized_before_mixing
test_turnover_fraction_bounds_local_raw_cfl
```

---

### 13.2 Work package S4.2 - Build requested semantic and probe currents

#### New types

```python
@dataclass(frozen=True)
class DirectionalField:
    commodity_id: str
    edge_values: tuple[float, ...]
    norm: float
    metric_id: str
    source_components: tuple[str, ...]

@dataclass(frozen=True)
class RequestedCurrent:
    commodity_id: str
    velocity: tuple[float, ...]
    turnover_rate: float
    normalization_contract_id: str
    semantic_weight: float
    probe_weight: float
```

#### Construction

For each `(goal, mode, resource)` commodity:

1. construct typed semantic edge direction from teleological operators;
2. construct mean corrected successful probe path current;
3. normalize each direction;
4. mix with declared convex weights;
5. set rate from turnover and outer packet allocation;
6. attach source-sink boundary vector and legality mask.

Path-current deposits are normalized by successful meet count and path energy. Raw path count is never an additive gain.

#### Path closure

Add explicit closure policies in `flow_control/cycles.py`:

- known proof-chain or splice closure;
- reservoir return closure;
- source-sink representation without explicit return edge;
- projection fallback only when it preserves the intended semantics.

On a tree, never project an open path into the zero-dimensional cycle space and call the zero result a route. Prefer source-sink flow or an accounting lift.

#### Virtual-edge firewall

Resource return edges are marked `RESOURCE_RETURN`, excluded from:

- forward truth adjacency;
- backward causal planning;
- evidence traversal;
- proof explanations;
- operation legality.

They may appear only in attentional accounting explanations.

---

### 13.3 Work package S4.3 - Implement uncapacitated source-sink projection

#### New module

Add:

`src/freeciv_agent/flow_control/projection.py`

#### Mathematical contract

Given incidence matrix `B`, edge mobility `M`, raw request `u_e`, and balanced source-sink vector `b`, solve:

```text
minimize 0.5 ||u - u_e||^2_{M^-1}
subject to B^T u = b
```

with:

```text
u = u_e - M B pi
(B^T M B) pi = B^T u_e - b
```

`pi` is `CongestionDual` or hydraulic pressure. Fix a gauge per connected component.

#### Mobility

Mobility may include:

- learned conductance;
- contextual compatibility;
- legal-transition gate;
- reliability;
- declared capacity scaling.

It may not include truth confidence as a way to manufacture support. Any use of epistemic uncertainty must be explicit and operation-specific.

#### Solver API

```python
@dataclass(frozen=True)
class ProjectionResult:
    feasible_current: tuple[float, ...]
    congestion_dual: tuple[float, ...]
    balance_residual: float
    iterations: int
    gauge_policy: str
    health: str

class ProjectionSolver:
    def solve(self, view, requested, boundary, tolerance) -> ProjectionResult:
        ...
```

Start with SciPy sparse conjugate gradient and a diagonal preconditioner. Add exact dense solves only for small golden fixtures.

#### Tests

```text
test_projection_satisfies_source_sink_balance
test_projection_gauge_does_not_change_current
test_tree_source_sink_flow_is_nonzero
test_virtual_return_lift_matches_source_sink_restriction
test_projection_failure_returns_unhealthy_status_not_candidate_authority
test_mobility_zero_blocks_illegal_edge
```

---

### 13.4 Work package S4.4 - Add capacity provenance and multi-commodity constraints

#### New module

Add:

`src/freeciv_agent/flow_control/capacities.py`

#### Capacity types

```python
class CapacityKind(str, Enum):
    MEASURED = "measured"
    ALLOCATED = "allocated"
    SHAPING = "shaping"
    NONE = "none"

@dataclass(frozen=True)
class CapacityRecord:
    edge_or_node_id: str
    resource: ResourceKind
    value: float
    kind: CapacityKind
    provenance_id: str | None
    measured_window: tuple | None
    confidence: float
```

#### Interpretation

- **Measured** capacities may identify a genuine shared bottleneck and can propose caching, compilation, replication, or more workers.
- **Allocated** capacities reflect an outer policy choice and may request budget reallocation.
- **Shaping** capacities are numerical regularizers only and may not trigger structural self-improvement.

#### Solver

Implement a warm-started primal-dual or ADMM-like multi-commodity relaxation. Expose:

- primal residual;
- dual residual;
- complementarity gap;
- active set changes;
- dual autocorrelation;
- convergence status;
- capacity provenance for every nonzero dual.

A nonconverged solve may guide exploration but may not claim economically meaningful prices.

#### Initial FreeCiv capacities

Use only capacities that have clear meaning:

- packet budgets from the outer arbiter are `ALLOCATED`;
- LLM token limits and simulator concurrency are measured or allocated according to their actual source;
- server request rate or worker queue throughput may become `MEASURED` when instrumented;
- concentration caps used to preserve diversity are `SHAPING`;
- logical edges have no intrinsic physical capacity by default.

#### Tests

```text
test_measured_allocated_and_shaping_capacities_are_distinct_types
test_shaping_dual_cannot_trigger_structural_change
test_allocated_dual_requests_arbiter_reconsideration_only
test_measured_capacity_dual_tracks_service_bottleneck_in_fixture
test_nonconverged_dual_is_not_reported_as_economic_price
test_multi_commodity_total_edge_flow_respects_capacity
```

---

### 13.5 Work package S4.5 - Implement conservative two-dye advection

#### New module

Add:

`src/freeciv_agent/flow_control/advection.py`

#### State

Maintain separate forward and backward attention densities because the legal graphs are asymmetric:

```python
@dataclass
class AttentionState:
    forward_mass: np.ndarray
    backward_mass: np.ndarray
    reservoir_mass: dict[str, float]
    inflight_mass: dict[str, float]
    reservations: PacketReservationLedger
```

#### Flux and update

Use an upwind donor-cell flux with optional conservative diffusion. The kernel must report total mass before and after each step. Compute forward and backward feasible fields on separately legal edge sets; do not assume `u_backward = -u_forward`.

Define an overlap readout such as:

```text
M_i = (a_i^+ + epsilon)^alpha (a_i^- + epsilon)^alpha
```

Under the single-use contract, overlap identifies candidate locations; typed PF advantage scores the actual operation.

#### CFL and positivity

Before each explicit step, enforce a graph CFL limit. Rescale velocities if needed. Occasional small floating-point correction is acceptable and logged. Frequent clipping or renormalization is a health failure that triggers smaller time step or fallback.

#### Transport latency

Measure microsteps and wall time per corridor length. Implement no macro-edges or multilevel acceleration until the plain reference establishes where transport latency becomes limiting.

#### Tests

```text
test_attention_mass_is_conserved_without_declared_reactions
test_forward_backward_masses_use_separate_legalities
test_valid_cfl_preserves_nonnegative_mass
test_cfl_rescaling_is_reported
test_overlap_peaks_on_true_meeting_corridor
test_transport_latency_scales_with_corridor_length
test_reservoir_and_reservation_mass_are_in_total_accounting
```

---

### 13.6 Work package S4.6 - Integrate continuous eligibility with discrete packets

#### Objective

Make flow a routing relaxation, not an alternative execution semantics.

#### Readout pipeline

```text
attention overlap at node
  -> enumerate concrete operations
  -> typed PF advantage and risk score
  -> continuous operation eligibility
  -> packet reservation solver
  -> complete RequirementSet and operation thresholds
  -> exact revalidation
  -> commit or return packets
```

Continuous mass that reaches an operation gate but cannot complete a packet remains a bounded reservation or is returned. It is not counted as proof progress or action progress.

#### Candidate schema

```python
@dataclass(frozen=True)
class FlowCandidate:
    candidate_id: str
    flow_view_id: str
    semantic_epoch: int
    topology_generation: int
    node_semantic_id: str
    operation_id: str
    per_goal_expected_relief: tuple
    overlap_score: float
    bridge_diagnostics: tuple
    congestion_delta: float
    risk: RiskEstimate
    cost_vector: CostVector
    packet_costs: tuple[PacketCost, ...]
    packet_threshold: int
    selection_propensity: float | None
    reason_codes: tuple[str, ...]
```

Raw bridge height and raw flow alignment remain diagnostics by default.

#### Integrality diagnostics

Report:

- relaxed continuous value;
- packet-feasible value;
- integrality gap;
- stranded mass;
- incomplete reservations;
- packet starvation by operation and RequirementSet;
- reservation age and return rate.

---

### 13.7 Work package S4.7 - Add flow diagnostics, repair, and fallback

#### New module

Add:

`src/freeciv_agent/flow_control/diagnostics.py`

Required diagnostics:

| Diagnostic | Meaning | Required response when unhealthy |
|---|---|---|
| forward/backward total mass | conservation | stop flow block, repair or fallback |
| balance residual | projection correctness | regional resolve or scalar fallback |
| local CFL | stability | rescale velocity or reduce step |
| bridge overlap | meeting corridor | expand, diffuse, or fallback |
| probe meet rate | graph/estimator health | increase exploration or use messages |
| ESS and clipping | correction health | more reference probes or holdout mode |
| path diversity | lock-in | increase temperature/diffusion |
| feedback ratio | self-reinforcement | lower deposit/current-following gain |
| pressure peak | bottleneck | inspect capacity provenance |
| dual health | solver convergence | suppress economic interpretation |
| integrality gap | relaxation mismatch | concentrate routes or change packet policy |
| packet starvation | incomplete operations | return/reallocate reservations |
| stale-view lag | commit invalidation risk | patch, rebuild, or fallback |
| predicted vs realized relief | calibration | update or disable estimator |
| normalization drift | semantic identity change | invalidate calibration |
| controller overhead | scientific viability | compare against scalar baseline |

#### Repair order

1. local numerical repair;
2. increase exploration or reduce feedback;
3. apply pending topology patches;
4. rebuild the affected view;
5. fall back to bridge-scalar;
6. fall back to scalar-v2;
7. fall back to scalar-v1 or canonical Impact planner.

A repair must never alter truth to make the controller’s preferred route viable.

---

### 13.8 Work package S4.8 - Execute the Stage-0 scientific-risk sandbox

#### Location

Add:

```text
python/reference_model/
python/ablations/
python/stability/
python/proof_tasks/
benchmarks/freeciv/pf_unified/
```

Within the current Python repository, an equivalent layout under `research/flow_control/` is acceptable if packaging constraints make a top-level `python/` undesirable. Keep the reference independent of live planner code so it can expose every intermediate matrix and field.

#### Required synthetic families

- two-corridor positive-feedback model;
- long paths with stable and changing corridors;
- OR alternatives with packet thresholds;
- AND coalitions and zero-gradient blockers;
- trees, DAGs, cyclic graphs, and disconnected distractors;
- asymmetric backward legality;
- measured service bottlenecks;
- allocated and shaping capacities;
- dynamic edge failures and stale topology;
- evidence-acquisition selection bias;
- resource conversion and reservation fragmentation.

#### Required baselines

- uniform or random expansion;
- forward-only best-first;
- backward-only best-first;
- tuned bidirectional heuristic search;
- strong smoothed scalar priority with route momentum and diversity floor;
- diffusion-only attention;
- scalar probe pheromone;
- bridge scoring without flow;
- electrical-flow routing;
- ACO-style reinforcement;
- compatible GFlowNet-style flow matching or trajectory balance on construction DAGs;
- exact small integer packet solver as an oracle for integrality regret.

#### Required ablation ladder

1. scalar PF-v1;
2. scalar PF-v2;
3. scalar PF-v2 plus packets;
4. explicit bridge without probes;
5. corrected versus uncorrected probes;
6. scalar pheromone;
7. path currents without PF typing;
8. PF plus bridge with scalar packet scheduler;
9. source-sink projection without advection;
10. continuous advection without packet gates;
11. advection plus packet gates;
12. capacities without provenance;
13. capacities with provenance;
14. full multi-goal controller.

#### Stability maps

Map false-corridor fixed points, hysteresis, and recovery over deposit gain, current-following gain, decay, temperature, diffusion, turnover, packet quantum, and corridor length. Publish negative and unstable regions, not only a tuned optimum.

---

### 13.9 Gate G4 - Flow earns its cost

Proceed to live FreeCiv flow integration only if:

- mass and source-sink accounting invariants hold;
- packet completion, not relaxed mass, predicts useful work;
- capacity duals are interpreted according to provenance;
- the flow controller beats the strong smoothed scalar baseline in at least one preregistered held-out regime after controller overhead;
- the improvement survives corridor-length and dynamic-failure tests;
- false-corridor recovery is reliable in the selected parameter region;
- normalization and turnover settings transfer across held-out generators;
- transport latency is included;
- bridge and flow components each earn incremental value in ablation;
- the fallback ladder is tested under numerical failure.

If these conditions fail, retain the best scalar/bridge/packet subset and stop the fluid implementation.

---

## 14. Stage S5 - Live FreeCiv integration

Stage S5 connects the scientifically accepted controller subset to the existing `GroundedImpactPlanner` without weakening authoritative candidate generation, safety, or execution. Integration is incremental: shadow first, then advisory ranking, then narrowly scoped live selection.

### 14.1 Work package S5.1 - Introduce a versioned planner-controller adapter

#### Objective

Avoid expanding `ImpactPressureRanker` into one monolithic class containing teleology, bridge estimation, flow integration, packets, events, and learning.

#### New adapter

Add:

`src/freeciv_agent/planning/impact_flow_adapter.py`

```python
class ImpactControlAdapter:
    """Narrow boundary between grounded Impact candidates and control engines."""

    def build_query(
        self,
        snapshot,
        candidates,
        expansion_city_target,
        horizon_turn,
        survival_threat_radius,
        goal_facts,
    ) -> ControlQuery:
        ...

    def rank_or_schedule(
        self,
        query: ControlQuery,
        mode: str,
    ) -> ControlDecision:
        ...

    def record_outcome(self, decision, before, after, execution_result) -> None:
        ...
```

The adapter delegates to one of:

- `LegacyImpactPressureController` wrapping current `ImpactPressureRanker`;
- `ScalarV2Controller`;
- `BridgeScalarController`;
- `UnifiedFlowController`;
- `CanonicalUtilityController` fallback.

`GroundedImpactPlanner.plan()` continues to enumerate candidates first and materialize a plan only from the selected grounded candidate.

#### Controller result

```python
@dataclass(frozen=True)
class ControlDecision:
    ordered_candidate_keys: tuple[str, ...]
    selected_candidate_key: str | None
    packet_schedule: PacketSchedule | None
    controller_mode: str
    artifact: dict
    health: str
    fallback_chain: tuple[str, ...]
```

The adapter may reorder or withhold candidates. It may not add an unadvertised legal action.

#### Compatibility

During migration, `ImpactPressureRanker.rank()` remains callable and returns its historical tuple. The new adapter wraps it rather than changing all callers at once.

---

### 14.2 Work package S5.2 - Define a FreeCiv control query and semantic epoch

#### Control query

```python
@dataclass(frozen=True)
class ControlQuery:
    query_id: str
    snapshot_id: str
    semantic_epoch: int
    legal_actions_digest: str
    current_turn: int
    horizon_turn: int
    active_goals: tuple
    grounded_candidates: tuple
    truth_summaries: tuple
    evidence_summaries: tuple
    context_digest: str
    config_digest: str
    ruleset_digest: str
```

#### Epoch policy

The existing snapshot identifier and legal-action digest already provide strong commit guards. Add a local `semantic_epoch` that changes when any control-relevant item changes:

- authoritative snapshot;
- legal candidate set;
- active goal set;
- pressure/conductance state generation;
- lifecycle clone generation;
- normalization contract;
- controller profile or ruleset digest.

A `FlowView` can be boundedly stale during speculation, but any candidate emitted for commitment retains the source epoch and must be checked against the current query.

---

### 14.3 Work package S5.3 - Add exact candidate revalidation

#### New module

Add:

`src/freeciv_agent/planning/commit_validator.py`

#### Validation sequence

Before plan materialization:

1. resolve candidate stable key;
2. verify source snapshot and legal-action digest or translate through an explicitly accepted refresh;
3. confirm the action is still present in the authoritative candidate set;
4. re-run exact category-specific safety and resource guards;
5. confirm actor, target, route, production, treasury, and deadline preconditions;
6. verify context and clone generation;
7. verify evidence-overlap and quarantine status;
8. confirm complete packet reservation and no double spend;
9. refresh predicted cost when material changes occurred;
10. either `Commit`, `Reject`, or `Regenerate`.

#### Result types

```python
class ValidationDisposition(str, Enum):
    COMMIT = "commit"
    REJECT = "reject"
    REGENERATE = "regenerate"

@dataclass(frozen=True)
class ValidationResult:
    disposition: ValidationDisposition
    reason: str | None
    current_snapshot_id: str
    current_legal_actions_digest: str
    released_packets: tuple[PacketCost, ...]
    refreshed_candidate_key: str | None
```

The existing plan and execution gates remain final authority after this validator. This is an additional controller boundary, not a replacement.

#### Tests

```text
test_stale_candidate_is_revalidated_before_plan_materialization
test_retired_action_releases_reserved_packets
test_changed_cost_requests_regeneration
test_clone_generation_change_rejects_stale_candidate
test_current_legal_candidate_survives_bounded_stale_flow_view
test_commit_validator_cannot_create_new_action
```

---

### 14.4 Work package S5.4 - Implement controller shadow mode

#### Mode

Add:

```text
pressure_controller_mode: unified_shadow
```

In shadow mode:

- the canonical live selection remains unchanged;
- scalar-v2, bridge-scalar, and flow controllers can run in parallel under strict budget caps;
- each produces a candidate ranking and packet schedule;
- no shadow packet is spendable in the live execution ledger;
- later outcomes are used to estimate counterfactual ranking quality only where grounded comparison is valid;
- latency and memory overhead are recorded separately.

#### Counterfactual caution

A candidate not selected cannot be assigned realized external relief as though executed. Use:

- exact one-step model comparisons;
- replayable deterministic projections;
- simulator outcomes where independently available;
- offline paired-seed cohorts;
- explicit “unknown counterfactual” rather than fabricated labels.

#### Shadow acceptance

Run shadow mode until:

- no truth, state, legal action, or execution output differs;
- packet accounting is internally conserved;
- candidate revalidation rejection reasons are understood;
- latency budgets are met;
- deterministic replay succeeds;
- controller-health fallback is exercised by fault injection.

---

### 14.5 Work package S5.5 - Advisory ranking mode

#### Mode

Add:

```text
pressure_controller_mode: bridge_scalar_advisory
pressure_controller_mode: unified_flow_advisory
```

Advisory mode permits the new controller to reorder candidates only when:

- its artifact is healthy;
- the selected candidate is already in the authoritative set;
- packet completion and exact revalidation pass;
- no safety-class conflict exists;
- confidence and calibration thresholds are met;
- the fallback controller agrees that the candidate is admissible.

If the controller abstains or fails health checks, use scalar-v2 or the configured fallback.

#### Disagreement logs

For every disagreement between live baseline and advisory controller, log:

- top candidates and categories;
- per-goal typed advantage;
- bridge reachability and usefulness;
- packet completion state;
- risk and deadline estimates;
- expected resource use;
- controller health;
- later authoritative outcome where observable.

This disagreement set is the most valuable review corpus before live activation.

---

### 14.6 Work package S5.6 - Limited live activation

#### Activation scope

Enable live selection only for predeclared candidate categories and contexts where:

- the bridge/flow layer passed the relevant held-out benchmark;
- transition models are calibrated;
- commit rejection rate is low;
- no safety regression appeared in shadow or advisory mode;
- controller overhead fits the turn budget;
- there is a fresh, seed-disjoint paired cohort.

Do not enable all categories at once. A sensible order is:

1. internal inference, simulation, or observation choices with no direct external action;
2. reversible low-cost action categories;
3. production or movement choices with robust authoritative guards;
4. irreversible strategic actions only after separate risk and safety acceptance.

#### Cohort discipline

Each live claim requires:

- preregistered primary metric;
- fixed ruleset, opponent, horizon, and controller profile;
- seed-disjoint treatment and control pairs;
- identical tuning effort;
- controller-inclusive compute;
- exact replay and schema validation;
- safety and legality gate results;
- no pooling with diagnostic or pilot cohorts.

#### Rollback

A runtime flag can return immediately to scalar-v2 or v1 without changing stored truth. Packet reservations from the disabled controller are returned or expired before mode switch.

---

### 14.7 Work package S5.7 - Integrate three separate explanation products

The controller must answer different questions with different ledgers.

#### Why is this believed?

Return:

- evidence tokens or capsules;
- truth formulas;
- committed proof path;
- assumptions and contexts;
- confidence and uncertainty;
- overlap and conflict handling.

Exclude probe currents, virtual return edges, and controller scores.

#### Why was this considered?

Return:

- active goals;
- cost-to-go or immediate-loss estimate;
- teleological demand path;
- bridge factors and estimator health;
- probe support and path diversity;
- attention/current and congestion summary;
- expected information or relief.

This is an attentional explanation, not epistemic evidence.

#### Why was this done?

Return:

- candidate operation and authoritative grounding;
- per-goal expected effects;
- risk, deadlines, costs, and packet use;
- resource conflicts and rejected alternatives;
- safety and provenance gates;
- commit revalidation result;
- fallback chain.

#### API

Add:

```python
class DecisionExplainer:
    def belief_explanation(self, semantic_id): ...
    def attention_explanation(self, decision_id): ...
    def action_explanation(self, decision_id): ...
```

Do not collapse these into one narrative that makes control telemetry appear evidential.

---

### 14.8 Work package S5.8 - Add bounded-staleness view updates

#### Python implementation first

A live Python `FlowView` should use:

- immutable base topology generation;
- small delta overlay for added nodes/edges;
- tombstones for retirement;
- coalesced scalar patches;
- single-writer ownership;
- generation-tagged local handles;
- periodic deterministic rebuild.

#### Patch schema

```python
@dataclass(frozen=True)
class FlowPatch:
    sequence_number: int
    semantic_epoch: int
    operation: str
    stable_ids: tuple[str, ...]
    payload: dict
```

Supported patch classes:

```text
AddNode
AddEdge
RetireNode
RetireEdge
UpdateTruthSummary
UpdateCompatibility
UpdateCost
UpdateConductance
UpdateCapacity
GoalChanged
ContextInvalidated
CloneGenerationChanged
```

Structural patches are idempotent and ordered. Scalar updates may be coalesced when semantics permit.

#### Safe-point rhythm

A worker iteration should:

1. run a bounded probe block;
2. merge deposits;
3. apply scalar patches;
4. apply at most a bounded number of structural deltas;
5. invalidate affected paths or cycles;
6. repair potentials and projection;
7. run a bounded attention block;
8. emit candidates;
9. checkpoint diagnostics.

No semantic commit occurs inside this loop.

---

### 14.9 Work package S5.9 - Extend runtime declarations and configuration

#### Controller modes

Recommended enum:

```text
canonical
legacy_scalar
scalar_v2
bridge_scalar
unified_shadow
bridge_scalar_advisory
unified_flow_advisory
unified_flow_live
```

#### Configuration groups

```yaml
impact_policy:
  pressure_enabled: true
  pressure_controller_mode: legacy_scalar
  pressure_semantics_version: v1

  pressure_v2:
    achievement_uncertainty_split: false
    signed_channels: false
    distributional_risk: false
    requirement_sets: false
    packet_scheduler: false

  teleology:
    estimator: immediate_loss
    max_horizon: 6
    calibration_required: false
    metacontrol_budget_fraction: 0.05

  bridge:
    enabled: false
    estimator_policy: holdout
    forward_depth: 8
    backward_depth: 8
    probe_count: 256
    reference_probe_fraction: 0.20
    max_importance_weight: 20.0
    minimum_ess: 32.0
    temperature: 1.0
    deposit_decay: 0.10
    current_following_gain: 0.0

  flow:
    enabled: false
    turnover_fraction: 0.30
    time_step: 0.10
    cfl_limit: 0.80
    diffusion: 0.03
    projection_tolerance: 1.0e-8
    mass_tolerance: 1.0e-8
    maximum_microsteps: 16
    scalar_fallback: true

  packets:
    budgets:
      cpu: 64
      exact_rule: 8
      observation: 2
      simulation: 4
      action: 1
      expansion: 1
      llm_token: 0
    reservation_ttl: 2
    backup_route_fraction: 0.10

  safety:
    hard_tail_risk_gate: true
    commit_revalidation: true
```

#### Validation

`config.py` must reject invalid combinations. Examples:

- flow without packets;
- live flow without commit revalidation;
- importance-corrected probes without reference likelihood support;
- structural self-improvement from shaping capacities;
- LLM expansion without validation packet budget;
- signed v2 artifacts decoded as v1.

#### Runtime declaration

Update `pf_runtime.py` to report separately:

- PF theory phase support;
- controller-layer support;
- current activation;
- artifact schema versions;
- normalization contract;
- estimator policy;
- fallback availability.

Fix the current documentation drift between live adapter `1.33` and the older adapter name in the runtime document while preserving historical records.

---

### 14.10 Release gate for live integration

A live mode is releasable only when:

- current authoritative legal-action and execution gates remain unchanged;
- the new controller cannot create or execute unadvertised actions;
- exact revalidation is mandatory and tested;
- packet accounting and evidence firewalls pass fault injection;
- deterministic replay and artifact schemas are stable;
- bounded-staleness commit rejection is within the preregistered limit;
- controller latency and memory are within declared budgets;
- shadow/advisory disagreement review is complete;
- a fresh paired cohort meets its scoped primary endpoint;
- safety and legality metrics show zero unsupported violations;
- rollback to scalar-v2 and legacy modes is tested.

---

## 15. Stage S6 - Conditional native, MORK, and CeTTa acceleration

Stage S6 is optional and begins only after Gate G4 and a successful Python live subset. The uploaded theory proposes Rust/MORK for canonical semantics and lifecycle safety, C for compact numerical kernels, and CeTTa/FlowPack for guarded specialization. The current FreeCiv repository is Python-centric, so native integration should be treated as a performance architecture, not as a prerequisite for semantic completion.

### 15.1 Entry criteria

Do not begin native work unless profiling shows that one or more of the following dominates and cannot be solved by simpler Python optimization:

- query-local graph factorization;
- probe throughput;
- sparse path-current deposition;
- projection or capacity solve;
- conservative advection;
- patch application;
- candidate collection;
- repeated specialization opportunity on stable shards.

The Python reference remains the semantic oracle.

---

### 15.2 Work package S6.1 - Freeze portable schemas and golden traces

Before any ABI:

- freeze incidence orientation and divergence sign;
- freeze node and edge kind numeric values;
- freeze resource and packet types;
- freeze normalization and turnover semantics;
- freeze capacity provenance enum;
- freeze candidate and diagnostics schemas;
- create float64 golden traces;
- create permitted float32 ranking tolerances;
- define endianness, alignment, and ownership;
- define deterministic seed/substream handling;
- define fallback behavior for every error status.

No C struct layout is considered stable until differential tests pass.

---

### 15.3 Work package S6.2 - Implement a minimal native FlowView kernel

A minimal native kernel should support only:

- dense local node and edge IDs;
- structure-of-arrays fields;
- separate forward/backward legal edges;
- normalized requested current;
- source-sink projection;
- conservative upwind transport;
- CFL scaling;
- total mass and residual diagnostics;
- bounded candidate readout.

It should not initially implement multi-commodity capacities, dynamic compaction, GPU execution, or specialization.

#### Illustrative C ABI

```c
typedef struct FlowView FlowView;
typedef struct FlowOpenSpec FlowOpenSpec;
typedef struct FlowPatchBatch FlowPatchBatch;
typedef struct ProbeRunSpec ProbeRunSpec;
typedef struct AttentionRunSpec AttentionRunSpec;
typedef struct FlowCandidateBuffer FlowCandidateBuffer;
typedef struct FlowDiagnostics FlowDiagnostics;

FlowView *flow_open(const FlowOpenSpec *spec);
void flow_close(FlowView *view);
FlowStatus flow_apply_patches(FlowView *view, const FlowPatchBatch *patches);
FlowStatus flow_run_probe_block(FlowView *view, const ProbeRunSpec *spec);
FlowStatus flow_run_attention_block(FlowView *view, const AttentionRunSpec *spec);
FlowStatus flow_collect_candidates(FlowView *view, FlowCandidateBuffer *out);
FlowStatus flow_get_diagnostics(const FlowView *view, FlowDiagnostics *out);
```

Cross the FFI once per substantial block, never once per node or edge.

---

### 15.4 Work package S6.3 - Add a Rust owner and patch runtime

If the project adopts MORK or another durable semantic substrate, Rust should own:

- stable semantic identities;
- snapshot extraction;
- patch queues;
- worker creation, cancellation, and backpressure;
- single-writer `FlowView` ownership;
- cross-shard accounting tokens;
- commit revalidation;
- checkpoint and artifact guards.

A Python bridge can call the Rust runtime through a coarse extension module while the rest of the FreeCiv agent remains Python.

#### Cross-shard token invariant

For each transfer:

```text
source local mass decreases
in-flight mass increases
exactly-once destination credit occurs
acknowledgement clears in-flight mass
```

Duplicate or dropped messages must not create or destroy total resource. Use idempotent transfer IDs and durable acknowledgement state.

---

### 15.5 Work package S6.4 - Add CeTTa/FlowPack only if the runtime uses it

A `FlowPack` is justified only when stable query classes and topology shards recur enough to amortize guards and rebuilds. Its manifest should include:

- semantic profile and language-definition digests;
- source-space identities and epochs;
- rule-schema and factorization hashes;
- context and clone policies;
- resource and capacity policy hashes;
- normalization contract;
- estimator policy;
- precision, mass, balance, and CFL tolerances;
- patchable and invalidating change classes;
- fallback entrypoint;
- differential-test digest.

Runtime outcomes:

```text
valid     -> run specialized kernel
patchable -> apply bounded patches and repair
replan    -> use safe fallback and rebuild asynchronously
invalid   -> use generic semantic controller
```

Specialization must never eliminate exact commit validation.

---

### 15.6 Work package S6.5 - Multiscale acceleration

Only after the generic native kernel earns its cost, consider:

- validated path macro-edges with auditable expansion back to semantic edges;
- multilevel coarse corridor modes;
- event-driven packet transfer along a validated stable path;
- effective-resistance or spectral preconditioners;
- fused edge-family kernels;
- compact path-cycle motif dictionaries;
- guarded vectorization or GPU offload.

Every accelerator must preserve source-sink accounting and provide a differential test against the reference model.

---

### 15.7 Native performance gate

Accept native or specialized execution only when:

- committed results remain equivalent to the Python semantic reference;
- candidate ranking differences stay within declared tolerance and revalidation catches stale cases;
- guard, patch, rebuild, deoptimization, and FFI overhead are included;
- sanitizer and fault-injection tests pass;
- cancellation and compaction cannot leak resource or stale IDs;
- fallback and unload are safe;
- speedup remains after full controller overhead;
- the native layer does not become the authoritative truth store.

---

## 16. Proposed repository layout

The exact paths can adapt to repository conventions, but the following separation should remain visible:

```text
src/freeciv_agent/
  pressure/
    __init__.py
    model.py                   # v1 compatibility and shared semantic records
    teleology.py               # loss, cost-to-go, leverage, typed advantage
    risk.py                    # risk distributions and policy gates
    time.py                    # deadline and completion semantics
    reverse_operators.py       # adjoint, requirement, counterfactual, information
    coalitions.py              # RequirementSet and premise credit
    packets.py                 # resource quanta, reservations, integer scheduler
    budget_arbiter.py          # between-goal/activity value of computation
    engine.py                  # scalar-v1 and scalar-v2 reverse transport
    scheduler.py               # scalar scores and compatibility path
    scalar_baseline.py         # smoothed route-momentum baseline
    adapters.py                # proof adapter and legacy Impact adapter
    observation.py
    provenance.py
    lifecycle.py
    induction.py
    differentiable.py
    learning.py

  flow_control/
    __init__.py
    model.py                   # FlowNode, FlowEdge, FlowView, candidates
    topology.py                # dense IDs, generations, overlays
    builder.py                 # query-local factorization
    normalization.py           # units, scales, turnover contract
    potentials.py              # f, g, phi, psi, H
    probes.py                  # behavior/reference probes, ESS
    cycles.py                  # path currents and accounting closure
    projection.py              # source-sink solve and congestion duals
    capacities.py              # provenance and multi-commodity solver
    advection.py               # conservative two-dye transport
    packet_readout.py          # operation gates and packet handoff
    candidate_selector.py      # single-use signal contract
    diagnostics.py             # health, repair, fallback
    controller.py              # nested-loop coordinator
    runtime.py                 # view registry, patches, checkpoints

  planning/
    impact.py                  # existing authoritative candidate generator
    impact_flow_adapter.py     # new narrow controller boundary
    commit_validator.py        # current-state exact validation
    model.py
    scheduler.py

  llm/
    gateway.py                 # existing pressure-gated quarantine gateway

  events/
    schema.py
    writer.py

  pf_runtime.py
  config.py

Autotests/
  test_freeciv_pressure.py
  test_freeciv_pressure_v2.py
  test_freeciv_teleology.py
  test_freeciv_risk.py
  test_freeciv_packets.py
  test_freeciv_bridge.py
  test_freeciv_probes.py
  test_freeciv_flow_projection.py
  test_freeciv_flow_advection.py
  test_freeciv_flow_capacities.py
  test_freeciv_flow_integration.py
  test_freeciv_commit_revalidation.py
  test_freeciv_selection_bias.py
  test_freeciv_flow_faults.py

benchmarks/freeciv/pf_unified/
  baseline_manifest.yaml
  golden/
  synthetic/
  bridge_ablation/
  flow_ablation/
  live_shadow/
  paired_cohorts/
  reports/

docs/freeciv/
  pf-pln.md
  pf-pln-runtime.md
  pf-pln-phase-map.md
  pf-pln-v2-semantics.md
  pf-pln-bridge.md
  pf-pln-flow.md
  pf-pln-packets.md
  pf-pln-benchmark-protocol.md
  pf-pln-operations-runbook.md
```

---

## 17. Detailed data and API contracts

### 17.1 Epistemic summaries

The flow layer may cache a read-only summary:

```python
@dataclass(frozen=True)
class EpistemicSummary:
    semantic_id: str
    strength: float
    confidence: float
    uncertainty: float
    evidence_digest: str
    provenance_risk: float
    context_digest: str
    clone_generation: int
    semantic_epoch: int
```

This is not an independently revisable truth object. Any truth update returns through the canonical evidence path.

### 17.2 Goal specification

```python
@dataclass(frozen=True)
class GoalSpecV2:
    goal_id: str
    target_semantic_id: str
    target_strength: float
    utility_scale: float
    loss_scale: float
    urgency_policy: str
    commitment: float
    deadline: DeadlineState | None
    risk_profile: RiskProfile
    safety_class: str
    context_digest: str
```

Goal scales and risk profiles are explicit. A safety class may impose hard constraints independent of scalar utility.

### 17.3 Factor and requirement records

```python
@dataclass(frozen=True)
class RuleFactorRecord:
    factor_id: str
    rule_id: str
    premise_roles: tuple[tuple[str, str], ...]
    conclusion_roles: tuple[tuple[str, str], ...]
    rule_kind: str
    causal_kind: str
    forward_operator_id: str
    reverse_operator_id: str
    context_guard: tuple
    conductance: float
    compatibility: float
    residual: float
    source: str

@dataclass(frozen=True)
class RequirementSetRecord:
    requirement_set_id: str
    factor_id: str
    requirement_ids: tuple[str, ...]
    completion_policy: str
    packet_vector: tuple[PacketCost, ...]
    completion_state: tuple[bool, ...]
    coalition_method: str
```

### 17.4 Flow node and edge records

```python
@dataclass(frozen=True)
class FlowNodeRecord:
    local_id: int
    semantic_id: str | None
    semantic_generation: int
    kind: FlowNodeKind
    context_digest: str
    clone_generation: int
    flags: int
    truth_summary: EpistemicSummary | None
    evidence_risk: float
    selection_exposure: float
    capacity: CapacityRecord | None

@dataclass(frozen=True)
class FlowEdgeRecord:
    local_id: int
    semantic_id: str | None
    src: int
    dst: int
    kind: FlowEdgeKind
    legality: int
    cost: float
    conductance: float
    compatibility: float
    reliability: float
    evidence_risk: float
    capacity: CapacityRecord | None
    born_generation: int
    retired_generation: int | None
```

### 17.5 Flow view

```python
@dataclass
class FlowView:
    flow_view_id: str
    query_id: str
    semantic_epoch: int
    topology_generation: int
    field_generation: int
    nodes: list[FlowNodeRecord]
    edges: list[FlowEdgeRecord]
    forward_mass: np.ndarray
    backward_mass: np.ndarray
    phi: np.ndarray
    psi: np.ndarray
    bridge_height: np.ndarray
    requested_forward: np.ndarray
    requested_backward: np.ndarray
    feasible_forward: np.ndarray
    feasible_backward: np.ndarray
    congestion_dual: np.ndarray
    reservoir_mass: dict[str, float]
    inflight_mass: dict[str, float]
    packet_ledger: PacketReservationLedger
    normalization_contract_id: str
```

This is ephemeral control state. It is not serialized as evidence.

### 17.6 Health state

```python
class ControllerHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    REPAIRING = "repairing"
    FALLBACK = "fallback"
    INVALID = "invalid"

@dataclass(frozen=True)
class HealthReport:
    status: ControllerHealth
    reasons: tuple[str, ...]
    mass_error: float
    balance_residual: float
    cfl: float
    ess: float | None
    packet_starvation: float
    stale_lag: int
    solver_iterations: int
    fallback_target: str | None
```

Candidate commitment is allowed only under policies that explicitly accept the reported health. `INVALID` always falls back.

---

## 18. File-by-file change map

This section translates the staged architecture into concrete repository edits. It is a planning map, not permission to modify every file in one pull request.

### 18.1 `src/freeciv_agent/pressure/model.py`

#### Preserve

- immutable `TruthState` and the explicit statement that pressure cannot mutate truth;
- `AtomState`, contexts, lifecycle, and clone identity;
- v1 `PressureVector`, `Resolvability`, `GoalState`, `PressureRule`, `CostVector`, `Operation`, and `PressureConfig` decoding;
- structural hashing and deterministic serialization.

#### Change

- add artifact schema/version fields;
- add `TruthAssessment` helpers for strength gap and uncertainty;
- add v2 goal specification or adapters to `GoalSpecV2`;
- replace new uses of scalar `direction` with signed per-channel rails;
- extend `Operation` or add `OperationV2` containing transition model ID, risk estimate reference, packet costs, threshold, reservation policy, semantic epoch, and grounding digest;
- prohibit v2 control code from using `supported_strength` as achievement deficit;
- provide explicit v1-v2 conversion functions.

#### Review hazards

- changing v1 `to_dict()` output will break hashes and replays;
- adding default fields without schema version can silently alter artifacts;
- pressure types must remain immutable even if `FlowView` arrays are mutable.

---

### 18.2 `src/freeciv_agent/pressure/engine.py`

#### Preserve

- deterministic ordering;
- bounded hops and route count;
- conductance, compatibility, and residual gates;
- causal/procedural action-route firewall;
- trace generation;
- v1 behavior behind explicit compatibility mode.

#### Change

- split dependency transport into factor demand and premise support;
- use achievement and epistemic demand separately;
- route signed channel pressure;
- call `CompositeReverseOperator` by rule family;
- materialize `RequirementSet` demand;
- return richer `PressureResultV2` with factor, coalition, channel, and assumption traces;
- retain action-route provenance to the goal and factor chain;
- expose route features required by bridge ablations without embedding bridge calculations.

#### Review hazards

- costs must remain scheduler-level except where cost-to-go prediction explicitly requires them;
- rule shares and premise shares are different concepts;
- normalizing premise effort must not normalize away coalition demand;
- action pressure cannot traverse associative or diagnostic routes.

---

### 18.3 `src/freeciv_agent/pressure/scheduler.py`

#### Preserve

- per-goal effects;
- safety firewall;
- causal firewall;
- deterministic tie-breaking;
- cost applied once at the operation layer;
- v1 `OperationScore` compatibility.

#### Change

- compute goal-specific risk-adjusted value;
- accept typed advantage and predicted transitions;
- separate admissibility, continuous score, packet feasibility, and final commitment;
- remove any interpretation of fractional `BudgetAllocation` as executable progress;
- delegate integer reservations to `PacketScheduler`;
- report conflict mass from signed pressure;
- expose score components and signal-use ledger.

#### Review hazards

- `risk_sensitivity` must not be applied twice through both `CostVector.risk` and `RiskProfile`;
- a safety gate is not a large negative score;
- information gain is valuable only in relation to future decisions;
- the first admissible row is not necessarily packet-feasible.

---

### 18.4 `src/freeciv_agent/pressure/adapters.py`

#### Preserve

- proof-DAG adapter behavior;
- `ImpactPressureRanker` as legacy controller;
- grounded candidate category mappings;
- authoritative threat and safety grounding;
- category conductance and exact-grounding exceptions;
- current decision artifacts for v1 replay.

#### Change

- add v2 builders rather than expanding the legacy path indefinitely;
- construct explicit goal loss, risk profile, deadline state, and expected transition inputs;
- factor candidates into rule, operation, and RequirementSet nodes;
- expose observations, simulations, expansion stubs, and lifecycle operations where supported;
- attach snapshot, legal-action, context, and generation digests;
- hand off to `ImpactControlAdapter`.

#### Review hazards

- current FreeCiv heuristics encode substantial domain safety; do not duplicate them loosely in the flow package;
- category conductance is not current reachability;
- candidate-level alternatives must not be diluted merely because more legal alternatives are advertised;
- direct completion exceptions must remain grounding-specific.

---

### 18.5 `src/freeciv_agent/pressure/differentiable.py`

#### Preserve

- pressure-free truth tensors;
- clear distinction between goal adjoints and learning gradients;
- finite-difference audits;
- explicit threshold exclusion;
- symbolic requirement and counterfactual operators.

#### Change

- implement the `ReverseOperator` protocol;
- return uncertainty and health status;
- expose operator applicability predicates;
- add component-normalization metadata;
- retain exact fallback to requirement semantics.

#### Review hazards

- automatic differentiation does not authorize truth updates;
- a zero gradient can indicate a hard prerequisite, not irrelevance;
- differentiable and symbolic contributions cannot be added without a declared normalization.

---

### 18.6 `src/freeciv_agent/pressure/observation.py`

#### Preserve

- exact bounded one-step information-value calculations;
- exhaustive outcome enumeration where tractable;
- simulator identity and confidence caps;
- conservative selection-effect handling.

#### Change

- return `TypedAdvantage` and `ExpectedTransition` records;
- attach packet costs and selection propensity;
- integrate risk of misleading or delayed observations;
- expose operation nodes for the common scheduler;
- support audit-observation designation.

#### Review hazards

- entropy reduction is not automatically goal value;
- a state already present in the snapshot is not a new observation;
- selected evidence coverage must remain auditable.

---

### 18.7 `src/freeciv_agent/pressure/provenance.py`

#### Preserve

- immutable evidence tokens;
- token-set union;
- overlap and conflict semantics;
- causal ancestry;
- quarantine and proof-cycle protection.

#### Change

- add read-only risk summaries;
- add selection-exposure and coverage metrics;
- add propensity metadata for evidence acquisition;
- expose exact overlap guard to commit validation;
- keep telemetry and evidence storage in separate namespaces.

#### Review hazards

- never create an evidence token for probe success, bridge meet, or flow occupancy;
- inverse-propensity weighting is an audit method, not an automatic truth update;
- a conflict can alter operation admissibility without changing underlying evidence.

---

### 18.8 `src/freeciv_agent/pressure/lifecycle.py`

#### Preserve

- Bayesian clone update;
- visible truth and pressure projections;
- split/merge gates;
- cap, complexity, lineage, and transaction safety;
- persistent state and idempotence.

#### Change

- represent split/merge as typed structural operations;
- attach packet costs and expected transition models;
- expose clone-generation patches to flow views;
- preserve signed channel pressure per clone;
- add shadow-mode outcome logging.

#### Review hazards

- pressure concentration cannot justify a clone split by itself;
- stale clone handles must invalidate candidates;
- merging clones must not merge evidence ancestry incorrectly.

---

### 18.9 `src/freeciv_agent/pressure/induction.py`

#### Preserve

- bounded pattern mining;
- quarantined proposals;
- structure-checked analogy;
- transfer uncertainty;
- held-out replay;
- contradiction-safe promotion and demotion.

#### Change

- expose mining, proposal, validation, promotion, and demotion as separate operations;
- attach compute, simulation, expansion, and mutation packets;
- add bridge creation diagnostics without using bridge success as proof;
- report expected option value and validation cost.

#### Review hazards

- high expansion pressure is not evidence for a proposed rule;
- analogy confidence and causal authorization remain distinct;
- promotion requires current validation, not cached probe success.

---

### 18.10 `src/freeciv_agent/pressure/learning.py`

#### Preserve

- persistent conductance state;
- atomic updates;
- grounded positive credit and no-progress decay;
- direct-completion grounding exceptions;
- truth-free route learning.

#### Change

- version context-conditioned and generic conductance separately;
- store uncertainty and sample count;
- record frontier and goal-class applicability;
- add calibration records for route value, cost, success, and relief;
- expose features for the bridge-equivalence experiment;
- never merge query-specific bridge estimates into generic conductance without a validated learning rule.

---

### 18.11 `src/freeciv_agent/llm/gateway.py`

#### Preserve

- typed requests;
- prompt sanitization;
- token budget ledger;
- validation plans;
- strict quarantine;
- no-call path;
- causal events.

#### Change

- accept packet reservations from the shared ledger;
- score the proposal-validation compound operation;
- include semantic epoch, frontier stub, and bridge diagnostics;
- release or settle token and validation packets atomically;
- emit proposal topology patches only to speculative views until validation.

---

### 18.12 `src/freeciv_agent/planning/impact.py`

#### Preserve

- `GroundedImpactPlanner` candidate generation;
- all existing category-specific safety and sustainability gates;
- authoritative action grounding;
- candidate suppression and no-progress logic;
- plan materialization;
- snapshot and legal-action digests;
- execution integration.

#### Change minimally

- instantiate `ImpactControlAdapter` based on config;
- pass grounded candidates and domain facts into `ControlQuery`;
- receive `ControlDecision`;
- run `CommitValidator` before selecting the final candidate;
- attach the controller artifact to the plan;
- record controller timing and fallback diagnostics;
- preserve legacy code path exactly under `legacy_scalar`.

#### Review hazards

- avoid moving thousands of lines of domain logic into generic flow modules;
- do not let a flow candidate bypass `_no_effect_suppressed` or other existing filters;
- no new controller should alter candidate utility fields in place;
- selection remains one step in a larger authoritative plan pipeline.

---

### 18.13 `src/freeciv_agent/pf_runtime.py`

#### Preserve

- historical phase support records;
- deterministic canonical declaration;
- runtime validation;
- engine-live versus component-only distinction.

#### Change

- bump schema with backward decoder;
- add controller-layer support and activation;
- report semantic, bridge, flow, packet, and native modes separately;
- include normalization, estimator, and artifact versions;
- include fallback capabilities;
- emit one clear activation record per layer.

---

### 18.14 `src/freeciv_agent/config.py`

#### Preserve

- strict validation;
- explicit capabilities and condition ordering;
- current configuration compatibility.

#### Change

- validate nested v2, teleology, bridge, flow, packet, and safety groups;
- reject invalid mode combinations;
- distinguish benchmark-only and live-enabled settings;
- include a configuration digest in artifacts;
- support frozen profile loading for paired cohorts.

---

### 18.15 Event schemas and writers

#### Change

- add versioned payloads for new aggregate controller events;
- keep old event kinds readable;
- prohibit per-microstep event floods;
- add event-chain references from query to controller decision, validation, execution, and outcome;
- extend structural-hash tooling to all new artifacts.

---

### 18.16 Documentation

Update:

- `pf-pln.md` with scalar-v2 semantics and fallback hierarchy;
- `pf-pln-runtime.md` with actual adapter `1.33` and new controller modes;
- `pf-pln-phase-map.md` to distinguish PF phase implementation from unified controller-layer implementation;
- add bridge, flow, packet, benchmark, and operations documents;
- retain negative results and stopped gates.

---

## 19. Event, telemetry, and explanation plan

### 19.1 Event principles

Events should capture semantic boundaries and aggregated numerical blocks. Logging every probe step or advection microstep would distort performance and flood the event chain.

Required principles:

- every event has schema version, query ID, semantic epoch, topology generation, config digest, and parent event IDs;
- control artifacts use structural hashes;
- truth/evidence events are distinct from control events;
- aggregate numerical blocks include health summaries and reproducibility seeds;
- commit and outcome events link back to the exact controller decision;
- dropped telemetry may reduce observability but may not change semantics.

### 19.2 Proposed event kinds

| Event | Trigger | Essential payload |
|---|---|---|
| `teleology_estimated` | goal/cost-to-go update | goal loss, estimator, uncertainty, deadline, risk policy |
| `reverse_operator_applied` | factor-level reverse pass | rule, operator components, factor demand, assumptions |
| `requirement_set_materialized` | coalition created | rule, roles, requirements, generation reason |
| `bridge_estimated` | potential block complete | f/g/H summaries, uncertainty, policy, ESS |
| `probe_block_completed` | probe batch merged | count, meet rate, diversity, ESS, clipping, seed range |
| `path_current_deposited` | corrected path motifs updated | motif IDs, normalized weight, decay, health |
| `flow_projected` | source-sink solve complete | residual, iterations, gauge, capacity provenance |
| `attention_advected` | aggregate flow block complete | steps, mass before/after, CFL, overlap, latency |
| `packet_reserved` | reservation created | operation, typed costs, threshold, expiry |
| `packet_returned` | reservation abandoned or invalidated | operation, reason, returned quanta |
| `flow_candidate_selected` | candidate buffer emitted | operation, per-goal relief, overlap, risk, packets |
| `candidate_revalidated` | commit boundary | disposition, stale checks, guard results |
| `controller_fallback` | health or config fallback | source mode, target mode, reason, diagnostics |
| `control_outcome_recorded` | result observed | predicted/realized relief, cost, success, calibration targets |
| `selection_coverage_sample` | evidence-coverage audit | exposure, observations, updates, audit coverage |

### 19.3 Event granularity

Use one event per:

- goal/teleology update batch;
- probe block;
- projection block;
- attention block;
- packet scheduling decision;
- commit validation;
- realized outcome.

A debug-only trace may sample paths or node fields, but it is not part of the default causal event stream.

### 19.4 Telemetry storage

Store aggregate metrics such as:

- controller wall time by stage;
- node/edge counts;
- factorization and patch time;
- probe throughput;
- meet rate and ESS;
- balance residual;
- mass error;
- CFL rescale count;
- solver iterations;
- active measured/allocated/shaping dual counts;
- overlap concentration;
- packet completion and starvation;
- candidate invalidation rate;
- fallback frequency;
- predicted-versus-realized relief;
- selection coverage;
- peak memory.

Use sampling and rollups so instrumentation does not dominate the controller.

### 19.5 Checkpoints

A checkpoint need not persist every float. Store:

- semantic and topology generations;
- normalization contract;
- RNG state;
- sparse potentials and masses above threshold;
- active path-current motifs;
- reservoir, in-flight, and reservation totals;
- learned calibration summaries;
- diagnostics;
- stable semantic support of every persisted motif.

Checkpoints are control artifacts, not evidence.

---

## 20. Comprehensive test plan

### 20.1 Unit tests

#### Scalar semantics

```text
test_low_confidence_routes_to_observation_not_automatic_action
test_action_pressure_depends_on_state_deficit_not_confidence_alone
test_goal_risk_sensitivity_monotonically_changes_risky_action_priority
test_safety_tail_risk_can_hard_veto_commitment
test_pressure_addition_is_commutative
test_pressure_addition_is_associative
test_goal_cost_is_applied_exactly_once
test_deadline_urgency_and_fit_are_not_double_counted
```

#### Coalitions and packets

```text
test_and_requirement_set_retains_full_parent_demand
test_and_operation_requires_complete_prerequisite_packet_vector
test_fractional_budget_cannot_commit_an_operation
test_or_route_concentrates_packets_on_complete_candidate
test_packet_reservation_is_atomic_across_resource_types
test_abandoned_packet_reservation_returns_all_quanta
test_packet_integrality_gap_is_reported
```

#### Bridge and probes

```text
test_bridge_rejects_useful_but_unreachable_node
test_bridge_rejects_reachable_but_irrelevant_node
test_behavior_reference_ratio_is_correct
test_effective_sample_size_is_correct
test_low_ess_falls_back_or_requests_reference_probes
test_forward_and_backward_probe_legality_is_asymmetric
test_probe_telemetry_never_changes_truth_or_evidence
test_single_use_signal_contract_rejects_duplicate_bridge_feature
```

#### Flow

```text
test_path_current_has_expected_source_sink_divergence
test_virtual_return_edges_are_not_proof_edges
test_source_sink_projection_residual_is_bounded
test_projection_is_gauge_invariant
test_attention_mass_is_conserved
test_cfl_rescaling_preserves_positivity
test_forward_and_backward_dyes_use_separate_graphs
test_shaping_capacity_dual_cannot_trigger_structural_change
test_measured_capacity_dual_has_provenance
test_nonconverged_solver_cannot_emit_economic_claim
```

#### Integration and freshness

```text
test_stale_candidate_is_revalidated_before_commit
test_retired_legal_action_is_rejected
test_snapshot_digest_mismatch_triggers_regeneration
test_clone_generation_change_invalidates_candidate
test_flow_failure_falls_back_without_changing_logical_result
test_controller_mode_switch_returns_reserved_packets
test_legacy_scalar_golden_artifact_is_unchanged
```

### 20.2 Property-based tests

Generate random connected graphs, balanced source-sink vectors, legal-edge masks, and raw fields. Check:

```text
||B^T u - b|| <= tolerance
sum(mass_after) = sum(mass_before) + declared_reaction
min(mass_after) >= -tolerance
packet_spend + packet_available + packet_reserved = declared_budget
virtual edges never appear in proof reachability
aggregation result is independent of insertion order
v1 compatibility output is deterministic
```

Generate random AND/OR factor graphs and compare packet schedule against an exact small integer solver. Measure regret and ensure no incomplete operation commits.

Generate random patch sequences that are equivalent under permitted coalescing and verify identical final topology, stable IDs, and candidate validity.

### 20.3 Differential tests

Compare:

- scalar-v1 current code versus frozen golden output;
- scalar-v2 immediate-loss fallback versus v1 on fixtures without uncertainty conflicts;
- adjoint versus finite differences;
- source-sink versus lifted-reservoir formulations;
- Python projection versus exact dense solve;
- float32 versus float64 ranking;
- synchronous full rebuild versus incremental patch application;
- generic versus specialized native kernel;
- relaxed flow allocation versus exact packet solver;
- corrected versus holdout probe estimates;
- conductance-only versus explicit bridge;
- flow controller versus bridge-scalar with identical features.

### 20.4 Fault injection

Inject:

- duplicate, reordered, and dropped flow patches;
- edge retirement during a probe block;
- topology compaction while a candidate buffer exists;
- clone-generation change before commit;
- NaN or infinity from a learned predictor;
- low ESS and all clipped importance weights;
- singular or nonconvergent projection;
- dual oscillation;
- CFL violation;
- negative mass from numerical error;
- duplicate cross-shard transfer;
- packet ledger corruption;
- token reservation timeout;
- LLM proposal validation failure;
- event writer failure;
- checkpoint corruption;
- controller cancellation during compaction;
- runtime mode change during an active query.

Every fault must have a documented safe response and a test that no truth or external action is committed incorrectly.

### 20.5 Replay tests

A replay fixture includes:

- repository and ruleset identity;
- snapshot bytes or digest;
- legal-action set;
- active goals;
- config and normalization contract;
- conductance and clone state;
- seed and RNG substreams;
- patch sequence;
- controller mode;
- expected selected candidate, fallback chain, packet ledger, and structural hashes.

Replay mode should expose bounded nondeterminism explicitly if thread count or floating-point reduction order can vary.

### 20.6 Performance tests

Measure separately:

- candidate generation;
- semantic factorization;
- teleology calculation;
- bridge estimation;
- probe block;
- projection;
- advection;
- packet scheduling;
- revalidation;
- event and telemetry overhead;
- rebuild/deoptimization;
- memory.

A speed claim that excludes guards, factorization, or rebuild is invalid.

### 20.7 Test matrix by controller mode

| Test class | Legacy | Scalar-v2 | Bridge-scalar | Flow shadow | Flow live |
|---|---:|---:|---:|---:|---:|
| v1 golden replay | required | compatibility | compatibility | compatibility | compatibility |
| epistemic firewall | required | required | required | required | required |
| packets | not used | required | required | required | required |
| bridge calibration | n/a | n/a | required | required | required |
| mass conservation | n/a | n/a | n/a | required | required |
| commit revalidation | current gates | required | required | required | required |
| fallback fault tests | basic | required | required | required | required |
| paired live cohort | historical | required for claim | required for claim | no behavior change | required before release |

---

## 21. Benchmark and experimental protocol

### 21.1 Research hypotheses

Use predeclared hypotheses:

- **H1:** scalar-v2 repairs improve semantic correctness without degrading grounded decision quality.
- **H2:** whole packets and RequirementSet gates improve completed useful operations on AND, OR, and threshold tasks relative to fractional allocation.
- **H3:** explicit forward/backward bridge factors reduce work relative to conductance-conditioned one-ended search on held-out reachable-usefulness tasks.
- **H4:** corrected path currents improve long-corridor reuse relative to scalar pheromone and route-momentum baselines.
- **H5:** conserved source-sink flow and packet completion improve verified goal relief over the strong smoothed scalar baseline after full controller overhead in at least one stable regime.
- **H6:** measured-capacity duals improve scheduling around real shared bottlenecks without shaping-price artifacts.
- **H7:** bounded-stale views preserve most control benefit while exact revalidation prevents semantic or action corruption.
- **H8:** optional native specialization improves throughput after guards, patches, rebuilds, and fallback overhead.

### 21.2 Primary metric

The default primary metric is:

```text
verified goal-loss relief at fixed controller-inclusive resource budget
```

Depending on task, operationalize this as:

- completed valid proof operations;
- first valid splice time;
- deadline success;
- decision regret;
- FreeCiv turn-horizon score or scoped goal achievement;
- complete packet firings;
- expensive simulator, observation, or LLM calls avoided.

Never use relaxed attention mass or probe meet count as the primary goal-achievement metric.

### 21.3 Secondary metrics

- expensive rule firings;
- node and edge expansions;
- simulator calls;
- observations;
- LLM token cost;
- action count;
- wall time;
- energy where measurable;
- peak memory;
- controller overhead;
- false-corridor allocation;
- recovery time;
- packet starvation and integrality gap;
- candidate invalidation rate;
- calibration error;
- selection coverage;
- safety and legality violations;
- explanation completeness.

### 21.4 Equal tuning effort

Each baseline receives:

- the same development graph families;
- comparable hyperparameter search budget;
- the same PF and bridge features where applicable;
- the same packet scheduler when packet semantics are not the independent variable;
- the same controller-inclusive resource accounting;
- held-out evaluation.

Do not compare a heavily tuned flow controller with a default priority queue.

### 21.5 Synthetic benchmark families

For each family, publish generator parameters and held-out ranges:

- branch factor;
- depth;
- distractor ratio;
- corridor length;
- edge failure rate;
- conductance noise;
- context shift;
- AND arity;
- OR alternatives;
- packet thresholds;
- capacity bottlenecks;
- observation cost;
- selection bias;
- goal conflict.

### 21.6 FreeCiv benchmark families

Use fixed snapshots and paired runs covering:

- capital defense under deadline;
- treasury stabilization;
- production choice with delayed effect;
- settlement route and founding;
- tactical move with safety constraints;
- observation or simulation before commitment;
- multi-goal conflict around shared production or simulator budget;
- context change invalidating learned conductance;
- repeated route where motif reuse may help;
- candidate set expansion and contraction across turns.

Maintain strict scope for existing empirical claims. New controller claims require fresh seed-disjoint cohorts and must not be pooled with the prior pressure or expansion confirmations.

### 21.7 Bridge-equivalence statistical analysis

For the conductance-versus-bridge question, report:

- conditional ranking lift of forward factor after existing fields;
- calibration of forward reachability;
- false-positive useful-but-unreachable rate;
- route selection AUC or ranking correlation on held-out data;
- goal relief and compute cost;
- estimator overhead;
- ablation with shuffled factors;
- confidence intervals across graph families;
- transfer under context shift.

The conclusion may be:

1. bridge is independently useful;
2. bridge is useful only as a transient diagnostic;
3. context-conditioned conductance captures most bridge information;
4. neither helps enough over the scalar baseline.

All four are legitimate scientific results.

### 21.8 Controller-inclusive accounting

Include:

- snapshot extraction;
- factorization;
- model prediction;
- bridge estimation;
- probe generation and correction;
- current construction;
- projection and dual solve;
- advection;
- packet scheduling;
- revalidation;
- patch handling;
- logging;
- rebuild and fallback.

### 21.9 Parameter reporting

Publish dimensionless ranges and selected settings for:

- normalization clipping;
- bridge temperature;
- deposit gain/decay ratio;
- current-following gain;
- diffusion and turnover;
- CFL target;
- packet quantum;
- route concentration;
- capacity dual step and smoothing;
- risk aversion and tail level;
- metacontrol budget fraction.

Include local sensitivity surfaces around selected settings.

### 21.10 Stop conditions

Stop or simplify a layer when:

- it does not beat the next simpler tuned controller after overhead;
- calibration fails to transfer;
- integrality gap remains high;
- false-corridor recovery is unreliable;
- solver health frequently triggers fallback;
- live commit rejection wastes excessive compute;
- the layer complicates explanations without measurable value;
- capacity duals are dominated by shaping constraints;
- selection bias worsens without practical audit coverage.

---

## 22. Migration, compatibility, and rollout

### 22.1 Compatibility policy

- v1 truth, pressure, runtime, and decision artifacts remain readable;
- v1 hashes do not change;
- v2 artifacts have explicit schema and solver identities;
- old conductance state is imported as generic-context conductance with conservative uncertainty;
- no old state is interpreted as a calibrated bridge estimate;
- no fractional historical budget is imported as packet reservations;
- runtime declarations separate historical phase acceptance from new controller-layer status.

### 22.2 State migration

#### Conductance

Migrate each v1 conductance row to:

```text
value: historical conductance
scope: generic category or original grounding
sample_count: unknown or reconstructed
uncertainty: conservative high value
source_semantics: pf-v1
bridge_equivalence: untested
```

#### Goals

Map `GoalState` to `GoalSpecV2` using explicit defaults and record the migration policy. Do not infer a risk profile from `CostVector.risk`.

#### Pressure traces

Keep v1 traces in their original format. A v2 replay may display them through a compatibility view but cannot claim missing coalition or signed-channel details.

#### Runtime config

Default remains `legacy_scalar` until the new mode passes gates. New fields must have no behavioral effect when their controller layer is disabled.

### 22.3 Rollout phases

1. **Compile and unit test only.** New modules unreachable from live path.
2. **Offline replay.** Run scalar-v2 and bridge/flow on captured snapshots.
3. **Shadow.** Live inputs, no influence on selection.
4. **Advisory.** Influence ranking only under health and revalidation gates.
5. **Limited live.** Predeclared categories and contexts.
6. **Expanded live.** Only after fresh cohorts and safety review.
7. **Native optimization.** Only after algorithmic value and profiling.

### 22.4 Rollback

Rollback must be a configuration change, not a data migration. On rollback:

- stop accepting new queries in the disabled controller;
- return or expire outstanding packet reservations;
- checkpoint diagnostics;
- preserve durable learned state without applying it;
- use scalar-v2, legacy, or canonical fallback;
- continue exact outcome recording for postmortem analysis.

### 22.5 Deprecation

Do not remove legacy scalar code until:

- v2 has stable artifacts and replay;
- all live profiles have a tested fallback;
- historical cohorts remain reproducible;
- maintainers agree the compatibility value is lower than its cost.

Even then, retain a frozen reference implementation for scientific comparison.

---

## 23. Risk register

| Risk | Failure mode | Detection | Mitigation | Stop condition |
|---|---|---|---|---|
| Epistemic contamination | probes or pressure increase confidence | type tests, evidence audit | strict ledgers, commit-only evidence | any unexplained truth delta |
| Confidence/action conflation | uncertainty triggers world-changing action | channel tests | split achievement and uncertainty | action invariant fails |
| AND starvation | budget repeatedly funds one prerequisite | packet/coalition telemetry | RequirementSet and complete vector gate | incomplete commits or chronic starvation |
| Risk double count | risk applied in cost and goal policy | score decomposition | one declared risk path | monotonicity/calibration failure |
| Self-confirming corridor | deposits lock onto early false route | diversity, ESS, feedback ratio | holdout probes, decay, diffusion, caps | recovery outside preregistered bound |
| Bridge redundancy | `f` adds no information beyond conductance | conditional ablation | remove independent field | no held-out incremental value |
| Signal double count | H, overlap, current, PF value reused | signal-use ledger | single-use contract | duplicate uncalibrated use |
| Flow overhead | controller costs exceed benefit | wall-time accounting | scalar fallback, stop native work | no controller-inclusive win |
| Transport latency | mass crawls through long graph | steps per distance | macro-edge only after proof | loses to route-momentum baseline |
| Integrality gap | mass splits below operation threshold | gap/starvation metrics | packet scheduler, concentration | low packet completion |
| Capacity fiction | shaping cap interpreted as real scarcity | provenance audit | typed capacities | unsupported structural action |
| Dual oscillation | unstable shared-capacity prices | residual/autocorrelation | deadbands, smoothing, fallback | nonconvergence frequent |
| Stale candidate | action invalid by commit time | revalidation rejection | exact commit validator | any stale external commit |
| Dynamic topology | paths and IDs refer to retired graph | generation tests | overlays, invalidation, rebuild | dangling ID or wrong target |
| Selection bias | only high-pressure beliefs get evidence | coverage diagnostics | audit observations, exploration | blind-region coverage unacceptable |
| LLM authority leak | generated rule enters truth unverified | quarantine tests | typed proposal and validation | any quarantine escape |
| Clone overgrowth | pressure creates excessive contexts | clone cap/complexity | existing gates and shadow | cap or predictive gate bypass |
| Artifact drift | same name changes semantics | hash/schema checks | version all contracts | unreplayable result |
| Logging overhead | telemetry dominates runtime | sampled timing | aggregate blocks | logging > declared fraction |
| Native divergence | C/Rust differs from Python semantics | differential tests | Python oracle, fallback | committed mismatch |
| Cross-shard duplication | resource mass minted | transfer ledger | idempotent tokens | conservation failure |
| Overfitting | parameter region fails transfer | held-out generators | scale contract, preregistration | no transfer across families |

---

## 24. Pull-request and issue sequence

The following sequence keeps reviews bounded. Sizes are relative implementation scopes, not time estimates.

| ID | Scope | Size | Depends on | Gate contribution |
|---|---|---:|---|---|
| UIC-000 | baseline manifest, commit identity, docs drift fix | S | none | G0 |
| UIC-001 | v1 golden artifacts and replay runner | M | UIC-000 | G0 |
| UIC-002 | strong smoothed scalar baseline | M | UIC-001 | G0/G3/G4 |
| UIC-010 | achievement/uncertainty split | M | G0 | G1 |
| UIC-011 | signed pressure rails and conflict | M | UIC-010 | G1 |
| UIC-012 | risk distributions and goal-specific policy | M | UIC-010 | G1 |
| UIC-013 | deadline state and calibration | S/M | UIC-010 | G1 |
| UIC-014 | RequirementSet factor demand | L | UIC-011 | G1 |
| UIC-015 | typed packet ledger and scheduler | L | UIC-014 | G1 |
| UIC-016 | v2 schemas, runtime modes, config validation | M | UIC-010..015 | G1 |
| UIC-020 | teleology types and immediate-loss estimator | M | G1 | G2 |
| UIC-021 | expected transition registry | L | UIC-020 | G2 |
| UIC-022 | composite reverse operator interface | L | UIC-020 | G2 |
| UIC-023 | value-of-computation budget arbiter | M | UIC-015,020 | G2 |
| UIC-024 | live observation/simulation operation adapter | M | UIC-015,021 | G2 |
| UIC-025 | provenance selection-coverage monitor | M | UIC-024 | G2 |
| UIC-026 | LLM compound operation and packets | M | UIC-015,021 | G2 |
| UIC-027 | clone and induction shadow operations | L | UIC-015,021 | G2 |
| UIC-028 | typed control calibration records | M | UIC-021..027 | G2 |
| UIC-030 | flow-control model and bounded builder | L | G2 | G3 |
| UIC-031 | deeper FreeCiv candidate factorization | L | UIC-030 | G3 |
| UIC-032 | deterministic message potential estimator | M | UIC-030 | G3 |
| UIC-033 | probe engine, reference stream, ESS | L | UIC-032 | G3 |
| UIC-034 | single-use signal ledger and bridge selector | M | UIC-032,033 | G3 |
| UIC-035 | conductance-versus-bridge benchmark | L | UIC-002,031..034 | G3 |
| UIC-036 | bridge-scalar controller and fallback | M | UIC-034 | G3 |
| UIC-040 | normalization and unit contract | M | G3 | G4 |
| UIC-041 | path currents and closure policies | M | UIC-033,040 | G4 |
| UIC-042 | SciPy source-sink projection | L | UIC-040,041 | G4 |
| UIC-043 | capacity provenance and solver | L | UIC-042 | G4 |
| UIC-044 | two-dye conservative advection | L | UIC-042 | G4 |
| UIC-045 | flow-to-packet candidate readout | M | UIC-015,044 | G4 |
| UIC-046 | diagnostics, repair, fallback | M | UIC-042..045 | G4 |
| UIC-047 | complete Stage-0 ablation sandbox | XL | UIC-002,035,040..046 | G4 |
| UIC-050 | ImpactControlAdapter and ControlQuery | L | G4 or bridge-only decision | live gate |
| UIC-051 | commit validator | M | UIC-050 | live gate |
| UIC-052 | shadow mode and disagreement corpus | L | UIC-050,051 | live gate |
| UIC-053 | advisory mode | M | UIC-052 | live gate |
| UIC-054 | limited live profile and paired cohort | XL | UIC-053 | release |
| UIC-055 | explanation products and operator runbook | M | UIC-050..054 | release |
| UIC-056 | bounded-stale patches and view runtime | L | UIC-052 | scale |
| UIC-060 | portable native schemas and golden traces | M | G4 | native gate |
| UIC-061 | minimal native kernel | XL | UIC-060 | native gate |
| UIC-062 | Rust owner/patch runtime | XL | UIC-061 | native gate |
| UIC-063 | optional FlowPack/CeTTa host | XL | UIC-062 and runtime need | native gate |
| UIC-064 | multiscale acceleration | XL | UIC-061 and profiling | native gate |

### 24.1 Parallel work

After G1:

- teleology types and expected transition registry can proceed in parallel with documentation and benchmark tooling;
- provenance coverage and LLM packet integration can proceed after packet APIs stabilize;
- bridge builder and synthetic graph generator can proceed in parallel after the factor schemas freeze;
- projection and advection reference kernels can be developed on synthetic schemas while the FreeCiv factorization is reviewed, but cannot enter live integration before G3;
- native schema design can be drafted, not frozen, before G4.

### 24.2 Pull-request template additions

Every PR should state:

```text
Controller layer:
Artifact/schema versions affected:
Normative invariants touched:
Files allowed to change:
Fallback behavior:
New tests:
Golden/replay impact:
Benchmark impact:
Configuration default:
Truth/evidence impact: none | exact verified path
Packet accounting impact:
Capacity provenance impact:
Definition of done:
```

---

## 25. Definition of done

### 25.1 Scalar-v2 done

Scalar-v2 is complete when:

- achievement and uncertainty are separate;
- signed pressure is commutative;
- risk sensitivity is live and calibrated;
- deadline semantics are explicit;
- RequirementSet coalitions retain full demand;
- operations use whole packets;
- v1 compatibility and replay remain available;
- safety and causal firewalls pass;
- controller-inclusive overhead is measured.

### 25.2 Teleology done

The teleological layer is complete when:

- loss, cost-to-go, leverage, advantage, score, and packets are distinct artifacts;
- every estimator declares method and uncertainty;
- operation transitions are explicit;
- predicted and realized relief are paired;
- observation, simulation, expansion, and structural operations share the typed scheduler;
- no utility, risk, cost, or deadline term is double-counted.

### 25.3 Bridge done

The bridge layer is complete when:

- forward and backward legalities are separate;
- `f`, `g`, and `H` have calibrated semantics;
- corrected or holdout probes report ESS;
- probe telemetry remains non-evidential;
- single-use signal rules are enforced;
- the conductance-equivalence experiment is complete;
- the layer either earns incremental value or is deliberately simplified.

### 25.4 Flow done

The flow layer is complete when:

- requested and feasible currents are distinct;
- source-sink accounting works on trees and cyclic graphs;
- mass is conserved to tolerance;
- capacities have provenance;
- congestion duals are interpreted correctly;
- forward/backward advection uses separate legality;
- CFL and positivity are controlled;
- final execution is packetized;
- diagnostics and fallback are complete;
- flow beats the strong scalar baseline after overhead in a preregistered regime.

### 25.5 Live integration done

Live integration is complete when:

- the controller only ranks authoritative grounded candidates;
- every commit is current-state revalidated;
- shadow and advisory phases are complete;
- disagreement cases are reviewed;
- runtime flags and rollback are tested;
- explanations separate belief, attention, and action;
- fresh paired evaluation supports the scoped claim;
- safety and legality remain intact.

### 25.6 Native optimization done

Native optimization is complete when:

- the Python reference remains the semantic oracle;
- differential, sanitizer, and fault tests pass;
- guards and rebuild overhead are included;
- fallback and unload are safe;
- speedup is measured on controller-inclusive workloads;
- no native control field becomes authoritative truth.

---

## 26. First vertical slice

The recommended first end-to-end implementation is deliberately narrower than the whole theory. It should answer the key scientific questions with minimal infrastructure.

### 26.1 Scope

Build a Python-only vertical slice containing:

1. a synthetic typed graph generator with trees, two corridors, AND/OR factors, thresholds, and optional measured service nodes;
2. scalar-v2 achievement/uncertainty semantics;
3. RequirementSet and whole packet scheduler;
4. forward and backward reference kernels;
5. separately steered behavior probes;
6. importance-corrected or holdout bridge estimation with ESS;
7. explicit source-sink path accounting;
8. normalized semantic/probe direction mixing;
9. conservative two-dye transport;
10. a strong smoothed scalar route-momentum baseline;
11. exact small packet solver for regret measurement;
12. full controller-inclusive comparison across corridor length and false-corridor changes.

### 26.2 Success question

The slice should answer:

> Does the explicit bridge provide incremental reachability information, and does conserved transport convert that information into more completed useful operation packets than a strong scalar scheduler at equal total compute?

### 26.3 Deliverables

- transparent notebook or CLI experiments;
- reusable Python modules, not only notebook cells;
- fixed graph generators and held-out generators;
- phase diagrams for feedback stability;
- calibration plots;
- packet completion and integrality-gap plots;
- controller-overhead breakdown;
- negative regions and failure examples;
- a written G3/G4 decision.

### 26.4 What is intentionally absent

- no MORK dependency;
- no C or Rust ABI;
- no CeTTa specialization;
- no GPU;
- no live external action;
- no claim that the bridge is independent before the ablation;
- no tuning on held-out graphs.

### 26.5 Second vertical slice

Only after the first slice passes:

- wrap one captured FreeCiv snapshot family;
- factor grounded candidates and prerequisites;
- run the same controllers in replay and shadow mode;
- preserve the canonical candidate selection;
- compare bridge and flow rankings, packet completion, latency, and revalidation;
- decide whether a live advisory category is justified.

---

## 27. Appendix A - Reference unified controller pseudocode

```text
procedure UnifiedControlStep(snapshot, controller_state):
    query = build_control_query(snapshot, controller_state.config)

    # Semantic loop: truth remains authoritative and separate.
    epistemic = read_epistemic_summaries(query)
    goals = update_active_goal_specs(query, epistemic)
    losses = estimate_goal_losses(goals, epistemic)
    cost_to_go = estimate_cost_to_go(query, losses)

    semantic_graph = build_or_patch_factor_graph(
        query,
        epistemic,
        goals,
        controller_state.topology,
    )

    pf_messages = propagate_typed_teleology(
        semantic_graph,
        goals,
        losses,
        cost_to_go,
        reverse_operator_registry,
    )

    activity_budgets = budget_arbiter.allocate_next_packets(
        goals,
        pf_messages,
        controller_state.packet_ledger,
    )

    if controller_mode is scalar_v2:
        operations = enumerate_typed_operations(semantic_graph, pf_messages)
        scores = score_operations(operations, pf_messages, goals)
        schedule = packet_scheduler.schedule(scores, activity_budgets)
        return revalidate_and_select(schedule, query)

    # Bridge or flow loop.
    view = flow_view_registry.build_or_patch(
        semantic_graph,
        query,
        activity_budgets,
    )

    update_forward_backward_factors(view)
    probes = emit_probe_block(view)
    update_corrected_factor_estimators(view, probes)
    deposit_corrected_path_currents(view, probes)

    if controller_mode is bridge_scalar:
        operations = select_bridge_locations_and_operations(view, pf_messages)
        scores = score_operations(operations, pf_messages, goals)
        schedule = packet_scheduler.schedule(scores, activity_budgets)
        return revalidate_and_select(schedule, query)

    requested = build_normalized_requested_currents(
        view,
        pf_messages,
        probes,
        activity_budgets,
    )

    feasible = solve_source_sink_and_capacity_constraints(view, requested)
    if not feasible.health.acceptable:
        return fallback_to_bridge_or_scalar(query, feasible.health)

    advect_forward_backward_attention(view, feasible)
    operations = read_out_typed_operations(view, pf_messages)
    scores = score_operations(operations, pf_messages, goals)
    schedule = packet_scheduler.schedule(scores, activity_budgets)

    candidate = exact_revalidate_against_current_state(schedule, query)
    if candidate.reject:
        return return_packets_and_regenerate_or_fallback(candidate)

    decision = commit_through_existing_plan_and_execution_gate(candidate)
    record_control_prediction(decision)
    return decision
end procedure

procedure RecordOutcome(decision, before, after, authoritative_result):
    realized = measure_realized_goal_relief(before, after, decision.goals)
    update_transition_calibration(decision.prediction, realized)
    update_conductance_and_resolvability(decision, realized)
    update_probe_and_motif_reliability(decision, realized)
    update_cost_and_latency_models(decision, authoritative_result)
    update_selection_coverage(decision)
    never_update_truth_from_control_telemetry()
end procedure
```

---

## 28. Appendix B - Example controller configuration

```yaml
impact_policy:
  pressure_enabled: true
  pressure_controller_mode: unified_shadow
  pressure_semantics_version: v2
  pressure_scalar_fallback_enabled: true

  pressure_v2:
    achievement_uncertainty_split: true
    signed_channels: true
    distributional_risk: true
    requirement_sets: true
    packet_scheduler: true

  teleology:
    estimator: calibrated_one_step
    fallback_estimator: immediate_loss
    max_horizon: 6
    calibration_required_for_live: true
    metacontrol_budget_fraction: 0.05
    base_progress_fraction: 0.20
    exploration_fraction: 0.10

  bridge:
    enabled: true
    estimator_policy: holdout
    deterministic_message_depth: 8
    behavior_probe_count: 512
    reference_probe_count: 128
    maximum_probe_depth: 12
    maximum_importance_weight: 20.0
    minimum_effective_sample_size: 48.0
    clipped_weight_fraction_limit: 0.20
    temperature: 1.0
    route_momentum: 0.10
    deposit_gain: 0.05
    deposit_decay: 0.10
    diversity_floor: 0.10

  flow:
    enabled: true
    implementation: python_reference
    semantic_direction_weight: 0.60
    probe_direction_weight: 0.40
    turnover_fraction: 0.25
    time_step: 0.10
    cfl_limit: 0.80
    attention_diffusion: 0.03
    projection_tolerance: 1.0e-8
    mass_tolerance: 1.0e-8
    maximum_microsteps: 16
    maximum_nodes: 4096
    maximum_edges: 16384
    maximum_structural_patches_per_block: 64

  capacities:
    enable_shared_solver: false
    structural_change_from_measured_only: true
    dual_smoothing: 0.10
    dual_deadband: 1.0e-4

  packets:
    budgets:
      cpu: 64
      exact_rule: 8
      observation: 2
      simulation: 4
      action: 1
      expansion: 1
      llm_token: 0
      memory: 8
    reservation_ttl_turns: 2
    backup_route_fraction: 0.10
    exact_small_solver_for_audit: true

  safety:
    commit_revalidation: true
    hard_tail_risk_gate: true
    tail_level: 0.95
    risk_hysteresis: true
    allow_flow_candidate_under_degraded_health: false

  telemetry:
    aggregate_probe_blocks: true
    aggregate_attention_blocks: true
    sample_path_fraction: 0.01
    emit_explanations: true
    deterministic_replay: true
```

The default production profile remains `legacy_scalar` until the relevant gates pass.

---

## 29. Appendix C - Coding-agent work order template

```text
Task ID:
Component:
Objective:
Why this task exists:
Non-goals:
Normative invariants:
Controller mode(s) affected:
Artifact/schema versions affected:
Inputs and existing interfaces:
Files allowed to change:
Required public API:
Reference equations or algorithms:
Compatibility requirements:
Fallback behavior:
Tests to add:
Golden or replay impact:
Benchmarks to record:
Telemetry/events to add:
Failure behavior:
Documentation updates:
Definition of done:
Review checklist:
```

Coding agents must not broaden scope, weaken a safety or epistemic invariant, or change benchmark semantics merely to make an implementation pass.

---

## 30. Appendix D - Review checklist

Before accepting a change, reviewers should answer:

1. Does the change preserve truth, teleology, bridge, and resource separation?
2. Can any control quantity directly alter truth or evidence?
3. Are achievement deficit and epistemic uncertainty still separate?
4. Are positive and negative channel demands aggregated commutatively?
5. Does an AND rule retain coalition demand and require complete prerequisites?
6. Does every effective operation consume whole typed packets?
7. Is risk goal-specific, distribution-sensitive, and applied exactly once?
8. Are deadlines and urgency counted exactly once?
9. Are forward and backward legal transitions distinct?
10. Are virtual accounting edges excluded from proof, causal, and evidence traversal?
11. Are bridge and probe signals used only once or residualized with held-out evidence?
12. Are behavior/reference semantics and ESS visible?
13. Does resource mass balance, including reservations and in-flight state?
14. Are capacity duals interpreted according to provenance?
15. Is the candidate tied to stable identity, epoch, and legal-action digest?
16. Is the commit path current-state revalidated?
17. Does failure degrade to a simpler safe controller?
18. Can the behavior be replayed from a fixed snapshot, seed, and patch trace?
19. Are controller overhead and logging cost measured?
20. Does the new complexity earn value in an ablation or preserve a required invariant?
21. Are selection propensity and evidence coverage visible?
22. Are LLM and induction proposals still quarantined?
23. Does the change preserve existing FreeCiv domain safety gates?
24. Are new claims based on a fresh, predeclared cohort?
25. Could a simpler scalar implementation provide the same measured benefit?

---

## 31. Appendix E - Anti-patterns

Do not:

- store probe, flow, or congestion state as truth atoms;
- reuse `pressure` as an untyped name for demand, current, and hydraulic dual;
- compute action deficit from `strength × confidence`;
- collapse opposing goal demands into the direction of whichever update arrived first;
- split an AND parent’s importance and then forget the coalition;
- commit a fraction of a proof, observation, simulation, LLM call, or action;
- treat bridge height, probe count, overlap, flow alignment, and PF value as independent multiplicative evidence;
- use backward edges by automatically reversing every forward edge;
- project an open path on a tree into a zero cycle space and call zero a route;
- add virtual resource edges to proof or causal traversal;
- infer physical scarcity from a shaping cap;
- interpret a nonconverged dual as a meaningful price;
- let an LLM proposal enter evidence because probes found it useful;
- rebuild the entire graph for every scalar update;
- make a mutable FlowView authoritative for semantic identity;
- expose raw local array positions in durable candidates;
- commit from a stale candidate without revalidation;
- hide flow latency or controller overhead;
- compare against an intentionally weak scalar baseline;
- tune on held-out generators;
- freeze a native ABI before the Python scientific gate;
- build GPU or distributed infrastructure to rescue a negative algorithmic result;
- erase negative results from the runtime or phase documentation.

---

## 32. Appendix F - Source basis and interpretation boundaries

This plan is grounded in two materials:

1. the uploaded July 2026 design document *Pressure, Value, and Flow: A Unified Theory and Architecture for Goal-Directed Inference Control*;
2. the reviewed `experimental/pln-pressure` branch snapshot at commit `9b1c2c8ec071a3d1db18f67a8e5c8b709737c46e`.

The uploaded document explicitly describes a research proposal rather than a completed unified formalism. Accordingly, this plan preserves its scientific gates, Python-first ablation strategy, scale contract, packet semantics, capacity provenance, evidence firewall, and fallback discipline. It does not assume that fluid transport will outperform the scalar controller.

Repository-specific recommendations in this plan are implementation inferences based on the reviewed code structure. In particular:

- the current branch is treated as the scalar baseline;
- the current `GroundedImpactPlanner` remains authoritative for grounded candidate generation and plan materialization;
- the current phase map is not reinterpreted as proof that the newer bridge and flow layers are engine-live;
- MORK, Rust, C, and CeTTa are conditional acceleration options rather than immediate repository dependencies;
- the bridge-conductance relationship remains an empirical question resolved at Gate G3.

---

## 33. Final implementation decision

The recommended path is not “implement every layer of the unification immediately.” It is:

1. **freeze the current branch as a reproducible scalar baseline;**
2. **repair its scalar semantics;**
3. **make discrete operation packets and coalition completion real;**
4. **represent cost-to-go, leverage, advantage, risk, and deadlines explicitly;**
5. **connect existing component-only capabilities through the same typed scheduler;**
6. **test whether forward bridge reachability adds information beyond Hebbian conductance and existing utility fields;**
7. **implement conserved flow only if the bridge earns value and transport beats the strongest scalar baseline after overhead;**
8. **integrate through shadow, exact revalidation, and narrow live cohorts;**
9. **optimize natively only after algorithmic value is established.**

This sequence preserves what is already strong in the branch while making the unified theory falsifiable, implementable, and safe. It also keeps open the scientifically important simplification: the final successful system may be scalar PF-v2 plus packets, PF-v2 plus an explicit bridge, or the complete pressure-bridge-flow controller. The architecture should follow the evidence.
