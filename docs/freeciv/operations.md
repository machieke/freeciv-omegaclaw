# PLN-FreeCiv operations and failure recovery

## Health and identities

Before a live run, verify the service and immutable inputs:

```bash
export OMEGACLAW_ROOT="$(git rev-parse --show-toplevel)"
curl --fail http://127.0.0.1:8002/health
git -C "$FREECIV_LLM_ROOT" rev-parse HEAD
git -C "$FREECIV_LLM_ROOT" apply --reverse --check \
  "$OMEGACLAW_ROOT/scripts/freeciv/upstream/0001-pln-authoritative-state.patch"
ollama list | grep 'qwen3-coder-next'
```

The external commit must be `26ba7124249f34fd3050ef29bf191bd4d8808018`; the reverse
patch check proves the tracked contract patch is applied. A release manifest must also record
its own configuration hash, ruleset hashes, seed, model configuration, and dirty-state flag.

Inspect the effective PF-PLN activation for a completed game with:

```bash
python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); print(json.dumps(value["pf_pln_runtime"], indent=2, sort_keys=True))' path/to/manifest.json
```

An engine-live pressure treatment currently enables exactly phases 0, 1, 4,
and 9. Component-only phases must remain disabled even if their standalone
acceptance benchmark passes. A mismatch between the manifest report and the
backend, capability matrix, or effective impact policy fails before the live
connection is opened.

For model-selection efficiency, inspect the final `metric_sample` events named
`model_selection_call_rate` and `model_selection_call_avoided_rate`, and count
per-turn `goal_selection` events. A `goal_selection` event is valid only for
the versioned canonical-singleton policy; multi-candidate decisions retain
`llm_proposal`. Readiness calls are operational warm-up and are not counted as
goal-selection calls.

Each completed engine arm also records `model_readiness_latency_ms`,
`model_readiness_method`, and `model_readiness_reused` in `status.json`. These
are operational timings, not gameplay outcomes, and make cold-chat versus
resident-refresh cost directly measurable without contaminating the event-based
score analysis. The same status record splits total backend time into
`engine_preflight_latency_ms` (proxy clear plus server recycle),
`engine_gameplay_latency_ms`, and `engine_cleanup_latency_ms`, with
`engine_backend_latency_ms` as the enclosing measurement.

Accepted impact actions receive a bounded 0.5-second authoritative refresh
window with two identical samples at 5 Hz. If the packet-backed effect is not
visible in that window, the action is deferred and reconciled against the next
authoritative snapshot. Do not treat `decision_effect_confirmation_timeouts` as
failures; use the recovered, expired, and pending counters to audit outcomes.

## Port isolation

Real-engine workers own one dedicated port each in 6001-6009. Never run a smoke, state
comparator, or second harness on a port assigned to an active run. Inspect ownership with:

```bash
ps -eo pid,etimes,args | grep 'run_harness.py'
docker exec "$FREECIV_SERVER_CONTAINER" ps -eo pid,args | grep 'freeciv-web.*--port 600'
```

The harness hard-clears proxy-side game metadata, then recycles its server process before each
job; it hard-clears and recycles again afterward. A killed server must be observed at a new PID
before the next connection is allowed. Each retry uses a new operational `attempt_id`, so an
old suspended authentication session cannot be resumed accidentally.

Paired game IDs use deterministic short cohort/arm tokens and remain within the proxy's
50-character termination-contract limit. Pre-run hard-termination errors fail the arm as
infrastructure failures; they are never silently ignored before a server recycle.

## Resuming the harness

Rerun the identical command without `--no-resume`. A game is resumed only when:

- `status.json` is completed;
- the event stream validates;
- the persisted manifest identity equals the current job identity; and
- the persisted configuration hash equals the current configuration hash.

Changed model, confidence, seed, ruleset, engine, capability, or turn settings cause a fresh
run, not reuse. Infrastructure failures remain visible in the aggregate and can be retried;
game losses are completed outcomes and are never relabeled as infrastructure failures.

## Connection or configuration failure

For `E102`, `E142`, handshake timeout, or an exact-configuration mismatch:

1. Confirm no other live runner owns the same port.
2. Inspect `logs/llm-handler-debug.log` and `logs/freeciv-web-log-<port>.log` in the external
   checkout.
3. Hard-terminate the affected game through the proxy or rerun the harness, whose startup and
   `finally` paths both perform the teardown.
4. Verify that the backing server PID changes.
5. Retry the same manifested job. Do not edit its status to completed.

If a server repeatedly loads stale autosave state, stop all owners of that port and restart the
`fciv-net` service. Preserve the failed manifest/status/events before any manual cleanup.

## Model timeout

The model loop has a 30-second whole-turn budget and keeps a two-second reserve for grading,
planning, execution checks, and end-turn. A timeout emits a proposal failure, verification,
logging gap, and a safe exact `end_turn`; it cannot bypass verification. Diagnose with the
`model_latency_ms`, `turn_full_loop_latency_ms`, correction count, and logging-gap events.

Do not increase the timeout only in an environment variable. Any accepted budget change must
be versioned in `profile/freeciv_harness.yaml` and therefore change the manifest identity.

## Event-tail disconnect or restart

The UI reconnects from the last `(game_id, turn, seq)`. The server reads only persisted JSONL,
so an acknowledged event remains replayable after restart. On a visible gap, duplicate,
out-of-order line, incompatible schema, or truncated JSON:

1. stop applying live events;
2. preserve the diagnostic and cursor;
3. restart the tail if needed; and
4. replay from the last accepted cursor.

Never repair UI state directly. Validate the source first:

```bash
PYTHONPATH=src python3 scripts/freeciv/validate_events.py path/to/events.jsonl
```

## Evidence retention

For release/nightly runs retain:

- per-game manifest, status, and exact JSONL;
- run summary, machine-readable aggregate, and Markdown report;
- compiler/parity/state/ETA/equivalence reports and their SHA-256 hashes;
- the release audit; and
- visual verification summary, screenshots, error logs, and recording.

Artifacts may be stored outside Git, but evidence documents must use repository-relative
logical paths and hashes. Tokens, database credentials, and provider secrets must never be
retained.
