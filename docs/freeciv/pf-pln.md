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
The next adapter correction must compare pressure at category level and use
grounded utility within each category. Full evidence is in
[`evidence/pf-pressure-defense-relevance-pilot-v1.md`](evidence/pf-pressure-defense-relevance-pilot-v1.md).

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
- conductance effect/relief separation, partial and full no-progress decay,
  monotonic direct credit, and bounded downstream credit;
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
