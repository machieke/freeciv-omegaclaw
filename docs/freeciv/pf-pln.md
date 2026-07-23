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
- `adapters.py`: lossless proof-DAG conversion and opt-in grounded impact
  ranking.

The existing uncertain `BeliefStore` now fuses unique provenance
contributions in evidence-weight space. Its repeated-path behavior remains
idempotent, and it exposes weighted lineage overlap without mixing pressure
into revision.

## Live integration

The experimental harness profiles enable the pressure ranker:

```yaml
impact_policy:
  pressure_enabled: true
  pressure_damping: 0.85
  pressure_exploration_floor: 0.05
  pressure_temperature: 0.15
  pressure_max_routes_per_conclusion: 32
  pressure_learning_enabled: true
  pressure_learning_rate: 0.10
  pressure_no_progress_rate: 0.10
  pressure_initial_conductance: 0.50
```

The impact planner still enumerates only server-advertised legal actions.
PF-PLN groups those grounded candidates under separate survival, expansion,
score, and exploration goals, propagates pressure through procedural OR
routes, and ranks the resulting operations. The selected action still becomes
a snapshot-bound `Plan` and passes through the unchanged execution gate.

Candidate categories have separate learned routes. Credit is applied only
after the candidate-specific authoritative effect predicate succeeds.
Authoritative next-turn no-effect resolution applies bounded no-progress
decay; transport acceptance alone never receives credit. Deferred effects keep
the originating action-result ID so replay cannot apply the same update twice.
The ledger is written atomically to `pressure-conductance.json`, scoped to one
run attempt, and archived with superseded attempts.

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
  conductance, outcome counters, application status, and state hash.

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

## Verification

The PF-specific suite is:

```bash
python3 -m pytest -q Autotests/test_freeciv_pressure.py
```

It covers:

- reproducible capital-defense pressure and an unchanged truth graph;
- pressure reaching multiple false AND prerequisites;
- bounded cyclic transport;
- deterministic wide-route pruning and pressure concentration;
- causal, contextual, and safety firewalls;
- cost appearing only at scheduling;
- exact token union, overlap, decay, and selection-policy provenance;
- conductance credit and no-progress decay;
- confidence loss under maximally disagreeing clones;
- existing proof-DAG adaptation;
- multi-goal impact ranking;
- schema-valid pressure and operation events.

Run the existing belief, event, impact, and harness suites alongside it before
changing pressure defaults.

## Current scope

The implementation is a production-connected PF-PLN vertical slice, not a
claim that all research phases are empirically complete. In particular,
live clone split/merge, pressure-triggered LLM expansion, differentiable truth
execution, and a new paired engine-backed impact claim still require dedicated
experiments before they can be enabled or claimed. Online conductance learning
is enabled for the experimental profile, but no performance claim is made
until historical replay and a fresh paired engine cohort measure it. See the
[phase map](pf-pln-phase-map.md) for the exact implemented, partial, and
pending acceptance work.
