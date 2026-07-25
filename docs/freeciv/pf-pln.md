# Pressure-Field PLN integration

## Outcome

PF-PLN is implemented as a control layer over the existing FreeCiv agent. It
does not replace the mechanically compiled rules, crisp dependency oracle,
authoritative state bridge, uncertain belief store, execution gate, or engine.
Those components remain the source of truth. PF-PLN decides which admissible
inference, observation, expansion, retention, or action operation should
receive bounded attention.

The implementation follows this pipeline:

```text
goal demand
  -> reverse rule transport
  -> mode resolvability
  -> expected relief / scalarized cost
  -> existing plan and execution gate
```

The distinctions are enforced in code:

- dependency pressure is not operational pressure;
- operational pressure is not scheduled budget;
- utility and pressure are not truth inputs;
- association and diagnosis cannot authorize actions;
- safety goals veto harmful operations instead of merely lowering their score;
- operation cost is applied only by the scheduler;
- pressure remains keyed by goal until scheduling.

## Package boundaries

`src/freeciv_agent/pressure/` contains:

- `model.py`: immutable truth views, atoms, goals, typed pressure,
  resolvability, reverse-rule declarations, operations, and vector costs;
- `engine.py`: damped reverse transport, AND blocker allocation, OR route
  allocation, residual scheduling, action-path gating, traces, and
  conductance credit;
- `scheduler.py`: multi-goal aggregation, expected relief per cost,
  information/coherence/option value, safety and causal firewalls, selection,
  and soft budget allocation;
- `provenance.py`: immutable evidence tokens, decayed evidence weight,
  token-set union, weighted-Jaccard lineage overlap, conflict severity, and
  observation-selection policy records;
- `lifecycle.py`: bounded clone posteriors, Bayes updates,
  variance-matched visible truth, pressure projection, and split/merge gates;
- `induction.py`: scoped pattern mining, contextual generalization,
  structure-checked analogy, expansion gating, held-out replay, and the
  quarantined rule lifecycle;
- `adapters.py`: lossless proof-DAG conversion and opt-in grounded impact
  ranking.

`src/freeciv_agent/llm/gateway.py` retains the existing constrained proposer,
claim verifier, quarantine, and goal grader while making model invocation a
typed `expand` operation subject to expected value, validation cost, and hard
token reservations.

The existing uncertain `BeliefStore` now fuses unique provenance
contributions in evidence-weight space. Its repeated-path behavior remains
idempotent, and it exposes weighted lineage overlap without mixing pressure
into revision.

High-confidence, provenance-distinct disagreement is now materialized as an
explicit `Conflict` atom rather than hidden by the aggregate mean. Conflict
creation uses declared minimum-confidence and severity thresholds, retains
both immutable lineages, and never changes authoritative state. When the
lineages came from different stable evidence contexts, the store exposes
deterministic context-quarantine operations. Applying one excludes the
incompatible lineage only from that contextual belief view; the global
evidence ledger and the opposing contextual view remain intact.

Uncertain deductions carry their complete atom/rule ancestry. The store
rejects a derivation if its target already occurs in that ancestry or if it
tries to derive an atom from its own observation token. Materialized
`belief_conflict` and `context_quarantine` events are schema validated, and a
quarantine event must directly cite and exactly partition a preceding conflict
event. Phase 2 implementation and adversarial benchmark evidence are recorded
in
[`evidence/pf-provenance-contradiction-phase-2.md`](evidence/pf-provenance-contradiction-phase-2.md).

## Observation value and simulator containment

Phase 3 adds exact, myopic one-step expected information gain over a bounded
discrete hypothesis set. Each candidate test declares every outcome likelihood
for every hypothesis. The evaluator enumerates those outcomes, computes
expected posterior entropy, and passes information value, pressure relief, and
the existing vector cost to the same scheduler used for actions. Observation
and action choices therefore compete under one cost-aware decision rule.

Active conflict atoms can inject `observe` pressure into this planner. Candidate
tests require an immutable simulator ID, version, model hash, exactness flag,
and confidence cap. Scheduling a test records both that model provenance and
the goal-conditioned observation policy. Merely simulating an outcome does not
write truth: a result must enter through the evidence store, and an inexact
simulator cannot exceed either its own declared confidence cap or the
configured global cap.

Goal-selected observations are treated as selectively sampled. A recorded
propensity conservatively scales their evidence confidence; when propensity is
unknown, the declared `selection_unknown_discount` widens uncertainty instead
of treating the sample as representative. This is a containment approximation,
not a claim of unbiased causal identification.

The exhaustive parity and abduction-selection evidence is recorded in
[`evidence/pf-observation-voi-phase-3.md`](evidence/pf-observation-voi-phase-3.md).

## Persistent latent-clone lifecycle

Phase 5 adds a durable clone lifecycle store around the existing posterior,
truth, and pressure projections. Each visible atom has a hard clone cap.
Bayesian updates, accepted splits, and guarded merges are serialized and
atomically replaced on disk; replaying an event ID is idempotent. Split and
merge operations preserve posterior mass.

Retired clone IDs forward through a persistent lineage DAG. A reference to a
split parent resolves to all active children; if those children later merge,
the same old reference resolves to the merged clone. Forwarding cycles,
wrong-atom children, mass loss, cap overflow, dissimilar merges, and
noncanonical transactions fail closed.

Merge eligibility now includes truth, pressure, and successor-distribution
distance. Visible pressure supports both posterior expectation and an explicit
worst-tail projection for safety-sensitive goals. Live profiles do not
silently enable splitting; consumers must supply the persistent store and pass
the declared predictive-gain, complexity, split-score, cap, and merge gates.

The exact hidden-context ablation and persistence evidence is recorded in
[`evidence/pf-clone-lifecycle-phase-5.md`](evidence/pf-clone-lifecycle-phase-5.md).

## Live integration

The experimental harness profiles enable the pressure ranker:

```yaml
impact_policy:
  pressure_enabled: true
  pressure_damping: 0.85
  pressure_exploration_floor: 0.05
  pressure_temperature: 0.15
  pressure_max_routes_per_conclusion: 32
  pressure_survival_threat_radius: 3
  pressure_learning_enabled: true
  pressure_learning_rate: 0.10
  pressure_no_progress_rate: 0.10
  pressure_initial_conductance: 1.00
```

The impact planner still enumerates only server-advertised legal actions.
PF-PLN groups those grounded candidates under separate survival, expansion,
score, and exploration goals, propagates pressure through procedural OR
routes, and ranks the resulting operations. The selected action still becomes
a snapshot-bound `Plan` and passes through the unchanged execution gate.

Live goal truth is derived from the same immutable authoritative snapshot and
grounded legal-candidate set. Survival is satisfied when there is no grounded
city-defense deficit and no packet-visible opponent within the configured
wrapped distance of an owned city (or an owned unit when no city exists).
Distant visible opponents remain authoritative observations but do not create
existential safety pressure. Expansion is the bounded owned-city count divided
by the configured city target; score and exploration remain active only while
the current legal set contains a grounded operation for them. Each derivation
and the threat radius are recorded in the goal context carried by
`pressure_propagated`.

Candidate categories have separate learned routes. Immediate action effect and
goal relief are distinct observations. A candidate-specific no-effect result
receives full no-progress decay. A local effect with no measurable goal
progress receives one-quarter decay and no positive teleological credit.
Authoritative direct goal progress receives monotonic bounded credit.

The planner also retains at most one successful, goal-neutral route per
category and goal. When a later candidate produces authoritative progress for
that same goal, each distinct pending category can receive one idempotent
downstream update. Repeated movement therefore cannot multiply credit. Each
update identifies whether it is no-effect, effect-without-relief, direct
relief, or downstream relief, names the relief source, and links downstream
credit to the feedback event which established goal progress. City-count,
owned-population recovery, visible-target hit-point reduction, fortified
defense posture, new visible map area, and resolved known huts are the only
currently admitted relief predicates. Production-target changes and actor
movement alone are not relief.

Deferred effects keep the originating action-result ID so replay cannot apply
the same update twice. The conductance ledger is written atomically to
`pressure-conductance.json`, scoped to one run attempt, and archived with
superseded attempts. Pending route traces are process-local and conservative
on restart: losing a trace can omit downstream credit but cannot invent it.

Server-advertised but untried category routes start optimistically at
conductance 1.0. Grounded no-progress feedback decays them from that prior.
This prevents a frequently exercised instrumental movement route from
automatically suppressing a rare, immediately legal goal-completion route.

Candidate/site suppression is applied before category learning. When the
remaining legal set exposes a new direct settlement completion or an exact
move onto a packet-known hut, failure learned under other action groundings
cannot penalize that completion a second time. Its effective conductance is
floored at the configured initial prior for that decision only, provided it is
also the highest-valued current action serving its goal. The learned ledger is
not mutated, preparatory routes retain learned conductance, and each decision
records learned/effective values plus the authoritative floor source.

Reverse expansion uses a deterministic expected-transport beam, configured by
`pressure_max_routes_per_conclusion`. Conclusions with at most 32 routes are
unchanged; wider conclusions expand the 32 highest-value routes with stable
rule-ID tie breaking.

## Pressure-concentration benchmark

Run the host-only benchmark with:

```bash
python3 scripts/freeciv/benchmark_pressure.py
```

The checked 128-decoy, depth-four fixture compares the pressure beam with
exhaustive backward premise expansion. The current deterministic artifact
selects the relevant route, leaves truth unchanged, concentrates 99.54% of
transported non-root pressure on the relevant chain, and expands 128 rather
than 516 premise edges—a 75.19% reduction. These are synthetic control-path
metrics, not gameplay or score claims. The checked result is stored in
[`evidence/pf-pressure-concentration.json`](evidence/pf-pressure-concentration.json).

## Offline pressure replay

Complete authoritative captures can be replayed without an engine:

```bash
python3 scripts/freeciv/replay_pressure_snapshots.py \
  benchmarks/freeciv/samples/real_state_turn0.json \
  benchmarks/freeciv/samples/real_state_turn1.json
```

The replay constructs one immutable snapshot, enumerates candidates independently
with pressure off and on, verifies identical candidate sets, checks the pressure
decision artifact, and hashes the source before and after. The turn-one capture
contains 134 legal actions and 35 grounded impact candidates. Initial replay
exposed a hash-based tie-ordering defect between equivalent founding actions;
the ranker now preserves canonical planner order when pressure priorities tie.
After that correction both modes select the same actor and category. The checked
artifact is
[`evidence/pf-pressure-snapshot-replay.json`](evidence/pf-pressure-snapshot-replay.json).

Legacy event logs can be classified or replayed with:

```bash
python3 scripts/freeciv/replay_pressure_decisions.py PATH
```

Pre-PF `state_snapshot` events retain the legal-action digest but not the full
legal-action set, so the tool marks them audit-only instead of inventing missing
candidates. PF-enabled `operation_scored` events contain the complete grounded
candidate set and support exact pressure-selection versus unpressured-order
comparison plus schedule-hash verification. The checked two-arm legacy finding
is stored in
[`evidence/pf-pressure-replay-legacy-cohort.json`](evidence/pf-pressure-replay-legacy-cohort.json).

## Pressure-only paired pilot

`pressure_ablation_pilot_v1` predeclares 40 fresh, seed-disjoint pairs at a
60-turn horizon. It reuses the existing paired-seed ordering, fixed-horizon
outcomes, source-freeze, retry, initial-state-fidelity, and safety gates. The
fully merged arm policies are validated to differ in exactly two coupled keys:

```text
baseline:  pressure_enabled=false, pressure_learning_enabled=false
treatment: pressure_enabled=true,  pressure_learning_enabled=true
```

All production, horizon scoring, no-effect handling, model, ruleset, engine,
and controller settings remain identical. Run a smoke prefix only after
committing the source:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-ablation-pilot-v1 \
  --backend engine-live \
  --cohort pressure_ablation_pilot_v1 \
  --limit-pairs 1
```

Omit `--limit-pairs` to execute the full pilot. The cohort is intentionally
claim-ineligible: it estimates paired variance and operational behavior for a
new confirmatory design. It cannot be combined with the earlier
static-priority versus horizon-score experiment.

### Completed v1 result

All 40 v1 pairs completed under clean commit `e790316` with zero infrastructure
failures and passing source, initial-state, policy-isolation, and safety gates.
The pressure treatment changed mean score by -0.175 points (95% paired
bootstrap interval [-1.05, 0.825], paired randomization p=0.789). Its observed
fixed-horizon lead rate was 22.5% versus 17.5% for baseline, but only four
pairs were discordant (McNemar p=0.625). This is a neutral,
claim-ineligible pilot result.

The paired score SD was 3.0875, so the predeclared power calculation recommends
at least 30 fresh pairs to detect a two-point effect at 80% power. The
confirmatory cohort is intentionally deferred. Exact replay found that pressure
changed 566 of 3,061 decisions and displaced an immediately legal
city-founding action 230 times. The adapter must first correct its pessimistic
prior for untried routes and replace constant goal strengths with
authoritative snapshot-derived values, then run a fresh seed-disjoint pilot.
Full results and artifact hashes are in
[`evidence/pf-pressure-ablation-pilot-v1.md`](evidence/pf-pressure-ablation-pilot-v1.md).

`pressure_ablation_pilot_v2` is the fresh, claim-ineligible validation cohort
for the grounded-goal and optimistic-prior correction. It contains 40 new
SHA-derived pairs in the disjoint 2400000-2499999 range and retains the exact
same two-key arm isolation. Run a committed smoke prefix with:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/pf-pressure-ablation-pilot-v2 \
  --backend engine-live \
  --cohort pressure_ablation_pilot_v2 \
  --limit-pairs 1
```

Omit `--limit-pairs` only after the smoke trace demonstrates grounded goal
contexts, optimistic initial conductance, exact replay, and direct
goal-completion preservation. V1 and v2 results must not be pooled.

### Completed v2 result

All 40 v2 pairs completed under clean commit `c2ad563` with zero
infrastructure failures and passing source, initial-state, policy-isolation,
safety, grounded-context, and exact-replay gates. The pressure treatment
changed mean score by +0.075 points (95% paired-bootstrap interval
[-0.125, 0.300], paired randomization p=0.654). Fixed-horizon lead rate was
10.0% versus 7.5%, but only one pair was discordant (McNemar p=1). V2 is a
neutral, claim-ineligible result.

The semantic correction reduced decision changes from 18.49% in v1 to 10.31%
in v2 and reduced city-founding displacements from 230 to 16 across the
separate diagnostic cohorts. The remaining three same-goal substitutions to
another expansion move each followed exactly four grounded no-progress
outcomes. Action-rate and latency overhead became indistinguishable from zero.

The observed paired score SD was 0.6938 and the upper score-effect interval was
only 0.300 points. A confirmatory cohort is therefore not frozen. Downstream
goal-relief credit and deterministic offline acceptance were added after v2.
The fresh 40-pair goal-relief pilot then found a -0.05 score delta with
interval [-0.775, 0.600], so no confirmatory cohort is frozen. Threat-relevant
survival grounding was then accepted in a fresh 40-pair engine/replay pilot.
It reduced inappropriate tactical substitutions and improved explored
positions, but its score delta was only +0.10 with interval
[-0.725, 1.050], and fixed-horizon lead rate changed by -2.5 percentage
points. No confirmatory cohort is frozen.

The 81 remaining substitutions into `city_defense` exposed another semantic
issue: a legal fortification opportunity counted as a defense deficit even
though a combat unit was already on the city tile. Defense-relevance grounding
now preserves urgent fortification under a proximate threat while preventing
routine fortification from manufacturing survival pressure.
The initial goal-relief semantic gate is recorded in
[`evidence/pf-goal-relief-offline-acceptance.md`](evidence/pf-goal-relief-offline-acceptance.md).
Full engine evidence is in
[`evidence/pf-pressure-goal-relief-pilot-v1.md`](evidence/pf-pressure-goal-relief-pilot-v1.md)
and
[`evidence/pf-pressure-threat-relevance-pilot-v1.md`](evidence/pf-pressure-threat-relevance-pilot-v1.md);
the preceding v2 evidence is in
[`evidence/pf-pressure-ablation-pilot-v2.md`](evidence/pf-pressure-ablation-pilot-v2.md).

Defense-relevance grounding subsequently passed a fresh 40-pair engine/replay
pilot. Substitutions into `city_defense` fell from 81 to 4, but score changed
by only +0.05 with interval [-0.300, 0.475] and fixed-horizon lead rate was
unchanged. The dominant remaining bias is action enumeration: category
pressure is divided across every legal alternative before cross-goal
comparison, so adding equivalent expansion moves can make exploration win.
The grounded Impact adapter now compares pressure at category level and uses
grounded utility within each category. Candidate atoms and generic OR-route
transport remain intact for complete provenance, while adding dominated legal
alternatives no longer changes the winning goal. Full defense evidence is in
[`evidence/pf-pressure-defense-relevance-pilot-v1.md`](evidence/pf-pressure-defense-relevance-pilot-v1.md).
Deterministic category-invariance acceptance is in
[`evidence/pf-category-invariance-offline-acceptance.md`](evidence/pf-category-invariance-offline-acceptance.md).

The category-invariance correction then passed its fresh 40-pair engine/replay
pilot with zero failures and zero invariant violations across 2,553 treatment
decisions. Expansion-to-exploration substitutions fell from 66 in the prior
seed-disjoint pilot to 29, but score changed by -0.225 with interval
[-0.800, 0.325], fixed-horizon lead rate changed by -2.5 percentage points,
and settlement attempts changed by -0.20. This is semantic acceptance only,
not evidence of a performance improvement.

Replay now exposes the next issue without relying on goal-weight tuning:
absolute grounded action value is normalized independently within each goal
before category pressures are compared. High-value immediate hut exploration
and city founding can therefore lose to lower-value operations from another
non-safety goal. Cross-goal opportunity cost must be integrated exactly once
while retaining category invariance and allowing authoritative urgent survival
pressure to preempt non-safety value. Full pilot evidence and artifact
identities are in
[`evidence/pf-pressure-category-invariance-pilot-v1.md`](evidence/pf-pressure-category-invariance-pilot-v1.md).

Cross-goal opportunity cost is now applied only by the scheduler. Every
operation serving one goal shares the difference between that goal's best
grounded action value and the best currently actionable goal value. This
retains category enumeration invariance and within-goal conductance learning.
When an authoritative survival deficit is active and a grounded survival
operation exists, non-survival operations are explicitly rejected by the
lexicographic safety firewall; if no survival operation exists, the legal set
is not exhausted by the firewall.

Read-only counterfactual replay over the preceding 2,553 decisions removes 82
substitutions, reduces grounded utility regret by 51.3%, and eliminates all
safe city-founding, known-hut, and expansion-to-exploration displacements.
The replay holds outcomes fixed and therefore is not score evidence. The
correction, limitations, reproduction command, and fresh predeclared
`pressure_opportunity_cost_pilot_v1` gate are recorded in
[`evidence/pf-opportunity-cost-offline-acceptance.md`](evidence/pf-opportunity-cost-offline-acceptance.md).

That fresh gate subsequently completed 40/40 pairs and 80/80 engine arms with
zero failures. Score changed by +0.175 with interval [-0.175, 0.550] and
fixed-horizon lead rate changed by +5.0 percentage points with interval
[0.0, 12.5]. All 107 actionable-safety decisions selected survival work, all
80 schemas passed, and all 2,535 treatment decisions replayed exactly. These
are the first positive score and lead point estimates from a fresh pressure
pilot, but the score interval crosses zero and only two pairs are lead-rate
discordant. The cohort remains claim-ineligible and no confirmation is frozen.
Full results are in
[`evidence/pf-pressure-opportunity-cost-pilot-v1.md`](evidence/pf-pressure-opportunity-cost-pilot-v1.md).

The subsequent paired heterogeneity audit found that exact-site pruning and
global category conductance were both consuming the same failure evidence.
Candidate-scoped direct-completion optimism, deterministic gates, exact
2,535-decision retrospective replay, and the fresh
`pressure_direct_completion_pilot_v1` declaration are recorded in
[`evidence/pf-direct-completion-offline-acceptance.md`](evidence/pf-direct-completion-offline-acceptance.md).

That fresh 40-pair gate passed every semantic and replay invariant. Its
claim-ineligible score delta was +0.475 with interval [0.075, 0.975], while
lead-rate evidence remained sparse and inconclusive. The result and frozen
100-pair score-only confirmatory design are recorded in
[`evidence/pf-pressure-direct-completion-pilot-v1.md`](evidence/pf-pressure-direct-completion-pilot-v1.md).

The predeclared confirmation subsequently completed all 100 pairs and 200
engine arms with zero failures, exact arm-order balance, matched initial
states, passing safety gates, 200 valid event schemas, and exact replay of all
6,726 treatment decisions. Its standalone score delta was +0.03 with interval
[-0.25, 0.31] and exact sign-flip p=0.8912 across 34 nonzero pairs. The
predeclared +0.5-point superiority claim is not supported, and the pilot and
confirmation are not pooled. Correctness, safety, provenance, artifact
identity, and secondary diagnostics are recorded in
[`evidence/pf-pressure-direct-completion-confirmatory-v1.md`](evidence/pf-pressure-direct-completion-confirmatory-v1.md).

Direct `GroundedImpactPlanner` consumers remain backward compatible:
`pressure_enabled` defaults to `false` unless the runtime profile enables it.
This preserves unit-level policy isolation and makes an unpressured ablation
available without a code fork.

## Event contract

Three schema-validated events expose the control path:

- `pressure_propagated`: goals, graph identity, dependency pressure,
  operational pressure, transport trace, and configuration;
- `operation_scored`: per-goal effects, conflict penalty, scalarized cost,
  priority, budget allocation, and selected operation.
- `conductance_updated`: grounded feedback identity, prior and posterior route
  conductance, outcome counters, application status, direct/effect-only/
  downstream credit kind, realized relief, relief provenance, causal feedback
  link, no-progress amount, and state hash. Legacy v1 events remain valid.

In live runs the causal chain is:

```text
prior event
  -> pressure_propagated
  -> operation_scored
  -> plan_created
  -> action_sent
  -> action_result
  -> state_snapshot
  -> conductance_updated
```

The observability application remains trace-only; no pressure formula is
recomputed in TypeScript.

## Firewalls

### Epistemic

`PressureRule` intentionally has no forward truth function. `PressureEngine`
accepts immutable `TruthState` inputs and returns a separate `PressureResult`.
Running pressure propagation cannot change graph atoms or belief values.

### Provenance

Evidence IDs are immutable tokens. Union is set union, so a repeated token or
the same observation arriving through multiple proof paths contributes once.
Overlap is the decayed weighted intersection divided by the decayed weighted
union.

### Causal and contextual

Only `causal` and `procedural` reverse paths transport action pressure.
Associative and diagnostic paths may still transport inference or observation
pressure. A path below the configured compatibility threshold cannot carry
action pressure.

### Safety and commitment

An operation harmful to a safety goal is inadmissible regardless of weighted
benefit. Action execution remains subject to the repository's independent
commitment, monitor, snapshot, legal-action, and engine checks.

### Induction and analogy

`PatternMiner` searches a bounded feature-combination space inside exact
opponent, ruleset, era, geometry, and diplomacy contexts. Its immutable
`InducedRuleProposal` contains the complete training population and provenance,
the canonical induction-trigger factors, and remains quarantined.

`ContextGeneralizer` and `StructuralAnalogy` also return quarantined proposals.
Analogy requires matching relational profiles, full role mapping, exact
context, explicit provenance, and transfer reliability. `ExpansionGate`
creates validation work only from typed `expand` pressure when expected value
clears validation cost.

`ReplayValidator` enforces disjoint episode and provenance populations. It
promotes only rules that improve held-out Brier score and activated-rule
calibration without raising contradiction rate. `InductionLedger` persists
that lifecycle atomically and exposes only promoted rules. No mining,
similarity, or replay API writes to truth or the executable pressure graph.

### LLM gateway

`GatewayRequest` is a typed high-pressure graph-gap document rather than a
free-form environment prompt. `PressureLLMGateway` applies the canonical
expansion-pressure, useful-proposal probability, expected-relief, and total
cost quotient before reserving tokens. `PressureGatedTurnLoop` makes no model
call when that admission fails.

Admitted output is parsed by the existing strict JSON schema and wrapped as a
low-confidence `GatewayProposalEnvelope`. The envelope is always
`quarantined`, records model/prompt/context/token provenance and a
`ValidationPlan`, and can reach planning only through the existing claim
router and goal grader. Failed, oversized, or malformed calls consume their
bounded reservation and cannot escape as proposals.

## Verification

The PF-specific suite is:

```bash
python3 -m pytest -q \
  Autotests/test_freeciv_pressure.py \
  Autotests/test_freeciv_pressure_induction.py
```

It covers:

- reproducible capital-defense pressure and an unchanged truth graph;
- pressure reaching multiple false AND prerequisites;
- bounded cyclic transport;
- deterministic wide-route pruning and pressure concentration;
- causal, contextual, and safety firewalls;
- cost appearing only at scheduling;
- exact token union, overlap, decay, and selection-policy provenance;
- conductance effect/relief separation, partial and full no-progress decay,
  monotonic direct credit, and bounded downstream credit;
- confidence loss under maximally disagreeing clones;
- contextual mining, expansion gating, analogy uncertainty, disjoint replay,
  overgeneralization demotion, and persistent quarantine;
- existing proof-DAG adaptation;
- multi-goal impact ranking;
- schema-valid pressure and operation events.

Run the existing belief, event, impact, and harness suites alongside it before
changing pressure defaults.

## Current scope

The implementation is a production-connected PF-PLN vertical slice, not a
claim that all research phases are empirically complete. In particular,
differentiable truth execution and a new paired engine-backed impact claim
still require dedicated experiments before they can be enabled or claimed.
Persistent clone
split/merge is available behind explicit lifecycle gates but is not enabled by
default in gameplay profiles. See the [phase map](pf-pln-phase-map.md) for the
exact implemented, partial, and pending acceptance work.
