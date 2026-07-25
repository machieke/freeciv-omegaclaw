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

Server recycle readiness requires both a fresh dedicated-server PID and an
observed `LISTEN` socket for that port inside the container. The harness polls
those facts at 100 ms; it does not use a fixed post-spawn sleep or open a
protocol connection that could allocate a transient player slot. Publite2
restarts a cleanly exited game after 100 ms, while crashes and launch failures
retain the five-second backoff. After a successful arm, the next arm may accept
the already-listening successor of the recorded prior PID. Failed arms never
publish that shortcut and therefore retain unconditional kill/recycle
isolation. `status.json` records `engine_server_pid` and
`engine_server_recycle_method` for direct audit.

Authoritative refreshes use the v4 proxy contract's bounded
`after_source_seq`/`wait_timeout_ms` hint when a caller requires a newer packet
revision. The optional `accept_unchanged` flag lets a completed quiet wait
return the exact turn/source revision without retransmitting the retained
atomic projection. The harness deadline, 50 ms interval, and independent
stability sample remain authoritative. Repeated
same-sequence queries before the required revision indicate an unpatched or
stale proxy mount. A response whose source sequence advances while its
same-turn research, city, unit, or legal-action payload remains unchanged for
the five-second cache TTL indicates the obsolete turn-only inner extractor
cache. Verify the pinned patch digest before changing timeouts.

Turn-boundary diagnostics are emitted as
`turn_boundary_state_latency_ms`, `turn_boundary_state_query_latency_ms`,
`turn_boundary_state_query_count`, `turn_boundary_state_parse_latency_ms`,
`turn_boundary_state_settle_wait_ms`, `turn_boundary_nonstate_latency_ms`,
and `turn_checkpoint_sync_latency_ms`. Use these components before adjusting
stability or engine timeouts.

Accepted impact actions receive a bounded 0.3-second authoritative refresh
window with two identical samples separated by at least 50 ms. A differing
state, enemy-observation, or exact legal-action digest restarts the stability
count, so the shorter interval reduces settled action latency without accepting
a changing execution catalog. If the packet-backed effect is not
visible in that window, the action is deferred and reconciled against the next
authoritative snapshot. Do not treat `decision_effect_confirmation_timeouts` as
failures; use the recovered, expired, and pending counters to audit outcomes.

Initial and inter-turn readiness gates use the same 50 ms interval whenever
they require consecutive identical decision fingerprints. This retains the
exact state, visible-enemy, and legal-action stability condition while avoiding
an extra 50 ms at every stable boundary. Do not reduce the interval below the
proxy contract's 50 ms minimum guard without a new engine-backed acceptance
cohort.

The separate 500 ms post-`game_ready` quiet period remains intentional. Removing
it moved the first snapshot earlier but increased complete gameplay time in two
independent exact-behavior cohorts, so the candidate was rejected; see
[the adaptive-startup evidence](evidence/adaptive-initial-readiness-rejected.md).

Observer totals are turn-gated as well as population-gated. Initial and
inter-turn global state must be at least as new as the corresponding
authoritative player snapshot. Final scoring normally requires the observer's
post-horizon turn; terminal player elimination instead accepts the absorbing
terminal turn because no next begin-turn packet is expected. Inspect
`final_global_settle_latency_ms` when diagnosing endgame latency. Never restore
a fixed scoring sleep or accept a populated observer response without checking
its authoritative `turn`.

Scheduler-enabled engine runs use packet-visible grounded candidates and do not
invoke the observer-backed scout driver. They therefore query global state only
for initial opponent/score identity and final scoring; plain conditions retain
their per-turn observer refresh for navigation. Inspect
`observer_global_state_queries` (normally `2` for a completed scheduler game).
Final observer timeout is an infrastructure failure—never fall back to a stale
prior-turn score.

## Port isolation

Real-engine workers own one dedicated port each in 6001-6009. Never run a smoke, state
comparator, or second harness on a port assigned to an active run. Inspect ownership with:

```bash
ps -eo pid,etimes,args | grep 'run_harness.py'
docker exec "$FREECIV_SERVER_CONTAINER" ps -eo pid,args | grep 'freeciv-web.*--port 600'
```

The harness hard-clears proxy-side game metadata before every job. It either
kills the current server and observes a new listening PID, or—only after a
successfully completed predecessor—observes that predecessor's distinct clean
successor. It hard-clears proxy metadata afterward but does not duplicate the
same server boundary. Each retry uses a new operational `attempt_id`, so an old
suspended authentication session cannot be resumed accidentally.

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

The UI reconnects from the last `(game_id, turn, seq)`. The server reads only
complete JSONL records. Engine events are atomically appended immediately,
completed turns are fsynced before waiting for the next turn, and
`run_completed` forces final durability. On a visible gap, duplicate,
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
