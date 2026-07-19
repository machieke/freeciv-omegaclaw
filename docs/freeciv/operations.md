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
