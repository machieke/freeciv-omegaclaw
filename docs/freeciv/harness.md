# Five-condition evaluation harness

The M7 harness runs one implementation under immutable capability manifests. Its
five conditions are `a_stock_llm`, `b_state_oracle`,
`c_dependency_scheduler`, `d_uncertain_monitor`, and `e_full_loop`. Capability
dependencies are validated at load time and disallowed accesses fail at runtime.

Configuration is versioned in `profile/freeciv_agent.yaml` and
`profile/freeciv_harness.yaml`. Each game persists `manifest.json`, `events.jsonl`,
and `status.json`; aggregation produces `run-summary.json`, `aggregate.json`,
`aggregate-events.jsonl`, and `report.md`.

## Commands

Run the deterministic 250-job implementation/CI matrix:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/m7-representative-current \
  --backend representative --workers 3 --no-resume
```

Run the release engine matrix against the pinned proxy, FreeCiv, and Ollama:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/m7-engine-release-current-20260718 \
  --backend engine-live --workers 3
```

Run one full-loop engine smoke:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/m7-engine-smoke --backend engine-live \
  --workers 1 --limit-seeds 1 --main-only --condition e_full_loop
```

The real 200-turn model-latency gate has its own versioned profile:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness_200_turn.yaml \
  --out artifacts/freeciv/m6-engine-200-turn --backend engine-live \
  --workers 1 --limit-seeds 1 --main-only --condition e_full_loop
```

The exploratory 960-turn horizon extension uses the same single-game shape
with its versioned long-horizon profile:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness_960_turn.yaml \
  --out artifacts/freeciv/pf-pln-960-turn-live-tail \
  --backend engine-live --workers 1 --limit-seeds 1 \
  --main-only --condition e_full_loop
```

This extended run is diagnostic and does not create a score or win-rate claim.
Its long-horizon treatment enables the v1.3 ruleset capability policy:
the confirmed five-city expansion capacity, ruleset-derived modernization,
naval response with 80-turn visible-threat memory,
industrial/research/commerce infrastructure, and authoritative score-gap
pressure. The previously rejected global luxury, city-governor, Monarchy, and
speculative overexpansion experiments remain disabled. Every production target
must still be in the current server legal set and pass upkeep, horizon, and
execution gates. Commerce repair is limited to one self-financing project at a
time, twice the ordinary treasury reserve, and a maximum 20-turn completion
ETA; the selected city's Coinage contribution is removed before evaluating
that counterfactual.

The versioned 2,000-turn continuation profile preserves the same first seed,
opponent, model, and policy while extending both the policy and engine
horizons:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness_2000_turn.yaml \
  --out artifacts/freeciv/pf-pln-strategic-2000 \
  --backend engine-live --workers 1 --limit-seeds 1 \
  --main-only --condition e_full_loop
```

This remains a single-seed lifecycle and stability diagnostic, not a paired
score or win-rate claim.

Scheduler-enabled engine conditions also use the declared grounded gameplay impact
policy in `impact_policy`. See [impact-policy.md](impact-policy.md) for its exact
action priorities, safety boundaries, and decision-impact metrics. For CPU-hosted
Ollama, preload the configured model before timed runs if its cold load exceeds the
per-turn model budget; the harness reports any resulting safe fallbacks rather than
hiding them. Engine runs use the fail-closed
`chat-once-expiry-aware-resident-v2` readiness policy: one complete chat validates
each controller process and model tuple. Later arms reuse the exact `/api/ps`
resident-model row when its parsed expiry remains at least 300 seconds away.
Missing, malformed, or near-expiry rows take the zero-token keep-alive refresh
path, and refresh failure falls back to the complete chat contract.

The outcome experiment for that policy is a separate paired baseline/treatment track
so the five-condition release matrix remains unchanged. It has disjoint development,
pilot, 100-pair score-confirmatory, and 450-pair joint-confirmatory cohorts. See
[paired-impact-evaluation.md](paired-impact-evaluation.md) for endpoint semantics,
fresh-seed derivation, clean-source gates, power declarations, and claim rules.

## FDAS shadow selection

The default harness remains on `profile/dependent_atomspace.yaml`, where the
rich runtime is disabled. A shadow experiment can select
`profile/dependent_atomspace_shadow_sampled.yaml` through
`FREECIV_FDAS_CONFIG_PATH`. Configuration loading resolves and hashes that
profile into the behavioral manifest; an empty override fails validation.
Neither the override nor the sampled profile enables policy authority.
The FDAS schema-1.1 declaration independently versions region, corridor,
settlement, recovery, transport, and combat projection flags, so changing one
of those shadow slices changes the manifest identity without activating the
others.

The experimental bounded city-stability slice requires an explicit matched
profile and manifest pair:

```bash
export FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_city_stability_authority.yaml
export FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_city_stability_authority.json
```

Setting only one override fails closed. Unsetting both immediately restores
the default component-disabled, non-authoritative path. The bounded slice is
an exact legacy-winner pass-through and does not make a gameplay-improvement
claim.

Only one engine-live controller may run at once. It owns
`artifacts/freeciv/.engine-live.lock`; its workers receive fixed ports within
6001-6009 and each worker serializes its own games. Induction games are globally
sequential so opponent memory always observes the declared order.

## Resume and identity

Rerun the identical command to resume. A completed job is reused only when its event
log validates and both persisted `manifest_identity` and `configuration_hash` equal
the current values. Individual worker/port assignment is operational and excluded
from behavioral identity, while total controller concurrency is included because it
changes local-model queueing and bounded-fallback behavior. A changed seed, model,
capability, belief parameter, opponent, ruleset, turn limit, or worker count forces a
fresh game.

Every backend invocation also records a distinct `attempt_id` and includes it in the
proxy agent identity without including it in behavioral identity. Before the new
civserver is started, the backend hard-terminates any proxy game metadata left by an
interrupted attempt. Retries therefore cannot resume an older session or inherit an
"already configured" marker for a newly recycled server.
The preflight status separates proxy-clear and server-recycle latency. A clean
successor reuses its initial distinct-PID result for the listening check; it does
not repeat the same container process query. Process identity and listener state
are captured by one container-side inspection, so a successful poll needs one
Docker execution while preserving both checks.

Before any fresh/retried backend call, `status.json` is atomically replaced with a
`running` record tied to the new manifest identity. If the controller is killed,
operators therefore see an incomplete attempt rather than the prior completion.

Engine event streams use `EventWriter`'s explicit `turn` sync mode. Individual
records remain validated atomic appends and are immediately available to the
persisted-first tail. The harness forces a sync after each
`turn_full_loop_latency_ms` record; transition detection provides a second
boundary guard, and `run_completed` forces the final sync. Representative and
other writers retain their existing durability mode.

Scheduler-enabled engine jobs issue exactly two observer-global queries during
a normal completed game: initial paired identity/fidelity and authoritative
post-horizon scoring. Their grounded planner consumes only the player snapshot,
so the former per-turn observer refresh was unused. Non-scheduler conditions
retain per-turn queries for the observer-backed scout driver. The emitted
`observer_global_state_queries` metric audits this boundary.

An infrastructure failure remains in `status.json` and the aggregate. Retry it with
the same command; never relabel it as a loss or completion. Game losses are completed
outcomes. The report retains losses, null effects, negative deltas, and exclusions at
the same fidelity as wins.

## Statistics and release checks

Binary arm intervals use Wilson scores. Continuous and paired deltas use the
predeclared deterministic percentile bootstrap, paired by seed. Paired score-lead
rates additionally use an exact two-sided McNemar test and a seed-pair bootstrap risk
difference interval. A confirmatory score claim additionally requires an exact
two-sided within-seed sign-flip randomization test; the confidence interval and
randomization test must both pass. Calibration uses 0.1 buckets,
minimum ten samples per populated acceptance bucket, and +/-0.15 tolerance. The
release gate requires:

- 30 identical-seed main games for every condition;
- 20 ordered same-opponent games for each memory-enabled condition;
- 30 graded and 30 ungraded full-loop games;
- zero hidden infrastructure failures;
- schema- and causally-valid input event streams; and
- byte-identical `aggregate.json` on unchanged input.

The metrics UI reads `aggregate-events.jsonl` and does not recompute intervals or
calibration. See [Phase 11 evidence](evidence/phase-11-m7-v4.md) and
[operations](operations.md) for recovery procedures.
