# PLN-FreeCiv setup and verification

This is the clean-environment path from checkout to compiled rules, focused tests, a live
engine turn, the replay UI, and a small five-condition harness smoke. Runtime paths are
discovery inputs only; manifests identify the pinned commits, configuration, hashes, model,
and seeds.

## 1. Prerequisites

- Git, Python 3.8 or newer, and the packages in `requirements.txt`.
- Node.js 20 or newer and npm for `apps/freeciv-observability`.
- Docker with Compose v2.
- A checkout of `freeciv-llm` at commit
  `26ba7124249f34fd3050ef29bf191bd4d8808018`.
- Ollama with `qwen3-coder-next:latest` only for the M6/M7 LLM paths. Compiler, oracle,
  state, planner, event, replay, and representative-harness checks need no model endpoint.

Install this repository's dependencies:

```bash
python3 -m pip install -r requirements.txt
npm --prefix apps/freeciv-observability ci
```

## 2. Pin and patch the external stack

Set discovery paths for the current shell. Replace the example path with your checkout;
do not put it in tracked configuration.

```bash
export FREECIV_LLM_ROOT=/path/to/freeciv-llm
git -C "$FREECIV_LLM_ROOT" checkout 26ba7124249f34fd3050ef29bf191bd4d8808018
git -C "$FREECIV_LLM_ROOT" rev-parse HEAD
scripts/freeciv/apply_proxy_patch.sh "$FREECIV_LLM_ROOT"
export FREECIV_RULESET_ROOT="$FREECIV_LLM_ROOT/freeciv/freeciv/data"
```

The patch series is tracked at
`scripts/freeciv/upstream/0001-pln-authoritative-state.patch` and
`scripts/freeciv/upstream/0002-pln-spatial-projection.patch`,
`scripts/freeciv/upstream/0003-pln-unit-lifecycle.patch`,
`scripts/freeciv/upstream/0004-pln-government-and-sustainability.patch`, and
`scripts/freeciv/upstream/0005-pln-sustainability-control.patch`. The
application script verifies every digest, is idempotent, rejects a different upstream
commit, and supports normal checkouts and Git worktrees. It adds the
`pln_authoritative` DTO, monotonic packet sequence, bounded and conditional
source-stability waiting, settled turn-boundary projections, atomic
packet/projection construction, exact packet-known tiles and visibility,
release-game configuration, canonical executable actions, ruleset readiness,
government selection after revolutions, city sustainability and unit support
state, ruleset-aware net gold, city-surplus and upkeep telemetry, bounded tax/science controls,
exact unit rehoming, causal unit-removal attribution, and proxy contract tests.

Verify the patch in the FreeCiv image (the cache secret is test-only and is not persisted):

```bash
docker run --rm --entrypoint /bin/sh \
  -e CACHE_HMAC_SECRET=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  -v "$FREECIV_LLM_ROOT/freeciv-proxy:/docker/freeciv-proxy" \
  freeciv/fciv-net -lc \
  'cd /docker/freeciv-proxy && python3 -m pytest -q \
   tests/test_pln_authoritative_state.py tests/test_release_game_configuration.py'
```

Start or rebuild the mounted development stack:

```bash
docker compose -f "$FREECIV_LLM_ROOT/docker-compose.yml" up -d fciv-net
docker ps --filter name=fciv-net
curl --fail http://127.0.0.1:8002/health
```

Engine harness process isolation waits for a fresh dedicated-server PID and
its exact listening socket; it does not rely on a fixed post-spawn delay.

## 3. Runtime environment

The proxy token is the only required secret in the local live path. Obtain it from the
external stack's deployment configuration; never put it in a manifest, fixture, event log,
or shell transcript retained as evidence.

```bash
export FREECIV_PROXY_URL=http://127.0.0.1:8002
export FREECIV_PROXY_WS=ws://127.0.0.1:8002/llmsocket/8002
export FREECIV_API_TOKEN='<proxy API token>'
export FREECIV_SERVER_CONTAINER=fciv-net
export OLLAMA_OPENAI_BASE_URL=http://127.0.0.1:11434/v1
```

Configuration ownership is deliberate:

| Setting | Source |
|---|---|
| capabilities, belief confidence/decay, sweeps, PF-PLN runtime support | `profile/freeciv_agent.yaml` |
| ruleset, seeds, opponent, statistics, model budget | `profile/freeciv_harness.yaml` |
| provider endpoint/model mapping | `profile/llm_providers.yaml` |
| proxy endpoints, token, container, source discovery | environment variables above |

The impact policy also versions a 0.3-second accepted-action refresh deadline
and a 50 ms two-sample stability interval. A changed fingerprint resets the
sample count; the interval is not a single-sample shortcut.

The configured evaluation model is `qwen3-coder-next:latest`, temperature `0`, with
Ollama thinking mode explicitly disabled and a 30-second whole-turn budget. The task
requires a bounded JSON proposal rather than a reasoning trace; the `think: false`
setting is versioned in both harness profiles and retained in manifests. The
`selection_call_policy: canonical-singleton-bypass-v1` setting also fails
closed: a constrained turn skips model selection only when the canonical
catalog has exactly one candidate. An active research target is treated as
that single candidate only while the exact legal-action catalog contains no
new research selection. The
`readiness_policy: chat-once-expiry-aware-resident-v2` setting performs one
complete chat validation per controller/model tuple. A later arm can reuse the
locked exact-model residency check only when `expires_at` is valid and at least
`readiness_residency_floor_seconds: 300` seconds away. Otherwise it refreshes
keep-alive without completion tokens and falls back to complete chat validation
if that refresh fails. A local Ollama installation needs no API key unless its
own deployment enforces one.

```bash
ollama pull qwen3-coder-next:latest
ollama list | grep 'qwen3-coder-next:latest'
python3 scripts/freeciv/test_ollama_proposer.py
```

## 4. Compile and audit both rulesets

Generated rules are ignored build artifacts. Both rulesets use the same compiler path.

```bash
python3 scripts/freeciv/compile_ruleset.py \
  --ruleset-root "$FREECIV_RULESET_ROOT" --ruleset civ2civ3 \
  --out build/freeciv/rulesets/civ2civ3
python3 scripts/freeciv/compile_ruleset.py \
  --ruleset-root "$FREECIV_RULESET_ROOT" --ruleset classic \
  --out build/freeciv/rulesets/classic
```

Each output contains canonical IR, generated MeTTa, grounded signatures, independent audit,
and a hash manifest. Repeating either command in a clean output directory must be byte
identical.

## 5. Test lanes

Run the complete FreeCiv domain lane:

```bash
FREECIV_RULESET_ROOT="$FREECIV_RULESET_ROOT" \
PYTHONPATH=src:benchmarks \
python3 -m pytest -q Autotests/test_freeciv_*.py
```

Run the original focused transport/regression lane:

```bash
python3 -m pytest -q \
  Autotests/test_freeciv_agent_foundation.py \
  Autotests/test_freeciv_adapter.py Autotests/test_freeciv_client_ws.py \
  Autotests/test_freeciv_turn_cycle.py Autotests/test_freeciv_ab.py \
  Autotests/test_metta_sessions.py Autotests/test_tracing.py \
  Autotests/test_memory_schema.py Autotests/test_scheduler.py
```

Run the UI lane:

```bash
npm --prefix apps/freeciv-observability test
```

That command type-checks, validates every tracked event fixture, enforces the event-only
dependency boundary, runs unit/as-of/performance/live tests, and builds production assets.

## 6. Native dependency parity

Build or select the pinned native parity image, then run 50 randomized states for every
technology in each ruleset:

```bash
scripts/freeciv/build_native_parity_image.sh \
  "$FREECIV_LLM_ROOT/freeciv/freeciv" freeciv-research-parity:local
python3 scripts/freeciv/run_engine_parity.py \
  --ruleset-root "$FREECIV_RULESET_ROOT" --ruleset civ2civ3 \
  --states 50 --seed 20260717 --out artifacts/freeciv/m1-parity/civ2civ3-parity.json
python3 scripts/freeciv/run_engine_parity.py \
  --ruleset-root "$FREECIV_RULESET_ROOT" --ruleset classic \
  --states 50 --seed 20260717 --out artifacts/freeciv/m1-parity/classic-parity.json
```

The expected acceptance result is 4,350 comparisons and zero mismatches per ruleset.

## 7. Live smoke and state parity

First verify the transport without external services:

```bash
python3 scripts/freeciv/smoke.py --mode fixture
```

Then run one real turn:

```bash
export FREECIV_GAME_ID=pln-freeciv-smoke-$(date +%s)
export FREECIV_TURNS=1
python3 scripts/freeciv/smoke.py --mode live
```

Success means authentication, populated authoritative state, local rejection of an invalid
action, submission of an exact server-advertised action, and a monotonic turn advance.

For the full M2/M3/V5 engine comparator:

```bash
python3 scripts/freeciv/run_live_state_parity.py \
  --ws-url "$FREECIV_PROXY_WS" --api-token "$FREECIV_API_TOKEN" \
  --game-id pln-state-parity --agent-id pln-state-parity --port 6001 \
  --turns 100 --seed 613 \
  --events artifacts/freeciv/state-parity/events.jsonl
```

Use a dedicated port from 6001-6009. Do not run another live harness against the same port.

## 8. Harness runs

The fast representative backend is deterministic and exercises the complete 250-job matrix:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/m7-representative --backend representative --workers 4 --no-resume
```

A small real-engine smoke uses the same condition implementations and pinned seed prefix:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/m7-engine-smoke --backend engine-live \
  --workers 1 --limit-seeds 1 --main-only --condition e_full_loop
```

The release matrix omits `--limit-seeds` and `--main-only`. It requires 30 main games per
condition, 20 sequential induction games for each memory-enabled condition, and 30 games per
graded/ungraded arm. Runs are resumable only when the persisted manifest identity and current
configuration hash match exactly.

The real 200-turn full-loop latency gate uses the versioned away-opponent profile so
elimination cannot truncate the measurement:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness_200_turn.yaml \
  --out artifacts/freeciv/m6-engine-200-turn --backend engine-live \
  --workers 1 --limit-seeds 1 --main-only --condition e_full_loop
```

## 9. Replay and live observability

Generate compact and 200-turn logs if no engine log is available:

```bash
python3 scripts/freeciv/generate_synthetic_log.py \
  --all --out artifacts/freeciv/v0-synthetic --overwrite
```

Start the application:

```bash
npm --prefix apps/freeciv-observability run dev -- --port 4178
```

Load a JSONL file through the Replay control. For the persisted-first live path, start the
read-only tail in another terminal:

```bash
PYTHONPATH=src python3 scripts/freeciv/serve_event_tail.py \
  --events artifacts/freeciv/v5-live-200/events.jsonl \
  --game-id pln-v5-live-200 --host 127.0.0.1 --port 8765
```

In the UI set the endpoint to `ws://127.0.0.1:8765`, set the matching game ID, and choose
Live. Replay and live events use the same parser, validator, fold, indexes, and views.

Compare every turn cursor after a soak:

```bash
apps/freeciv-observability/node_modules/.bin/vite-node \
  apps/freeciv-observability/scripts/compare-live-replay.ts \
  --events artifacts/freeciv/v5-live-200/events.jsonl \
  --output artifacts/freeciv/v5-live-200/equivalence.json
```

## 10. Final release audit

First replay all ten canonical PF-PLN phase gates and verify their checked
evidence fingerprints:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/audit_pf_pln.py \
  --workers 4 \
  --output artifacts/freeciv/pf-pln-release-audit/report.json
```

Use a completed full-loop trace that includes a planned non-control action:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/audit_release.py \
  --ruleset-root "$FREECIV_RULESET_ROOT" \
  --freeciv-llm-root "$FREECIV_LLM_ROOT" \
  --events path/to/e_full_loop/events.jsonl \
  --require-cognitive-trace \
  --output artifacts/freeciv/release-audit/report.json
```

The command audits handwritten rules, independent compilation, numeric-inference separation,
declared confidence parameters, raw-state/LLM isolation, UI boundaries, workstation paths,
the pinned proxy patch, event validity and volume, invalid-plan exclusion, and complete
cognitive action ancestry. It also embeds the PF-PLN audit, so a missing phase,
drifted benchmark/evidence fingerprint, incomplete phase-map row, or stale
generated event type fails the complete release.

For each game, inspect `manifest.json` → `pf_pln_runtime` for the activation
hash and per-phase reasons. The event stream repeats the same boundary as ten
turn-0 `pf_pln_phase_enabled` metric declarations. See
`docs/freeciv/pf-pln-runtime.md` for the current engine/component matrix.

Failure recovery and operational checks are in `docs/freeciv/operations.md`. Protocol and
DTO details are in `docs/freeciv/integration-contract.md` and `docs/freeciv/state-bridge.md`.
