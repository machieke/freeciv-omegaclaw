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
`scripts/freeciv/upstream/0005-pln-sustainability-control.patch`, and
`scripts/freeciv/upstream/0006-pln-city-food-governor.patch`, and
`scripts/freeciv/upstream/0007-pln-government-transition.patch`, and
`scripts/freeciv/upstream/0008-pln-disorder-luxury-recovery.patch`,
`scripts/freeciv/upstream/0009-pln-strategic-observability.patch`, and
`scripts/freeciv/upstream/0010-pln-ruleset-name-sanitization.patch`, and
`scripts/freeciv/upstream/0011-pln-government-state-correction.patch`, and
`scripts/freeciv/upstream/0012-pln-city-ownership-reconciliation.patch`, and
`scripts/freeciv/upstream/0013-pln-native-movement-routes.patch`, and
`scripts/freeciv/upstream/0014-pln-known-terrain-semantics.patch`, and
`scripts/freeciv/upstream/0015-pln-route-refresh-validity.patch`, and
`scripts/freeciv/upstream/0016-pln-native-combat-probabilities.patch`. The
application script verifies every digest, is idempotent, rejects a different upstream
commit, and supports normal checkouts and Git worktrees. It adds the
`pln_authoritative` DTO, monotonic packet sequence, bounded and conditional
source-stability waiting, settled turn-boundary projections, atomic
packet/projection construction, exact packet-known tiles and visibility,
release-game configuration, canonical executable actions, ruleset readiness,
government selection after revolutions, city sustainability and unit support
state, ruleset-aware net gold, city-surplus and upkeep telemetry, bounded tax/science controls,
exact unit rehoming, causal unit-removal attribution, bounded server-side
food-surplus governance, stable-government revolution initiation, exact
post-revolution recovery, bounded packet-exact tax/luxury/science transitions,
optional city-local `require_happy` governance, captured-city ownership
reconciliation from `PACKET_CITY_SHORT_INFO`, stale city-internal eviction, and
proxy contract tests. Patch 0013 adds bounded, opt-in server-pathfinder route
requests for own units to own cities. Responses include explicit
reachable/unreachable status, native ETA, total and first-edge movement cost,
remaining movement, and first-step identity; the proxy exposes only routes
that still match the exact unit origin, movement allowance, transport state,
and turn.
Patch 0014 enriches only packet-known tiles with public ruleset terrain name,
land/ocean class, and native unit-class membership. This supports conservative
player-information-safe reachability checks without querying hidden map state
or enemy routes.
Patch 0015 keeps a native route request pending until a response matches the
unit's current origin, movement allowance, transport state, destination, and
turn. A stale same-key cache entry therefore cannot masquerade as a completed
fresh route query.
Patch 0016 adds bounded, opt-in native combat probability requests for
current advertised combat actions against packet-visible adjacent targets.
The projection records the server-selected defender and preserves probability
intervals without inventing combat modifiers. Exact actor and target-stack
revision checks prevent stale or cross-state results from entering a snapshot.
The final sanitizer patch permits legitimate ruleset tokens such as
`Labor Union` while retaining the compound `UNION SELECT` rejection and exact
server-advertised technology validation.

Engine-live fixed-horizon games configure `victories=SPACERACE` with
`endspaceship=false`. This retains spaceship construction and arrival behavior
but prevents it from truncating the declared turn horizon; allied and culture
victories are excluded. Conquest remains a genuine terminal outcome. The proxy
projects the cross-connection game-over flag into `pln_authoritative` state so a
real terminal report is scored rather than retried as a missing turn.

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

The live harnesses configure `preferred_government: ""`, which disables
transition initiation after two 480-turn Monarchy cohorts regressed materially.
They also configure `government_economic_gate_enabled: false`. The optional
gate requires a positive declared `government_expected_operating_gold_gain`,
prices current productive output over `government_transition_cost_turns`, and
caps payback at `government_maximum_payback_turns`. A later matched 240-turn
gate diagnostic still scored 201 under Monarchy versus 202 under Despotism, so
the additional gate did not justify enabling the policy.
The proxy still advertises every exact legal alternative. Once a revolution has
already started, recovery remains mandatory and uses the packet-declared
intended target whenever it remains legal, regardless of remaining horizon.
`disorder_luxury_recovery_enabled` and
`city_happiness_governor_enabled` are also false in live profiles. Their exact
actions remain available for explicit diagnostic ablations but cannot alter a
release game by default. The bounded luxury diagnostic additionally accepts
`disorder_luxury_trigger_turns`, `disorder_luxury_minimum_city_size`, and
`disorder_luxury_bridge_max_turns`; these settings are inert while recovery is
disabled.

Live profiles set `structural_economy_maximum_completion_turns: 20`.
Ruleset-driven commerce repair may use Coinage as a temporary bridge only when
the post-switch cash flow is nonnegative, twice the ordinary treasury reserve
survives construction plus upkeep, and no other structural commerce project is
active. The exact selected queue is held through completion. This is the
accepted adapter-1.33 boundary; longer or reserve-consuming variants are
documented as rejected engine ablations.

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

To run the rich Functional Dependent AtomSpace as a read-only shadow, keep the
checked default unchanged and select the versioned sampled profile for that
process only:

```bash
export FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_shadow_sampled.yaml
```

The harness embeds the resolved declaration, source path, capability manifest,
and structural hash in every run manifest. This profile verifies a deterministic
5% sample against a cold build and leaves aggregate and per-domain action
authority disabled.

Configuration ownership is deliberate:

| Setting | Source |
|---|---|
| capabilities, belief confidence/decay, sweeps, PF-PLN runtime support | `profile/freeciv_agent.yaml` |
| ruleset, seeds, opponent, statistics, model budget | `profile/freeciv_harness.yaml` |
| provider endpoint/model mapping | `profile/llm_providers.yaml` |
| optional manifest-bound FDAS experiment profile | `FREECIV_FDAS_CONFIG_PATH` |
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
  --game-id pln-v5-live-200 --host 127.0.0.1 --port 18765
```

In the UI set the endpoint to `ws://127.0.0.1:18765`, set the matching game ID, and choose
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
