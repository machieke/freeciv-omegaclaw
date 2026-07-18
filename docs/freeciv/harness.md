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

Before any fresh/retried backend call, `status.json` is atomically replaced with a
`running` record tied to the new manifest identity. If the controller is killed,
operators therefore see an incomplete attempt rather than the prior completion.

An infrastructure failure remains in `status.json` and the aggregate. Retry it with
the same command; never relabel it as a loss or completion. Game losses are completed
outcomes. The report retains losses, null effects, negative deltas, and exclusions at
the same fidelity as wins.

## Statistics and release checks

Binary intervals use Wilson scores. Continuous and paired deltas use the predeclared
deterministic percentile bootstrap, paired by seed. Calibration uses 0.1 buckets,
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
