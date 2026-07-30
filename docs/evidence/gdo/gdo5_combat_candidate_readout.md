# GDO-5 combat candidate readout correction

Status: captured candidate-recall mechanism gate passed; execution and gameplay
gates remain open

Date: 2026-07-30

Branch: `experimental/pln-pressure–bridge–fluid`

## Claim boundary

The corrected readout recovers safe, server-advertised attacks in all five
retained joint-combat snapshots that the prior garrison rule suppressed.
This is a candidate-recall and safety result. It does not establish operation
execution, target neutralization, material advantage, score improvement, or
win-rate improvement.

## Root cause

The planner formerly used the final mood value
`happy - unhappy - 2 * angry` as both a disorder margin and a proxy for the
number of defenders that had to remain in a city. A stable all-content city
has a final margin of zero. The old `margin <= 1` rule therefore classified
that healthy state as near disorder and reserved as many defenders as the
configured city limit.

In the retained turn-68 through turn-70 states, Roma had:

- six citizens;
- no disorder;
- final mood of zero happy, six content, zero unhappy, zero angry;
- three local attack-capable units;
- two unhappy citizens before the packet's martial-law stage and zero after.

The old rule required all three defenders and removed every exact visible
attack from the candidate set. This happened before scalar PF-v2 could score
the actions. Faster flow or different pressure weights could not repair the
missing candidates.

## Correction

`grounded-impact-planner/1.35` now reads the protocol-ordered citizen mood
stages:

- stage index 3: before martial-law effects;
- stage index 4: after martial-law effects;
- final stage: authoritative post-effect mood.

It measures the observed reduction in disorder burden across the martial-law
stage. Positive final mood margin offsets that burden. Each remaining relief
point conservatively reserves at most one defender, bounded by the existing
military-unit limit. Explicitly disordered cities retain the prior
fail-closed protection.

For the captured states:

| Turns | Local defenders | Prior requirement | Corrected requirement | Safe single-step attack recalled |
| --- | ---: | ---: | ---: | ---: |
| 68, 69, 70 | 3 | 3 | 2 | yes |
| 72, 72 refresh | 3 | 3 | 1 | yes |

The one-step condition is important. At every readout, removing one acting
unit still leaves at least the corrected required garrison. Later operation
steps remain subject to a new snapshot, new candidate enumeration, and exact
commit revalidation.

## Captured replay

The retained command is:

```bash
python3 scripts/run_gdo_combat_candidate_readout_replay.py \
  --manifest benchmarks/gdo/captured_snapshots/combat_operations_native_160_manifest.json \
  --iterations 100 \
  --output benchmarks/gdo/gdo5_combat_candidate_readout_diagnostic.json
```

The report hash is:

```text
62b726a44d4cdce71f56e84e7b2cce190f03bc50d88f491e7bab41abed9899d7
```

All seven declared gates pass. The previous rule suppresses all five retained
joint states; the corrected readout recalls at least one exact attack in all
five; every recalled single step preserves the grounded garrison requirement;
and readout digests are deterministic. Across 500 candidate-enumeration
samples, latency was 3.01 ms mean, 3.05 ms p95, and 13.50 ms maximum.

## Fresh engine pilot

A fresh 160-turn same-seed run was executed after the correction:

```bash
FREECIV_PROXY_WS=ws://127.0.0.1:8002/llmsocket/8002 \
FREECIV_API_TOKEN=test-token-fc3d-001 \
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_SERVER_CONTAINER=fciv-net \
OLLAMA_OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/gdo5-combat-readout-pilot-v1 \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6100 \
  --limit-seeds 1 --condition e_full_loop --main-only --no-resume
```

The run completed 160 turns with zero experiment failures, zero infrastructure
failures, zero rejected engine actions, and a valid 12,298-event trace. Its
`events.jsonl` SHA-256 is:

```text
574a07107236e74ca103eb1e2a61dca79a7cba9d1c3543ad33bda37e527cf918
```

The trace contained six native combat-probability rows, but never two actors
against the same target. It therefore contained zero eligible joint-combat
operations and cannot validate execution of the corrected joint readout. No
`unit_attack` action was submitted. This is an opportunity-absent pilot, not a
negative execution result and not an outcome comparison.

## Decision

The demonstrated pre-score suppression bug is fixed and protected by both a
small unit regression and a replay over all retained player-visible engine
fixtures. The next GDO-5 experiment must obtain a fresh joint opportunity and
actual matching scalar action, or introduce a separately gated, decision-safe
slice authority. Until then combat operations remain shadow-only and the
score/win-rate claim remains unchanged.
