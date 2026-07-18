# Phase 0 acceptance evidence

- Date: 2026-07-17 UTC
- Branch: `feature/pln-freeciv-agent`
- Repository base commit: `6cdef39c` (full commit recorded in each manifest)
- FreeCiv/proxy source: `26ba7124249f34fd3050ef29bf191bd4d8808018`
- OmegaClaw image: `sha256:d6c9fe0cba1c47381c3be88f294f837972e621a164ce639efa5dd84b81eadac0`
- Provider/model: `Ollama-local` / `qwen3-coder-next:latest`

## Acceptance results

| Criterion | Result | Evidence |
|---|---|---|
| P0.A1 focused regression | PASS | `94 passed, 6 skipped in 21.48s` across the foundation, FreeCiv, sessions, tracing, memory, and legacy scheduler tests |
| P0.A2 manifested baseline | PASS | One-turn stock plain-LLM run; 3 proposed, 3 submitted, 0 blocked, turn 1 -> 2; ignored artifact `artifacts/freeciv/phase0-baseline-live` |
| P0.A3 live smoke | PASS | Authenticated player 0, populated 7 units, rejected unknown unit locally with `E201`, canonical end-turn advanced 1 -> 2 |
| P0.A4 deterministic identity | PASS | Unit tests show run ID/time/host do not affect identity, while seed/model do; tampering is rejected |
| P0.A5 portable paths | PASS | Domain package scan rejects `/home/`; external source is discovered only through argument or `FREECIV_LLM_ROOT` and recorded by commit |
| P0.A6 decisions | PASS | ADRs 0001-0005 are accepted under `docs/architecture/freeciv` |

## Baseline artifact hashes

| Artifact | SHA-256 |
|---|---|
| `manifest.json` | `d081e1b839865c98963bbe8af4a2f76f741643370cb42fa1a9bf6238aa28340f` |
| `plain.jsonl` | `9a8c9e1cc576abfecaf5125e6b599b7357037c871066f556a4abfb9175c20192` |
| `plain_summary.json` | `0973cdbd99be225147bed4127a3a3d5314efb7ce3f01d1170f4d7d805378ba02` |
| `run_status.json` | `12be49a331e1dabeb834fd5b4c0c3e7dd8b2cbe5cdc8353dee85834c7b860a49` |

The manifest identity for this run is
`aadb58623172d257c40ca0172f1e7cff0378e8d962714b15fe713cc38070d769`.
It records that the repository was dirty, plus the dirty-patch hash; the artifact is not
misrepresented as a clean committed release.

## Commands

```bash
PYTHONPATH=src python3 -m freeciv_agent.config
python3 scripts/freeciv/smoke.py --mode fixture
FREECIV_TURNS=1 python3 scripts/freeciv/smoke.py --mode live
python3 scripts/freeciv/run_baseline.py --game-id phase0_baseline_live_20260717 \
  --seed 42 --max-turns 1 --out artifacts/freeciv/phase0-baseline-live \
  --provider Ollama-local --freeciv-llm-root "$FREECIV_LLM_ROOT" \
  --engine-image-digest sha256:d6c9fe0cba1c47381c3be88f294f837972e621a164ce639efa5dd84b81eadac0
pytest -q Autotests/test_freeciv_agent_foundation.py \
  Autotests/test_freeciv_adapter.py Autotests/test_freeciv_client_ws.py \
  Autotests/test_freeciv_turn_cycle.py Autotests/test_freeciv_ab.py \
  Autotests/test_metta_sessions.py Autotests/test_tracing.py \
  Autotests/test_memory_schema.py Autotests/test_scheduler.py
```

The live command requires the endpoint/token environment described in
`docs/freeciv/setup.md`; no credential is retained here.

