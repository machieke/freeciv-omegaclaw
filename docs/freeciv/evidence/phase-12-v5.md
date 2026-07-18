# Phase 12 / V5 evidence

Date: 2026-07-18 UTC

## Live/replay data path

`PersistedEventTail` reads only newline-complete durable records, subscribes after a
`(game_id, turn, seq)` cursor, and backfills before following new appends. It rejects
wrong games/schema versions, gaps, duplicates, out-of-order cursors, and truncation.
The browser sends live records through the same validation, indexes, and `foldEvents`
function used for file replay. Writer reconstruction validates the existing log and
continues the sequence.

## 200-turn soak

`artifacts/freeciv/v5-live-200/report.json` records:

- 200 verified engine turns;
- 200 accepted random advertised actions plus 200 accepted end-turns;
- zero engine rejections and zero planned-action rejections;
- 199 stale prior-snapshot attempts blocked locally;
- 3,803 schema/causally valid events, 3,277,282 bytes;
- event SHA-256 `daf7c342abb3998a1a88bb692d450c4d6fc4d85fe2f810d209502c1609f97eff`.

`equivalence.json` compares live incremental state with fresh replay at 201 cursors
and records zero divergence. The log is far below the 5 MB/turn budget.

## Acceptance results

- P12.A1: 201/201 sampled/final cursors are identical.
- P12.A2: forced disconnect resumes after the last cursor with no missing or
  double-applied record.
- P12.A3: reconstructed writer plus UI/tail restart retains causal completeness and
  deterministic replay.
- P12.A4: the full log is 3.28 MB total and information-loss-free.
- P12.A5: `docs/freeciv/release-checklist.md` maps all phase criteria to commands and
  evidence without implicit waiver.
- P12.A6: `docs/freeciv/setup.md` provides the clean compiler/test/live-smoke/UI/
  small-harness sequence and exact required environment.

## Final invariant audit

`artifacts/freeciv/release-audit-final/report.json` audits both the final-identity
M7 engine trace and the real 200-turn Qwen trace with
`--require-cognitive-trace`. All ten checks pass: no handwritten game rules, no
UI/agent boundary violation, query-summary-only LLM input, all confidence
parameters declared, both compiled rulesets independently audited, no numeric
accumulation through inference, no workstation paths, exact pinned external patch
identity, and schema/causally valid cognitive action chains in both traces.

The audited M7 trace contains 609 events, 14 confidence declarations, one planned
cognitive engine action with no incomplete ancestry, maximum 29,083 bytes/turn, and
event SHA-256 `1bda7f8e7da8b43ffd26691293267f6c90b4ba6f5cb0554c718865ee5d43ff46`.
The audited 200-turn trace contains 4,126 events, the same 14 declarations, one
complete planned-action ancestry, maximum 253,420 bytes/turn, and event SHA-256
`a9cf20de0cbc93907789ba7f0dcd2728bd0b64d67665d0d25ef3faaf484374ba`.
The final two-trace audit report SHA-256 is
`45760d32c7bf14c7c3dbc039660783ee4e3284f44dc05e5e826c065ebe5cd0e6`.

## Final regression results

- 152/152 focused Python FreeCiv tests pass.
- 18/18 observability tests pass with strict TypeScript typecheck, valid fixtures,
  a production build, zero boundary violations, and zero npm audit vulnerabilities
  at the configured level.
- 12/12 focused tests pass in the patched upstream proxy container.
- The live proposer returns schema-valid output from
  `qwen3-coder-next:latest` with explicit `think: false`.
- Reverse applicability of the retained upstream patch passes at pinned checkout
  `26ba7124249f34fd3050ef29bf191bd4d8808018`.
- The final M7 identity audit finds exactly 250 completed manifests, 250 distinct
  behavioral identities, 250 distinct final attempt IDs, and zero non-completed
  current slots.
- `git diff --check` passes and the release checklist contains no pending entry.

## Repeatable commands

```bash
pytest -q Autotests/test_freeciv_events.py
npm --prefix apps/freeciv-observability test -- --run
npx --prefix apps/freeciv-observability vite-node \
  apps/freeciv-observability/scripts/compare-live-replay.ts \
  --events artifacts/freeciv/v5-live-200/events.jsonl
```

The static/dynamic invariant output is written by
`scripts/freeciv/audit_release.py`. The final release report is
`artifacts/freeciv/release-audit-final/report.json` and requires complete cognitive
ancestry in both the current M7 and 200-turn engine traces.
