# Implementation Plan: Grounded Freeciv Domain Estimates and Operation Coordination for PLN-Pressure–Bridge–Fluid

**Repository:** `machieke/freeciv-omegaclaw`
**Target branch:** `experimental/pln-pressure–bridge–fluid`
**Review basis:** commit `87f3482e631b0713378e69b350e460d4c6a310b7` and the branch status/evidence documents present on 2026-07-30
**Plan status:** Completed grounded implementation program
**Compatibility target:** Python 3.8+; all new live behavior disabled by default
**Primary objective:** Ground pressure decisions in Freeciv-specific transition estimates and coordinate indivisible, identity-bearing game resources without prematurely restoring bridge or conserved-flow policy authority

---

## 1. Executive decision

The next implementation should **not** begin by re-enabling bridge selection, source–sink flow, or generic path persistence as live authorities.

The branch already established an important negative result: corrected bridge/flow machinery did not demonstrate reliable live gameplay value, and generic path-persistence follow-ons did not survive their fresh evaluation gates. That evidence must remain part of the design, rather than being bypassed by another scoring layer.

The next program should instead repair the semantic and operational foundations that bridge and flow would need:

1. Replace relative utility used as a proxy for success probability with grounded, candidate-invariant transition estimates.
2. Reuse the existing `ExpectedTransition` and `PredictedOutcome` types as the canonical prediction representation.
3. Introduce identity-bearing and time-indexed resource claims for units, cities, tiles, transport capacity, treasury, and controller capacity.
4. Represent multi-step activity as explicit operations with participants, requirements, progress, expiry, and failure semantics.
5. Retain Freeciv’s strong local algorithms—pathfinding, combat calculation, city allocation, and dependency processing—as domain estimators or exact subproblem solvers.
6. Validate the architecture through narrow vertical slices, beginning with city defence, then multi-unit combat, then ferry/founder coordination.
7. Permit bridge or conserved-flow machinery to return to live consideration only after a fresh experiment shows that the remaining error is specifically a route/capacity-allocation error that simpler exact schedulers cannot solve.

The intended supported path after this program is:

```text
authoritative snapshot + advertised legal actions + ruleset IR
    -> candidate generation
    -> grounded domain transition models
    -> typed teleological advantage
    -> explicit operation assembly
    -> identity/time resource scheduling
    -> next legal operation step
    -> exact current-state commit revalidation
    -> execution
    -> outcome resolution and calibration
```

Bridge and conserved flow remain downstream experimental consumers of the same operation/resource graph:

```text
grounded operations + resource graph
    -> bridge shadow analysis
    -> conserved-flow shadow analysis
    -> fresh evidence gate
    -> optional bounded advisory authority
```

---

## 2. Why this follow-on is necessary

### 2.1 What the current branch already gets right

The current branch contains substantial infrastructure that should be retained:

- scalar PF-v2 scoring and typed pressure semantics;
- `RequirementSet` support;
- whole-packet scheduling and atomic reservation at the current abstract resource level;
- exact commit revalidation against the current snapshot and advertised legal actions;
- transition prediction types with explicit outcome probabilities and residual unknown mass;
- teleological loss, cost-to-go, leverage, and typed-advantage concepts;
- calibration ledgers and transition-value support gates;
- bridge and flow feature gates;
- fail-closed runtime configuration;
- outcome feedback separated from truth revision;
- extensive experiment and evidence documentation.

The implementation plan therefore extends the branch rather than replacing it.

### 2.2 The semantic gap

`ImpactCandidate.utility` is currently a broad desirability score. In the pressure adapter, category-relative utility has also been used to derive `success_probability`. This causes one number to perform incompatible roles:

- legacy action desirability;
- estimated probability of an effect;
- premise or route weight;
- scheduler cost or priority;
- indirect opportunity-cost signal.

That is not stable under changes to the candidate set. Adding a stronger unrelated candidate can lower another candidate’s derived “probability” without changing the state, actor, target, or action. A probability estimate must instead be intrinsic to the action and context.

### 2.3 The resource gap

The current packet scheduler conserves abstract quanta such as `ACTION` and `CPU`. It cannot express that:

- unit `143` cannot defend two cities in the same turn;
- city `7` has one production slot;
- ferry `82` has two seats over a particular interval;
- two operations require the same tactical tile;
- a future move depends on movement points that do not yet exist;
- a treasury claim competes with another purchase;
- a particular participant must remain attached to one operation.

This prevents the scheduler from representing the real cause of many Freeciv coordination failures.

### 2.4 The operation gap

A ranked action is not the same as a persistent operation. An overseas settlement may require:

- a founder;
- a ferry;
- a pickup location;
- a landing location;
- a safe path;
- possibly an escort;
- several legal actions over multiple turns.

Generic score persistence is insufficient because it lacks explicit participants, prerequisites, progress, cancellation conditions, and resource ownership. Persistence should be attached to a structured operation, not to an opaque score path.

### 2.5 The domain-grounding gap

Freeciv already has well-defined local subproblems:

- movement cost and route feasibility;
- combat probabilities and expected material outcomes;
- city defence assignment;
- city worker allocation;
- technology dependencies;
- production availability.

PLN-pressure should not approximate these with an undifferentiated fluid metaphor. It should consume their outputs as grounded estimates and coordinate across them.

---

## 3. Scope

### 3.1 In scope

This program covers:

- a typed transition-estimate envelope around the existing transition types;
- a domain transition-model registry;
- movement, combat, defence, production, and transport model interfaces;
- candidate-invariant probability and expected-relief semantics;
- identity- and time-bearing resource claims;
- a deterministic resource-capacity extractor;
- exact bounded resource assignment for narrow vertical slices;
- explicit multi-turn operation lifecycle;
- city-defence coordination;
- multi-unit combat coordination;
- ferry/founder coordination;
- contextual transition calibration and conductance;
- observability, replay, and evaluation;
- feature flags, fallback, migration, and rollback;
- a conditional bridge/flow re-entry protocol.

### 3.2 Explicitly out of scope

The following are not goals of the initial implementation:

- replacing Freeciv’s tile pathfinder with a pressure-fluid simulation;
- replacing combat rules with learned black-box prediction;
- allowing uncalibrated bridge or flow scores to reorder live actions;
- treating evidence, truth, utility, pressure, and resource flow as one scalar;
- generic cross-turn score hysteresis;
- live online learning during a controlled evaluation cohort;
- off-policy causal claims from ordinary game logs;
- copying Freeciv GPL implementation code into the MIT-licensed OmegaClaw repository;
- a global optimal plan for the entire game;
- adding hidden-information access not available to the player;
- declaring success solely from a small win-rate change.

---

## 4. Design invariants

These invariants are mandatory and should be encoded as tests where practical.

### 4.1 State and legality

1. The authoritative snapshot and server-advertised legal actions remain the source of truth.
2. No estimator may infer access to hidden map, unit, city, diplomatic, or ruleset state.
3. Every committed step must pass the existing current-state revalidation boundary.
4. A prediction that was valid for snapshot `S` is not automatically valid for snapshot `S+1`.
5. A ruleset change invalidates every estimate whose semantics depend on that ruleset.

### 4.2 Semantic separation

1. Legacy utility is not probability.
2. Outcome probability is not truth confidence.
3. Expected relief is not route conductance.
4. Pressure is not a conserved physical resource.
5. Evidence is not consumed by being used.
6. Resource capacity is conserved only within its declared identity and time window.
7. Unknown outcome mass is explicit; it must not be silently assigned to success.
8. Success probability must not be multiplied twice when expected relief is already integrated over outcomes.

### 4.3 Candidate invariance

For a fixed state and fixed action:

- adding a dominated candidate cannot change the action’s intrinsic transition estimate;
- duplicating another candidate cannot change the action’s transition estimate;
- permuting candidates cannot change any intrinsic estimate;
- multiplying all legacy utility values by a positive constant cannot change typed probabilities.

Resource competition may change the selected plan, but not the intrinsic prediction.

### 4.4 Authority and fallback

1. Estimators may abstain.
2. Missing input must produce an explicit abstention or lower authority, not fabricated precision.
3. Winner-changing typed authority is allowed only when every relevant comparison has approved support.
4. If a required live estimate is unsupported, the entire decision falls back to the frozen supported comparator.
5. A partial mixture of calibrated and uncalibrated values must not silently change a winner.
6. All new live paths are disabled by default.

### 4.5 Resource commitments

1. Current-turn authoritative resources may be hard-reserved.
2. Future-turn capacities are forecasts and must be represented as conditional or soft claims.
3. An operation cannot reserve a resource that does not exist in the authoritative snapshot.
4. Every reservation has an owner, time window, quantity, source, and release path.
5. Failed commit revalidation releases all current-step reservations.
6. No unit, city slot, seat, or exclusive tile may be hard-reserved beyond capacity.
7. Resource scheduling is deterministic under identical inputs.

### 4.6 Operation persistence

1. Persistence belongs to a structured operation, never to a bare score.
2. An operation has explicit participants, target, requirements, steps, progress, and expiry.
3. Only the next legal step is committed.
4. Multi-turn execution is not assumed transactional.
5. Every later step is re-estimated and revalidated.
6. Operations may block, suspend, fail, expire, or be abandoned for explicit reason codes.
7. A new candidate may replace an operation only under predeclared replacement rules.

### 4.7 Experimental discipline

1. The current supported comparator remains frozen during each evaluation.
2. Diagnostic, pilot, and confirmation seeds are disjoint.
3. Hyperparameters are frozen before confirmation.
4. Controller-inclusive latency is measured.
5. Negative results are retained.
6. Bridge or flow cannot claim value from a candidate-generation improvement supplied by another component.
7. No post-result retuning is presented as confirmation.

---

## 5. Licensing boundary

OmegaClaw is MIT-licensed, while upstream Freeciv code is GPLv2. This creates a hard implementation constraint.

### 5.1 Permitted approach

The repository may use:

- independently written algorithms based on publicly documented game rules;
- authoritative protocol-visible state;
- ruleset data and compiled ruleset IR;
- clean-room formulations of mathematical algorithms;
- subprocess-based or separately distributed native parity executables for testing, subject to legal review;
- black-box differential tests against a separately installed Freeciv binary;
- recorded input/output fixtures whose redistribution is legally permitted.

### 5.2 Prohibited approach

Do not:

- copy Freeciv C source into the MIT tree;
- mechanically translate GPL functions into Python or Rust;
- paste GPL comments or test vectors that are creative expressions rather than facts;
- link or embed GPL code into the MIT deliverable without an explicit legal and distribution decision;
- obscure provenance.

### 5.3 Required repository control

Add `docs/licensing/freeciv_algorithm_boundary.md` before implementing path or combat parity. It must record:

- which behavior is derived from game rules;
- which implementation was written independently;
- whether any native tool is separately distributed;
- which fixtures are generated;
- reviewer sign-off before merge.

---

## 6. Current-to-target architecture

### 6.1 Current simplified path

```text
ImpactCandidate
    utility
    category
    untyped projection
        |
        v
pressure adapter
    category utility ceiling
    relative utility -> success_probability
    category conductance
        |
        v
scalar PF-v2 / packets
        |
        v
commit validator
```

### 6.2 Target path

```text
AuthoritativeSnapshot
LegalActionSet
RulesetIR
      |
      +----------------------+
      |                      |
      v                      v
Impact candidate       Domain input extraction
generation                    |
      |                       v
      +--------------> DomainTransitionModelRegistry
                              |
                              v
                   GroundedTransitionEstimate
                    - ExpectedTransition
                    - context key
                    - authority
                    - confidence
                    - validity
                    - provenance
                              |
                              v
                   Teleological advantage
                              |
                              v
                      OperationAssembler
                    - explicit participants
                    - requirements
                    - operation steps
                    - current hard claims
                    - future soft claims
                              |
                              v
                   ResourceCapacityExtractor
                              |
                              v
                 DeterministicResourceScheduler
                              |
                              v
                   next grounded legal step
                              |
                              v
                  exact commit revalidation
                              |
                              v
                           execute
                              |
                              v
             outcome resolution + calibration ledger
```

### 6.3 Experimental consumers

```text
Grounded operation graph
    |
    +--> bridge membership shadow
    |
    +--> source-sink flow shadow
    |
    +--> disagreement and residual-error analysis
```

Neither experimental consumer receives live authority merely because it can consume the new graph.

---

## 7. Canonical data contracts

The branch already has `ExpectedTransition` and `PredictedOutcome`. They should remain canonical. Do not add a competing outcome hierarchy.

### 7.1 Estimate authority

Create `src/freeciv_agent/planning/domain_models/context.py`:

```python
from enum import Enum


class EstimateAuthority(str, Enum):
    EXACT_AUTHORITATIVE = "exact_authoritative"
    DETERMINISTIC_DERIVED = "deterministic_derived"
    CALIBRATED = "calibrated"
    HEURISTIC = "heuristic"
    LEGACY_PROXY = "legacy_proxy"
    ABSTAIN = "abstain"
```

Meanings:

| Authority | Meaning | Eligible for live typed authority |
|---|---|---:|
| `EXACT_AUTHORITATIVE` | Directly implied by authoritative state/rules | Yes |
| `DETERMINISTIC_DERIVED` | Deterministic clean-room solver over complete authoritative inputs | Yes after parity tests |
| `CALIBRATED` | Frozen model meeting predeclared support and calibration gates | Yes within approved scope |
| `HEURISTIC` | Bounded domain heuristic without calibration authority | Shadow/advisory only |
| `LEGACY_PROXY` | Existing utility-derived compatibility estimate | Legacy comparator only |
| `ABSTAIN` | Required information or support absent | No |

### 7.2 Context key

```python
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TransitionContextKey:
    schema_version: int
    action_category: str
    action_type: str
    goal_id: str
    lifecycle_state: str
    actor_class: Optional[str]
    target_class: Optional[str]
    threat_regime: Optional[str]
    terrain_bucket: Optional[str]
    horizon_bucket: str
    ruleset_digest: str
```

Rules:

- every field has a stable normalization function;
- IDs that would fragment support are represented by classes, not raw object IDs;
- raw actor/target IDs belong in event metadata, not calibration keys;
- unknown values are explicit canonical tokens, not empty strings;
- key schema changes require a version bump.

### 7.3 Validity envelope

```python
@dataclass(frozen=True)
class EstimateValidity:
    snapshot_id: str
    legal_actions_digest: str
    ruleset_digest: str
    estimated_at_turn: int
    valid_through_turn: int
```

Default `valid_through_turn` for a current action is the current turn. Multi-turn operations receive new estimates each turn.

### 7.4 Grounded estimate envelope

```python
from dataclasses import dataclass
from typing import Optional, Tuple

from freeciv_agent.pressure.transitions import ExpectedTransition


@dataclass(frozen=True)
class GroundedTransitionEstimate:
    transition: ExpectedTransition
    context_key: TransitionContextKey
    authority: EstimateAuthority
    confidence: float
    validity: EstimateValidity
    estimator_id: str
    estimator_version: str
    provenance: Tuple[str, ...]
    abstention_reason: Optional[str] = None
```

Validation:

- `0 <= confidence <= 1`;
- outcome probability plus residual unknown mass equals one within tolerance;
- every outcome identifies the effects needed to compute goal relief;
- `ABSTAIN` requires `abstention_reason`;
- live-approved authorities require matching snapshot, legal-action, and ruleset digests;
- an estimate cannot claim exact authority while retaining unknown mass caused by missing inputs.

### 7.5 Domain model protocol

Create `src/freeciv_agent/planning/domain_models/base.py`:

```python
from typing import Protocol


class DomainTransitionModel(Protocol):
    model_id: str
    model_version: str

    def supports(self, request: "DomainEstimateRequest") -> bool:
        ...

    def estimate(
        self,
        request: "DomainEstimateRequest",
    ) -> "GroundedTransitionEstimate":
        ...
```

`DomainEstimateRequest` includes:

- immutable authoritative snapshot view;
- ruleset IR;
- legal-action record;
- candidate;
- applicable goals and current goal losses;
- current operation context, when any;
- deterministic request ID.

The registry selects by declared action types and validates that exactly one approved model has authority. Multiple shadow models may run for comparison.

### 7.6 Legacy candidate compatibility

Retain `ImpactCandidate.utility` during the migration. Its semantic name in all new code is:

```text
legacy_domain_utility
```

`projection` remains readable for compatibility, but no new model may depend on undocumented projection keys. Where candidate generation knows a fact that cannot be reconstructed from the snapshot, add a small typed feature object:

```python
@dataclass(frozen=True)
class CandidateDomainFeatures:
    schema_version: int
    actor_id: Optional[str]
    target_id: Optional[str]
    advertised_action_id: Optional[str]
    intent_tags: Tuple[str, ...]
```

Do not place probabilities or final scores in this object.

---

## 8. Transition and teleological semantics

### 8.1 Expected goal relief

For goal \(g\), current state \(s\), and predicted outcome \(o\):

\[
\Delta L_g(o) = L_g(s) - L_g(s_o)
\]

The expected relief is:

\[
\mathbb{E}[\Delta L_g \mid s,a]
=
\sum_o P(o \mid s,a)\Delta L_g(o)
\]

Unknown mass receives no invented positive relief. Depending on the safety policy, it may receive:

- zero relief for neutral planning;
- a bounded adverse-loss reserve for safety-critical goals;
- explicit tail-risk treatment.

### 8.2 No double probability

If `ExpectedTransition` already contains outcome probabilities, teleological scoring must not multiply by a second `operation.success_probability`.

Replace semantics of the form:

```text
pressure × success_probability × relief_scale
```

with:

```text
pressure × expected_relief_from_transition
```

or, when an operation has a conditional effect not represented in the transition, make that condition an explicit outcome branch.

### 8.3 Typed operation bid

A bounded operation bid may be expressed as:

\[
B(a,g)
=
P_g
\cdot
\mathbb{E}[\Delta L_g \mid s,a]
\cdot
D(T_a)
\cdot
C(a,g,\chi)
-
\lambda_g R(a,g)
-
\Pi(a)
\]

where:

- \(P_g\) is unresolved goal pressure;
- \(\mathbb{E}[\Delta L_g]\) is grounded expected relief;
- \(D(T_a)\) is temporal/deadline fit;
- \(C(a,g,\chi)\) is contextual conductance;
- \(R(a,g)\) is downside/tail risk;
- \(\Pi(a)\) is the shadow price or explicit opportunity cost of claimed resources.

Each term has one meaning. None is derived by normalizing against unrelated candidates.

### 8.4 Fail-closed comparison

For typed authority mode:

1. Identify all candidates capable of changing the winner relative to the frozen comparator.
2. Require an approved estimate for each relevant candidate.
3. If any is missing, stale, invalid, or below support threshold, return the comparator’s complete ordering.
4. Record the reason and unsupported comparison set.
5. Never mix a typed winner with a legacy-relative probability for its strongest competitor.

---

## 9. Identity- and time-bearing resource model

### 9.1 New resource types

Create `src/freeciv_agent/pressure/resource_claims.py`:

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class GameResourceKind(str, Enum):
    ACTOR = "actor"
    MOVE_POINTS = "move_points"
    CITY_PRODUCTION_SLOT = "city_production_slot"
    TILE_OCCUPANCY = "tile_occupancy"
    TRANSPORT_SEAT = "transport_seat"
    TREASURY = "treasury"
    RESEARCH_SLOT = "research_slot"
    DIPLOMATIC_COMMITMENT = "diplomatic_commitment"
    ACTION_BUDGET = "action_budget"
    CPU = "cpu"


class ClaimHardness(str, Enum):
    HARD_CURRENT = "hard_current"
    CONDITIONAL_FUTURE = "conditional_future"
    ADVISORY = "advisory"


@dataclass(frozen=True)
class ResourceRef:
    kind: GameResourceKind
    owner_id: str
    subresource: Optional[str]
    scope: str


@dataclass(frozen=True)
class TurnWindow:
    start_turn: int
    end_turn_exclusive: int


@dataclass(frozen=True)
class ResourceClaim:
    resource: ResourceRef
    quantity: int
    window: TurnWindow
    hardness: ClaimHardness
    exclusive: bool
    source_operation_id: str
    source_step_id: str


@dataclass(frozen=True)
class ResourceCapacity:
    resource: ResourceRef
    quantity: int
    window: TurnWindow
    snapshot_id: str
    authority: str
```

### 9.2 Examples

```text
ACTOR / unit:143 / whole_actor / player:2 / turn 40..41 / quantity 1
MOVE_POINTS / unit:143 / current_turn / player:2 / turn 40..41 / quantity 3
CITY_PRODUCTION_SLOT / city:7 / production / player:2 / turn 40..41 / quantity 1
TRANSPORT_SEAT / unit:82 / cargo / player:2 / turn 42..45 / quantity 2
TILE_OCCUPANCY / tile:18:11 / military_stack / map / turn 43..44 / quantity ruleset_limit
TREASURY / player:2 / gold / player:2 / turn 40..41 / quantity 35
```

### 9.3 Hard and future claims

Current-turn claims are based on authoritative capacities. Future claims are predictions:

- `HARD_CURRENT`: may block another live action now;
- `CONDITIONAL_FUTURE`: contributes to operation feasibility and replacement cost but cannot manufacture future authority;
- `ADVISORY`: used only for shadow analysis.

A future ferry seat is not guaranteed merely because an operation expects the ferry to arrive. Each turn converts only the next eligible claim to hard status after re-estimation and revalidation.

### 9.4 Compatibility with existing packets

Keep `PacketCost`, `PacketBudget`, and `PacketScheduler` unchanged as version 1. Add a compatibility adapter:

```text
legacy PacketCost
    -> anonymous ResourceClaim
```

This permits existing tests and supported behavior to remain stable. New operation paths use the v2 resource scheduler.

### 9.5 Deterministic scheduler

Create `src/freeciv_agent/pressure/resource_scheduler.py` with two backends:

1. `GreedyIdentityScheduler`: deterministic density/priority ordering with identity-aware conflict checks.
2. `BoundedExactScheduler`: branch-and-bound over the candidate operation set, with deterministic tie-breaking and a strict node/time budget.

For city defence, also provide a dedicated bipartite or min-cost assignment solver. Do not force every subproblem through a generic fluid solver.

Objective:

```text
maximize total approved operation bid
subject to all hard current capacities
and all RequirementSets
and protected safety constraints
```

Required outputs:

- selected operations;
- rejected operations and conflict reasons;
- reservation ledger;
- optimality status: exact, bounded, or greedy fallback;
- explored-node count;
- latency;
- deterministic digest of input and result.

---

## 10. Operation model and lifecycle

### 10.1 Files

Create:

- `src/freeciv_agent/planning/operations.py`
- `src/freeciv_agent/planning/operation_store.py`
- `src/freeciv_agent/planning/operation_assembler.py`

### 10.2 Operation states

```python
class OperationState(str, Enum):
    PROPOSED = "proposed"
    RESERVABLE = "reservable"
    RESERVED = "reserved"
    ACTIVE = "active"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"
    EXPIRED = "expired"
```

### 10.3 Operation contract

```python
@dataclass(frozen=True)
class OperationParticipant:
    role: str
    actor_id: str
    actor_class: str
    required: bool


@dataclass(frozen=True)
class OperationStep:
    step_id: str
    action_type: str
    actor_role: str
    target_ref: Optional[str]
    requirement_set_id: str
    completion_predicate_id: str
    maximum_attempts: int


@dataclass(frozen=True)
class OperationSpec:
    schema_version: int
    operation_id: str
    operation_type: str
    goal_ids: Tuple[str, ...]
    participants: Tuple[OperationParticipant, ...]
    target_ref: Optional[str]
    steps: Tuple[OperationStep, ...]
    created_turn: int
    expiry_turn: int
    replacement_margin: float
    provenance: Tuple[str, ...]
```

Mutable progress belongs in a separately persisted state record:

```python
@dataclass
class OperationProgress:
    operation_id: str
    state: OperationState
    current_step_index: int
    attempt_count: int
    blocked_reason: Optional[str]
    last_snapshot_id: str
    last_updated_turn: int
```

### 10.4 Stable identity

Generate `operation_id` from a canonical digest of:

- operation type;
- goal set;
- participant role IDs;
- target;
- ruleset digest;
- creation epoch or turn.

Do not include a volatile scalar score.

### 10.5 Replacement rules

An active operation is replaced only when one of these applies:

- a hard requirement is false;
- a participant no longer exists or is no longer controllable;
- the next step is no longer legal and no bounded repair route exists;
- the deadline is impossible;
- the operation’s approved expected relief falls below zero;
- a competing operation exceeds it by the frozen replacement margin after accounting for sunk and switching costs;
- a safety override applies;
- expiry or attempt limit is reached.

Every replacement emits a reason code.

### 10.6 Next-step execution

At each turn:

1. Load active operation.
2. Resolve participants and target against the current snapshot.
3. Re-estimate the next step.
4. Recompute current hard claims.
5. Compete for current resources.
6. Revalidate the selected legal action.
7. Commit one step.
8. Release consumed/current reservations.
9. Update progress from the authoritative next snapshot.

This is persistent coordination without pretending the future is transactionally reserved.

---

## 11. Work program

The work is divided into ten gated stages. Each stage merges with flags off unless explicitly stated.

---

# GDO-0 — Freeze the comparator and baseline

## Objective

Create a reproducible baseline before changing semantics.

## Tasks

1. Record the exact target commit, dependency lock, ruleset set, engine version, default feature flags, and supported decision path.
2. Run the complete existing test suite.
3. Run existing engine-live baseline cohorts with fixed seeds.
4. Save controller-inclusive latency distributions.
5. Export representative captured snapshots for:
   - city under immediate threat;
   - multiple cities competing for defenders;
   - legal attack choices;
   - transport/founder situations;
   - production and research choices.
6. Freeze comparator IDs:
   - `B0`: canonical Impact baseline;
   - `B1`: current scalar PF-v2 plus current whole-packet scheduler.
7. Add a machine-readable baseline manifest.

## Files

- `docs/evidence/gdo/baseline_manifest.md`
- `benchmarks/gdo/baseline_manifest.json`
- `benchmarks/gdo/captured_snapshots/`
- `scripts/run_gdo_baseline.py`
- no policy code changes

## Tests

- baseline manifest schema;
- snapshot replay determinism;
- feature-flag digest determinism;
- test-suite status included in manifest.

## Exit gate

- clean full test suite;
- repeatable comparator results on two runs;
- no unexplained replay divergence;
- baseline latency and gameplay metrics stored.

## Rollback

Not applicable; documentation and fixtures only.

---

# GDO-1 — Grounded transition envelope and shadow registry

## Objective

Introduce typed transition estimates without changing live decisions.

## Tasks

1. Add authority, context, validity, request, and estimate-envelope types.
2. Add `DomainTransitionModelRegistry`.
3. Wrap the current projection model as `legacy_projection_v1`.
4. Add explicit `LEGACY_PROXY` handling.
5. Update `pressure/adapters.py` to request a grounded estimate in shadow mode.
6. Preserve the current live `success_probability` and ordering while shadow mode is enabled.
7. Emit estimate disagreement events.
8. Add `typed_expected_relief()` in `pressure/teleology.py`.
9. Add a code path that computes a fully typed score but cannot authorize.
10. Document the exact transition-to-score derivation.

## Files

New:

- `src/freeciv_agent/planning/domain_models/__init__.py`
- `src/freeciv_agent/planning/domain_models/base.py`
- `src/freeciv_agent/planning/domain_models/context.py`
- `src/freeciv_agent/planning/domain_models/registry.py`
- `src/freeciv_agent/planning/domain_models/legacy.py`

Modified:

- `src/freeciv_agent/pressure/transitions.py`
- `src/freeciv_agent/pressure/teleology.py`
- `src/freeciv_agent/pressure/adapters.py`
- `src/freeciv_agent/pf_runtime.py`

## Tests

Create:

- `Autotests/test_freeciv_domain_estimate_schema.py`
- `Autotests/test_freeciv_domain_registry.py`
- `Autotests/test_freeciv_candidate_invariance.py`
- `Autotests/test_freeciv_typed_relief.py`

Required properties:

- probabilities plus residual mass equal one;
- adding or duplicating candidates leaves intrinsic estimates unchanged;
- candidate permutation leaves estimates unchanged;
- scaling legacy utilities leaves typed estimates unchanged;
- no double multiplication of probability;
- stale snapshot or legal-action digest invalidates authority;
- ruleset mismatch invalidates authority;
- registry selection deterministic;
- unsupported input produces `ABSTAIN`.

## Exit gate

- shadow estimates are emitted for at least 95% of captured candidate events;
- unsupported events have explicit abstention reasons;
- live action trace is byte-for-byte identical to `B1`;
- no more than 5% added p95 planning latency in shadow mode;
- all candidate-invariance tests pass.

## Rollback

Disable `pressure_domain_estimates_enabled`; legacy path remains unchanged.

---

# GDO-2 — Grounded movement and combat models

This stage is split because movement and combat have different authority and parity requirements.

## GDO-2A — Movement model

### Objective

Provide deterministic route feasibility, cost, ETA, and corridor identity from authoritative state.

### First task: data-availability audit

Before implementation, enumerate which inputs are present in:

- snapshot schema;
- ruleset IR;
- legal action records;
- map and unit state;
- transport state;
- movement points and turn information.

Produce `docs/evidence/gdo/movement_input_audit.md`.

The model must abstain for any rule interaction that cannot be reconstructed safely.

### Model output

The movement transition should include:

- legal first action;
- reachable/unreachable;
- minimum current-turn movement cost;
- estimated turns to destination;
- movement points remaining;
- transport requirement;
- zone-of-control or terrain blockers visible to the player;
- path-risk features;
- stable corridor digest;
- candidate next hops when ties exist;
- unknown mass where future occupancy or hidden information matters.

### Implementation

Create:

- `src/freeciv_agent/planning/domain_models/movement.py`
- `src/freeciv_agent/planning/path_corridors.py`
- `src/freeciv_agent/oracle/native_gameplay.py` for optional black-box parity tooling

Use a clean-room deterministic shortest-path implementation over repository-owned data structures. The path cost function must be ruleset-driven.

### Parity strategy

1. Generate randomized visible states within supported ruleset subsets.
2. Ask the separately installed native Freeciv environment for path results through a subprocess or test harness.
3. Compare:
   - reachability;
   - movement cost;
   - first step;
   - ETA;
   - transport requirement.
4. Store only legally redistributable generated fixtures.
5. Treat mismatch as abstention for the affected rule subset until resolved.

### Tests

- ordinary terrain;
- roads and rails;
- exhausted movement points;
- zones of control;
- impassable terrain;
- transport embark/disembark;
- tie-breaking;
- path invalidation after snapshot change;
- no hidden-tile leakage;
- deterministic corridor IDs;
- parity corpus.

### Exit gate

- 100% parity on the declared supported subset;
- every unsupported modifier produces abstention;
- no hidden-state dependency;
- p95 model latency within the budget established in GDO-0;
- no live authority yet.

## GDO-2B — Combat model

### Objective

Replace fixed tactical-attack pseudo-probabilities with grounded outcome distributions.

### First task: combat-input audit

Produce `docs/evidence/gdo/combat_input_audit.md` covering:

- attacker and defender statistics;
- hit points and veteran state;
- terrain and city bonuses;
- fortification;
- ruleset effects;
- multi-defender selection;
- bombardment;
- capture eligibility;
- post-action position;
- retaliation/counterattack observability.

### Model output

At minimum:

- probability target is destroyed;
- probability attacker survives;
- expected friendly shield-equivalent loss;
- expected enemy shield-equivalent loss;
- city capture probability where applicable;
- immediate goal-feature deltas;
- post-action exposure estimate;
- adverse-loss distribution;
- residual unknown mass;
- estimator provenance.

### Implementation

Create:

- `src/freeciv_agent/planning/domain_models/combat.py`
- `src/freeciv_agent/planning/domain_models/combat_rules.py`
- optional native parity commands in `oracle/native_gameplay.py`

Separate:

- exact/deterministic combat mechanics;
- strategic post-action risk;
- goal-relief mapping.

The deterministic combat core may receive `DETERMINISTIC_DERIVED` authority after parity. Post-action exposure begins as `HEURISTIC` or `CALIBRATED`.

### Tests

- canonical one-versus-one battles;
- damaged units;
- terrain and fortification modifiers;
- city attack and capture;
- no legal attack;
- multiple defenders;
- edge probabilities;
- material expected value;
- probability mass conservation;
- native differential corpus;
- abstention on unsupported effects.

### Exit gate

- parity on the declared deterministic subset;
- Brier/log-loss baseline established on engine outcomes;
- no fixed utility is exposed as a probability in typed shadow output;
- unsupported states abstain;
- live ordering remains unchanged.

---

# GDO-3 — Identity/time resource claims and scheduler

## Objective

Represent actual game resource conflicts and schedule bounded operation sets deterministically.

## Tasks

1. Implement resource contracts.
2. Add `ResourceCapacityExtractor` from authoritative snapshots.
3. Add compatibility conversion from v1 packet budgets.
4. Implement overlap and capacity checks.
5. Implement `GreedyIdentityScheduler`.
6. Implement `BoundedExactScheduler`.
7. Add a deterministic branch ordering and timeout/node-limit fallback.
8. Add a reservation ledger.
9. Integrate reservation release with commit validation.
10. Add shadow scheduling beside the current packet scheduler.
11. Emit disagreement and conflict events.

## Files

New:

- `src/freeciv_agent/pressure/resource_claims.py`
- `src/freeciv_agent/pressure/resource_capacity.py`
- `src/freeciv_agent/pressure/resource_scheduler.py`
- `src/freeciv_agent/pressure/resource_ledger.py`

Modified:

- `src/freeciv_agent/pressure/packets.py` only for adapters/documentation, not semantic replacement;
- `src/freeciv_agent/planning/commit_validator.py`;
- `src/freeciv_agent/pressure/adapters.py`;
- `src/freeciv_agent/pf_runtime.py`.

## Tests

Create:

- `Autotests/test_freeciv_resource_claims.py`
- `Autotests/test_freeciv_resource_capacity.py`
- `Autotests/test_freeciv_identity_scheduler.py`
- `Autotests/test_freeciv_resource_release.py`

Required cases:

- two operations claim one actor;
- two seats versus three passengers;
- overlapping and non-overlapping turn windows;
- exclusive tile occupancy;
- treasury quantities;
- current hard versus future conditional claims;
- capacity disappears after snapshot update;
- commit rejection releases claims;
- exact scheduler beats a constructed greedy counterexample;
- node-limit fallback deterministic;
- resource input permutation invariance;
- zero over-allocation.

## Exit gate

- zero hard-capacity violations across replay corpus;
- shadow scheduler deterministic;
- all rejection reasons attributable and logged;
- exact scheduler returns the known optimum on exhaustive small instances;
- controller-inclusive p95 overhead no more than 15% of baseline and no more than 50 ms for bounded test sets;
- no live authority.

---

# GDO-4 — City-defence vertical slice

## Objective

Demonstrate that grounded estimates plus identity-aware assignment solve a real Freeciv coordination problem before expanding scope.

## Why city defence is first

City defence has:

- a safety-critical goal;
- visible attackers and defenders;
- measurable threat ETA;
- discrete defender identities;
- short feedback cycles;
- clear “preventable loss” metrics;
- natural comparison with greedy assignment.

## Candidate operation types

- `FORTIFY_EXISTING_DEFENDER`
- `MOVE_DEFENDER_TO_CITY`
- `INTERCEPT_IMMEDIATE_THREAT`
- `BLOCK_APPROACH_TILE`
- `EMERGENCY_BUILD_DEFENDER`
- `RETREAT_EXPOSED_UNIT`
- `HOLD_SOLE_DEFENDER`

The last type is a protected constraint rather than an ordinary positive bid.

## Threat model

Create `src/freeciv_agent/planning/domain_models/defense.py`.

For each visible threat:

- actor identity and class;
- earliest visible attack turn;
- reachable target cities;
- approximate damage/capture outcome;
- confidence and unknown mass;
- path corridor;
- whether interception is legal.

For each defender:

- current city;
- ETA to threatened city;
- expected defensive contribution;
- opportunity cost of leaving;
- whether it is the sole or protected defender;
- current legal action.

## Assignment formulation

Build a bipartite/min-cost problem:

```text
defenders and emergency production options
    <-> city defence requirements
```

An edge exists only when:

- the defender can arrive before the relevant threat;
- the next action is legal;
- protected constraints are satisfied;
- the assignment has a grounded transition estimate.

The objective maximizes expected prevented goal loss minus movement, production, and opportunity cost.

## Operation structure

A move-to-defend operation includes:

- defender participant;
- destination city;
- path corridor;
- arrival deadline;
- current movement step;
- actor and movement claims;
- completion predicate: defender contributes to city defence before deadline;
- cancellation conditions.

## Safety constraints

Hard constraints:

- never remove the only effective defender from an immediately threatened city unless the alternative prevents greater expected loss and is explicitly safety-approved;
- never select an action absent from the current legal-action set;
- never assign one defender to two cities in the same window;
- do not count a future build as present defence;
- terminal survival goals outrank ordinary expansion or economy goals;
- if typed support is incomplete for a winner-changing comparison, use `B1`.

## Baselines

- `B1`: current scalar-v2 plus current packets;
- `B2`: typed defence estimates with current scheduler;
- `B3`: typed estimates with identity-aware greedy assignment;
- `B4`: typed estimates with exact bounded city-defence assignment;
- optional Classic-like greedy reference implementation, independently written.

## Metrics

Primary mechanism metrics:

- preventable city losses;
- uncovered threat-turns;
- over-defended city-turns;
- defenders assigned after deadline;
- actor conflicts;
- emergency builds completed too late;
- sole-defender violations;
- no-effect operations;
- operation completion rate;
- added p50/p95 latency.

Secondary gameplay metrics:

- city survival;
- material loss;
- score delta;
- win rate only after mechanism gates pass.

## Exit gate for bounded live pilot

All must hold on disjoint replay and diagnostic cohorts:

1. zero legality violations;
2. zero hard-resource conflicts;
3. zero sole-defender invariant violations;
4. lower uncovered threat-turns than `B1`;
5. no increase in preventable city loss;
6. positive operation-completion delta;
7. p95 planning overhead no more than 15% of baseline and no more than 50 ms;
8. typed estimate coverage at least 90% for winner-changing defence comparisons;
9. unsupported states fall back exactly to `B1`.

A fresh pilot may then enable city-defence authority only, with all other domains unchanged.

## Rollback

Disable `pressure_city_defense_operations_enabled`. Existing candidates and comparator remain intact.

---

# GDO-5 — Multi-unit combat operations

## Objective

Coordinate attacks whose value depends on multiple actors or ordered steps.

## Operation types

- bombard then attack;
- weaken defender then capture;
- escort attacker to staging tile;
- attack then occupy;
- attack then hold against visible counterattack;
- sacrificial interception protecting a terminal goal.

## Operation packet

Example:

```text
ATTACK_OPERATION
    target: city:19
    participants:
        bombardier -> unit:41
        attacker -> unit:57
        occupier -> unit:63
    steps:
        1. bombard target
        2. attack selected defender
        3. enter/occupy target
        4. hold or consolidate
    hard current claims:
        current acting unit
        current movement points
        current action budget
    conditional future claims:
        later participants
        staging tiles
        later movement windows
```

## Tasks

1. Add `CombatOperationAssembler`.
2. Enumerate legal participant-role combinations.
3. Use `RequirementSet` for AND dependencies.
4. Add target and staging-tile conflicts.
5. Estimate the joint operation through explicit step-conditioned transitions.
6. Do not multiply independent step probabilities unless independence is justified; use conditional branches.
7. Re-estimate after every step.
8. Add abandonment and repair rules.
9. Compare atomic operation assembly with independent action ranking.

## Tests

- all required participants present;
- missing bombardment prerequisite;
- first step succeeds/fails;
- target destroyed before later step;
- participant removed;
- staging tile becomes illegal;
- attacker conflict across operations;
- operation completion and claim release;
- conditional probability calculation;
- deterministic operation ID;
- fallback when joint support is incomplete.

## Evaluation metrics

- target neutralization;
- capture and retention;
- friendly material loss;
- abandoned partial attacks;
- duplicated targeting;
- actor idle turns;
- operation completion;
- no-effect;
- latency;
- full score only after mechanism improvement.

## Exit gate

- zero partial activation when required current participants cannot be reserved;
- lower duplicated targeting than `B1`;
- lower abandoned-partial-operation rate;
- no adverse shift in friendly expected-versus-realized loss beyond predeclared tolerance;
- fresh disjoint pilot shows directional mechanism benefit;
- policy authority remains limited to the declared operation types.

---

# GDO-6 — Ferry/founder operation coordination

## Objective

Test explicit multi-turn coordination across a transport bottleneck without returning to generic path persistence.

## Operation type

```text
FOUNDER_TRANSPORT_OPERATION
    founder
    ferry
    pickup tile
    landing tile
    settlement target
    optional threat-gated escort
    route corridors
    rendezvous deadline
```

## Required steps

1. founder moves to pickup;
2. ferry moves to pickup;
3. embark;
4. transport to landing corridor;
5. disembark;
6. founder reaches target;
7. found city;
8. optional post-settlement defence operation.

Each step is legal-action driven and revalidated.

## Escort policy

Do not implement unconditional escort persistence. Earlier branch work already indicates that settlement/escort value is context-dependent.

Escort becomes required only when:

- visible threat crosses a frozen risk threshold;
- founder or new city survival risk is supported by a grounded estimator;
- a legal escort path exists;
- the escort opportunity cost is included;
- required participants can be reserved.

Otherwise the operation proceeds unescorted or abstains according to policy.

## Tasks

1. Add `transport.py` domain model.
2. Add transport-seat capacity extraction.
3. Add rendezvous feasibility and deadline estimates.
4. Add corridor and landing-site identity.
5. Add founder/ferry partner locking at the operation level.
6. Add bounded repair:
   - alternate pickup;
   - alternate landing;
   - replacement ferry only if explicit margin and feasibility gates pass.
7. Add settlement completion and retention outcome resolution.
8. Compare against generic path persistence with that feature disabled.

## Metrics

- rendezvous completion rate;
- founder idle turns;
- ferry idle turns;
- partner switches;
- embark/disembark failures;
- settlement completion;
- settlement retention after a fixed horizon;
- escort cost and preventable founder loss;
- blocked-operation duration;
- no-effect;
- latency.

## Exit gate

- lower partner-switch frequency;
- lower rendezvous latency;
- higher completed-settlement rate without worse retention;
- no increase in founder loss attributable to omitted threat-gated escorts;
- zero transport-seat over-allocation;
- no generic score/path persistence enabled;
- fresh disjoint pilot supports the mechanism.

---

# GDO-7 — Production, research, and city-worker extensions

This stage is conditional. Begin only after at least one prior vertical slice passes its mechanism gate.

## GDO-7A — Production

Model:

- current city production slot;
- completion ETA;
- shield cost;
- switch cost;
- upkeep;
- unit/building availability;
- operation dependency;
- emergency timing.

Represent production as an enabling operation:

```text
BUILD_DEFENDER
    city production slot
    treasury/upkeep implications
    completion deadline
    downstream defence operation
```

Do not treat a unit under construction as an available participant.

## GDO-7B — Research

Reuse the existing dependency oracle and `RequirementSet` machinery.

Rules:

- represent technology prerequisites explicitly;
- avoid propagating legacy `tech_want` through the same dependency graph a second time;
- choose one mode:
  - legacy propagated `tech_want` as a terminal comparator; or
  - decomposed ruleset dependency graph with pressure propagation;
- include research switching cost;
- preserve long-term and immediate goal distinction;
- one research slot is an identity-bearing resource.

## GDO-7C — City workers

Use the existing/local exact city solver where authoritative interfaces expose enough detail.

Pressure decides:

- city-level output priorities;
- minimum constraints;
- which city deserves optimization budget.

The local solver decides:

- tile/specialist assignment.

Represent the result as a macro-action with:

- predicted output vector;
- constraints met;
- solver status;
- optimality gap;
- snapshot/ruleset provenance.

Do not assign citizens one at a time through the pressure fluid.

## Exit gate

Each subdomain requires its own mechanism metric and must beat its immediate simpler baseline before receiving any authority.

---

# GDO-8 — Contextual calibration and conductance

## Objective

Replace category-only learning with frozen, support-aware contextual estimates.

## Current problem

A category-level update can incorrectly transfer failure or success across unrelated contexts. Examples:

- a blocked overseas founder route affects all expansion;
- a damaged primitive unit affects all tactical attacks;
- one ferry corridor affects transport everywhere.

## Context hierarchy

Predeclare this backoff hierarchy:

```text
exact supported context
    -> action + actor/target class + threat/horizon bucket
    -> action + actor class
    -> action category
    -> global prior
```

No silent pooling outside this hierarchy.

## Transition value key v2

Extend or version `TransitionValueKey` to include `TransitionContextKey`.

Migration rules:

- read legacy v1 records only as category priors;
- never reinterpret v1 as exact context support;
- write v2 records only under the new schema;
- preserve estimator and policy version;
- include ruleset digest or ruleset family.

## Contextual conductance

Conductance represents realized causal effectiveness of a route in a comparable context, not popularity or activation frequency.

A shrinkage estimator may use:

\[
C_{\text{context}}
=
\frac{n C_{\text{observed}} + \kappa C_{\text{parent}}}{n+\kappa}
\]

but live authority requires:

- a frozen model;
- declared parent;
- minimum support;
- confidence interval or posterior bound;
- holdout calibration;
- no evaluation-data updates.

## Outcome records

Each record includes:

- estimate context;
- selected policy and propensity where defined;
- action and operation IDs;
- predicted transition;
- realized authoritative outcome;
- goal relief;
- adverse loss;
- eligibility/causal trace;
- estimator and policy versions;
- terminal/no-effect/unknown status.

Unknown outcomes must not be coerced into failure or success.

## Support gates

Initial authority gate for a context or declared parent bucket:

- minimum support count set before evaluation;
- Brier or log-loss improvement against the legacy proxy on held-out data;
- aggregate 95% bootstrap interval excludes no improvement for the intended slice;
- no supported high-volume context worsens Brier by more than the predeclared tolerance;
- coverage of at least 80% for the intended live slice, otherwise exact fallback;
- calibration model frozen before pilot.

Exact numerical support thresholds should be set in GDO-0 after observing event frequency, then frozen. They must not be tuned from confirmation outcomes.

## Tests

- context isolation;
- declared backoff only;
- ruleset separation;
- frozen model immutability;
- no evaluation updates;
- unknown outcomes excluded correctly;
- propensity field presence where required;
- deterministic serialization;
- legacy migration.

---

# GDO-9 — Conditional bridge and flow re-entry

## Objective

Determine whether a residual coordination problem remains after grounded estimates, operation assembly, and exact resource scheduling.

## Entry conditions

Bridge/flow experimentation may resume only when all are true:

1. Typed estimates are candidate-invariant and calibrated for the target slice.
2. Identity/resource scheduling has zero hard over-allocation.
3. Operation completion and failure semantics are stable.
4. A dedicated exact or bounded combinatorial scheduler is the active comparison baseline.
5. Replay analysis identifies a residual error specifically caused by route/bottleneck allocation.
6. The error is not due to missing candidates, incorrect semantics, stale state, or unsupported transition estimates.
7. The expected value of solving the residual error exceeds the measured controller-inclusive latency cost.

## Required baselines

- `B0`: canonical Impact;
- `B1`: frozen scalar-v2 plus v1 packets;
- `B2`: grounded estimates plus v1 scheduler;
- `B3`: grounded estimates plus identity-aware greedy scheduler;
- `B4`: grounded estimates plus exact bounded operation scheduler;
- `B5`: `B4` plus bridge membership/shadow scoring;
- `B6`: `B5` plus source–sink flow shadow allocation.

Bridge value is measured against `B4`, not against an older weaker baseline.

## Bridge claim

Bridge must demonstrate one of:

- increased recall of feasible enabling operations;
- correct identification of a bottleneck omitted by the operation assembler;
- lower regret than `B4` on predeclared route-allocation cases.

It does not receive credit for predictions or candidates supplied by the new domain models.

## Flow claim

Flow must demonstrate:

- a capacity allocation improvement over the exact bounded scheduler on cases beyond its bounded horizon;
- no safety-goal dilution;
- no hard-capacity violation;
- controller-inclusive value after latency;
- fresh pilot and frozen confirmation.

## Rollout order

```text
offline replay
    -> shadow
    -> advisory with protected scalar ordering
    -> bounded slice-specific reordering
    -> broader authority only after separate confirmation
```

A negative result returns the component to shadow/offline status and is documented.

---

## 12. File-by-file implementation map

| Path | Change |
|---|---|
| `src/freeciv_agent/planning/impact.py` | Retain `utility` and legacy projection; add only minimal typed candidate features; do not remove fixed utilities until typed authority is validated |
| `src/freeciv_agent/planning/domain_models/base.py` | Domain request/model protocol |
| `src/freeciv_agent/planning/domain_models/context.py` | Authority, context key, validity, estimate envelope |
| `src/freeciv_agent/planning/domain_models/registry.py` | Deterministic model registration and dispatch |
| `src/freeciv_agent/planning/domain_models/legacy.py` | Explicit legacy projection/proxy wrapper |
| `src/freeciv_agent/planning/domain_models/movement.py` | Route feasibility, ETA, cost, corridor estimates |
| `src/freeciv_agent/planning/domain_models/combat.py` | Combat outcome distribution and material effects |
| `src/freeciv_agent/planning/domain_models/combat_rules.py` | Clean-room deterministic ruleset-driven mechanics |
| `src/freeciv_agent/planning/domain_models/defense.py` | Threat ETA, defensive contribution, preventable-loss model |
| `src/freeciv_agent/planning/domain_models/production.py` | Build completion and enabling-operation estimates |
| `src/freeciv_agent/planning/domain_models/transport.py` | Ferry/passenger/rendezvous estimates |
| `src/freeciv_agent/planning/path_corridors.py` | Stable path/corridor identity and summaries |
| `src/freeciv_agent/planning/operations.py` | Immutable operation and step contracts |
| `src/freeciv_agent/planning/operation_store.py` | Versioned progress persistence |
| `src/freeciv_agent/planning/operation_assembler.py` | Candidate-to-operation construction |
| `src/freeciv_agent/pressure/transitions.py` | Preserve canonical outcomes; add helpers/versioned serialization if needed |
| `src/freeciv_agent/pressure/teleology.py` | Compute expected relief from transitions; remove double-probability semantics from typed path |
| `src/freeciv_agent/pressure/adapters.py` | Registry calls, typed shadow/authority modes, all-or-fallback comparison |
| `src/freeciv_agent/pressure/resource_claims.py` | Identity/time resource contracts |
| `src/freeciv_agent/pressure/resource_capacity.py` | Authoritative capacity extraction |
| `src/freeciv_agent/pressure/resource_scheduler.py` | Greedy identity and bounded exact schedulers |
| `src/freeciv_agent/pressure/resource_ledger.py` | Reservations, release, conflict reasons |
| `src/freeciv_agent/pressure/packets.py` | Keep v1 stable; add compatibility adapter only |
| `src/freeciv_agent/pressure/transition_value.py` | Versioned contextual key and strict v1-to-prior migration |
| `src/freeciv_agent/pressure/learning.py` | Contextual conductance v2; frozen model handling |
| `src/freeciv_agent/planning/commit_validator.py` | Validate estimate validity, operation step, participant identity, and hard claims; release on failure |
| `src/freeciv_agent/oracle/native_gameplay.py` | Optional separately installed native parity harness |
| `src/freeciv_agent/state/snapshot.py` | Stable read-only accessors; no inferred hidden information |
| `src/freeciv_agent/rulesets/ir.py` | Stable movement/combat/production accessors and digests |
| `src/freeciv_agent/pf_runtime.py` | New flags, invalid-combination checks, default-off policy |
| `src/freeciv_agent/events/` | Versioned estimate/resource/operation event schemas |
| `Autotests/` | Unit, property, parity, integration, replay, and migration tests |
| `benchmarks/gdo/` | Captured replay, mechanism benchmarks, manifests, result bundles |
| `docs/evidence/gdo/` | Audits, gates, pilot reports, negative results, licensing boundary |

---

## 13. Runtime flags and validity rules

Add flags with defaults:

```python
pressure_domain_estimates_enabled = False
pressure_domain_estimates_authority_enabled = False
pressure_identity_resource_packets_enabled = False
pressure_operation_lifecycle_enabled = False
pressure_city_defense_operations_enabled = False
pressure_combat_operations_enabled = False
pressure_transport_operations_enabled = False
pressure_contextual_conductance_enabled = False
pressure_contextual_conductance_authority_enabled = False
```

Existing bridge/flow/path-persistence defaults remain disabled.

### 13.1 Required combinations

| Flag | Requires |
|---|---|
| domain-estimate authority | scalar-v2, domain estimates, commit revalidation |
| identity resource packets | packet scheduler and commit revalidation |
| operation lifecycle | identity resources and domain estimates |
| city-defence operations | operation lifecycle, movement model, identity resources |
| combat operations | operation lifecycle, movement model, combat model |
| transport operations | operation lifecycle, movement model, transport-seat capacities |
| contextual conductance | domain estimates and v2 context schema |
| contextual conductance authority | frozen approved calibration bundle |
| bridge live authority | all existing bridge gates plus GDO-9 entry gate |
| flow live authority | bridge, identity resources, exact commit revalidation, GDO-9 flow gate |

### 13.2 Invalid configurations

Runtime startup must reject:

- authority enabled while estimate generation is disabled;
- operation lifecycle without identity resource claims;
- transport operations without transport capacity extraction;
- contextual authority with a mutable model;
- live bridge/flow with legacy-relative probability semantics;
- any live operation path without commit revalidation;
- ruleset digest mismatch between model and current game.

---

## 14. Event and observability model

Add versioned JSON events.

### 14.1 Estimate events

`domain_estimate_emitted`:

- request ID;
- candidate/action ID;
- actor and target IDs;
- operation ID;
- context key;
- authority;
- estimator ID/version;
- snapshot/legal-action/ruleset digests;
- outcome probabilities;
- residual mass;
- expected relief by goal;
- adverse risk;
- latency;
- provenance.

`domain_estimate_abstained`:

- same identifiers;
- reason code;
- missing fields;
- unsupported rule/effect;
- fallback chosen.

### 14.2 Resource events

- `resource_claim_requested`
- `resource_claim_reserved`
- `resource_claim_rejected`
- `resource_claim_released`
- `resource_capacity_changed`

Each includes the full resource identity, window, quantity, operation owner, and reason.

### 14.3 Operation events

- `operation_proposed`
- `operation_reserved`
- `operation_activated`
- `operation_step_selected`
- `operation_step_revalidated`
- `operation_step_committed`
- `operation_blocked`
- `operation_repaired`
- `operation_suspended`
- `operation_completed`
- `operation_failed`
- `operation_abandoned`
- `operation_expired`

### 14.4 Evaluation events

- `policy_disagreement`
- `scheduler_disagreement`
- `prediction_resolved`
- `goal_relief_realized`
- `no_effect_resolved`
- `unknown_outcome`
- `fallback_triggered`

### 14.5 Reason-code discipline

Reason codes are enums. Free text is supplementary only. This allows aggregate analysis without parsing logs.

---

## 15. Testing strategy

### 15.1 Unit and schema tests

Cover every new dataclass, enum, serializer, validator, and migration.

### 15.2 Metamorphic tests

Mandatory properties:

1. Add a dominated candidate: intrinsic estimates unchanged.
2. Duplicate a candidate: intrinsic estimates unchanged.
3. Permute candidates: estimates and deterministic schedule unchanged.
4. Scale legacy utilities: typed probabilities unchanged.
5. Rename an unrelated actor: unrelated estimate unchanged.
6. Change snapshot ID without state equality proof: authority invalidated.
7. Change ruleset digest: estimate invalidated.
8. Outcome probability plus residual mass remains one.
9. Expected relief is integrated exactly once.
10. Resource windows that do not overlap do not conflict.
11. Overlapping exclusive resource claims conflict.
12. Soft future claims cannot block an authoritative current action unless policy explicitly prices them.
13. Rejected commit releases all hard claims.
14. Context update in one bucket does not change an unrelated exact bucket.
15. Frozen calibration model cannot mutate.

### 15.3 Differential/native parity tests

For movement and deterministic combat subsets:

- generated states;
- separately installed native reference;
- exact comparison where deterministic;
- tolerance only where the output is floating-point probability;
- mismatch corpus retained;
- unsupported feature causes abstention.

### 15.4 Captured snapshot replay

Each fixture includes:

- snapshot;
- legal actions;
- ruleset digest;
- legacy candidate set;
- expected model support;
- expected resource conflicts;
- expected comparator action;
- expected typed action where approved.

Replay must be deterministic and fast enough for CI subsets.

### 15.5 Integration tests

Cover:

- candidate -> estimate -> operation -> resources -> commit;
- stale estimate before commit;
- legal action removed;
- participant disappears;
- capacity changes;
- operation repair;
- operation release after failure;
- fallback to `B1`;
- bridge/flow disabled despite available graph.

### 15.6 Engine tests

Use clean source and disjoint seed sets.

Recommended command family:

```bash
PYTHONPATH=.:src:benchmarks pytest -q Autotests/test_freeciv_*.py
python scripts/run_gdo_replay.py --manifest benchmarks/gdo/replay_manifest.json
python scripts/run_gdo_engine_cohort.py --cohort diagnostic
python scripts/run_gdo_engine_cohort.py --cohort pilot
python scripts/run_gdo_engine_cohort.py --cohort confirmation
```

The actual command interface may follow existing repository conventions, but must emit a frozen manifest and checksums.

### 15.7 Compatibility

- Python 3.8 syntax only;
- deterministic ordering independent of hash randomization;
- versioned serialization;
- legacy stores remain readable;
- corrupted or unknown records are quarantined, not guessed.

---

## 16. Evaluation design

### 16.1 Baseline ladder

| ID | Policy |
|---|---|
| `B0` | Canonical Impact |
| `B1` | Frozen scalar PF-v2 plus current packet scheduler |
| `B2` | Grounded estimates plus current packet scheduler |
| `B3` | Grounded estimates plus identity-aware greedy scheduler |
| `B4` | Grounded estimates plus bounded exact operation scheduler |
| `B5` | `B4` plus bridge shadow/advisory |
| `B6` | `B5` plus source–sink flow shadow/advisory |

Every component claims incremental value only against the immediately preceding appropriate baseline.

### 16.2 Prediction metrics

- Brier score;
- log loss where probabilities are bounded away from zero;
- reliability/calibration curves;
- expected calibration error;
- residual unknown-mass rate;
- abstention rate;
- expected-versus-realized goal-relief MAE;
- adverse-loss calibration;
- coverage by authority level and context.

### 16.3 Coordination metrics

- hard resource conflicts;
- reservation rejection reasons;
- exact versus greedy objective gap;
- operation completion;
- operation abandonment;
- blocked duration;
- partner switching;
- duplicated target assignments;
- participant idle turns;
- no-effect rate.

### 16.4 Safety metrics

- illegal commit attempts;
- stale-estimate rejects;
- protected-goal regressions;
- sole-defender violations;
- preventable city losses;
- unexpected adverse-loss tail;
- fallback correctness.

### 16.5 Gameplay metrics

Only after mechanism gates:

- score delta;
- settlement and city-retention outcomes;
- material balance;
- technology progress;
- win rate;
- game length.

### 16.6 Performance metrics

Measure controller-inclusive:

- estimate latency p50/p95/p99;
- operation assembly latency;
- scheduling latency;
- commit-validation latency;
- total planning and full-loop latency;
- memory growth;
- event volume.

A faster local solver does not offset added orchestration cost unless total loop value improves.

### 16.7 Cohort discipline

1. **Offline/replay:** implementation correctness.
2. **Diagnostic cohort:** claim-ineligible, used to find defects.
3. **Pilot cohort:** predeclared directional mechanism test.
4. **Confirmation cohort:** frozen policy and fresh seeds, only if pilot passes.
5. **Broader gameplay cohort:** only after the slice-specific mechanism passes.

Do not pool failed pilot and retuned runs into a confirmation claim.

---

## 17. Calibration and outcome resolution

### 17.1 Prediction identifiers

Every prediction gets a stable ID composed from:

- estimator/version;
- policy version;
- snapshot;
- action;
- operation/step;
- context;
- turn.

### 17.2 Resolution horizon

Each model declares a resolution horizon:

- immediate combat: next authoritative outcome;
- movement step: next snapshot;
- city-defence arrival: threat deadline;
- settlement: founding event plus retention horizon;
- production: completion turn;
- research: technology completion.

### 17.3 Resolution states

- `RESOLVED_SUCCESS`
- `RESOLVED_FAILURE`
- `RESOLVED_PARTIAL`
- `RESOLVED_NO_EFFECT`
- `UNRESOLVED_UNKNOWN`
- `CENSORED_OPERATION_ABORT`
- `INVALIDATED_STATE_CHANGE`

Calibration code must distinguish them.

### 17.4 Causal restraint

Action selection is not randomized by default. Therefore:

- ordinary logs calibrate factual transition prediction for selected actions;
- they do not automatically establish counterfactual policy value;
- conductance updates require explicit eligibility traces and comparable context;
- off-policy value claims require a separate design.

---

## 18. Migration and persistence

### 18.1 Schema versioning

Version independently:

- transition context;
- grounded estimate;
- resource claim;
- capacity;
- operation spec;
- operation progress;
- calibration record;
- conductance record.

### 18.2 Legacy handling

- `ImpactCandidate.utility` remains available;
- legacy relative probability is labelled `LEGACY_PROXY`;
- legacy category conductance is a parent prior only;
- legacy packet budgets remain active on `B1`;
- no automatic conversion implies exact identity;
- unknown schema versions are rejected or quarantined.

### 18.3 Store rollout

1. read old / write old;
2. read old / shadow-write new;
3. validate checksums and replay;
4. read both / compare;
5. enable new writes for flagged cohorts;
6. retain rollback reader for at least one full evidence cycle.

### 18.4 Operation recovery

On process restart:

1. load operation records;
2. compare game/session identity;
3. compare snapshot/ruleset lineage;
4. re-resolve participants;
5. downgrade all future claims;
6. re-estimate the next step;
7. resume, suspend, or expire explicitly.

Never resume solely because an operation record exists.

---

## 19. Pull-request sequence

Each pull request should be reviewable, testable, and default-off.

| PR | Contents | Policy effect |
|---|---|---|
| PR-00 | Baseline manifest, fixtures, licensing boundary | None |
| PR-01 | Estimate authority/context/validity contracts | None |
| PR-02 | Domain registry and legacy shadow wrapper | None |
| PR-03 | Typed expected-relief path and invariance tests | None |
| PR-04 | Movement model and parity harness | Shadow |
| PR-05 | Combat model and parity harness | Shadow |
| PR-06 | Identity/time resource contracts and capacities | None |
| PR-07 | Greedy identity and bounded exact schedulers | Shadow |
| PR-08 | Operation contracts, store, lifecycle, events | None |
| PR-09 | Commit-validator integration and release semantics | Default-off |
| PR-10 | City-defence model and operation assembler | Shadow |
| PR-11 | City-defence bounded live pilot flag | Slice-only, default-off |
| PR-12 | Multi-unit combat operations | Shadow/default-off |
| PR-13 | Ferry/founder operations | Shadow/default-off |
| PR-14 | Contextual transition/conductance v2 | Shadow |
| PR-15 | Conditional bridge/flow residual-error experiments | No live authority initially |

Every PR includes:

- tests;
- schema/version notes;
- events;
- performance measurement;
- rollback behavior;
- no unrelated refactor.

---

## 20. Detailed acceptance checklist by component

### 20.1 Grounded estimates

- [x] Existing `ExpectedTransition` is canonical.
- [x] Authority, context, validity, confidence, and provenance are explicit.
- [x] Unknown mass is explicit.
- [x] Candidate-set invariance tests pass.
- [x] Legacy utility is never labelled probability in the typed path.
- [x] Unsupported cases abstain.
- [x] Typed authority is all-or-fallback.
- [x] Snapshot and ruleset invalidation work.
- [x] Prediction outcomes resolve into the calibration ledger.

### 20.2 Resources

- [x] Every hard claim has identity and time.
- [x] Capacity comes from authoritative state.
- [x] Future claims are conditional.
- [x] No hard over-allocation is possible.
- [x] Scheduler is deterministic.
- [x] Exact small-instance optimum is verified.
- [x] Timeout fallback is deterministic.
- [x] Commit rejection releases claims.
- [x] v1 packets remain intact.

### 20.3 Operations

- [x] Operation ID is stable.
- [x] Participants and roles are explicit.
- [x] Requirements and steps are explicit.
- [x] Current and future claims are separated.
- [x] Only the next step commits.
- [x] Re-estimation occurs every turn.
- [x] Replacement and abandonment use reason codes.
- [x] Restart recovery is safe.
- [x] No generic path-score persistence is required.

### 20.4 City defence

- [x] Threat ETA is grounded or abstains.
- [x] Defender ETA is grounded or abstains.
- [x] Sole-defender constraint is protected.
- [x] One defender cannot serve incompatible assignments.
- [x] Build completion timing is respected.
- [x] Preventable loss is measured.
- [x] Exact assignment baseline exists.
- [x] Slice-specific pilot gate passes before authority.

### 20.5 Combat

- [x] Deterministic rules subset has parity.
- [x] Joint operations use conditional transitions.
- [x] Partial current activation is impossible.
- [x] Target and participant conflicts are represented.
- [x] Post-action risk authority is labelled correctly.
- [x] Adverse loss is calibrated.

### 20.6 Transport

- [x] Ferry seat identity and capacity are represented.
- [x] Founder/ferry partnership is operation-scoped.
- [x] Rendezvous and landing routes are explicit.
- [x] Escort is threat-gated.
- [x] Partner switching and idle turns are measured.
- [x] Settlement retention is resolved.
- [x] Generic path persistence remains disabled.

### 20.7 Learning

- [x] Context schema and backoff hierarchy are frozen.
- [x] Legacy category data is only a prior.
- [x] Models are immutable during evaluation.
- [x] Unknown/censored outcomes are handled explicitly.
- [x] No off-policy claim is made without design support.
- [x] Confirmation uses fresh seeds.

---

## 21. Risk register

| Risk | Failure mode | Mitigation |
|---|---|---|
| Probability/utility conflation | Unstable scores and false confidence | Canonical transition envelope; invariance tests |
| Double-counted success | Probability multiplied in outcome and score | Expected-relief integration test |
| Incomplete snapshot | Estimator invents missing mechanics | Input audits; explicit abstention |
| GPL contamination | MIT repository incorporates GPL implementation | Clean-room design; native sidecar boundary; legal review |
| Resource fiction | Future capacity treated as guaranteed | Hard-current versus conditional-future claims |
| Combinatorial explosion | Exact scheduler stalls turn loop | Narrow slices; node budget; deterministic greedy fallback |
| Over-persistence | Bad operations consume resources too long | Expiry, replacement margin, blocked timeout, per-turn re-estimation |
| Context fragmentation | No bucket reaches support | Predeclared hierarchical backoff |
| Context contamination | Unrelated outcomes alter conductance | Versioned exact keys and declared parents |
| Evaluation leakage | Tuning on confirmation seeds | Frozen manifests and disjoint cohorts |
| Bridge credit leakage | Bridge credited for domain-model candidates | Incremental baseline ladder |
| Latency regression | Better local metric but worse gameplay loop | Controller-inclusive latency gates |
| Hidden-information leak | Unfair/invalid AI behavior | Visible-state accessors and tests |
| Stale execution | Action legal when planned but not at commit | Existing exact revalidation plus validity envelope |
| Migration ambiguity | Old data interpreted as exact new semantics | Strict schema versions and quarantine |
| Outcome misresolution | Aborted action counted as failure | Explicit resolution states |
| Online-learning drift | Cohort policy changes during test | Frozen read-only calibration bundle |

---

## 22. Definition of done

The program is complete when all of the following hold:

1. The supported comparator is reproducible and frozen.
2. Typed domain estimates no longer derive intrinsic probability from relative candidate utility.
3. Movement and combat have declared supported subsets with parity or explicit abstention.
4. Expected goal relief is computed from canonical outcome transitions exactly once.
5. Resource claims identify actual game resources and time windows.
6. Hard capacity cannot be over-allocated.
7. Multi-turn coordination uses explicit operations with safe lifecycle and restart behavior.
8. City-defence coordination passes its mechanism and safety gates.
9. At least one additional operation slice—combat or ferry/founder—passes a fresh pilot gate.
10. Contextual calibration is versioned, frozen, and support-aware.
11. All new authority is slice-specific, default-off, and fully reversible.
12. Existing bridge/flow negative evidence remains documented.
13. Bridge/flow live authority remains disabled unless GDO-9 independently passes.
14. Full tests, replay, latency, and evaluation artifacts are reproducible from a manifest.
15. No GPL implementation code has entered the MIT repository.

Completion does **not** require bridge or flow to become live. A scientifically valid outcome may be that grounded estimates plus an exact bounded operation scheduler are sufficient and bridge/flow remain research-only.

### 22.1 Completion record

Status: complete for the program definition above

Date: 2026-07-30

| Definition item | Result | Canonical evidence |
|---|---|---|
| 1. Frozen comparator | passed | `benchmarks/freeciv/pf_unified/baseline_manifest.yaml`, its byte-exact golden set, and `benchmarks/gdo/baseline_manifest.json` |
| 2. Typed probability semantics | passed | `docs/evidence/gdo/gdo1_grounded_transition_shadow.md` |
| 3. Movement/combat support boundary | passed | `docs/evidence/gdo/native_movement_route_foundation.md`, `docs/evidence/gdo/gdo5_native_combat_foundation.md`, and explicit abstention regressions |
| 4. Single expected-relief integration | passed | typed teleology and candidate-invariance regressions |
| 5. Identity/time resource claims | passed | GDO-3 resource-shadow artifact and claim tests |
| 6. No hard over-allocation | passed | GDO-3 bounded exact scheduler artifact and exhaustive small-instance tests |
| 7. Safe operation lifecycle | passed | `docs/evidence/gdo/operation_lifecycle_foundation.md` and lifecycle replay artifacts |
| 8. City-defence gate | passed | GDO-4 process-isolation confirmation V6: 30 complete pairs and all mechanism, safety, coverage, source, trace, and latency gates |
| 9. Additional operation pilot | passed | GDO-5 atomic-combat repair pilot: every predeclared operation gate passed |
| 10. Contextual calibration | passed | GDO-8 clean training/disjoint holdout audit and fresh read-only authority diagnostic |
| 11. Limited reversible authority | passed | slice-specific default-off flags, exact commit validation, and limited-live activation tests |
| 12. Historical negative evidence | passed | GDO-9 report retains the 100-pair flow result and its semantic failure |
| 13. Bridge/flow authority gate | passed | GDO-9 is closed with four of seven entry conditions proven; live bridge/flow authority remains disabled |
| 14. Reproducible artifacts | passed | source/trace/self-hashed manifests, retained replays, latency reports, regeneration commands, and 1,063 passing FreeCiv tests |
| 15. GPL boundary | passed | `docs/licensing/freeciv_algorithm_boundary.md`; implementation is repository-native and native parity remains a black-box process boundary |

The transport/founder slice is complete at the contract, capacity, scheduler,
operation, lifecycle, replacement, and retention layers. It remains
default-off because the retained engine corpus contains no advertised embark
sequence; no transport gameplay claim is made. This does not leave the
program definition open because the required additional fresh operation pilot
is the passing atomic-combat slice.

The canonical city-defence mechanism evidence remains V6. V7--V12 are
transparent terminal-score-readout diagnostics. They neither invalidate V6
nor establish a general score or win-rate claim. In particular, the deployed
engine accepted but did not produce V12's optional SCORELOG2 artifact, so that
source remains disabled in the current runtime.

The final GDO-9 outcome is deliberately negative: calibrated grounded
estimates and B4 operations are implemented, while no post-B4 residual proves
that route allocation is the limiting error or that bridge/flow value exceeds
its measured controller cost. Per the plan, further bridge/flow authority is
therefore out of scope until new independent evidence opens the entry gate.

### 22.2 Post-completion GDO-7 shadow confirmation

Status: passed on 2026-08-01

The claim-ineligible `grounded_enabling_operations_diagnostic_v2` cohort adds
a fresh engine confirmation for the production and research extensions. It
ran 10 disjoint paired seeds for 120 turns (20 complete arms, zero
infrastructure failures) with GDO-7A/GDO-7B disabled in baseline and enabled
only as shadow lifecycle observers in treatment.

The source-fresh audit passed every declared gate:

- exact paired score, score-lead, meaningful-action, and technology-gain
  parity;
- 109/109 production and 16/16 research operations attributed to byte-exact
  accepted engine actions;
- 93 authoritative product identities and 6 authoritative technology
  identities observed later, all within their declared deadlines and all
  releasing the exact downstream dependency;
- all research admissions on the proved frontier, one decomposed dependency
  mode, and zero legacy `tech_want` applications;
- grounded production upkeep profiles, an exercised block/repair lifecycle,
  and zero hard production/research slot overallocations;
- zero schema errors, duplicate operation identities, or semantic contract
  violations across 109,431 events.

Canonical evidence:

- `docs/freeciv/evidence/gdo7-grounded-enabling-operations-diagnostic-v2.json`;
- `docs/evidence/gdo/gdo7a_grounded_production.md`;
- `docs/evidence/gdo/gdo7b_grounded_research.md`.

This closes fresh shadow-execution confirmation only. It does not alter the
program's authority boundary and makes no score or win-rate claim. Production
and research remain default-off and require their own predeclared advisory or
bounded-live policy-benefit pilot before receiving authority.

### 22.3 Post-completion GDO-7A bounded-live pilot

Status: completed with a failed overall mechanism gate on 2026-08-01

The claim-ineligible `grounded_production_persistence_pilot_v1` cohort tested
a default-off, same-city production-switch veto over 30 fresh paired seeds and
120 turns. All 60 arms completed with zero infrastructure failures and zero
engine rejections. The source-fresh audit validated 419,358 events with no
schema warnings or errors.

The bounded treatment reduced unique queue divergence from 15.32% to 8.50%,
increased completion from 77.44% to 85.84%, increased completed products/game
by 0.833, and produced a paired mean score delta of +0.9. The score interval
[-0.867, 3.2] crosses zero and the exact paired randomization p-value is 0.5;
no score or win-rate claim is supported.

Twelve of 13 declared gates passed. The pilot failed the predeclared zero
`guarded_operations_do_not_diverge` gate because 13 previously guarded
operations later diverged. Trace RCA found no same-snapshot override: 11 later
switches followed entry of a visible threat into the safety radius and two
followed negative operating gold for an upkeep-bearing product. Those are
required authority-relinquishment conditions. The result remains a failure
rather than being rescored post hoc.

Production persistence authority remains default-off. A corrected follow-on
must predeclare snapshot-local protection and reason-coded safety
relinquishment, use disjoint seeds, retain all completion/throughput/safety
floors, and remain separate from any powered score confirmation.

Canonical evidence:

- `docs/freeciv/evidence/gdo7a-production-persistence-pilot-v1.json`;
- `docs/evidence/gdo/gdo7a_production_persistence_pilot.md`.

### 22.4 Post-completion GDO-7A snapshot-local confirmation

Status: all corrected mechanism gates passed on 2026-08-01

The claim-ineligible `grounded_production_persistence_snapshot_pilot_v2`
cohort corrected the first pilot's evidence contract without retuning its
controller. One application protects only the current authoritative snapshot;
the audit separately requires proof whenever a previously guarded operation
is relinquished on a later snapshot.

All 30 fresh pairs and 60 arms completed at frozen commit
`c17d7d85769039aa138e384d6c6e98fb67251ae9`, with zero infrastructure
failures, zero engine rejections, and zero schema errors across 396,093
events. All 13 declared gates passed:

- 3,914 treatment guard applications and zero baseline authority rows;
- zero accepted excluded switches within a protected snapshot;
- all nine later relinquishments attributed to authoritative negative food
  (five), visible threat (three), or completion-bound excess (one);
- unique divergence reduced from 15.83% to 8.06% (-7.78 points);
- completion increased from 78.89% to 84.72% (+5.83 points);
- completed products/game increased from 9.967 to 10.167 (+0.200); and
- no scope, source-freeze, or score-safety-floor violation.

This establishes that the same bounded controller improves the declared
production-continuity mechanism while honoring its snapshot-local safety
contract. It does not establish general score benefit. Paired score was +0.9
with a 95% interval of [-0.3, 2.5] and exact randomization p=0.359375; the
cohort was not claim-eligible. Authority therefore remains default-off pending
a separately frozen and adequately powered score confirmation.

Canonical evidence:

- `docs/freeciv/evidence/gdo7a-production-persistence-snapshot-pilot-v2.json`;
- `docs/evidence/gdo/gdo7a_production_persistence_snapshot_pilot.md`.

---

## 23. Recommended first implementation issue

**Issue title:** Add candidate-invariant grounded transition estimates in shadow mode

### Deliverables

1. `EstimateAuthority`
2. `TransitionContextKey`
3. `EstimateValidity`
4. `GroundedTransitionEstimate`
5. `DomainTransitionModelRegistry`
6. `LegacyProjectionTransitionModel`
7. shadow adapter integration
8. typed expected-relief helper
9. candidate-invariance test suite
10. estimate events and abstention reason codes
11. runtime flag defaulting to false
12. no live-policy difference

### Acceptance

```text
Given the same snapshot and legal action:
- adding an unrelated stronger candidate does not change the estimate;
- duplicating candidates does not change the estimate;
- candidate order does not change the estimate;
- scaling legacy utilities does not change the estimate;
- live action trace equals the frozen comparator;
- stale/ruleset-mismatched estimates cannot claim authority.
```

This issue provides the semantic foundation for every later stage and should merge before movement, combat, resources, or operations are built.

---

## 24. Recommended second implementation issue

**Issue title:** Add identity- and time-bearing resource claims with shadow exact scheduling

### Deliverables

1. resource contract module;
2. capacity extractor;
3. reservation ledger;
4. identity-aware greedy scheduler;
5. bounded exact scheduler;
6. v1 packet compatibility adapter;
7. commit-rejection release integration;
8. resource events;
9. exhaustive small-instance tests;
10. no live-policy difference.

### Acceptance

```text
- one unit cannot be selected for two incompatible current operations;
- a city has one production slot;
- turn windows determine conflicts;
- future claims are conditional;
- exact scheduler finds the optimum on exhaustive small cases;
- node-limit fallback is deterministic;
- no hard capacity violation occurs in replay.
```

---

## 25. Coding-agent execution rules

For each implementation task:

1. Read the nearest repository guidance and existing tests before editing.
2. Preserve the current supported path.
3. Add the schema and tests before policy integration.
4. Use Python 3.8-compatible typing.
5. Avoid broad refactors.
6. Keep estimator inputs immutable.
7. Include stable ordering and deterministic digests.
8. Add explicit abstention instead of guessing.
9. Emit reason-coded events.
10. Add a feature flag for any behavior-changing path.
11. Include targeted tests and the relevant full-suite result.
12. Measure controller-inclusive latency.
13. Store experiment manifests and checksums.
14. Do not enable bridge, flow, or generic path persistence.
15. Do not copy or translate upstream Freeciv GPL source.

---

## 26. Source basis

This plan was prepared against:

- the `experimental/pln-pressure–bridge–fluid` branch and its current status/evidence documents;
- the existing unified implementation plan and calibrated follow-on material;
- current code in `planning/impact.py`, `pressure/adapters.py`, `pressure/model.py`, `pressure/packets.py`, `pressure/transitions.py`, `pressure/teleology.py`, `pressure/learning.py`, `pressure/transition_value.py`, `planning/commit_validator.py`, `pf_runtime.py`, and oracle/ruleset modules;
- upstream Freeciv algorithm structure as a conceptual reference for local domain solvers;
- the MIT/GPLv2 licensing boundary between OmegaClaw and Freeciv.

Repository references:

- OmegaClaw branch: <https://github.com/machieke/freeciv-omegaclaw/tree/experimental/pln-pressure%E2%80%93bridge%E2%80%93fluid>
- Upstream Freeciv: <https://github.com/freeciv/freeciv>

---

## 27. Final architectural criterion

The implementation succeeds when the layers have non-overlapping responsibilities:

```text
Freeciv domain models
    answer: what is feasible and what is likely to happen?

PLN evidence and transition records
    answer: why do we believe that, with what support and provenance?

Pressure
    answers: which unresolved goals demand progress?

Operation assembly
    answers: which explicit participants and steps can realize that progress?

Resource scheduling
    answers: which compatible operations fit the actual capacities now?

Commit validation
    answers: is the next step still legal in the authoritative state?

Bridge
    may later answer: which enabling structures connect otherwise separated goals and operations?

Conserved flow
    may later answer: how should genuinely divisible capacity be allocated across a validated operation graph?
```

This separation allows the system to improve Freeciv’s cross-domain coordination without discarding its strong local algorithms, conflating semantics, or repeating an already negative bridge/flow experiment under a new name.
